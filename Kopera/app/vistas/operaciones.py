"""
Operaciones (demo): el CRUD de escritura sobre Atlas.

Que demuestra esta pantalla: que la interface no es un visor. Registra un pago
o un movimiento, y el cambio aparece de inmediato en el panel, en cartera y en
la ficha del cliente porque todo lee del mismo documento.

El flujo de cada formulario es el mismo que el de un sistema real:

    elegir  ->  validar (reglas de los triggers)  ->  escribir
            ->  recalcular el analisis  ->  verificar leyendo la base

Los errores de negocio se muestran con el mismo mensaje que daria el trigger en
Oracle, para poder compararlos en la defensa.
"""

import streamlit as st

from consultas import (
    clientes_con_cuotas_abiertas,
    listar_bitacora,
    listar_catalogos,
    obtener_cliente,
    opciones_clientes,
)
from formato import badge_atraso, clp, fecha, fecha_hora, numero, tono_estado_cuota
from operaciones import registrar_movimiento, registrar_pago
from ui import (
    alerta,
    badge,
    esc,
    estado_vacio,
    header,
    mini_fila,
    seccion,
    tabla,
)


# ==========================================================================
# Utilidades de la vista
# ==========================================================================

def _clientes() -> tuple[list[int], dict]:
    """Ids y etiquetas del selector de cliente."""
    opciones = opciones_clientes()
    ids = [o["nro_cliente"] for o in opciones]
    etiquetas = {
        o["nro_cliente"]: f"{o['nombre_completo']} · {o['run']}"
        for o in opciones
    }
    return ids, etiquetas


def _mostrar_resultado(tipo: str):
    """
    Pinta el resultado de la ultima operacion de este formulario.

    Se guarda en session_state porque la operacion termina en st.rerun(): sin
    eso, la confirmacion se perderia en el rerun que refresca los datos.
    """
    resultado = st.session_state.get("op_resultado")
    if not resultado or resultado.get("tipo") != tipo:
        return

    st.write("")
    if resultado["ok"]:
        alerta(f"<b>{esc(resultado['titulo'])}</b>", ok=True)
        mini_fila(resultado.get("detalle") or [])
        st.caption(
            f"{resultado.get('nota', '')} Abrí el Panel general o la ficha del "
            "cliente para ver el cambio reflejado."
        )
    else:
        cuerpo = f"<b>{esc(resultado['titulo'])}</b>"
        for error in resultado.get("errores") or []:
            cuerpo += f"<br>• {esc(error)}"
        alerta(cuerpo)


def _limpiar_widgets(prefijos: tuple[str, ...]):
    """
    Borra el estado de los widgets del formulario antes de rerun.

    Es la forma documentada de reiniciar un widget en Streamlit (asignar el
    valor no siempre se puede) y evita que un selectbox quede apuntando a una
    cuota que acaba de pasar a PAGADA.
    """
    for clave in list(st.session_state.keys()):
        if clave.startswith(prefijos):
            del st.session_state[clave]


# ==========================================================================
# Pestana 1: registrar pago de cuota
# ==========================================================================

