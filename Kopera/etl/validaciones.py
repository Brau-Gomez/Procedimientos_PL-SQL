"""
Validaciones de negocio: replica en Python las reglas de los triggers de Oracle.

Los triggers de la Evaluacion 2 (Kopera/sql/04_triggers.sql)
definen las reglas de integridad del negocio. En Atlas NO hay triggers (el tier
M0 de Atlas no permite Atlas Triggers ni Functions), asi que esas reglas se
replican en Python, en la capa de aplicacion.

NO es una duplicacion inutil: es la traduccion del modelo relacional (reglas
en el motor) al modelo documental (reglas en la aplicacion). Cada funcion de
este modulo tiene su trigger de referencia en el comentario.

Las 4 reglas replicadas:

  REGLA 1  trg_cuota_valida_pago
           El pago debe estar entre cero y el valor de la cuota, y el saldo
           se DERIVA: saldo = valor_cuota - monto_pagado.

  REGLA 2  trg_cuota_bitacora
           Solo se registra el evento si el monto pagado cambio de verdad
           (monto_anterior distinto de monto_nuevo).

  REGLA 3  trg_movimiento_valida
           El monto del movimiento debe ser positivo, el tipo debe ser ABONO
           o RESCATE, y un RESCATE no puede exceder el ahorro disponible ni
           el porcentaje maximo contractual.

  REGLA 4  trg_movimiento_actualiza_ahorro
           El saldo de la inversion se actualiza sumando el abono o restando
           el rescate.

DISTINCTION IMPORTANTE entre error y observacion:

  - ERROR       : la operacion propuesta violaria una regla. Se rechaza,
                  igual que haria el trigger (RAISE_APPLICATION_ERROR).
  - OBSERVACION : la inconsistencia ya existe en los datos migrados (la
                  semilla BD_KOPERA.SQL se cargo sin pasar por los triggers).
                  No se bloquea la carga: se informa, porque son datos
                  historicos que el reporte debe conocer.

Los codigos de error replican los del PL/SQL (-20001, -20010, ...), para que
el informe pueda comparar el comportamiento de Oracle y de MongoDB.
"""

from dataclasses import dataclass, field
from decimal import Decimal

# Codigos de error (identicos a los del PL/SQL)
CODIGO_ERROR_PAGO_FUERA_DE_RANGO = -20001
CODIGO_ERROR_MONTO_NO_POSITIVO = -20010
CODIGO_ERROR_TIPO_MOVIMIENTO = -20011
CODIGO_ERROR_RESCATE_EXCEDE_SALDO = -20012
CODIGO_ERROR_RESCATE_EXCEDE_PORCENTAJE = -20013
CODIGO_ERROR_NO_EXISTE = -20014

TIPOS_MOVIMIENTO_VALIDOS = ("ABONO", "RESCATE")


@dataclass
class ResultadoValidacion:
    """
    Resultado de una validacion.

    valido        : True si no hay errores (las observaciones no invalidan).
    errores       : lista de dicts {codigo, mensaje}.
    observaciones : lista de dicts {codigo, mensaje} sobre datos preexistentes.
    datos         : valores derivados que la regla produce (saldo, etc.).
    """

    valido: bool = True
    errores: list = field(default_factory=list)
    observaciones: list = field(default_factory=list)
    datos: dict = field(default_factory=dict)

    def agregar_error(self, codigo, mensaje):
        self.valido = False
        self.errores.append({"codigo": codigo, "mensaje": mensaje})

    def agregar_observacion(self, codigo, mensaje):
        self.observaciones.append({"codigo": codigo, "mensaje": mensaje})

    def resumen(self):
        """Resumen de una linea, util para los reportes."""
        if self.valido and not self.observaciones:
            return "VALIDO"
        partes = []
        if not self.valido:
            partes.append(f"{len(self.errores)} error(es)")
        if self.observaciones:
            partes.append(f"{len(self.observaciones)} observacion(es)")
        return ", ".join(partes)


def _decimal(valor):
    """Convierte a Decimal para hacer las comparaciones monetarias exactas."""
    if valor is None:
        return Decimal("0")
    return Decimal(str(valor))


# ==========================================================================
# REGLA 1 - trg_cuota_valida_pago
# ==========================================================================

