"""
Consultas de lectura sobre la base 'kopera'.

Todas las vistas de la app consumen funciones de este modulo: ninguna vista
arma un pipeline por su cuenta. La ventaja es doble:

  1. las agregaciones quedan documentadas en un solo lugar (sirven de anexo
     para el informe de la evaluacion);
  2. si cambia la forma del documento, se corrige aca y no en cada pantalla.

Las escrituras (el CRUD de demostracion) viven en operaciones.py, separadas a
proposito: leer y escribir tienen riesgos distintos.
"""

import re

from pymongo import DESCENDING

from config_app import (
    COLECCION_BITACORA,
    COLECCION_CATALOGOS,
    COLECCION_CLIENTES,
    COLECCION_PROCESOS,
    obtener_base,
)

# Columnas que necesita una LISTA de clientes. No se trae el documento
# completo: un cliente puede tener 48 cuotas y 10 movimientos, y la tabla solo
# muestra el resumen del bloque analisis.
PROYECCION_RESUMEN = {
    "_id": 1,
    "nro_cliente": 1,
    "run": 1,
    "nombre_completo": 1,
    "ubicacion.comuna": 1,
    "contacto.correo": 1,
    "analisis": 1,
}


# ==========================================================================
# PANEL GENERAL
# ==========================================================================

def resumen_general() -> dict:
    """
    KPIs del panel en UNA sola pasada sobre la coleccion de clientes.

    Se usa $group con $cond en vez de diez count_documents(): cada consulta
    separada seria un round-trip a Atlas, y el tier M0 no es gratis en latencia.
    """
    base = obtener_base()

    pipeline = [
        {
            "$group": {
                "_id": None,
                "clientes": {"$sum": 1},
                "con_credito": {
                    "$sum": {"$cond": [{"$gt": [{"$size": "$creditos"}, 0]}, 1, 0]}
                },
                "con_inversion": {
                    "$sum": {"$cond": [{"$gt": [{"$size": "$inversiones"}, 0]}, 1, 0]}
                },
                "con_alertas": {
                    "$sum": {
                        "$cond": [
                            {"$gt": [{"$size": "$analisis.alertas"}, 0]}, 1, 0
                        ]
                    }
                },
                "total_creditos": {"$sum": "$analisis.total_creditos"},
                "total_pagado": {"$sum": "$analisis.total_pagado"},
                "saldo_pendiente": {"$sum": "$analisis.saldo_pendiente"},
                "total_ahorrado": {"$sum": "$analisis.total_ahorrado"},
                "cuotas_total": {"$sum": "$analisis.cuotas.total"},
                "cuotas_pagadas": {"$sum": "$analisis.cuotas.pagadas"},
                "cuotas_parciales": {"$sum": "$analisis.cuotas.parciales"},
                "cuotas_vencidas": {"$sum": "$analisis.cuotas.vencidas"},
                "cuotas_pendientes": {"$sum": "$analisis.cuotas.pendientes"},
            }
        }
    ]

    fila = next(iter(base[COLECCION_CLIENTES].aggregate(pipeline)), None)
    if fila is None:
        return {"clientes": 0}

    fila.pop("_id", None)
    return fila


def por_clasificacion() -> list[dict]:
    """Cantidad de clientes por clasificacion financiera, de mayor a menor."""
    base = obtener_base()
    return list(
        base[COLECCION_CLIENTES].aggregate([
            {"$group": {"_id": "$analisis.clasificacion", "clientes": {"$sum": 1}}},
            {"$sort": {"clientes": DESCENDING}},
        ])
    )


def por_comuna(limite: int = 10) -> list[dict]:
    """Top de comunas por saldo pendiente de credito."""
    base = obtener_base()
    return list(
        base[COLECCION_CLIENTES].aggregate([
            {"$match": {"analisis.saldo_pendiente": {"$gt": 0}}},
            {
                "$group": {
                    "_id": "$ubicacion.comuna",
                    "clientes": {"$sum": 1},
                    "saldo": {"$sum": "$analisis.saldo_pendiente"},
                }
            },
            {"$sort": {"saldo": DESCENDING}},
            {"$limit": limite},
        ])
    )


