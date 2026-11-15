"""
Ficha del cliente.

Es la pantalla donde el modelo documental rinde: un unico findOne({_id}) trae
datos personales, creditos con sus cuotas, inversiones con sus movimientos,
historial de pagos y el analisis precalculado por el ETL. No hay joins ni
$lookup: todo vive en el mismo documento.

Decision de diseno: las cuotas se muestran con un semaforo de atraso
(verde / amarillo / naranja / rojo). Es la retroalimentacion visual que se
necesita para detectar de un vistazo donde esta el problema de cobranza.
"""

import streamlit as st

from consultas import listar_bitacora, obtener_cliente, opciones_clientes
from formato import (
    SEMAFORO_CLASIFICACION,
    badge_atraso,
    badge_movimiento,
    clp,
    fecha,
    fecha_hora,
    numero,
    porcentaje,
    tasa,
    texto,
    tono_estado_cuota,
)
from ui import (
    alerta,
    badge,
    datos_grid,
    esc,
    estado_vacio,
    header,
    kpi,
    mini_fila,
    seccion,
    tabla,
)


# ==========================================================================
# Selector
# ==========================================================================

def _seleccionar_cliente() -> dict | None:
    """Selector de cliente, sincronizado con la tabla de la vista Clientes."""
    opciones = opciones_clientes()
    if not opciones:
        estado_vacio("La colección de clientes está vacía.")
        return None

    ids = [o["nro_cliente"] for o in opciones]
    etiquetas = {
        o["nro_cliente"]: f"{o['nombre_completo']} · {o['run']}" for o in opciones
    }

    actual = st.session_state.get("cliente_id")
    if actual not in ids:
        actual = ids[0]
        st.session_state["cliente_id"] = actual

    # Sincronizacion en un solo sentido.
    #
    # BUG que corrige este bloque: antes se comparaba contra `cliente_id` en
    # CADA rerun. Al elegir otro cliente en el selector, el widget ya tenia el
    # valor nuevo, pero `cliente_id` seguia con el viejo; la condicion se
    # cumplia y se pISABA la eleccion del usuario. Resultado: el selector
    # volvia al cliente anterior y la pagina parecia no reaccionar.
    #
    # Ahora se guarda el ultimo valor APLICADO (`ficha_aplicada`). Solo se
    # empuja al widget cuando `cliente_id` cambio por fuera del selector
    # (por ejemplo, al llegar desde la tabla de Clientes).
    if st.session_state.get("ficha_aplicada") != actual:
        st.session_state["sel_ficha"] = actual
        st.session_state["ficha_aplicada"] = actual

    elegido = st.selectbox(
        "Cliente",
        ids,
        key="sel_ficha",
        format_func=lambda n: etiquetas.get(n, str(n)),
    )
    st.session_state["cliente_id"] = elegido
    st.session_state["ficha_aplicada"] = elegido
    return obtener_cliente(elegido)


# ==========================================================================
# Encabezado y resumen
# ==========================================================================

def _encabezado(cliente: dict):
    ubicacion = cliente.get("ubicacion") or {}
    header(
        cliente.get("nombre_completo", "Cliente"),
        f"RUN {cliente.get('run', '—')} · N° {cliente.get('nro_cliente')} · "
        f"{ubicacion.get('comuna', '—')}, {ubicacion.get('region', '—')}",
    )


def _kpis(cliente: dict):
    analisis = cliente.get("analisis") or {}
    clasif = analisis.get("clasificacion")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi(
            "Saldo pendiente",
            clp(analisis.get("saldo_pendiente")),
            f"{porcentaje(analisis.get('porcentaje_pagado'), 1)} pagado",
            destacado=True,
            alerta=True,
        )
    with col2:
        kpi(
            "Créditos otorgados",
            clp(analisis.get("total_creditos")),
            f"{len(cliente.get('creditos') or [])} crédito(s) · "
            f"{numero((analisis.get('cuotas') or {}).get('total'))} cuotas",
        )
    with col3:
        kpi(
            "Ahorro acumulado",
            clp(analisis.get("total_ahorrado")),
            f"{len(cliente.get('inversiones') or [])} inversión(es)",
        )
    with col4:
        kpi(
            "Clasificación",
            f"{SEMAFORO_CLASIFICACION.get(clasif, '⚪')} {clasif or '—'}",
            analisis.get("motivo_clasificacion", ""),
        )


def _alertas(cliente: dict):
    analisis = cliente.get("analisis") or {}
    alertas = analisis.get("alertas") or []

    st.write("")
    if not alertas:
        alerta("Sin alertas: el cliente no tiene cuotas vencidas ni pagos incompletos.", ok=True)
        return

    visibles = alertas[:6]
    extra = len(alertas) - len(visibles)
    cuerpo = "<br>".join(f"• {esc(a)}" for a in visibles)
    if extra > 0:
        cuerpo += f"<br>• … y {extra} alerta(s) más"
    alerta(cuerpo)


# ==========================================================================
# Pestana 1: creditos y cuotas
# ==========================================================================

