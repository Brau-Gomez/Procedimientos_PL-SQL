# KOPERA — Proyecto de Bases de Datos

Proyecto académico del **Taller de Base de Datos (BDY1103, sección 004D)**.
Implementa en Oracle una base de datos para KOPERA, una entidad financiera
ficticia, y rutinas PL/SQL para consultar y procesar su cartera de clientes.

---

## 📖 Cómo usar esta guía

Esta guía está escrita para que **la sigas de arriba abajo, sin saltarte
nada**. Cada paso tiene tres partes:

| Marca | Qué significa |
|---|---|
| **Ejecuta esto** | Copia el bloque de código y pégalo en la terminal. |
| **Deberías ver** | Lo que tiene que aparecer. Si no aparece, mira el troubleshooting del final. |
| **⚠️ Ojo** | Algo que puede romperte y conviene que sepas de antemano. |

> **Todos los comandos se ejecutan desde la raíz del repositorio** (la
> carpeta que tiene este README y el archivo `docker-compose.yml`). Si no
> estás ahí, la terminal te va a decir "no such file or directory".

---

## 1. Qué vas a montar (léelo antes de empezar)

Son **tres piezas** que se hablan entre sí:

```text
   1. ORACLE  ──────────────►  2. ATLAS  ◄──────────────  3. APP WEB
   La base de datos            La copia "moderna"          La pantalla
   (la fuente de verdad)       (MongoDB, en la nube)       que se ve
        ▲                                                        │
        └──────────────── 4. PYTHON (el ETL) ────────────────────┘
                            el que copia de un lado a otro
```

**1 · Oracle** — Donde vive el modelo relacional: clientes, créditos, cuotas,
inversiones, y el PL/SQL que aplica las reglas del negocio. Corre dentro de
Docker, en tu computador.

**2 · MongoDB Atlas** — Una base de datos en la nube (gratis, el plan M0).
Acá se copia la información de los clientes, pero **desnormalizada**: en vez
de 16 tablas separadas, hay **un documento por cliente** que trae todo lo suyo
dentro (sus créditos, sus cuotas, sus inversiones, sus movimientos).

**3 · La app web** — Una pantalla en Streamlit para mostrar los resultados y
hacer demostraciones en vivo.

**4 · El ETL** — El puente entre Oracle y Atlas. ETL significa
**E**xtract (extraer), **T**ransform (transformar) y **L**oad (cargar). Es un
programa que:

1. **Extrae** los datos de Oracle.
2. **Transforma**: les arregla los caracteres dañados (acentos que quedaron
   como `` en la base original) y los anida (junta los créditos dentro del
   cliente, las cuotas dentro del crédito, etc.).
3. **Valida**: les aplica las mismas reglas que aplican los triggers de
   Oracle, para que no llegue nada roto a Atlas.
4. **Carga**: los escribe en Atlas.

### ¿Qué es Docker?

Un programa que te deja ejecutar software (como Oracle) **dentro de una
caja aislada** de tu computador, sin que tengas que instalarlo ni
configurarlo. Por eso Oracle y Python no se instalan a mano: ya vienen
empaquetados.

### ¿Qué es un contenedor?

La "caja" donde corre el programa. En este proyecto hay dos:

| Contenedor | Qué corre | Puerto |
|---|---|---|
| `oracle-free` | La base de datos Oracle | `1521` |
| `kopera-web` | La interfaz web | `8501` |

Los contenedores se levantan y se apagan con `docker compose up` y
`docker compose down`, y sus datos se guardan en un "volumen" que sobrevive
aunque apagues el contenedor.

---

## 2. Antes de empezar

**Solo necesitas instalar Docker Desktop.** Todo lo demás va en Docker o se
instala con un comando.

| Necesitas | Cómo | Link |
|---|---|---|
| Docker Desktop | Descárgalo e instálalo. En Linux basta con Docker Engine + el plugin de Compose. | <https://www.docker.com/products/docker-desktop/> |

Comprueba que quedó instalado:

```bash
docker --version
docker compose version
```

**Deberías ver** las dos versiones. Si el comando no existe, Docker no está
instalado o no está en el PATH: reinicia la terminal o reinicia el
computador.

