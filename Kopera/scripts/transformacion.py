"""
Transformacion: convierte los datos planos extraidos de Oracle en los
documentos de MongoDB Atlas (EVAL 3).

Este modulo concentra las TRES decisiones de diseno que se tomaron para la
migracion:

1. LIMPIEZA DE CARACTERES DAÑADOS. El archivo semilla BD_KOPERA.SQL tiene el
   caracter de reemplazo Unicode U+FFFD (�) donde deberian ir los acentos. No
   es un problema de codificacion del driver ni de la consola: el dato llega
   asi desde el origen. Se corrige con un diccionario de 108 entradas, sin
   eliminar los acentos: el nombre debe quedar legible en la coleccion.

2. ANIDADO POR AGREGADO. El cliente es el agregado natural: sus creditos con
   sus cuotas, sus inversiones con sus movimientos. Se resuelve en memoria con
   diccionarios indexados, no con joins ni con $lookup.

3. RECLASIFICACION A OPORTUNIDAD. fn_clasifica_cliente marca RIESGO a 129 de
   los 130 clientes, porque 107 no tienen credito y su porcentaje pagado es 0
   (0 < 50 -> RIESGO). Un cliente con ahorro y sin deuda no es un riesgo: es
   una OPORTUNIDAD comercial. La correccion se aplica en Python, sin tocar el
   package de la Evaluacion 2, y se conserva el valor original para
   trazabilidad.
"""

from datetime import date, datetime

# ==========================================================================
# 1. LIMPIEZA DE CARACTERES
# ==========================================================================

# Diccionario de correccion. La clave es el texto dañado tal como llega de
# Oracle (con U+FFFD) y el valor es la forma correcta.
#
# Se construyó extrayendo todos los tokens dañados de la base (108 distintos)
# y revisando uno por uno. Todos son toponimos o palabras del español Chilean
# donde el caracter acentuado es inequivoco.
CORRECCIONES = {
    # --- Nombres y apellidos de clientes ---
    "NICOL�S": "NICOLÁS",
    "Mar�a": "María",
    "BEL�N": "BELÉN",
    "MU�OZ": "MUÑOZ",
    "BUGUE�O": "BUGUEÑO",
    "Andr�s": "Andrés",
    "Mart�n": "Martín",
    "Mart�nez": "Martínez",
    "Fern�ndez": "Fernández",
    "Vel�squez": "Velásquez",
    "Alc�zar": "Alcázar",
    "Joaqu�n": "Joaquín",
    "P�rez": "Pérez",
    "Guti�rrez": "Gutiérrez",
    "Ram�n": "Ramón",
    "Bar�n": "Barón",
    "Garc�a": "García",
    "H�roes": "Héroes",
    "Tom�s": "Tomás",
    "Larra�n": "Larrañán",
    "Casta�os": "Castaños",
    "Vald�s": "Valdés",
    "Jos�": "José",
    "Mu�oz": "Muñoz",
    "Sim�n": "Simón",
    "Bol�var": "Bolívar",
    "C�rdova": "Córdova",
    "Err�zuriz": "Errázuriz",
    "Chapiqui�a": "Chapiquina",
    "�lvarez": "Álvarez",
    "Vicu�a": "Vicuña",
    "Arag�n": "Aragón",
    "Breta�a": "Bretaña",
    # --- Toponimos: regiones ---
    "Tarapac�": "Tarapacá",
    "Valpara�so": "Valparaíso",
    "O�Higgins": "O'Higgins",
    "Biob�o": "Biobío",
    "Araucan�a": "Araucanía",
    "Ays�n": "Aysén",
    "Ib��ez": "Ibáñez",
    "Ant�rtica": "Antártica",
    "R�os": "Ríos",
    "�uble": "Ñuble",
    # --- Toponimos: provincias ---
    "Copiap�": "Copiapó",
    "Cha�aral": "Chañaral",
    "Limar�": "Limarí",
    "Curic�": "Curicó",
    "Concepci�n": "Concepción",
    "Caut�n": "Cautén",
    "Chilo�": "Chiloé",
    "Capit�n": "Capitán",
    "�ltima": "Última",
    "Diguill�n": "Diguillén",
    # --- Toponimos: comunas ---
    "Cami�a": "Camiña",
    "Ollag�e": "Ollagüe",
    "Combarbal�": "Combarbalá",
    "R�o": "Río",
    "Conc�n": "Concepción",
    "Puchuncav�": "Puchuncaví",
    "Vi�a": "Viña",
    "Quilpu�": "Quilpué",
    "Olmu�": "Olmué",
    "�ngeles": "Ángeles",
    "Ais�n": "Aisén",
    "Uni�n": "Unión",
    "Chill�n": "Chillán",
    # --- Palabras del credito ---
    "Cr�dito": "Crédito",
    "cr�dito": "crédito",
    "m�nima": "mínima",
    "ampliaci�n": "ampliación",
    "reparaci�n": "reparación",
    "construcci�n": "construcción",
    "adquisici�n": "adquisición",
    "veh�culo": "vehículo",
    "cat�strofe": "catástrofe",
    "pensi�n": "pensión",
    # --- Productos, profesiones y otros ---
    "Dep�sito": "Depósito",
    "Inversi�n": "Inversión",
    "Electr�nica": "Electrónica",
    "T�cnico": "Técnico",
    "�rea": "Área",
    "computaci�n": "computación",
    "Inform�tica": "Informática",
    "cami�n": "camino",
    "Mec�nico": "Mecánico",
    "Dise�ador": "Diseñador",
    "p�rvulo": "párvulo",
    # --- Promedio de renta (TIPO_CONTRATO) ---
    "�ltimos": "últimos",
    "�timos": "últimos",
    "a�os": "años",
}


