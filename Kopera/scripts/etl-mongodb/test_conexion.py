"""
Prueba rapida de conexion a MongoDB Atlas.

NOTA: este script es un smoke test minimo. El verificador completo, que ademas
ejecuta el CRUD de humo, esta en Kopera/scripts/conexion_mongodb.py.

La ruta del .env era incorrecta: desde Kopera/scripts/etl-mongodb/ la raiz del
repositorio esta en parents[3], no en parents[2].
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

# .env esta en la raiz del repositorio: parents[3] desde este archivo
env_path = Path(__file__).resolve().parents[3] / '.env'
load_dotenv(env_path)

uri = os.getenv('MONGODB_URI')
if not uri:
    raise ValueError(
        f"MONGODB_URI no esta definida. Revisa el archivo {env_path}"
    )

cliente = MongoClient(uri, serverSelectionTimeoutMS=5000)
print(cliente.admin.command('ping'))
print(cliente.list_database_names())
cliente.close()