"""
Sistema visual de la aplicacion: paleta, CSS y componentes HTML.

Por que un modulo aparte:
    todas las pantallas deben verse igual sin repetir CSS. Las tarjetas KPI y
    las tablas se construyen como HTML propio (no con st.metric ni st.table)
    para que el estilo no dependa de las clases internas de Streamlit, que
    cambian entre versiones.

Paleta: azul institucional como color base y naranja como acento. El naranja
se reserva para lo que requiere atencion (riesgo, alertas, cifra principal);
si se usa en todo, pierde sentido.

Escala: los tamanos estan pensados para leerse en un proyector o en una
presentacion, no solo en un monitor de 13 pulgadas.
"""

import html as _html

import streamlit as st

# --------------------------------------------------------------------------
# Paleta
# --------------------------------------------------------------------------
AZUL = "#0B2E4F"          # institucional, titulos y cifras
AZUL_MEDIO = "#14406B"    # bordes de tarjeta
AZUL_SUAVE = "#4A90C4"    # series secundarias de graficos
NARANJA = "#E8722C"       # acento: alertas y KPI destacado
NARANJA_SUAVE = "#FDEBDD"
VERDE = "#1F7A5C"
ROJO = "#B3261E"
GRIS = "#5B6B7C"
GRIS_CLARO = "#9AA8B8"

PALETA_CLASIFICACION = {
    "RIESGO": ROJO,
    "REGULAR": NARANJA,
    "BUENO": VERDE,
    "OPORTUNIDAD": AZUL_SUAVE,
    "SIN PRODUCTOS": GRIS_CLARO,
}

# Colores de estado de cuota (coherentes con formato.SEMAFORO_CUOTA)
PALETA_CUOTA = {
    "PAGADA": VERDE,
    "PARCIAL": NARANJA,
    "VENCIDA": ROJO,
    "PENDIENTE": GRIS_CLARO,
}

