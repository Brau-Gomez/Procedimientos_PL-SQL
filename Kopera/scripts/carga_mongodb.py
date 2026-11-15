"""
Carga de los documentos migrados a MongoDB Atlas (EVAL 3).

Este modulo ESCRIBE en Atlas. Recibe los documentos ya transformados y:

  1. crea las colecciones con un validador $jsonSchema (la "Create" con
     validacion que exige el enunciado), de modo que el servidor mismo
     rechaza un documento mal formado;
  2. crea los indices que soportan las consultas de lectura del informe;
  3. inserta los documentos.

Decisiones de diseno:

- IDEMPOTENCIA. Las colecciones clientes, catalogos y bitacora_pagos se borran
  y se recargan en cada ejecucion: su fuente de verdad es Oracle, asi que lo
  correcto es que reflejen el estado actual, no que acumulen versiones.
  La coleccion procesos_mensuales NO se borra: es un historico de ejecuciones
  del proceso mensual y cada corrida agrega un documento nuevo.

- TIER M0. No se usa nada que exija Atlas Functions, triggers del servidor ni
  transacciones multi-documento. Los validadores $jsonSchema y los indices son
  funciones del servidor MongoDB y funcionan en el cluster gratuito.

- insert_many con ordered=False. Si un documento invalido aparece, el servidor
  lo rechaza y el resto se inserta; el reporte final indica cuantos quedaron.
"""

from pymongo import ASCENDING, DESCENDING, IndexModel, TEXT

from config import (
    COLECCION_BITACORA,
    COLECCION_CATALOGOS,
    COLECCION_CLIENTES,
    COLECCION_PROCESOS,
)

# ==========================================================================
# VALIDADORES $jsonSchema
# ==========================================================================
#
# El validador describe la forma minima que debe cumplir cada documento.
# Se usa validationAction "error": un documento que no cumple NO se inserta.
#
# Nota sobre los campos que pueden ser null: en Oracle, snombre y apmaterno
# son opcionales (hay clientes con un solo nombre), por eso el validador no
# los exige, pero si exige los que el negocio siempre tiene.

VALIDADOR_CLIENTES = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id", "nro_cliente", "run", "nombre", "nombre_completo",
            "creditos", "inversiones", "historial_pagos", "analisis",
        ],
        "properties": {
            "_id": {"bsonType": "int", "minimum": 1},
            "nro_cliente": {"bsonType": "int", "minimum": 1},
            "run": {"bsonType": "string", "minLength": 3},
            "nombre": {
                "bsonType": "object",
                "required": ["pnombre", "appaterno"],
                "properties": {
                    "pnombre": {"bsonType": "string", "minLength": 1},
                    "snombre": {"bsonType": ["string", "null"]},
                    "appaterno": {"bsonType": "string", "minLength": 1},
                    "apmaterno": {"bsonType": ["string", "null"]},
                },
            },
            "nombre_completo": {"bsonType": "string", "minLength": 1},
            "contacto": {
                "bsonType": "object",
                "properties": {
                    "correo": {"bsonType": ["string", "null"]},
                    "fono_contacto": {"bsonType": ["string", "int", "null"]},
                    "direccion": {"bsonType": ["string", "null"]},
                },
            },
            "ubicacion": {
                "bsonType": "object",
                "required": ["region", "comuna"],
                "properties": {
                    "region": {"bsonType": "string"},
                    "provincia": {"bsonType": "string"},
                    "comuna": {"bsonType": "string"},
                },
            },
            "creditos": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["nro_solic_credito", "tipo_credito", "cuotas"],
                    "properties": {
                        "nro_solic_credito": {"bsonType": "int"},
                        "monto_credito": {"bsonType": "number", "minimum": 0},
                        "cuotas": {
                            "bsonType": "array",
                            "items": {
                                "bsonType": "object",
                                "required": [
                                    "nro_cuota", "valor_cuota", "monto_pagado",
                                    "saldo_por_pagar", "estado",
                                ],
                                "properties": {
                                    "nro_cuota": {"bsonType": "int", "minimum": 1},
                                    "valor_cuota": {"bsonType": "number", "minimum": 0},
                                    "monto_pagado": {"bsonType": "number", "minimum": 0},
                                    "saldo_por_pagar": {"bsonType": "number", "minimum": 0},
                                    "estado": {
                                        "enum": ["PAGADA", "PARCIAL", "VENCIDA", "PENDIENTE"]
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "inversiones": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["nro_solic_prod", "producto", "monto_total_ahorrado"],
                    "properties": {
                        "nro_solic_prod": {"bsonType": "int"},
                        "monto_total_ahorrado": {"bsonType": "number", "minimum": 0},
                        "movimientos": {
                            "bsonType": "array",
                            "items": {
                                "bsonType": "object",
                                "required": ["nro_movimiento", "monto", "tipo_movimiento"],
                                "properties": {
                                    "nro_movimiento": {"bsonType": "int"},
                                    "monto": {"bsonType": "number", "minimum": 0},
                                    "tipo_movimiento": {"enum": ["ABONO", "RESCATE"]},
                                    "signo": {"enum": [1, -1]},
                                },
                            },
                        },
                    },
                },
            },
            "historial_pagos": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": [
                        "nro_solic_credito", "nro_cuota",
                        "monto_pagado_nuevo", "saldo_resultante",
                    ],
                    "properties": {
                        "monto_pagado_nuevo": {"bsonType": "number", "minimum": 0},
                        "saldo_resultante": {"bsonType": "number", "minimum": 0},
                    },
                },
            },
            "analisis": {
                "bsonType": "object",
                "required": [
                    "total_creditos", "total_pagado", "saldo_pendiente",
                    "porcentaje_pagado", "cuotas", "clasificacion", "alertas",
                ],
                "properties": {
                    "saldo_pendiente": {"bsonType": "number", "minimum": 0},
                    "porcentaje_pagado": {"bsonType": "number", "minimum": 0, "maximum": 100},
                    "cuotas": {
                        "bsonType": "object",
                        "required": ["total", "pagadas", "parciales", "vencidas", "pendientes"],
                    },
                    "clasificacion": {
                        "enum": ["RIESGO", "REGULAR", "BUENO", "OPORTUNIDAD", "SIN PRODUCTOS"]
                    },
                    "alertas": {"bsonType": "array", "items": {"bsonType": "string"}},
                },
            },
        },
    }
}

