/* ================================================================
   PROYECTO KOPERA - EVALUACIÓN PARCIAL 2 (BDY1103)
   Script  : 02_procedimientos.sql
   --------------------------------------------------------------
   Propósito: implementar PROCEDIMIENTOS ALMACENADOS con y sin
   parámetros que procesen la información masiva de la cartera de
   créditos de KOPERA, y que puedan ser invocados desde otros
   programas PL/SQL y desde sentencias SQL (CALL / EXECUTE).
   ================================================================ */

SET SERVEROUTPUT ON;

/* ----------------------------------------------------------------
   LIMPIEZA PREVIA
   Permite ejecutar el script varias veces. En la primera ejecución
   los objetos no existen, por lo que el DROP falla; ese error se
   controla con la excepción OTHERS (repaso de la Eva 1).
   ---------------------------------------------------------------- */
BEGIN
    EXECUTE IMMEDIATE 'DROP PROCEDURE sp_reporte_cartera';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -4043 THEN RAISE; END IF; -- solo se ignora objeto inexistente
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP PROCEDURE sp_registra_pago';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -4043 THEN RAISE; END IF; -- solo se ignora objeto inexistente
END;
/

/* ================================================================
   1) sp_reporte_cartera  --  PROCEDIMIENTO SIN PARÁMETROS
   --------------------------------------------------------------
   Qué hace:
     Ejecuta el "proceso mensual" del caso de negocio: recorre TODA
     la cartera de clientes con créditos (procesamiento masivo) y
     entrega el informe consolidado por cliente:
       - monto total de sus créditos (sumatoria de las cuotas)
       - total pagado hasta la fecha
       - saldo pendiente
       - porcentaje pagado de la deuda

   Cómo lo hace:
     - La agregación la resuelve el motor con JOIN + GROUP BY
       (operación de conjuntos, no fila a fila).
     - El cursor explícito solo se usa para recorrer el resultado
       y dar formato al informe (repite el patrón de la Eva 1).
     - Un RECORD guarda la fila consolidada de cada cliente.

   Cómo se usa:
     - Sentencia SQL   : CALL sp_reporte_cartera();
     - Otro programa   : dentro de un bloque PL/SQL o EXECUTE.
   ================================================================ */
CREATE OR REPLACE PROCEDURE sp_reporte_cartera AS

    -- RECORD consolidado por cliente (tipo compuesto, Eva 1)
    TYPE t_reg_cliente IS RECORD (
        nro_cliente       cliente.nro_cliente%TYPE,
        nombre            VARCHAR2(120),
        total_cuotas      NUMBER,   -- total a pagar (suma de cuotas)
        total_pagado      NUMBER,   -- lo efectivamente pagado
        saldo_pendiente   NUMBER    -- lo que falta por pagar
    );
    r_cliente t_reg_cliente;

    -- Cursor explícito sobre TODA la cartera (información masiva).
    -- Las cuotas sin pago tienen monto_pagado y saldo_por_pagar en
    -- NULL, por eso se usa NVL para tratarlas como "pendientes".
    CURSOR c_cartera IS
        SELECT cli.nro_cliente,
               cli.pnombre || ' ' || cli.appaterno          AS nombre,
               SUM(cuo.valor_cuota)                         AS total_cuotas,
               SUM(NVL(cuo.monto_pagado, 0))                AS total_pagado,
               SUM(NVL(cuo.saldo_por_pagar, cuo.valor_cuota)) AS saldo_pendiente
          FROM cliente cli
          JOIN credito_cliente cre
                 ON cre.nro_cliente = cli.nro_cliente
          JOIN cuota_credito_cliente cuo
                 ON cuo.nro_solic_credito = cre.nro_solic_credito
      GROUP BY cli.nro_cliente, cli.pnombre, cli.appaterno
      ORDER BY cli.nro_cliente;

    v_porc_pagado   NUMBER(5,1);
    v_saldo_cartera NUMBER := 0;
    v_clientes      PLS_INTEGER := 0;   -- contador propio de clientes

    -- Excepción definida por el usuario (Eva 1)
    e_cartera_vacia EXCEPTION;