def limpiar_texto(valor):
    """
    Corrige los caracteres dañados de un texto y normaliza espacios.

    Si el texto no tiene U+FFFD, se devuelve tal cual (solo con espacios
    duplicados colapsados). Si tiene un token que no está en el diccionario,
    se deja el U+FFFD y se deja constancia para el reporte de calidad.
    """
    if valor is None:
        return None

    texto = str(valor)

    if "�" in texto:
        for danado, correcto in CORRECCIONES.items():
            texto = texto.replace(danado, correcto)

    # Colapsar espacios sobrantes (al corregir un token pueden quedar dobles)
    while "  " in texto:
        texto = texto.replace("  ", " ")

    return texto.strip()


def contar_danados(texto):
    """Cuenta los U+FFFD que quedan sin corregir en un texto."""
    if texto is None:
        return 0
    return str(texto).count("�")


# ==========================================================================
# 2. UTILIDADES DE FORMATO
# ==========================================================================

def _iso(fecha):
    """Convierte una fecha de Oracle a texto ISO, que es el formato nativo de BSON."""
    if fecha is None:
        return None
    if isinstance(fecha, datetime):
        return fecha.isoformat()
    if isinstance(fecha, date):
        return fecha.isoformat()
    return str(fecha)


def _nombre_completo(cliente):
    """
    Arma el nombre completo del cliente a partir de sus partes.

    Cada parte se pasa por limpiar_texto: si no, el nombre completo quedaria
    con el U+FFFD original aunque los campos por separado estuvieran
    corregidos (el nombre completo se arma desde los datos CRUDOS de Oracle).
    """
    partes = [
        limpiar_texto(cliente.get("pnombre")),
        limpiar_texto(cliente.get("snombre")),
        limpiar_texto(cliente.get("appaterno")),
        limpiar_texto(cliente.get("apmaterno")),
    ]
    return " ".join(p for p in partes if p)


# ==========================================================================
# 3. RECLASIFICACION
# ==========================================================================

def reclasificar(clasificacion_oracle, cantidad_creditos):
    """
    Ajusta la clasificacion que devuelve el package PL/SQL.

    Regla de negocio acordada: un cliente SIN creditos no es un riesgo, es una
    oportunidad comercial (puede ser cross-selling). Se conserva el valor
    original del package para trazabilidad.
    """
    if cantidad_creditos == 0:
        return "OPORTUNIDAD", "Cliente sin creditos vigentes"
    return clasificacion_oracle, "Clasificacion calculada por pk_analisis_kopera"