def cartera_por_tipo_credito() -> list[dict]:
    """
    Saldo pendiente agrupado por tipo de credito.

    Requiere $unwind porque los creditos estan embebidos: primero se aplana un
    credito por fila y despues se agrupa por su tipo.
    """
    base = obtener_base()
    return list(
        base[COLECCION_CLIENTES].aggregate([
            {"$unwind": "$creditos"},
            {
                "$group": {
                    "_id": "$creditos.tipo_credito.nombre",
                    "creditos": {"$sum": 1},
                    "monto_credito": {"$sum": "$creditos.monto_credito"},
                    "saldo": {
                        "$sum": {"$sum": "$creditos.cuotas.saldo_por_pagar"}
                    },
                }
            },
            {"$sort": {"monto_credito": DESCENDING}},
        ])
    )


# ==========================================================================
# CLIENTES
# ==========================================================================

def buscar_clientes(termino: str = "", clasificacion: str = "",
                    solo_credito: bool = False,
                    solo_inversion: bool = False,
                    limite: int = 300) -> list[dict]:
    """
    Buscador de la pantalla de clientes.

    - Si el termino son solo digitos, busca por nro_cliente exacto o por RUN
      que empiece con esos digitos.
    - Si no, busca por nombre (regex sin distinguir mayusculas, escapando
      el texto para que un '.' o '(' no rompa la expresion).
    """
    base = obtener_base()
    filtro = {}

    termino = (termino or "").strip()
    if termino:
        if termino.isdigit():
            filtro["$or"] = [
                {"nro_cliente": int(termino)},
                {"run": {"$regex": f"^{re.escape(termino)}"}},
            ]
        else:
            filtro["nombre_completo"] = {
                "$regex": re.escape(termino), "$options": "i"
            }

    if clasificacion:
        filtro["analisis.clasificacion"] = clasificacion

    if solo_credito:
        filtro["creditos.0"] = {"$exists": True}

    if solo_inversion:
        filtro["inversiones.0"] = {"$exists": True}

    return list(
        base[COLECCION_CLIENTES]
        .find(filtro, PROYECCION_RESUMEN)
        .sort("analisis.saldo_pendiente", DESCENDING)
        .limit(limite)
    )


def obtener_cliente(nro_cliente: int) -> dict | None:
    """Trae el documento COMPLETO de un cliente (para la ficha)."""
    base = obtener_base()
    return base[COLECCION_CLIENTES].find_one({"_id": int(nro_cliente)})


def opciones_clasificacion() -> list[str]:
    """Lista de clasificaciones existentes, para poblar el filtro."""
    return sorted(
        r["_id"] for r in por_clasificacion() if r.get("_id")
    )


def opciones_clientes() -> list[dict]:
    """
    Lista liviana (id, run, nombre) para el selector de la ficha.

    Se proyectan solo tres campos: traer los 130 documentos completos solo
    para armar un desplegable seria mover decenas de MB sin necesidad.
    """
    base = obtener_base()
    return list(
        base[COLECCION_CLIENTES]
        .find({}, {"nro_cliente": 1, "run": 1, "nombre_completo": 1})
        .sort("nombre_completo", 1)
    )


def clientes_con_cuotas_abiertas() -> list[int]:
    """
    Ids de clientes que tienen al menos una cuota sin pagar.

    Se usa para que el formulario de pago abra en un cliente que realmente
    tenga algo que pagar: el primer cliente alfabético suele no tener créditos
    y el formulario aparecería vacío en la demo.

    Se resuelve recorriendo una proyección con solo los estados de las cuotas
    (unos pocos KB) en vez de un $elemMatch anidado, que seria mas dificil de
    leer para lo mismo.
    """
    base = obtener_base()
    abiertos = []
    for documento in base[COLECCION_CLIENTES].find(
        {}, {"creditos.cuotas.estado": 1}
    ):
        tiene = any(
            cuota.get("estado") != "PAGADA"
            for credito in documento.get("creditos") or []
            for cuota in credito.get("cuotas") or []
        )
        if tiene:
            abiertos.append(documento["_id"])
    return abiertos


# ==========================================================================
# CARTERA Y CUOTAS
# ==========================================================================
# Las cuotas estan EMBEBIDAS dentro de creditos, y los creditos dentro del
# cliente. Para analizarlas hay que aplanar dos niveles: $unwind de creditos y
# despues $unwind de creditos.cuotas. Esa es la diferencia principal con el
# esquema relacional, donde bastaba un JOIN.

