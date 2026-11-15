"""
Extraccion de datos desde Oracle para la migracion a MongoDB Atlas (EVAL 3).

Este modulo SOLO LEE de Oracle. No transforma nada: devuelve estructuras
planas (listas de diccionarios) con los datos tal cual estan en la base. El
ensamblado del documento por cliente y las reglas de negocio viven en
02_transformacion.py.

Puntos de diseno importantes:

1. EXTRACCION SET-BASED. No hay cursores ni loops sobre filas: cada consulta
   trae el conjunto completo. Es la misma distincion que se hizo en la
   Evaluacion 2 (cursor explicito para formatear vs. GROUP BY para agregar).

2. LA LOGICA DE NEGOCIO SIGUE EN ORACLE. Los valores derivados (saldo
   pendiente, porcentaje pagado, clasificacion, conteo de cuotas por estado,
   porcentaje de rescate, aporte a la SBIF, dias de atraso) se obtienen
   llamando a las FUNCIONES del package pk_analisis_kopera y a los triggers,
   no recalculandolos en Python. Python no duplica reglas: las consume.

   Como las funciones son escalares, se invocan dentro de la propia consulta
   (una llamada por cliente, no un round-trip por cliente). Por eso el
   analisis completo de los 130 clientes se obtiene en una sola consulta.

3. ESTADOS DE CUOTA. El estado (PAGADA / PARCIAL / VENCIDA / PENDIENTE) no
   existe como columna: es un CASE en el package pk_analisis_kopera. Aqui se
   replica el mismo CASE para poder etiquetar cada cuota individual, que es un
   dato a nivel de cuota y no de cliente.

   El CASE usa TRUNC(SYSDATE), igual que fn_cuenta_cuotas del package: una
   cuota que vence HOY todavia no esta vencida. Si se usara SYSDATE (con
   hora), el conteo de cuotas embebidas con estado VENCIDA no coincidiria con
   el bloque analisis.cuotas.vencidas, que viene de fn_cuenta_cuotas.
"""

# Nombre del package con la logica de negocio de la Evaluacion 2
PACKAGE = "pk_analisis_kopera"


# ==========================================================================
# UTILIDADES
# ==========================================================================

def obtener_fecha_corte(cursor):
    """
    Devuelve la fecha de corte del proceso (SYSDATE de la base).

    Se toma UNA vez y se usa en todo el proceso, para que todos los documentos
    compartan la misma referencia temporal.
    """
    cursor.execute("SELECT SYSDATE FROM dual")
    return cursor.fetchone()[0]


