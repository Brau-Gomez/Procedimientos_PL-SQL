/*
  PRUEBA INTEGRADA: RESUMEN FINANCIERO KOPERA

  Prerrequisito: ejecutar BD_KOPERA.SQL conectado como ADMIN_PROYECTO.
  El bloque es de solo lectura: no crea objetos ni modifica datos.
*/

SET SERVEROUTPUT ON SIZE UNLIMITED;

DECLARE
  ------------------------------------------------------------------
  -- 1. TIPOS COMPUESTOS
  ------------------------------------------------------------------
  TYPE t_resumen_cliente IS RECORD (
    nro_cliente              CLIENTE.nro_cliente%TYPE,
    nombre_completo          VARCHAR2(203),
    cant_inversiones         PLS_INTEGER,
    total_ahorrado           NUMBER(14, 2),
    cant_creditos            PLS_INTEGER,
    total_creditos           NUMBER(14, 2),
    saldo_pendiente          NUMBER(14, 2),
    cant_movimientos         PLS_INTEGER,
    porcentaje_saldo         NUMBER(7, 2),
    clasificacion_financiera VARCHAR2(30),
    estado_actividad         VARCHAR2(60)
  );

  TYPE t_movimientos_recientes IS VARRAY(5) OF VARCHAR2(250);

  v_resumen     t_resumen_cliente;
  v_movimientos t_movimientos_recientes := t_movimientos_recientes();

  ------------------------------------------------------------------
  -- 2. EXCEPCION PERSONALIZADA
  ------------------------------------------------------------------
  e_sin_productos_financieros EXCEPTION;

  ------------------------------------------------------------------
  -- 3. CURSOR SIMPLE SIN PARAMETROS
  ------------------------------------------------------------------
  CURSOR c_clientes IS
    SELECT c.nro_cliente,
           TRIM(c.pnombre || ' ' || NVL(c.snombre || ' ', '') ||
                c.appaterno || ' ' || NVL(c.apmaterno, ''))
             AS nombre_completo
      FROM CLIENTE c
     ORDER BY c.nro_cliente;

  ------------------------------------------------------------------
  -- 4. CURSORES COMPLEJOS PARAMETRIZADOS
  ------------------------------------------------------------------
  CURSOR c_inversiones(p_nro_cliente CLIENTE.nro_cliente%TYPE) IS
    SELECT pic.nro_solic_prod,
           pi.nombre_prod_inv,
           pic.monto_total_ahorrado
      FROM PRODUCTO_INVERSION_CLIENTE pic
      JOIN PRODUCTO_INVERSION pi
        ON pi.cod_prod_inv = pic.cod_prod_inv
     WHERE pic.nro_cliente = p_nro_cliente
     ORDER BY pi.nombre_prod_inv, pic.nro_solic_prod;

  CURSOR c_creditos(p_nro_cliente CLIENTE.nro_cliente%TYPE) IS
    SELECT cc.nro_solic_credito,
           cr.nombre_credito,
           cc.monto_credito,
           cc.total_cuotas_credito,
           COUNT(cu.nro_cuota) AS cuotas_registradas,
           NVL(SUM(cu.saldo_por_pagar), 0) AS saldo_pendiente
      FROM CREDITO_CLIENTE cc
      JOIN CREDITO cr
        ON cr.cod_credito = cc.cod_credito
      LEFT JOIN CUOTA_CREDITO_CLIENTE cu
        ON cu.nro_solic_credito = cc.nro_solic_credito
     WHERE cc.nro_cliente = p_nro_cliente
     GROUP BY cc.nro_solic_credito,
              cr.nombre_credito,
              cc.monto_credito,
              cc.total_cuotas_credito
     ORDER BY cc.nro_solic_credito;

  CURSOR c_movimientos(p_nro_cliente CLIENTE.nro_cliente%TYPE) IS
    SELECT m.nro_movimiento,
           m.fecha_movimiento,
           tm.nombre_tipo_mov,
           pi.nombre_prod_inv,
           m.monto_movimiento
      FROM MOVIMIENTO m
      JOIN TIPO_MOVIMIENTO tm
        ON tm.cod_tipo_mov = m.cod_tipo_mov
      JOIN PRODUCTO_INVERSION pi
        ON pi.cod_prod_inv = m.cod_prod_inv
     WHERE m.nro_cliente = p_nro_cliente
     ORDER BY m.fecha_movimiento DESC, m.nro_movimiento DESC;

