# KOPERA — Proyecto de Bases de Datos

Proyecto académico del **Taller de Base de Datos (BDY1103, sección 004D)**. Implementa en Oracle una base de datos para KOPERA, una entidad financiera ficticia, y rutinas PL/SQL para consultar y procesar su cartera de clientes.

El modelo contempla clientes, sucursales y ubicación geográfica, créditos y cuotas, productos de inversión, movimientos de ahorro, formas de pago y aportes a la SBIF. Incluye datos de ejemplo para ejecutar los reportes y pruebas.

## Funcionalidades

- Creación del esquema relacional y carga de datos de referencia.
- Reporte consolidado de la cartera de créditos y registro de pagos parciales o totales.
- Paquete de análisis por cliente: saldos, pagos, cuotas vencidas, ahorro, alertas y clasificación financiera.
- Validaciones automáticas para pagos de cuotas, abonos y rescates de productos de inversión.
- Bitácora de auditoría de cambios en los pagos de cuotas.
- Pruebas de integración de los procedimientos, paquete y triggers.

## Estructura del repositorio

```text
.
├── docker-compose.yml
├── Kopera/
│   ├── BD_KOPERA.SQL
│   ├── CreacionUsuarios.sql
│   ├── resumen_financiero_kopera.sql
│   └── procedimiento_pl-sql/
│       ├── 01_tablas_apoyo.sql
│       ├── 02_procedimientos.sql
│       ├── 03_package_analisis_kopera.sql
│       ├── 04_triggers.sql
│       └── 05_pruebas_integracion.sql
```

- `BD_KOPERA.SQL`: crea las tablas, relaciones y datos de ejemplo.
- `procedimiento_pl-sql/`: objetos y pruebas de la segunda evaluación, organizados en el orden de ejecución.
- `resumen_financiero_kopera.sql`: reporte financiero integrado de solo lectura; requiere que el esquema ya esté cargado.
- `CreacionUsuarios.sql`: script de administración de usuario ADMIN_PROYECTO y permisos para este usuario.

## Requisitos

- Docker y Docker Compose.
- Oracle Database Free (se inicia mediante el archivo `docker-compose.yml`).
- Oracle SQL Developer o Extension SQL Developer Visual Studio Code. 

## Puesta en marcha

1. **Configura las credenciales** antes de iniciar Oracle. Cambia la contraseña configurada en `docker-compose.yml` y la contraseña definida en `Kopera/CreacionUsuarios.sql`; no reutilices credenciales reales en un entorno compartido.
2. Inicia la base de datos desde la raíz del proyecto:

   ```bash
   docker compose up -d
   ```

   Espera a que Oracle termine de inicializarse antes de conectarte. El servicio publica el puerto `1521` en `localhost`.

3. En SQL Developer, conéctate al servicio `FREEPDB1` como administrador de Oracle y ejecuta `Kopera/CreacionUsuarios.sql` para crear `ADMIN_PROYECTO`. En una instalación nueva, comenta o elimina temporalmente la instrucción inicial `DROP USER`, ya que el usuario aún no existe. En ejecuciones posteriores, ten presente que esa instrucción elimina el usuario y sus objetos antes de crearlo de nuevo.
4. Conéctate como `ADMIN_PROYECTO` al mismo servicio y ejecuta `Kopera/BD_KOPERA.SQL`.
5. Para instalar los objetos de la evaluación, ejecuta como `ADMIN_PROYECTO`, en este orden:

   1. `Kopera/procedimiento_pl-sql/01_tablas_apoyo.sql`
   2. `Kopera/procedimiento_pl-sql/02_procedimientos.sql`
   3. `Kopera/procedimiento_pl-sql/03_package_analisis_kopera.sql`
   4. `Kopera/procedimiento_pl-sql/04_triggers.sql`
   5. `Kopera/procedimiento_pl-sql/05_pruebas_integracion.sql`

   Ejecuta cada archivo completo (por ejemplo, con **F5** en SQL Developer) y habilita `DBMS_OUTPUT` para ver reportes y resultados.

El reporte `Kopera/resumen_financiero_kopera.sql` es opcional y puede ejecutarse como `ADMIN_PROYECTO` después de cargar el esquema. No crea objetos ni modifica datos.

## Precauciones

- `BD_KOPERA.SQL` elimina y vuelve a crear tablas y secuencias antes de cargar los datos de ejemplo. **Reejecutarlo borra los datos actuales del esquema.**
- `CreacionUsuarios.sql` elimina el usuario `ADMIN_PROYECTO` con `CASCADE` antes de crearlo. Úsalo solo en este entorno académico y considera su efecto antes de volver a ejecutarlo.
- El volumen `oracle_data` conserva los datos del contenedor. `docker compose down` detiene los servicios, pero no elimina ese volumen; no uses `docker compose down -v` salvo que quieras borrar la base de datos persistida.
