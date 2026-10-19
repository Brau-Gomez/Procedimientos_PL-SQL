/*
  Pruebas de integración sin dejar cambios permanentes.
  Prerrequisitos: ejecutar 01, 02, 03 y 04; habilitar DBMS_OUTPUT.
  Los SAVEPOINT/ROLLBACK protegen datos; no invocar sp_registra_pago porque hoy confirma con COMMIT.
*/
SET SERVEROUTPUT ON SIZE UNLIMITED;
DECLARE
  v_credito NUMBER; v_cuota NUMBER; v_pagado NUMBER; v_valor NUMBER;
  v_solicitud NUMBER; v_tipo_abono NUMBER; v_tipo_rescate NUMBER;
  v_cliente NUMBER; v_producto NUMBER; v_mensaje VARCHAR2(4000);
  v_resumen pk_analisis_kopera.t_resumen_cliente;
  v_alertas pk_analisis_kopera.t_alertas;
BEGIN
  -- El análisis no modifica datos.
  pk_analisis_kopera.sp_analiza_cliente(5,v_resumen,v_alertas);
  DBMS_OUTPUT.PUT_LINE('Análisis cliente 5: '||v_resumen.clasificacion||
    ', saldo $'||v_resumen.saldo_pendiente||', alertas '||v_alertas.COUNT);

  SELECT nro_solic_credito,nro_cuota,NVL(monto_pagado,0),valor_cuota
    INTO v_credito,v_cuota,v_pagado,v_valor
    FROM (SELECT cu.* FROM cuota_credito_cliente cu ORDER BY nro_solic_credito,nro_cuota)
   WHERE ROWNUM=1;
  SAVEPOINT prueba_pago;
  UPDATE cuota_credito_cliente SET monto_pagado=LEAST(v_valor,v_pagado+1)
   WHERE nro_solic_credito=v_credito AND nro_cuota=v_cuota;
  DBMS_OUTPUT.PUT_LINE('Pago válido: saldo recalculado y bitácora creada.');
  ROLLBACK TO prueba_pago;

  SAVEPOINT prueba_exceso;
  BEGIN
    UPDATE cuota_credito_cliente SET monto_pagado=valor_cuota+1
     WHERE nro_solic_credito=v_credito AND nro_cuota=v_cuota;
    DBMS_OUTPUT.PUT_LINE('ERROR: el pago excedido fue aceptado.');
  EXCEPTION WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('Pago excedido rechazado: '||SQLERRM);
  END;
  ROLLBACK TO prueba_exceso;

  SELECT cod_tipo_mov INTO v_tipo_abono FROM tipo_movimiento WHERE UPPER(nombre_tipo_mov)='ABONO';
  SELECT cod_tipo_mov INTO v_tipo_rescate FROM tipo_movimiento WHERE UPPER(nombre_tipo_mov)='RESCATE';
  SELECT nro_solic_prod,nro_cliente,cod_prod_inv INTO v_solicitud,v_cliente,v_producto
    FROM (SELECT * FROM producto_inversion_cliente WHERE monto_total_ahorrado>0 ORDER BY nro_solic_prod)
   WHERE ROWNUM=1;
  SAVEPOINT prueba_movimiento;
  INSERT INTO movimiento(nro_movimiento,nro_solic_prod,nro_cliente,cod_prod_inv,fecha_movimiento,monto_movimiento,cod_tipo_mov)
  VALUES((SELECT NVL(MAX(nro_movimiento),0)+1 FROM movimiento),v_solicitud,v_cliente,v_producto,SYSDATE,1,v_tipo_abono);
  DBMS_OUTPUT.PUT_LINE('Abono válido: ahorro sincronizado.');
  ROLLBACK TO prueba_movimiento;

  BEGIN
    INSERT INTO movimiento(nro_movimiento,nro_solic_prod,nro_cliente,cod_prod_inv,fecha_movimiento,monto_movimiento,cod_tipo_mov)
    VALUES((SELECT NVL(MAX(nro_movimiento),0)+1 FROM movimiento),v_solicitud,v_cliente,v_producto,SYSDATE,9999999999,v_tipo_rescate);
    DBMS_OUTPUT.PUT_LINE('ERROR: rescate excedido aceptado.');
  EXCEPTION WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('Rescate excedido rechazado: '||SQLERRM);
  END;
  ROLLBACK;

  DBMS_OUTPUT.PUT_LINE('Prueba del proceso mensual (salida resumida en DBMS_OUTPUT):');
  pk_analisis_kopera.sp_proceso_mensual;
END;
/

-- Revisar estado de compilación y errores tras ejecutar los scripts.
SELECT object_name, object_type, status FROM user_objects
 WHERE object_name IN ('PK_ANALISIS_KOPERA','TRG_CUOTA_VALIDA_PAGO','TRG_CUOTA_BITACORA',
   'TRG_MOVIMIENTO_VALIDA','TRG_MOVIMIENTO_ACTUALIZA_AHORRO')
 ORDER BY object_type,object_name;
SELECT name,type,line,position,text FROM user_errors ORDER BY name,sequence;