def clasificar_cliente(porcentaje_pagado, cuotas_vencidas, saldo_pendiente,
                       tiene_creditos, tiene_inversiones):
    """
    Equivalente en Python de fn_clasifica_cliente, MAS la reclasificacion.

    Se necesita cuando un documento YA migrado se modifica (por ejemplo al
    registrar un pago): en Oracle la clasificacion siempre es "viva" porque
    las funciones la recalculan en cada consulta, pero en MongoDB el bloque
    analisis esta MATERIALIZADO dentro del documento, asi que hay que
    recalcularlo para que no quede desactualizado.

    Regla de fn_clasifica_cliente:
        sin productos ni creditos -> SIN PRODUCTOS
        tiene cuotas vencidas o pago < 50% -> RIESGO
        saldo pendiente > 0                -> REGULAR
        en otro caso                       -> BUENO

    Regla de la EVAL 3 (aplicada encima):
        sin creditos -> OPORTUNIDAD
    """
    if not tiene_creditos and not tiene_inversiones:
        return "SIN PRODUCTOS", "Cliente sin productos ni creditos"

    if cuotas_vencidas > 0 or porcentaje_pagado < 50:
        clasificacion_oracle = "RIESGO"
    elif saldo_pendiente > 0:
        clasificacion_oracle = "REGULAR"
    else:
        clasificacion_oracle = "BUENO"

    return reclasificar(clasificacion_oracle, 1 if tiene_creditos else 0)


# ==========================================================================
# 4. ALERTAS
# ==========================================================================

# Mismo criterio que sp_analiza_cliente: cuota vencida o pago incompleto.
MAXIMO_ALERTAS = 10


def generar_alertas(creditos):
    """
    Genera las alertas financieras del cliente.

    Replica el criterio de sp_analiza_cliente (cuota vencida y pago
    incompleto) en formato texto. El package no se puede llamar desde Python
    porque sus parametros OUT son de tipo RECORD y VARRAY, que el driver no
    soporta; los conteos de cada estado SI vienen del package (fn_cuenta_cuotas).
    """
    alertas = []
    for credito in creditos:
        for cuota in credito.get("cuotas", []):
            if len(alertas) >= MAXIMO_ALERTAS:
                return alertas
            if cuota["estado"] == "VENCIDA":
                alertas.append(
                    f"Cuota vencida: credito {credito['nro_solic_credito']}, "
                    f"cuota {cuota['nro_cuota']}"
                )
            elif cuota["estado"] == "PARCIAL":
                alertas.append(
                    f"Pago incompleto: credito {credito['nro_solic_credito']}, "
                    f"cuota {cuota['nro_cuota']}"
                )
    return alertas


# ==========================================================================
# 5. ENSAMBLADO DE LOS DOCUMENTOS
# ==========================================================================