# Mismas claves que usa el resumen del panel: asi graficos.barras_estado_cuotas
# sirve para las dos pantallas sin duplicar codigo.
CLAVES_ESTADO_CUOTA = {
    "PAGADA": "cuotas_pagadas",
    "PARCIAL": "cuotas_parciales",
    "VENCIDA": "cuotas_vencidas",
    "PENDIENTE": "cuotas_pendientes",
}


def cartera_resumen() -> dict:
    """
    Totales de cuotas por estado en una sola pasada sobre los clientes.

    Devuelve las mismas claves que resumen_general() (cuotas_pagadas, ...)
    para reutilizar el grafico de estados, mas los montos y el atraso maximo.
    """
    base = obtener_base()

    pipeline = [
        {"$unwind": "$creditos"},
        {"$unwind": "$creditos.cuotas"},
        {
            "$group": {
                "_id": "$creditos.cuotas.estado",
                "cuotas": {"$sum": 1},
                "valor": {"$sum": "$creditos.cuotas.valor_cuota"},
                "pagado": {"$sum": "$creditos.cuotas.monto_pagado"},
                "saldo": {"$sum": "$creditos.cuotas.saldo_por_pagar"},
                "con_atraso": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$creditos.cuotas.dias_atraso", 0]}, 1, 0
                        ]
                    }
                },
                "atraso_max": {"$max": "$creditos.cuotas.dias_atraso"},
            }
        },
    ]

    resumen = {clave: 0 for clave in CLAVES_ESTADO_CUOTA.values()}
    resumen.update({
        "cuotas_total": 0,
        "valor_total": 0,
        "pagado_total": 0,
        "saldo_total": 0,
        "monto_vencido": 0,
        "cuotas_con_atraso": 0,
        "atraso_maximo": 0,
    })

    for fila in base[COLECCION_CLIENTES].aggregate(pipeline):
        estado = fila.get("_id")
        clave = CLAVES_ESTADO_CUOTA.get(estado)

        if clave:
            resumen[clave] = fila.get("cuotas", 0)
        resumen["cuotas_total"] += fila.get("cuotas", 0)
        resumen["valor_total"] += fila.get("valor", 0) or 0
        resumen["pagado_total"] += fila.get("pagado", 0) or 0
        resumen["saldo_total"] += fila.get("saldo", 0) or 0
        resumen["cuotas_con_atraso"] += fila.get("con_atraso", 0) or 0
        resumen["atraso_maximo"] = max(
            resumen["atraso_maximo"], fila.get("atraso_max", 0) or 0
        )
        if estado == "VENCIDA":
            resumen["monto_vencido"] = fila.get("saldo", 0) or 0

    return resumen


def cartera_por_atraso() -> list[dict]:
    """
    Cuotas con atraso agrupadas por tramo, con su saldo.

    El tramo se calcula en la base con $switch (no en Python) para no traer
    las 519 cuotas solo para contarlas. Los cortes coinciden exactamente con
    formato.badge_atraso: 30 / 60 dias.
    """
    base = obtener_base()

    pipeline = [
        {"$unwind": "$creditos"},
        {"$unwind": "$creditos.cuotas"},
        {"$match": {"creditos.cuotas.dias_atraso": {"$gt": 0}}},
        {
            "$group": {
                "_id": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {"$lte": ["$creditos.cuotas.dias_atraso", 30]},
                                "then": "1 a 30 días",
                            },
                            {
                                "case": {"$lte": ["$creditos.cuotas.dias_atraso", 60]},
                                "then": "31 a 60 días",
                            },
                        ],
                        "default": "más de 60 días",
                    }
                },
                "cuotas": {"$sum": 1},
                "saldo": {"$sum": "$creditos.cuotas.saldo_por_pagar"},
            }
        },
    ]
    return list(base[COLECCION_CLIENTES].aggregate(pipeline))