# Tramos de atraso. Los cortes son los mismos de formato.badge_atraso (30/60
# dias) para que el grafico y las insignias cuenten la misma historia.
PALETA_ATRASO = {
    "1 a 30 días": "#D9A404",
    "31 a 60 días": NARANJA,
    "más de 60 días": ROJO,
}


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------
_CSS = f"""
<style>
  /* --- Layout general: mas ancho y con tipografia mas grande --- */
  [data-testid="stMainBlockContainer"], .block-container {{
    padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1700px;
  }}
  .stMarkdown p, .stMarkdown li {{ font-size: 1.02rem; }}
  [data-testid="stWidgetLabel"] p {{ font-size: .95rem; }}

  /* --- Encabezado de pagina --- */
  .k-header {{
    border-left: 7px solid {NARANJA};
    padding: .2rem 0 .2rem 1.1rem;
    margin-bottom: 1.7rem;
  }}
  .k-header .k-title {{
    font-size: 2.35rem; color: {AZUL}; margin: 0; letter-spacing: -.6px;
    font-weight: 750; line-height: 1.15;
  }}
  .k-header h1 {{
    font-size: 2.35rem; color: {AZUL}; margin: 0; letter-spacing: -.6px;
    font-weight: 750; line-height: 1.15;
  }}
  .k-header p {{ color: {GRIS}; margin: .35rem 0 0; font-size: 1.05rem; }}

  /* --- Se oculta la barra de acciones que Streamlit superpone al pasar el
         mouse (copiar / enlace). En un tablero solo distrae y hace que los
         titulos parezcan enlaces. --- */
  [data-testid="stElementToolbar"],
  [data-testid="stElementToolbarButton"] {{ display: none !important; }}
  [data-testid="stHeadingWithActionElements"] a {{ display: none !important; }}

  /* --- Tarjetas KPI --- */
  .k-kpi {{
    background: #FFFFFF;
    border: 1px solid #E3EAF3;
    border-top: 4px solid {AZUL_MEDIO};
    border-radius: 12px;
    padding: 1.15rem 1.3rem;
    box-shadow: 0 1px 4px rgba(11, 46, 79, .07);
    height: 100%;
    cursor: default;
  }}
  .k-kpi-label {{ cursor: default; user-select: none; }}
  .k-kpi.destacado {{ border-top-color: {NARANJA}; background: #FFFCF9; }}
  .k-kpi-label {{
    font-size: .82rem; text-transform: uppercase; letter-spacing: .09em;
    color: {GRIS}; font-weight: 700;
  }}
  .k-kpi-value {{
    font-size: 2.15rem; font-weight: 750; color: {AZUL};
    line-height: 1.2; margin-top: .35rem;
    font-variant-numeric: tabular-nums;
  }}
  .k-kpi-foot {{ font-size: .93rem; color: {GRIS}; margin-top: .4rem; }}
  .k-kpi-foot.alerta {{ color: {NARANJA}; font-weight: 700; }}

  /* --- Franja de alerta --- */
  .k-alerta {{
    background: {NARANJA_SUAVE};
    border-left: 6px solid {NARANJA};
    border-radius: 7px;
    padding: .9rem 1.15rem;
    color: #7A3A0E;
    font-size: 1.02rem;
    line-height: 1.5;
    margin: .3rem 0 .2rem;
  }}
  .k-alerta.ok {{
    background: #E7F3EC; border-left-color: {VERDE}; color: #174F3B;
  }}

  /* --- Titulo de seccion --- */
  .k-seccion {{ font-size: 1.22rem; font-weight: 700; color: {AZUL}; margin: 0; }}
  .k-seccion-sub {{ font-size: .93rem; color: {GRIS}; margin: .2rem 0 .8rem; }}

  /* --- Fila de datos compactos --- */
  .k-mini {{ display: flex; gap: 2rem; flex-wrap: wrap; font-size: 1rem; color: {GRIS}; }}
  .k-mini b {{ color: {AZUL}; font-weight: 700; font-size: 1.05rem; }}

  /* --- Tablas HTML --- */
  .k-tabla-wrap {{ overflow-x: auto; margin: .2rem 0 .4rem; }}
  .k-tabla {{
    width: 100%; border-collapse: collapse; font-size: .95rem;
    background: #FFFFFF; border-radius: 8px; overflow: hidden;
  }}
  .k-tabla thead th {{
    background: {AZUL}; color: #FFFFFF; text-align: left;
    padding: .65rem .75rem; font-weight: 650; font-size: .76rem;
    letter-spacing: .06em; text-transform: uppercase; white-space: nowrap;
  }}
  .k-tabla td {{
    padding: .62rem .75rem; border-bottom: 1px solid #E3EAF3;
    color: #22384E; vertical-align: middle;
  }}
  .k-tabla tbody tr:nth-child(even) td {{ background: #F7F9FC; }}
  .k-tabla tbody tr:hover td {{ background: #EDF3FA; }}
  .k-tabla .num {{ text-align: right; font-variant-numeric: tabular-nums; }}

  /* --- Insignias (semaforos) --- */
  .k-badge {{
    display: inline-block; padding: .2rem .62rem; border-radius: 999px;
    font-size: .82rem; font-weight: 700; white-space: nowrap;
  }}
  .k-badge-verde {{ background: #E7F3EC; color: #174F3B; }}
  .k-badge-amarillo {{ background: #FCF3D6; color: #7A5A0B; }}
  .k-badge-naranja {{ background: #FDEBDD; color: #8A3F0E; }}
  .k-badge-rojo {{ background: #FBE4E2; color: #8C1D18; }}
  .k-badge-gris {{ background: #EDF1F6; color: #5B6B7C; }}
  .k-badge-azul {{ background: #E6EFF8; color: #14406B; }}

  /* --- Grilla de datos (ficha) --- */
  .k-datos {{ width: 100%; border-collapse: collapse; font-size: 1rem; }}
  .k-datos th {{
    text-align: left; font-weight: 600; color: {GRIS}; width: 42%;
    padding: .45rem .6rem .45rem 0; border-bottom: 1px solid #E3EAF3;
    vertical-align: top;
  }}
  .k-datos td {{
    color: {AZUL}; font-weight: 550; padding: .45rem 0;
    border-bottom: 1px solid #E3EAF3;
  }}

  /* --- Widgets --- */
  button[data-baseweb="tab"] {{ font-size: 1.02rem !important; font-weight: 600; }}
  [data-testid="stExpander"] summary p {{
    font-size: 1.05rem !important; font-weight: 650; color: {AZUL};
  }}
  [data-testid="stDataFrame"] {{ font-size: .98rem; }}

  /* --- Barra lateral institucional --- */
  [data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {AZUL} 0%, {AZUL_MEDIO} 100%);
  }}
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] small,
  [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] {{
    color: #E8EEF6 !important;
  }}
  [data-testid="stSidebar"] [role="radiogroup"] label p {{ font-size: 1.04rem; }}
  [data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.16); }}
  /* --- Panel de conexion (barra lateral) ---
     Se construye con un <details> PROPIO y no con st.expander. Motivo: el
     expander de Streamlit pinta su encabezado con bgMix (mezcla clara del
     tema) y esa capa cambia de nombre entre versiones, por eso se seguia
     viendo como un recuadro blanco sobre el sidebar azul. Con <details> el
     fondo es nuestro y no depende del tema ni de la version. */
  [data-testid="stSidebar"] details.k-panel {{
    background: #10355A;
    border: 1px solid rgba(255,255,255,.22);
    border-radius: 9px;
    margin: .1rem 0 .9rem;
    overflow: hidden;
  }}
  [data-testid="stSidebar"] details.k-panel > summary {{
    background: #10355A;
    color: #FFFFFF !important;
    padding: .62rem .85rem;
    font-size: .98rem;
    font-weight: 650;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    list-style: none;
  }}
  [data-testid="stSidebar"] details.k-panel > summary::-webkit-details-marker {{
    display: none;
  }}
  [data-testid="stSidebar"] details.k-panel > summary::after {{
    content: "▾"; color: #FFFFFF; font-size: .9rem; line-height: 1;
  }}
  [data-testid="stSidebar"] details.k-panel[open] > summary::after {{
    content: "▴";
  }}
  [data-testid="stSidebar"] details.k-panel > summary:hover {{
    background: #17497A;
  }}
  [data-testid="stSidebar"] details.k-panel .k-panel-cuerpo {{
    padding: .75rem .85rem .8rem;
    border-top: 1px solid rgba(255,255,255,.14);
  }}
  [data-testid="stSidebar"] details.k-panel .k-panel-cuerpo > p {{
    margin: 0 0 .1rem; color: #FFFFFF !important; font-size: .95rem;
  }}
  [data-testid="stSidebar"] details.k-panel ul.k-conn-lista {{
    list-style: none; margin: .55rem 0 0; padding: 0; font-size: .92rem;
  }}
  [data-testid="stSidebar"] details.k-panel ul.k-conn-lista li {{
    display: flex; justify-content: space-between; gap: .6rem;
    padding: .14rem 0; color: #C9D8E8 !important;
  }}
  [data-testid="stSidebar"] details.k-panel ul.k-conn-lista li b {{
    color: #FFFFFF !important;
  }}
  /* La regla del sidebar pinta TODO span con color claro. Eso dejaba el texto
     de la insignia de estado invisible sobre su fondo claro, porque el span
     interno heredaba un !important. Se restituye el color de cada tono. */
  [data-testid="stSidebar"] details.k-panel .k-badge {{
    color: #174F3B !important;
  }}
  [data-testid="stSidebar"] details.k-panel .k-badge-rojo {{
    color: #8C1D18 !important;
  }}
  [data-testid="stSidebar"] code {{ background: rgba(255,255,255,.12); color: #FFFFFF; }}
  [data-testid="stSidebar"] .k-brand {{
    font-size: 1.7rem; font-weight: 800; letter-spacing: .5px; color: #FFFFFF;
  }}
  [data-testid="stSidebar"] .k-brand span {{ color: {NARANJA}; }}
  [data-testid="stSidebar"] .k-brand-sub {{
    font-size: .78rem; color: #A9BCD2; letter-spacing: .06em;
    text-transform: uppercase; margin-top: .1rem;
  }}
</style>
"""


