# KOPERA — Proyecto de Bases de Datos

Proyecto académico del **Taller de Base de Datos (BDY1103, sección 004D)**. Implementa en Oracle una base de datos para KOPERA, una entidad financiera ficticia, y rutinas PL/SQL para consultar y procesar su cartera de clientes.

El modelo contempla clientes, sucursales y ubicación geográfica, créditos y cuotas, productos de inversión, movimientos de ahorro, formas de pago y aportes a la SBIF. Incluye datos de ejemplo para ejecutar los reportes y pruebas.

## Evaluaciones

| Evaluación | Qué entrega | Dónde está |
|---|---|---|
| **Parcial 2** | Modelo relacional en Oracle + PL/SQL (paquete, procedimientos y triggers) | `Kopera/procedimiento_pl-sql/`, entregables en `docs/eva2/` |
| **Parcial 3** | Migración a **MongoDB Atlas** como modelo NoSQL + CRUD en Python | `Kopera/scripts/`, entregables en `docs/eva3/` |

### Arquitectura de la Evaluación 3

Oracle sigue siendo la **fuente de verdad** y el motor de la automatización (el PL/SQL de la
EVA2 queda intacto). Python es el **puente**: extrae de Oracle, transforma, carga en Atlas y
ejecuta el CRUD. MongoDB Atlas es la **capa de consulta y colección**, con un documento
desnormalizado por cliente.

```text
Oracle (fuente de verdad)          Python (puente)                 Atlas (consulta)
┌──────────────────────┐          ┌─────────────────────┐        ┌────────────────────┐
│ 16 tablas + PL/SQL   │ ───────► │ extracción          │ ─────► │ clientes           │
│ package + triggers   │          │ transformación      │        │ catalogos          │
│                      │          │ carga + CRUD        │        │ bitacora_pagos     │
└──────────────────────┘          └─────────────────────┘        │ procesos_mensuales │
                                                              └────────────────────┘
```

El modelo documental **embebe** los agregados: cada cliente es un documento con sus
`creditos[].cuotas[]` y sus `inversiones[].movimientos[]`. Los catálogos maestro se quedan en
su propia colección para no duplicar nombres. Las reglas de los triggers de Oracle se
replican en la capa de aplicación (`validaciones.py`), porque el tier gratuito **M0** de Atlas
no permite Atlas Triggers ni Atlas Functions.

## Funcionalidades

### Oracle (Evaluación Parcial 2)

- Creación del esquema relacional y carga de datos de referencia.
- Reporte consolidado de la cartera de créditos y registro de pagos parciales o totales.
- Paquete de análisis por cliente: saldos, pagos, cuotas vencidas, ahorro, alertas y clasificación financiera.
- Validaciones automáticas para pagos de cuotas, abonos y rescates de productos de inversión.
- Bitácora de auditoría de cambios en los pagos de cuotas.
- Pruebas de integración de los procedimientos, paquete y triggers.

### Python + MongoDB Atlas (Evaluación Parcial 3)

- **Extracción set-based** desde Oracle, reutilizando las funciones del package `pk_analisis_kopera`
  para no duplicar la lógica de negocio.
- **Transformación**: corrección de los caracteres dañados (U+FFFD), anidado por agregado y
  reclasificación a `OPORTUNIDAD` de los clientes sin créditos.
- **Carga** en cuatro colecciones con validador `$jsonSchema` (`validationLevel: strict`) y 12 índices.
- **CRUD completo en Python** con 18 casos etiquetados (C1–C4, R1–R7, U1–U4, D1–D3),
  re-ejecutable: al terminar restaura la base a su estado original.
- **Verificación de correspondencia** Oracle ↔ Atlas, cliente por cliente.

## Estructura del repositorio

```text
.
├── docker-compose.yml
├── Kopera/
│   ├── BD_KOPERA.SQL
│   ├── CreacionUsuarios.sql
│   ├── resumen_financiero_kopera.sql
│   ├── procedimiento_pl-sql/          (Evaluación 2)
│   │   ├── 01_tablas_apoyo.sql
│   │   ├── 02_procedimientos.sql
│   │   ├── 03_package_analisis_kopera.sql
│   │   ├── 04_triggers.sql
│   │   └── 05_pruebas_integracion.sql
│   └── scripts/                       (Evaluación 3)
│       ├── config.py                  configuración + conexiones
│       ├── dbms_output.py             captura de DBMS_OUTPUT
│       ├── plan_pagos.py              DATA: plan de cobranza editable
│       ├── poblar_bitacora.py         proceso mensual de cobranza
│       ├── extraccion_oracle.py       ETAPA 1: lectura desde Oracle
│       ├── transformacion.py          ETAPA 2: limpieza y anidado
│       ├── carga_mongodb.py           ETAPA 3: carga con $jsonSchema e índices
│       ├── validaciones.py            reglas replicadas de los triggers
│       ├── crud_mongodb.py            CRUD en Python (18 casos)
│       ├── verificacion_correspondencia.py  prueba Oracle ↔ Atlas
│       ├── revision_estatica.py       verificador de typos y caracteres
│       └── etl_principal.py           orquestador del pipeline
└── docs/
    ├── eva2/                          entregables de la Evaluación 2
    └── eva3/                          entregables de la Evaluación 3
```

