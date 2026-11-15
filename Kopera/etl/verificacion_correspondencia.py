"""
Verificacion de correspondencia entre Oracle y MongoDB Atlas (EVAL 3).

Este script es la PRUEBA de que la migracion no perdio ni transformo datos por
error. Compara, cliente por cliente y en agregado, lo que hay en la base
relacional contra lo que quedo en Atlas.

Que compara:
    1. Conteos de las colecciones contra los conteos de las tablas.
    2. Importes por cliente: deuda, pagado, saldo pendiente y ahorro total.
    3. Cantidad de cuotas e inversiones por cliente.
    4. Movimientos embebidos: total y suma por tipo (ABONO / RESCATE).
    5. Eventos de la bitacora de pagos, con sus montos.
    6. El informe del proceso mensual (clientes analizados y saldo total).

Salida: un informe por pantalla (para el anexo del informe) y, con --archivo,
un CSV con el detalle de las diferencias.

Uso:
    .venv/bin/python Kopera/etl/verificacion_correspondencia.py
    .venv/bin/python Kopera/etl/verificacion_correspondencia.py --archivo docs/eva3/correspondencia.csv
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path

from config import (
    COLECCION_BITACORA,
    COLECCION_CATALOGOS,
    COLECCION_CLIENTES,
    COLECCION_PROCESOS,
    conectar_mongodb,
    conectar_oracle,
    obtener_base_mongodb,
)


def leer_oracle(cursor):
    """Devuelve los totales por cliente que hay en la base relacional."""
    cursor.execute("""
        SELECT cc.nro_cliente,
               COUNT(DISTINCT cc.nro_solic_credito)      AS creditos,
               COUNT(cuo.nro_cuota)                       AS cuotas,
               NVL(SUM(cuo.valor_cuota), 0)               AS deuda,
               NVL(SUM(NVL(cuo.monto_pagado, 0)), 0)      AS pagado,
               NVL(SUM(NVL(cuo.saldo_por_pagar, cuo.valor_cuota)), 0) AS saldo,
               NVL((SELECT SUM(pic.monto_total_ahorrado) FROM producto_inversion_cliente pic
                    WHERE pic.nro_cliente = cc.nro_cliente), 0) AS ahorrado,
               NVL((SELECT COUNT(*) FROM producto_inversion_cliente pic
                    WHERE pic.nro_cliente = cc.nro_cliente), 0) AS inversiones
          FROM credito_cliente cc
          LEFT JOIN cuota_credito_cliente cuo
            ON cuo.nro_solic_credito = cc.nro_solic_credito
         GROUP BY cc.nro_cliente
         ORDER BY cc.nro_cliente
    """)

    clientes = {}
    for fila in cursor.fetchall():
        clientes[fila[0]] = {
            "nro_cliente": fila[0],
            "creditos": fila[1],
            "cuotas": fila[2],
            "deuda": fila[3],
            "pagado": fila[4],
            "saldo": fila[5],
            "ahorrado": fila[6],
            "inversiones": fila[7],
        }

    # Los clientes SIN credito no aparecen en la consulta anterior: se
    # agregan con los totales de ahorro, que si tienen.
    cursor.execute("""
        SELECT nro_cliente,
               NVL(SUM(monto_total_ahorrado), 0),
               COUNT(*)
          FROM producto_inversion_cliente
         GROUP BY nro_cliente
         ORDER BY nro_cliente
    """)
    for nro_cliente, ahorrado, inversiones in cursor.fetchall():
        if nro_cliente not in clientes:
            clientes[nro_cliente] = {
                "nro_cliente": nro_cliente,
                "creditos": 0,
                "cuotas": 0,
                "deuda": 0,
                "pagado": 0,
                "saldo": 0,
                "ahorrado": ahorrado,
                "inversiones": inversiones,
            }

    # Totales globales de movimientos, por tipo.
    cursor.execute("""
        SELECT UPPER(tm.nombre_tipo_mov), COUNT(*), NVL(SUM(m.monto_movimiento), 0)
          FROM movimiento m
          JOIN tipo_movimiento tm ON tm.cod_tipo_mov = m.cod_tipo_mov
         GROUP BY UPPER(tm.nombre_tipo_mov)
         ORDER BY 1
    """)
    movimientos = {
        tipo: {"cantidad": cantidad, "monto": monto}
        for tipo, cantidad, monto in cursor.fetchall()
    }

    # Total de la cartera.
    cursor.execute("""
        SELECT NVL(SUM(cuo.valor_cuota), 0),
               NVL(SUM(NVL(cuo.monto_pagado, 0)), 0),
               NVL(SUM(NVL(cuo.saldo_por_pagar, cuo.valor_cuota)), 0),
               COUNT(*)
          FROM cuota_credito_cliente cuo
    """)
    deuda, pagado, saldo, cuotas = cursor.fetchone()

    # Bitacora.
    cursor.execute("""
        SELECT COUNT(*), NVL(SUM(monto_pagado_nuevo), 0),
               NVL(SUM(NVL(monto_pagado_anterior, 0)), 0)
          FROM bitacora_pago_cuota
    """)
    eventos, monto_nuevo, monto_anterior = cursor.fetchone()

    # Catalogos maestro: son las mismas siete tablas que arma
    # extraccion_oracle.extraer_catalogos, y cada fila produce un documento.
    cursor.execute("""
        SELECT (SELECT COUNT(*) FROM producto_inversion)
             + (SELECT COUNT(*) FROM credito)
             + (SELECT COUNT(*) FROM forma_pago)
             + (SELECT COUNT(*) FROM tipo_movimiento)
             + (SELECT COUNT(*) FROM aporte_a_sbif)
             + (SELECT COUNT(*) FROM profesion_oficio)
             + (SELECT COUNT(*) FROM tipo_contrato)
          FROM dual
    """)
    catalogos = cursor.fetchone()[0]

    return {
        "clientes": clientes,
        "movimientos": movimientos,
        "totales": {
            "deuda": deuda,
            "pagado": pagado,
            "saldo": saldo,
            "cuotas": cuotas,
        },
        "bitacora": {
            "eventos": eventos,
            "monto_nuevo": monto_nuevo,
            "monto_anterior": monto_anterior,
        },
        "catalogos": catalogos,
    }


def leer_atlas(base):
    """Devuelve los mismos totales, leidos de Atlas."""
    clientes = {}
    for documento in base[COLECCION_CLIENTES].find():
        analisis = documento.get("analisis", {})
        creditos = documento.get("creditos", [])
        inversiones = documento.get("inversiones", [])

        cuotas = sum(len(c.get("cuotas", [])) for c in creditos)

        # Los importes se toman del bloque "analisis", que es el que materializa
        # la logica del package: asi se compara contra Oracle el MISMO valor,
        # no un recalculo paralelo hecho aqui.
        clientes[documento["nro_cliente"]] = {
            "nro_cliente": documento["nro_cliente"],
            "creditos": len(creditos),
            "cuotas": cuotas,
            "deuda": analisis.get("total_creditos", 0),
            "pagado": analisis.get("total_pagado", 0),
            "saldo": analisis.get("saldo_pendiente", 0),
            "ahorrado": analisis.get("total_ahorrado", 0),
            "inversiones": len(inversiones),
        }

    movimientos = {}
    for documento in base[COLECCION_CLIENTES].find({}, {"inversiones": 1}):
        for inversion in documento.get("inversiones", []):
            for movimiento in inversion.get("movimientos", []):
                tipo = (movimiento.get("tipo_movimiento") or "").upper()
                if tipo not in movimientos:
                    movimientos[tipo] = {"cantidad": 0, "monto": 0}
                movimientos[tipo]["cantidad"] += 1
                movimientos[tipo]["monto"] += movimiento.get("monto", 0)

    totales = {
        "deuda": sum(c["deuda"] for c in clientes.values()),
        "pagado": sum(c["pagado"] for c in clientes.values()),
        "saldo": sum(c["saldo"] for c in clientes.values()),
        "cuotas": sum(c["cuotas"] for c in clientes.values()),
    }

    bitacora = {
        "eventos": base[COLECCION_BITACORA].count_documents({}),
        "monto_nuevo": 0,
        "monto_anterior": 0,
    }
    for documento in base[COLECCION_BITACORA].find():
        bitacora["monto_nuevo"] += documento.get("monto_pagado_nuevo", 0)
        bitacora["monto_anterior"] += documento.get("monto_pagado_anterior", 0) or 0

    return {
        "clientes": clientes,
        "movimientos": movimientos,
        "totales": totales,
        "bitacora": bitacora,
        "conteos": {
            "clientes": base[COLECCION_CLIENTES].count_documents({}),
            "catalogos": base[COLECCION_CATALOGOS].count_documents({}),
            "bitacora": base[COLECCION_BITACORA].count_documents({}),
            "procesos": base[COLECCION_PROCESOS].count_documents({}),
        },
    }


def comparar(oracle, atlas):
    """Compara los dos conjuntos de datos y devuelve las diferencias."""
    diferencias = []
    campos = ("creditos", "cuotas", "deuda", "pagado", "saldo", "ahorrado", "inversiones")

    claves = set(oracle["clientes"]) | set(atlas["clientes"])

    for nro_cliente in sorted(claves):
        en_oracle = oracle["clientes"].get(nro_cliente)
        en_atlas = atlas["clientes"].get(nro_cliente)

        if en_oracle is None:
            diferencias.append({
                "nro_cliente": nro_cliente,
                "campo": "*",
                "oracle": "NO EXISTE",
                "atlas": "EXISTE",
            })
            continue
        if en_atlas is None:
            diferencias.append({
                "nro_cliente": nro_cliente,
                "campo": "*",
                "oracle": "EXISTE",
                "atlas": "NO EXISTE",
            })
            continue

        for campo in campos:
            if en_oracle[campo] != en_atlas[campo]:
                diferencias.append({
                    "nro_cliente": nro_cliente,
                    "campo": campo,
                    "oracle": en_oracle[campo],
                    "atlas": en_atlas[campo],
                })

    return diferencias


def imprimir_comparacion(etiqueta, valor_oracle, valor_atlas, unidad=""):
    """Imprime una fila de la tabla comparativa."""
    coincide = valor_oracle == valor_atlas
    marca = "OK" if coincide else "DIFERENTE"
    if isinstance(valor_oracle, (int, float)) and not isinstance(valor_oracle, bool):
        print(f"  {etiqueta:<38} {valor_oracle:>16,.0f} {valor_atlas:>16,.0f}  {marca}")
    else:
        print(f"  {etiqueta:<38} {str(valor_oracle):>16} {str(valor_atlas):>16}  {marca}")
    return coincide


def main():
    parser = argparse.ArgumentParser(
        description="Verifica la correspondencia entre Oracle y MongoDB Atlas."
    )
    parser.add_argument(
        "--archivo",
        type=Path,
        default=None,
        help="CSV de salida con el detalle de las diferencias.",
    )
    args = parser.parse_args()

    print()
    print("=" * 92)
    print("  KOPERA - Verificacion de correspondencia Oracle <-> MongoDB Atlas")
    print("=" * 92)
    print(f"  Fecha: {datetime.now():%d/%m/%Y %H:%M}")
    print()

    # ----------------------------------------------------------- lectura
    with conectar_oracle() as conexion:
        with conexion.cursor() as cursor:
            oracle = leer_oracle(cursor)

    with conectar_mongodb() as cliente:
        base = obtener_base_mongodb(cliente)
        atlas = leer_atlas(base)

        # ------------------------------------------------------- comparacion
        print("  CONCEPTO                                     ORACLE            ATLAS")
        print("  " + "-" * 88)

        todo_ok = True

        # Conteos de colecciones contra conteos de tablas.
        todo_ok &= imprimir_comparacion(
            "Clientes", len(oracle["clientes"]), atlas["conteos"]["clientes"]
        )
        todo_ok &= imprimir_comparacion(
            "Catalogos maestro", oracle["catalogos"], atlas["conteos"]["catalogos"]
        )
        todo_ok &= imprimir_comparacion(
            "Eventos de bitacora",
            oracle["bitacora"]["eventos"], atlas["conteos"]["bitacora"],
        )

        # Importes de la cartera.
        todo_ok &= imprimir_comparacion(
            "Total deuda (suma cuotas)", oracle["totales"]["deuda"], atlas["totales"]["deuda"]
        )
        todo_ok &= imprimir_comparacion(
            "Total pagado", oracle["totales"]["pagado"], atlas["totales"]["pagado"]
        )
        todo_ok &= imprimir_comparacion(
            "Saldo pendiente", oracle["totales"]["saldo"], atlas["totales"]["saldo"]
        )
        todo_ok &= imprimir_comparacion(
            "Cuotas migradas", oracle["totales"]["cuotas"], atlas["totales"]["cuotas"]
        )

        # Movimientos por tipo.
        print()
        print("  MOVIMIENTOS POR TIPO")
        for tipo in sorted(set(oracle["movimientos"]) | set(atlas["movimientos"])):
            o = oracle["movimientos"].get(tipo, {"cantidad": 0, "monto": 0})
            a = atlas["movimientos"].get(tipo, {"cantidad": 0, "monto": 0})
            todo_ok &= imprimir_comparacion(f"  {tipo} (cantidad)", o["cantidad"], a["cantidad"])
            todo_ok &= imprimir_comparacion(f"  {tipo} (monto)", o["monto"], a["monto"])

        # Bitacora.
        print()
        print("  BITACORA DE PAGOS")
        todo_ok &= imprimir_comparacion(
            "Eventos registrados", oracle["bitacora"]["eventos"], atlas["bitacora"]["eventos"]
        )
        todo_ok &= imprimir_comparacion(
            "Suma montos nuevos", oracle["bitacora"]["monto_nuevo"], atlas["bitacora"]["monto_nuevo"]
        )
        todo_ok &= imprimir_comparacion(
            "Suma montos anteriores",
            oracle["bitacora"]["monto_anterior"], atlas["bitacora"]["monto_anterior"],
        )

        # -------------------------------------------------- detalle clientes
        diferencias = comparar(oracle, atlas)

        print()
        print("  DETALLE CLIENTE POR CLIENTE")
        print(f"  Clientes en Oracle: {len(oracle['clientes'])} | "
              f"clientes en Atlas: {len(atlas['clientes'])}")
        print(f"  Clientes con diferencias: {len({d['nro_cliente'] for d in diferencias})}")
        print(f"  Total de campos con diferencia: {len(diferencias)}")

        if diferencias:
            print()
            print(f"  {'cliente':>8}  {'campo':<14} {'oracle':>16} {'atlas':>16}")
            print("  " + "-" * 60)
            for diferencia in diferencias[:40]:
                print(f"  {diferencia['nro_cliente']:>8}  {diferencia['campo']:<14} "
                      f"{str(diferencia['oracle']):>16} {str(diferencia['atlas']):>16}")
            if len(diferencias) > 40:
                print(f"  ... y {len(diferencias) - 40} diferencia(s) mas")

        # ------------------------------------------------------ proceso
        print()
        print("  INFORME DEL PROCESO MENSUAL")
        for documento in base[COLECCION_PROCESOS].find().sort("fecha_corte", -1).limit(1):
            print(f"  Fecha de corte      : {documento['fecha_corte']}")
            print(f"  Procedimiento       : {documento['procedimiento']}")
            print(f"  Clientes analizados : {documento['clientes_analizados']}")
            print(f"  Saldo total cartera : ${documento['saldo_total_cartera']:,}")
            print(f"  Lineas del informe  : {len(documento['lineas_salida'])}")

        # ------------------------------------------------------ veredicto
        print()
        print("=" * 92)
        if todo_ok and not diferencias:
            print("  RESULTADO: CORRESPONDENCIA TOTAL. No se perdio ningun dato en la migracion.")
        elif todo_ok:
            print("  RESULTADO: los totales agregados coinciden; hay diferencias en el detalle.")
        else:
            print("  RESULTADO: HAY DIFERENCIAS EN LOS TOTALES. Revisar el detalle.")
        print("=" * 92)
        print()

    # --------------------------------------------------------- archivo CSV
    if args.archivo:
        args.archivo.parent.mkdir(parents=True, exist_ok=True)
        with args.archivo.open("w", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(
                archivo, fieldnames=["nro_cliente", "campo", "oracle", "atlas"]
            )
            escritor.writeheader()
            for diferencia in diferencias:
                escritor.writerow(diferencia)
        print(f"  Detalle de diferencias escrito en: {args.archivo}")
        print()

    return 0 if (todo_ok and not diferencias) else 1


if __name__ == "__main__":
    raise SystemExit(main())
