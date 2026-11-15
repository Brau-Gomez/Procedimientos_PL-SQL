/*
  Proyecto KOPERA – análisis mensual de cartera.

  Prerrequisitos: base/BD_KOPERA.SQL y 01_tablas_apoyo.sql.
  Ejecución: correr completo con F5 como ADMIN_PROYECTO.
  Las funciones quedan dentro del package para mantener una sola lógica.
*/
CREATE OR REPLACE PACKAGE pk_analisis_kopera AS
  TYPE t_resumen_cliente IS RECORD (
    nro_cliente cliente.nro_cliente%TYPE,
    nombre_completo VARCHAR2(203),
    total_creditos NUMBER,
    total_pagado NUMBER,
    saldo_pendiente NUMBER,
    total_ahorrado NUMBER,
    clasificacion VARCHAR2(30)
  );
  TYPE t_alertas IS VARRAY(10) OF VARCHAR2(300);
  e_cartera_vacia EXCEPTION;
  e_cliente_sin_productos EXCEPTION;
  e_pago_excedido EXCEPTION;
  e_rescate_excedido EXCEPTION;

  FUNCTION fn_saldo_pendiente(p_cliente NUMBER) RETURN NUMBER;
  FUNCTION fn_porcentaje_pagado(p_cliente NUMBER) RETURN NUMBER;
  FUNCTION fn_cuenta_cuotas(p_cliente NUMBER, p_estado VARCHAR2) RETURN PLS_INTEGER;
  FUNCTION fn_total_ahorrado(p_cliente NUMBER) RETURN NUMBER;
  FUNCTION fn_clasifica_cliente(p_cliente NUMBER) RETURN VARCHAR2;
  FUNCTION fn_dias_atraso(p_credito NUMBER, p_nro_cuota NUMBER) RETURN NUMBER;
  FUNCTION fn_porc_rescate(p_solicitud NUMBER) RETURN NUMBER;
  FUNCTION fn_aporte_sbif(p_monto_credito NUMBER) RETURN NUMBER;
  PROCEDURE sp_analiza_cliente(p_cliente NUMBER, p_resumen OUT t_resumen_cliente,
                               p_alertas OUT t_alertas);
  PROCEDURE sp_proceso_mensual;
  PROCEDURE sp_registra_movimiento(p_solicitud NUMBER, p_monto NUMBER,
      p_tipo_movimiento NUMBER, p_mensaje OUT VARCHAR2);
END pk_analisis_kopera;
/