def aplicar_tema():
    """Inyecta el CSS. Se llama una vez al inicio de cada rerun."""
    st.markdown(_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def esc(valor) -> str:
    """Escapa texto que viene de la base antes de inyectarlo en HTML."""
    return _html.escape(str(valor)) if valor is not None else ""


# --------------------------------------------------------------------------
# Componentes
# --------------------------------------------------------------------------

def header(titulo: str, subtitulo: str = ""):
    """
    Encabezado de pagina con la barra naranja de acento.

    Se usa un <div> y no un <h1>: Streamlit envuelve los titulos de markdown
    en un componente con un boton de ancla que aparece al pasar el mouse, y
    eso hace que el titulo parezca un enlace.
    """
    st.markdown(
        f'<div class="k-header"><div class="k-title">{titulo}</div>'
        f'<p>{subtitulo}</p></div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, valor: str, pie: str = "", destacado: bool = False,
        alerta: bool = False):
    """
    Tarjeta KPI.

    destacado=True la pinta con borde naranja: usar SOLO en la cifra principal
    de la pantalla, para que el ojo sepa donde mirar primero.
    """
    clase = "k-kpi destacado" if destacado else "k-kpi"
    clase_pie = "k-kpi-foot alerta" if alerta else "k-kpi-foot"
    st.markdown(
        f'<div class="{clase}">'
        f'<div class="k-kpi-label">{label}</div>'
        f'<div class="k-kpi-value">{valor}</div>'
        f'<div class="{clase_pie}">{pie}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def alerta(texto: str, ok: bool = False):
    """Franja de mensaje unico. ok=True la vuelve verde (nada que reportar)."""
    clase = "k-alerta ok" if ok else "k-alerta"
    st.markdown(f'<div class="{clase}">{texto}</div>', unsafe_allow_html=True)


def panel_conexion(ok: bool, mensaje: str,
                   items: list[tuple[str, str]] | None = None):
    """
    Panel desplegable de estado de la conexion, para la barra lateral.

    Usa un <details> propio en lugar de st.expander: el encabezado del
    expander de Streamlit se pinta con una mezcla clara del tema y aparece
    como un recuadro blanco sobre el azul del sidebar. Con <details> el color
    lo definimos nosotros (ver la regla details.k-panel en el CSS).

    ok=True muestra la insignia verde "Conectado"; ok=False la roja.
    `items` son los pares (coleccion, cantidad) que se listan dentro.
    """
    tono = "verde" if ok else "rojo"
    etiqueta = "Conectado" if ok else "Sin conexión"
    lista = ""
    if items:
        filas = "".join(
            f"<li><span>{esc(nombre)}</span><b>{esc(valor)}</b></li>"
            for nombre, valor in items
        )
        lista = f'<ul class="k-conn-lista">{filas}</ul>'

    # Todo en una sola linea: un salto seguido de sangria haria que Markdown
    # lo interprete como bloque de codigo y se pierda el formato.
    html = (
        '<details class="k-panel">'
        '<summary>Estado de la conexión</summary>'
        '<div class="k-panel-cuerpo">'
        f'<p>{badge(etiqueta, tono)} {esc(mensaje)}</p>'
        f"{lista}"
        "</div>"
        "</details>"
    )
    st.markdown(html, unsafe_allow_html=True)


def seccion(titulo: str, subtitulo: str = ""):
    """Titulo de seccion con bajada opcional."""
    sub = f'<p class="k-seccion-sub">{subtitulo}</p>' if subtitulo else ""
    st.markdown(
        f'<p class="k-seccion">{titulo}</p>{sub}', unsafe_allow_html=True
    )


def mini_fila(items: list[tuple[str, str]]):
    """Fila de datos secundarios en texto: [("Clientes", "130"), ...]."""
    partes = "".join(f"<span>{k} <b>{v}</b></span>" for k, v in items)
    st.markdown(f'<div class="k-mini">{partes}</div>', unsafe_allow_html=True)


def badge(texto: str, tono: str = "gris") -> str:
    """
    Insignia de color para semaforos.

    tono: verde | amarillo | naranja | rojo | gris | azul
    Devuelve HTML: se usa dentro de tabla() o de una franja.
    """
    return f'<span class="k-badge k-badge-{tono}">{esc(texto)}</span>'


def tabla(encabezados: list[str], filas: list[list[str]],
          alinear_derecha: list[int] | None = None):
    """
    Tabla HTML con encabezado azul y filas alternadas.

    `filas` contiene HTML ya construido (por ejemplo con badge()), asi que el
    llamador es responsable de escapar los textos libres con esc().
    """
    derecha = set(alinear_derecha or [])
    head = "".join(
        f'<th class="num">{esc(h)}</th>' if i in derecha else f"<th>{esc(h)}</th>"
        for i, h in enumerate(encabezados)
    )
    cuerpo = []
    for fila in filas:
        celdas = "".join(
            f'<td class="num">{valor}</td>' if i in derecha else f"<td>{valor}</td>"
            for i, valor in enumerate(fila)
        )
        cuerpo.append(f"<tr>{celdas}</tr>")

    st.markdown(
        '<div class="k-tabla-wrap"><table class="k-tabla">'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(cuerpo)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def datos_grid(pares: list[tuple[str, str]]):
    """Grilla etiqueta/valor para la ficha del cliente."""
    filas = "".join(
        f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in pares
    )
    st.markdown(f'<table class="k-datos">{filas}</table>', unsafe_allow_html=True)


def estado_vacio(mensaje: str):
    """Mensaje neutral para listas o secciones sin datos."""
    st.info(mensaje, icon="ℹ️")
