"""
Operaciones de ESCRITURA de la app (la "C" y la "U" del CRUD).

Por que este modulo esta separado de consultas.py:
    leer es idempotente y sin riesgo; escribir no. Teniendo las escrituras en un
    solo archivo, queda claro que cualquier funcion de aca modifica la base y
    que todas verifican el resultado antes de informar exito.

Que se reutiliza y NO se duplica:
    - validaciones.py  -> las 4 reglas que replican los triggers de Oracle
                          (rango de pago, evento de auditoria, movimiento
                          valido y actualizacion del ahorro).
    - transformacion.py -> recalcular_analisis(), que deja el bloque `analisis`
                          del cliente igual que lo dejaria el ETL.

    Ambos modulos se importan desde Kopera/etl, montado como /etl en el
    contenedor. Si se copiaran las reglas aca, en dos semanas la app y el ETL
    dirian cosas distintas.

Por que el analisis se recalcula a mano:
    en Oracle los totales se calculan en cada consulta; en MongoDB el bloque
    `analisis` esta MATERIALIZADO. Si se actualiza una cuota y no se recalcula,
    el panel seguiria mostrando el saldo viejo. Es el precio del modelo
    documental y hay que pagarlo en cada escritura.
"""

import copy
import sys
from datetime import datetime
from pathlib import Path

from config_app import COLECCION_BITACORA, COLECCION_CLIENTES, obtener_base

# ==========================================================================
# Carga de los modulos del ETL
# ==========================================================================

def _cargar_modulos_etl():
    """
    Importa validaciones.py y transformacion.py desde Kopera/etl.

    Se buscan dos ubicaciones para que funcione igual en Docker (donde el
    directorio esta montado en /etl) y en local (streamlit run desde el repo).
    NO se importa etl/config.py: ese archivo hace `import oracledb` a nivel
    de modulo y arrastraria el driver de Oracle a la imagen.
    """
    candidatos = [
        Path("/etl"),
        Path(__file__).resolve().parent.parent / "etl",
        Path.cwd() / "Kopera" / "etl",
    ]

    for ruta in candidatos:
        if (ruta / "validaciones.py").exists():
            if str(ruta) not in sys.path:
                sys.path.insert(0, str(ruta))
            break
    else:
        raise RuntimeError(
            "No se encontró Kopera/etl. En Docker se monta como /etl "
            "(ver docker-compose.app.yml); en local debe existir junto a la app."
        )

    import transformacion  # noqa: PLC0415 - import diferido a proposito
    import validaciones  # noqa: PLC0415

    return validaciones, transformacion


# ==========================================================================
# Utilidades
# ==========================================================================

def _ahora() -> str:
    """Marca de tiempo en el mismo formato ISO que usa el ETL."""
    return datetime.now().isoformat(timespec="seconds")


def _buscar_cuota(documento, nro_credito, nro_cuota):
    """Devuelve (credito, cuota) dentro del documento, o (None, None)."""
    for credito in documento.get("creditos") or []:
        if credito.get("nro_solic_credito") != nro_credito:
            continue
        for cuota in credito.get("cuotas") or []:
            if cuota.get("nro_cuota") == nro_cuota:
                return credito, cuota
    return None, None


def _buscar_inversion(documento, nro_solic_prod):
    """Devuelve la inversion embebida, o None."""
    for inversion in documento.get("inversiones") or []:
        if inversion.get("nro_solic_prod") == nro_solic_prod:
            return inversion
    return None


def _error(mensaje: str, errores: list | None = None) -> dict:
    """Respuesta uniforme para las vistas cuando la operacion no procede."""
    return {
        "ok": False,
        "titulo": mensaje,
        "errores": errores or [],
    }


def _siguiente_id_bitacora() -> int:
    """
    Replica la secuencia IDENTITY de Oracle: maximo actual + 1.

    El validador de la coleccion exige que _id sea int, asi que no se puede
    dejar que MongoDB genere un ObjectId.
    """
    coleccion = obtener_base()[COLECCION_BITACORA]
    ultimo = coleccion.find_one(sort=[("_id", -1)])
    return 1 if ultimo is None else int(ultimo["_id"]) + 1


def _siguiente_nro_movimiento() -> int:
    """
    Numero correlativo global de movimiento.

    Se calcula sobre TODOS los clientes (no sobre uno): en la semilla el
    numero de movimiento es unico en toda la base, viene de la secuencia
    global de Oracle.
    """
    base = obtener_base()
    fila = next(iter(base[COLECCION_CLIENTES].aggregate([
        {"$unwind": "$inversiones"},
        {"$unwind": "$inversiones.movimientos"},
        {"$group": {"_id": None,
                    "maximo": {"$max": "$inversiones.movimientos.nro_movimiento"}}},
    ])), None)
    return 1 if not fila or fila.get("maximo") is None else int(fila["maximo"]) + 1


# ==========================================================================
# REGISTRAR PAGO DE CUOTA  (reglas 1 y 2)
# ==========================================================================