def buscar_cuotas(estado: str = "", termino: str = "",
                  limite: int = 250) -> list[dict]:
    """
    Lista de cuotas aplanadas, con el cliente y el credito al que pertenecen.

    El filtro por cliente se aplica ANTES de los $unwind (sobre el documento
    completo); el filtro por estado se aplica DESPUES, sobre cada cuota ya
    separada. Si se aplicara antes, un cliente con una cuota pagada entraria
    igual al filtro "PAGADA" y luego aparecerian sus demas cuotas.
    """
    base = obtener_base()

    filtro_cliente = {}
    termino = (termino or "").strip()
    if termino:
        if termino.isdigit():
            filtro_cliente["$or"] = [
                {"nro_cliente": int(termino)},
                {"run": {"$regex": f"^{re.escape(termino)}"}},
            ]
        else:
            filtro_cliente["nombre_completo"] = {
                "$regex": re.escape(termino), "$options": "i"
            }

    pipeline = []
    if filtro_cliente:
        pipeline.append({"$match": filtro_cliente})

    pipeline += [
        {"$unwind": "$creditos"},
        {"$unwind": "$creditos.cuotas"},
    ]
    if estado:
        pipeline.append({"$match": {"creditos.cuotas.estado": estado}})

    pipeline += [
        {
            "$project": {
                "_id": 0,
                "nro_cliente": 1,
                "nombre_completo": 1,
                "nro_credito": "$creditos.nro_solic_credito",
                "tipo_credito": "$creditos.tipo_credito.nombre",
                "nro_cuota": "$creditos.cuotas.nro_cuota",
                "fecha_vencimiento": "$creditos.cuotas.fecha_vencimiento",
                "valor_cuota": "$creditos.cuotas.valor_cuota",
                "monto_pagado": "$creditos.cuotas.monto_pagado",
                "saldo_por_pagar": "$creditos.cuotas.saldo_por_pagar",
                "estado": "$creditos.cuotas.estado",
                "dias_atraso": "$creditos.cuotas.dias_atraso",
            }
        },
        # Lo mas urgente primero: mas dias de atraso y vencimiento mas antiguo.
        {"$sort": {"dias_atraso": DESCENDING, "fecha_vencimiento": 1}},
        {"$limit": limite},
    ]

    return list(base[COLECCION_CLIENTES].aggregate(pipeline))


# ==========================================================================
# INVERSIONES
# ==========================================================================

