"""
Verificacion de la conexion a Oracle y ejecucion de los procesos automaticos
de KOPERA (objetos PL/SQL de la Evaluacion 2).

Este script cubre el Paso 2 de la guia de verificacion del Dia 1:
    1) Confirma que se puede conectar al esquema ADMIN_PROYECTO.
    2) Lista los objetos programables del esquema y su estado de compilacion.
    3) Ejecuta los dos procesos automaticos de la Evaluacion 2
       (sp_reporte_cartera y pk_analisis_kopera.sp_proceso_mensual) y muestra
       la salida que cada uno genera.

Nota sobre pandas: no se usa aqui porque estos procedimientos imprimen texto
formateado, no un result set tabular. pandas queda disponible para los scripts
de extraccion y CRUD, donde si se trabalha con filas.

Ejecucion:
    .venv/bin/python Kopera/scripts/conexion_oracle.py
"""

from config import conectar_oracle
from dbms_output import capturar_dbms_output


def mostrar_servidor(cursor):
    """
    Muestra la version del servidor Oracle al que se conecto.

    La vista v$version exige privilegios que el usuario ADMIN_PROYECTO puede
    no tener (ORA-00942). Si falla, se recurre a product_component_version,
    que es de lectura publica.
    """
    try:
        cursor.execute("SELECT banner FROM v$version WHERE banner LIKE 'Oracle%'")
        fila = cursor.fetchone()
        if fila:
            print("Servidor:", fila[0].splitlines()[0])
            return
    except Exception:
        pass

    cursor.execute("""
        SELECT version FROM product_component_version
         WHERE product LIKE 'Oracle%' AND ROWNUM = 1
    """)
    fila = cursor.fetchone()
    print("Servidor:", fila[0] if fila else "(version no disponible)")


def mostrar_objetos(cursor):
    """Lista los objetos programables del esquema y su estado de compilacion."""
    cursor.execute("""
        SELECT object_type, status, COUNT(*) AS total
          FROM user_objects
         WHERE object_type IN (
               'PROCEDURE', 'FUNCTION', 'PACKAGE', 'PACKAGE BODY',
               'TRIGGER', 'TYPE', 'TYPE BODY'
               )
         GROUP BY object_type, status
         ORDER BY object_type, status
    """)
    objetos = cursor.fetchall()

    print("Objetos programables del esquema conectado:")
    if objetos:
        for tipo, estado, total in objetos:
            print(f"  {tipo} ({estado}): {total}")
    else:
        print("  No se encontraron objetos programables.")

    return objetos


def ejecutar_procesos_automaticos(cursor):
    """
    Ejecuta los procesos automaticos de la Evaluacion 2 y muestra su salida.

    Ambos procedimientos son sin parametros: no devuelven filas, imprimen su
    informe con DBMS_OUTPUT, por eso se capturan con el helper
    capturar_dbms_output.
    """
    procesos = [
        ("sp_reporte_cartera", "Reporte consolidado de la cartera de creditos"),
        ("pk_analisis_kopera.sp_proceso_mensual", "Analisis mensual de los clientes"),
    ]

    for nombre, descripcion in procesos:
        print("=" * 70)
        print(f"  {descripcion}")
        print(f"  Procedimiento: {nombre}")
        print("=" * 70)

        lineas = capturar_dbms_output(cursor, nombre)
        for linea in lineas:
            print(linea)

        print(f"  (lineas capturadas: {len(lineas)})")
        print()


def main():
    """Punto de entrada del script."""
    try:
        # Una sola conexion para toda la verificacion. El bloque with se
        # encarga de cerrarla, incluso si ocurre una excepcion.
        with conectar_oracle() as conexion:
            with conexion.cursor() as cursor:
                mostrar_servidor(cursor)
                print()
                mostrar_objetos(cursor)
                print()
                ejecutar_procesos_automaticos(cursor)

    except Exception as e:
        print(f"Error al ejecutar la verificacion en Oracle: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
