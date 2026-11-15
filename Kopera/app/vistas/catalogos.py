"""
Catalogos: los 7 maestros migrados desde Oracle.

Decision de modelado que conviene explicar en la demo: las 7 tablas de
catalogo del esquema relacional se migraron a UNA sola coleccion, con el campo
`categoria` como discriminador. En SQL eran siete tablas de dos o tres
columnas; en MongoDB serian siete colecciones casi vacias, y cada una obligaria
a un round-trip distinto. Con discriminador hay un solo indice por categoria.

Como cada categoria tiene campos propios (tasa y cuotas en CREDITO, meses y
rescate en INVERSION), la tabla de detalle cambia sus columnas segun lo
elegido.
"""

import streamlit as st

from consultas import categorias_catalogo, conteo_catalogos, listar_catalogos
from formato import clp, numero, porcentaje, tasa
from ui import esc, estado_vacio, header, kpi, seccion, tabla


def _recortar(valor, largo: int = 120) -> str:
    """Acorta un texto largo para que no desarme la tabla."""
    texto = str(valor or "").strip()
    return texto if len(texto) <= largo else texto[:largo].rstrip() + "…"


def _detalle(categoria: str, docs: list[dict]) -> tuple[list[str], list[list[str]], list[int]]:
    """
    Devuelve (encabezados, filas, columnas a alinear a la derecha) segun la
    categoria. Cada catalogo muestra solo sus campos reales: no se rellena con
    guiones lo que no aplica.
    """
    if categoria == "CREDITO":
        encabezados = ["ID", "Código", "Nombre", "Tasa anual", "Máx. cuotas",
                       "Descripción"]
        filas = [[
            esc(d.get("_id")),
            esc(d.get("codigo")),
            esc(d.get("nombre")),
            esc(tasa(d.get("tasa_interes_anual"))),
            esc(numero(d.get("nro_maximo_cuotas"))),
            esc(_recortar(d.get("descripcion"))),
        ] for d in docs]
        return encabezados, filas, [1, 3, 4]

    if categoria == "INVERSION":
        encabezados = ["ID", "Código", "Nombre", "Meses mínimos de ahorro",
                       "% máx. de rescate"]
        filas = [[
            esc(d.get("_id")),
            esc(d.get("codigo")),
            esc(d.get("nombre")),
            esc(numero(d.get("meses_minimo_ahorro"))),
            esc(porcentaje(d.get("porc_maximo_rescate"))),
        ] for d in docs]
        return encabezados, filas, [1, 3, 4]

    if categoria == "APORTE_SBIF":
        encabezados = ["ID", "Nombre", "Crédito desde", "Crédito hasta",
                       "% entregado al SBIF"]
        filas = [[
            esc(d.get("_id")),
            esc(d.get("nombre")),
            esc(clp(d.get("monto_credito_desde"))),
            esc(clp(d.get("monto_credito_hasta"))),
            esc(porcentaje(d.get("porc_entrega_sbif"))),
        ] for d in docs]
        return encabezados, filas, [2, 3, 4]

    if categoria == "TIPO_CONTRATO":
        encabezados = ["ID", "Código", "Nombre", "Promedio de renta"]
        filas = [[
            esc(d.get("_id")),
            esc(d.get("codigo")),
            esc(d.get("nombre")),
            esc(d.get("promedio_renta")),
        ] for d in docs]
        return encabezados, filas, [1]

    # FORMA_PAGO, PROFESION y TIPO_MOVIMIENTO: codigo + nombre, nada mas.
    encabezados = ["ID", "Código", "Nombre"]
    filas = [[
        esc(d.get("_id")),
        esc(d.get("codigo")),
        esc(d.get("nombre")),
    ] for d in docs]
    return encabezados, filas, [1]


def render():
    categorias = categorias_catalogo()
    conteos = conteo_catalogos()
    total = sum(c.get("registros", 0) for c in conteos)

    header(
        "Catálogos",
        f"{len(categorias)} catálogos maestros migrados desde Oracle, en una "
        f"sola colección discriminada por categoría.",
    )

    if not categorias:
        estado_vacio("La colección de catálogos está vacía.")
        return

    # --- Cifras ----------------------------------------------------------
    col1, col2, col3 = st.columns(3)
    with col1:
        kpi("Categorías", numero(len(categorias)), "tablas maestras migradas",
            destacado=True)
    with col2:
        kpi("Registros", numero(total), "documentos en `catalogos`")
    with col3:
        mayor = max(conteos, key=lambda c: c.get("registros", 0))
        kpi(
            "Categoría más grande",
            esc(mayor.get("_id")),
            f"{numero(mayor.get('registros'))} registros",
        )

    # --- Reparto ---------------------------------------------------------
    st.write("")
    seccion(
        "Composición de la colección",
        "Cada categoría vive en la misma colección, separada por el campo "
        "`categoria`.",
    )
    tabla(
        ["Categoría", "Registros"],
        [[esc(c.get("_id")), esc(numero(c.get("registros")))] for c in conteos],
        alinear_derecha=[1],
    )

    # --- Detalle ---------------------------------------------------------
    st.write("")
    seccion("Detalle del catálogo", "Elige una categoría para ver sus campos.")

    categoria = st.selectbox("Categoría", categorias)
    docs = listar_catalogos(categoria)

    if not docs:
        estado_vacio("La categoría seleccionada no tiene registros.")
        return

    encabezados, filas, derecha = _detalle(categoria, docs)
    tabla(encabezados, filas, alinear_derecha=derecha)

    st.caption(
        f"{numero(len(docs))} registros en `{categoria}`. "
        "Los catálogos no se editan desde la app: se cargan por el ETL."
    )