VALIDADOR_CATALOGOS = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "categoria", "nombre"],
        "properties": {
            "_id": {"bsonType": "string"},
            "categoria": {
                "enum": [
                    "INVERSION", "CREDITO", "FORMA_PAGO",
                    "TIPO_MOVIMIENTO", "APORTE_SBIF", "PROFESION", "TIPO_CONTRATO",
                ]
            },
            "codigo": {"bsonType": ["int", "null"]},
            "nombre": {"bsonType": "string", "minLength": 1},
        },
    }
}

VALIDADOR_BITACORA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id", "nro_solic_credito", "nro_cuota", "fecha_evento",
            "monto_pagado_nuevo", "valor_cuota", "saldo_resultante",
        ],
        "properties": {
            "_id": {"bsonType": "int"},
            "nro_solic_credito": {"bsonType": "int"},
            "nro_cuota": {"bsonType": "int", "minimum": 1},
            "nro_cliente": {"bsonType": "int"},
            "monto_pagado_anterior": {"bsonType": ["int", "null"]},
            "monto_pagado_nuevo": {"bsonType": "number", "minimum": 0},
            "valor_cuota": {"bsonType": "number", "minimum": 0},
            "saldo_resultante": {"bsonType": "number", "minimum": 0},
            "fecha_evento": {"bsonType": "string"},
        },
    }
}

VALIDADOR_PROCESOS = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id", "fecha_corte", "procedimiento",
            "clientes_analizados", "saldo_total_cartera", "lineas_salida",
        ],
        "properties": {
            "_id": {"bsonType": "string"},
            "fecha_corte": {"bsonType": "string"},
            "clientes_analizados": {"bsonType": "int", "minimum": 0},
            "saldo_total_cartera": {"bsonType": "number", "minimum": 0},
            "lineas_salida": {"bsonType": "array", "items": {"bsonType": "string"}},
        },
    }
}

VALIDADORES = {
    COLECCION_CLIENTES: VALIDADOR_CLIENTES,
    COLECCION_CATALOGOS: VALIDADOR_CATALOGOS,
    COLECCION_BITACORA: VALIDADOR_BITACORA,
    COLECCION_PROCESOS: VALIDADOR_PROCESOS,
}


# ==========================================================================
# INDICES
# ==========================================================================
#
# Cada indice responde a una consulta concreta del informe. Un indice que no
# se usa es solo espacio desperdiciado en el tier M0, asi que cada uno esta
# justificado con su consulta de lectura.

INDICES_CLIENTES = [
    # Identificacion: el _id ya es un indice unico, pero el RUN tambien lo es
    # porque es el identificador legal del cliente.
    IndexModel([("run", ASCENDING)], name="idx_clientes_run", unique=True),
    # Consultas de analisis y clasificacion
    IndexModel([("analisis.clasificacion", ASCENDING)], name="idx_clientes_clasificacion"),
    IndexModel([("analisis.saldo_pendiente", DESCENDING)], name="idx_clientes_saldo"),
    # Consultas geograficas
    IndexModel([("ubicacion.comuna", ASCENDING)], name="idx_clientes_comuna"),
    # Consulta "creditos de un cliente" y "clientes de un credito"
    IndexModel([("creditos.nro_solic_credito", ASCENDING)], name="idx_clientes_credito"),
    # Busqueda por nombre (indice de texto)
    IndexModel([("nombre_completo", TEXT)], name="idx_clientes_nombre_texto"),
]

