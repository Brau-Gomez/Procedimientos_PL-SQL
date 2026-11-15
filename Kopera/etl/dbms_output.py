"""
Helper para capturar la salida DBMS_OUTPUT de los procedimientos PL/SQL.

Contexto:
    Los procedimientos automaticos de la Evaluacion 2 (sp_reporte_cartera y
    pk_analisis_kopera.sp_proceso_mensual) NO devuelven un cursor de resultados:
    imprimen su informe con DBMS_OUTPUT.PUT_LINE. El driver python-oracledb no
    expone esa salida de forma automatica, por lo que hay que:

        1) habilitar el buffer con DBMS_OUTPUT.ENABLE,
        2) ejecutar el procedimiento,
        3) leer el buffer con DBMS_OUTPUT.GET_LINES hasta que se vacie.

    Tecnica documentada en la seccion 7.7 ("Using DBMS_OUTPUT") de la guia
    oficial de python-oracledb.

    La diferencia con un procedimiento que si devuelve filas es fundamental:
    aqui no hay result set, solo texto. Por eso el resultado se devuelve como
    una lista de cadenas y no como un cursor.
"""

# Cantidad de lineas que se piden en cada lectura del buffer.
TAMANO_LOTE = 100


def capturar_dbms_output(cursor, nombre_procedimiento, *argumentos):
    """
    Ejecuta un procedimiento PL/SQL y devuelve las lineas que imprima.

    Parametros:
        cursor               : cursor de la conexion (oracledb cursor).
        nombre_procedimiento : nombre del procedimiento, por ejemplo
                               "sp_reporte_cartera" o
                               "pk_analisis_kopera.sp_proceso_mensual".
        argumentos           : argumentos opcionales que recibe el procedimiento.

    Retorna:
        list[str]: lineas de salida en orden de emision.
    """
    # (1) Habilitar el buffer de salida para esta conexion
    cursor.callproc("dbms_output.enable")

    # (2) Ejecutar el procedimiento. callproc arma internamente un bloque
    #     anonimo equivalente a "begin <proc>(:1,...); end;"
    if argumentos:
        cursor.callproc(nombre_procedimiento, list(argumentos))
    else:
        cursor.callproc(nombre_procedimiento)

    # (3) Leer el buffer. GET_LINES devuelve como maximo TAMANO_LOTE lineas por
    #     llamada; si la ultima lectura trae menos que el lote, el buffer ya
    #     quedo vacio y se termina el ciclo.
    lineas = []
    var_lineas = cursor.arrayvar(str, TAMANO_LOTE)
    var_cantidad = cursor.var(int)
    var_cantidad.setvalue(0, TAMANO_LOTE)

    while True:
        cursor.callproc("dbms_output.get_lines", (var_lineas, var_cantidad))
        cantidad = var_cantidad.getvalue()
        lineas.extend([linea for linea in var_lineas.getvalue()[:cantidad] if linea])
        if cantidad < TAMANO_LOTE:
            break

    return lineas