> **Necesitas una cuenta en MongoDB Atlas** (gratis). La creamos en el
> Paso 8, así que no hace falta ahora.

---

## 3. Guía paso a paso

### Paso 1 · Copia el repositorio

```bash
git clone https://github.com/Brau-Gomez/Procedimientos_PL-SQL.git
cd Procedimientos_PL-SQL
```

**Deberías ver** la lista de archivos (README.md, docker-compose.yml,
Kopera/, tests/...).

> Si no quieres usar git, en GitHub pulsá **Code → Download ZIP** y descomprimí
> la carpeta. Pero entonces no vas a poder subir tus cambios.

---

### Paso 2 · Crea el archivo de configuración

El proyecto lee las credenciales (contraseñas, puertos, URLs) de un archivo
llamado `.env`, que vive en la raíz del repositorio.

```bash
cp .env.example .env
```

Ahora abre `.env` con cualquier editor de texto y completa estos valores:

```dotenv
# ─── ORACLE ────────────────────────────────────────────────────────
ORACLE_USER=ADMIN_PROYECTO
ORACLE_PASSWORD="elige_una_contrasena_aqui"     ← ponle la que tú quieras
ORACLE_HOST=127.0.0.1
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=FREEPDB1

# ─── MONGODB ATLAS ─────────────────────────────────────────────────
MONGODB_URI="mongodb+srv://USUARIO:CLAVE@cluster0.xxxxx.mongodb.net"   ← lo sales en el Paso 8
MONGODB_DATABASE=kopera
```

> ⚠️ **Ojo**
> - **Siempre entrecomilla las contraseñas.** Si la tuya tiene `#` o `$` y no
>   la entrecomillas, la terminal la corta y el programa se confunde.
> - La contraseña de `ORACLE_PASSWORD` es la que vas a usar **para entrar a
>   la base de datos**. Anótala: la vas a necesitar en el Paso 4.
> - `MONGODB_URI` lo dejas por ahora: lo copias en el Paso 8.
> - El archivo `.env` **nunca** se sube a Git. Es tu información privada.

**Para comprobar que quedó bien**, puedes ver las variables sin mostrar la
contraseña:

```bash
grep ORACLE_USER .env
```

---

### Paso 3 · Levanta la base de datos Oracle

Crea el volumen de datos (una sola vez; el comando es idempotente, si ya
existe no hace nada y no borra nada):

```bash
docker volume create kopera_oracle_data
```

Después levanta el contenedor:

```bash
docker compose up -d
```

**La primera vez tarda bastante** (descarga una imagen de Oracle de ~2 GB).
Las siguientes, segundos.

**Deberías ver** algo como:

```
 Container oracle-free  Started
```

Ahora **espera a que Oracle termine de inicializarse**. Pregúntale el estado:

```bash
docker compose ps
```

**Deberías ver** una fila así:

```
NAME          IMAGE                                          STATUS
oracle-free   container-registry.oracle.com/database/free    Up 2 minutes (healthy)
```

La palabra **`healthy`** es la que importa. Si dice `starting`, todavía no
está listo: espera un poco y vuelve a preguntar. Tarda entre 2 y 4 minutos
desde cero.

> 📦 **Sobre el volumen de datos.** El `docker-compose.yml` declara el
> volumen con nombre explícito (`kopera_oracle_data`) a propósito. Sin eso,
> Docker Compose deriva el nombre del volumen del **nombre de la carpeta**
> donde estás, y si clonás el repo en otra carpeta te crea una base **vacía**
> con otro nombre. Con el nombre fijo, todos los clones comparten la misma
> base. El detalle está en la sección de problemas frecuentes.

**Comprobación rápida** — entra a la base y mira la versión:

```bash
docker exec -i oracle-free bash -lc "sqlplus -S / as sysdba@FREEPDB1 <<'EOF'
SET PAGESIZE 20
SELECT banner FROM v\$version WHERE ROWNUM=1;
EXIT
EOF"
```

**Deberías ver** algo con `Oracle AI Database ... Free`.

> ⚠️ **Ojo:** el comando usa `\$version` (con barra) porque estás dentro de
> una cadena de doble comillas. Si te da error de sintaxis, se te escapó la
> barra. Y usa `-i` (no `-it`): la `t` pide una terminal real y falla si
> copias el comando desde un script.

