"""
CRUD completo en Python sobre MongoDB Atlas para KOPERA (EVAL 3).

Este script demuestra las cuatro operaciones basicas de MongoDB (Create,
Read, Update, Delete) sobre el modelo migrado. Cada operacion esta etiquetada
con un codigo (C1, R1, U1, D1...) para poder citarla en el informe.

    C1  Create  - Insertar un cliente nuevo con el validador $jsonSchema.
    C2  Create  - Insertar un catalogo de producto.
    C3  Create  - Insertar un evento de auditoria de pago (regla 2).
    C4  Create  - Insertar un movimiento de ahorro con las reglas 3 y 4.

    R1  Read    - Buscar un cliente por su clave primaria.
    R2  Read    - Filtrar clientes por clasificacion y saldo, con proyeccion.
    R3  Read    - Contar clientes por clasificacion.
    R4  Read    - Agregar el saldo ahorrado por producto (aggregation).
    R5  Read    - Consultar dentro de un array embebido (cuotas vencidas).
    R6  Read    - Buscar por nombre usando el indice de texto.
    R7  Read    - Leer la bitacora de pagos de un cliente.

    U1  Update  - Actualizar los datos de contacto con $set.
    U2  Update  - Registrar un pago: actualiza la cuota, deriva el saldo,
                   recalcula el analisis y deja el evento en la bitacora
                   (reglas 1 y 2).
    U3  Update  - Abonar a una inversion: $inc del saldo + $push del
                   movimiento (reglas 3 y 4).
    U4  Update  - Actualizar la clasificacion del cliente.

    D1  Delete  - Eliminar el cliente de prueba creado en C1.
    D2  Delete  - Eliminar un movimiento (revertiendo su $inc).
    D3  Delete  - Eliminar un evento de la bitacora.

REPRODUCIBILIDAD. El script se puede ejecutar las veces que quiera sin dejar
la base sucia: al empezar toma una COPIA de todos los documentos que va a
modificar y al terminar los restaura. Al final verifica que los conteos y los
importes Sean los mismos que antes de empezar.

Las operaciones se hacen SIEMPRE sobre un unico documento, nunca con
transacciones multi-documento: el cluster M0 de Atlas no las admite.
"""

import argparse
import copy
from datetime import datetime

from pymongo.errors import WriteError

import transformacion as transform
import validaciones as reglas
from config import (
    COLECCION_BITACORA,
    COLECCION_CATALOGOS,
    COLECCION_CLIENTES,
    conectar_mongodb,
    obtener_base_mongodb,
)

# Cliente de prueba para el CRUD de Create/Delete. No existe en Oracle, asi
# que no altera la correspondencia entre las dos bases.
NRO_CLIENTE_PRUEBA = 9001
RUN_CLIENTE_PRUEBA = "11111111-1"
ID_CATALOGO_PRUEBA = "TEST-INV-999"

# Cliente real que se usa en los casos de Update y Delete. Al final se
# restaura a su estado original.
NRO_CLIENTE_TRABAJO = 5

# Credito, cuotas e inversiones del cliente de trabajo. Son los identificadores
# de la semilla BD_KOPERA.SQL: el CRUD los usa como fixture conocido.
CREDITO_TRABAJO = 2001
CUOTA_TRABAJO_LECTURA = 5
CUOTA_TRABAJO_PAGO = 8
INVERSION_TRABAJO = 250001
INVERSION_TRABAJO_ALTERNATIVA = 250002

# Identificadores de los documentos que crea el CRUD. Son altos y fijos para
# que nunca choquen con los de la semilla (nro_movimiento llega a 345).
NRO_MOVIMIENTO_PRUEBA = 999999
NRO_MOVIMIENTO_ALTERNATIVO = 999998
NRO_CLIENTE_INCOMPLETO = 9998

# Cantidad de clientes que trae la semilla y que migra el ETL.
TOTAL_CLIENTES_MIGRADOS = 130


class EntornoPrueba:
    """
    Guarda copias de los documentos que el CRUD modifica, para restaurarlos.

    Es lo que permite que el script sea re-ejecutable: el resultado final es
    identico al inicial, y la base sigue reflejando el estado de Oracle.
    """

    def __init__(self, base):
        self.base = base
        self.clientes = {}
        self.bitacora = {}
        self.catalogos = {}
        # Documentos NUEVOS que creo el CRUD: hay que borrarlos al restaurar.
        self.creados_bitacora = []
        self.creados_catalogos = []
        self.creados_clientes = []

    def guardar_cliente(self, nro_cliente):
        documento = self.base[COLECCION_CLIENTES].find_one({"nro_cliente": nro_cliente})
        if documento is not None and nro_cliente not in self.clientes:
            self.clientes[nro_cliente] = copy.deepcopy(documento)

    def guardar_bitacora(self, id_bitacora):
        documento = self.base[COLECCION_BITACORA].find_one({"_id": id_bitacora})
        if documento is not None and id_bitacora not in self.bitacora:
            self.bitacora[id_bitacora] = copy.deepcopy(documento)

    def guardar_catalogo(self, id_catalogo):
        documento = self.base[COLECCION_CATALOGOS].find_one({"_id": id_catalogo})
        if documento is not None and id_catalogo not in self.catalogos:
            self.catalogos[id_catalogo] = copy.deepcopy(documento)

    def restaurar(self):
        """
        Devuelve la base al estado previo a la ejecucion.

        Tres operaciones distintas:
          - los documentos MODIFICADOS se reescriben con replace_one;
          - los documentos ELIMINADOS se vuelven a insertar con upsert=True
            (sin upsert, replace_one no hace nada si no encuentra el _id);
          - los documentos NUEVOS que creo el CRUD se borran.
        """
        for documento in self.clientes.values():
            self.base[COLECCION_CLIENTES].replace_one(
                {"_id": documento["_id"]}, documento, upsert=True
            )
        for documento in self.bitacora.values():
            self.base[COLECCION_BITACORA].replace_one(
                {"_id": documento["_id"]}, documento, upsert=True
            )
        for documento in self.catalogos.values():
            self.base[COLECCION_CATALOGOS].replace_one(
                {"_id": documento["_id"]}, documento, upsert=True
            )

        # Se borran los documentos que creo el CRUD.
        for id_bitacora in self.creados_bitacora:
            self.base[COLECCION_BITACORA].delete_one({"_id": id_bitacora})
        for id_catalogo in self.creados_catalogos:
            self.base[COLECCION_CATALOGOS].delete_one({"_id": id_catalogo})
        for nro_cliente in self.creados_clientes:
            self.base[COLECCION_CLIENTES].delete_one({"_id": nro_cliente})

        return {
            "clientes_restaurados": len(self.clientes),
            "bitacora_restaurada": len(self.bitacora),
            "catalogos_restaurados": len(self.catalogos),
            "bitacora_eliminada": len(self.creados_bitacora),
            "catalogos_eliminados": len(self.creados_catalogos),
            "clientes_eliminados": len(self.creados_clientes),
        }


