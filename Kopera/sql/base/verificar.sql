/* ============================================================
   VERIFICACIÓN DE LA INSTALACIÓN DE KOPERA
   Oracle Database

   Corre este script después de los pasos 4, 5 y 6 de la guía.
   Todo tiene que salir como dice el comentario al lado.

   Cómo se corre:
       ./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/verificar.sql
   ============================================================ */

SET SERVEROUTPUT ON;
SET PAGESIZE 200;
SET LINESIZE 200;
COLUMN object_type FORMAT A20;
COLUMN status FORMAT A10;
COLUMN tabla FORMAT A30;
COLUMN nro_cliente FORMAT 999999;
COLUMN clasificacion FORMAT A20;
COLUMN saldo FORMAT 999999999999;

/* ---------------------------------------------------------------
   1. OBJETOS PL/SQL
   Deben ser 8 y TODOS en estado VALID.
   Si alguno sale INVALID, el archivo que lo crea está mal copiado:
   volvé a correrlo.
   --------------------------------------------------------------- */
PROMPT === 1. Objetos PL/SQL (esperado: 8, todos VALID) ===
SELECT object_type, status, COUNT(*) AS total
  FROM user_objects
 WHERE object_type IN ('PROCEDURE', 'PACKAGE', 'PACKAGE BODY', 'TRIGGER')
 GROUP BY object_type, status
 ORDER BY object_type;

/* ---------------------------------------------------------------
   2. CANTIDAD DE TABLAS
   Esperado: 17 (16 del modelo + BITACORA_PAGO_CUOTA de apoyo).
   --------------------------------------------------------------- */
PROMPT
PROMPT === 2. Tablas en el esquema (esperado: 17) ===
SELECT COUNT(*) AS tablas FROM user_tables;

/* ---------------------------------------------------------------
   3. DATOS DE EJEMPLO
   Esperado: 130 / 25 / 519 / 134 / 345
   --------------------------------------------------------------- */
PROMPT
PROMPT === 3. Datos de ejemplo (esperado: 130 / 25 / 519 / 134 / 345) ===
SELECT 'CLIENTE' AS tabla, COUNT(*) AS filas FROM cliente
UNION ALL SELECT 'CREDITO_CLIENTE', COUNT(*) FROM credito_cliente
UNION ALL SELECT 'CUOTA_CREDITO_CLIENTE', COUNT(*) FROM cuota_credito_cliente
UNION ALL SELECT 'PRODUCTO_INVERSION_CLIENTE', COUNT(*) FROM producto_inversion_cliente
UNION ALL SELECT 'MOVIMIENTO', COUNT(*) FROM movimiento
UNION ALL SELECT 'BITACORA_PAGO_CUOTA', COUNT(*) FROM bitacora_pago_cuota;

/* ---------------------------------------------------------------
   4. LAS FUNCIONES DEL PACKAGE RESPONDEN
   Esperado: 130 clientes con saldo calculado y 1 clasificacion.
   --------------------------------------------------------------- */
PROMPT
PROMPT === 4. El package responde (esperado: 130 clientes y una clasificacion) ===
SELECT COUNT(*) AS clientes_analizados
  FROM cliente
 WHERE pk_analisis_kopera.fn_saldo_pendiente(nro_cliente) >= 0;

SELECT nro_cliente,
       pk_analisis_kopera.fn_clasifica_cliente(nro_cliente) AS clasificacion,
       pk_analisis_kopera.fn_saldo_pendiente(nro_cliente) AS saldo
  FROM cliente
 WHERE ROWNUM <= 5;

/* ---------------------------------------------------------------
   5. LOS TRIGGERS FUNCIONAN
   Se espera que el pago excedido sea RECHAZADO (ORA-20001).
   Que salga el error es la prueba de que el trigger está vivo.
   --------------------------------------------------------------- */
PROMPT
PROMPT === 5. Los triggers rechazan un pago excedido (esperado: ORA-20001) ===
DECLARE
  v_error VARCHAR2(400);
BEGIN
  UPDATE cuota_credito_cliente
     SET monto_pagado = valor_cuota + 1
   WHERE nro_solic_credito = 2001 AND nro_cuota = 1;
  DBMS_OUTPUT.PUT_LINE('ERROR: el pago excedido fue aceptado.');
EXCEPTION
  WHEN OTHERS THEN
    v_error := SQLERRM;
    DBMS_OUTPUT.PUT_LINE('OK: el trigger lo rechazo -> ' || SUBSTR(v_error, 1, 80));
    ROLLBACK;
END;
/

PROMPT
PROMPT === Verificacion terminada. Si todo lo anterior salio bien, la base esta lista. ===

EXIT
