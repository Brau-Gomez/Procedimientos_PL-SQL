"""
Configuracion central del proyecto KOPERA (Evaluacion Parcial 3).

Este modulo concentra TODA la configuracion y las dos conexiones del proyecto:

    Oracle        : esquema ADMIN_PROYECTO, que es la fuente de verdad y el motor
                    de la automatizacion (procedimientos, package, triggers).
    MongoDB Atlas : cluster M0 (tier gratuito), que es la capa de consulta y
                    coleccion donde se migra la ficha financiera del cliente.

Las credenciales se leen del archivo .env en la raiz del repositorio. Ese
archivo esta excluido del control de versiones, junto con atlas-credentials.env.
Nunca se escriben credenciales directamente en el codigo.
"""

import os
from pathlib import Path

import oracledb
from pymongo import MongoClient
from dotenv import load_dotenv

# Raiz del repositorio: Kopera/scripts/config.py -> parents[2]
RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=RAIZ / ".env")


# ==========================================================================
# CONSTANTES DE MONGODB
# ==========================================================================

# Base de datos donde vive la coleccion migrada
BASE_MONGO = os.getenv("MONGODB_DATABASE", "kopera")

# Nombres de las colecciones
COLECCION_CLIENTES = "clientes"
COLECCION_CATALOGOS = "catalogos"
COLECCION_BITACORA = "bitacora_pagos"
COLECCION_PROCESOS = "procesos_mensuales"

# Tiempo maximo de espera para elegir un servidor del cluster. Si se supera,
# la conexion falla rapido en lugar de quedarse colgada.
TIMEOUT_SERVIDOR_MS = 10000


# ==========================================================================
# ORACLE
# ==========================================================================

def obtener_parametros_oracle() -> oracledb.ConnectParams:
    """
    Encapsula host, puerto y nombre de servicio de Oracle.

    Se usan ConnectParams para dejar la configuracion de conexion en un solo
    lugar; las credenciales se pasan aparte, en conectar_oracle().
    """
    return oracledb.ConnectParams(
        host=os.getenv("ORACLE_HOST", "127.0.0.1"),
        port=int(os.getenv("ORACLE_PORT", "1521")),
        service_name=os.getenv("ORACLE_SERVICE_NAME", "FREEPDB1"),
    )


def conectar_oracle() -> oracledb.Connection:
    """
    Abre la conexion con el esquema KOPERA (ADMIN_PROYECTO).

    El driver trabaja en modo thin: habla el protocolo Oracle Net directamente
    y no requiere Oracle Client instalado en el sistema.
    """
    usuario = os.getenv("ORACLE_USER")
    clave = os.getenv("ORACLE_PASSWORD")
    if not usuario or not clave:
        raise RuntimeError(
            "Faltan ORACLE_USER / ORACLE_PASSWORD. Revisa el archivo .env en la raiz."
        )
    return oracledb.connect(
        user=usuario,
        password=clave,
        params=obtener_parametros_oracle(),
    )


# ==========================================================================
# MONGODB ATLAS
# ==========================================================================

def conectar_mongodb() -> MongoClient:
    """
    Abre el cliente contra el cluster de MongoDB Atlas.

    La URI se define en el .env con formato SRV (mongodb+srv://), que es el
    que entrega Atlas: el driver resuelve los nodos reales del cluster por DNS.

    retryWrites se deja en su valor por defecto (True). El cluster M0 si admite
    retryable writes, pero NO admite transacciones multi-documento, por lo que
    el diseno del CRUD debe trabajar siempre sobre un unico documento.
    """
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "Falta MONGODB_URI en el archivo .env de la raiz."
        )
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=TIMEOUT_SERVIDOR_MS,
        appname="kopera-eva3",
    )


def obtener_base_mongodb(cliente: MongoClient):
    """Devuelve el objeto Database donde se trabaja."""
    return cliente.get_database(BASE_MONGO)


def verificar_mongodb(cliente: MongoClient) -> dict:
    """
    Prueba de humo de la conexion a Atlas.

    Devuelve el resultado del ping, la version del servidor y la base de datos
    de trabajo. Si el ping falla, casi siempre es porque la IP publica de la
    maquina no esta en la IP Access List del proyecto en Atlas.
    """
    ping = cliente.admin.command("ping")
    version = cliente.admin.command("buildInfo")["version"]
    return {
        "ping": ping,
        "version": version,
        "base": BASE_MONGO,
        "colecciones": cliente.get_database(BASE_MONGO).list_collection_names(),
    }