BEGIN
    DBMS_OUTPUT.PUT_LINE('==================================================');
    DBMS_OUTPUT.PUT_LINE('  INFORME MENSUAL DE CARTERA KOPERA');
    DBMS_OUTPUT.PUT_LINE('  Fecha del proceso: '
                        || TO_CHAR(SYSDATE, 'DD/MM/YYYY'));
    DBMS_OUTPUT.PUT_LINE('==================================================');
    DBMS_OUTPUT.PUT_LINE(RPAD('NRO', 5)
        || RPAD('CLIENTE', 28)
        || RPAD('TOTAL DEUDA', 15)
        || RPAD('PAGADO', 15)
        || RPAD('SALDO', 15)
        || 'PAGADO %');
    DBMS_OUTPUT.PUT_LINE('--------------------------------------------------');

    OPEN c_cartera;
    LOOP
        FETCH c_cartera INTO r_cliente;
        EXIT WHEN c_cartera%NOTFOUND;

        -- Evita división por cero si la deuda fuera 0
        IF r_cliente.total_cuotas > 0 THEN
            v_porc_pagado := ROUND(
                r_cliente.total_pagado
                / r_cliente.total_cuotas * 100, 1);
        ELSE
            v_porc_pagado := 0;
        END IF;

        DBMS_OUTPUT.PUT_LINE(
              RPAD(r_cliente.nro_cliente, 5)
            || RPAD(r_cliente.nombre, 28)
            || RPAD(TO_CHAR(r_cliente.total_cuotas, 'FM$999,999,999'), 15)
            || RPAD(TO_CHAR(r_cliente.total_pagado, 'FM$999,999,999'), 15)
            || RPAD(TO_CHAR(r_cliente.saldo_pendiente, 'FM$999,999,999'), 15)
            || TO_CHAR(v_porc_pagado, 'FM990.0') || '%');

        v_clientes      := v_clientes + 1;
        v_saldo_cartera := v_saldo_cartera + r_cliente.saldo_pendiente;
    END LOOP;
    CLOSE c_cartera;

    -- Control: si la consulta no devolvió clientes, se levanta una
    -- excepción definida por el usuario.
    IF v_clientes = 0 THEN
        RAISE e_cartera_vacia;
    END IF;

    DBMS_OUTPUT.PUT_LINE('--------------------------------------------------');
    DBMS_OUTPUT.PUT_LINE('Clientes procesados : ' || v_clientes);
    DBMS_OUTPUT.PUT_LINE('Saldo total cartera  : '
        || TO_CHAR(v_saldo_cartera, 'FM$999,999,999'));
    DBMS_OUTPUT.PUT_LINE('Proceso mensual finalizado correctamente.');

EXCEPTION
    WHEN e_cartera_vacia THEN
        DBMS_OUTPUT.PUT_LINE('ERROR: no hay clientes con creditos '
            || 'para procesar en la cartera.');
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('ERROR inesperado en el proceso de '
            || 'cartera: ' || SQLERRM);
        RAISE;   -- re-lanza el error para que el llamador lo note
END sp_reporte_cartera;
/

/* ================================================================
   2) sp_registra_pago  --  PROCEDIMIENTO CON PARÁMETROS
   --------------------------------------------------------------
   Qué hace:
     Registra el pago (total o parcial) de UNA cuota de un crédito,
     actualizando monto_pagado, saldo_por_pagar, la fecha de pago
     y la forma de pago. Devuelve al llamador un mensaje y el nuevo
     saldo de la cuota mediante parámetros OUT.

   Firma:
     IN  : p_nro_solic_credito, p_nro_cuota, p_monto, p_cod_forma_pago
     OUT : p_mensaje (resultado de la operación)
           p_nuevo_saldo (saldo restante de la cuota)

   Validaciones (reglas de negocio):
     a) El monto debe ser mayor que cero        -> excepción propia
     b) La forma de pago debe existir            -> excepción propia
     c) La cuota debe existir                    -> NO_DATA_FOUND
     d) El pago acumulado no puede superar el
        valor de la cuota                       -> excepción propia

   Nota de integración: cuando en el script 05 exista el trigger de
   fila trg_cuota, el UPDATE de este procedimiento lo disparará y
   el trigger recalculará saldo_por_pagar automáticamente, dejando
   la regla aún más centralizada.
   ================================================================ */
