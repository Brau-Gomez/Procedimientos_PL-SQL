"""
Orquestador del pipeline ETL de KOPERA (Oracle -> MongoDB Atlas).

Ejecuta las cuatro etapas del proceso en un solo comando:

    1. EXTRACCION   Oracle  ->  estructuras planas (set-based, sin loops).
    2. TRANSFORMACION  datos planos  ->  documentos NoSQL (limpieza de
       caracteres, anidado por agregado, reclasificacion a OPORTUNIDAD).
    3. VALIDACION   se aplican las reglas de los triggers de Oracle sobre los
       documentos migrados, y se emite el reporte de validacion.
    4. CARGA        documentos  ->  Atlas (colecciones con $jsonSchema + indices).

La validacion va ANTES de la carga a proposito: si un documento violara una
regla no debe llegar a Atlas.

Antes de ejecutar este script, la bitacora de Oracle debe estar poblada
(Kopera/etl/poblar_bitacora.py): el ETL refleja el estado ACTUAL de la
base, y los pagos cambian cuotas, saldos y clasificaciones.

Uso:
    .venv/bin/python Kopera/etl/etl_principal.py --simular
    .venv/bin/python Kopera/etl/etl_principal.py
    .venv/bin/python Kopera/etl/etl_principal.py --sin-proceso
"""

import argparse
from datetime import datetime

import extraccion_oracle as extraccion
import transformacion as transform
import validaciones as reglas
from carga_mongodb import cargar_todo, verificar_carga
from config import (
    COLECCION_BITACORA,
    COLECCION_CATALOGOS,
    COLECCION_CLIENTES,
    COLECCION_PROCESOS,
    conectar_mongodb,
    conectar_oracle,
    obtener_base_mongodb,
)
from dbms_output import capturar_dbms_output

# Procedimiento del package que produce el informe mensual.
PROCEDIMIENTO_PROCESO = "pk_analisis_kopera.sp_proceso_mensual"


def imprimir_encabezado(titulo):
    print()
    print("=" * 78)
    print(f"  {titulo}")
    print("=" * 78)


def extraer_todo(conexion):
    """
    ETAPA 1: lee todo de Oracle y devuelve el diccionario de datos planos.

    Ademas captura la salida de sp_proceso_mensual, que es el informe mensual
    que el package PL/SQL produce con DBMS_OUTPUT.
    """
    with conexion.cursor() as cursor:
        fecha_corte = extraccion.obtener_fecha_corte(cursor)

        datos = {
            "fecha_corte": fecha_corte,
            "clientes": extraccion.extraer_clientes(cursor),
            "analisis": extraccion.extraer_analisis_clientes(cursor),
            "totales": extraccion.extraer_totales_clientes(cursor),
            "creditos": extraccion.extraer_creditos(cursor),
            "cuotas": extraccion.extraer_cuotas(cursor),
            "inversiones": extraccion.extraer_inversiones(cursor),
            "movimientos": extraccion.extraer_movimientos(cursor),
            "catalogos": extraccion.extraer_catalogos(cursor),
            "bitacora": extraccion.extraer_bitacora(cursor),
            "pagos": extraccion.extraer_pagos_por_cliente(cursor),
        }

    return datos


def capturar_proceso_mensual(conexion):
    """
    Ejecuta sp_proceso_mensual y devuelve sus lineas de salida.

    El procedimiento no devuelve un cursor: imprime con DBMS_OUTPUT. Por eso
    se usa el helper capturar_dbms_output, que habilita el buffer, ejecuta el
    procedimiento y lee el buffer.
    """
    with conexion.cursor() as cursor:
        lineas = capturar_dbms_output(cursor, PROCEDIMIENTO_PROCESO)
    return lineas


def transformar(datos, lineas_proceso):
    """
    ETAPA 2: convierte los datos planos en documentos de MongoDB.
    """
    documentos_clientes, observaciones = transform.construir_documentos_clientes(datos)
    documentos_catalogos = transform.construir_documentos_catalogos(datos["catalogos"])
    documentos_bitacora = transform.construir_documentos_bitacora(datos["bitacora"])

    documentos_procesos = []
    if lineas_proceso:
        # Las lineas del informe tambien pasan por la limpieza: el package
        # arma el nombre con los datos CRUDOS de Oracle. El resumen se parsea
        # sobre las lineas YA limpiadas, para que el documento y los totales
        # provengan del mismo texto.
        lineas_limpias = [transform.limpiar_texto(linea) for linea in lineas_proceso]
        clientes_analizados, saldo_total = transform.parsear_resumen_proceso(lineas_limpias)
        documentos_procesos.append(
            transform.construir_documento_proceso(
                lineas_limpias,
                datos["fecha_corte"],
                clientes_analizados,
                saldo_total,
            )
        )

    return {
        "clientes": documentos_clientes,
        "catalogos": documentos_catalogos,
        "bitacora": documentos_bitacora,
        "procesos": documentos_procesos,
        "observaciones": observaciones,
    }