# ==========================================================================
# UTILIDADES
# ==========================================================================

def siguiente_id_bitacora(coleccion):
    """
    Devuelve el siguiente id de la bitacora.

    En Oracle la columna ID_BITACORA es IDENTITY (la genera la secuencia del
    motor). En MongoDB no hay secuencias, asi que se replica el comportamiento
    con el maximo actual + 1.
    """
    documento = coleccion.find_one(sort=[("_id", -1)])
    if documento is None:
        return 1
    return documento["_id"] + 1


def buscar_cuota(documento, nro_credito, nro_cuota):
    """Localiza una cuota dentro del documento del cliente."""
    for credito in documento.get("creditos", []):
        if credito.get("nro_solic_credito") == nro_credito:
            for cuota in credito.get("cuotas", []):
                if cuota.get("nro_cuota") == nro_cuota:
                    return credito, cuota
    return None, None


def buscar_inversion(documento, nro_solic_prod):
    """Localiza una inversion dentro del documento del cliente."""
    for inversion in documento.get("inversiones", []):
        if inversion.get("nro_solic_prod") == nro_solic_prod:
            return inversion
    return None


def totales_base(base):
    """
    Calcula los totales de la base para verificar al final que el CRUD no
    dejo nada cambiado.
    """
    pipeline = [
        {"$group": {
            "_id": None,
            "clientes": {"$sum": 1},
            "saldo": {"$sum": "$analisis.saldo_pendiente"},
            "pagado": {"$sum": "$analisis.total_pagado"},
            "ahorrado": {"$sum": "$analisis.total_ahorrado"},
        }},
    ]
    resultado = list(base[COLECCION_CLIENTES].aggregate(pipeline))
    clientes = resultado[0] if resultado else {
        "clientes": 0, "saldo": 0, "pagado": 0, "ahorrado": 0,
    }
    clientes["bitacora"] = base[COLECCION_BITACORA].count_documents({})
    return clientes


# ==========================================================================
# CREATE
# ==========================================================================

def caso_c1_crear_cliente(base, entorno):
    """
    C1 - Inserta un cliente nuevo con la forma completa del modelo.

    El documento se valida en el SERVIDOR contra el $jsonSchema: si le falta
    un campo obligatorio, MongoDB lo rechaza. Eso es la "Create con
    validacion" del enunciado.
    """
    documento = {
        "_id": NRO_CLIENTE_PRUEBA,
        "nro_cliente": NRO_CLIENTE_PRUEBA,
        "run": RUN_CLIENTE_PRUEBA,
        "nombre": {
            "pnombre": "CLIENTE",
            "snombre": "DE",
            "appaterno": "PRUEBA",
            "apmaterno": "EVAL3",
        },
        "nombre_completo": "CLIENTE DE PRUEBA EVAL3",
        "fecha_nacimiento": "1990-01-15T00:00:00",
        "fecha_inscripcion": "2024-03-01T00:00:00",
        "contacto": {
            "correo": "cliente.prueba@kopera.cl",
            "fono_contacto": "912345678",
            "direccion": "Calle Prueba 123",
        },
        "ubicacion": {
            "region": "Metropolitana de Santiago",
            "provincia": "Santiago",
            "comuna": "Santiago",
        },
        "profesion": "Analista",
        "tipo_contrato": {
            "nombre": "Trabajador Dependiente",
            "promedio_renta": "De los ultimos 3 meses",
        },
        "creditos": [],
        "inversiones": [],
        "historial_pagos": [],
        "analisis": {
            "total_creditos": 0,
            "total_pagado": 0,
            "saldo_pendiente": 0,
            "porcentaje_pagado": 0,
            "total_ahorrado": 0,
            "cuotas": {
                "total": 0, "pagadas": 0, "parciales": 0,
                "vencidas": 0, "pendientes": 0,
            },
            "clasificacion": "OPORTUNIDAD",
            "clasificacion_oracle": None,
            "motivo_clasificacion": "Cliente sin creditos vigentes",
            "alertas": [],
        },
        "calidad_datos": {"caracteres_corregidos": True, "observaciones": []},
        "metadata": {
            "origen": "Prueba CRUD EVAL 3",
            "fecha_corte": datetime.now().isoformat(),
            "migrado_en": datetime.now().isoformat(),
        },
    }

    # Primero se prueba que el servidor RECHAZA un documento incompleto:
    # es la evidencia de que la validacion del lado del servidor funciona.
    incompleto = copy.deepcopy(documento)
    del incompleto["nombre"]
    incompleto["nro_cliente"] = NRO_CLIENTE_INCOMPLETO
    incompleto["_id"] = NRO_CLIENTE_INCOMPLETO

    mensaje_rechazo = "el servidor ACEPTÓ el documento incompleto"
    try:
        base[COLECCION_CLIENTES].insert_one(incompleto)
        base[COLECCION_CLIENTES].delete_one({"_id": NRO_CLIENTE_INCOMPLETO})
    except WriteError:
        # Solo se acepta este error: un fallo de red o de conexion no es un
        # rechazo del validador y no debe reportarse como si lo fuera.
        mensaje_rechazo = "el servidor RECHAZÓ el documento incompleto (validación $jsonSchema)"

    base[COLECCION_CLIENTES].insert_one(documento)
    entorno.creados_clientes.append(NRO_CLIENTE_PRUEBA)
    encontrados = base[COLECCION_CLIENTES].count_documents({"nro_cliente": NRO_CLIENTE_PRUEBA})

    obtenido = (
        f"documento insertado (nro_cliente={NRO_CLIENTE_PRUEBA}), "
        f"verificado en el servidor: {encontrados} documento(s); {mensaje_rechazo}"
    )
    cumple = encontrados == 1
    return obtenido, cumple