def _filas_a_diccionarios(cursor):
    """
    Convierte el resultado de la consulta en lista de diccionarios.

    Oracle devuelve los nombres de columna en MAYUSCULAS (tanto para columnas
    fisicas como para los alias "AS ..."), asi que se normalizan a minuscula
    para que el codice Python use una convencion uniforme (snake_case).
    """
    columnas = [desc[0].lower() for desc in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


# ==========================================================================
# EXTRACCION
# ==========================================================================

def extraer_clientes(cursor):
    """
    Los 130 clientes con su ubicacion, profesion y tipo de contrato resueltos.

    La desnormalizacion geografica (region / provincia / comuna) se hace aqui,
    en la consulta, para que el documento de MongoDB no necesite joins.
    """
    cursor.execute("""
        SELECT cli.nro_cliente,
               cli.numrun,
               cli.dvrun,
               cli.pnombre,
               cli.snombre,
               cli.appaterno,
               cli.apmaterno,
               cli.fecha_nacimiento,
               cli.fecha_inscripcion,
               cli.correo,
               cli.fono_contacto,
               cli.direccion,
               reg.nombre_region,
               pro.nombre_provincia,
               com.nombre_comuna,
               prof.nombre_prof_ofic,
               tc.nombre_tipo_contrato,
               tc.promedio_renta
          FROM cliente cli
          JOIN region reg
            ON reg.cod_region = cli.cod_region
          JOIN provincia pro
            ON pro.cod_region = cli.cod_region
           AND pro.cod_provincia = cli.cod_provincia
          JOIN comuna com
            ON com.cod_region = cli.cod_region
           AND com.cod_provincia = cli.cod_provincia
           AND com.cod_comuna = cli.cod_comuna
          JOIN profesion_oficio prof
            ON prof.cod_prof_ofic = cli.cod_prof_ofic
          JOIN tipo_contrato tc
            ON tc.cod_tipo_contrato = cli.cod_tipo_contrato
         ORDER BY cli.nro_cliente
    """)
    return _filas_a_diccionarios(cursor)


def extraer_analisis_clientes(cursor):
    """
    El analisis financiero por cliente, calculado por el package PL/SQL.

    Cada columna es una llamada a una funcion del package. La clasificacion se
    guarda con el nombre "clasificacion_oracle" porque la transformacion la
    ajusta (clientes sin creditos pasan a OPORTUNIDAD) pero se quiere
    conservar el valor original para trazabilidad.
    """
    cursor.execute(f"""
        SELECT cli.nro_cliente,
               NVL({PACKAGE}.fn_saldo_pendiente(cli.nro_cliente), 0)      AS saldo_pendiente,
               NVL({PACKAGE}.fn_porcentaje_pagado(cli.nro_cliente), 0)    AS porcentaje_pagado,
               NVL({PACKAGE}.fn_total_ahorrado(cli.nro_cliente), 0)       AS total_ahorrado,
               {PACKAGE}.fn_cuenta_cuotas(cli.nro_cliente, 'PAGADA')     AS cuotas_pagadas,
               {PACKAGE}.fn_cuenta_cuotas(cli.nro_cliente, 'PARCIAL')    AS cuotas_parciales,
               {PACKAGE}.fn_cuenta_cuotas(cli.nro_cliente, 'VENCIDA')    AS cuotas_vencidas,
               {PACKAGE}.fn_cuenta_cuotas(cli.nro_cliente, 'PENDIENTE')  AS cuotas_pendientes,
               {PACKAGE}.fn_clasifica_cliente(cli.nro_cliente)           AS clasificacion_oracle
          FROM cliente cli
         ORDER BY cli.nro_cliente
    """)
    return _filas_a_diccionarios(cursor)


def extraer_totales_clientes(cursor):
    """
    Totales de deuda y pago por cliente (agregaciones simples).

    No son reglas de negocio sino sumas de la cartera, por eso se calculan en
    SQL. Se dejan consistentes con fn_porcentaje_pagado, que suma exactamente
    las mismas columnas.
    """
    cursor.execute("""
        SELECT cc.nro_cliente,
               SUM(cuo.valor_cuota)              AS total_deuda,
               SUM(NVL(cuo.monto_pagado, 0))     AS total_pagado,
               SUM(NVL(cuo.saldo_por_pagar, cuo.valor_cuota)) AS total_saldo,
               COUNT(cuo.nro_cuota)              AS total_cuotas
          FROM credito_cliente cc
          JOIN cuota_credito_cliente cuo
            ON cuo.nro_solic_credito = cc.nro_solic_credito
         GROUP BY cc.nro_cliente
    """)
    return {fila["nro_cliente"]: fila for fila in _filas_a_diccionarios(cursor)}


def extraer_creditos(cursor):
    """
    Los 25 creditos de los clientes, con el tipo de credito, la sucursal
    otorgante y el aporte a la SBIF calculado por el package.
    """
    cursor.execute(f"""
        SELECT cc.nro_solic_credito,
               cc.nro_cliente,
               cc.fecha_solic_cred,
               cc.fecha_otorga_cred,
               cc.monto_solicitado,
               cc.monto_credito,
               cc.total_cuotas_credito,
               cc.cod_credito,
               cre.nombre_credito,
               cre.desc_credito,
               cre.tasa_interes_anual,
               cre.nro_maximo_cuotas,
               cc.id_sucursal,
               suc.direccion      AS sucursal_direccion,
               suc.telefono       AS sucursal_telefono,
               reg.nombre_region  AS sucursal_region,
               pro.nombre_provincia AS sucursal_provincia,
               com.nombre_comuna  AS sucursal_comuna,
               {PACKAGE}.fn_aporte_sbif(cc.monto_credito) AS aporte_sbif
          FROM credito_cliente cc
          JOIN credito cre
            ON cre.cod_credito = cc.cod_credito
          JOIN sucursal suc
            ON suc.id_sucursal = cc.id_sucursal
          JOIN region reg
            ON reg.cod_region = suc.cod_region
          JOIN provincia pro
            ON pro.cod_region = suc.cod_region
           AND pro.cod_provincia = suc.cod_provincia
          JOIN comuna com
            ON com.cod_region = suc.cod_region
           AND com.cod_provincia = suc.cod_provincia
           AND com.cod_comuna = suc.cod_comuna
         ORDER BY cc.nro_solic_credito
    """)
    return _filas_a_diccionarios(cursor)


def extraer_cuotas(cursor):
    """
    Las 519 cuotas con su estado y sus dias de atraso.

    El estado replica el CASE del package pk_analisis_kopera. Los dias de
    atraso se obtienen con la funcion fn_dias_atraso del package, para no
    duplicar esa regla.
    """
    cursor.execute(f"""
        SELECT cu.nro_solic_credito,
               cu.nro_cuota,
               cu.fecha_venc_cuota,
               cu.valor_cuota,
               cu.fecha_pago_cuota,
               NVL(cu.monto_pagado, 0) AS monto_pagado,
               NVL(cu.saldo_por_pagar, cu.valor_cuota) AS saldo_por_pagar,
               cu.cod_forma_pago,
               fpa.nombre_forma_pago,
               CASE
                   WHEN NVL(cu.saldo_por_pagar, cu.valor_cuota) = 0 THEN 'PAGADA'
                   WHEN NVL(cu.monto_pagado, 0) > 0                 THEN 'PARCIAL'
                   WHEN cu.fecha_venc_cuota < TRUNC(SYSDATE)       THEN 'VENCIDA'
                   ELSE 'PENDIENTE'
               END AS estado,
               {PACKAGE}.fn_dias_atraso(cu.nro_solic_credito, cu.nro_cuota) AS dias_atraso
          FROM cuota_credito_cliente cu
          LEFT JOIN forma_pago fpa
            ON fpa.cod_forma_pago = cu.cod_forma_pago
         ORDER BY cu.nro_solic_credito, cu.nro_cuota
    """)
    return _filas_a_diccionarios(cursor)


def extraer_inversiones(cursor):
    """
    Los 134 productos de inversion de los clientes, con el catalogo del
    producto y el porcentaje de rescate calculado por el package.
    """
    cursor.execute(f"""
        SELECT pic.nro_solic_prod,
               pic.nro_cliente,
               pic.fecha_solic_prod,
               pic.ahorro_minimo_mensual,
               pic.dia_pago_mensual,
               pic.monto_total_ahorrado,
               pic.cod_prod_inv,
               pi.nombre_prod_inv,
               pi.meses_minimo_ahorro,
               pi.porc_maximo_rescate,
               {PACKAGE}.fn_porc_rescate(pic.nro_solic_prod) AS porc_rescate
          FROM producto_inversion_cliente pic
          JOIN producto_inversion pi
            ON pi.cod_prod_inv = pic.cod_prod_inv
         ORDER BY pic.nro_solic_prod
    """)
    return _filas_a_diccionarios(cursor)


def extraer_movimientos(cursor):
    """
    Los 345 movimientos de ahorro y rescate.

    El signo se calcula aqui para que la regla "ABONO suma, RESCATE resta"
    quede explicita en el documento. El control de que un rescate no exceda el
    saldo lo hace el trigger trg_movimiento_valida en Oracle y se replica en
    la capa de validaciones de Python.
    """
    cursor.execute("""
        SELECT mov.nro_movimiento,
               mov.nro_solic_prod,
               mov.nro_cliente,
               mov.cod_prod_inv,
               mov.fecha_movimiento,
               mov.monto_movimiento,
               mov.cod_tipo_mov,
               tm.nombre_tipo_mov,
               CASE WHEN UPPER(tm.nombre_tipo_mov) = 'ABONO' THEN 1 ELSE -1 END AS signo
          FROM movimiento mov
          JOIN tipo_movimiento tm
            ON tm.cod_tipo_mov = mov.cod_tipo_mov
         ORDER BY mov.nro_solic_prod, mov.fecha_movimiento, mov.nro_movimiento
    """)
    return _filas_a_diccionarios(cursor)


def extraer_catalogos(cursor):
    """
    Los catalogos maestro, que en MongoDB quedan en su propia coleccion para
    no duplicar nombres dentro de cada documento de cliente.
    """
    catalogos = {}

    cursor.execute("""
        SELECT cod_prod_inv, nombre_prod_inv, meses_minimo_ahorro, porc_maximo_rescate
          FROM producto_inversion ORDER BY cod_prod_inv
    """)
    catalogos["productos_inversion"] = _filas_a_diccionarios(cursor)

    cursor.execute("""
        SELECT cod_credito, nombre_credito, desc_credito, tasa_interes_anual, nro_maximo_cuotas
          FROM credito ORDER BY cod_credito
    """)
    catalogos["tipos_credito"] = _filas_a_diccionarios(cursor)

    cursor.execute("SELECT cod_forma_pago, nombre_forma_pago FROM forma_pago ORDER BY 1")
    catalogos["formas_pago"] = _filas_a_diccionarios(cursor)

    cursor.execute("SELECT cod_tipo_mov, nombre_tipo_mov FROM tipo_movimiento ORDER BY 1")
    catalogos["tipos_movimiento"] = _filas_a_diccionarios(cursor)

    cursor.execute("""
        SELECT id_rango, monto_credito_desde, monto_credito_hasta, porc_entrega_sbif
          FROM aporte_a_sbif ORDER BY monto_credito_desde
    """)
    catalogos["aportes_sbif"] = _filas_a_diccionarios(cursor)

    cursor.execute("""
        SELECT cod_prof_ofic, nombre_prof_ofic FROM profesion_oficio ORDER BY 1
    """)
    catalogos["profesiones"] = _filas_a_diccionarios(cursor)

    cursor.execute("""
        SELECT cod_tipo_contrato, nombre_tipo_contrato, promedio_renta
          FROM tipo_contrato ORDER BY 1
    """)
    catalogos["tipos_contrato"] = _filas_a_diccionarios(cursor)

    return catalogos


def extraer_bitacora(cursor):
    """
    Los eventos de auditoria de pagos (BITACORA_PAGO_CUOTA).

    Se enriquecen con el cliente dueno del credito y con el nombre de la forma
    de pago, datos que la tabla de auditoria no guarda.
    """
    cursor.execute("""
        SELECT b.id_bitacora,
               b.nro_solic_credito,
               b.nro_cuota,
               b.fecha_evento,
               b.usuario_evento,
               b.monto_pagado_anterior,
               b.monto_pagado_nuevo,
               b.valor_cuota,
               b.saldo_resultante,
               b.cod_forma_pago,
               cc.nro_cliente,
               fpa.nombre_forma_pago
          FROM bitacora_pago_cuota b
          JOIN credito_cliente cc
            ON cc.nro_solic_credito = b.nro_solic_credito
          LEFT JOIN forma_pago fpa
            ON fpa.cod_forma_pago = b.cod_forma_pago
         ORDER BY b.id_bitacora
    """)
    return _filas_a_diccionarios(cursor)


def extraer_pagos_por_cliente(cursor):
    """
    Historial de pagos por cliente, para incrustarlo en su documento.

    Se arma desde la bitacora (que ya tiene el historial real de cambios) mas
    la cuota asociada, para poder mostrar el estado final de la cuota.
    """
    cursor.execute("""
        SELECT cc.nro_cliente,
               b.nro_solic_credito,
               b.nro_cuota,
               b.fecha_evento,
               b.monto_pagado_anterior,
               b.monto_pagado_nuevo,
               b.saldo_resultante,
               b.cod_forma_pago,
               fpa.nombre_forma_pago,
               cu.fecha_venc_cuota,
               cu.valor_cuota,
               CASE
                   WHEN NVL(cu.saldo_por_pagar, cu.valor_cuota) = 0 THEN 'PAGADA'
                   WHEN NVL(cu.monto_pagado, 0) > 0                 THEN 'PARCIAL'
                   WHEN cu.fecha_venc_cuota < TRUNC(SYSDATE)       THEN 'VENCIDA'
                   ELSE 'PENDIENTE'
               END AS estado_cuota
          FROM bitacora_pago_cuota b
          JOIN credito_cliente cc
            ON cc.nro_solic_credito = b.nro_solic_credito
          JOIN cuota_credito_cliente cu
            ON cu.nro_solic_credito = b.nro_solic_credito
           AND cu.nro_cuota = b.nro_cuota
          LEFT JOIN forma_pago fpa
            ON fpa.cod_forma_pago = b.cod_forma_pago
         ORDER BY cc.nro_cliente, b.fecha_evento, b.id_bitacora
    """)
    return _filas_a_diccionarios(cursor)