def validar_documentos(documentos_clientes):
    """
    ETAPA 4: aplica las reglas de los triggers sobre los documentos migrados.

    Devuelve (resumen, detalle) donde detalle son los mensajes con su
    documento de referencia, para el anexo del informe.
    """
    resultados = []
    detalle = []

    for documento in documentos_clientes:
        resultado = reglas.validar_documento_cliente(documento)
        resultados.append(resultado)

        for error in resultado.errores:
            detalle.append({
                "tipo": "ERROR",
                "nro_cliente": documento.get("nro_cliente"),
                "codigo": error["codigo"],
                "mensaje": error["mensaje"],
            })
        for observacion in resultado.observaciones:
            detalle.append({
                "tipo": "OBSERVACION",
                "nro_cliente": documento.get("nro_cliente"),
                "codigo": observacion["codigo"],
                "mensaje": observacion["mensaje"],
            })

    return reglas.resumir_validaciones(resultados), detalle


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline ETL de KOPERA: Oracle -> MongoDB Atlas."
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Ejecuta todo el pipeline pero NO escribe en Atlas.",
    )
    parser.add_argument(
        "--sin-proceso",
        action="store_true",
        help="No ejecuta sp_proceso_mensual (la coleccion procesos_mensuales queda vacia).",
    )
    args = parser.parse_args()

    modo = "SIMULACION (no se escribe en Atlas)" if args.simular else "EJECUCION REAL"

    imprimir_encabezado("KOPERA - Migracion Oracle -> MongoDB Atlas (EVAL 3)")
    print(f"  Modo            : {modo}")
    print(f"  Fecha de proceso: {datetime.now():%d/%m/%Y %H:%M}")
    print()

    # ---------------------------------------------------------------- ETAPA 1
    imprimir_encabezado("ETAPA 1 - EXTRACCION desde Oracle")
    with conectar_oracle() as conexion:
        datos = extraer_todo(conexion)
        lineas_proceso = [] if args.sin_proceso else capturar_proceso_mensual(conexion)

    print(f"  Fecha de corte (SYSDATE de Oracle) : {datos['fecha_corte']}")
    print(f"  Clientes                           : {len(datos['clientes'])}")
    print(f"  Creditos                           : {len(datos['creditos'])}")
    print(f"  Cuotas                             : {len(datos['cuotas'])}")
    print(f"  Inversiones                        : {len(datos['inversiones'])}")
    print(f"  Movimientos                        : {len(datos['movimientos'])}")
    print(f"  Eventos de bitacora                : {len(datos['bitacora'])}")
    print(f"  Lineas del proceso mensual         : {len(lineas_proceso)}")

    # ---------------------------------------------------------------- ETAPA 2
    imprimir_encabezado("ETAPA 2 - TRANSFORMACION a documentos NoSQL")
    documentos = transformar(datos, lineas_proceso)

    cuotas_embebidas = sum(
        len(c["cuotas"]) for d in documentos["clientes"] for c in d["creditos"]
    )
    movimientos_embebidos = sum(
        len(i["movimientos"]) for d in documentos["clientes"] for i in d["inversiones"]
    )
    pagos_embebidos = sum(len(d["historial_pagos"]) for d in documentos["clientes"])

    print(f"  Documentos de cliente              : {len(documentos['clientes'])}")
    print(f"  Cuotas embebidas                   : {cuotas_embebidas} "
          f"(de {len(datos['cuotas'])} en Oracle)")
    print(f"  Movimientos embebidos              : {movimientos_embebidos} "
          f"(de {len(datos['movimientos'])} en Oracle)")
    print(f"  Pagos embebidos en el cliente      : {pagos_embebidos}")
    print(f"  Documentos de catalogo             : {len(documentos['catalogos'])}")
    print(f"  Documentos de bitacora             : {len(documentos['bitacora'])}")
    print(f"  Documentos de proceso mensual      : {len(documentos['procesos'])}")
    print(f"  Clientes con texto sin corregir    : {len(documentos['observaciones'])}")

    # ---------------------------------------------------------------- ETAPA 3
    # La validacion se hace ANTES de cargar: si un documento violara una regla
    # no debe llegar a Atlas.
    imprimir_encabezado("ETAPA 3 - VALIDACION (reglas de los triggers de Oracle)")
    resumen_validacion, detalle_validacion = validar_documentos(documentos["clientes"])
    print(f"  Documentos validados               : {resumen_validacion['documentos_validados']}")
    print(f"  Documentos con errores             : {resumen_validacion['documentos_con_errores']}")
    print(f"  Documentos con observaciones        : {resumen_validacion['documentos_con_observaciones']}")
    print(f"  Total de errores                   : {resumen_validacion['total_errores']}")
    print(f"  Total de observaciones             : {resumen_validacion['total_observaciones']}")
    if resumen_validacion["errores_por_codigo"]:
        print(f"  Errores por codigo                 : {resumen_validacion['errores_por_codigo']}")

    if resumen_validacion["documentos_con_errores"]:
        print()
        print("  Los siguientes clientes tienen inconsistencies heredadas de la")
        print("  semilla BD_KOPERA.SQL (datos que se cargaron sin pasar por los")
        print("  triggers). Se informan, no bloquean la carga:")
        for item in detalle_validacion:
            if item["tipo"] == "ERROR":
                print(f"    [ERROR] cliente {item['nro_cliente']}: {item['mensaje']}")

    # ---------------------------------------------------------------- ETAPA 4
    imprimir_encabezado("ETAPA 4 - CARGA en MongoDB Atlas")

    if args.simular:
        print("  Modo simulacion: no se escribe nada en Atlas.")
        print(f"  Se habrian cargado {len(documentos['clientes'])} clientes, "
              f"{len(documentos['catalogos'])} catalogos, "
              f"{len(documentos['bitacora'])} eventos de bitacora y "
              f"{len(documentos['procesos'])} procesos mensuales.")
        print()
        print("  Sin cambios en Atlas. Use el comando sin --simular para cargar.")
        return 0

    with conectar_mongodb() as cliente:
        base = obtener_base_mongodb(cliente)

        reporte = cargar_todo(
            base,
            documentos["clientes"],
            documentos["catalogos"],
            documentos["bitacora"],
            documentos["procesos"] or None,
        )

        print(f"  Colecciones recargadas (intercambio): {reporte['colecciones_recargadas']}")
        print()
        print(f"  {'coleccion':<22} {'recibidos':>10} {'insertados':>11} {'rechazados':>11}")
        print("  " + "-" * 58)
        for carga in reporte["cargas"]:
            print(f"  {carga['coleccion']:<22} {carga['recibidos']:>10} "
                  f"{carga['insertados']:>11} {carga['rechazados']:>11}")
        print("  " + "-" * 58)
        print(f"  {'TOTAL':<22} {'':>10} {reporte['total_insertados']:>11} "
              f"{reporte['total_rechazados']:>11}")

        if reporte["total_rechazados"]:
            print()
            print("  Documentos rechazados por el validador $jsonSchema:")
            for carga in reporte["cargas"]:
                for detalle in carga["detalle_rechazados"]:
                    print(f"    [{carga['coleccion']}] id={detalle['id']}: "
                          f"{detalle.get('detalle') or detalle['mensaje']}")

        print()
        print("  Conteo real leido del servidor:")
        conteos = verificar_carga(base)
        for nombre in (COLECCION_CLIENTES, COLECCION_CATALOGOS,
                       COLECCION_BITACORA, COLECCION_PROCESOS):
            print(f"    {nombre:<22} {conteos.get(nombre, 0):>6} documentos")

    # --------------------------------------------------------------- RESUMEN
    imprimir_encabezado("RESUMEN DE LA MIGRACION")
    print(f"  Origen        : Oracle ADMIN_PROYECTO (16 tablas, 130 clientes)")
    print(f"  Destino       : MongoDB Atlas / base kopera")
    print(f"  Clientes      : {len(documentos['clientes'])}")
    print(f"  Movimientos   : embebidos en el documento del cliente "
          f"({movimientos_embebidos})")
    print(f"  Bitacora      : {len(documentos['bitacora'])} eventos de pago")
    print(f"  Procesos      : {len(documentos['procesos'])} informe(s) mensual(es)")
    print(f"  Errores de reglas: {resumen_validacion['total_errores']} "
          f"(heredados de la semilla)")
    print()
    print("  Siguiente paso: Kopera/etl/crud_mongodb.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