INDICES_CATALOGOS = [
    IndexModel([("categoria", ASCENDING)], name="idx_catalogos_categoria"),
    IndexModel([("nombre", ASCENDING)], name="idx_catalogos_nombre"),
]

INDICES_BITACORA = [
    IndexModel([("nro_cliente", ASCENDING)], name="idx_bitacora_cliente"),
    IndexModel([("nro_solic_credito", ASCENDING), ("nro_cuota", ASCENDING)],
               name="idx_bitacora_cuota"),
    IndexModel([("fecha_evento", DESCENDING)], name="idx_bitacora_fecha"),
]

INDICES_PROCESOS = [
    IndexModel([("fecha_corte", DESCENDING)], name="idx_procesos_fecha"),
]

INDICES = {
    COLECCION_CLIENTES: INDICES_CLIENTES,
    COLECCION_CATALOGOS: INDICES_CATALOGOS,
    COLECCION_BITACORA: INDICES_BITACORA,
    COLECCION_PROCESOS: INDICES_PROCESOS,
}


# ==========================================================================
# FUNCIONES
# ==========================================================================

def eliminar_colecciones(base, colecciones):
    """
    Borra las colecciones indicadas (con sus indices) para recargar desde cero.

    Se usa antes de insertar en clientes, catalogos y bitacora_pagos. La
    coleccion de procesos NO se borra: es historico.
    """
    eliminadas = []
    for nombre in colecciones:
        if nombre in base.list_collection_names():
            base[nombre].drop()
            eliminadas.append(nombre)
    return eliminadas


def crear_colecciones(base):
    """
    Crea las colecciones con su validador $jsonSchema.

    Si la coleccion ya existe, se actualiza el validador con el comando
    collMod, que es la forma oficial de cambiar las reglas de validacion de
    una coleccion existente.
    """
    existentes = set(base.list_collection_names())
    creadas = []
    actualizadas = []

    for nombre, validador in VALIDADORES.items():
        if nombre in existentes:
            base.command(
                "collMod",
                nombre,
                validator=validador,
                validationLevel="strict",
                validationAction="error",
            )
            actualizadas.append(nombre)
        else:
            base.create_collection(
                nombre,
                validator=validador,
                validationLevel="strict",
                validationAction="error",
            )
            creadas.append(nombre)

    return creadas, actualizadas


def crear_indices(base):
    """Crea los indices de cada coleccion. Devuelve el total de indices."""
    total = 0
    for nombre, indices in INDICES.items():
        if nombre in base.list_collection_names():
            base[nombre].create_indexes(indices)
            total += len(indices)
    return total


def _errores_de_escritura(excepcion):
    """
    Normaliza los errores de escritura de PyMongo.

    Hay dos formas distintas de fallo y conviene tratar las dos:
      - WriteError (un solo documento): el detalle esta en excepcion.details,
        con las claves index, code, errmsg y errInfo directamente.
      - BulkWriteError (insert_many): el detalle esta en
        excepcion.details["writeErrors"], que es una lista.
    """
    detalles = getattr(excepcion, "details", None) or {}

    lista = detalles.get("writeErrors")
    if isinstance(lista, list):
        return lista, detalles.get("nInserted", 0)

    # WriteError individual: el propio detalle es el error.
    if "errmsg" in detalles:
        return [detalles], 0

    return [], 0


def insertar_documentos(coleccion, documentos):
    """
    Inserta una lista de documentos.

    Devuelve (insertados, rechazados). Los rechazados se devuelven con su
    error para que el reporte indique exactamente que documento fallo y por
    que: es la evidencia de que el validador $jsonSchema funciona.
    """
    if not documentos:
        return 0, []

    insertados = 0
    rechazados = []
    try:
        resultado = coleccion.insert_many(documentos, ordered=False)
        insertados = len(resultado.inserted_ids)
    except Exception as e:
        # insert_many con ordered=False lanza una BulkWriteError en el primer
        # error, pero el servidor ya habia insertado el resto.
        errores, ya_insertados = _errores_de_escritura(e)
        insertados = ya_insertados

        for error in errores:
            indice = error.get("index")
            documento = documentos[indice] if indice is not None else {}
            # errInfo trae el detalle de la regla de $jsonSchema incumplida:
            # sin esto el mensaje es solo "Document failed validation".
            err_info = error.get("errInfo") or {}
            rechazados.append({
                "indice": indice,
                "id": documento.get("_id"),
                "mensaje": error.get("errmsg"),
                "codigo": error.get("code"),
                "detalle": _resumir_err_info(err_info),
            })

        if not errores:
            rechazados.append({
                "indice": None,
                "id": None,
                "mensaje": str(e),
                "codigo": None,
                "detalle": "",
            })

    return insertados, rechazados