def caso_c2_crear_catalogo(base, entorno):
    """
    C2 - Inserta un producto de inversion en el catalogo maestro.

    El catalogo se guarda aparte del cliente para no duplicar nombres: es la
    diferencia entre el modelo relacional normalizado y el documental.
    """
    documento = {
        "_id": ID_CATALOGO_PRUEBA,
        "categoria": "INVERSION",
        "codigo": 999,
        "nombre": "Producto de prueba EVAL 3",
        "meses_minimo_ahorro": 6,
        "porc_maximo_rescate": 50,
    }
    base[COLECCION_CATALOGOS].insert_one(documento)
    entorno.creados_catalogos.append(ID_CATALOGO_PRUEBA)
    encontrados = base[COLECCION_CATALOGOS].count_documents({"categoria": "INVERSION"})

    obtenido = (
        f"catalogo insertado (_id={ID_CATALOGO_PRUEBA}); "
        f"total de productos de inversion en la coleccion: {encontrados}"
    )
    return obtenido, encontrados > 0


def caso_c3_crear_evento_bitacora(base, entorno):
    """
    C3 - Inserta un evento de auditoria de pago (REGLA 2).

    El evento se arma con la MISMA funcion que replica trg_cuota_bitacora, y
    solo se crea si el monto pagado cambio de verdad.
    """
    documento = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    credito, cuota = buscar_cuota(documento, CREDITO_TRABAJO, CUOTA_TRABAJO_LECTURA)
    if cuota is None:
        return f"no se encontro la cuota {CREDITO_TRABAJO}/{CUOTA_TRABAJO_LECTURA} del cliente de trabajo", False

    entorno.guardar_cliente(NRO_CLIENTE_TRABAJO)

    # Se simula un segundo pago sobre una cuota YA pagada: el monto no
    # cambio, asi que la REGLA 2 dice que NO hay evento que registrar.
    evento_inexistente = reglas.construir_evento_bitacora(
        cuota, NRO_CLIENTE_TRABAJO, cuota["monto_pagado"], cuota["monto_pagado"],
        "Efectivo", nro_credito=CREDITO_TRABAJO, fecha_evento=datetime.now().isoformat(),
    )

    # Y ahora un pago real sobre una cuota pendiente: si cambia, hay evento.
    _, cuota_pendiente = buscar_cuota(documento, CREDITO_TRABAJO, CUOTA_TRABAJO_PAGO)
    monto_nuevo = cuota_pendiente["monto_pagado"] + 1000
    evento = reglas.construir_evento_bitacora(
        cuota_pendiente, NRO_CLIENTE_TRABAJO,
        cuota_pendiente["monto_pagado"], monto_nuevo, "Efectivo",
        nro_credito=CREDITO_TRABAJO,
        fecha_evento=datetime.now().isoformat(),
        id_bitacora=siguiente_id_bitacora(base[COLECCION_BITACORA]),
    )

    if evento is None:
        return "la regla 2 no genero evento (el monto no cambio)", False

    base[COLECCION_BITACORA].insert_one(evento)
    entorno.creados_bitacora.append(evento["_id"])
    encontrados = base[COLECCION_BITACORA].count_documents({"_id": evento["_id"]})

    obtenido = (
        f"evento insertado en bitacora_pagos (_id={evento['_id']}, "
        f"pago {evento['monto_pagado_anterior']} -> {evento['monto_pagado_nuevo']}); "
        f"con pago sin cambio: {evento_inexistente is None} "
        f"(la regla 2 no duplica eventos)"
    )
    return obtenido, encontrados == 1