---

### Paso 4 · Crea el usuario de la base de datos

Oracle no deja crear usuarios sin permisos. El primero que hay que crear es
`ADMIN_PROYECTO`, que es el "dueño" de todas las tablas del proyecto.

> **⚖️ ¿Usás la extensión de SQL Developer o el helper?**
>
> Las dos formas sirven y **no son excluyentes**. El helper no reemplaza a la
> extensión: es el camino para los que no la tienen instalada.
>
> | | Extensión de SQL Developer | Helper `ejecutar-sql.sh` |
> |---|---|---|
> | **Qué es** | Un IDE de SQL (cliente gráfico) | Un atajo de terminal |
> | **Cómo llega a la base** | Por TCP al puerto `1521` publicado | Por `docker exec`, entrando al contenedor |
> | **Qué motor ejecuta** | Su driver de Oracle en tu PC | El `SQL*Plus` que ya viene **adentro** del contenedor |
> | **Hay que instalar** | La extensión + configurar un perfil de conexión | Nada |
> | **Interfaz** | Árbol de objetos, grilla de resultados, historial | Texto en la terminal |
>
> **Usa la extensión si** querés explorar la base (ver tablas, índices y
> constraints sin escribir consultas), correr **solo un trozo** de un archivo
> (seleccionás el `SELECT` y le das F5), ver los resultados en grilla, o
> depurar PL/SQL con breakpoints.
>
> **Usa el helper si** vas a **correr los scripts del proyecto** (los del
> PL/SQL, `verificar.sql`), si **no tenés** la extensión instalada, o si
> querés automatizar algo (es un comando, se puede meter en un script).
>
> Los dos terminan ejecutando el **mismo archivo `.sql` en la misma base**:
> lo que cambia es el camino y las herramientas alrededor.

**Opción A — Sin instalar nada (la más fácil).** El contenedor ya trae
SQL\*Plus adentro, así que usamos el script `ejecutar-sql.sh`:

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/CreacionUsuarios.sql.example
```

**Deberías ver**:

```
════════════════════════════════════════════════════════════════════
  Ejecutando: Kopera/sql/base/CreacionUsuarios.sql.example
════════════════════════════════════════════════════════════════════

User created.

Grant succeeded.
```

El script toma la contraseña **del `.env` automáticamente**. No tenés que
escribirla en ningún archivo.

> **Opción B — Con Oracle SQL Developer** (si ya lo tenés instalado):
> conéctate al servicio `FREEPDB1` como administrador de Oracle, abre
> `Kopera/sql/base/CreacionUsuarios.sql.example` y presioná **F5**. Cuando
> pida `ORACLE_PASSWORD`, escribe la misma clave que pusiste en el `.env`.
>
> Ojo: la extensión **necesita el puerto `1521` publicado** (el compose ya lo
> hace). El helper no lo necesita: entra por `docker exec`.

> ⚠️ **Ojo:** el script **borra** el usuario `ADMIN_PROYECTO` con `CASCADE`
> antes de recrearlo. Si lo corrés de nuevo, se borran también todas las
> tablas y datos que tengas cargados. Solo correlo una vez, al principio.

---

### Paso 5 · Carga las tablas y los datos de ejemplo

Este script crea las 16 tablas del modelo relacional y las llena con 130
clientes de prueba.

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/BD_KOPERA.SQL
```

**Deberías ver** un montón de líneas de `Table created.` y al final los
mensajes de carga de datos.

Tarda un par de minutos: son 130 clientes con todos sus créditos, cuotas,
inversiones y movimientos.

> ⚠️ **Ojo:** este script **borra las tablas antes de crearlas**. Si lo
> volvés a correr, perdés los datos que hayas cargado.

---

### Paso 6 · Instala el PL/SQL

Ahora sí, la automatización: el package con las funciones de análisis, los
procedimientos y los triggers. Son 5 archivos y **el orden importa**.

