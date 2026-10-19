/* ============================================================
   CREACIÓN DE USUARIO ADMINISTRADOR, OPERADORES Y PERMISOS
   Oracle Database
   ============================================================ */

SET SERVEROUTPUT ON;

/* ============================================================
   1. CREACIÓN DEL USUARIO ADMINISTRADOR
   ============================================================ */
DROP USER ADMIN_PROYECTO cascade;
CREATE USER ADMIN_PROYECTO IDENTIFIED BY "Duocsemestre#4"
DEFAULT TABLESPACE USERS
TEMPORARY TABLESPACE TEMP
QUOTA UNLIMITED ON USERS;

GRANT CREATE SESSION,
      CREATE TABLE,
      CREATE VIEW,
      CREATE SEQUENCE,
      CREATE PROCEDURE,
      CREATE TRIGGER,
      CREATE SYNONYM,
      CREATE TYPE,
      CREATE MATERIALIZED VIEW,
      CREATE JOB
TO ADMIN_PROYECTO;

