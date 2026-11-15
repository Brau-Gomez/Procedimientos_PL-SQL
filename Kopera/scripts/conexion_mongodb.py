"""
Verificacion de la conexion a MongoDB Atlas (cluster M0 del proyecto KOPERA).

Este script cubre el Paso 4 de la guia de verificacion del Dia 1:
    1) Abre el cliente contra el cluster y ejecuta un ping.
    2) Muestra la version del servidor y las colecciones existentes.
    3) Ejecuta un CRUD minimo de humo (Create, Read, Update, Delete) sobre una
       coleccion temporal, que se elimina al terminar.

La coleccion de prueba se descarta al final: no queda ningun documento de
prueba en la base 'kopera'.

Ejecucion:
    .venv/bin/python Kopera/scripts/conexion_mongodb.py
"""

from config import (
    BASE_MONGO,
    conectar_mongodb,
    obtener_base_mongodb,
    verificar_mongodb,
)

COLECCION_PRUEBA = "_verificacion_conexion"


def mostrar_estado(cliente):
    """Muestra el resultado del ping, la version y las colecciones."""
    print("Conexion a MongoDB Atlas:")
    print(f"  Base de datos de trabajo: {BASE_MONGO}")

    estado = verificar_mongodb(cliente)
    print(f"  Ping                  : {estado['ping']}")
    print(f"  Version del servidor  : {estado['version']}")

    if estado["colecciones"]:
        print("  Colecciones existentes:")
        for nombre in estado["colecciones"]:
            print(f"    - {nombre}")
    else:
        print("  Colecciones existentes: (ninguna, la base esta vacia)")

    return estado


def prueba_crud(cliente):
    """
    Prueba de humo del CRUD sobre una coleccion temporal.

    Create : inserta un documento.
    Read   : lo recupera y lo cuenta.
    Update : modifica un campo del documento.
    Delete : elimina el documento y luego la coleccion.
    """
    base = obtener_base_mongodb(cliente)
    coleccion = base[COLECCION_PRUEBA]
    print(f"\nPrueba de humo CRUD en '{BASE_MONGO}.{COLECCION_PRUEBA}':")

    # Create
    resultado = coleccion.insert_one(
        {"tipo": "verificacion", "estado": "inicial", "intentos": 1}
    )
    print(f"  Create : documento insertado con _id={resultado.inserted_id}")

    # Read
    documento = coleccion.find_one({"_id": resultado.inserted_id})
    print(f"  Read   : documento recuperado -> {documento}")

    # Update
    coleccion.update_one(
        {"_id": resultado.inserted_id}, {"$set": {"estado": "actualizado"}}
    )
    documento = coleccion.find_one({"_id": resultado.inserted_id})
    print(f"  Update : documento actualizado -> {documento}")

    # Delete
    borrado = coleccion.delete_one({"_id": resultado.inserted_id})
    print(f"  Delete : documentos eliminados -> {borrado.deleted_count}")
    print(f"          quedan {coleccion.count_documents({})} documentos en la coleccion")

    # Limpieza: se elimina la coleccion temporal
    coleccion.drop()
    print(f"  Limpieza: coleccion '{COLECCION_PRUEBA}' eliminada")


def main():
    """Punto de entrada del script."""
    try:
        with conectar_mongodb() as cliente:
            mostrar_estado(cliente)
            prueba_crud(cliente)

    except Exception as e:
        print(f"Error al conectar con MongoDB Atlas: {e}")
        print(
            "Revisa que la IP publica de esta maquina "
            "(curl -s https://api.ipify.org) este en la IP Access List del proyecto."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
