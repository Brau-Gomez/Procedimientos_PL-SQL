"""
Pobla la bitacora de pagos (BITACORA_PAGO_CUOTA) de KOPERA ejecutando el
proceso mensual de cobranza.

La bitacora NO se puebla insertando filas: la escribe el trigger
trg_cuota_bitacora cada vez que el monto pagado de una cuota cambia. Por eso
este script registra los pagos a traves del procedimiento almacenado
sp_registra_pago, que es la via oficial del negocio:

    sp_registra_pago  ->  UPDATE cuota_credito_cliente
                             ->  trg_cuota_valida_pago  (BEFORE: valida y deriva saldo)
                             ->  trg_cuota_bitacora     (AFTER:  inserta la fila de auditoria)

Como el INSERT del trigger ocurre en la misma transaccion que el UPDATE, el
lote se confirma con un unico COMMIT al final: el proceso de cobranza mensual
se confirma como una unidad atomica. Si algo falla, no queda nada a medias.

El plan de pagos vive en plan_pagos.py y se puede editar sin tocar este codigo.
El script es idempotente: al reejecutarse omite lo que ya esta pagado y lo
informa en el reporte.

Uso:
    .venv/bin/python Kopera/scripts/poblar_bitacora.py --simular
    .venv/bin/python Kopera/scripts/poblar_bitacora.py
"""

import argparse
from datetime import datetime

import oracledb

from config import conectar_oracle
from plan_pagos import FORMAS_PAGO, PLAN_PAGOS

# Ancho de la cadena para los mensajes OUT de sp_registra_pago.
# El parametro p_mensaje es VARCHAR2 sin longitud fija: si el bind no declara
# tamano, Oracle responde ORA-06502 (character string buffer too small).
TAMANO_MENSAJE = 300


def obtener_formas_pago(cursor):
    """Lee los nombres de las formas de pago desde FORMA_PAGO (fuente unica)."""
    cursor.execute("SELECT cod_forma_pago, nombre_forma_pago FROM forma_pago ORDER BY 1")
    return {codigo: nombre for codigo, nombre in cursor.fetchall()}


def leer_estado_cuota(cursor, credito, cuota):
    """
    Devuelve el estado actual de una cuota:
    (valor_cuota, monto_pagado, saldo_por_pagar, fecha_pago, cliente_dueno)
    o None si la cuota no existe.
    """
    cursor.execute("""
        SELECT cu.valor_cuota,
               NVL(cu.monto_pagado, 0),
               NVL(cu.saldo_por_pagar, cu.valor_cuota),
               TO_CHAR(cu.fecha_pago_cuota, 'DD/MM/YYYY'),
               cc.nro_cliente
          FROM cuota_credito_cliente cu
          JOIN credito_cliente cc
            ON cc.nro_solic_credito = cu.nro_solic_credito
         WHERE cu.nro_solic_credito = :1
           AND cu.nro_cuota = :2
    """, [credito, cuota])
    return cursor.fetchone()


def validar_plan(cursor):
    """
    Revisa el plan contra el estado real de la base antes de tocar nada.

    Devuelve (problemas, avisos). Un problema invalida el lote: el script
    aborta sin ejecutar ni un pago. Un aviso solo se informa.
    """
    problemas = []
    avisos = []

    for evento in PLAN_PAGOS:
        credito = evento["nro_solic_credito"]
        cuota = evento["nro_cuota"]
        objetivo = evento["monto_objetivo"]

        if evento["cod_forma_pago"] not in FORMAS_PAGO:
            problemas.append(
                f"Credito {credito} cuota {cuota}: forma de pago "
                f"{evento['cod_forma_pago']} no existe en FORMA_PAGO"
            )
            continue

        estado = leer_estado_cuota(cursor, credito, cuota)
        if estado is None:
            problemas.append(
                f"Credito {credito} cuota {cuota}: la cuota no existe"
            )
            continue

        valor_cuota, monto_pagado, _, _, cliente_real = estado

        if cliente_real != evento["nro_cliente"]:
            problemas.append(
                f"Credito {credito} cuota {cuota}: el plan dice cliente "
                f"{evento['nro_cliente']} pero la cuota pertenece al "
                f"cliente {cliente_real}"
            )

        if objetivo > valor_cuota:
            problemas.append(
                f"Credito {credito} cuota {cuota}: el objetivo "
                f"({objetivo}) supera el valor de la cuota ({valor_cuota}); "
                f"el trigger trg_cuota_valida_pago lo rechazaria"
            )

        if monto_pagado > objetivo:
            avisos.append(
                f"Credito {credito} cuota {cuota}: ya esta pagada con "
                f"{monto_pagado} (supera el objetivo {objetivo}); se omitira"
            )

    return problemas, avisos


