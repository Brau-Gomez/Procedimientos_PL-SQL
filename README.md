# KOPERA — Proyecto de Bases de Datos

Proyecto académico del **Taller de Base de Datos (BDY1103, sección 004D)**.
Implementa en Oracle una base de datos para KOPERA, una entidad financiera
ficticia, y rutinas PL/SQL para consultar y procesar su cartera de clientes.

El modelo contempla clientes, sucursales y ubicación geográfica, créditos y
cuotas, productos de inversión, movimientos de ahorro, formas de pago y
aportes a la SBIF. Incluye datos de ejemplo para ejecutar los reportes y
pruebas.

| Evaluación | Qué entrega | Dónde está |
|---|---|---|
| **Parcial 2** | Modelo relacional en Oracle + PL/SQL (paquete, procedimientos y triggers) | [`Kopera/sql/`](Kopera/sql/) · [README del PL/SQL](Kopera/sql/README.md) |
| **Parcial 3** | Migración a **MongoDB Atlas** como modelo NoSQL + CRUD en Python + interfaz web | [`Kopera/etl/`](Kopera/etl/) · [`Kopera/app/`](Kopera/app/) · [README del ETL](Kopera/etl/README.md) |

### Arquitectura de la Evaluación 3

Oracle sigue siendo la **fuente de verdad** y el motor de la automatización
(el PL/SQL de la EVA2 queda intacto). Python es el **puente**: extrae de
Oracle, transforma, carga en Atlas y ejecuta el CRUD. MongoDB Atlas es la
**capa de consulta y colección**, con un documento desnormalizado por cliente.

```text
Oracle (fuente de verdad)          Python (puente)                 Atlas (consulta)
┌──────────────────────┐          ┌─────────────────────┐        ┌────────────────────┐
│ 16 tablas + PL/SQL   │ ───────► │ extracción          │ ─────► │ clientes           │
│ package + triggers   │          │ transformación      │        │ catalogos          │
│                      │          │ carga + CRUD        │        │ bitacora_pagos     │
└──────────────────────┘          └─────────────────────┘        │ procesos_mensuales │
                                                               └────────────────────┘
```

El modelo documental **embebe** los agregados: cada cliente es un documento
con sus `creditos[].cuotas[]` y sus `inversiones[].movimientos[]`. Los
catálogos maestro se quedan en su propia colección para no duplicar nombres.
Las reglas de los triggers de Oracle se replican en la capa de aplicación
(`validaciones.py`), porque el tier gratuito **M0** de Atlas no permite
Atlas Triggers ni Atlas Functions.

---

## Levantar el proyecto con Docker

Son dos servicios independientes, cada uno con su compose:

| Servicio | Compose | Puerto | Para qué |
|---|---|---|---|
| **Base de datos** | `docker-compose.yml` | `1521` | Oracle Database Free: el esquema y el PL/SQL |
| **Aplicación web** | `docker-compose.app.yml` | `8501` | Interfaz Streamlit para consultar Atlas |

> La app va en un compose **aparte** a propósito: la app solo lee MongoDB, y
> levantar Oracle (2 GB de RAM) para mirar reportes no tiene sentido.

### Requisitos previos

- Docker y Docker Compose.
- Un proyecto en **MongoDB Atlas** con el tier gratuito **M0**.
- La IP pública de tu máquina autorizada en *Network Access* de Atlas
  (tu IP es dinámica: la sacas con `curl -s https://api.ipify.org`).

### Paso 1 — Configura las credenciales

```bash
cp .env.example .env
```

Edita `.env` y pon la contraseña que quieras para `ADMIN_PROYECTO`. Ese
archivo **no se versiona**: está en `.gitignore`. La plantilla `.env.example`
sí se versiona, porque no contiene ningún secreto.

```dotenv
ORACLE_USER=ADMIN_PROYECTO
ORACLE_PASSWORD="tu_contrasena_aqui"
ORACLE_HOST=127.0.0.1
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=FREEPDB1
MONGODB_URI="mongodb+srv://USUARIO:CLAVE@cluster0.xxxxx.mongodb.net"
MONGODB_DATABASE=kopera
```

`docker-compose.yml` lee ese mismo `.env` para la contraseña del contenedor,
así que no hay que tocar el compose para cambiar la clave. Si falta la
variable, `docker compose` aborta con un mensaje explícito en vez de levantar
el contenedor con una contraseña vacía.

> Entrecomilla SIEMPRE las contraseñas: pueden llevar caracteres especiales
> como `#` o `$` que, sin comillas, se interpretan como comentario o como
> variable.

### Paso 2 — Levanta la base de datos