def inversiones_resumen() -> dict:
    """
    Totales del bloque inversiones: cantidad, ahorro y movimientos.

    $addToSet + $size cuenta clientes distintos sin necesitar un segundo
    count_documents: un cliente puede tener varias inversiones y no queremos
    contarlo dos veces.
    """
    base = obtener_base()

    pipeline = [
        {"$unwind": "$inversiones"},
        {
            "$group": {
                "_id": None,
                "inversiones": {"$sum": 1},
                "ahorro": {"$sum": "$inversiones.monto_total_ahorrado"},
                "movimientos": {
                    "$sum": {"$size": {"$ifNull": ["$inversiones.movimientos", []]}}
                },
                "clientes": {"$addToSet": "$_id"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "inversiones": 1,
                "ahorro": 1,
                "movimientos": 1,
                "clientes": {"$size": "$clientes"},
            }
        },
    ]

    fila = next(iter(base[COLECCION_CLIENTES].aggregate(pipeline)), None)
    if fila is None:
        return {"inversiones": 0, "ahorro": 0, "movimientos": 0, "clientes": 0}
    return fila


def inversiones_por_producto() -> list[dict]:
    """Ahorro total, cantidad de inversiones y clientes por producto."""
    base = obtener_base()

    pipeline = [
        {"$unwind": "$inversiones"},
        {
            "$group": {
                "_id": "$inversiones.producto.nombre",
                "inversiones": {"$sum": 1},
                "ahorro": {"$sum": "$inversiones.monto_total_ahorrado"},
                "rescate_promedio": {"$avg": "$inversiones.porc_rescate"},
                "clientes": {"$addToSet": "$_id"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "producto": "$_id",
                "inversiones": 1,
                "ahorro": 1,
                "rescate_promedio": 1,
                "clientes": {"$size": "$clientes"},
            }
        },
        {"$sort": {"ahorro": DESCENDING}},
    ]
    return list(base[COLECCION_CLIENTES].aggregate(pipeline))


def top_clientes_ahorro(limite: int = 10) -> list[dict]:
    """Clientes con mayor ahorro acumulado (suma de sus inversiones)."""
    base = obtener_base()
    return list(
        base[COLECCION_CLIENTES].aggregate([
            {"$match": {"inversiones.0": {"$exists": True}}},
            {
                "$project": {
                    "_id": 0,
                    "nro_cliente": 1,
                    "nombre_completo": 1,
                    "inversiones": {"$size": "$inversiones"},
                    "ahorro": {"$sum": "$inversiones.monto_total_ahorrado"},
                }
            },
            {"$sort": {"ahorro": DESCENDING}},
            {"$limit": limite},
        ])
    )


def movimientos_recientes(limite: int = 30) -> list[dict]:
    """Ultimos movimientos de inversion de toda la cartera."""
    base = obtener_base()

    pipeline = [
        {"$unwind": "$inversiones"},
        {"$unwind": "$inversiones.movimientos"},
        {
            "$project": {
                "_id": 0,
                "nro_cliente": 1,
                "nombre_completo": 1,
                "producto": "$inversiones.producto.nombre",
                "nro_movimiento": "$inversiones.movimientos.nro_movimiento",
                "fecha": "$inversiones.movimientos.fecha",
                "tipo_movimiento": "$inversiones.movimientos.tipo_movimiento",
                "monto": "$inversiones.movimientos.monto",
                "signo": "$inversiones.movimientos.signo",
            }
        },
        {"$sort": {"fecha": DESCENDING}},
        {"$limit": limite},
    ]
    return list(base[COLECCION_CLIENTES].aggregate(pipeline))


# ==========================================================================
# BITACORA Y PROCESOS
# ==========================================================================

def ultimo_proceso() -> dict | None:
    """Documento mas reciente de procesos_mensuales (el ultimo ETL ejecutado)."""
    base = obtener_base()
    return base[COLECCION_PROCESOS].find_one(sort=[("fecha_corte", DESCENDING)])


def listar_procesos(limite: int = 20) -> list[dict]:
    """Historial de ejecuciones del proceso mensual, mas reciente primero."""
    base = obtener_base()
    return list(
        base[COLECCION_PROCESOS]
        .find({}, {"lineas_salida": 0})
        .sort("fecha_corte", DESCENDING)
        .limit(limite)
    )


def obtener_proceso(proceso_id) -> dict | None:
    """
    Un proceso completo, INCLUYENDO lineas_salida.

    Se pide aparte de proponer el historial: las lineas son 260 strings por
    ejecucion y no tiene sentido traerlas para pintar una tabla de 9 filas.
    """
    base = obtener_base()
    return base[COLECCION_PROCESOS].find_one({"_id": proceso_id})


def contar_procesos() -> int:
    """Cantidad de ejecuciones registradas del proceso mensual."""
    return obtener_base()[COLECCION_PROCESOS].count_documents({})


def listar_bitacora(limite: int = 100, nro_cliente: int | None = None) -> list[dict]:
    """Eventos de auditoria de pagos, opcionalmente de un solo cliente."""
    base = obtener_base()
    filtro = {}
    if nro_cliente is not None:
        filtro["nro_cliente"] = int(nro_cliente)

    return list(
        base[COLECCION_BITACORA]
        .find(filtro)
        .sort("fecha_evento", DESCENDING)
        .limit(limite)
    )


def contar_bitacora() -> int:
    """Total de eventos de auditoria (se usa como KPI y como verificacion del CRUD)."""
    return obtener_base()[COLECCION_BITACORA].count_documents({})


# ==========================================================================
# CATALOGOS
# ==========================================================================

def listar_catalogos(categoria: str | None = None) -> list[dict]:
    """Documentos de catalogo, opcionalmente filtrados por categoria."""
    base = obtener_base()
    filtro = {"categoria": categoria} if categoria else {}
    return list(base[COLECCION_CATALOGOS].find(filtro).sort("nombre", 1))


def categorias_catalogo() -> list[str]:
    """Las 7 categorias presentes en la coleccion catalogos."""
    base = obtener_base()
    return sorted(base[COLECCION_CATALOGOS].distinct("categoria"))


def conteo_catalogos() -> list[dict]:
    """Cantidad de registros por categoria, para el resumen de la vista."""
    base = obtener_base()
    return list(
        base[COLECCION_CATALOGOS].aggregate([
            {"$group": {"_id": "$categoria", "registros": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ])
    )