Córrelos **uno por uno**, en este orden:

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/01_tablas_apoyo.sql
./Kopera/sql/ejecutar-sql.sh Kopera/sql/02_procedimientos.sql
./Kopera/sql/ejecutar-sql.sh Kopera/sql/03_package_analisis_kopera.sql
./Kopera/sql/ejecutar-sql.sh Kopera/sql/04_triggers.sql
./Kopera/sql/ejecutar-sql.sh Kopera/sql/05_pruebas_integracion.sql
```

**Deberías ver**, en cada uno, algo como:

```
  Ejecutando: Kopera/sql/02_procedimientos.sql
════════════════════════════════════════════════════════════════════

Procedure created.
```

En el último (el de las pruebas), vas a ver los mensajes de cada prueba:

```
Análisis cliente 5: RIESGO, saldo $2348972, alertas 4
Pago válido: saldo recalculado y bitácora creada.
Pago excedido rechazado: ORA-20001: El pago debe estar entre cero y el valor de la cuota.
Abono válido: ahorro sincronizado.
Rescate excedido rechazado: ORA-20012: El rescate excede el ahorro disponible.
Prueba del proceso mensual (salida resumida en DBMS_OUTPUT):
Proceso mensual KOPERA | 15/11/2026
...
```

> Los `ORA-20001` y `ORA-20012` que aparecen son **lo esperado**: son las
> pruebas confirmando que los triggers rechazan los pagos y rescates que
> exceden los límites.

> **¿Qué hace cada archivo?** Está todo detallado en
> **[Kopera/sql/README.md](Kopera/sql/README.md)**.

---

### Paso 7 · Verifica que Oracle quedó bien

Hay un script que revisa todo de una vez:

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/verificar.sql
```

**Deberías ver**:

```
=== 1. Objetos PL/SQL (esperado: 8, todos VALID) ===

OBJECT_TYPE      STATUS     TOTAL
---------------- --------- ----------
PACKAGE          VALID           1
PACKAGE BODY     VALID           1
PROCEDURE        VALID           2
TRIGGER          VALID           4

=== 2. Tablas en el esquema (esperado: 17) ===

=== 3. Datos de ejemplo (esperado: 130 / 25 / 519 / 134 / 345) ===

TABLA                        FILAS
---------------------------- ------
CLIENTE                         130
CREDITO_CLIENTE                   25
CUOTA_CREDITO_CLIENTE            519
PRODUCTO_INVERSION_CLIENTE       134
MOVIMIENTO                       345
BITACORA_PAGO_CUOTA               23

=== 4. El package responde (esperado: 130 clientes y una clasificacion) ===

=== 5. Los triggers rechazan un pago excedido (esperado: ORA-20001) ===
OK: el trigger lo rechazo -> ORA-20001: El pago debe estar entre cero y el valor de la cuota.
```

Cinco comprobaciones:

| # | Qué verifica | Valor esperado |
|---|---|---|
| 1 | Los objetos PL/SQL | 8, todos `VALID` |
| 2 | Las tablas del esquema | 17 |
| 3 | Los datos de ejemplo | 130 / 25 / 519 / 134 / 345 |
| 4 | Que el package responde | 130 clientes analizados |
| 5 | Que los triggers rechazan un pago excedido | `ORA-20001` |

> La bitácora marca 23 en vez de 0 porque ya corrieron los pagos. En una
> instalación recién sembrada es 0.
>
> Si algún objeto sale `INVALID` en vez de `VALID`, corré el archivo que lo
> crea de nuevo: lo más probable es que se haya copiado mal.

---

### Paso 8 · Crea tu cluster de MongoDB Atlas

Atlas es la base de datos en la nube donde va a vivir la "copia" de los
clientes. El plan **M0 es gratis** y alcanza perfecto para este proyecto.

**8.1 — Creá la cuenta y el cluster**

1. Entrá a <https://cloud.mongodb.com> y creá una cuenta (o iniciá sesión).
2. Menú **Cluster** → **Create** (o **+ Create**).
3. Elegí el plan **FREE / M0** → **Create**.

**8.2 — Creá el usuario de la base**

1. Menú **Database Access** → **Add New Database User**.
2. Method: **Password**.
3. Ponés un usuario y una contraseña (**anotalos**) y le das el rol
   **Read and write to any database**.
4. Guardás. Te aparece una tarjeta con el usuario.

**8.3 — Autorizá tu IP**

