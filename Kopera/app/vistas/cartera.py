"""
Cartera y cuotas: la vista transversal de los creditos.

El panel general responde "cuanta plata hay en la calle"; esta pantalla
responde "que cuotas exactamente y desde cuando". Por eso la tabla es el
centro: se filtran las 519 cuotas por estado y por cliente, y cada fila trae
el semaforo de atraso para priorizar la cobranza.

Recordatorio del modelo: en MongoDB no hay tabla de cuotas. Cada credito
embebido en el cliente trae su arreglo `cuotas`, asi que esta vista se arma
aplanando dos niveles con $unwind (ver consultas.cartera_resumen).
"""

import streamlit as st

from consultas import buscar_cuotas, cartera_por_atraso, cartera_resumen
from formato import badge_atraso, clp, fecha, numero, porcentaje, tono_estado_cuota
from graficos import barras_atraso, barras_estado_cuotas
from ui import (
    alerta,
    badge,
    esc,
    estado_vacio,
    header,
    kpi,
    mini_fila,
    seccion,
    tabla,
)

ESTADOS = ["Todas", "VENCIDA", "PARCIAL", "PENDIENTE", "PAGADA"]


def render():
    datos = cartera_resumen()

    header(
        "Cartera y cuotas",
        f"{numero(datos['cuotas_total'])} cuotas repartidas entre todos los "
        f"créditos de la cartera.",
    )

    if not datos["cuotas_total"]:
        estado_vacio("No hay cuotas registradas: la cartera está vacía.")
        return

    # --- Cifras ----------------------------------------------------------
    total = datos["cuotas_total"]
    pagadas = datos["cuotas_pagadas"]
    vencidas = datos["cuotas_vencidas"]
    parciales = datos["cuotas_parciales"]
    pendientes = datos["cuotas_pendientes"]
    por_cobrar = pendientes + parciales + vencidas

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi(
            "Saldo por cobrar",
            clp(datos["saldo_total"]),
            f"{numero(por_cobrar)} cuotas todavía sin cerrar",
            destacado=True,
            alerta=True,
        )
    with col2:
        kpi(
            "Monto vencido",
            clp(datos["monto_vencido"]),
            f"{numero(vencidas)} cuotas vencidas",
            alerta=True,
        )
    with col3:
        kpi(
            "Ya recuperado",
            clp(datos["pagado_total"]),
            f"{numero(pagadas)} de {numero(total)} cuotas pagadas "
            f"({porcentaje(pagadas * 100 / total, 1)})",
        )
    with col4:
        kpi(
            "Atraso máximo",
            f"{numero(datos['atraso_maximo'])} días",
            f"{numero(parciales)} cuotas con pago parcial",
        )

    # --- Franja de atencion ----------------------------------------------
    st.write("")
    if vencidas:
        alerta(
            f"<b>{numero(vencidas)}</b> cuotas vencidas por "
            f"<b>{clp(datos['monto_vencido'])}</b>. La más antigua lleva "
            f"<b>{numero(datos['atraso_maximo'])} días</b> de atraso."
        )
    else:
        alerta("Sin cuotas vencidas en la cartera.", ok=True)

    # --- Graficos --------------------------------------------------------
    st.write("")
    col_izq, col_der = st.columns(2)

    with col_izq:
        seccion(
            "Estado de las cuotas",
            "Pagada · parcial · vencida · pendiente.",
        )
        st.plotly_chart(
            barras_estado_cuotas(datos),
            width="stretch",
            config={"displayModeBar": False},
        )

    with col_der:
        por_atraso = cartera_por_atraso()
        seccion(
            "Cuotas con atraso por tramo",
            f"{numero(datos['cuotas_con_atraso'])} cuotas con al menos un día "
            f"de atraso.",
        )
        if por_atraso:
            st.plotly_chart(
                barras_atraso(por_atraso),
                width="stretch",
                config={"displayModeBar": False},
            )
        else:
            st.info("Ninguna cuota registra atraso.")

    # --- Detalle de cuotas ----------------------------------------------
    st.write("")
    seccion("Detalle de cuotas", "Filtra por estado o busca un cliente.")

    col_estado, col_busqueda = st.columns([1, 2.4])
    with col_estado:
        estado = st.selectbox("Estado", ESTADOS)
    with col_busqueda:
        termino = st.text_input(
            "Buscar cliente",
            placeholder="Nombre, N° de cliente o RUN…",
        )

    filas = buscar_cuotas(
        estado="" if estado == "Todas" else estado,
        termino=termino,
        # Se listan todas: con los filtros de estado y cliente la tabla ya
        # queda acotada, y el orden por atraso deja arriba lo urgente.
        limite=600,
    )

    if not filas:
        estado_vacio("Ninguna cuota coincide con los filtros.")
        return

    # Totales de lo filtrado: sirven para cerrar la pregunta "cuanto suma".
    saldo_filtrado = sum(f.get("saldo_por_pagar") or 0 for f in filas)
    mini_fila([
        ("Cuotas listadas", numero(len(filas))),
        ("Saldo", clp(saldo_filtrado)),
        ("Con atraso", numero(sum(1 for f in filas if (f.get("dias_atraso") or 0) > 0))),
    ])

    filas_tabla = []
    for cuota in filas:
        estado_cuota = cuota.get("estado")
        texto_atraso, tono_atraso = badge_atraso(
            cuota.get("dias_atraso"), pagada=estado_cuota == "PAGADA"
        )
        filas_tabla.append([
            esc(cuota.get("nombre_completo")),
            esc(cuota.get("nro_credito")),
            esc(cuota.get("nro_cuota")),
            esc(fecha(cuota.get("fecha_vencimiento"))),
            esc(clp(cuota.get("valor_cuota"))),
            esc(clp(cuota.get("monto_pagado"))),
            esc(clp(cuota.get("saldo_por_pagar"))),
            badge(estado_cuota or "—", tono_estado_cuota(estado_cuota)),
            badge(texto_atraso, tono_atraso),
        ])

    tabla(
        ["Cliente", "Crédito", "N°", "Vence", "Valor", "Pagado", "Saldo",
         "Estado", "Atraso"],
        filas_tabla,
        alinear_derecha=[2, 3, 4, 5, 6],
    )
    st.caption(
        "Semáforo de atraso: 🟢 al día · 🟡 1–30 días · "
        "🟠 31–60 días · 🔴 más de 60 días."
    )