def _resumir_err_info(err_info):
    """
    Convierte el errInfo del servidor en un texto legible.

    El servidor envia la regla incumplida anidada:
        {"details": {"operatorName": "$jsonSchema",
                     "schemaRulesNotSatisfied": [{"operatorName": "properties",
                                                  "propertiesNotSatisfied": [
                                                      {"propertyName": "inversiones",
                                                       "description": "..."}]}]}}

    Para los fallos de enum, el servidor agrega el valor considerado y la
    lista de valores permitidos, que es lo mas util para corregir el dato.
    """
    detalles = err_info.get("details") or {}
    reglas = detalles.get("schemaRulesNotSatisfied") or []
    partes = []

    for regla in reglas:
        operador = regla.get("operatorName", "?")
        if "required" in regla:
            faltan = regla["required"].get("missing")
            if faltan:
                partes.append(f"falta el campo obligatorio: {', '.join(faltan)}")
        if "propertiesNotSatisfied" in regla:
            for propiedad in regla["propertiesNotSatisfied"]:
                nombre = propiedad.get("propertyName", "?")
                descripcion = propiedad.get("description", "")
                texto = f"campo '{nombre}' no cumple el esquema"
                if descripcion:
                    texto += f": {descripcion}"
                partes.append(texto)
        if "itemsNotSatisfied" in regla:
            partes.append(_resumir_items(regla["itemsNotSatisfied"]))
        if not any(k in regla for k in ("required", "propertiesNotSatisfied", "itemsNotSatisfied")):
            partes.append(f"regla incumplida: {operador} {regla}")

    return " | ".join(partes) if partes else str(err_info)


def _resumir_items(items):
    """Resume los elementos de un array que incumplen el esquema."""
    partes = []
    for item in items:
        considered = item.get("consideredValue")
        reason = item.get("reason", "")
        enum = item.get("enum")
        texto = "un elemento del array no cumple"
        if considered is not None:
            texto += f" (valor: {considered!r})"
        if enum:
            texto += f" - valores permitidos: {enum}"
        if reason:
            texto += f" - motivo: {reason}"
        partes.append(texto)
    return "; ".join(partes)


def cargar_todo(base, documentos_clientes, documentos_catalogos,
                documentos_bitacora, documentos_procesos=None):
    """
    Ejecuta la carga completa y devuelve un reporte.

    El reporte es el insumo del anexo del informe: muestra cuantos documentos
    entraron en cada coleccion y si el validador rechazo alguno.
    """
    # 1. Limpieza: las colecciones que reflejan Oracle se recargan desde cero.
    eliminadas = eliminar_colecciones(
        base, [COLECCION_CLIENTES, COLECCION_CATALOGOS, COLECCION_BITACORA]
    )

    # 2. Colecciones con validador
    creadas, actualizadas = crear_colecciones(base)

    # 3. Indices
    total_indices = crear_indices(base)

    # 4. Carga
    reporte = {
        "colecciones_eliminadas": eliminadas,
        "colecciones_creadas": creadas,
        "colecciones_validadas": actualizadas,
        "indices_creados": total_indices,
        "cargas": [],
        "total_insertados": 0,
        "total_rechazados": 0,
    }

    cargas = [
        (COLECCION_CLIENTES, documentos_clientes),
        (COLECCION_CATALOGOS, documentos_catalogos),
        (COLECCION_BITACORA, documentos_bitacora),
    ]
    if documentos_procesos:
        cargas.append((COLECCION_PROCESOS, documentos_procesos))

    for nombre, documentos in cargas:
        insertados, rechazados = insertar_documentos(base[nombre], documentos)
        reporte["cargas"].append({
            "coleccion": nombre,
            "recibidos": len(documentos),
            "insertados": insertados,
            "rechazados": len(rechazados),
            "detalle_rechazados": rechazados,
        })
        reporte["total_insertados"] += insertados
        reporte["total_rechazados"] += len(rechazados)

    return reporte


def verificar_carga(base):
    """Devuelve el conteo real de documentos por coleccion, leido del servidor."""
    conteos = {}
    for nombre in base.list_collection_names():
        conteos[nombre] = base[nombre].count_documents({})
    return conteos