1. Menú **Network Access** → **IP Access List** → **Add IP Address**.
2. Click en **Add My Current IP Address** → **Save**.

**Deberías ver** tu IP en la lista. Esperá ~1 minuto a que se aplique.

> ⚠️ Tu IP pública es **dinámica**: si cambia, Atlas te va a rechazar la
> conexión y vas a ver el error `SSL handshake failed`. Es normal que pase:
> volvé a hacer este paso 8.3.

**8.4 — Copiá la URI**

1. Menú **Cluster** → click en tu cluster → **Connect**.
2. Pestaña **Drivers** → **Python** → copiá la connection string.

Tiene esta forma:

```
mongodb+srv://TU_USUARIO:TU_CLAVE@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

**8.5 — Pegala en el `.env`**

Abrí `.env` y reemplazá la línea de `MONGODB_URI`:

```dotenv
MONGODB_URI="mongodb+srv://TU_USUARIO:TU_CLAVE@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
```

> ⚠️ **Ojo:** si tu contraseña tiene `@`, `:` o `/`, tenés que **codificarla**
> en formato URL (`%40`, `%3A`, `%2F`). MongoDB te avisa si está mal.

---

### Paso 9 · Prepara Python

Python es el único programa que hay que instalar "a mano", y es una
instalación de un comando.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Deberías ver** que la terminal empieza con `(.venv)` al principio. Eso
significa que el entorno virtual está activo.

> En Windows el comando de activación es `.venv\Scripts\activate`.

> ¿Ya tenías un `.venv`? Si te dice que el directorio existe, no es un
> error: `source .venv/bin/activate` y `pip install -r requirements.txt` de
> todas formas.

---

### Paso 10 · Probá las dos conexiones

Antes de correr nada grande, verificá que Oracle y Atlas responden.

**Oracle:**

```bash
.venv/bin/python Kopera/etl/conexion_oracle.py
```

**Deberías ver**:

```
Servidor: Oracle AI Database 26ai Free Release 23.26.3.0.0 - Develop, Learn, and Run for Free

Objetos programables del esquema conectado:
  PACKAGE (VALID): 1
  PACKAGE BODY (VALID): 1
  PROCEDURE (VALID): 2
  TRIGGER (VALID): 4

======================================================================
  Reporte consolidado de la cartera de creditos
  Procedimiento: sp_reporte_cartera
======================================================================
==================================================
  INFORME MENSUAL DE CARTERA KOPERA
  Fecha del proceso: 15/11/2026
==================================================
NRO  CLIENTE                     TOTAL DEUDA    PAGADO         SALDO          PAGADO %
--------------------------------------------------
5    SEBASTIAN QUINTANA          $2,750,016     $401,044       $2,348,972     14.6%
...
```

**Atlas:**

```bash
.venv/bin/python Kopera/etl/conexion_mongodb.py
```

**Deberías ver**:

```
Conexión a MongoDB Atlas:
  Base de datos de trabajo: kopera
  Ping                  : {'ok': 1}
  Version del servidor  : 8.0.37
  Colecciones existentes:
    (ninguna, la base está vacía)

Prueba de humo CRUD en 'kopera._verificacion_conexion':
  Create : documento insertado con _id=...
  Read   : documento recuperado -> {...}
  Update : documento actualizado -> {...}
  Delete : documentos eliminados -> 1
  Limpieza: colección '_verificacion_conexion' eliminada
```

> Si aparece `SSL handshake failed`, tu IP no está autorizada: volvé al
> paso 8.3.

---

### Paso 11 · Carga los datos en Atlas (el ETL)

Ahora sí, la migración. Son **tres comandos y el orden importa**.

**11.1 — Poblar la bitácora de pagos en Oracle**

```bash
.venv/bin/python Kopera/etl/poblar_bitacora.py --simular
```

**Deberías ver** el plan de cobranza en modo ensayo (no cambia nada).

```bash
.venv/bin/python Kopera/etl/poblar_bitacora.py
```

Ahora sí, de verdad. **Deberías ver** los 22 eventos de pago aplicados.

**11.2 — Cargar en Atlas**

Primero un ensayo (no escribe nada):

```bash
.venv/bin/python Kopera/etl/etl_principal.py --simular
```

**Deberías ver** un resumen como este:

```
ETAPA 1 - EXTRACCION desde Oracle
  Fecha de corte (SYSDATE de Oracle) : 15/11/2026
  Clientes                           : 130
  Creditos                           : 25
  Cuotas                             : 519
  Inversiones                        : 134
  Movimientos                        : 345

