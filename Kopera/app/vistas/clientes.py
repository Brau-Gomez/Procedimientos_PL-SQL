"""
Clientes: buscador sobre la ficha financiera.

La tabla usa st.dataframe con seleccion de fila (on_select="rerun") porque
aprovecha el ordenamiento y el scroll nativos. Para que el estado se lea de
un vistazo, las columnas de clasificacion y de cuotas vencidas llevan emoji de
semaforo: en una tabla no se puede pintar la celda, pero el color del emoji
cumple la misma funcion.
"""

import pandas as pd
import streamlit as st

from consultas import buscar_clientes, opciones_clasificacion
from formato import SEMAFORO_CLASIFICACION, clp, numero, porcentaje
from ui import estado_vacio, header, seccion


def _emoji_clasificacion(valor) -> str:
    """Clasificacion con semaforo para la tabla: RIESGO -> 🔴 RIESGO."""
    return f"{SEMAFORO_CLASIFICACION.get(valor, '⚪')} {valor or '—'}"


def _emoji_vencidas(cantidad) -> str:
    """Cuotas vencidas con semaforo: 0 en verde, >0 en rojo."""
    n = int(cantidad or 0)
    return f"{'🔴' if n else '🟢'} {n}"


def _abrir_ficha(nro_cliente: int):
    """
    Callback del boton "Abrir ficha completa".

    Se usa on_click y NO un `if st.button(...)` con asignaciones adentro:
    el callback se ejecuta ANTES de que Streamlit instancie los widgets del
    siguiente rerun. `nav` es la clave del st.radio de la barra lateral; si se
    modifica despues de que el radio ya se dibujo, Streamlit lanza
    StreamlitWidgetAlreadyInstantiatedError.
    """
    st.session_state["cliente_id"] = nro_cliente
    st.session_state["nav"] = "Ficha del cliente"


def _a_dataframe(filas: list[dict]) -> pd.DataFrame:
    """Arma la tabla visible con los campos de resumen."""
    registros = []
    for f in filas:
        analisis = f.get("analisis") or {}
        registros.append({
            "N°": f.get("nro_cliente"),
            "RUN": f.get("run"),
            "Nombre": f.get("nombre_completo"),
            "Comuna": (f.get("ubicacion") or {}).get("comuna", "—"),
            "Clasificación": _emoji_clasificacion(analisis.get("clasificacion")),
            "Saldo pendiente": clp(analisis.get("saldo_pendiente")),
            "% pagado": porcentaje(analisis.get("porcentaje_pagado"), 1),
            "Cuotas vencidas": _emoji_vencidas((analisis.get("cuotas") or {}).get("vencidas")),
        })
    return pd.DataFrame(registros)


def render():
    header("Clientes", "Buscador sobre la ficha financiera migrada a MongoDB.")

    # --- Filtros ---------------------------------------------------------
    col_busqueda, col_clasif, col_credito, col_inversion = st.columns([2.3, 1.4, 1, 1])

    with col_busqueda:
        termino = st.text_input(
            "Buscar",
            placeholder="N° de cliente, RUN o parte del nombre…",
        )
    with col_clasif:
        clasif = st.selectbox(
            "Clasificación",
            ["Todas"] + opciones_clasificacion(),
        )
    with col_credito:
        st.write("")
        solo_credito = st.toggle("Solo con crédito")
    with col_inversion:
        st.write("")
        solo_inversion = st.toggle("Solo con inversión")

    filas = buscar_clientes(
        termino=termino,
        clasificacion="" if clasif == "Todas" else clasif,
        solo_credito=solo_credito,
        solo_inversion=solo_inversion,
    )

    # --- Resultado -------------------------------------------------------
    seccion(
        f"{numero(len(filas))} clientes",
        "Ordenados por saldo pendiente. Selecciona una fila para abrir la ficha.",
    )

    if not filas:
        estado_vacio("Ningún cliente coincide con los filtros.")
        return

    evento = st.dataframe(
        _a_dataframe(filas),
        hide_index=True,
        width="stretch",
        height=min(620, 44 + 35 * len(filas)),
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "N°": st.column_config.NumberColumn(width="small"),
            "RUN": st.column_config.TextColumn(width="small"),
            "Nombre": st.column_config.TextColumn(width="medium"),
            "Comuna": st.column_config.TextColumn(width="small"),
            "Clasificación": st.column_config.TextColumn(width="small"),
            "Saldo pendiente": st.column_config.TextColumn(width="small"),
            "% pagado": st.column_config.TextColumn(width="small"),
            "Cuotas vencidas": st.column_config.TextColumn(width="small"),
        },
    )

    # --- Accion sobre la fila seleccionada --------------------------------
    if evento.selection.rows:
        indice = evento.selection.rows[0]
        if indice < len(filas):
            cliente = filas[indice]
            st.write("")
            col_texto, col_accion = st.columns([3, 1])
            analisis = cliente.get("analisis") or {}

            with col_texto:
                st.markdown(
                    f"**{cliente['nombre_completo']}** · RUN {cliente['run']} · "
                    f"N° {cliente['nro_cliente']} · "
                    f"{_emoji_clasificacion(analisis.get('clasificacion'))}"
                )
                st.caption(
                    f"Saldo pendiente {clp(analisis.get('saldo_pendiente'))} · "
                    f"pagado {porcentaje(analisis.get('porcentaje_pagado'), 1)} · "
                    f"ahorro {clp(analisis.get('total_ahorrado'))}"
                )

            with col_accion:
                st.button(
                    "Abrir ficha completa",
                    type="primary",
                    width="stretch",
                    on_click=_abrir_ficha,
                    args=(cliente["nro_cliente"],),
                )
