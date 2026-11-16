# KOPERA · Oracle y PL/SQL (Evaluación Parcial 2)

Todo el lado relacional del proyecto: el esquema, la semilla de datos y los
objetos PL/SQL que automatizan las reglas del negocio.

Oracle es la **fuente de verdad** del proyecto: el modelo relacional y el
PL/SQL de esta carpeta siguen vivos y son los que alimentan el ETL de la
Evaluación 3 (ver [`../etl/README.md`](../etl/README.md)).

---

## 1. Requisitos

- Oracle Database Free 23ai/26ai, corriendo en Docker (ver el
  [README general](../../README.md) para levantarlo).
- Oracle SQL Developer, o la extensión *SQL Developer for VS Code*, o
  `sqlplus` desde la terminal.
- El usuario `ADMIN_PROYECTO` creado y con el esquema cargado.

## 2. Orden de ejecución

El orden **no es negociable**: cada script asume que el anterior ya corrió.
Los pasos 1 a 3 dejan la base lista; los pasos 4 a 8 instalan la
automatización.

| # | Archivo | Qué hace |
|---|---|---|
| 1 | `base/CreacionUsuarios.sql.example` | Crea el usuario `ADMIN_PROYECTO` (plantilla **sin** contraseña real) |
| 2 | `base/BD_KOPERA.SQL` | Crea las 16 tablas, las secuencias y carga los datos de ejemplo |
| 3 | `base/verificar.sql` | *(opcional)* Comprueba que todo quedó instalado y bien |
| 4 | `01_tablas_apoyo.sql` | Tabla de apoyo `BITACORA_PAGO_CUOTA` (auditoría de pagos) |
| 5 | `02_procedimientos.sql` | `sp_reporte_cartera` y `sp_registra_pago` |
| 6 | `03_package_analisis_kopera.sql` | El package `pk_analisis_kopera` (spec + body) |
| 7 | `04_triggers.sql` | Los 4 triggers de integridad y auditoría |
| 8 | `05_pruebas_integracion.sql` | Pruebas de integración de todo lo anterior |

> El paso 1 es el único que **no** se puede automatizar desde la terminal con
> un usuario normal: la contraseña se pide por prompt. Ver la sección 4.

### Cómo ejecutar cada archivo