ETAPA 2 - TRANSFORMACION a documentos NoSQL
  Documentos de cliente              : 130
  Cuotas embebidas                   : 519 (de 519 en Oracle)
  Movimientos embebidos              : 345 (de 345 en Oracle)
  Documentos de catalogo             : 51
  Documentos de bitacora             : 23
  Documentos de proceso mensual      : 1
  Clientes con texto sin corregir    : 0

ETAPA 3 - VALIDACION (reglas de los triggers de Oracle)
  Documentos validados               : 130
  Total de errores                   : 3
  Total de observaciones              : 139
```

Ahora la carga real:

```bash
.venv/bin/python Kopera/etl/etl_principal.py
```

**Deberías ver** el detalle de la carga:

```
ETAPA 4 - CARGA en MongoDB Atlas

  Colecciones eliminadas (recarga)  : 4
  Colecciones creadas                : 4
  Indices creados                    : 12

  coleccion                  recibidos  insertados  rechazados
  ------------------------------------------------------
  clientes                        130         130           0
  catalogos                        51          51           0
  bitacora_pagos                   23          23           0
  procesos_mensuales                1           1           0
```

> **¿Por qué la bitácora va antes?** Porque los pagos cambian las cuotas, los
> saldos y las clasificaciones. Si cargás en Atlas antes de cobrar, la copia
> queda desactualizada respecto de Oracle.

**11.3 — Verificar que todo calza**

```bash
.venv/bin/python Kopera/etl/crud_mongodb.py
```

**Deberías ver** los 18 casos del CRUD y al final:

```
CASOS: 18/18 | Integridad: OK | Restauración: OK
```

```bash
.venv/bin/python Kopera/etl/verificacion_correspondencia.py
```

**Deberías ver**:

```
CORRESPONDENCIA TOTAL
  130/130 clientes coinciden en los 7 campos comparados
```

---

### Paso 12 · Levanta la interfaz web

```bash
docker compose -f docker-compose.app.yml up -d --build
```

La primera vez compila la imagen (un par de minutos). Las siguientes, segundos.

**Deberías ver**:

```
 Container kopera-web  Started
```

Abrí <http://localhost:8501> en el navegador.

**Deberías ver** el panel de KOPERA con las tarjetas de indicadores y, en la
barra lateral, la conexión a Atlas en verde.

> El código de la app está montado como volumen: si guardás un archivo de
> `Kopera/app/`, la página se recarga sola. No hace falta rebuild.

---

### Paso 13 · Corré las pruebas

```bash
.venv/bin/python -m pytest
```

**Deberías ver**:

```
............................................................       [100%]
60 passed in 0.20s
```

```bash
.venv/bin/python Kopera/etl/revision_estatica.py
```

**Deberías ver**:

```
  [OK] 14 scripts revisados, sin problemas detectados.
```

---

### 🎉 Listo

Ya tenés todo andando:

| | | |
|---|---|---|
| ✅ | Oracle con 16 tablas, 130 clientes y el PL/SQL instalado | `localhost:1521` |
| ✅ | Atlas con 4 colecciones cargadas (130 clientes, 51 catálogos, 23 bitácora, 1 proceso) | en la nube |
| ✅ | La interfaz web | <http://localhost:8501> |
| ✅ | 60 pruebas unitarias en verde | |

---

## 4. Cheatsheet: los comandos del día a día

```bash
# ── Estado de los contenedores ───────────────────────────────────────
docker compose ps                            # Oracle
docker compose -f docker-compose.app.yml ps  # App web

# ── Logs (para ver qué está pasando) ─────────────────────────────────
docker compose logs -f oracle
docker compose -f docker-compose.app.yml logs -f web

# ── Apagar / encender ────────────────────────────────────────────────
docker compose down                          # Oracle (NO borra los datos)
docker compose -f docker-compose.app.yml down  # App web
docker compose up -d                         # Levantar Oracle de nuevo
docker compose -f docker-compose.app.yml up -d   # Levantar la app