```bash
docker compose up -d
```

Espera a que Oracle termine de inicializarse. En arranque en frío tarda entre
2 y 4 minutos (la primera vez, más: crea la base).

```bash
docker ps        # la línea de "oracle-free" debe decir "healthy"
```

### Paso 3 — Carga el esquema y el PL/SQL

Necesitas un cliente SQL: Oracle SQL Developer, la extensión *SQL Developer
for VS Code*, o `sqlplus`.

1. Conéctate al servicio `FREEPDB1` como `ADMIN_PROYECTO` y crea el usuario
   con `Kopera/sql/base/CreacionUsuarios.sql.example`.
2. Ejecuta `Kopera/sql/base/BD_KOPERA.SQL`.
3. Ejecuta, en este orden, los cinco scripts de `Kopera/sql/`:
   `01_tablas_apoyo.sql` → `02_procedimientos.sql` →
   `03_package_analisis_kopera.sql` → `04_triggers.sql` →
   `05_pruebas_integracion.sql`.

El detalle completo, con las instrucciones paso a paso y cómo verificar que
quedó todo `VALID`, está en el
**[README del PL/SQL](Kopera/sql/README.md)**.

### Paso 4 — Levanta la aplicación web

```bash
docker compose -f docker-compose.app.yml up -d --build
```

Abre <http://localhost:8501>.

El código va montado como volumen: al guardar un archivo de `Kopera/app/`,
Streamlit recarga solo. No hace falta rebuild, salvo que cambien las
dependencias.

Más detalles en el **[README de la app](Kopera/app/README.md)**.

### Comandos útiles

```bash
docker compose ps                                   # estado de los servicios
docker compose logs -f oracle                      # log de Oracle
docker compose down                                 # detener (NO borra los datos)
docker compose -f docker-compose.app.yml logs -f web
docker compose -f docker-compose.app.yml down
```

> ⚠️ **Nunca uses `docker compose down -v`**: la `-v` borra el volumen
> `oracle_data` y pierdes el esquema y los datos.

### Cargar la base de Atlas (opcional)

Para ver datos en la app hay que correr el ETL, que escribe en Atlas:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

.venv/bin/python Kopera/etl/poblar_bitacora.py            # puebla la bitácora en Oracle
.venv/bin/python Kopera/etl/etl_principal.py               # carga real en Atlas
```

El orden importa y el resto de los comandos están en el
**[README del ETL](Kopera/etl/README.md)**.

---

## Estructura del repositorio

```text
.
├── README.md                    este archivo
├── docker-compose.yml           Oracle Database Free (la clave sale del .env)
├── docker-compose.app.yml       interfaz web (Streamlit)
├── .env.example                 plantilla de credenciales (SÍ se versiona)
├── .dockerignore                qué NO se manda como contexto de build
├── requirements.txt             dependencias fijadas del ETL
├── requirements-dev.txt         lo que hace falta para correr las pruebas
├── pytest.ini
├── Kopera/
│   ├── README.md                índice del proyecto
│   ├── sql/                     Evaluación 2 — Oracle y PL/SQL
│   │   ├── README.md            ← instrucciones de ejecución del PL/SQL
│   │   ├── 01_tablas_apoyo.sql
│   │   ├── 02_procedimientos.sql
│   │   ├── 03_package_analisis_kopera.sql
│   │   ├── 04_triggers.sql
│   │   ├── 05_pruebas_integracion.sql
│   │   └── base/
│   │       ├── CreacionUsuarios.sql.example   plantilla SIN la contraseña real
│   │       ├── BD_KOPERA.SQL                  tablas, relaciones y datos de ejemplo
│   │       └── resumen_financiero_kopera.sql  reporte de solo lectura
│   ├── etl/                     Evaluación 3 — pipeline en Python
│   │   ├── README.md            ← instrucciones de ejecución del ETL
│   │   ├── config.py            configuración + las dos conexiones
│   │   ├── dbms_output.py       captura de DBMS_OUTPUT
│   │   ├── conexion_oracle.py   prueba de conexión a Oracle
│   │   ├── conexion_mongodb.py  prueba de conexión a Atlas
│   │   ├── plan_pagos.py        DATA: plan de cobranza editable
│   │   ├── poblar_bitacora.py   proceso mensual de cobranza
│   │   ├── extraccion_oracle.py ETAPA 1: lectura desde Oracle
│   │   ├── transformacion.py    ETAPA 2: limpieza y anidado
│   │   ├── validaciones.py      reglas replicadas de los triggers
│   │   ├── carga_mongodb.py     ETAPA 3: carga con $jsonSchema e índices
│   │   ├── crud_mongodb.py      CRUD en Python (18 casos)
│   │   ├── verificacion_correspondencia.py   prueba Oracle ↔ Atlas
│   │   ├── revision_estatica.py verificador de typos, imports y aridad
│   │   └── etl_principal.py     orquestador del pipeline
│   └── app/                     Evaluación 3 — interfaz web (Streamlit)
│       ├── README.md
│       ├── main.py              navegación y estado de la conexión
│       ├── config_app.py        cliente MongoDB (cacheado)
│       ├── consultas.py         agregaciones de LECTURA
│       ├── operaciones.py        ESCRITURA: pagos y movimientos
│       ├── formato.py           moneda CLP, fechas ISO, semáforos
│       ├── ui.py                paleta, CSS, tarjetas KPI, tablas
│       ├── graficos.py          dona, barras de estado y atraso
│       ├── vistas/              una función render() por pantalla
│       ├── requirements.txt
│       ├── Dockerfile
│       └── .streamlit/config.toml
├── tests/                       pruebas unitarias (pytest)
│   ├── conftest.py
│   ├── test_poblar_bitacora.py
│   ├── test_transformacion.py
│   └── test_validaciones.py
└── docs/                        entregables de las evaluaciones (SOLO en local)
    ├── eva2/
    └── eva3/