**La forma más fácil: `./Kopera/sql/ejecutar-sql.sh`** (no necesitás instalar
Oracle SQL Developer).

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/01_tablas_apoyo.sql
./Kopera/sql/ejecutar-sql.sh Kopera/sql/02_procedimientos.sql
./Kopera/sql/ejecutar-sql.sh Kopera/sql/03_package_analisis_kopera.sql
./Kopera/sql/ejecutar-sql.sh Kopera/sql/04_triggers.sql
./Kopera/sql/ejecutar-sql.sh Kopera/sql/05_pruebas_integracion.sql
```

> **⚖️ ¿Extensión de SQL Developer o el helper?**
>
> No son excluyentes. Los dos ejecutan el **mismo archivo `.sql` en la misma
> base**; lo que cambia es el camino y las herramientas alrededor.
>
> | | Extensión de SQL Developer | Helper `ejecutar-sql.sh` |
> |---|---|---|
> | **Cómo llega a la base** | Por TCP al puerto `1521` publicado | Por `docker exec`, entrando al contenedor |
> | **Qué motor ejecuta** | Su driver de Oracle en tu PC | El `SQL*Plus` que ya viene adentro del contenedor |
> | **Hay que instalar** | La extensión + un perfil de conexión | Nada |
> | **Ideal para** | Explorar la base, correr solo un trozo del archivo, grilla de resultados, debug de PL/SQL | Correr los scripts completos del proyecto, automatizar |
>
> Usa la extensión para **explorar** (árbol de objetos, índices, constraints) y
> para correr **un solo `SELECT`** que seleccionaste. Usa el helper para
> **correr los scripts del proyecto** de punta a punta.

El script se encarga de todo lo molesto:

| Se encarga de | Por qué |
|---|---|
| Leer la contraseña del `.env` | No tenés que escribirla en ningún archivo ni recordarla. |
| Reemplazar `&ORACLE_PASSWORD` | Por lo que vale en tu `.env`. |
| Pasarte `NLS_LANG=…AL32UTF8` | Para que los acentos se vean bien y no salgan como `An?lisis`. |
| Avisarte si falta el contenedor | En vez de un error de sqlplus críptico. |
| Validar que el archivo exista | Antes de intentar conectarte. |
| **Diagnosticar un `ORA-01017`** | Oracle usa el mismo error para "el usuario no existe" y para "la clave está mal". El helper consulta `cdb_users` para decirte cuál de los dos es. |

**La forma clásica: Oracle SQL Developer.**

1. Conéctate al servicio `FREEPDB1` como `ADMIN_PROYECTO`.
2. Abre el archivo.
3. Presiona **F5** (Ejecutar script). Si el archivo tiene varios bloques
   `PL/SQL` separados por `/`, F5 los corre todos en orden.
4. Habilita la salida con **Ctrl+B** → *DBMS Output*, o la barra de abajo.

**Con `sqlplus`**:

```bash
sqlplus ADMIN_PROYECTO@localhost:1521/FREEPDB1 @01_tablas_apoyo.sql
```

**Con la extensión de VS Code**: abre el archivo, `Ctrl+Alt+Enter` para
ejecutar, y revisa la salida en el panel *Output*.

> **Habilita `DBMS_OUTPUT`.** Los procedimientos y el package imprimen sus
> informes con `DBMS_OUTPUT.PUT_LINE`. Sin esa opción, el script corre pero no
> ves nada:

> ```sql
> SET SERVEROUTPUT ON;
> ```

## 3. Qué hay en cada archivo

### `base/BD_KOPERA.SQL`

Crea el modelo relacional completo y lo puebla (16 tablas):

| Grupo | Tablas |
|---|---|
| Clientes | `CLIENTE` |
| Créditos | `CREDITO`, `CREDITO_CLIENTE`, `CUOTA_CREDITO_CLIENTE` |
| Inversiones | `PRODUCTO_INVERSION`, `PRODUCTO_INVERSION_CLIENTE`, `MOVIMIENTO` |
| Ubicación | `REGION`, `PROVINCIA`, `COMUNA`, `SUCURSAL` |
| Catálogos | `TIPO_CONTRATO`, `TIPO_MOVIMIENTO`, `FORMA_PAGO`, `PROFESION_OFICIO`, `APORTE_A_SBIF` |

La semilla trae **130 clientes**, 25 créditos, 519 cuotas, 134 productos de
inversión y 345 movimientos.

> ⚠️ **Reejecutarlo borra los datos.** El script hace `DROP TABLE` de todo
> antes de recrear. Si ya tienes la base cargada y solo quieres probar los
> procedimientos, no lo vuelvas a correr.

### `base/CreacionUsuarios.sql.example`

Plantilla del script de administración del usuario. Pide el valor de
`ORACLE_PASSWORD` por prompt y es **idempotente**: el `DROP USER` va dentro de
un bloque PL/SQL que captura el error si el usuario todavía no existe.

Copia la plantilla a `base/CreacionUsuarios.sql` (ese archivo **no se
versiona**, está en `.gitignore`) y reemplaza `&ORACLE_PASSWORD` por la clave
literal, o deja la plantilla y escribe la clave cuando el script te la pida.

> ⚠️ En las ejecuciones posteriores, ese `DROP USER` **elimina el usuario y
> todos sus objetos** antes de recrearlo. Úsalo solo en este entorno
> académico.

### `base/verificar.sql`

Comprueba la instalación completa en una sola corrida: los 8 objetos
PL/SQL y su estado, la cantidad de tablas, los conteos de filas, que el
package responda y que los triggers realmente rechacen un pago excedido.

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/verificar.sql
```

### `base/resumen_financiero_kopera.sql`