def _tabla_cuotas(cuotas: list[dict]):
    """Tabla de cuotas con semaforo de estado y de dias de atraso."""
    filas = []
    for cuota in cuotas:
        estado = cuota.get("estado")
        pagada = estado == "PAGADA"
        texto_atraso, tono_atraso = badge_atraso(
            cuota.get("dias_atraso"), pagada=pagada
        )
        filas.append([
            esc(cuota.get("nro_cuota")),
            esc(fecha(cuota.get("fecha_vencimiento"))),
            esc(clp(cuota.get("valor_cuota"))),
            esc(clp(cuota.get("monto_pagado"))),
            esc(clp(cuota.get("saldo_por_pagar"))),
            badge(estado or "—", tono_estado_cuota(estado)),
            badge(texto_atraso, tono_atraso),
            esc(fecha(cuota.get("fecha_pago"))),
            esc(texto(cuota.get("forma_pago"), "—")),
        ])

    tabla(
        ["N°", "Vencimiento", "Valor", "Pagado", "Saldo", "Estado", "Atraso",
         "Fecha pago", "Forma de pago"],
        filas,
        alinear_derecha=[0, 2, 3, 4],
    )


def _creditos(cliente: dict):
    creditos = cliente.get("creditos") or []
    if not creditos:
        estado_vacio("Este cliente no tiene créditos registrados.")
        return

    st.caption(
        "Semáforo de atraso: 🟢 al día · 🟡 1–30 días · "
        "🟠 31–60 días · 🔴 más de 60 días"
    )

    for credito in creditos:
        tipo = credito.get("tipo_credito") or {}
        cuotas = credito.get("cuotas") or []
        sucursal = credito.get("sucursal") or {}

        seccion(
            f"Crédito {credito.get('nro_solic_credito')} · {tipo.get('nombre', '—')}",
            f"Otorgado el {fecha(credito.get('fecha_otorgamiento'))} · "
            f"{numero(credito.get('total_cuotas'))} cuotas · "
            f"tasa {tasa(tipo.get('tasa_interes_anual'))}",
        )

        datos_grid([
            ("Monto solicitado", clp(credito.get("monto_solicitado"))),
            ("Monto del crédito", clp(credito.get("monto_credito"))),
            ("Sucursal", f"{texto(sucursal.get('direccion'))}, "
                         f"{texto(sucursal.get('comuna'))}"),
            ("Aporte SBIF", f"{texto(credito.get('aporte_sbif'))}%"),
        ])

        st.write("")
        _tabla_cuotas(cuotas)

        pagado = sum(c.get("monto_pagado") or 0 for c in cuotas)
        saldo = sum(c.get("saldo_por_pagar") or 0 for c in cuotas)
        vencidas = sum(1 for c in cuotas if c.get("estado") == "VENCIDA")

        st.write("")
        mini_fila([
            ("Cuotas", numero(len(cuotas))),
            ("Pagado", clp(pagado)),
            ("Saldo", clp(saldo)),
            ("Vencidas", numero(vencidas)),
        ])
        st.divider()


# ==========================================================================
# Pestana 2: inversiones
# ==========================================================================

def _inversiones(cliente: dict):
    inversiones = cliente.get("inversiones") or []
    if not inversiones:
        estado_vacio("Este cliente no tiene inversiones registradas.")
        return

    for inversion in inversiones:
        producto = inversion.get("producto") or {}
        movimientos = inversion.get("movimientos") or []

        seccion(
            f"Inversión {inversion.get('nro_solic_prod')} · "
            f"{producto.get('nombre', '—')}",
            f"Solicitada el {fecha(inversion.get('fecha_solicitud'))} · "
            f"ahorro mínimo {clp(inversion.get('ahorro_minimo_mensual'))} "
            f"los días {numero(inversion.get('dia_pago_mensual'))}",
        )

        datos_grid([
            ("Saldo ahorrado", clp(inversion.get("monto_total_ahorrado"))),
            ("Ahorro mínimo mensual", clp(inversion.get("ahorro_minimo_mensual"))),
            ("% de rescate usado", porcentaje(inversion.get("porc_rescate"))),
            ("Máximo de rescate del producto",
             porcentaje(producto.get("porc_maximo_rescate"))),
            ("Meses mínimos de ahorro",
             numero(producto.get("meses_minimo_ahorro"))),
        ])

        st.write("")
        if movimientos:
            filas = []
            for mov in movimientos:
                tipo_mov, tono = badge_movimiento(mov.get("tipo_movimiento"))
                signo = mov.get("signo", 1)
                monto = f"{'+' if signo > 0 else '−'}{clp(mov.get('monto'))}"
                filas.append([
                    esc(mov.get("nro_movimiento")),
                    esc(fecha(mov.get("fecha"))),
                    badge(tipo_mov, tono),
                    esc(monto),
                ])
            tabla(
                ["N°", "Fecha", "Tipo", "Monto"],
                filas,
                alinear_derecha=[0, 3],
            )
        else:
            st.caption("Sin movimientos registrados en esta inversión.")

        st.divider()


# ==========================================================================
# Pestana 3: historial de pagos
# ==========================================================================