def registrar_pago(nro_cliente: int, nro_credito: int, nro_cuota: int,
                   monto_pago: int, forma_pago: str) -> dict:
    """
    Registra un pago sobre una cuota y deja el evento de auditoria.

    Pasos, en el mismo orden que la transaccion de Oracle:

      1. REGLA 1  validar el pago acumulado contra el valor de la cuota y
                  derivar el saldo (nunca se confia en un saldo de entrada).
      2. REGLA 2  construir el evento solo si el monto cambio de verdad.
      3. Escribir: $set de la cuota + $push del historial en UNA operacion,
                  para que el documento no quede a medias.
      4. Insertar el evento en bitacora_pagos.
      5. Releer y verificar antes de declarar exito.

    `monto_pago` es el monto que se paga AHORA; la regla 1 trabaja con el
    acumulado (monto anterior + este pago), igual que el trigger.
    """
    reglas, transform = _cargar_modulos_etl()
    base = obtener_base()

    documento = base[COLECCION_CLIENTES].find_one({"_id": int(nro_cliente)})
    if documento is None:
        return _error(f"No existe el cliente {nro_cliente}.")

    _, cuota = _buscar_cuota(documento, nro_credito, nro_cuota)
    if cuota is None:
        return _error(
            f"El cliente {nro_cliente} no tiene la cuota {nro_cuota} en el "
            f"crédito {nro_credito}."
        )

    anterior = int(cuota.get("monto_pagado") or 0)
    nuevo = anterior + int(monto_pago)

    # 1) REGLA 1
    validacion = reglas.validar_pago_cuota(
        cuota.get("valor_cuota"), nuevo, cuota.get("saldo_por_pagar")
    )
    if not validacion.valido:
        return _error(
            "El pago no cumple la regla 1 "
            "(el pago debe estar entre cero y el valor de la cuota).",
            [e["mensaje"] for e in validacion.errores],
        )

    saldo = validacion.datos["saldo_por_pagar"]
    if saldo == 0:
        estado = "PAGADA"
    elif nuevo > 0:
        estado = "PARCIAL"
    else:
        estado = cuota.get("estado")

    fecha_pago = _ahora()

    # 2) REGLA 2
    evento = reglas.construir_evento_bitacora(
        cuota, int(nro_cliente), anterior, nuevo, forma_pago,
        nro_credito=nro_credito,
        fecha_evento=fecha_pago,
        id_bitacora=_siguiente_id_bitacora(),
    )
    if evento is None:
        return _error(
            "No hubo cambio en el monto pagado: la regla 2 no registra eventos "
            "sin cambio real."
        )
    # El trigger firmaba como "PYTHON (replica...)"; aca interesa saber que el
    # cambio vino de la app web y no del ETL.
    evento["usuario_evento"] = "app-web (demo)"
    evento["origen"] = "Python (app web, réplica de trg_cuota_bitacora)"

    # 3) Documento tal como quedara, para recalcular el analisis con el ETL.
    copia = copy.deepcopy(documento)
    _, cuota_copia = _buscar_cuota(copia, nro_credito, nro_cuota)
    cuota_copia.update({
        "monto_pagado": nuevo,
        "saldo_por_pagar": saldo,
        "estado": estado,
        "fecha_pago": fecha_pago,
        "forma_pago": forma_pago,
    })
    analisis = transform.recalcular_analisis(copia)

    resultado = base[COLECCION_CLIENTES].update_one(
        {"_id": int(nro_cliente)},
        {
            "$set": {
                "creditos.$[cred].cuotas.$[cuo].monto_pagado": nuevo,
                "creditos.$[cred].cuotas.$[cuo].saldo_por_pagar": saldo,
                "creditos.$[cred].cuotas.$[cuo].estado": estado,
                "creditos.$[cred].cuotas.$[cuo].fecha_pago": fecha_pago,
                "creditos.$[cred].cuotas.$[cuo].forma_pago": forma_pago,
                "analisis": analisis,
            },
            "$push": {
                "historial_pagos": {
                    "nro_solic_credito": nro_credito,
                    "nro_cuota": nro_cuota,
                    "fecha_evento": fecha_pago,
                    "monto_pagado_anterior": anterior,
                    "monto_pagado_nuevo": nuevo,
                    "saldo_resultante": saldo,
                    "forma_pago": forma_pago,
                    "estado_cuota": estado,
                }
            },
        },
        array_filters=[
            {"cred.nro_solic_credito": nro_credito},
            {"cuo.nro_cuota": nro_cuota},
        ],
    )

    if resultado.matched_count == 0:
        return _error("La cuota no se encontró al momento de actualizar.")
    if resultado.modified_count == 0:
        return _error("La actualización no modificó el documento (¿datos iguales?).")

    # 4) Evento de auditoria. Se escribe DESPUES del documento: si fallara, el
    # dato de negocio ya quedo consistente y solo falta la bitacora.
    base[COLECCION_BITACORA].insert_one(evento)

    # 5) Verificacion: se relee y se compara.
    final = base[COLECCION_CLIENTES].find_one({"_id": int(nro_cliente)})
    _, cuota_final = _buscar_cuota(final, nro_credito, nro_cuota)

    if cuota_final.get("monto_pagado") != nuevo or cuota_final.get("saldo_por_pagar") != saldo:
        return _error("El documento no refleja el pago: revisar en Atlas.")

    return {
        "ok": True,
        "titulo": (
            f"Pago de {forma_pago} registrado en la cuota {nro_cuota} del "
            f"crédito {nro_credito}."
        ),
        "cliente": int(nro_cliente),
        "detalle": [
            ("Pagado antes", f"${anterior:,}".replace(",", ".")),
            ("Pagado ahora", f"${nuevo:,}".replace(",", ".")),
            ("Saldo de la cuota", f"${saldo:,}".replace(",", ".")),
            ("Estado", estado),
            ("Saldo del cliente",
             f"${int(analisis['saldo_pendiente']):,}".replace(",", ".")),
            ("% pagado", f"{analisis['porcentaje_pagado']}%"),
        ],
        "bitacora_id": evento["_id"],
        "nota": f"Evento de auditoría #{evento['_id']} en bitacora_pagos.",
    }