def _tab_pago():
    ids, etiquetas = _clientes()
    if not ids:
        estado_vacio("La colección de clientes está vacía.")
        return

    # Arrancar en un cliente con cuotas abiertas: el primero alfabético suele
    # no tener créditos y el formulario quedaría vacío en la demo.
    abiertos = clientes_con_cuotas_abiertas()
    inicial = ids.index(abiertos[0]) if abiertos and abiertos[0] in ids else 0

    nro_cliente = st.selectbox(
        "Cliente", ids,
        index=inicial,
        format_func=lambda i: etiquetas.get(i, str(i)),
        key="op_cliente_pago",
    )

    documento = obtener_cliente(nro_cliente) or {}
    # Solo cuotas abiertas Y con saldo: una cuota con estado abierto pero saldo
    # cero (inconsistencia heredada de la semilla) rompería el number_input,
    # cuyo maximo es el saldo.
    creditos = [
        c for c in (documento.get("creditos") or [])
        if any(
            q.get("estado") != "PAGADA" and (q.get("saldo_por_pagar") or 0) > 0
            for q in (c.get("cuotas") or [])
        )
    ]

    if not creditos:
        estado_vacio("Este cliente no tiene cuotas por pagar.")
        return

    col_credito, col_cuota = st.columns([1, 1.6])

    with col_credito:
        nro_credito = st.selectbox(
            "Crédito",
            [c["nro_solic_credito"] for c in creditos],
            format_func=lambda n: f"{n} · " + next(
                (c["tipo_credito"]["nombre"] for c in creditos
                 if c["nro_solic_credito"] == n), "—"
            ),
            key="op_credito",
        )

    credito = next(c for c in creditos if c["nro_solic_credito"] == nro_credito)
    cuotas = [
        q for q in credito["cuotas"]
        if q.get("estado") != "PAGADA" and (q.get("saldo_por_pagar") or 0) > 0
    ]

    with col_cuota:
        nro_cuota = st.selectbox(
            "Cuota",
            [q["nro_cuota"] for q in cuotas],
            format_func=lambda n: next(
                (f"Cuota {q['nro_cuota']} · vence {fecha(q.get('fecha_vencimiento'))} "
                 f"· saldo {clp(q.get('saldo_por_pagar'))}"
                 for q in cuotas if q["nro_cuota"] == n), str(n)
            ),
            key="op_cuota",
        )

    cuota = next(q for q in cuotas if q["nro_cuota"] == nro_cuota)
    saldo = int(cuota.get("saldo_por_pagar") or 0)

    # --- Estado actual ---------------------------------------------------
    texto_atraso, _ = badge_atraso(
        cuota.get("dias_atraso"), pagada=cuota.get("estado") == "PAGADA"
    )
    st.write("")
    mini_fila([
        ("Valor de la cuota", clp(cuota.get("valor_cuota"))),
        ("Ya pagado", clp(cuota.get("monto_pagado"))),
        ("Saldo", clp(saldo)),
        ("Estado", str(cuota.get("estado"))),
        ("Atraso", texto_atraso),
    ])

    # --- Formulario ------------------------------------------------------
    formas = [c["nombre"] for c in listar_catalogos("FORMA_PAGO")]
    if not formas:
        estado_vacio("No hay formas de pago en el catálogo.")
        return

    st.write("")
    col_monto, col_forma = st.columns([1, 1])
    with col_monto:
        monto = st.number_input(
            "Monto a pagar ahora",
            min_value=1,
            max_value=saldo,
            value=saldo,
            step=1000,
            key=f"op_monto_{nro_credito}_{nro_cuota}",
            help="El saldo se deriva: saldo = valor de la cuota − pagado acumulado.",
        )
    with col_forma:
        forma = st.selectbox("Forma de pago", formas, key="op_forma_pago")

    if st.button("Registrar pago", type="primary", width="stretch"):
        resultado = registrar_pago(nro_cliente, nro_credito, nro_cuota, int(monto), forma)
        resultado["tipo"] = "pago"
        st.session_state["op_resultado"] = resultado
        _limpiar_widgets(("op_credito", "op_cuota", "op_monto"))
        st.rerun()


# ==========================================================================
# Pestana 2: registrar movimiento de inversion
# ==========================================================================

def _disponible_rescate(inversion: dict) -> tuple[int, int]:
    """(rescates acumulados, monto maximo que aun se puede rescatar)."""
    rescates = sum(
        int(m.get("monto") or 0)
        for m in (inversion.get("movimientos") or [])
        if (m.get("tipo_movimiento") or "").upper() == "RESCATE"
    )
    saldo = int(inversion.get("monto_total_ahorrado") or 0)
    maximo = (inversion.get("producto") or {}).get("porc_maximo_rescate") or 0
    # Misma formula que la regla 3: (saldo + rescates) * % / 100.
    limite = (saldo + rescates) * int(maximo) / 100
    return rescates, max(0, int(limite - rescates))