```

> `docs/` está en `.gitignore`: los `.docx`, `.pptx`, `.pdf` y `.zip` de las
> evaluaciones se quedan solo en la máquina, no se suben al repositorio.

> El pipeline en JavaScript/mongosh que contributed el equipo
> (`KOPERA_EP3_scripts/`) se movió **fuera de este repositorio**, a
> `~/Documentos/universidad/KOPERA_EP3_scripts/`, para que no se confunda con
> el camino principal. Queda como aporte de referencia.

---

## ¿Qué archivo necesito?

### Para levantar y configurar

| Quiero… | Dónde está |
|---|---|
| Levantar la base de datos | `docker-compose.yml` |
| Levantar la interfaz web | `docker-compose.app.yml` |
| Poner las credenciales | `.env` (plantilla: `.env.example`) |
| Entender las variables | `Kopera/etl/config.py` |

### Para la base de datos (Evaluación 2)

| Quiero… | Dónde está |
|---|---|
| Crear el usuario `ADMIN_PROYECTO` | `Kopera/sql/base/CreacionUsuarios.sql.example` |
| Crear las tablas y los datos de ejemplo | `Kopera/sql/base/BD_KOPERA.SQL` |
| Instalar el PL/SQL (tablas de apoyo, procedimientos, package, triggers) | `Kopera/sql/01_…` a `Kopera/sql/05_…` |
| Ver el resumen financiero | `Kopera/sql/base/resumen_financiero_kopera.sql` |
| Entender el PL/SQL y el orden de ejecución | **[Kopera/sql/README.md](Kopera/sql/README.md)** |

### Para el pipeline (Evaluación 3)

| Quiero… | Dónde está |
|---|---|
| Ver el pipeline completo de punta a punta | `Kopera/etl/etl_principal.py` |
| Cambiar el plan de cobranza mensual | `Kopera/etl/plan_pagos.py` |
| Revisar las reglas de negocio replicadas | `Kopera/etl/validaciones.py` |
| Revisar la limpieza de caracteres y el anidado | `Kopera/etl/transformacion.py` |
| Revisar los validadores `$jsonSchema` y los índices | `Kopera/etl/carga_mongodb.py` |
| Verificar que Oracle responde | `Kopera/etl/conexion_oracle.py` |
| Verificar que Atlas responde | `Kopera/etl/conexion_mongodb.py` |
| Entender el ETL y el orden de ejecución | **[Kopera/etl/README.md](Kopera/etl/README.md)** |

### Para la interfaz web

| Quiero… | Dónde está |
|---|---|
| El listado de clientes | `Kopera/app/vistas/clientes.py` |
| La ficha de un cliente | `Kopera/app/vistas/ficha.py` |
| La cartera de créditos | `Kopera/app/vistas/cartera.py` |
| Las inversiones y sus movimientos | `Kopera/app/vistas/inversiones.py` |
| Los catálogos maestros | `Kopera/app/vistas/catalogos.py` |
| El historial de procesos mensuales | `Kopera/app/vistas/procesos.py` |
| El panel general | `Kopera/app/vistas/panel.py` |
| Registrar pagos y movimientos | `Kopera/app/vistas/operaciones.py` |
| Cambiar el estilo, los colores y los gráficos | `Kopera/app/ui.py`, `formato.py`, `graficos.py` |
| Entender la app | **[Kopera/app/README.md](Kopera/app/README.md)** |

---

## Requisitos

- Docker y Docker Compose.
- Oracle SQL Developer o la extensión SQL Developer para Visual Studio Code.
- Python 3.10+ con las dependencias de `requirements.txt` (`pymongo`,
  `oracledb` y `python-dotenv`; para las pruebas, `requirements-dev.txt` agrega
  `pytest`).
- Un proyecto en **MongoDB Atlas** con el tier gratuito **M0**.

---

## Pruebas y revisión estática

```bash
.venv/bin/python -m pytest                       # 60 passed
.venv/bin/python Kopera/etl/revision_estatica.py # [OK] 14 scripts revisados
```

- `revision_estatica.py` revisa los 14 scripts sin necesidad de base de
  datos: nombres no definidos, caracteres dañados, imports rotos, imports sin
  usar, **llamadas con la aridad equivocada** y claves duplicadas en
  diccionarios.
- `tests/` contiene las pruebas unitarias de las funciones puras (las 4
  reglas de negocio y la transformación). No necesitan Oracle ni Atlas.

---

## Funcionalidades

### Oracle (Evaluación Parcial 2)

- Creación del esquema relacional y carga de datos de referencia.
- Reporte consolidado de la cartera de créditos y registro de pagos parciales
  o totales.
- Paquete de análisis por cliente: saldos, pagos, cuotas vencidas, ahorro,
  alertas y clasificación financiera.
- Validaciones automáticas para pagos de cuotas, abonos y rescates de
  productos de inversión.
- Bitácora de auditoría de cambios en los pagos de cuotas.
- Pruebas de integración de los procedimientos, paquete y triggers.

### Python + MongoDB Atlas (Evaluación Parcial 3)

- **Extracción set-based** desde Oracle, reutilizando las funciones del
  package `pk_analisis_kopera` para no duplicar la lógica de negocio.
- **Transformación**: corrección de los caracteres dañados (U+FFFD), anidado
  por agregado y reclasificación a `OPORTUNIDAD` de los clientes sin
  créditos.
- **Carga** en cuatro colecciones con validador `$jsonSchema`
  (`validationLevel: strict`) y 12 índices.
- **CRUD completo en Python** con 18 casos etiquetados (C1–C4, R1–R7, U1–U4,
  D1–D3), re-ejecutable: al terminar restaura la base a su estado original.
- **Verificación de correspondencia** Oracle ↔ Atlas, cliente por cliente.
- **Interfaz web** en Streamlit para consultar todo lo anterior.

---

## Precauciones

- `Kopera/sql/base/BD_KOPERA.SQL` elimina y vuelve a crear tablas y
  secuencias antes de cargar los datos de ejemplo. **Reejecutarlo borra los
  datos actuales del esquema.**
- `Kopera/sql/base/CreacionUsuarios.sql` (y su plantilla `.example`) elimina
  el usuario `ADMIN_PROYECTO` con `CASCADE` antes de crearlo. Úsalo solo en
  este entorno académico y considera su efecto antes de volver a ejecutarlo.
- El volumen `oracle_data` conserva los datos del contenedor. `docker compose
  down` detiene los servicios, pero no elimina ese volumen; no uses `docker
  compose down -v` salvo que quieras borrar la base de datos persistida.

---

## Secretos y credenciales

Estos tres archivos **no** se versionan (están en `.gitignore`):

| Archivo | Qué contiene | Qué se versiona en su lugar |
|---|---|---|
| `.env` | Contraseñas de Oracle y de Atlas | `.env.example` (plantilla vacía) |
| `Kopera/sql/base/CreacionUsuarios.sql` | La contraseña real de `ADMIN_PROYECTO` | `Kopera/sql/base/CreacionUsuarios.sql.example` |
| `atlas-credentials.env` | Credenciales de Atlas generadas por el panel | — |

Antes de subir cambios, comprueba que no se te cuele ningún secreto:

```bash
git ls-files | grep -E "\.env$|CreacionUsuarios\.sql$"   # no debe devolver nada
grep -rnE "mongodb\+srv://[^ \")']+:[^ \")']+@" Kopera/ --include="*.py"   # idem
```

Con estos cambios, **ninguna contraseña queda versionada**: `docker-compose.yml`
la toma del `.env` y el script de usuarios es una copia local sin versionar. Lo
único que viaja al repositorio son las plantillas vacías (`.env.example` y
`CreacionUsuarios.sql.example`), que sirven de referencia de qué variables hay
que completar.