CREATE OR REPLACE PACKAGE BODY pk_analisis_kopera AS
  -- Estos cursores reflejan la jerarquía cliente/crédito/cuota e inversión/movimiento.
  CURSOR c_clientes IS
    SELECT nro_cliente, TRIM(pnombre || ' ' || appaterno) nombre
      FROM cliente ORDER BY nro_cliente;
  CURSOR c_creditos_cliente(p_cliente NUMBER) IS
    SELECT cc.nro_solic_credito, cc.monto_credito
      FROM credito_cliente cc WHERE cc.nro_cliente = p_cliente;
  CURSOR c_cuotas_credito(p_credito NUMBER, p_fecha_corte DATE) IS
    SELECT nro_cuota, valor_cuota, NVL(monto_pagado,0) monto_pagado,
           NVL(saldo_por_pagar, valor_cuota) saldo,
           CASE WHEN NVL(saldo_por_pagar,valor_cuota)=0 THEN 'PAGADA'
                WHEN NVL(monto_pagado,0)>0 THEN 'PARCIAL'
                WHEN fecha_venc_cuota < p_fecha_corte THEN 'VENCIDA'
                ELSE 'PENDIENTE' END estado
      FROM cuota_credito_cliente WHERE nro_solic_credito=p_credito;
  CURSOR c_inversiones_cliente(p_cliente NUMBER) IS
    SELECT nro_solic_prod, monto_total_ahorrado FROM producto_inversion_cliente
     WHERE nro_cliente=p_cliente;
  CURSOR c_movimientos_producto(p_solicitud NUMBER) IS
    SELECT m.monto_movimiento, tm.nombre_tipo_mov
      FROM movimiento m JOIN tipo_movimiento tm ON tm.cod_tipo_mov=m.cod_tipo_mov
     WHERE m.nro_solic_prod=p_solicitud ORDER BY m.fecha_movimiento DESC;
  CURSOR c_cuotas_vencidas(p_fecha_corte DATE) IS
    SELECT cu.nro_solic_credito, cu.nro_cuota FROM cuota_credito_cliente cu
     WHERE NVL(cu.saldo_por_pagar,cu.valor_cuota)>0
       AND cu.fecha_venc_cuota<p_fecha_corte;

  FUNCTION fn_saldo_pendiente(p_cliente NUMBER) RETURN NUMBER IS v NUMBER;
  BEGIN
    SELECT NVL(SUM(NVL(cu.saldo_por_pagar,cu.valor_cuota)),0) INTO v
      FROM credito_cliente cc JOIN cuota_credito_cliente cu
        ON cu.nro_solic_credito=cc.nro_solic_credito WHERE cc.nro_cliente=p_cliente;
    RETURN v;
  END;

  FUNCTION fn_porcentaje_pagado(p_cliente NUMBER) RETURN NUMBER IS v_total NUMBER; v_pagado NUMBER;
  BEGIN
    SELECT NVL(SUM(cu.valor_cuota),0), NVL(SUM(NVL(cu.monto_pagado,0)),0)
      INTO v_total,v_pagado FROM credito_cliente cc JOIN cuota_credito_cliente cu
        ON cu.nro_solic_credito=cc.nro_solic_credito WHERE cc.nro_cliente=p_cliente;
    RETURN CASE WHEN v_total=0 THEN 0 ELSE ROUND(v_pagado/v_total*100,2) END;
  END;

  FUNCTION fn_cuenta_cuotas(p_cliente NUMBER,p_estado VARCHAR2) RETURN PLS_INTEGER IS v PLS_INTEGER;
  BEGIN
    SELECT COUNT(*) INTO v FROM credito_cliente cc JOIN cuota_credito_cliente cu
      ON cu.nro_solic_credito=cc.nro_solic_credito WHERE cc.nro_cliente=p_cliente
      AND CASE WHEN NVL(cu.saldo_por_pagar,cu.valor_cuota)=0 THEN 'PAGADA'
        WHEN NVL(cu.monto_pagado,0)>0 THEN 'PARCIAL'
        WHEN cu.fecha_venc_cuota<TRUNC(SYSDATE) THEN 'VENCIDA' ELSE 'PENDIENTE' END=UPPER(p_estado);
    RETURN v;
  END;

  FUNCTION fn_total_ahorrado(p_cliente NUMBER) RETURN NUMBER IS v NUMBER;
  BEGIN
    SELECT NVL(SUM(monto_total_ahorrado),0) INTO v FROM producto_inversion_cliente WHERE nro_cliente=p_cliente;
    RETURN v;
  END;

  FUNCTION fn_clasifica_cliente(p_cliente NUMBER) RETURN VARCHAR2 IS
    v_productos PLS_INTEGER; v_vencidas PLS_INTEGER; v_saldo NUMBER;
  BEGIN
    SELECT (SELECT COUNT(*) FROM producto_inversion_cliente WHERE nro_cliente=p_cliente)+
           (SELECT COUNT(*) FROM credito_cliente WHERE nro_cliente=p_cliente) INTO v_productos FROM dual;
    IF v_productos=0 THEN RETURN 'SIN PRODUCTOS'; END IF;
    v_vencidas:=fn_cuenta_cuotas(p_cliente,'VENCIDA'); v_saldo:=fn_saldo_pendiente(p_cliente);
    IF v_vencidas>0 OR fn_porcentaje_pagado(p_cliente)<50 THEN RETURN 'RIESGO';
    ELSIF v_saldo>0 THEN RETURN 'REGULAR'; ELSE RETURN 'BUENO'; END IF;
  END;

  FUNCTION fn_dias_atraso(p_credito NUMBER,p_nro_cuota NUMBER) RETURN NUMBER IS v NUMBER;
  BEGIN
    SELECT GREATEST(TRUNC(SYSDATE)-TRUNC(fecha_venc_cuota),0) INTO v
      FROM cuota_credito_cliente WHERE nro_solic_credito=p_credito AND nro_cuota=p_nro_cuota
       AND NVL(saldo_por_pagar,valor_cuota)>0;
    RETURN v;
  EXCEPTION WHEN NO_DATA_FOUND THEN RETURN 0;
  END;

  FUNCTION fn_porc_rescate(p_solicitud NUMBER) RETURN NUMBER IS v_saldo NUMBER; v_abonado NUMBER;
  BEGIN
    SELECT monto_total_ahorrado, NVL((SELECT SUM(m.monto_movimiento) FROM movimiento m
      JOIN tipo_movimiento t ON t.cod_tipo_mov=m.cod_tipo_mov
      WHERE m.nro_solic_prod=pic.nro_solic_prod AND UPPER(t.nombre_tipo_mov)='RESCATE'),0)
      INTO v_saldo,v_abonado FROM producto_inversion_cliente pic WHERE nro_solic_prod=p_solicitud;
    RETURN CASE WHEN v_saldo+v_abonado=0 THEN 0 ELSE ROUND(v_abonado/(v_saldo+v_abonado)*100,2) END;
  END;

  FUNCTION fn_aporte_sbif(p_monto_credito NUMBER) RETURN NUMBER IS v NUMBER;
  BEGIN
    SELECT NVL(MAX(porc_entrega_sbif),0) INTO v FROM aporte_a_sbif
     WHERE p_monto_credito BETWEEN monto_credito_desde AND monto_credito_hasta;
    RETURN v;
  END;

  PROCEDURE sp_analiza_cliente(p_cliente NUMBER,p_resumen OUT t_resumen_cliente,p_alertas OUT t_alertas) IS
    v_producto PLS_INTEGER:=0; v_credito PLS_INTEGER:=0; v_total_pago NUMBER:=0;
  BEGIN
    SELECT TRIM(pnombre||' '||appaterno) INTO p_resumen.nombre_completo FROM cliente WHERE nro_cliente=p_cliente;
    p_resumen.nro_cliente:=p_cliente; p_resumen.total_creditos:=0; p_resumen.total_pagado:=0;
    p_resumen.saldo_pendiente:=0; p_resumen.total_ahorrado:=0; p_alertas:=t_alertas();
    FOR i IN c_inversiones_cliente(p_cliente) LOOP
      v_producto:=v_producto+1; p_resumen.total_ahorrado:=p_resumen.total_ahorrado+NVL(i.monto_total_ahorrado,0);
      FOR m IN c_movimientos_producto(i.nro_solic_prod) LOOP NULL; END LOOP;
    END LOOP;
    FOR c IN c_creditos_cliente(p_cliente) LOOP
      v_credito:=v_credito+1; p_resumen.total_creditos:=p_resumen.total_creditos+c.monto_credito;
      FOR q IN c_cuotas_credito(c.nro_solic_credito,SYSDATE) LOOP
        p_resumen.saldo_pendiente:=p_resumen.saldo_pendiente+q.saldo;
        p_resumen.total_pagado:=p_resumen.total_pagado+q.monto_pagado;
        IF q.estado='VENCIDA' AND p_alertas.COUNT<10 THEN
          p_alertas.EXTEND; p_alertas(p_alertas.LAST):='Cuota vencida: crédito '||c.nro_solic_credito||', cuota '||q.nro_cuota;
        ELSIF q.estado='PARCIAL' AND p_alertas.COUNT<10 THEN
          p_alertas.EXTEND; p_alertas(p_alertas.LAST):='Pago incompleto: crédito '||c.nro_solic_credito||', cuota '||q.nro_cuota;
        END IF;
      END LOOP;
    END LOOP;
    IF v_producto=0 AND v_credito=0 THEN RAISE e_cliente_sin_productos; END IF;
    p_resumen.clasificacion:=fn_clasifica_cliente(p_cliente);
  END;

  PROCEDURE sp_proceso_mensual IS r t_resumen_cliente; a t_alertas; v_clientes PLS_INTEGER:=0; v_saldo NUMBER:=0;
  BEGIN
    DBMS_OUTPUT.PUT_LINE('Proceso mensual KOPERA | '||TO_CHAR(SYSDATE,'DD/MM/YYYY'));
    FOR c IN c_clientes LOOP
      BEGIN
        sp_analiza_cliente(c.nro_cliente,r,a); v_clientes:=v_clientes+1; v_saldo:=v_saldo+r.saldo_pendiente;
        DBMS_OUTPUT.PUT_LINE(c.nro_cliente||' '||r.nombre_completo||' | créditos $'||r.total_creditos||
          ' | pagado $'||r.total_pagado||' | saldo $'||r.saldo_pendiente||' | '||r.clasificacion);
        FOR i IN 1..a.COUNT LOOP DBMS_OUTPUT.PUT_LINE('  ALERTA: '||a(i)); END LOOP;
      EXCEPTION WHEN e_cliente_sin_productos THEN NULL;
      END;
    END LOOP;
    IF v_clientes=0 THEN RAISE e_cartera_vacia; END IF;
    DBMS_OUTPUT.PUT_LINE('Clientes analizados: '||v_clientes||' | saldo total: $'||v_saldo);
  END;

  PROCEDURE sp_registra_movimiento(p_solicitud NUMBER,p_monto NUMBER,p_tipo_movimiento NUMBER,p_mensaje OUT VARCHAR2) IS
    v_cliente NUMBER; v_prod NUMBER;
  BEGIN
    IF p_monto IS NULL OR p_monto<=0 THEN RAISE_APPLICATION_ERROR(-20020,'El monto debe ser positivo.'); END IF;
    SELECT nro_cliente,cod_prod_inv INTO v_cliente,v_prod FROM producto_inversion_cliente WHERE nro_solic_prod=p_solicitud;
    INSERT INTO movimiento(nro_movimiento,nro_solic_prod,nro_cliente,cod_prod_inv,fecha_movimiento,monto_movimiento,cod_tipo_mov)
      VALUES((SELECT NVL(MAX(nro_movimiento),0)+1 FROM movimiento),p_solicitud,v_cliente,v_prod,SYSDATE,p_monto,p_tipo_movimiento);
    p_mensaje:='Movimiento registrado correctamente.';
  EXCEPTION WHEN OTHERS THEN p_mensaje:=SQLERRM; RAISE;
  END;
END pk_analisis_kopera;
/
SHOW ERRORS PACKAGE pk_analisis_kopera
SHOW ERRORS PACKAGE BODY pk_analisis_kopera
