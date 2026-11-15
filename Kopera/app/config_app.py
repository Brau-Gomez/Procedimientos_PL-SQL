"""
Conexion a MongoDB Atlas para la aplicacion web de KOPERA.

Por que no se importa Kopera/etl/config.py:
    ese modulo hace `import oracledb` a nivel de modulo. La interfaz solo
    necesita MongoDB, asi que arrastrar el driver de Oracle al contenedor
    seria peso y dependencia innecesarios.

Que SI se reutiliza:
    las mismas variables del .env de la raiz que usa el ETL
    (MONGODB_URI, MONGODB_DATABASE) y los mismos nombres de coleccion.
    Asi la app siempre muestra exactamente la base que acaba de cargar
    etl_principal.py.
"""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient

def _raiz_con_env() -> Path:
    """
    Ubica la carpeta que contiene el .env subiendo desde este archivo.

    No se usa un parents[N] fijo a proposito: en local el archivo esta en
    Kopera/app/ (raiz = parents[2]) pero dentro de la imagen Docker queda en
    /app/ y parents[2] no existe. Buscar el .env funciona en ambos casos; si
    no aparece (caso Docker), se devuelve el directorio actual y las variables
    llegan igual por environment desde env_file.
    """
    actual = Path(__file__).resolve()
    for directorio in [actual.parent, *actual.parents]:
        if (directorio / ".env").exists():
            return directorio
    return Path.cwd()


RAIZ = _raiz_con_env()
load_dotenv(dotenv_path=RAIZ / ".env")

BASE_MONGO = os.getenv("MONGODB_DATABASE", "kopera")

# Mismos nombres que config.py del ETL.
COLECCION_CLIENTES = "clientes"
COLECCION_CATALOGOS = "catalogos"
COLECCION_BITACORA = "bitacora_pagos"
COLECCION_PROCESOS = "procesos_mensuales"

COLECCIONES = (
    COLECCION_CLIENTES,
    COLECCION_CATALOGOS,
    COLECCION_BITACORA,
    COLECCION_PROCESOS,
)

# Si Atlas no responde en este plazo, mejor fallar rapido que colgar la pagina.
TIMEOUT_MS = 10000


@st.cache_resource(show_spinner=False)
def obtener_cliente() -> MongoClient:
    """
    Devuelve el cliente de MongoDB (una sola instancia por proceso).

    cache_resource guarda el objeto entre reruns de Streamlit. Es importante:
    si se creara un MongoClient por consulta, cada interaccion del usuario
    abriria un pool de conexiones nuevo y el cluster M0 de Atlas terminaria
    rechazando conexiones.
    """
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "Falta MONGODB_URI. Defínela en el archivo .env de la raíz "
            "o pásala por env_file en docker-compose.app.yml."
        )
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=TIMEOUT_MS,
        appname="kopera-web",
    )


def obtener_base():
    """Devuelve el objeto Database de trabajo (base 'kopera')."""
    return obtener_cliente().get_database(BASE_MONGO)


def probar_conexion() -> dict:
    """
    Prueba de humo para la barra lateral.

    Devuelve el estado de la conexion y el conteo de documentos por coleccion.
    Si el ping falla, casi siempre es porque la IP publica de la maquina no
    esta en la IP Access List del proyecto en Atlas.
    """
    base = obtener_base()
    cliente = obtener_cliente()
    cliente.admin.command("ping")

    conteos = {}
    for nombre in COLECCIONES:
        conteos[nombre] = base[nombre].count_documents({})

    return {"base": BASE_MONGO, "conteos": conteos}
