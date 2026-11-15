"""
Panel general.

Criterio de diseno: la pantalla responde UNA pregunta de negocio
("como esta la cartera y por donde se me esta escapando plata") en menos de
cinco segundos. Por eso:

  - hay una sola cifra destacada (saldo pendiente), no doce metricas iguales;
  - el resto de los indicadores vive en un expander, disponible pero no
    compitiendo por la atencion;
  - los graficos van de lo que importa (riesgo de cobranza) a lo accesorio
    (comuna).
"""

import streamlit as st

from consultas import (
    cartera_por_tipo_credito,
    por_clasificacion,
    por_comuna,
    resumen_general,
    ultimo_proceso,
)
from formato import clp, fecha_hora, numero, porcentaje
from graficos import (
    barras_comunas,
    barras_estado_cuotas,
    barras_tipo_credito,
    dona_clasificacion,
)
from ui import alerta, header, kpi, mini_fila, seccion


def render():
    datos = resumen_general()
    proceso = ultimo_proceso()

    corte = (
        f"corte del {fecha_hora(proceso['fecha_corte'])}"
        if proceso
        else "sin procesos registrados"
    )
    header("Panel de cartera", f"Cartera consolidada · {corte}")

    # --- Cifras base -----------------------------------------------------
    otorgado = datos.get("total_creditos", 0) or 0
    saldo = datos.get("saldo_pendiente", 0) or 0
    pagado = datos.get("total_pagado", 0) or 0
    ahorro = datos.get("total_ahorrado", 0) or 0
    cuotas_total = datos.get("cuotas_total", 0) or 0
    vencidas = datos.get("cuotas_vencidas", 0) or 0
    con_alertas = datos.get("con_alertas", 0) or 0

    pct_saldo = saldo * 100 / otorgado if otorgado else 0
    pct_pagado = pagado * 100 / otorgado if otorgado else 0
    pct_vencidas = vencidas * 100 / cuotas_total if cuotas_total else 0

    # --- Tres tarjetas: una manda, dos acompanian ------------------------
    col_principal, col_secundaria, col_terciaria = st.columns([1.25, 1, 1])
    with col_principal:
        kpi(
            "Saldo pendiente de cartera",
            clp(saldo),
            f"{porcentaje(pct_saldo, 1)} de lo otorgado sigue sin pagar",
            destacado=True,
            alerta=True,
        )
    with col_secundaria:
        kpi(
            "Cartera otorgada",
            clp(otorgado),
            f"{porcentaje(pct_pagado, 1)} ya recuperado",
        )
    with col_terciaria:
        kpi(
            "Ahorro de los clientes",
            clp(ahorro),
            f"{numero(datos.get('con_inversion', 0))} clientes con inversión",
        )

    # --- Franja de atencion ---------------------------------------------
    st.write("")
    if vencidas:
        alerta(
            f"<b>{numero(vencidas)}</b> cuotas vencidas "
            f"({porcentaje(pct_vencidas, 1)} de la cartera) en "
            f"<b>{numero(con_alertas)}</b> clientes con alertas activas."
        )
    else:
        alerta("Sin cuotas vencidas: la cartera está al día.", ok=True)

    # --- Dos graficos: segmentacion y cobranza ---------------------------
    st.write("")
    col_izq, col_der = st.columns(2)

    with col_izq:
        seccion(
            "Clasificación de clientes",
            "Segmentación que asigna el análisis del ETL a cada cliente.",
        )
        filas = por_clasificacion()
        if filas:
            st.plotly_chart(
                dona_clasificacion(filas), width="stretch",
                config={"displayModeBar": False},
            )
        else:
            st.info("Sin datos de clasificación.")

    with col_der:
        seccion(
            "Estado de las cuotas",
            f"{numero(cuotas_total)} cuotas entre todos los créditos.",
        )
        if cuotas_total:
            st.plotly_chart(
                barras_estado_cuotas(datos),
                width="stretch",
                config={"displayModeBar": False},
            )
        else:
            st.info("Sin cuotas registradas.")

    # --- Detalle bajo demanda -------------------------------------------
    with st.expander("Ver más indicadores", expanded=False):
        mini_fila([
            ("Clientes", numero(datos.get("clientes", 0))),
            ("Con crédito", numero(datos.get("con_credito", 0))),
            ("Con inversión", numero(datos.get("con_inversion", 0))),
            ("Con alertas", numero(con_alertas)),
        ])

        st.write("")
        col_a, col_b = st.columns(2)

        with col_a:
            seccion(
                "Saldo por tipo de crédito",
                "Dónde está concentrada la deuda.",
            )
            tipos = cartera_por_tipo_credito()
            if tipos:
                st.plotly_chart(
                    barras_tipo_credito(tipos), width="stretch",
                    config={"displayModeBar": False},
                )
            else:
                st.info("Sin créditos registrados.")

        with col_b:
            seccion(
                "Saldo por comuna",
                "Top 10 de comunas con deuda pendiente.",
            )
            comunas = por_comuna()
            if comunas:
                st.plotly_chart(
                    barras_comunas(comunas), width="stretch",
                    config={"displayModeBar": False},
                )
            else:
                st.info("Sin datos geográficos.")
