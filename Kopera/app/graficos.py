"""
Graficos Plotly reutilizables.

Se centralizan aca para que todas las vistas compartan la misma estetica
(fondo transparente, sin grillas duras, tipografia del tema) y para que los
colores de clasificacion y de estado de cuota sean los mismos en toda la app.
"""

import plotly.graph_objects as go

from ui import (
    AZUL,
    AZUL_MEDIO,
    AZUL_SUAVE,
    GRIS,
    GRIS_CLARO,
    NARANJA,
    PALETA_ATRASO,
    PALETA_CLASIFICACION,
    PALETA_CUOTA,
)

# Orden fijo de los estados de cuota: de lo cerrado a lo abierto.
ORDEN_CUOTAS = ["PAGADA", "PARCIAL", "VENCIDA", "PENDIENTE"]
# El resumen del panel trae los conteos planos (cuotas_pagadas, ...).
CLAVE_CUOTAS = {
    "PAGADA": "cuotas_pagadas",
    "PARCIAL": "cuotas_parciales",
    "VENCIDA": "cuotas_vencidas",
    "PENDIENTE": "cuotas_pendientes",
}


def _layout(fig, altura=300, leyenda="v"):
    """Aplica el estilo comun a todas las figuras."""
    fig.update_layout(
        height=altura,
        margin=dict(l=8, r=8, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=13, color=GRIS),
        showlegend=leyenda is not None,
        legend=dict(
            orientation=leyenda,
            x=1 if leyenda == "v" else 0,
            y=0.5 if leyenda == "v" else -0.18,
            xanchor="right" if leyenda == "v" else "left",
            font=dict(size=13, color=AZUL),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#E3EAF3")
    fig.update_yaxes(showgrid=False, zeroline=False, linecolor="#E3EAF3")
    return fig


def _miles(valor) -> str:
    """Separador de miles chileno para etiquetas de grafico."""
    try:
        return f"{int(round(float(valor))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


# --------------------------------------------------------------------------
# Clasificacion de clientes (dona)
# --------------------------------------------------------------------------

def dona_clasificacion(filas: list[dict], altura: int = 360) -> go.Figure:
    """
    Dona con la cantidad de clientes por clasificacion.

    Se deja un hueco central con el total: es el dato que el usuario busca
    primero y evita tener que sumar las porciones.
    """
    etiquetas = [f.get("_id") or "Sin clasificar" for f in filas]
    valores = [f.get("clientes", 0) for f in filas]
    colores = [PALETA_CLASIFICACION.get(e, GRIS_CLARO) for e in etiquetas]
    total = sum(valores)

    fig = go.Figure(
        go.Pie(
            labels=etiquetas,
            values=valores,
            hole=0.62,
            marker=dict(colors=colores, line=dict(color="#FFFFFF", width=2)),
            textinfo="percent",
            textfont=dict(size=12.5, color="#FFFFFF"),
            hovertemplate="%{label}: %{value} clientes<extra></extra>",
            sort=False,
        )
    )
    # Texto del centro
    fig.add_annotation(
        text=f"<b>{_miles(total)}</b><br><span style='font-size:10px'>clientes</span>",
        showarrow=False,
        font=dict(size=15, color=AZUL),
    )
    return _layout(fig, altura=altura, leyenda="v")


# --------------------------------------------------------------------------
# Estado de las cuotas (barras verticales)
# --------------------------------------------------------------------------

def barras_estado_cuotas(cuotas: dict, altura: int = 360) -> go.Figure:
    """Cantidad de cuotas por estado, con el color de semaforo de cada uno."""
    valores = [cuotas.get(CLAVE_CUOTAS[e], 0) or 0 for e in ORDEN_CUOTAS]

    fig = go.Figure(
        go.Bar(
            x=ORDEN_CUOTAS,
            y=valores,
            marker_color=[PALETA_CUOTA[e] for e in ORDEN_CUOTAS],
            text=[_miles(v) for v in valores],
            textposition="outside",
            textfont=dict(size=13.5, color=AZUL),
            cliponaxis=False,
            hovertemplate="%{x}: %{y} cuotas<extra></extra>",
        )
    )
    fig.update_yaxes(showticklabels=False, showgrid=False)
    fig.update_xaxes(tickfont=dict(size=12.5, color=AZUL))
    return _layout(fig, altura=altura, leyenda=None)


# --------------------------------------------------------------------------
# Barras horizontales (tipo de credito y comunas)
# --------------------------------------------------------------------------

def barras_horizontales(etiquetas, valores, altura=360, color=AZUL_MEDIO,
                        resaltar_maximo=True) -> go.Figure:
    """
    Barras horizontales ordenadas de mayor a menor.

    Horizontales porque las etiquetas son largas ("Crédito Hipotecario") y en
    vertical se rotarian o se cortarian. La barra mayor se pinta en naranja:
    es el hallazgo que el usuario deberia ver primero.
    """
    # Orden ascendente para que la barra mayor quede arriba en Plotly
    pares = sorted(zip(etiquetas, valores), key=lambda p: p[1])
    etiquetas = [p[0] for p in pares]
    valores = [p[1] for p in pares]

    colores = [color] * len(valores)
    if resaltar_maximo and colores:
        colores[-1] = NARANJA

    fig = go.Figure(
        go.Bar(
            x=valores,
            y=etiquetas,
            orientation="h",
            marker_color=colores,
            hovertemplate="%{y}: %{x:,.0f}<extra></extra>",
        )
    )
    fig.update_xaxes(showticklabels=False, showgrid=False)
    fig.update_yaxes(tickfont=dict(size=12.5, color=AZUL))
    return _layout(fig, altura=max(altura, 60 + 26 * len(etiquetas)), leyenda=None)


def barras_tipo_credito(filas: list[dict], altura=320) -> go.Figure:
    """Saldo pendiente por tipo de credito."""
    etiquetas = [f.get("_id") or "Sin tipo" for f in filas]
    valores = [f.get("saldo", 0) or 0 for f in filas]
    return barras_horizontales(etiquetas, valores, altura=altura, color=AZUL_SUAVE)


def barras_comunas(filas: list[dict], altura=340) -> go.Figure:
    """Saldo pendiente por comuna (top N)."""
    etiquetas = [f.get("_id") or "Sin comuna" for f in filas]
    valores = [f.get("saldo", 0) or 0 for f in filas]
    return barras_horizontales(etiquetas, valores, altura=altura, color=AZUL_SUAVE)


# --------------------------------------------------------------------------
# Atraso de la cartera (tramos)
# --------------------------------------------------------------------------

def barras_atraso(filas: list[dict], altura=360) -> go.Figure:
    """
    Cuotas con atraso por tramo, en orden fijo y con color de semaforo.

    A diferencia de barras_horizontales(), NO se ordena por valor: el orden
    1-30 / 31-60 / +60 es semantico (gravedad creciente) y reordenarlo por
    tamano haria que el ojo comparara mal.
    """
    orden = list(PALETA_ATRASO)
    por_tramo = {f.get("_id"): f for f in filas}
    valores = [(por_tramo.get(t) or {}).get("cuotas", 0) or 0 for t in orden]

    fig = go.Figure(
        go.Bar(
            x=orden,
            y=valores,
            marker_color=[PALETA_ATRASO[t] for t in orden],
            text=[_miles(v) for v in valores],
            textposition="outside",
            textfont=dict(size=13.5, color=AZUL),
            cliponaxis=False,
            hovertemplate="%{x}: %{y} cuotas<extra></extra>",
        )
    )
    fig.update_yaxes(showticklabels=False, showgrid=False)
    fig.update_xaxes(tickfont=dict(size=12.5, color=AZUL))
    return _layout(fig, altura=altura, leyenda=None)