Reporte financiero integrado, de **solo lectura**: no crea objetos ni
modifica datos. Requiere que el esquema ya esté cargado.

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/resumen_financiero_kopera.sql
```

### `01_tablas_apoyo.sql`

Crea `BITACORA_PAGO_CUOTA`: la tabla de auditoría donde se registra cada
cambio efectivo del monto pagado de una cuota (monto anterior, monto nuevo,
saldo resultante, forma de pago, fecha y usuario).

### `02_procedimientos.sql`

| Procedimiento | Qué hace |
|---|---|
| `sp_reporte_cartera` | Reporte consolidado de la cartera: por cliente, sus créditos, cuota, pagado, saldo y % pagado. No recibe parámetros e imprime con `DBMS_OUTPUT`. |
| `sp_registra_pago(p_credito, p_cuota, p_monto, p_forma_pago)` | Registra un pago de cuota. Es **la vía oficial del negocio**: dispara los triggers de validación y de bitácora. |

### `03_package_analisis_kopera.sql`

El package con la lógica de análisis. El spec declara los tipos y las
excepciones; el body implementa todo.

**Funciones escalares** (las usa el ETL de la EVAL 3 para no duplicar la
lógica de negocio):

| Función | Devuelve |
|---|---|
| `fn_saldo_pendiente(p_cliente)` | Deuda pendiente del cliente |
| `fn_porcentaje_pagado(p_cliente)` | % pagado de sus cuotas |
| `fn_cuenta_cuotas(p_cliente, p_estado)` | Cuotas en un estado (`PAGADA`, `PARCIAL`, `VENCIDA`, `PENDIENTE`) |
| `fn_total_ahorrado(p_cliente)` | Total ahorrado en sus productos de inversión |
| `fn_clasifica_cliente(p_cliente)` | `BUENO` / `REGULAR` / `RIESGO` / `SIN PRODUCTOS` |
| `fn_dias_atraso(p_credito, p_nro_cuota)` | Días de atraso de una cuota |
| `fn_porc_rescate(p_solicitud)` | % de rescate acumulado de una inversión |
| `fn_aporte_sbif(p_monto_credito)` | Aporte a la SBIF que corresponde a un crédito |

**Procedimientos:**

| Procedimiento | Qué hace |
|---|---|
| `sp_analiza_cliente(p_cliente, p_resumen OUT, p_alertas OUT)` | Analiza **un** cliente y devuelve su resumen y sus alertas. |
| `sp_proceso_mensual` | Analiza **todos** los clientes e imprime el informe mensual. No recibe parámetros ni devuelve filas: imprime con `DBMS_OUTPUT`. |
| `sp_registra_movimiento(p_solicitud, p_monto, p_tipo_movimiento, p_mensaje OUT)` | Registra un abono o rescate sobre un producto de inversión, validando saldo y % máximo de rescate. |

Excepciones declaradas: `e_cartera_vacia`, `e_cliente_sin_productos`,
`e_pago_excedido`, `e_rescate_excedido`.

### `04_triggers.sql`

Las 4 reglas automáticas. **No hacen `COMMIT`**: escriben dentro de la misma
transacción que la operación que las dispara.

| Trigger | Momento | Regla |
|---|---|---|
| `trg_cuota_valida_pago` | `BEFORE INSERT OR UPDATE` de `cuota_credito_cliente` | El pago va entre 0 y el valor de la cuota, y el saldo se deriva: `saldo = valor - pagado`. |
| `trg_cuota_bitacora` | `AFTER UPDATE` de `monto_pagado` | Escribe en `BITACORA_PAGO_CUOTA` **solo** si el monto pagado cambió de verdad. |
| `trg_movimiento_valida` | `BEFORE INSERT` de `movimiento` | Monto mayor que 0, tipo `ABONO` o `RESCATE`, rescate no mayor al saldo disponible y rescate acumulado dentro del % máximo del producto. |
| `trg_movimiento_actualiza_ahorro` | `AFTER INSERT` de `movimiento` | Mantiene sincronizado `monto_total_ahorrado` según el signo del movimiento. |

> El tier gratuito **M0** de MongoDB Atlas no permite Atlas Triggers ni Atlas
> Functions, así que estas mismas 4 reglas están replicadas en Python en
> [`../etl/validaciones.py`](../etl/validaciones.py). La app web reutiliza esa
> réplica en vez de reimplementarla.

### `05_pruebas_integracion.sql`

Ejercita todo lo anterior en un solo bloque, con `DBMS_OUTPUT`:

1. Análisis del cliente 5 con `sp_analiza_cliente`.
2. Un pago válido: comprueba que el saldo se recalcula y que la bitácora se
   escribe.
3. Un pago **excedido**: comprueba que el trigger lo rechaza (`ORA-20001`).
4. Un abono válido: comprueba que el ahorro queda sincronizado.
5. Un **rescate excedido**: comprueba que el trigger lo rechaza.
6. El proceso mensual (`sp_proceso_mensual`).

## 4. Crear el usuario `ADMIN_PROYECTO`

Tienes tres opciones:

**a) Con el helper (la más fácil):**

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/CreacionUsuarios.sql.example
```

Toma la contraseña del `.env` y la inyecta en el `&ORACLE_PASSWORD`.

> **Cómo entra el helper en este archivo.** Para
> `base/CreacionUsuarios.sql.example` el helper se conecta **como SYS**
> (`as sysdba`) y cambia de contenedor a `FREEPDB1` antes de correr el
> script. Es necesario porque en una instalación nueva `ADMIN_PROYECTO`
> todavía no existe: entrar con ese usuario fallaría con `ORA-01017` y el
> usuario nunca se crearía. En todos los demás archivos el helper entra
> normalmente como `ADMIN_PROYECTO`.