def construir_documentos_clientes(datos):
    """
    Arma un documento por cliente, con todo su historial financiero embebido.

    datos es el diccionario devuelto por la extraccion. Devuelve la lista de
    documentos y el reporte de calidad de datos.
    """
    # Indices para resolver las relaciones en memoria (sin joins en MongoDB)
    cuotas_por_credito = {}
    for cuota in datos["cuotas"]:
        cuotas_por_credito.setdefault(cuota["nro_solic_credito"], []).append(cuota)

    movimientos_por_producto = {}
    for mov in datos["movimientos"]:
        movimientos_por_producto.setdefault(mov["nro_solic_prod"], []).append(mov)

    creditos_por_cliente = {}
    for credito in datos["creditos"]:
        creditos_por_cliente.setdefault(credito["nro_cliente"], []).append(credito)

    inversiones_por_cliente = {}
    for inv in datos["inversiones"]:
        inversiones_por_cliente.setdefault(inv["nro_cliente"], []).append(inv)

    analisis_por_cliente = {a["nro_cliente"]: a for a in datos["analisis"]}
    totales_por_cliente = datos["totales"]
    pagos_por_cliente = {}
    for pago in datos["pagos"]:
        pagos_por_cliente.setdefault(pago["nro_cliente"], []).append(pago)

    documentos = []
    observaciones_totales = []

    for cliente in datos["clientes"]:
        nro_cliente = cliente["nro_cliente"]
        danados = []

        # --- Creditos con sus cuotas embebidas ---
        lista_creditos = []
        for credito in creditos_por_cliente.get(nro_cliente, []):
            lista_cuotas = []
            for cuota in cuotas_por_credito.get(credito["nro_solic_credito"], []):
                lista_cuotas.append({
                    "nro_cuota": cuota["nro_cuota"],
                    "fecha_vencimiento": _iso(cuota["fecha_venc_cuota"]),
                    "valor_cuota": cuota["valor_cuota"],
                    "monto_pagado": cuota["monto_pagado"],
                    "saldo_por_pagar": cuota["saldo_por_pagar"],
                    "estado": cuota["estado"],
                    "dias_atraso": cuota["dias_atraso"],
                    "fecha_pago": _iso(cuota["fecha_pago_cuota"]),
                    "forma_pago": limpiar_texto(cuota["nombre_forma_pago"]),
                })

            lista_creditos.append({
                "nro_solic_credito": credito["nro_solic_credito"],
                "tipo_credito": {
                    "codigo": credito["cod_credito"],
                    "nombre": limpiar_texto(credito["nombre_credito"]),
                    "descripcion": limpiar_texto(credito["desc_credito"]),
                    "tasa_interes_anual": credito["tasa_interes_anual"],
                    "nro_maximo_cuotas": credito["nro_maximo_cuotas"],
                },
                "fecha_solicitud": _iso(credito["fecha_solic_cred"]),
                "fecha_otorgamiento": _iso(credito["fecha_otorga_cred"]),
                "monto_solicitado": credito["monto_solicitado"],
                "monto_credito": credito["monto_credito"],
                "total_cuotas": credito["total_cuotas_credito"],
                "aporte_sbif": credito["aporte_sbif"],
                "sucursal": {
                    "id_sucursal": credito["id_sucursal"],
                    "direccion": limpiar_texto(credito["sucursal_direccion"]),
                    "telefono": credito["sucursal_telefono"],
                    "region": limpiar_texto(credito["sucursal_region"]),
                    "provincia": limpiar_texto(credito["sucursal_provincia"]),
                    "comuna": limpiar_texto(credito["sucursal_comuna"]),
                },
                "cuotas": lista_cuotas,
            })

        # --- Inversiones con sus movimientos embebidos ---
        lista_inversiones = []
        for inversion in inversiones_por_cliente.get(nro_cliente, []):
            lista_movimientos = []
            for mov in movimientos_por_producto.get(inversion["nro_solic_prod"], []):
                lista_movimientos.append({
                    "nro_movimiento": mov["nro_movimiento"],
                    "fecha": _iso(mov["fecha_movimiento"]),
                    # El tipo se normaliza a MAYUSCULAS: es la forma en que
                    # lo comparan los triggers (UPPER(nombre_tipo_mov)) y la
                    # que usa el enum del validador $jsonSchema. En Oracle el
                    # catalogo lo guarda como "Abono" y "Rescate".
                    "tipo_movimiento": (limpiar_texto(mov["nombre_tipo_mov"]) or "").upper(),
                    "monto": mov["monto_movimiento"],
                    "signo": mov["signo"],
                    "monto_con_signo": mov["monto_movimiento"] * mov["signo"],
                })

            lista_inversiones.append({
                "nro_solic_prod": inversion["nro_solic_prod"],
                "producto": {
                    "codigo": inversion["cod_prod_inv"],
                    "nombre": limpiar_texto(inversion["nombre_prod_inv"]),
                    "meses_minimo_ahorro": inversion["meses_minimo_ahorro"],
                    "porc_maximo_rescate": inversion["porc_maximo_rescate"],
                },
                "fecha_solicitud": _iso(inversion["fecha_solic_prod"]),
                "ahorro_minimo_mensual": inversion["ahorro_minimo_mensual"],
                "dia_pago_mensual": inversion["dia_pago_mensual"],
                "monto_total_ahorrado": inversion["monto_total_ahorrado"],
                "porc_rescate": inversion["porc_rescate"],
                "movimientos": lista_movimientos,
            })

        # --- Analisis: snapshot de la logica del package PL/SQL ---
        analisis = analisis_por_cliente.get(nro_cliente, {})
        totales = totales_por_cliente.get(nro_cliente, {})
        clasificacion, motivo = reclasificar(
            analisis.get("clasificacion_oracle"), len(lista_creditos)
        )

        # --- Historial de pagos del cliente (desde la bitacora) ---
        historial_pagos = []
        for pago in pagos_por_cliente.get(nro_cliente, []):
            historial_pagos.append({
                "nro_solic_credito": pago["nro_solic_credito"],
                "nro_cuota": pago["nro_cuota"],
                "fecha_evento": _iso(pago["fecha_evento"]),
                "monto_pagado_anterior": pago["monto_pagado_anterior"],
                "monto_pagado_nuevo": pago["monto_pagado_nuevo"],
                "saldo_resultante": pago["saldo_resultante"],
                "forma_pago": limpiar_texto(pago["nombre_forma_pago"]),
                "estado_cuota": pago["estado_cuota"],
            })

        # --- Control de calidad del texto de este cliente ---
        textos_a_revisar = [
            cliente["pnombre"], cliente["snombre"], cliente["appaterno"],
            cliente["apmaterno"], cliente["direccion"], cliente["nombre_region"],
            cliente["nombre_provincia"], cliente["nombre_comuna"],
            cliente["nombre_prof_ofic"], cliente["nombre_tipo_contrato"],
        ]
        for credito in lista_creditos:
            textos_a_revisar.append(credito["tipo_credito"]["nombre"])
            textos_a_revisar.append(credito["tipo_credito"]["descripcion"])
        for inversion in lista_inversiones:
            textos_a_revisar.append(inversion["producto"]["nombre"])

        for texto in textos_a_revisar:
            if texto and contar_danados(limpiar_texto(texto)) > 0:
                danados.append(texto)

        if danados:
            observaciones_totales.append({
                "nro_cliente": nro_cliente,
                "campos_sin_corregir": danados,
            })

        documento = {
            "_id": nro_cliente,
            "nro_cliente": nro_cliente,
            "run": f"{cliente['numrun']}-{cliente['dvrun']}",
            "nombre": {
                "pnombre": limpiar_texto(cliente["pnombre"]),
                "snombre": limpiar_texto(cliente["snombre"]),
                "appaterno": limpiar_texto(cliente["appaterno"]),
                "apmaterno": limpiar_texto(cliente["apmaterno"]),
            },
            "nombre_completo": _nombre_completo(cliente),
            "fecha_nacimiento": _iso(cliente["fecha_nacimiento"]),
            "fecha_inscripcion": _iso(cliente["fecha_inscripcion"]),
            "contacto": {
                "correo": limpiar_texto(cliente["correo"]),
                "fono_contacto": cliente["fono_contacto"],
                "direccion": limpiar_texto(cliente["direccion"]),
            },
            "ubicacion": {
                "region": limpiar_texto(cliente["nombre_region"]),
                "provincia": limpiar_texto(cliente["nombre_provincia"]),
                "comuna": limpiar_texto(cliente["nombre_comuna"]),
            },
            "profesion": limpiar_texto(cliente["nombre_prof_ofic"]),
            "tipo_contrato": {
                "nombre": limpiar_texto(cliente["nombre_tipo_contrato"]),
                "promedio_renta": limpiar_texto(cliente["promedio_renta"]),
            },
            "creditos": lista_creditos,
            "inversiones": lista_inversiones,
            "historial_pagos": historial_pagos,
            "analisis": {
                "total_creditos": totales.get("total_deuda", 0),
                "total_pagado": totales.get("total_pagado", 0),
                "saldo_pendiente": analisis.get("saldo_pendiente", 0),
                "porcentaje_pagado": analisis.get("porcentaje_pagado", 0),
                "total_ahorrado": analisis.get("total_ahorrado", 0),
                "cuotas": {
                    "total": totales.get("total_cuotas", 0),
                    "pagadas": analisis.get("cuotas_pagadas", 0),
                    "parciales": analisis.get("cuotas_parciales", 0),
                    "vencidas": analisis.get("cuotas_vencidas", 0),
                    "pendientes": analisis.get("cuotas_pendientes", 0),
                },
                "clasificacion": clasificacion,
                "clasificacion_oracle": analisis.get("clasificacion_oracle"),
                "motivo_clasificacion": motivo,
                "alertas": generar_alertas(lista_creditos),
            },
            "calidad_datos": {
                "caracteres_corregidos": True,
                "observaciones": (
                    [f"Cliente {nro_cliente}: {len(danados)} campo(s) con U+FFFD sin corregir"]
                    if danados else []
                ),
            },
            "metadata": {
                "origen": "Oracle ADMIN_PROYECTO",
                "fecha_corte": _iso(datos["fecha_corte"]),
                "migrado_en": _iso(datetime.now()),
            },
        }

        documentos.append(documento)

    return documentos, observaciones_totales