def caso_c4_crear_movimiento(base, entorno):
    """
    C4 - Inserta un movimiento de ahorro aplicando las REGLAS 3 y 4.

    REGLA 3: el monto debe ser positivo y el tipo valido (ABONO o RESCATE).
    REGLA 4: el saldo de la inversion se actualiza con $inc segun el signo.

    Primero se prueba que un movimiento invalido es rechazado por las reglas
    (mismo comportamiento que trg_movimiento_valida en Oracle).

    El bloque "analisis" se recalcula en la MISMA operacion: en MongoDB esta
    materializado dentro del documento, asi que si no se refrescara, el
    documento quedaria con un analisis.total_ahorrado que ya no corresponde a
    sus inversiones.
    """
    documento = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    entorno.guardar_cliente(NRO_CLIENTE_TRABAJO)

    inversion = buscar_inversion(documento, INVERSION_TRABAJO)
    if inversion is None:
        return f"no se encontro la inversion {INVERSION_TRABAJO} del cliente de trabajo", False

    # --- REGLA 3 aplicada a un movimiento invalido (monto negativo) ---
    invalido = reglas.validar_movimiento(inversion, -5000, "ABONO")
    monto_invalido_rechazado = not invalido.valido

    # --- REGLA 3 aplicada a un tipo invalido ---
    tipo_invalido = reglas.validar_movimiento(inversion, 1000, "TRANSFERENCIA")

    # --- Movimiento valido ---
    monto = 50000
    valido = reglas.validar_movimiento(inversion, monto, "ABONO")

    if not valido.valido:
        return f"el movimiento valido fue rechazado: {valido.errores}", False

    # REGLA 4: el saldo nuevo lo calcula la funcion que replica el trigger.
    nuevo_saldo = reglas.calcular_ahorro_actualizado(inversion, monto, "ABONO")
    saldo_coincide = nuevo_saldo == valido.datos["saldo_actualizado"]

    movimiento = {
        "nro_movimiento": NRO_MOVIMIENTO_PRUEBA,
        "fecha": datetime.now().isoformat(),
        "tipo_movimiento": "ABONO",
        "monto": monto,
        "signo": 1,
        "monto_con_signo": monto,
    }

    # Se prepara el documento como quedara, para recalcular "analisis".
    documento_modificado = copy.deepcopy(documento)
    inversion_modificada = buscar_inversion(documento_modificado, INVERSION_TRABAJO)
    inversion_modificada["monto_total_ahorrado"] = nuevo_saldo
    inversion_modificada["movimientos"].append(movimiento)
    analisis = transform.recalcular_analisis(documento_modificado)

    resultado = base[COLECCION_CLIENTES].update_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {
            "$set": {"analisis": analisis},
            "$inc": {"inversiones.$[inv].monto_total_ahorrado": monto},
            "$push": {"inversiones.$[inv].movimientos": movimiento},
        },
        array_filters=[{"inv.nro_solic_prod": INVERSION_TRABAJO}],
    )

    actualizado = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    inversion_actualizada = buscar_inversion(actualizado, INVERSION_TRABAJO)

    obtenido = (
        f"movimiento ABONO de ${monto:,} insertado; "
        f"saldo de la inversion {inversion['monto_total_ahorrado']:,} -> "
        f"{inversion_actualizada['monto_total_ahorrado']:,} "
        f"(REGLA 4 aplicada con $inc); "
        f"movimientos: {len(inversion['movimientos'])} -> {len(inversion_actualizada['movimientos'])}; "
        f"analisis.total_ahorrado recalculado: "
        f"{actualizado['analisis']['total_ahorrado']:,}; "
        f"REGLA 3: monto negativo rechazado={monto_invalido_rechazado}, "
        f"tipo invalido rechazado={not tipo_invalido.valido}"
    )
    cumple = (
        resultado.modified_count == 1
        and inversion_actualizada["monto_total_ahorrado"] == nuevo_saldo
        and saldo_coincide
        and monto_invalido_rechazado
        and not tipo_invalido.valido
        and actualizado["analisis"]["total_ahorrado"] == analisis["total_ahorrado"]
    )
    return obtenido, cumple


# ==========================================================================
# READ
# ==========================================================================

def caso_r1_leer_cliente(base, entorno):
    """
    R1 - Busca un cliente por su clave primaria (_id = nro_cliente).
    """
    documento = base[COLECCION_CLIENTES].find_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {"_id": 1, "nro_cliente": 1, "nombre_completo": 1, "analisis": 1},
    )
    if documento is None:
        return "el cliente no existe", False

    obtenido = (
        f"cliente {documento['nro_cliente']} ({documento['nombre_completo']}); "
        f"clasificacion={documento['analisis']['clasificacion']}, "
        f"saldo=${documento['analisis']['saldo_pendiente']:,}, "
        f"ahorrado=${documento['analisis']['total_ahorrado']:,}"
    )
    return obtenido, True


def caso_r2_filtrar_clientes(base, entorno):
    """
    R2 - Filtra por clasificacion y saldo, con proyeccion y orden.

    Es la consulta que responde "¿quienes son los clientes en riesgo y
    cuanto nos deben?".
    """
    filtro = {
        "analisis.clasificacion": "RIESGO",
        "analisis.saldo_pendiente": {"$gt": 100000},
    }
    documentos = list(
        base[COLECCION_CLIENTES].find(
            filtro,
            {
                "_id": 0,
                "nro_cliente": 1,
                "nombre_completo": 1,
                "analisis.clasificacion": 1,
                "analisis.saldo_pendiente": 1,
                "analisis.porcentaje_pagado": 1,
            },
        ).sort("analisis.saldo_pendiente", -1).limit(5)
    )

    total = base[COLECCION_CLIENTES].count_documents(filtro)
    detalle = ", ".join(
        f"{d['nro_cliente']} (${d['analisis']['saldo_pendiente']:,})"
        for d in documentos
    )
    obtenido = f"{total} clientes en RIESGO con saldo > $100.000; top 5: {detalle}"
    return obtenido, total > 0 and len(documentos) == min(5, total)


def caso_r3_contar_por_clasificacion(base, entorno):
    """
    R3 - Cuenta los clientes por clasificacion.

    Se excluye el cliente de prueba (9001), que todavia existe porque el
    caso de borrado D1 viene despues: el conteo debe reflejar los 130
    clientes reales migrados desde Oracle.
    """
    pipeline = [
        {"$match": {"nro_cliente": {"$ne": NRO_CLIENTE_PRUEBA}}},
        {"$group": {
            "_id": "$analisis.clasificacion",
            "clientes": {"$sum": 1},
            "saldo": {"$sum": "$analisis.saldo_pendiente"},
        }},
        {"$sort": {"clientes": -1}},
    ]
    filas = list(base[COLECCION_CLIENTES].aggregate(pipeline))

    detalle = " | ".join(
        f"{f['_id']}: {f['clientes']} clientes, saldo ${f['saldo']:,}" for f in filas
    )
    total = sum(f["clientes"] for f in filas)
    obtenido = f"{detalle} (total: {total} clientes migrados)"
    return obtenido, total == TOTAL_CLIENTES_MIGRADOS