# ==========================================================================
# REGISTRAR MOVIMIENTO DE INVERSION  (reglas 3 y 4)
# ==========================================================================

def registrar_movimiento(nro_cliente: int, nro_solic_prod: int, tipo: str,
                         monto: int) -> dict:
    """
    ABONO o RESCATE sobre una inversion embebida.

    REGLA 3 valida monto, tipo y (si es rescate) saldo disponible y porcentaje
    contractual; REGLA 4 define el saldo nuevo. La escritura reutiliza el mismo
    patron que el CRUD del ETL: $inc del saldo + $push del movimiento + $set del
    analisis recalculado, todo en una sola operacion.
    """
    reglas, transform = _cargar_modulos_etl()
    base = obtener_base()

    documento = base[COLECCION_CLIENTES].find_one({"_id": int(nro_cliente)})
    if documento is None:
        return _error(f"No existe el cliente {nro_cliente}.")

    inversion = _buscar_inversion(documento, nro_solic_prod)
    if inversion is None:
        return _error(
            f"El cliente {nro_cliente} no tiene la inversión {nro_solic_prod}."
        )

    # 3) REGLA 3
    validacion = reglas.validar_movimiento(inversion, monto, tipo)
    if not validacion.valido:
        return _error(
            "El movimiento no cumple la regla 3.", 
            [e["mensaje"] for e in validacion.errores],
        )

    # 4) REGLA 4
    signo = validacion.datos["signo"]
    nuevo_saldo = reglas.calcular_ahorro_actualizado(inversion, monto, tipo)
    producto = inversion.get("producto") or {}

    movimiento = {
        "nro_movimiento": _siguiente_nro_movimiento(),
        "fecha": _ahora(),
        "tipo_movimiento": tipo,
        "monto": int(monto),
        "signo": signo,
        "monto_con_signo": signo * int(monto),
    }

    copia = copy.deepcopy(documento)
    inversion_copia = _buscar_inversion(copia, nro_solic_prod)
    inversion_copia["monto_total_ahorrado"] = nuevo_saldo
    inversion_copia.setdefault("movimientos", []).append(movimiento)
    analisis = transform.recalcular_analisis(copia)

    resultado = base[COLECCION_CLIENTES].update_one(
        {"_id": int(nro_cliente)},
        {
            "$set": {"analisis": analisis},
            "$inc": {"inversiones.$[inv].monto_total_ahorrado": signo * int(monto)},
            "$push": {"inversiones.$[inv].movimientos": movimiento},
        },
        array_filters=[{"inv.nro_solic_prod": nro_solic_prod}],
    )

    if resultado.modified_count == 0:
        return _error("La actualización no modificó el documento.")

    final = base[COLECCION_CLIENTES].find_one({"_id": int(nro_cliente)})
    inversion_final = _buscar_inversion(final, nro_solic_prod)
    if inversion_final.get("monto_total_ahorrado") != nuevo_saldo:
        return _error("El documento no refleja el movimiento: revisar en Atlas.")

    return {
        "ok": True,
        "titulo": (
            f"{tipo} de ${int(monto):,}".replace(",", ".") +
            f" registrado en la inversión {nro_solic_prod}."
        ),
        "cliente": int(nro_cliente),
        "detalle": [
            ("Producto", producto.get("nombre") or "—"),
            ("Saldo antes", f"${int(validacion.datos['saldo_actual']):,}".replace(",", ".")),
            ("Saldo ahora", f"${nuevo_saldo:,}".replace(",", ".")),
            ("Tipo", tipo),
            ("N° movimiento", str(movimiento["nro_movimiento"])),
            ("Ahorro del cliente",
             f"${int(analisis['total_ahorrado']):,}".replace(",", ".")),
        ],
        "nota": f"Movimiento #{movimiento['nro_movimiento']} en inversiones.",
    }