def validar_pago_cuota(valor_cuota, monto_pagado, saldo_actual=None):
    """
    REGLA 1 (trg_cuota_valida_pago).

    Valida que el pago este entre cero y el valor de la cuota, y devuelve el
    saldo DERIVADO (saldo = valor_cuota - monto_pagado), que es lo que el
    trigger asigna a :NEW.saldo_por_pagar.

    Parametros:
        valor_cuota   : valor nominal de la cuota.
        monto_pagado  : monto pagado acumulado (puede ser None).
        saldo_actual  : saldo que hay hoy en la cuota; si no coincide con el
                        derivado, se reporta como observacion (inconsistencia
                        heredada de la semilla).

    Retorna ResultadoValidacion con datos["saldo_por_pagar"] y
    datos["monto_pagado"] normalizados.
    """
    resultado = ResultadoValidacion()

    valor = _decimal(valor_cuota)
    monto = _decimal(monto_pagado if monto_pagado is not None else 0)

    # El trigger compara con NVL(:NEW.monto_pagado,0): un NULL cuenta como 0.
    if monto < 0 or monto > valor:
        resultado.agregar_error(
            CODIGO_ERROR_PAGO_FUERA_DE_RANGO,
            "El pago debe estar entre cero y el valor de la cuota. "
            f"(monto={monto}, valor_cuota={valor})",
        )

    # El trigger DERIVA el saldo; no lo toma de la entrada.
    saldo_derivado = valor - monto

    if saldo_actual is not None and _decimal(saldo_actual) != saldo_derivado:
        resultado.agregar_observacion(
            CODIGO_ERROR_PAGO_FUERA_DE_RANGO,
            f"Saldo almacenado ({saldo_actual}) distinto del derivado "
            f"por la regla 1 ({saldo_derivado}).",
        )

    resultado.datos["monto_pagado"] = int(monto)
    resultado.datos["saldo_por_pagar"] = int(saldo_derivado)
    return resultado


# ==========================================================================
# REGLA 2 - trg_cuota_bitacora
# ==========================================================================

def construir_evento_bitacora(cuota, nro_cliente, monto_anterior, monto_nuevo,
                              forma_pago, nro_credito=None, fecha_evento=None,
                              id_bitacora=None):
    """
    REGLA 2 (trg_cuota_bitacora).

    El trigger registra el evento SOLO si el monto pagado cambio de verdad:

        WHEN (NVL(NEW.monto_pagado,-1) <> NVL(OLD.monto_pagado,-1))

    Si no hubo cambio, devuelve None (no hay evento que registrar). Si lo
    hubo, devuelve el documento de auditoria con los mismos campos que la
    tabla BITACORA_PAGO_CUOTA de Oracle.

    Ojo: la cuota embebida en el documento del cliente NO tiene
    nro_solic_credito (el credito es el array que la contiene) ni fecha de
    evento (la del pago la genera el trigger). Por eso ambos valores se
    reciben como parametros y no se leen de la cuota.
    """
    # El -1 es el valor centinela del trigger para un NULL: un NULL anterior
    # y un 0 nuevo SI son un cambio real.
    anterior = -1 if monto_anterior is None else _decimal(monto_anterior)
    nuevo = -1 if monto_nuevo is None else _decimal(monto_nuevo)

    if anterior == nuevo:
        return None

    valor_cuota = _decimal(cuota.get("valor_cuota"))
    saldo_resultante = valor_cuota - nuevo if nuevo >= 0 else valor_cuota

    credito = nro_credito if nro_credito is not None else cuota.get("nro_solic_credito")

    evento = {
        "nro_solic_credito": credito,
        "nro_cuota": cuota.get("nro_cuota"),
        "nro_cliente": nro_cliente,
        "fecha_evento": fecha_evento,
        "usuario_evento": "PYTHON (replica de trg_cuota_bitacora)",
        "monto_pagado_anterior": None if monto_anterior is None else int(_decimal(monto_anterior)),
        "monto_pagado_nuevo": int(nuevo),
        "valor_cuota": int(valor_cuota),
        "saldo_resultante": int(saldo_resultante),
        "cod_forma_pago": cuota.get("cod_forma_pago"),
        "forma_pago": forma_pago,
        "origen": "Python (replica de trg_cuota_bitacora)",
    }

    if id_bitacora is not None:
        evento["_id"] = id_bitacora

    return evento


# ==========================================================================
# REGLA 3 - trg_movimiento_valida
# ==========================================================================

