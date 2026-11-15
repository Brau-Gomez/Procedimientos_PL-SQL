"""
KOPERA · Interfaz web de la cartera de clientes (Streamlit).

Punto de entrada. Solo resuelve dos cosas: la navegacion entre vistas y el
estado de la conexion. Toda la logica de datos vive en consultas.py (lectura)
y operaciones.py (escritura).

Ejecucion local:
    streamlit run Kopera/app/main.py

Ejecucion con Docker (recomendada):
    docker compose -f docker-compose.app.yml up -d
"""

import streamlit as st

from config_app import BASE_MONGO, probar_conexion
from formato import numero
from ui import aplicar_tema, esc, panel_conexion
from vistas import (
    cartera,
    catalogos,
    clientes,
    ficha,
    inversiones,
    operaciones,
    panel,
    procesos,
)

# set_page_config debe ser el PRIMER comando de Streamlit del script.
st.set_page_config(
    page_title="KOPERA · Cartera",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tema institucional (CSS propio + colores de .streamlit/config.toml).
aplicar_tema()


# Mapa de navegacion. Se agrega una entrada por cada vista nueva.
PAGINAS = {
    "Panel general": panel.render,
    "Clientes": clientes.render,
    "Ficha del cliente": ficha.render,
    "Cartera y cuotas": cartera.render,
    "Inversiones": inversiones.render,
    "Catálogos": catalogos.render,
    "Procesos del ETL": procesos.render,
    "Operaciones (demo)": operaciones.render,
}


def barra_lateral():
    """Marca, navegacion y estado de la conexion."""
    with st.sidebar:
        st.markdown(
            '<div class="k-brand">KOPERA<span>.</span></div>'
            '<div class="k-brand-sub">Taller de Bases de Datos · BDY1103</div>',
            unsafe_allow_html=True,
        )
        st.write("")

        seleccion = st.radio(
            "Sección",
            list(PAGINAS.keys()),
            label_visibility="collapsed",
            key="nav",
        )

        st.divider()

        try:
            estado = probar_conexion()
            panel_conexion(
                True,
                f"· {esc(estado['base'])}",
                [(nombre, numero(cantidad))
                 for nombre, cantidad in estado["conteos"].items()],
            )
        except Exception as error:  # noqa: BLE001 - se muestra al usuario
            panel_conexion(False, f"· {esc(BASE_MONGO)}")
            st.caption(
                "Revisa MONGODB_URI en el .env y que la IP pública de esta "
                "máquina esté en la IP Access List de Atlas."
            )
            st.code(str(error), language="text")

        st.divider()
        st.caption("Datos: base `kopera` en MongoDB Atlas")

    return seleccion


def main():
    seleccion = barra_lateral()
    PAGINAS[seleccion]()


if __name__ == "__main__":
    main()
