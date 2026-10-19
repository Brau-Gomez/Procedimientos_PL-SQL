/*
  Proyecto KOPERA – reglas automáticas de integridad y auditoría.
  Prerrequisitos: BD_KOPERA.SQL y eva2/01_tablas_apoyo.sql.
  Ejecutar como ADMIN_PROYECTO. Los triggers no hacen COMMIT.
*/
BEGIN
  EXECUTE IMMEDIATE 'DROP TRIGGER trg_cuota_valida_pago';
EXCEPTION WHEN OTHERS THEN IF SQLCODE <> -4080 THEN RAISE; END IF;
END;
/
BEGIN
  EXECUTE IMMEDIATE 'DROP TRIGGER trg_cuota_bitacora';
EXCEPTION WHEN OTHERS THEN IF SQLCODE <> -4080 THEN RAISE; END IF;
END;
/
BEGIN
  EXECUTE IMMEDIATE 'DROP TRIGGER trg_movimiento_valida';
EXCEPTION WHEN OTHERS THEN IF SQLCODE <> -4080 THEN RAISE; END IF;
END;
/
BEGIN
  EXECUTE IMMEDIATE 'DROP TRIGGER trg_movimiento_actualiza_ahorro';
EXCEPTION WHEN OTHERS THEN IF SQLCODE <> -4080 THEN RAISE; END IF;
END;
/

-- Valida el acumulado y deriva el saldo; evita que se mantengan cálculos inconsistentes.
CREATE OR REPLACE TRIGGER trg_cuota_valida_pago
BEFORE INSERT OR UPDATE OF monto_pagado, valor_cuota ON cuota_credito_cliente
FOR EACH ROW
BEGIN
  IF NVL(:NEW.monto_pagado,0)<0 OR NVL(:NEW.monto_pagado,0)>:NEW.valor_cuota THEN
    RAISE_APPLICATION_ERROR(-20001,'El pago debe estar entre cero y el valor de la cuota.');
  END IF;
  :NEW.saldo_por_pagar:=:NEW.valor_cuota-NVL(:NEW.monto_pagado,0);
END;
/

-- Registra únicamente cambios efectivos del monto pagado.
CREATE OR REPLACE TRIGGER trg_cuota_bitacora
AFTER UPDATE OF monto_pagado ON cuota_credito_cliente
FOR EACH ROW
WHEN (NVL(NEW.monto_pagado,-1) <> NVL(OLD.monto_pagado,-1))
BEGIN
  INSERT INTO bitacora_pago_cuota(nro_solic_credito,nro_cuota,fecha_evento,usuario_evento,
    monto_pagado_anterior,monto_pagado_nuevo,valor_cuota,saldo_resultante,cod_forma_pago)
  VALUES(:NEW.nro_solic_credito,:NEW.nro_cuota,SYSDATE,USER,:OLD.monto_pagado,
    :NEW.monto_pagado,:NEW.valor_cuota,:NEW.saldo_por_pagar,:NEW.cod_forma_pago);
END;
/

-- Verifica monto, catálogo, saldo disponible y porcentaje contractual máximo.
CREATE OR REPLACE TRIGGER trg_movimiento_valida
BEFORE INSERT ON movimiento
FOR EACH ROW
DECLARE
  v_nombre tipo_movimiento.nombre_tipo_mov%TYPE;
  v_saldo producto_inversion_cliente.monto_total_ahorrado%TYPE;
  v_maximo producto_inversion.porc_maximo_rescate%TYPE;
  v_rescates NUMBER;
BEGIN
  IF :NEW.monto_movimiento<=0 THEN
    RAISE_APPLICATION_ERROR(-20010,'El monto del movimiento debe ser positivo.');
  END IF;
  SELECT UPPER(nombre_tipo_mov) INTO v_nombre FROM tipo_movimiento WHERE cod_tipo_mov=:NEW.cod_tipo_mov;
  IF v_nombre NOT IN ('ABONO','RESCATE') THEN
    RAISE_APPLICATION_ERROR(-20011,'Tipo de movimiento debe ser ABONO o RESCATE.');
  END IF;
  IF v_nombre='RESCATE' THEN
    SELECT pic.monto_total_ahorrado,pi.porc_maximo_rescate
      INTO v_saldo,v_maximo FROM producto_inversion_cliente pic
      JOIN producto_inversion pi ON pi.cod_prod_inv=pic.cod_prod_inv
     WHERE pic.nro_solic_prod=:NEW.nro_solic_prod;
    SELECT NVL(SUM(m.monto_movimiento),0) INTO v_rescates FROM movimiento m
      JOIN tipo_movimiento t ON t.cod_tipo_mov=m.cod_tipo_mov
     WHERE m.nro_solic_prod=:NEW.nro_solic_prod AND UPPER(t.nombre_tipo_mov)='RESCATE';
    IF :NEW.monto_movimiento>v_saldo THEN
      RAISE_APPLICATION_ERROR(-20012,'El rescate excede el ahorro disponible.');
    END IF;
    IF (v_rescates+:NEW.monto_movimiento)>((v_saldo+v_rescates)*NVL(v_maximo,0)/100) THEN
      RAISE_APPLICATION_ERROR(-20013,'El rescate acumulado excede el porcentaje permitido.');
    END IF;
  END IF;
EXCEPTION WHEN NO_DATA_FOUND THEN
  RAISE_APPLICATION_ERROR(-20014,'No existe el producto o tipo de movimiento indicado.');
END;
/

-- Mantiene el ahorro actualizado después de insertar un movimiento válido.
CREATE OR REPLACE TRIGGER trg_movimiento_actualiza_ahorro
AFTER INSERT ON movimiento
FOR EACH ROW
DECLARE v_nombre tipo_movimiento.nombre_tipo_mov%TYPE;
BEGIN
  SELECT UPPER(nombre_tipo_mov) INTO v_nombre FROM tipo_movimiento WHERE cod_tipo_mov=:NEW.cod_tipo_mov;
  UPDATE producto_inversion_cliente
     SET monto_total_ahorrado=monto_total_ahorrado+
       CASE WHEN v_nombre='ABONO' THEN :NEW.monto_movimiento ELSE -:NEW.monto_movimiento END
   WHERE nro_solic_prod=:NEW.nro_solic_prod;
END;
/
SHOW ERRORS