# ── Correr el SQL ────────────────────────────────────────────────────
./Kopera/sql/ejecutar-sql.sh Kopera/sql/05_pruebas_integracion.sql

# ── El pipeline completo, de nuevo ───────────────────────────────────
.venv/bin/python Kopera/etl/poblar_bitacora.py
.venv/bin/python Kopera/etl/etl_principal.py
.venv/bin/python Kopera/etl/crud_mongodb.py
.venv/bin/python Kopera/etl/verificacion_correspondencia.py

# ── Pruebas ──────────────────────────────────────────────────────────
.venv/bin/python -m pytest
.venv/bin/python Kopera/etl/revision_estatica.py
```

---

## 5. Problemas frecuentes

### "docker: command not found"

Docker no está instalado o no está en el PATH. Instalá Docker Desktop y
**reiniciá la terminal** (o el computador).

### "permission denied while trying to connect to the Docker daemon"

Docker no tiene permiso. En Linux: `sudo usermod -aG docker $USER`, cerrá la
sesión y volvé a entrar.

### El contenedor de Oracle queda en `starting` y no llega a `healthy`

Es normal la primera vez: tarda entre 2 y 4 minutos. Si después de 10
minutos sigue igual:

```bash
docker compose logs oracle | tail -30
```

Lo más común es que la RAM no alcance. Oracle Free pide **2 GB libres**; si
tenés menos, andá a *Docker Desktop → Settings → Resources* y subí el límite
de memoria.

### `ORA-01017: invalid username/password`

Significa que **no se pudo entrar** a la base como `ADMIN_PROYECTO`. Tiene
dos causas distintas, y Oracle no dice cuál es:

| Causa | Qué hacer |
|---|---|
| El usuario **todavía no existe** (no corriste el Paso 4) | Crear el usuario: `./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/CreacionUsuarios.sql.example` |
| El usuario existe pero la **clave del `.env` no coincide** | Corregir `ORACLE_PASSWORD` en el `.env`, o recrear el usuario |

> El helper `ejecutar-sql.sh` **distingue los dos casos** y te dice cuál es,
> en vez de dejarte con un `ORA-01017` a secas.
>
> El comando de la primera fila funciona aunque el usuario no exista: para
> `base/CreacionUsuarios.sql.example` el helper entra **como SYS** y cambia
> de contenedor a `FREEPDB1` antes de correr el script.

### Cloné el repo en otra carpeta y la base aparece vacía

**Este es el error más común y el más confuso.** Docker Compose deriva el
nombre del volumen del **nombre de la carpeta** donde estás. Si clonás el
repo en `/test/Procedimientos_PL-SQL` y ahí corrés `docker compose up -d`,
te crea un volumen **nuevo y vacío** (`procedimientos_pl-sql_oracle_data`), y
la base arranca sin tablas ni usuario: todo falla con `ORA-01017`.

Por eso el `docker-compose.yml` de este repo declara el volumen con nombre
explícito:

```yaml
volumes:
  oracle_data:
    name: kopera_oracle_data