def validar_movimiento(inversion, monto, tipo_movimiento):
    """
    REGLA 3 (trg_movimiento_valida).

    Valida un movimiento nuevo contra la inversion embebida en el documento
    del cliente:

        inversion = {
            "nro_solic_prod": int,
            "monto_total_ahorrado": int,
            "producto": {"porc_maximo_rescate": int},
            "movimientos": [{"monto": int, "tipo_movimiento": "ABONO"/"RESCATE"}],
        }

    Retorna ResultadoValidacion con datos["saldo_actualizado"] (el saldo que
    dejaria la inversion con este movimiento) y datos["rescates_acumulados"].
    """
    resultado = ResultadoValidacion()

    monto_dec = _decimal(monto)

    # --- monto positivo ---
    if monto_dec <= 0:
        resultado.agregar_error(
            CODIGO_ERROR_MONTO_NO_POSITIVO,
            "El monto del movimiento debe ser positivo.",
        )
        # Con el monto invalido no se puede seguir calculando el saldo.
        return resultado

    tipo = (tipo_movimiento or "").strip().upper()

    # --- tipo valido ---
    if tipo not in TIPOS_MOVIMIENTO_VALIDOS:
        resultado.agregar_error(
            CODIGO_ERROR_TIPO_MOVIMIENTO,
            "Tipo de movimiento debe ser ABONO o RESCATE.",
        )
        return resultado

    saldo_actual = _decimal(inversion.get("monto_total_ahorrado"))

    # Rescates ya registrados: el trigger los suma de los movimientos
    # EXISTENTES del producto (antes de insertar el nuevo).
    rescates_acumulados = Decimal("0")
    for movimiento in inversion.get("movimientos", []):
        if (movimiento.get("tipo_movimiento") or "").strip().upper() == "RESCATE":
            rescates_acumulados += _decimal(movimiento.get("monto"))

    if tipo == "RESCATE":
        # --- el rescate no puede exceder el ahorro disponible ---
        if monto_dec > saldo_actual:
            resultado.agregar_error(
                CODIGO_ERROR_RESCATE_EXCEDE_SALDO,
                "El rescate excede el ahorro disponible.",
            )

        # --- el rescate acumulado no puede exceder el % contractual ---
        # El trigger compara:
        #   (v_rescates + nuevo) > ((v_saldo + v_rescates) * maximo / 100)
        # donde v_saldo es el saldo ACTUAL (ya descontados los rescates
        # anteriores) y v_rescates es la suma de los rescates ya hechos.
        maximo = _decimal(
            (inversion.get("producto") or {}).get("porc_maximo_rescate")
        )
        limite = (saldo_actual + rescates_acumulados) * maximo / Decimal("100")
        if rescates_acumulados + monto_dec > limite:
            resultado.agregar_error(
                CODIGO_ERROR_RESCATE_EXCEDE_PORCENTAJE,
                "El rescate acumulado excede el porcentaje permitido.",
            )

    # REGLA 4: el saldo resultante de la operacion.
    signo = 1 if tipo == "ABONO" else -1
    resultado.datos["saldo_actualizado"] = int(saldo_actual + signo * monto_dec)
    resultado.datos["rescates_acumulados"] = int(rescates_acumulados)
    resultado.datos["saldo_actual"] = int(saldo_actual)
    resultado.datos["signo"] = signo
    return resultado


# ==========================================================================
# REGLA 4 - trg_movimiento_actualiza_ahorro
# ==========================================================================

def calcular_ahorro_actualizado(inversion, monto, tipo_movimiento):
    """
    REGLA 4 (trg_movimiento_actualiza_ahorro).

    Devuelve el nuevo monto_total_ahorrado de la inversion:

        monto_total_ahorrado = monto_total_ahorrado
                               + monto  (ABONO)
                               - monto  (RESCATE)

    Es el mismo efecto del trigger AFTER INSERT.
    """
    saldo = _decimal(inversion.get("monto_total_ahorrado"))
    monto_dec = _decimal(monto)
    tipo = (tipo_movimiento or "").strip().upper()

    if tipo == "ABONO":
        return int(saldo + monto_dec)
    if tipo == "RESCATE":
        return int(saldo - monto_dec)
    # Tipo invalido: no se toca el saldo.
    return int(saldo)


# ==========================================================================
# CONTROL DE CALIDAD DEL DOCUMENTO YA MIGRADO
# ==========================================================================