def registrar_pago(cursor, credito, cuota, monto, forma_pago):
    """
    Invoca sp_registra_pago y devuelve (mensaje, saldo_nuevo).

    Los parametros OUT deben ser binds tipados: mensaje como str con tamano
    declarado y saldo como int. Ademas, el procedimiento captura sus propias
    excepciones de negocio y las devuelve en p_mensaje, por lo que NO hay que
    esperar una excepcion: hay que leer el mensaje.
    """
    var_mensaje = cursor.var(str, TAMANO_MENSAJE)
    var_saldo = cursor.var(int)

    cursor.callproc(
        "sp_registra_pago",
        [credito, cuota, monto, forma_pago, var_mensaje, var_saldo],
    )

    return var_mensaje.getvalue(), var_saldo.getvalue()


def ejecutar_lote(cursor, simular):
    """
    Recorre el plan y aplica los pagos.

    Devuelve (resultados, omitidos, error). Si error no es None, el lote se
    considera fallido y el llamador hace rollback.
    """
    resultados = []
    omitidos = []
    error = None

    # Estado acumulado en memoria. En simulacion no se toca la base, asi que
    # este diccionario es lo que permite calcular bien el delta de un pago en
    # dos partes (el segundo evento ve lo que "pago" el primero).
    acumulado_simulado = {}

    for numero, evento in enumerate(PLAN_PAGOS, start=1):
        credito = evento["nro_solic_credito"]
        cuota = evento["nro_cuota"]
        objetivo = evento["monto_objetivo"]
        forma = evento["cod_forma_pago"]
        clave = (credito, cuota)

        estado = leer_estado_cuota(cursor, credito, cuota)
        if estado is None:
            error = f"Credito {credito} cuota {cuota}: la cuota no existe"
            break

        monto_pagado, _, fecha_pago, _ = estado

        # En simulacion manda el estado acumulado en memoria, no el de la base.
        if simular and clave in acumulado_simulado:
            monto_pagado = acumulado_simulado[clave]

        # Idempotencia: si el pago acumulado ya cubre el objetivo, no hay nada
        # que hacer. Se informa y se sigue.
        if monto_pagado >= objetivo:
            omitidos.append({
                "numero": numero,
                "credito": credito,
                "cuota": cuota,
                "cliente": evento["nro_cliente"],
                "forma": forma,
                "objetivo": objetivo,
                "motivo": f"ya pagada ({monto_pagado} >= {objetivo})",
            })
            continue

        delta = objetivo - monto_pagado

        if simular:
            acumulado_simulado[clave] = objetivo
            resultados.append({
                "numero": numero,
                "credito": credito,
                "cuota": cuota,
                "cliente": evento["nro_cliente"],
                "forma": forma,
                "concepto": evento["concepto"],
                "objetivo": objetivo,
                "delta": delta,
                "estado": "SIMULADO",
                "mensaje": "(simulacion: no se ejecuto el pago)",
            })
            continue

        mensaje, saldo_nuevo = registrar_pago(cursor, credito, cuota, delta, forma)

        # El procedimiento devuelve el error como texto. Si empieza con
        # "ERROR", el pago no se aplico.
        if mensaje and mensaje.upper().startswith("ERROR"):
            error = f"Credito {credito} cuota {cuota}: {mensaje}"
            break

        # Se relee la cuota para confirmar que el UPDATE se aplico de verdad.
        estado_final = leer_estado_cuota(cursor, credito, cuota)
        if estado_final is None:
            error = f"Credito {credito} cuota {cuota}: la cuota desaparecio tras el pago"
            break

        _, pagado_final, saldo_final, fecha_pago_final, _ = estado_final

        resultados.append({
            "numero": numero,
            "credito": credito,
            "cuota": cuota,
            "cliente": evento["nro_cliente"],
            "forma": forma,
            "concepto": evento["concepto"],
            "objetivo": objetivo,
            "delta": delta,
            "estado": "APLICADO",
            "mensaje": mensaje,
            "saldo_nuevo": saldo_final if saldo_final is not None else saldo_nuevo,
            "pagado_acumulado": pagado_final,
            "fecha_pago": fecha_pago_final or fecha_pago,
        })

    return resultados, omitidos, error


def contar_bitacora(cursor):
    """Devuelve la cantidad de filas de la bitacora."""
    cursor.execute("SELECT COUNT(*) FROM bitacora_pago_cuota")
    return cursor.fetchone()[0]