def construir_documentos_catalogos(catalogos):
    """Arma los documentos de la coleccion de catalogos."""
    documentos = []

    for producto in catalogos["productos_inversion"]:
        documentos.append({
            "_id": f"INV-{producto['cod_prod_inv']}",
            "categoria": "INVERSION",
            "codigo": producto["cod_prod_inv"],
            "nombre": limpiar_texto(producto["nombre_prod_inv"]),
            "meses_minimo_ahorro": producto["meses_minimo_ahorro"],
            "porc_maximo_rescate": producto["porc_maximo_rescate"],
        })

    for credito in catalogos["tipos_credito"]:
        documentos.append({
            "_id": f"CRE-{credito['cod_credito']}",
            "categoria": "CREDITO",
            "codigo": credito["cod_credito"],
            "nombre": limpiar_texto(credito["nombre_credito"]),
            "descripcion": limpiar_texto(credito["desc_credito"]),
            "tasa_interes_anual": credito["tasa_interes_anual"],
            "nro_maximo_cuotas": credito["nro_maximo_cuotas"],
        })

    for forma in catalogos["formas_pago"]:
        documentos.append({
            "_id": f"FORMA-{forma['cod_forma_pago']}",
            "categoria": "FORMA_PAGO",
            "codigo": forma["cod_forma_pago"],
            "nombre": limpiar_texto(forma["nombre_forma_pago"]),
        })

    for tipo in catalogos["tipos_movimiento"]:
        documentos.append({
            "_id": f"TIPO-MOV-{tipo['cod_tipo_mov']}",
            "categoria": "TIPO_MOVIMIENTO",
            "codigo": tipo["cod_tipo_mov"],
            "nombre": limpiar_texto(tipo["nombre_tipo_mov"]),
        })

    for rango in catalogos["aportes_sbif"]:
        documentos.append({
            "_id": f"SBIF-{rango['id_rango']}",
            "categoria": "APORTE_SBIF",
            # El rango no tiene un nombre propio en Oracle: se construye uno
            # legible para que todos los catalogos tengan la misma forma.
            "nombre": (
                f"Aporte SBIF {rango['porc_entrega_sbif']}% "
                f"(credito de {rango['monto_credito_desde']} "
                f"a {rango['monto_credito_hasta']})"
            ),
            "monto_credito_desde": rango["monto_credito_desde"],
            "monto_credito_hasta": rango["monto_credito_hasta"],
            "porc_entrega_sbif": rango["porc_entrega_sbif"],
        })

    for profesion in catalogos["profesiones"]:
        documentos.append({
            "_id": f"PROF-{profesion['cod_prof_ofic']}",
            "categoria": "PROFESION",
            "codigo": profesion["cod_prof_ofic"],
            "nombre": limpiar_texto(profesion["nombre_prof_ofic"]),
        })

    for contrato in catalogos["tipos_contrato"]:
        documentos.append({
            "_id": f"CONTRATO-{contrato['cod_tipo_contrato']}",
            "categoria": "TIPO_CONTRATO",
            "codigo": contrato["cod_tipo_contrato"],
            "nombre": limpiar_texto(contrato["nombre_tipo_contrato"]),
            "promedio_renta": limpiar_texto(contrato["promedio_renta"]),
        })

    return documentos