def caso_r4_agregar_por_producto(base, entorno):
    """
    R4 - Agrega el saldo ahorrado por producto con $unwind + $group.

    Demuestra que los movimientos embebidos permiten agregar sin $lookup.
    """
    pipeline = [
        {"$unwind": "$inversiones"},
        {"$group": {
            "_id": "$inversiones.producto.nombre",
            "saldo": {"$sum": "$inversiones.monto_total_ahorrado"},
            "clientes": {"$sum": 1},
            "movimientos": {"$sum": {"$size": "$inversiones.movimientos"}},
        }},
        {"$sort": {"saldo": -1}},
        {"$limit": 5},
    ]
    filas = list(base[COLECCION_CLIENTES].aggregate(pipeline))

    detalle = " | ".join(
        f"{f['_id']}: ${f['saldo']:,} ({f['clientes']} clientes, "
        f"{f['movimientos']} movimientos)" for f in filas
    )
    obtenido = f"top 5 productos por saldo ahorrado: {detalle}"
    return obtenido, len(filas) > 0


def caso_r5_consultar_array_embebido(base, entorno):
    """
    R5 - Consulta dentro del array embebido de cuotas.

    Busca las cuotas VENCIDAS del cliente de trabajo. En el modelo relacional
    esto habria exigido un JOIN con cuota_credito_cliente; en el documento se
    resuelve con $elemMatch.
    """
    documento = base[COLECCION_CLIENTES].find_one(
        {
            "nro_cliente": NRO_CLIENTE_TRABAJO,
            "creditos": {
                "$elemMatch": {
                    "cuotas": {
                        "$elemMatch": {"estado": "VENCIDA"}
                    }
                }
            },
        },
        {
            "_id": 0,
            "nro_cliente": 1,
            "creditos": {
                "$elemMatch": {
                    "cuotas": {"$elemMatch": {"estado": "VENCIDA"}}
                }
            },
        },
    )

    if documento is None:
        return "no se encontraron cuotas vencidas", False

    vencidas = []
    for credito in documento["creditos"]:
        for cuota in credito.get("cuotas", []):
            if cuota["estado"] == "VENCIDA":
                vencidas.append(
                    f"{credito['nro_solic_credito']}/{cuota['nro_cuota']} "
                    f"(${cuota['saldo_por_pagar']:,}, {cuota['dias_atraso']} dias)"
                )

    obtenido = (
        f"{len(vencidas)} cuotas vencidas embebidas en el documento: "
        f"{', '.join(vencidas)}"
    )
    return obtenido, len(vencidas) > 0


def caso_r6_buscar_por_texto(base, entorno):
    """
    R6 - Busca por nombre usando el indice de texto.
    """
    documentos = list(
        base[COLECCION_CLIENTES].find(
            {"$text": {"$search": "QUINTANA"}},
            {
                "_id": 0,
                "nro_cliente": 1,
                "nombre_completo": 1,
                "analisis.clasificacion": 1,
                "puntaje": {"$meta": "textScore"},
            },
        ).sort("puntaje", {"$meta": "textScore"}).limit(5)
    )

    detalle = ", ".join(
        f"{d['nro_cliente']} {d['nombre_completo']}" for d in documentos
    )
    obtenido = f"busqueda de texto 'QUINTANA': {len(documentos)} resultado(s) -> {detalle}"
    return obtenido, len(documentos) > 0


def caso_r7_leer_bitacora(base, entorno):
    """
    R7 - Lee la bitacora de pagos de un cliente, ordenada por fecha.
    """
    documentos = list(
        base[COLECCION_BITACORA].find(
            {"nro_cliente": NRO_CLIENTE_TRABAJO},
            {
                "_id": 1,
                "nro_solic_credito": 1,
                "nro_cuota": 1,
                "fecha_evento": 1,
                "monto_pagado_anterior": 1,
                "monto_pagado_nuevo": 1,
                "forma_pago": 1,
            },
        ).sort("fecha_evento", 1)
    )

    detalle = " | ".join(
        f"{d['nro_solic_credito']}/{d['nro_cuota']}: "
        f"{d['monto_pagado_anterior']} -> {d['monto_pagado_nuevo']} ({d['forma_pago']})"
        for d in documentos
    )
    obtenido = f"{len(documentos)} evento(s) de pago del cliente {NRO_CLIENTE_TRABAJO}: {detalle}"
    return obtenido, len(documentos) > 0


# ==========================================================================
# UPDATE
# ==========================================================================

def caso_u1_actualizar_contacto(base, entorno):
    """
    U1 - Actualiza los datos de contacto con $set.
    """
    entorno.guardar_cliente(NRO_CLIENTE_TRABAJO)

    nuevo_telefono = "+56 9 8765 4321"
    resultado = base[COLECCION_CLIENTES].update_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {"$set": {"contacto.fono_contacto": nuevo_telefono}},
    )

    documento = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    telefono = documento["contacto"]["fono_contacto"]

    obtenido = (
        f"fono_contacto actualizado a '{telefono}' "
        f"(documentos modificados: {resultado.modified_count})"
    )
    return obtenido, telefono == nuevo_telefono and resultado.modified_count == 1