```

Con ese nombre fijo, **todos los clones comparten la misma base de datos**,
importe desde dónde la levantes.

> Si te pasó: el volumen con tus datos suele llamarse
> `<nombre_de_la_carpeta>_oracle_data`. Para recuperarlo:
>
> ```bash
> docker volume ls | grep oracle_data
> ```
>
> y después mirá cuál tiene los datos (el que pesa más):
>
> ```bash
> docker run --rm -v <volumen>:/d container-registry.oracle.com/database/free:latest du -sh /d/FREE
> ```

### `ORA-01918: user 'ADMIN_PROYECTO' does not exist`

El usuario todavía no se creó: falta el Paso 4.

### `ORA-00942: table or view does not exist`

Falta cargar el esquema: es el Paso 5.

### `SSL handshake failed: tlsv1 alert internal error` (Atlas)

**No es un error de código.** Tu IP pública no está en la lista de Atlas, o
cambió. Volvé al paso 8.3 y agregala de nuevo.

Si no funciona, mirá cuál es tu IP:

```bash
curl -s https://api.ipify.org
```

### La app abre pero dice "Sin conexión a MongoDB"

Dos causas posibles:

1. Falta `MONGODB_URI` en el `.env`, o tiene un error de tipeo.
2. Tu IP no está autorizada en Atlas (mismo error que arriba).

Verificá el `.env` y reiniciá la app:

```bash
docker compose -f docker-compose.app.yml down
docker compose -f docker-compose.app.yml up -d
```

### `ModuleNotFoundError: No module named 'pymongo'`

El entorno virtual no está activated, o faltan las dependencias:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### "Ojo con dotenv"

Si el `.env` no se carga y el error es raro, puede ser que tengas instalado
el paquete `dotenv` (de otro proyecto) además de `python-dotenv`, y se estén
pisando. Comprobá:

```bash
python -c "import dotenv; print(dotenv.__file__)"
```

Tiene que salir la ruta de `python-dotenv`.

### El script SQL no muestra los `DBMS_OUTPUT`

Te falta el `SET SERVEROUTPUT ON;` al principio del script, o lo estás
corrriendo en una sesión de SQL Developer sin habilitar la salida (Ctrl+B).

### "the container name /oracle-free is already in use"

Hay un contenedor `oracle-free` corriendo que pertenece a **otra copia** de
este repo (o a una versión anterior del compose). Como el repo declara el
nombre de proyecto `kopera` y el volumen `kopera_oracle_data`, todas las
copias deberían usar **el mismo** contenedor: si aparece este error, es que
quedó uno viejo de antes del cambio.

Mirá quién lo tiene:

```bash
docker ps -a --filter name=oracle-free --format "{{.Names}} | {{.Status}}"
```

Y si está parado y no lo estás usando:

```bash
docker rm -f oracle-free
docker compose up -d
```

### No quiero perder los datos de Oracle

`docker compose down` **no** borra los datos: viven en el volumen
`kopera_oracle_data`. **Nunca** uses `docker compose down -v`: la `-v` sí
borra el volumen y perdés la base entera.

Para perderlos de verdad tendrías que borrar el volumen a mano
(`docker volume rm kopera_oracle_data`) y volver a correr los pasos 4, 5 y 6
de esta guía.

---

## 6. ¿Dónde está cada cosa?

### Para levantar y configurar

| Quiero… | Dónde está |
|---|---|
| Levantar la base de datos | `docker-compose.yml` |
| Levantar la interfaz web | `docker-compose.app.yml` |
| Poner las credenciales | `.env` (plantilla: `.env.example`) |
| Entender las variables | `Kopera/etl/config.py` |
| Conectarme a Oracle | `Kopera/sql/ejecutar-sql.sh` |
| Comprobar que la base quedó bien | `Kopera/sql/base/verificar.sql` |

### Para la base de datos (Evaluación 2)

| Quiero… | Dónde está |
|---|---|
| Crear el usuario `ADMIN_PROYECTO` | `Kopera/sql/base/CreacionUsuarios.sql.example` |
| Crear las tablas y los datos de ejemplo | `Kopera/sql/base/BD_KOPERA.SQL` |
| Instalar el PL/SQL | `Kopera/sql/01_…` a `Kopera/sql/05_…` |
| Ver el resumen financiero | `Kopera/sql/base/resumen_financiero_kopera.sql` |
| Comprobar que la base quedó bien | `Kopera/sql/base/verificar.sql` |
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

## 7. Estructura del repositorio

```text
.
├── README.md                    este archivo (la guía)
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
│   │   ├── ejecutar-sql.sh      ← atajo para correr los .sql desde la terminal
│   │   ├── 01_tablas_apoyo.sql
│   │   ├── 02_procedimientos.sql
│   │   ├── 03_package_analisis_kopera.sql
│   │   ├── 04_triggers.sql
│   │   ├── 05_pruebas_integracion.sql
│   │   └── base/
│   │       ├── CreacionUsuarios.sql.example   plantilla SIN la contraseña real
│   │       ├── BD_KOPERA.SQL                  tablas, relaciones y datos de ejemplo
│   │       ├── verificar.sql                  comprueba que todo quedó bien
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

---

## 8. Qué hace el proyecto

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

## 9. Secretos y credenciales

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