CREATE OR REPLACE PROCEDURE sp_registra_pago(
    p_nro_solic_credito IN  cuota_credito_cliente.nro_solic_credito%TYPE,
    p_nro_cuota         IN  cuota_credito_cliente.nro_cuota%TYPE,
    p_monto             IN  cuota_credito_cliente.monto_pagado%TYPE,
    p_cod_forma_pago    IN  cuota_credito_cliente.cod_forma_pago%TYPE DEFAULT 1,
    p_mensaje           OUT VARCHAR2,
    p_nuevo_saldo       OUT NUMBER
) AS

    v_valor_cuota    cuota_credito_cliente.valor_cuota%TYPE;
    v_pagado_actual  cuota_credito_cliente.monto_pagado%TYPE;
    v_forma_pago     forma_pago.nombre_forma_pago%TYPE;

    -- Excepciones definidas por el usuario (Eva 1)
    e_monto_invalido  EXCEPTION;
    e_forma_invalida  EXCEPTION;
    e_pago_excedido   EXCEPTION;

BEGIN
    -- (a) Validación del monto ingresado
    IF p_monto IS NULL OR p_monto <= 0 THEN
        RAISE e_monto_invalido;
    END IF;

    -- (b) La forma de pago debe existir. Se valida en un bloque
    --     anidado para que su NO_DATA_FOUND no se confunda con el
    --     de la cuota (dos SELECT INTO distintos).
    BEGIN
        SELECT fpa.nombre_forma_pago
          INTO v_forma_pago
          FROM forma_pago fpa
         WHERE fpa.cod_forma_pago = p_cod_forma_pago;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE e_forma_invalida;
    END;

    -- (c) La cuota debe existir; si no hay coincidencias el SELECT
    --     INTO levanta NO_DATA_FOUND (excepción predefinida).
    SELECT cuo.valor_cuota,
           NVL(cuo.monto_pagado, 0)
      INTO v_valor_cuota, v_pagado_actual
      FROM cuota_credito_cliente cuo
     WHERE cuo.nro_solic_credito = p_nro_solic_credito
       AND cuo.nro_cuota         = p_nro_cuota;

    -- (d) El pago acumulado no puede superar el valor de la cuota
    IF v_pagado_actual + p_monto > v_valor_cuota THEN
        RAISE e_pago_excedido;
    END IF;

    -- Actualización de la cuota:
    --   fecha de pago: se conserva la primera si ya existía
    --   saldo        : valor de la cuota menos lo pagado acumulado
    UPDATE cuota_credito_cliente
       SET monto_pagado     = v_pagado_actual + p_monto,
           saldo_por_pagar  = v_valor_cuota - (v_pagado_actual + p_monto),
           fecha_pago_cuota = NVL(fecha_pago_cuota, SYSDATE),
           cod_forma_pago   = p_cod_forma_pago
     WHERE nro_solic_credito = p_nro_solic_credito
       AND nro_cuota         = p_nro_cuota;

    p_nuevo_saldo := v_valor_cuota - (v_pagado_actual + p_monto);
    p_mensaje     := 'Pago de '
                   || TO_CHAR(p_monto, 'FM$999,999,999')
                   || ' registrado (' || v_forma_pago || '). Nuevo saldo cuota: '
                   || TO_CHAR(p_nuevo_saldo, 'FM$999,999,999');

    -- No se confirma la transacción: el llamador decide cuándo hacer COMMIT.

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        -- No se revierte la transacción completa del llamador.
        p_mensaje     := 'ERROR: la cuota ' || p_nro_cuota
                      || ' de la solicitud ' || p_nro_solic_credito
                      || ' no existe.';
        p_nuevo_saldo := NULL;
    WHEN e_monto_invalido THEN
        -- No se revierte la transacción completa del llamador.
        p_mensaje     := 'ERROR: el monto del pago debe ser mayor que cero.';
        p_nuevo_saldo := NULL;
    WHEN e_forma_invalida THEN
        -- No se revierte la transacción completa del llamador.
        p_mensaje     := 'ERROR: la forma de pago ' || p_cod_forma_pago
                      || ' no existe.';
        p_nuevo_saldo := NULL;
    WHEN e_pago_excedido THEN
        -- No se revierte la transacción completa del llamador.
        p_mensaje     := 'ERROR: el pago excede el valor de la cuota ('
                      || TO_CHAR(v_valor_cuota, 'FM$999,999,999') || ').';
        p_nuevo_saldo := NULL;
    WHEN OTHERS THEN
        -- No se revierte la transacción completa del llamador.
        p_mensaje     := 'ERROR inesperado: ' || SQLERRM;
        p_nuevo_saldo := NULL;
        RAISE;   -- re-lanza para que el llamador se entere