BEGIN
  ------------------------------------------------------------------
  -- 5. PROCESAMIENTO MASIVO DE CLIENTES
  ------------------------------------------------------------------
  FOR r_cliente IN c_clientes LOOP
    BEGIN
      v_resumen.nro_cliente              := r_cliente.nro_cliente;
      v_resumen.nombre_completo          := r_cliente.nombre_completo;
      v_resumen.cant_inversiones         := 0;
      v_resumen.total_ahorrado           := 0;
      v_resumen.cant_creditos            := 0;
      v_resumen.total_creditos           := 0;
      v_resumen.saldo_pendiente          := 0;
      v_resumen.cant_movimientos         := 0;
      v_resumen.porcentaje_saldo         := 0;
      v_resumen.clasificacion_financiera := NULL;
      v_resumen.estado_actividad         := NULL;
      v_movimientos := t_movimientos_recientes();

      FOR r_inversion IN c_inversiones(r_cliente.nro_cliente) LOOP
        v_resumen.cant_inversiones := v_resumen.cant_inversiones + 1;
        v_resumen.total_ahorrado := v_resumen.total_ahorrado +
                                    r_inversion.monto_total_ahorrado;
      END LOOP;

      FOR r_credito IN c_creditos(r_cliente.nro_cliente) LOOP
        v_resumen.cant_creditos := v_resumen.cant_creditos + 1;
        v_resumen.total_creditos := v_resumen.total_creditos +
                                    r_credito.monto_credito;
        v_resumen.saldo_pendiente := v_resumen.saldo_pendiente +
                                     r_credito.saldo_pendiente;
      END LOOP;

      FOR r_movimiento IN c_movimientos(r_cliente.nro_cliente) LOOP
        v_resumen.cant_movimientos := v_resumen.cant_movimientos + 1;

        IF v_movimientos.COUNT < v_movimientos.LIMIT THEN
          v_movimientos.EXTEND;
          v_movimientos(v_movimientos.LAST) :=
            TO_CHAR(r_movimiento.fecha_movimiento, 'DD-MM-YYYY') ||
            ' | ' || r_movimiento.nombre_tipo_mov ||
            ' | ' || r_movimiento.nombre_prod_inv ||
            ' | $' || TO_CHAR(r_movimiento.monto_movimiento,
                               '$999G999G990');
        END IF;
      END LOOP;

      IF v_resumen.cant_inversiones = 0
         AND v_resumen.cant_creditos = 0 THEN
        RAISE e_sin_productos_financieros;
      END IF;

      ----------------------------------------------------------------
      -- ZERO_DIVIDE se demuestra cuando el cliente no tiene creditos.
      ----------------------------------------------------------------
      BEGIN
        v_resumen.porcentaje_saldo :=
          ROUND((v_resumen.saldo_pendiente /
                 v_resumen.total_creditos) * 100, 2);
      EXCEPTION
        WHEN ZERO_DIVIDE THEN
          v_resumen.porcentaje_saldo := 0;
      END;

      v_resumen.clasificacion_financiera :=
        CASE
          WHEN v_resumen.cant_creditos = 0 THEN 'SIN CREDITOS'
          WHEN v_resumen.saldo_pendiente = 0 THEN 'SIN SALDO PENDIENTE'
          WHEN v_resumen.porcentaje_saldo > 50 THEN 'SALDO ALTO'
          ELSE 'SEGUIMIENTO'
        END;

      IF v_resumen.cant_movimientos = 0 THEN
        v_resumen.estado_actividad :=
          'SIN MOVIMIENTOS - OPORTUNIDAD DE REACTIVACION';
      ELSE
        v_resumen.estado_actividad := 'ACTIVO';
      END IF;

      DBMS_OUTPUT.PUT_LINE('----------------------------------------');
      DBMS_OUTPUT.PUT_LINE('Cliente ' || v_resumen.nro_cliente ||
                           ': ' || v_resumen.nombre_completo);
      DBMS_OUTPUT.PUT_LINE('Inversiones: ' ||
                           v_resumen.cant_inversiones ||
                           ' | Total ahorrado: $' ||
                           TO_CHAR(v_resumen.total_ahorrado,
                                   '$999G999G990'));
      DBMS_OUTPUT.PUT_LINE('Creditos: ' || v_resumen.cant_creditos ||
                           ' | Total creditos: $' ||
                           TO_CHAR(v_resumen.total_creditos,
                                   '$999G999G990') ||
                           ' | Saldo pendiente: $' ||
                           TO_CHAR(v_resumen.saldo_pendiente,
                                   '$999G999G990'));
      DBMS_OUTPUT.PUT_LINE('Clasificacion: ' ||
                           v_resumen.clasificacion_financiera ||
                           ' | Actividad: ' ||
                           v_resumen.estado_actividad);

      IF v_movimientos.COUNT = 0 THEN
        DBMS_OUTPUT.PUT_LINE('Movimientos recientes: sin registros.');
      ELSE
        FOR i IN 1 .. v_movimientos.COUNT LOOP
          DBMS_OUTPUT.PUT_LINE('Movimiento ' || i || ': ' ||
                               v_movimientos(i));
        END LOOP;
      END IF;

    EXCEPTION
      WHEN e_sin_productos_financieros THEN
        DBMS_OUTPUT.PUT_LINE('Cliente ' || r_cliente.nro_cliente ||
          ': no posee inversiones ni creditos para consolidar.');
      WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Error en cliente ' ||
          r_cliente.nro_cliente || ' - ' || SQLCODE ||
          ': ' || SQLERRM);
    END;
  END LOOP;

EXCEPTION
  WHEN OTHERS THEN
    DBMS_OUTPUT.PUT_LINE('Error general ' || SQLCODE || ': ' || SQLERRM);
    RAISE;
END;
/