def validar_documento_cliente(documento):
    """
    Revisa un documento de cliente ya migrado contra las reglas.

    Sirve como control de calidad POST-CARGA: comprueba que los saldos
    derivados y los limites se respeten en lo que quedo en Atlas.

    Las inconsistencias heredadas de la semilla se reportan como
    OBSERVACIONES, no como errores: no son operaciones nuevas, son el estado
    historico de los datos.
    """
    resultado = ResultadoValidacion()

    # --- REGLA 1 sobre todas las cuotas ---
    for credito in documento.get("creditos", []):
        for cuota in credito.get("cuotas", []):
            validacion = validar_pago_cuota(
                cuota.get("valor_cuota"),
                cuota.get("monto_pagado"),
                cuota.get("saldo_por_pagar"),
            )
            for error in validacion.errores:
                resultado.agregar_error(
                    error["codigo"],
                    f"Credito {credito.get('nro_solic_credito')}, "
                    f"cuota {cuota.get('nro_cuota')}: {error['mensaje']}",
                )
            for observacion in validacion.observaciones:
                resultado.agregar_observacion(
                    observacion["codigo"],
                    f"Credito {credito.get('nro_solic_credito')}, "
                    f"cuota {cuota.get('nro_cuota')}: {observacion['mensaje']}",
                )

    # --- REGLA 3 y REGLA 4 sobre todas las inversiones ---
    for inversion in documento.get("inversiones", []):
        # REGLA 3: el rescate acumulado debe respetar el % maximo.
        rescates_acumulados = Decimal("0")
        for movimiento in inversion.get("movimientos", []):
            if (movimiento.get("tipo_movimiento") or "").strip().upper() == "RESCATE":
                rescates_acumulados += _decimal(movimiento.get("monto"))

        saldo = _decimal(inversion.get("monto_total_ahorrado"))
        maximo = _decimal(
            (inversion.get("producto") or {}).get("porc_maximo_rescate")
        )
        limite = (saldo + rescates_acumulados) * maximo / Decimal("100")
        if rescates_acumulados > limite:
            resultado.agregar_error(
                CODIGO_ERROR_RESCATE_EXCEDE_PORCENTAJE,
                f"Inversion {inversion.get('nro_solic_prod')}: el rescate "
                f"acumulado ({int(rescates_acumulados)}) excede el limite "
                f"contractual ({int(limite)}).",
            )

        # REGLA 4: el saldo debe coincidir con la suma de los movimientos.
        # Ojo: en la semilla el saldo inicial NO proviene de movimientos
        # (el trigger solo lo ajusta con cada INSERT nuevo), asi que la
        # diferencia se informa como observacion.
        saldo_por_movimientos = Decimal("0")
        for movimiento in inversion.get("movimientos", []):
            signo = movimiento.get("signo")
            if signo is None:
                signo = 1 if (movimiento.get("tipo_movimiento") or "").upper() == "ABONO" else -1
            saldo_por_movimientos += signo * _decimal(movimiento.get("monto"))

        if saldo_por_movimientos != saldo:
            resultado.agregar_observacion(
                CODIGO_ERROR_NO_EXISTE,
                f"Inversion {inversion.get('nro_solic_prod')}: el saldo "
                f"almacenado ({int(saldo)}) no coincide con la suma de sus "
                f"movimientos ({int(saldo_por_movimientos)}); la diferencia "
                f"proviene del saldo inicial de la semilla.",
            )

    return resultado


def resumir_validaciones(resultados):
    """
    Resume una lista de ResultadoValidacion en un conteo, para el informe.
    """
    resumen = {
        "documentos_validados": len(resultados),
        "documentos_validos": 0,
        "documentos_con_observaciones": 0,
        "documentos_con_errores": 0,
        "total_errores": 0,
        "total_observaciones": 0,
        "errores_por_codigo": {},
        "observaciones_por_codigo": {},
    }

    for resultado in resultados:
        resumen["total_errores"] += len(resultado.errores)
        resumen["total_observaciones"] += len(resultado.observaciones)

        if resultado.errores:
            resumen["documentos_con_errores"] += 1
        else:
            resumen["documentos_validos"] += 1

        if resultado.observaciones:
            resumen["documentos_con_observaciones"] += 1

        for error in resultado.errores:
            clave = str(error["codigo"])
            resumen["errores_por_codigo"][clave] = \
                resumen["errores_por_codigo"].get(clave, 0) + 1

        for observacion in resultado.observaciones:
            clave = str(observacion["codigo"])
            resumen["observaciones_por_codigo"][clave] = \
                resumen["observaciones_por_codigo"].get(clave, 0) + 1

    return resumen