def caso_u2_registrar_pago(base, entorno):
    """
    U2 - Registra un pago completo con las REGLAS 1 y 2.

    Es el caso central del CRUD: una sola operacion de negocio que, en el
    modelo relacional, habria que resolver actualizando el saldo de la cuota,
    derivando el saldo por trigger y grabando el evento de auditoria. En
    MongoDB se resuelve con $set sobre el array de cuotas, $push sobre el
    historial de pagos y un $set del bloque analisis recalculado.

    Primero se prueba que un pago fuera de rango es RECHAZADO por la regla 1.
    """
    documento = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    entorno.guardar_cliente(NRO_CLIENTE_TRABAJO)

    credito, cuota = buscar_cuota(documento, CREDITO_TRABAJO, CUOTA_TRABAJO_PAGO)
    if cuota is None:
        return f"no se encontro la cuota {CREDITO_TRABAJO}/{CUOTA_TRABAJO_PAGO}", False

    # --- REGLA 1: un pago mayor que el valor de la cuota debe rechazarse ---
    pago_invalido = reglas.validar_pago_cuota(
        cuota["valor_cuota"], cuota["valor_cuota"] + 1000, cuota["saldo_por_pagar"]
    )
    rechazado = not pago_invalido.valido

    # --- REGLA 1: el pago valido ---
    monto_pagado = cuota["valor_cuota"]
    valido = reglas.validar_pago_cuota(
        cuota["valor_cuota"], monto_pagado, cuota["saldo_por_pagar"]
    )
    if not valido.valido:
        return f"el pago valido fue rechazado: {valido.errores}", False

    saldo = valido.datos["saldo_por_pagar"]
    evento = reglas.construir_evento_bitacora(
        cuota, NRO_CLIENTE_TRABAJO, cuota["monto_pagado"], monto_pagado,
        "Transferencia Electronica",
        nro_credito=CREDITO_TRABAJO,
        fecha_evento=datetime.now().isoformat(),
        id_bitacora=siguiente_id_bitacora(base[COLECCION_BITACORA]),
    )

    # 1) Actualizar la cuota (monto pagado y saldo derivado) y el analisis.
    documento_modificado = copy.deepcopy(documento)
    credito_mod, cuota_mod = buscar_cuota(
        documento_modificado, CREDITO_TRABAJO, CUOTA_TRABAJO_PAGO
    )
    cuota_mod["monto_pagado"] = monto_pagado
    cuota_mod["saldo_por_pagar"] = saldo
    cuota_mod["estado"] = "PAGADA"
    cuota_mod["fecha_pago"] = datetime.now().isoformat()
    cuota_mod["forma_pago"] = "Transferencia Electronica"
    analisis = transform.recalcular_analisis(documento_modificado)

    resultado = base[COLECCION_CLIENTES].update_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {
            "$set": {
                "creditos.$[cred].cuotas.$[cuo].monto_pagado": monto_pagado,
                "creditos.$[cred].cuotas.$[cuo].saldo_por_pagar": saldo,
                "creditos.$[cred].cuotas.$[cuo].estado": "PAGADA",
                "creditos.$[cred].cuotas.$[cuo].fecha_pago": cuota_mod["fecha_pago"],
                "creditos.$[cred].cuotas.$[cuo].forma_pago": "Transferencia Electronica",
                "analisis": analisis,
            },
            "$push": {
                "historial_pagos": {
                    "nro_solic_credito": CREDITO_TRABAJO,
                    "nro_cuota": CUOTA_TRABAJO_PAGO,
                    "fecha_evento": datetime.now().isoformat(),
                    "monto_pagado_anterior": cuota["monto_pagado"],
                    "monto_pagado_nuevo": monto_pagado,
                    "saldo_resultante": saldo,
                    "forma_pago": "Transferencia Electronica",
                    "estado_cuota": "PAGADA",
                }
            },
        },
        array_filters=[
            {"cred.nro_solic_credito": CREDITO_TRABAJO},
            {"cuo.nro_cuota": CUOTA_TRABAJO_PAGO},
        ],
    )

    # 2) Grabar el evento de auditoria (REGLA 2).
    base[COLECCION_BITACORA].insert_one(evento)
    entorno.creados_bitacora.append(evento["_id"])

    # 3) Verificar el resultado leyendo el documento.
    final = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    _, cuota_8 = buscar_cuota(final, CREDITO_TRABAJO, CUOTA_TRABAJO_PAGO)
    eventos = base[COLECCION_BITACORA].count_documents(
        {
            "nro_cliente": NRO_CLIENTE_TRABAJO,
            "nro_solic_credito": CREDITO_TRABAJO,
            "nro_cuota": CUOTA_TRABAJO_PAGO,
        }
    )

    obtenido = (
        f"pago de ${monto_pagado:,} registrado en la cuota "
        f"{CREDITO_TRABAJO}/{CUOTA_TRABAJO_PAGO}: "
        f"monto_pagado={cuota_8['monto_pagado']:,}, saldo={cuota_8['saldo_por_pagar']:,}, "
        f"estado={cuota_8['estado']}; analisis recalculado "
        f"(saldo {documento['analisis']['saldo_pendiente']:,} -> {final['analisis']['saldo_pendiente']:,}, "
        f"pago {documento['analisis']['porcentaje_pagado']}% -> {final['analisis']['porcentaje_pagado']}%); "
        f"evento en bitacora: {eventos}; "
        f"REGLA 1: pago fuera de rango rechazado={rechazado}"
    )
    cumple = (
        resultado.modified_count == 1
        and cuota_8["monto_pagado"] == monto_pagado
        and cuota_8["saldo_por_pagar"] == saldo
        and eventos >= 1
        and rechazado
    )
    return obtenido, cumple


def caso_u3_abonar_inversion(base, entorno):
    """
    U3 - Abona a una inversion: $inc del saldo + $push del movimiento.

    Aplica las REGLAS 3 y 4 en una sola operacion de MongoDB, que es el
    equivalente del INSERT que dispara los dos triggers de Oracle.
    """
    documento = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    entorno.guardar_cliente(NRO_CLIENTE_TRABAJO)

    inversion = buscar_inversion(documento, INVERSION_TRABAJO_ALTERNATIVA)
    if inversion is None:
        inversion = buscar_inversion(documento, INVERSION_TRABAJO)
    if inversion is None:
        return "no se encontro una inversion del cliente de trabajo", False

    nro_solic_prod = inversion["nro_solic_prod"]
    monto = 30000

    # REGLA 3: validacion previa del movimiento.
    valido = reglas.validar_movimiento(inversion, monto, "ABONO")
    if not valido.valido:
        return f"el movimiento valido fue rechazado: {valido.errores}", False

    # REGLA 4: el saldo nuevo lo calcula la funcion que replica el trigger.
    nuevo_saldo = reglas.calcular_ahorro_actualizado(inversion, monto, "ABONO")
    saldo_coincide = nuevo_saldo == valido.datos["saldo_actualizado"]

    movimiento = {
        "nro_movimiento": NRO_MOVIMIENTO_ALTERNATIVO,
        "fecha": datetime.now().isoformat(),
        "tipo_movimiento": "ABONO",
        "monto": monto,
        "signo": 1,
        "monto_con_signo": monto,
    }

    # Se prepara el documento como quedara, para recalcular "analisis".
    documento_modificado = copy.deepcopy(documento)
    inversion_modificada = buscar_inversion(documento_modificado, nro_solic_prod)
    inversion_modificada["monto_total_ahorrado"] = nuevo_saldo
    inversion_modificada["movimientos"].append(movimiento)
    analisis = transform.recalcular_analisis(documento_modificado)

    resultado = base[COLECCION_CLIENTES].update_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {
            "$set": {"analisis": analisis},
            "$inc": {"inversiones.$[inv].monto_total_ahorrado": monto},
            "$push": {"inversiones.$[inv].movimientos": movimiento},
        },
        array_filters=[{"inv.nro_solic_prod": nro_solic_prod}],
    )

    final = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    inversion_final = buscar_inversion(final, nro_solic_prod)

    obtenido = (
        f"abono de ${monto:,} en la inversion {nro_solic_prod}: "
        f"saldo {inversion['monto_total_ahorrado']:,} -> {inversion_final['monto_total_ahorrado']:,}; "
        f"movimientos {len(inversion['movimientos'])} -> {len(inversion_final['movimientos'])}; "
        f"ahorro total del cliente: ${final['analisis']['total_ahorrado']:,}"
    )
    cumple = (
        resultado.modified_count == 1
        and inversion_final["monto_total_ahorrado"] == inversion["monto_total_ahorrado"] + monto
        and len(inversion_final["movimientos"]) == len(inversion["movimientos"]) + 1
        and saldo_coincide
        and final["analisis"]["total_ahorrado"] == analisis["total_ahorrado"]
    )
    return obtenido, cumple