def _historial(cliente: dict):
    pagos = cliente.get("historial_pagos") or []

    seccion(
        "Historial de pagos del cliente",
        "Eventos embebidos en el documento (historial_pagos).",
    )

    if pagos:
        filas = []
        for pago in pagos:
            filas.append([
                esc(fecha_hora(pago.get("fecha_evento"))),
                esc(pago.get("nro_solic_credito")),
                esc(pago.get("nro_cuota")),
                esc(clp(pago.get("monto_pagado_anterior"))),
                esc(clp(pago.get("monto_pagado_nuevo"))),
                esc(clp(pago.get("saldo_resultante"))),
                esc(texto(pago.get("forma_pago"), "—")),
                badge(pago.get("estado_cuota") or "—",
                      tono_estado_cuota(pago.get("estado_cuota"))),
            ])
        tabla(
            ["Fecha", "Crédito", "Cuota", "Pagado antes", "Pagado nuevo",
             "Saldo resultante", "Forma de pago", "Estado"],
            filas,
            alinear_derecha=[1, 2, 3, 4, 5],
        )
    else:
        estado_vacio("El cliente no tiene pagos registrados.")

    # La coleccion de auditoria existe aparte: se muestra para contrastar.
    with st.expander("Auditoría · colección bitacora_pagos"):
        eventos = listar_bitacora(nro_cliente=cliente.get("nro_cliente"))
        if not eventos:
            st.caption("Sin eventos de auditoría para este cliente.")
            return

        filas = []
        for evento in eventos:
            filas.append([
                esc(fecha_hora(evento.get("fecha_evento"))),
                esc(evento.get("nro_solic_credito")),
                esc(evento.get("nro_cuota")),
                esc(clp(evento.get("monto_pagado_anterior"))),
                esc(clp(evento.get("monto_pagado_nuevo"))),
                esc(clp(evento.get("saldo_resultante"))),
                esc(texto(evento.get("forma_pago"), "—")),
                esc(texto(evento.get("usuario_evento"), "—")),
            ])
        tabla(
            ["Fecha", "Crédito", "Cuota", "Antes", "Nuevo", "Saldo",
             "Forma de pago", "Usuario"],
            filas,
            alinear_derecha=[1, 2, 3, 4, 5],
        )
        st.caption(f"{len(eventos)} evento(s) de auditoría registrados.")


# ==========================================================================
# Pestana 4: datos del cliente
# ==========================================================================

def _datos(cliente: dict):
    nombre = cliente.get("nombre") or {}
    contacto = cliente.get("contacto") or {}
    ubicacion = cliente.get("ubicacion") or {}
    contrato = cliente.get("tipo_contrato") or {}
    metadata = cliente.get("metadata") or {}

    col_izq, col_der = st.columns(2)

    with col_izq:
        seccion("Datos personales")
        datos_grid([
            ("RUN", texto(cliente.get("run"))),
            ("Nombres", texto(" ".join(
                filter(None, [nombre.get("pnombre"), nombre.get("snombre")])
            ))),
            ("Apellidos", texto(" ".join(
                filter(None, [nombre.get("appaterno"), nombre.get("apmaterno")])
            ))),
            ("Fecha de nacimiento", fecha(cliente.get("fecha_nacimiento"))),
            ("Fecha de inscripción", fecha(cliente.get("fecha_inscripcion"))),
            ("Profesión u oficio", texto(cliente.get("profesion"))),
            ("Tipo de contrato", texto(contrato.get("nombre"))),
            ("Promedio de renta", texto(contrato.get("promedio_renta"))),
        ])

    with col_der:
        seccion("Contacto y ubicación")
        datos_grid([
            ("Correo", texto(contacto.get("correo"))),
            ("Teléfono", texto(contacto.get("fono_contacto"))),
            ("Dirección", texto(contacto.get("direccion"))),
            ("Comuna", texto(ubicacion.get("comuna"))),
            ("Provincia", texto(ubicacion.get("provincia"))),
            ("Región", texto(ubicacion.get("region"))),
        ])

    st.write("")
    st.caption(
        f"Origen: {texto(metadata.get('origen'), '—')} · "
        f"corte {fecha_hora(metadata.get('fecha_corte'))} · "
        f"migrado {fecha_hora(metadata.get('migrado_en'))}"
    )


# ==========================================================================
# Entrada
# ==========================================================================

def render():
    cliente = _seleccionar_cliente()
    if not cliente:
        return

    _encabezado(cliente)
    _kpis(cliente)
    _alertas(cliente)

    creditos = cliente.get("creditos") or []
    inversiones = cliente.get("inversiones") or []
    pagos = cliente.get("historial_pagos") or []

    tab1, tab2, tab3, tab4 = st.tabs([
        f"Créditos y cuotas ({len(creditos)})",
        f"Inversiones ({len(inversiones)})",
        f"Historial de pagos ({len(pagos)})",
        "Datos del cliente",
    ])

    with tab1:
        st.write("")
        _creditos(cliente)

    with tab2:
        st.write("")
        _inversiones(cliente)

    with tab3:
        st.write("")
        _historial(cliente)

    with tab4:
        st.write("")
        _datos(cliente)