def _tab_movimiento():
    ids, etiquetas = _clientes()
    if not ids:
        estado_vacio("La colección de clientes está vacía.")
        return

    nro_cliente = st.selectbox(
        "Cliente", ids,
        format_func=lambda i: etiquetas.get(i, str(i)),
        key="op_cliente_inv",
    )

    documento = obtener_cliente(nro_cliente) or {}
    inversiones = documento.get("inversiones") or []
    if not inversiones:
        estado_vacio("Este cliente no tiene inversiones registradas.")
        return

    nro_solic_prod = st.selectbox(
        "Inversión",
        [i["nro_solic_prod"] for i in inversiones],
        format_func=lambda n: next(
            (f"{i['producto']['nombre']} · N° {i['nro_solic_prod']} · "
             f"saldo {clp(i.get('monto_total_ahorrado'))}"
             for i in inversiones if i["nro_solic_prod"] == n), str(n)
        ),
        key="op_inversion",
    )

    inversion = next(i for i in inversiones if i["nro_solic_prod"] == nro_solic_prod)
    saldo = int(inversion.get("monto_total_ahorrado") or 0)
    rescates, disponible = _disponible_rescate(inversion)
    producto = inversion.get("producto") or {}

    # --- Estado actual ---------------------------------------------------
    st.write("")
    mini_fila([
        ("Saldo ahorrado", clp(saldo)),
        ("Rescates acumulados", clp(rescates)),
        ("Disponible para rescate", clp(disponible)),
        ("% máximo del producto",
         f"{producto.get('porc_maximo_rescate', 0)}%"),
        ("Movimientos", numero(len(inversion.get("movimientos") or []))),
    ])

    # --- Formulario ------------------------------------------------------
    st.write("")
    col_tipo, col_monto = st.columns([1, 1])
    with col_tipo:
        tipo = st.radio(
            "Tipo de movimiento",
            ["ABONO", "RESCATE"],
            horizontal=True,
            key="op_tipo",
        )

    tope = saldo if tipo == "ABONO" else max(1, min(saldo, disponible))
    sugerido = int(inversion.get("ahorro_minimo_mensual") or 25000) if tipo == "ABONO" else tope

    with col_monto:
        monto = st.number_input(
            "Monto",
            min_value=1,
            max_value=tope,
            value=min(sugerido, tope),
            step=1000,
            key=f"op_monto_inv_{nro_solic_prod}_{tipo}",
            help="Un RESCATE no puede superar el saldo ni el porcentaje del producto.",
        )

    if tipo == "RESCATE" and disponible == 0:
        st.caption(
            "Esta inversión ya usó el 100% del rescate permitido por su "
            "producto: la regla 3 rechazará cualquier rescate."
        )

    if st.button("Registrar movimiento", type="primary", width="stretch"):
        resultado = registrar_movimiento(nro_cliente, nro_solic_prod, tipo, int(monto))
        resultado["tipo"] = "movimiento"
        st.session_state["op_resultado"] = resultado
        _limpiar_widgets(("op_monto_inv",))
        st.rerun()


# ==========================================================================
# Ultimos eventos (para ver el efecto de la escritura)
# ==========================================================================

def _ultimos_eventos():
    eventos = listar_bitacora(10)
    if not eventos:
        estado_vacio("La bitácora de pagos está vacía.")
        return

    _, etiquetas = _clientes()
    filas = []
    for evento in eventos:
        nombre = etiquetas.get(evento.get("nro_cliente"), "—")
        estado = evento.get("estado_cuota") or "—"
        filas.append([
            esc(fecha_hora(evento.get("fecha_evento"))),
            esc(nombre),
            esc(evento.get("nro_solic_credito")),
            esc(evento.get("nro_cuota")),
            esc(clp(evento.get("monto_pagado_anterior"))),
            esc(clp(evento.get("monto_pagado_nuevo"))),
            esc(clp(evento.get("saldo_resultante"))),
            badge(estado, tono_estado_cuota(estado)),
            esc(evento.get("usuario_evento")),
        ])

    tabla(
        ["Fecha", "Cliente", "Crédito", "Cuota", "Antes", "Nuevo", "Saldo",
         "Estado", "Usuario"],
        filas,
        alinear_derecha=[2, 3, 4, 5, 6],
    )


# ==========================================================================
# Entrada
# ==========================================================================

def render():
    header(
        "Operaciones (demo)",
        "Escritura real sobre Atlas: registrar un pago o un movimiento y verlo "
        "reflejado en el resto del sistema.",
    )

    st.caption(
        "⚠️ Estas operaciones modifican la base `kopera` de Atlas. Se validan "
        "con las mismas reglas que replican los triggers de Oracle."
    )

    tab_pago, tab_movimiento = st.tabs([
        "Registrar pago de cuota",
        "Registrar movimiento de inversión",
    ])

    with tab_pago:
        st.write("")
        _tab_pago()
        _mostrar_resultado("pago")

    with tab_movimiento:
        st.write("")
        _tab_movimiento()
        _mostrar_resultado("movimiento")

    st.write("")
    seccion(
        "Últimos eventos de auditoría",
        "La tabla `bitacora_pagos` es la evidencia de cada escritura.",
    )
    _ultimos_eventos()