def caso_u4_actualizar_clasificacion(base, entorno):
    """
    U4 - Actualiza un campo del documento con $set (clasificacion).
    """
    entorno.guardar_cliente(NRO_CLIENTE_TRABAJO)

    resultado = base[COLECCION_CLIENTES].update_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {"$set": {"analisis.motivo_clasificacion": "Actualizado por prueba CRUD EVAL 3"}},
    )

    documento = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    motivo = documento["analisis"]["motivo_clasificacion"]

    obtenido = (
        f"motivo_clasificacion actualizado a '{motivo}' "
        f"(documentos modificados: {resultado.modified_count})"
    )
    return obtenido, resultado.modified_count == 1


# ==========================================================================
# DELETE
# ==========================================================================

def caso_d1_eliminar_cliente(base, entorno):
    """
    D1 - Elimina el cliente de prueba creado en C1.
    """
    resultado = base[COLECCION_CLIENTES].delete_one({"nro_cliente": NRO_CLIENTE_PRUEBA})
    restantes = base[COLECCION_CLIENTES].count_documents({"nro_cliente": NRO_CLIENTE_PRUEBA})

    obtenido = (
        f"documentos eliminados: {resultado.deleted_count}; "
        f"clientes de prueba restantes: {restantes}"
    )
    return obtenido, resultado.deleted_count == 1 and restantes == 0


def caso_d2_eliminar_movimiento(base, entorno):
    """
    D2 - Elimina un movimiento de una inversion y revierte su $inc.

    Muestra que en el modelo documental el movimiento es parte del documento:
    borrarlo es una operacion sobre el array, no un DELETE en otra tabla.

    Al quitar el movimiento, el bloque "analisis" tambien se recalcula: si no,
    el documento quedaria con un analisis.total_ahorrado que ya no corresponde
    a sus inversiones.
    """
    entorno.guardar_cliente(NRO_CLIENTE_TRABAJO)

    documento = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    inversion = buscar_inversion(documento, INVERSION_TRABAJO)
    if inversion is None or not inversion.get("movimientos"):
        return "no hay movimientos que borrar", False

    movimiento = inversion["movimientos"][0]
    saldo_anterior = inversion["monto_total_ahorrado"]

    # 1) Restar el monto del saldo (el signo inverso del $inc del abono).
    base[COLECCION_CLIENTES].update_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {"$inc": {"inversiones.$[inv].monto_total_ahorrado": -movimiento["monto_con_signo"]}},
        array_filters=[{"inv.nro_solic_prod": inversion["nro_solic_prod"]}],
    )

    # 2) Quitar el movimiento del array.
    resultado = base[COLECCION_CLIENTES].update_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {"$pull": {"inversiones.$[inv].movimientos": {"nro_movimiento": movimiento["nro_movimiento"]}}},
        array_filters=[{"inv.nro_solic_prod": inversion["nro_solic_prod"]}],
    )

    final = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    inversion_final = buscar_inversion(final, inversion["nro_solic_prod"])
    quedan = any(
        m["nro_movimiento"] == movimiento["nro_movimiento"]
        for m in inversion_final["movimientos"]
    )

    # 3) Refrescar el bloque "analisis" con el documento ya sin el movimiento.
    analisis = transform.recalcular_analisis(final)
    base[COLECCION_CLIENTES].update_one(
        {"nro_cliente": NRO_CLIENTE_TRABAJO},
        {"$set": {"analisis": analisis}},
    )
    final = base[COLECCION_CLIENTES].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})

    obtenido = (
        f"movimiento {movimiento['nro_movimiento']} eliminado del array; "
        f"movimientos {len(inversion['movimientos'])} -> {len(inversion_final['movimientos'])}; "
        f"saldo ajustado {saldo_anterior:,} -> {inversion_final['monto_total_ahorrado']:,}; "
        f"analisis.total_ahorrado recalculado: {final['analisis']['total_ahorrado']:,}; "
        f"el movimiento sigue presente: {quedan}"
    )
    return obtenido, resultado.modified_count == 1 and not quedan


