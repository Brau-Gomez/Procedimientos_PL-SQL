/* ================================================================
   PROYECTO KOPERA - ENTREGA EVALUACIÓN PARCIAL 2 (BDY1103 - 004D)
   Script  : 01_tablas_apoyo.sql
   ----------------------------------------------------------------
   PROPÓSITO
     Crear la tabla de apoyo BITACORA_PAGO_CUOTA, que servirá de
     auditoría de los pagos de cuotas. El trigger trg_cuota_bitacora
     (script 04) insertará aquí UNA FILA por cada cuota cuyo
     monto_pagado cambie, dejando registro del valor anterior, el
     nuevo, el saldo resultante, la fecha y el usuario que ejecutó
     la operación.

   PRERREQUISITOS
     - BD_KOPERA.SQL ejecutado (conectado como ADMIN_PROYECTO).
     - No modificar BD_KOPERA.SQL (regla de la guía).

   INSTRUCCIÓN DE EJECUCIÓN
     - Ejecutar el script completo (F5 en SQL Developer) ANTES de
       02, 03 y 04. Es re-ejecutable: primero elimina la tabla si
       ya existía (bloque de limpieza).

   NOTA SOBRE RE-CARGA DE DATOS
     - Si más adelante se re-ejecuta BD_KOPERA.SQL, el
       "DROP TABLE CUOTA_CREDITO_CLIENTE CASCADE CONSTRAINTS"
       de ese script elimina la clave foránea de esta bitácora
       (no la tabla). Re-ejecutar este script tras recargar la BD.
   ================================================================ */

SET SERVEROUTPUT ON;

/* ----------------------------------------------------------------
   LIMPIEZA PREVIA
   Permite ejecutar este script varias veces. En la primera
   ejecución la tabla no existe y el DROP falla; ese error se
   controla con WHEN OTHERS, caso justificado y comentado para
   limpieza de objetos (regla 3 de la guía de implementación).
   ---------------------------------------------------------------- */
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE BITACORA_PAGO_CUOTA CASCADE CONSTRAINTS';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -942 THEN RAISE; END IF; -- solo se ignora tabla inexistente
END;
/

/* ================================================================
   BITACORA_PAGO_CUOTA
   Auditoría de pagos de cuotas (diseño acordado, guía paso M2).
   --------------------------------------------------------------
   Reglas de negocio que respalda:
     - Todo cambio del monto pagado de una cuota debe quedar
       registrado con su valor anterior y el nuevo, para
       trazabilidad de la operación (auditoría).
     - La clave primaria es un IDENTITY (patrón usado en BD_KOPERA,
       igual que APORTE_A_SBIF o FORMA_PAGO): Oracle genera el id,
       nadie debe insertarlo a mano.
     - La clave foránea compuesta apunta a la cuota afectada
       (CUOTA_CREDITO_CLIENTE tiene PK (nro_solic_credito, nro_cuota)).
   ================================================================ */
CREATE TABLE BITACORA_PAGO_CUOTA
(
    id_bitacora            NUMBER(10) GENERATED ALWAYS AS IDENTITY
                           MINVALUE 1 MAXVALUE 9999999999
                           INCREMENT BY 1 START WITH 1 NOT NULL ENABLE,
    nro_solic_credito      NUMBER(10) NOT NULL,
    nro_cuota              NUMBER(2)  NOT NULL,
    fecha_evento           DATE       DEFAULT SYSDATE NOT NULL,
    usuario_evento         VARCHAR2(30) DEFAULT USER NOT NULL,
    monto_pagado_anterior  NUMBER(10),
    monto_pagado_nuevo     NUMBER(10),
    valor_cuota            NUMBER(10),
    saldo_resultante       NUMBER(10),
    cod_forma_pago         NUMBER(2),
    CONSTRAINT PK_BITACORA_PAGO_CUOTA PRIMARY KEY (id_bitacora),
    CONSTRAINT FK_BITACORA_CUOTA
        FOREIGN KEY (nro_solic_credito, nro_cuota)
        REFERENCES CUOTA_CREDITO_CLIENTE (nro_solic_credito, nro_cuota)
);

COMMENT ON TABLE  BITACORA_PAGO_CUOTA IS
    'Auditoría de pagos: una fila por cada cuota cuyo monto_pagado cambia (la inserta trg_cuota_bitacora).';
COMMENT ON COLUMN BITACORA_PAGO_CUOTA.fecha_evento IS
    'Fecha y hora en que se ejecutó el pago (SYSDATE al momento del UPDATE).';
COMMENT ON COLUMN BITACORA_PAGO_CUOTA.usuario_evento IS
    'Usuario de base de datos que ejecutó la operación (USER).';
COMMENT ON COLUMN BITACORA_PAGO_CUOTA.monto_pagado_anterior IS
    'Pago acumulado de la cuota ANTES del UPDATE (:OLD.monto_pagado; NULL si era primera vez).';
COMMENT ON COLUMN BITACORA_PAGO_CUOTA.monto_pagado_nuevo IS
    'Pago acumulado de la cuota DESPUÉS del UPDATE (:NEW.monto_pagado).';
COMMENT ON COLUMN BITACORA_PAGO_CUOTA.saldo_resultante IS
    'Saldo por pagar recalculado por trg_cuota_valida_pago (valor_cuota - monto_pagado).';

/* ----------------------------------------------------------------
   VERIFICACIÓN (ejecutar a mano tras crear la tabla)
   ----------------------------------------------------------------
   DESC bitacora_pago_cuota;

   SELECT constraint_name, constraint_type
     FROM user_constraints
    WHERE table_name = 'BITACORA_PAGO_CUOTA'
    ORDER BY constraint_type;
   -- Esperado: 1 P (PK_BITACORA_PAGO_CUOTA) y 1 R (FK_BITACORA_CUOTA)

   La tabla quedará en 0 filas: la inserta trg_cuota_bitacora
   (script 04) y las pruebas se hacen en 05_pruebas_integracion.sql.
   ---------------------------------------------------------------- */