**b) Con la plantilla versionada** (`base/CreacionUsuarios.sql.example`):
conéctate al servicio `FREEPDB1` como administrador de Oracle en SQL
Developer y ejecuta el archivo con **F5**. El script te pide el valor de
`ORACLE_PASSWORD`: escribe ahí la misma clave que pusiste en tu `.env`.

**c) Con tu copia local**: copia la plantilla como
`base/CreacionUsuarios.sql` (ese archivo **no se versiona**) y reemplaza
`&ORACLE_PASSWORD` por la clave literal.

## 5. Verificar que quedó bien

Lo más rápido es correr el script de verificación, que hace las cinco
comprobaciones de una vez:

```bash
./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/verificar.sql
```

Si prefieres hacerlas a mano, estas son las consultas:

```sql
SELECT object_type, status, COUNT(*)
  FROM user_objects
 WHERE object_type IN ('PROCEDURE','FUNCTION','PACKAGE','PACKAGE BODY','TRIGGER')
 GROUP BY object_type, status
 ORDER BY object_type;
```

Deben aparecer **8 objetos, todos `VALID`**:

| Tipo | Cuántos | Cuáles |
|---|---|---|
| `PACKAGE` | 1 | `pk_analisis_kopera` (spec) |
| `PACKAGE BODY` | 1 | `pk_analisis_kopera` (body, con las 8 funciones y los 3 procedimientos) |
| `PROCEDURE` | 2 | `sp_reporte_cartera`, `sp_registra_pago` |
| `TRIGGER` | 4 | `trg_cuota_valida_pago`, `trg_cuota_bitacora`, `trg_movimiento_valida`, `trg_movimiento_actualiza_ahorro` |

Los procedimientos del package (`sp_analiza_cliente`, `sp_proceso_mensual`,
`sp_registra_movimiento`) **no** aparecen como objetos separados: en
`USER_OBJECTS` viven dentro del `PACKAGE BODY`.

Si alguno sale `INVALID`, revisa `USER_ERRORS`:

```sql
SELECT name, type, line, text FROM user_errors ORDER BY sequence;
```

Y comprueba los datos:

```sql
SELECT 'CLIENTE' AS tabla, COUNT(*) FROM cliente
UNION ALL SELECT 'CREDITO_CLIENTE', COUNT(*) FROM credito_cliente
UNION ALL SELECT 'CUOTA_CREDITO_CLIENTE', COUNT(*) FROM cuota_credito_cliente
UNION ALL SELECT 'PRODUCTO_INVERSION_CLIENTE', COUNT(*) FROM producto_inversion_cliente
UNION ALL SELECT 'MOVIMIENTO', COUNT(*) FROM movimiento
UNION ALL SELECT 'BITACORA_PAGO_CUOTA', COUNT(*) FROM bitacora_pago_cuota;
```

Esperado: `130`, `25`, `519`, `134`, `345`, y `0` en la bitácora recién
sembrada (se llena después, con `sp_registra_pago` o con el proceso de
cobranza del ETL: tras una corrida completa quedan 23 eventos).

En total, el esquema tiene **17 tablas**: las 16 del modelo de `BD_KOPERA.SQL`
más `BITACORA_PAGO_CUOTA` de `01_tablas_apoyo.sql`.

## 6. También desde Python

Los mismos objetos se pueden invocar desde Python, que es como el ETL los
consume. Ver [`../etl/README.md`](../etl/README.md):

```bash
.venv/bin/python Kopera/etl/conexion_oracle.py
```

Ese script verifica la conexión, lista los objetos programables con su
estado de compilación y ejecuta `sp_reporte_cartera` y
`pk_analisis_kopera.sp_proceso_mensual` mostrando su salida.

## 7. Precauciones

- `base/BD_KOPERA.SQL` **elimina y vuelve a crear** tablas y secuencias.
  Reejecutarlo borra los datos del esquema.
- `base/CreacionUsuarios.sql` (y su plantilla) elimina el usuario
  `ADMIN_PROYECTO` con `CASCADE` antes de crearlo.
- Los triggers no hacen `COMMIT`: si haces `rollback`, se borra **también** la
  fila de la bitácora, porque el trigger escribe dentro de la misma
  transacción que el `UPDATE`. Para dejar la bitácora persistida hay que
  confirmar el pago.
- El volumen `oracle_data` conserva los datos del contenedor. `docker compose
  down` detiene el servicio pero no borra el volumen; no uses `docker compose
  down -v` salvo que quieras perder la base.