> El pipeline en JavaScript/mongosh que contributed el equipo (`KOPERA_EP3_scripts/`) se
> movió **fuera de este repositorio**, a `~/Documentos/universidad/KOPERA_EP3_scripts/`, para
> que no se confunda con el camino principal. Queda como aporte de referencia.

- `BD_KOPERA.SQL`: crea las tablas, relaciones y datos de ejemplo.
- `procedimiento_pl-sql/`: objetos y pruebas de la segunda evaluación, organizados en el orden de ejecución.
- `resumen_financiero_kopera.sql`: reporte financiero integrado de solo lectura; requiere que el esquema ya esté cargado.
- `CreacionUsuarios.sql`: script de administración de usuario ADMIN_PROYECTO y permisos para este usuario.
- `scripts/`: pipeline en Python de la tercera evaluación. Las credenciales se leen del `.env` de la raíz, que **nunca** se versiona.

## Requisitos

- Docker y Docker Compose.
- Oracle Database Free (se inicia mediante el archivo `docker-compose.yml`).
- Oracle SQL Developer o Extension SQL Developer Visual Studio Code. 
- Python 3.10+ con `pymongo` y `oracledb` (para la Evaluación 3).
- Un proyecto en **MongoDB Atlas** con el tier gratuito **M0**.

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

## Puesta en marcha de la Evaluación 3 (Oracle → MongoDB Atlas)

1. **Prepara el entorno de Python** en la raíz del repositorio:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install pymongo oracledb python-dotenv
   ```

2. **Configura las credenciales** en un archivo `.env` en la raíz del repositorio (este archivo
   **nunca** se versiona):

   ```dotenv
   ORACLE_USER=ADMIN_PROYECTO
   ORACLE_PASSWORD=...
   ORACLE_HOST=127.0.0.1
   ORACLE_PORT=1521
   ORACLE_SERVICE_NAME=FREEPDB1
   MONGODB_URI=mongodb+srv://...
   MONGODB_DATABASE=kopera
   ```

3. **Autoriza tu IP en Atlas.** Tu IP pública es dinámica: agrégala en *Network Access* del
   proyecto. Si la conexión falla con `SSL handshake failed: tlsv1 alert internal error`, el
   problema es la IP, no el código.

4. **Ejecuta el pipeline**, en este orden:

   ```bash
   .venv/bin/python Kopera/scripts/revision_estatica.py            # revisión del código
   .venv/bin/python Kopera/scripts/poblar_bitacora.py --simular   # ensayo del proceso de cobranza
   .venv/bin/python Kopera/scripts/poblar_bitacora.py             # puebla la bitácora en Oracle
   .venv/bin/python Kopera/scripts/etl_principal.py --simular      # ETL sin escribir en Atlas
   .venv/bin/python Kopera/scripts/etl_principal.py                # carga real en Atlas
   .venv/bin/python Kopera/scripts/crud_mongodb.py                # CRUD en Python (18 casos)
   .venv/bin/python Kopera/scripts/verificacion_correspondencia.py # prueba Oracle ↔ Atlas
   ```

> **El orden importa:** la bitácora se puebla **antes** del ETL, porque los pagos cambian
> cuotas, saldos y clasificaciones.

## Precauciones

- `BD_KOPERA.SQL` elimina y vuelve a crear tablas y secuencias antes de cargar los datos de ejemplo. **Reejecutarlo borra los datos actuales del esquema.**
- `CreacionUsuarios.sql` elimina el usuario `ADMIN_PROYECTO` con `CASCADE` antes de crearlo. Úsalo solo en este entorno académico y considera su efecto antes de volver a ejecutarlo.
- El volumen `oracle_data` conserva los datos del contenedor. `docker compose down` detiene los servicios, pero no elimina ese volumen; no uses `docker compose down -v` salvo que quieras borrar la base de datos persistida.
