"""
Inversiones: cuanto ahorro administra la cooperativa y en que productos.

La jerarquia es deliberada: primero el ahorro total (la cifra que se pide en
una reunion), despues el reparto por producto, y el movimiento diario queda en
un expander porque es detalle operativo, no indicador.
"""

import streamlit as st

from consultas import (
    inversiones_por_producto,
    inversiones_resumen,
    movimientos_recientes,
    top_clientes_ahorro,
)
from formato import badge_movimiento, clp, fecha, numero, porcentaje
from graficos import barras_horizontales
from ui import (
    badge,
    esc,
    estado_vacio,
    header,
    kpi,
    mini_fila,
    seccion,
    tabla,
)


def _tabla_productos(filas: list[dict]):
    """Reparto del ahorro por producto, con el rescate promedio permitido."""
    cuerpo = []
    for f in filas:
        cuerpo.append([
            esc(f.get("producto")),
            esc(numero(f.get("clientes"))),
            esc(numero(f.get("inversiones"))),
            esc(clp(f.get("ahorro"))),
            esc(porcentaje(f.get("rescate_promedio"))),
        ])
    tabla(
        ["Producto", "Clientes", "Inversiones", "Ahorro", "% rescate prom."],
        cuerpo,
        alinear_derecha=[1, 2, 3, 4],
    )


def _tabla_top_clientes(filas: list[dict]):
    """Los clientes que concentran el ahorro de la cooperativa."""
    cuerpo = []
    for f in filas:
        cuerpo.append([
            esc(f.get("nombre_completo")),
            esc(f.get("nro_cliente")),
            esc(numero(f.get("inversiones"))),
            esc(clp(f.get("ahorro"))),
        ])
    tabla(
        ["Cliente", "N°", "Inversiones", "Ahorro"],
        cuerpo,
        alinear_derecha=[1, 2, 3],
    )


def _tabla_movimientos(filas: list[dict]):
    """Ultimos movimientos con signo visible y semaforo por tipo."""
    cuerpo = []
    for mov in filas:
        tipo, tono = badge_movimiento(mov.get("tipo_movimiento"))
        signo = mov.get("signo", 1)
        monto = f"{'+' if signo > 0 else '−'}{clp(mov.get('monto'))}"
        cuerpo.append([
            esc(fecha(mov.get("fecha"))),
            esc(mov.get("nombre_completo")),
            esc(mov.get("producto")),
            badge(tipo, tono),
            esc(monto),
        ])
    tabla(
        ["Fecha", "Cliente", "Producto", "Tipo", "Monto"],
        cuerpo,
        alinear_derecha=[0, 4],
    )


def render():
    resumen = inversiones_resumen()

    header(
        "Inversiones",
        "Productos de ahorro: saldo administrado, reparto por producto y "
        "movimientos.",
    )

    if not resumen.get("inversiones"):
        estado_vacio("No hay inversiones registradas.")
        return

    # --- Cifras ----------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi(
            "Ahorro administrado",
            clp(resumen.get("ahorro")),
            "Suma de todas las inversiones vigentes",
            destacado=True,
        )
    with col2:
        kpi(
            "Inversiones",
            numero(resumen.get("inversiones")),
            f"en {numero(resumen.get('clientes'))} clientes",
        )
    with col3:
        kpi(
            "Movimientos",
            numero(resumen.get("movimientos")),
            "abonos y rescates registrados",
        )
    with col4:
        # Ahorro promedio por inversion: derivado de las dos cifras de arriba.
        prom = (resumen.get("ahorro") or 0) / (resumen.get("inversiones") or 1)
        kpi(
            "Ahorro promedio",
            clp(prom),
            "por inversión",
        )

    # --- Reparto por producto -------------------------------------------
    st.write("")
    productos = inversiones_por_producto()

    col_grafico, col_tabla = st.columns([1.1, 1])
    with col_grafico:
        seccion(
            "Ahorro por producto",
            "El producto con más saldo se resalta en naranja.",
        )
        if productos:
            etiquetas = [p.get("producto") or "Sin producto" for p in productos]
            valores = [p.get("ahorro") or 0 for p in productos]
            st.plotly_chart(
                barras_horizontales(etiquetas, valores),
                width="stretch",
                config={"displayModeBar": False},
            )

    with col_tabla:
        seccion(
            "Detalle por producto",
            "Clientes distintos, cantidad de inversiones y rescate promedio "
            "usado.",
        )
        _tabla_productos(productos)

    # --- Detalle operativo, bajo demanda --------------------------------
    st.write("")
    with st.expander("Clientes con mayor ahorro acumulado", expanded=False):
        _tabla_top_clientes(top_clientes_ahorro(10))

    with st.expander("Últimos movimientos de inversión", expanded=False):
        movimientos = movimientos_recientes(30)
        if movimientos:
            _tabla_movimientos(movimientos)
            mini_fila([
                ("Movimientos mostrados", numero(len(movimientos))),
                ("Total registrados", numero(resumen.get("movimientos"))),
            ])
        else:
            st.caption("Sin movimientos registrados.")