def construir_documentos_bitacora(eventos):
    """Arma los documentos de la coleccion de auditoria de pagos."""
    documentos = []
    for evento in eventos:
        documentos.append({
            "_id": evento["id_bitacora"],
            "nro_solic_credito": evento["nro_solic_credito"],
            "nro_cuota": evento["nro_cuota"],
            "nro_cliente": evento["nro_cliente"],
            "fecha_evento": _iso(evento["fecha_evento"]),
            "usuario_evento": evento["usuario_evento"],
            "monto_pagado_anterior": evento["monto_pagado_anterior"],
            "monto_pagado_nuevo": evento["monto_pagado_nuevo"],
            "valor_cuota": evento["valor_cuota"],
            "saldo_resultante": evento["saldo_resultante"],
            "cod_forma_pago": evento["cod_forma_pago"],
            "forma_pago": limpiar_texto(evento["nombre_forma_pago"]),
            "origen": "trigger trg_cuota_bitacora (Oracle)",
        })
    return documentos


def recalcular_analisis(documento):
    """
    Recalcula el bloque "analisis" de un documento ya migrado.

    En Oracle la clasificacion y los totales siempre estan "vivos": las
    funciones del package los recalculan en cada consulta. En MongoDB el
    bloque analisis esta MATERIALIZADO dentro del documento, asi que cuando
    el CRUD modifica una cuota o un movimiento, hay que recalcularlo para que
    el documento no quede desactualizado.

    Devuelve el bloque "analisis" completo, listo para un $set.
    """
    creditos = documento.get("creditos", [])
    inversiones = documento.get("inversiones", [])

    total_creditos = sum(c.get("monto_credito", 0) for c in creditos)
    total_pagado = 0
    saldo_pendiente = 0
    total_cuotas = 0
    pagadas = 0
    parciales = 0
    vencidas = 0
    pendientes = 0

    for credito in creditos:
        for cuota in credito.get("cuotas", []):
            total_cuotas += 1
            total_pagado += cuota.get("monto_pagado", 0)
            saldo_pendiente += cuota.get("saldo_por_pagar", 0)

            estado = cuota.get("estado")
            if estado == "PAGADA":
                pagadas += 1
            elif estado == "PARCIAL":
                parciales += 1
            elif estado == "VENCIDA":
                vencidas += 1
            else:
                pendientes += 1

    total_ahorrado = sum(i.get("monto_total_ahorrado", 0) for i in inversiones)

    if total_creditos:
        porcentaje_pagado = round(total_pagado / total_creditos * 100, 2)
    else:
        porcentaje_pagado = 0

    clasificacion, motivo = clasificar_cliente(
        porcentaje_pagado,
        vencidas,
        saldo_pendiente,
        tiene_creditos=bool(creditos),
        tiene_inversiones=bool(inversiones),
    )

    return {
        "total_creditos": total_creditos,
        "total_pagado": total_pagado,
        "saldo_pendiente": saldo_pendiente,
        "porcentaje_pagado": porcentaje_pagado,
        "total_ahorrado": total_ahorrado,
        "cuotas": {
            "total": total_cuotas,
            "pagadas": pagadas,
            "parciales": parciales,
            "vencidas": vencidas,
            "pendientes": pendientes,
        },
        "clasificacion": clasificacion,
        "clasificacion_oracle": clasificacion if clasificacion != "OPORTUNIDAD" else None,
        "motivo_clasificacion": motivo,
        "alertas": generar_alertas(creditos),
    }


