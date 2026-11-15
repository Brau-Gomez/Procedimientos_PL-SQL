"""
Procesos del ETL: historial de ejecuciones y la salida del procedimiento.

El proceso mensual (pk_analisis_kopera.sp_proceso_mensual) recorre la cartera en
Oracle, recalcula el bloque `analisis` de cada cliente y deja un documento en
`procesos_mensuales` con el resumen y las 260 lineas que el procedimiento
imprimia por DBMS_OUTPUT.

Guardar la salida como un arreglo de strings permite mostrarla tal cual, sin
reinterpretarla: sirve como evidencia de que el proceso corrio y para
comparar dos ejecuciones.
"""

import streamlit as st

from consultas import contar_procesos, listar_procesos, obtener_proceso
from formato import clp, fecha_hora, numero, texto
from ui import esc, estado_vacio, header, kpi, mini_fila, seccion, tabla

# Cuantas lineas se muestran de una vez: 260 lineas en pantalla tapan todo lo
# demas y no aportan mas que las primeras.
LINEAS_VISIBLES = 80


def _tabla_historial(procesos: list[dict]):
    """Historial de ejecuciones, mas reciente primero."""
    filas = []
    for proceso in procesos:
        filas.append([
            esc(fecha_hora(proceso.get("fecha_corte"))),
            esc(texto(proceso.get("procedimiento"), "—")),
            esc(numero(proceso.get("clientes_analizados"))),
            esc(clp(proceso.get("saldo_total_cartera"))),
            esc(texto(proceso.get("origen"), "—")),
        ])
    tabla(
        ["Fecha de corte", "Procedimiento", "Clientes", "Saldo de cartera",
         "Origen"],
        filas,
        alinear_derecha=[2, 3],
    )


def render():
    procesos = listar_procesos()
    total = contar_procesos()

    header(
        "Procesos del ETL",
        "Ejecuciones del proceso mensual y la salida que dejó cada una.",
    )

    if not procesos:
        estado_vacio(
            "Todavía no hay ejecuciones registradas en `procesos_mensuales`."
        )
        return

    ultimo = procesos[0]

    # --- Cifras ----------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi(
            "Ejecuciones",
            numero(total),
            "registradas en `procesos_mensuales`",
            destacado=True,
        )
    with col2:
        kpi(
            "Último corte",
            fecha_hora(ultimo.get("fecha_corte")),
            texto(ultimo.get("origen"), "—"),
        )
    with col3:
        kpi(
            "Clientes analizados",
            numero(ultimo.get("clientes_analizados")),
            "en la última ejecución",
        )
    with col4:
        kpi(
            "Saldo al corte",
            clp(ultimo.get("saldo_total_cartera")),
            "cartera consolidada por el proceso",
        )

    # --- Historial -------------------------------------------------------
    st.write("")
    seccion(
        "Historial de ejecuciones",
        f"{numero(len(procesos))} ejecuciones más recientes. El saldo se "
        f"mantiene porque el proceso es idempotente: recalcula el análisis, no "
        f"lo acumula.",
    )
    _tabla_historial(procesos)

    # --- Salida del procedimiento ---------------------------------------
    st.write("")
    seccion(
        "Salida del procedimiento",
        "Texto que el procedimiento escribía con DBMS_OUTPUT y que el ETL "
        "guardó en `lineas_salida`.",
    )

    ids = [p.get("_id") for p in procesos]
    etiquetas = {p.get("_id"): fecha_hora(p.get("fecha_corte")) for p in procesos}

    col_proceso, col_busqueda = st.columns([1.4, 1.6])
    with col_proceso:
        elegido = st.selectbox(
            "Ejecución",
            ids,
            format_func=lambda i: etiquetas.get(i, str(i)),
        )
    with col_busqueda:
        filtro = st.text_input(
            "Filtrar líneas",
            placeholder="Por ejemplo: RIESGO, cliente, saldo…",
        )

    proceso = obtener_proceso(elegido) or {}
    lineas = proceso.get("lineas_salida") or []

    if not lineas:
        st.caption("Esta ejecución no guardó salida del procedimiento.")
        return

    if filtro.strip():
        patron = filtro.strip().lower()
        lineas_filtradas = [ln for ln in lineas if patron in ln.lower()]
    else:
        lineas_filtradas = lineas

    mini_fila([
        ("Líneas totales", numero(len(lineas))),
        ("Que coinciden", numero(len(lineas_filtradas))),
        ("Mostrando", numero(min(len(lineas_filtradas), LINEAS_VISIBLES))),
    ])

    if not lineas_filtradas:
        st.caption("Ninguna línea contiene ese texto.")
        return

    st.code("\n".join(lineas_filtradas[:LINEAS_VISIBLES]), language="text")

    if len(lineas_filtradas) > LINEAS_VISIBLES:
        st.caption(
            f"Se muestran las primeras {LINEAS_VISIBLES} líneas de "
            f"{numero(len(lineas_filtradas))}. Afina el filtro o descarga el "
            "archivo completo."
        )

    st.download_button(
        "Descargar salida completa",
        data="\n".join(lineas),
        file_name=f"proceso_{elegido}.txt".replace(":", "-"),
        mime="text/plain",
    )