def imprimir_reporte(resultados, omitidos, formas):
    """Imprime el detalle evento por evento."""
    print()
    print("--- Detalle de eventos ---")
    encabezado = (
        f"{'#':>3}  {'credito':>7}  {'cuota':>5}  {'cli':>4}  "
        f"{'forma':<22}  {'objetivo':>10}  {'delta':>10}  {'estado':<9}"
    )
    print(encabezado)
    print("-" * len(encabezado))

    for r in resultados:
        nombre_forma = formas.get(r["forma"], str(r["forma"]))
        print(
            f"{r['numero']:>3}  {r['credito']:>7}  {r['cuota']:>5}  "
            f"{r['cliente']:>4}  {nombre_forma:<22}  "
            f"{r['objetivo']:>10,}  {r['delta']:>10,}  {r['estado']:<9}"
        )

    for o in omitidos:
        nombre_forma = formas.get(o["forma"], str(o["forma"]))
        print(
            f"{o['numero']:>3}  {o['credito']:>7}  {o['cuota']:>5}  "
            f"{o['cliente']:>4}  {nombre_forma:<22}  "
            f"{o['objetivo']:>10,}  {'-':>10}  {'OMITIDO':<9}  ({o['motivo']})"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Pobla la bitacora de pagos de KOPERA con el proceso mensual de cobranza."
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Muestra lo que se haria sin modificar nada (ensayo en seco).",
    )
    args = parser.parse_args()

    modo = "SIMULACION (no se modifica nada)" if args.simular else "EJECUCION REAL"

    print("=" * 78)
    print("  KOPERA - Proceso mensual de cobranza / Bitacora de pagos")
    print("=" * 78)
    print(f"  Modo            : {modo}")
    print(f"  Fecha de proceso: {datetime.now():%d/%m/%Y %H:%M}")
    print(f"  Plan cargado    : {len(PLAN_PAGOS)} eventos")

    clientes = {e["nro_cliente"] for e in PLAN_PAGOS}
    creditos = {e["nro_solic_credito"] for e in PLAN_PAGOS}
    print(f"  Alcance         : {len(clientes)} clientes, {len(creditos)} creditos")
    print()

    try:
        with conectar_oracle() as conexion:
            with conexion.cursor() as cursor:
                formas = obtener_formas_pago(cursor)

                print("--- Validacion del plan contra la base ---")
                problemas, avisos = validar_plan(cursor)

                for aviso in avisos:
                    print(f"  [AVISO]  {aviso}")

                if problemas:
                    for problema in problemas:
                        print(f"  [ERROR]  {problema}")
                    print()
                    print("El plan tiene errores. No se ejecuto ningun pago.")
                    raise SystemExit(1)

                print(f"  [OK]     {len(PLAN_PAGOS)} eventos validados, sin inconsistencias")
                print()

                filas_antes = contar_bitacora(cursor)
                print(f"  Filas en BITACORA_PAGO_CUOTA antes del lote: {filas_antes}")
                print()

                resultados, omitidos, error = ejecutar_lote(cursor, args.simular)

                if error:
                    print()
                    print(f"  [ERROR]  {error}")
                    print("  Se revierte todo el lote (rollback). Nada queda confirmado.")
                    conexion.rollback()
                    raise SystemExit(1)

                imprimir_reporte(resultados, omitidos, formas, args.simular)

                total_pagado = sum(r["delta"] for r in resultados)
                print()
                print(f"  Eventos aplicados : {len(resultados)}")
                print(f"  Eventos omitidos  : {len(omitidos)}")
                print(f"  Monto pagado      : ${total_pagado:,}")

                if args.simular:
                    print()
                    print("  Modo simulacion: no se confirmo nada. Usa --simular=False para ejecutar.")
                    conexion.rollback()
                    return

                # El lote se confirma como una unidad: un unico COMMIT.
                conexion.commit()
                print()
                print("  COMMIT ejecutado: el lote completo quedo confirmado.")

                # Verificacion desde una conexion nueva: demuestra que los datos
                # quedaron persistidos y no solo visibles en la transaccion.
                with conectar_oracle() as conexion_verificacion:
                    with conexion_verificacion.cursor() as cursor_v:
                        filas_despues = contar_bitacora(cursor_v)
                        print(f"  Filas en BITACORA_PAGO_CUOTA despues (nueva conexion): {filas_despues}")
                        print(f"  Eventos generados por este lote: {filas_despues - filas_antes}")

                        if filas_despues - filas_antes != len(resultados):
                            print("  [AVISO]  La cantidad de eventos en la bitacora no coincide")
                            print("            con la cantidad de pagos aplicados.")

    except SystemExit:
        raise
    except oracledb.DatabaseError as e:
        print(f"\nError de base de datos: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"\nError inesperado: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