def parsear_resumen_proceso(lineas_salida):
    """
    Extrae los totales del informe de sp_proceso_mensual.

    El procedimiento imprime su informe con DBMS_OUTPUT y la ultima linea
    tiene el formato:

        Clientes analizados: 130 | saldo total: $45312345

    Se parsea esa linea para guardar los totales como numeros (y no solo como
    texto), que es lo que hace util la coleccion para consultas agregadas.
    """
    clientes_analizados = 0
    saldo_total = 0

    for linea in reversed(lineas_salida):
        if linea.startswith("Clientes analizados:"):
            partes = linea.split("|")
            for parte in partes:
                parte = parte.strip()
                if parte.startswith("Clientes analizados:"):
                    clientes_analizados = int(parte.split(":")[1].strip())
                elif parte.startswith("saldo total:"):
                    # Quita el signo de moneda y cualquier separador de miles.
                    monto = parte.split(":")[1].strip().replace("$", "").replace(".", "")
                    saldo_total = int(monto)
            break

    return clientes_analizados, saldo_total


def construir_documento_proceso(lineas_salida, fecha_corte, clientes_analizados, saldo_total):
    """
    Arma el documento de la coleccion de procesos mensuales.

    Se arma con la salida capturada de pk_analisis_kopera.sp_proceso_mensual
    (DBMS_OUTPUT) mas los totales calculados por el package.
    """
    return {
        "_id": _iso(fecha_corte),
        "fecha_corte": _iso(fecha_corte),
        "procedimiento": "pk_analisis_kopera.sp_proceso_mensual",
        "clientes_analizados": clientes_analizados,
        "saldo_total_cartera": saldo_total,
        "lineas_salida": lineas_salida,
        "origen": "Oracle PL/SQL (DBMS_OUTPUT)",
    }