def caso_d3_eliminar_evento_bitacora(base, entorno):
    """
    D3 - Elimina un evento de la bitacora de pagos.
    """
    documento = base[COLECCION_BITACORA].find_one({"nro_cliente": NRO_CLIENTE_TRABAJO})
    if documento is None:
        return "no hay eventos de bitacora", False

    entorno.guardar_bitacora(documento["_id"])

    resultado = base[COLECCION_BITACORA].delete_one({"_id": documento["_id"]})
    restantes = base[COLECCION_BITACORA].count_documents({"_id": documento["_id"]})

    obtenido = (
        f"evento _id={documento['_id']} eliminado; "
        f"eventos totales ahora: {base[COLECCION_BITACORA].count_documents({})}; "
        f"el evento sigue presente: {restantes > 0}"
    )
    return obtenido, resultado.deleted_count == 1 and restantes == 0


# ==========================================================================
# ARNES
# ==========================================================================

CASOS = [
    ("C1", "Create - Insertar un cliente nuevo con $jsonSchema", caso_c1_crear_cliente),
    ("C2", "Create - Insertar un catalogo de producto", caso_c2_crear_catalogo),
    ("C3", "Create - Insertar un evento de auditoria de pago (regla 2)", caso_c3_crear_evento_bitacora),
    ("C4", "Create - Insertar un movimiento de ahorro (reglas 3 y 4)", caso_c4_crear_movimiento),
    ("R1", "Read - Buscar un cliente por clave primaria", caso_r1_leer_cliente),
    ("R2", "Read - Filtrar clientes por clasificacion y saldo", caso_r2_filtrar_clientes),
    ("R3", "Read - Contar clientes por clasificacion", caso_r3_contar_por_clasificacion),
    ("R4", "Read - Agregar saldo por producto ($unwind + $group)", caso_r4_agregar_por_producto),
    ("R5", "Read - Consultar dentro de un array embebido ($elemMatch)", caso_r5_consultar_array_embebido),
    ("R6", "Read - Buscar por nombre con el indice de texto", caso_r6_buscar_por_texto),
    ("R7", "Read - Leer la bitacora de pagos de un cliente", caso_r7_leer_bitacora),
    ("U1", "Update - Actualizar datos de contacto ($set)", caso_u1_actualizar_contacto),
    ("U2", "Update - Registrar un pago (reglas 1 y 2)", caso_u2_registrar_pago),
    ("U3", "Update - Abonar a una inversion ($inc + $push)", caso_u3_abonar_inversion),
    ("U4", "Update - Actualizar la clasificacion ($set)", caso_u4_actualizar_clasificacion),
    ("D1", "Delete - Eliminar el cliente de prueba", caso_d1_eliminar_cliente),
    ("D2", "Delete - Eliminar un movimiento y revertir su $inc", caso_d2_eliminar_movimiento),
    ("D3", "Delete - Eliminar un evento de la bitacora", caso_d3_eliminar_evento_bitacora),
]


def ejecutar(base, restaurar):
    """
    Ejecuta todos los casos y devuelve el reporte.

    Si restaurar es True, al final se devuelven los documentos modificados a
    su estado original y se verifica que la base quedo igual que estaba.
    """
    entorno = EntornoPrueba(base)
    antes = totales_base(base)

    print()
    print("=" * 78)
    print("  KOPERA - CRUD en MongoDB Atlas (Python)")
    print("=" * 78)
    print(f"  Fecha           : {datetime.now():%d/%m/%Y %H:%M}")
    print(f"  Restaurar al final: {'si' if restaurar else 'no'}")
    print()

    resultados = []

    for codigo, titulo, funcion in CASOS:
        print(f"  {codigo}  {titulo}")
        try:
            obtenido, cumple = funcion(base, entorno)
            error = None
        except Exception as e:
            obtenido = f"ERROR: {type(e).__name__}: {e}"
            cumple = False
            error = str(e)

        resultados.append({
            "codigo": codigo,
            "titulo": titulo,
            "obtenido": obtenido,
            "cumple": cumple,
            "error": error,
        })
        print(f"       {'CUMPLE' if cumple else 'NO CUMPLE'}: {obtenido}")
        print()

    # ---------------------------------------------------------------- cierre
    print("=" * 78)
    print("  VERIFICACION DE INTEGRIDAD")
    print("=" * 78)

    if restaurar:
        restaurado = entorno.restaurar()
        print(f"  Documentos restaurados: {restaurado['clientes_restaurados']} cliente(s), "
              f"{restaurado['bitacora_restaurada']} evento(s) de bitacora, "
              f"{restaurado['catalogos_restaurados']} catalogo(s)")
        print()

    despues = totales_base(base)
    print(f"  {'concepto':<26} {'antes':>14} {'despues':>14}  estado")
    print("  " + "-" * 66)
    todo_ok = True
    for clave, etiqueta in (
        ("clientes", "Clientes"),
        ("bitacora", "Eventos de bitacora"),
        ("saldo", "Saldo de cartera"),
        ("pagado", "Total pagado"),
        ("ahorrado", "Total ahorrado"),
    ):
        igual = antes.get(clave) == despues.get(clave)
        todo_ok = todo_ok and igual
        print(f"  {etiqueta:<26} {antes.get(clave, 0):>14,} {despues.get(clave, 0):>14,}  "
              f"{'igual' if igual else 'DIFERENTE'}")

    print()
    cumplidos = sum(1 for r in resultados if r["cumple"])
    print(f"  Casos ejecutados: {len(resultados)} | cumplidos: {cumplidos} | "
          f"fallidos: {len(resultados) - cumplidos}")
    print(f"  Integridad de la base: {'OK' if todo_ok else 'REVISAR'}")
    print()

    return {
        "resultados": resultados,
        "cumplidos": cumplidos,
        "total": len(resultados),
        "integridad_ok": todo_ok,
        "antes": antes,
        "despues": despues,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Demostracion CRUD de KOPERA sobre MongoDB Atlas."
    )
    parser.add_argument(
        "--sin-restaurar",
        action="store_true",
        help="No restaura los documentos modificados (deja los cambios aplicados).",
    )
    args = parser.parse_args()

    with conectar_mongodb() as cliente:
        base = obtener_base_mongodb(cliente)
        reporte = ejecutar(base, restaurar=not args.sin_restaurar)

    return 0 if (reporte["cumplidos"] == reporte["total"] and reporte["integridad_ok"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