END sp_registra_pago;
/

/* ================================================================
   3) DEMOSTRACIÓN DE USO
   --------------------------------------------------------------
   La rúbrica exige que los procedimientos "sean usadas en otros
   programas PL/SQL y en sentencias SQL". Este bloque anónimo:
     - llama al procedimiento sin parámetros (es un programa PL/SQL
       distinto que lo reutiliza), y
     - llama al procedimiento con parámetros capturando sus OUT.

   Pruebas sobre datos reales de BD_KOPERA (solicitud 2001, cliente 5):
     1) Informe mensual de toda la cartera.
     2) Pago válido: cuota 5 ($57.292, aún sin pagar).
     3) Forma de pago inexistente -> e_forma_invalida
     4) Pago que excede la cuota  -> e_pago_excedido
     5) Cuota inexistente         -> NO_DATA_FOUND
     6) Monto inválido            -> e_monto_invalido

   NOTA: la prueba 2 MODIFICA los datos. Para volver al estado
   original re-ejecuta BD_KOPERA.SQL.
   ================================================================ */
 DECLARE
    v_mensaje     VARCHAR2(300);
    v_nuevo_saldo NUMBER;
BEGIN
    DBMS_OUTPUT.PUT_LINE('--- Prueba 1: uso desde otro programa PL/SQL ---');

    -- (1) Llamada al procedimiento SIN parámetros
    sp_reporte_cartera;

    -- (2) Llamada al procedimiento CON parámetros: pago válido
    sp_registra_pago(2001, 5, 57292, 2, v_mensaje, v_nuevo_saldo);
    DBMS_OUTPUT.PUT_LINE('Prueba pago valido   : ' || v_mensaje);

    -- (3) Forma de pago inexistente (validación b)
    sp_registra_pago(2001, 6, 57292, 99, v_mensaje, v_nuevo_saldo);
    DBMS_OUTPUT.PUT_LINE('Prueba forma invalida: ' || v_mensaje);

    -- (4) Pago que excede el valor de la cuota (validación d)
    sp_registra_pago(2001, 5, 57292, 1, v_mensaje, v_nuevo_saldo);
    DBMS_OUTPUT.PUT_LINE('Prueba pago excedido : ' || v_mensaje);

    -- (5) Cuota inexistente (validación c)
    sp_registra_pago(2001, 99, 10000, 1, v_mensaje, v_nuevo_saldo);
    DBMS_OUTPUT.PUT_LINE('Prueba cuota invalida: ' || v_mensaje);

    -- (6) Monto inválido (validación a)
    sp_registra_pago(2001, 6, 0, 1, v_mensaje, v_nuevo_saldo);
    DBMS_OUTPUT.PUT_LINE('Prueba monto invalido: ' || v_mensaje);
END;
/
COMMIT;  -- confirma los cambios de la prueba 2

/* ----------------------------------------------------------------
   USO DESDE SENTENCIA SQL (SQL*Plus / SQL Developer):
   Otra forma de invocarlos, capturando los OUT en variables de
   sesión (bind variables):

     VARIABLE g_mensaje  VARCHAR2(300)
     VARIABLE g_saldo    NUMBER
     EXECUTE sp_registra_pago(2001, 6, 57292, 2, :g_mensaje, :g_saldo)
     PRINT g_mensaje
     CALL sp_reporte_cartera()
   ---------------------------------------------------------------- */
