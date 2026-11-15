# KOPERA · ETL y scripts en Python (Evaluación Parcial 3)

El **puente** entre Oracle y MongoDB Atlas. Oracle sigue siendo la fuente de
verdad y el motor de la automatización (el PL/SQL de la EVAL 2 queda intacto,
ver [`../sql/README.md`](../sql/README.md)); Python extrae de Oracle,
transforma, carga en Atlas y ejecuta el CRUD.

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
catálogos maestro quedan en su propia colección para no duplicar nombres.

---

## 1. Requisitos

- Python 3.10 o superior.
- Un entorno virtual con las dependencias de `requirements.txt`.
- Oracle con el esquema `ADMIN_PROYECTO` cargado y el PL/SQL instalado.
- Un proyecto en **MongoDB Atlas** con el tier gratuito **M0**.
- Tu IP pública autorizada en *Network Access* del proyecto de Atlas.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # o requirements-dev.txt para las pruebas
```

Las versiones van fijadas en `requirements.txt` a propósito: el pipeline
depende del comportamiento de `insert_many(ordered=False)` de PyMongo y del
modo *thin* de `oracledb`.

> **Ojo con `dotenv`:** el paquete `python-dotenv` provee el módulo `dotenv`.
> Si además tienes instalado el paquete `dotenv` (de otro proyecto), uno de
> los dos pisa al otro y la carga del `.env` puede fallar. Comprueba con
> `python -c "import dotenv; print(dotenv.__file__)"`.

## 2. Configuración

Todo se configura desde el **`.env` de la raíz del repositorio** (nunca se
versiona). La plantilla versionada es `.env.example`.

```dotenv
ORACLE_USER=ADMIN_PROYECTO
ORACLE_PASSWORD="..."
ORACLE_HOST=127.0.0.1
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=FREEPDB1
MONGODB_URI="mongodb+srv://..."
MONGODB_DATABASE=kopera
```

Entrecomilla los valores que lleven caracteres especiales (`#`, `$`): sin
comillas, el `#` se interpreta como inicio de comentario.

El módulo [`config.py`](config.py) es el **único** que lee esas variables y
el **único** que abre conexiones (`conectar_oracle()`, `conectar_mongodb()`).
Ninguna credencial está escrita en el código.

## 3. Mapa de los módulos

| Módulo | Qué hace |
|---|---|
| [`config.py`](config.py) | Configuración central y las dos conexiones (Oracle y Atlas). Nombres de las colecciones y parámetros del driver. |
| [`dbms_output.py`](dbms_output.py) | Helper que habilita el buffer de `DBMS_OUTPUT`, ejecuta un procedimiento y devuelve sus líneas. |
| [`conexion_oracle.py`](conexion_oracle.py) | **Prueba de conexión a Oracle**: versión del servidor, objetos programables y su estado, y ejecución de los dos procesos automáticos. |
| [`conexion_mongodb.py`](conexion_mongodb.py) | **Prueba de conexión a Atlas**: ping, versión, colecciones y un CRUD de humo sobre una colección temporal que se elimina al terminar. |
| [`plan_pagos.py`](plan_pagos.py) | **DATA, no lógica**: el plan de cobranza mensual (qué cuotas se pagan, cuánto y con qué forma de pago). Es editable. |
| [`poblar_bitacora.py`](poblar_bitacora.py) | Ejecuta el plan de cobranza en Oracle: valida, calcula el delta, llama a `sp_registra_pago` y confirma todo en un único `COMMIT`. |
| [`extraccion_oracle.py`](extraccion_oracle.py) | **ETAPA 1**: lee Oracle de forma *set-based* (sin loops) y arma el diccionario de datos planos. Llama a las funciones del package para el bloque `analisis`. |
| [`transformacion.py`](transformacion.py) | **ETAPA 2**: limpia los caracteres dañados (U+FFFD), anida por agregado y reclasifica a `OPORTUNIDAD` a los clientes sin créditos. |
| [`validaciones.py`](validaciones.py) | Las 4 reglas de negocio que replican los triggers de Oracle, para validar los documentos **antes** de cargarlos. |
| [`carga_mongodb.py`](carga_mongodb.py) | **ETAPA 3**: crea las colecciones con validador `$jsonSchema` (`validationLevel: strict`), crea los 12 índices y carga los documentos. |
| [`crud_mongodb.py`](crud_mongodb.py) | CRUD completo en Python: 18 casos etiquetados (C1–C4, R1–R7, U1–U4, D1–D3). Re-ejecutable: al terminar restaura la base a su estado original. |
| [`verificacion_correspondencia.py`](verificacion_correspondencia.py) | Comprueba Oracle ↔ Atlas cliente por cliente, en 7 campos. |
| [`revision_estatica.py`](revision_estatica.py) | Verificador de código: nombres no definidos, caracteres dañados, imports rotos, imports sin usar, **llamadas con la aridad equivocada** y claves duplicadas en diccionarios. No necesita base de datos. |
| [`etl_principal.py`](etl_principal.py) | Orquestador: corre las cuatro etapas del pipeline en un solo comando. |

## 4. Pruebas de conexión

Antes de correr el pipeline conviene confirmar que las dos conexiones
responden. Son los dos scripts de humo del proyecto.

### `conexion_oracle.py`

```bash
.venv/bin/python Kopera/etl/conexion_oracle.py
```

Hace tres cosas:

1. Abre la conexión al esquema `ADMIN_PROYECTO` y muestra la versión del
   servidor Oracle.
2. Lista los objetos programables del esquema con su estado de compilación
   (`VALID` / `INVALID`).
3. Ejecuta `sp_reporte_cartera` y `pk_analisis_kopera.sp_proceso_mensual`, y
   muestra la salida de cada uno.

Sale con código `1` si algo falla.

### `conexion_mongodb.py`

```bash
.venv/bin/python Kopera/etl/conexion_mongodb.py
```

Hace tres cosas:

1. Abre el cliente contra el cluster y ejecuta un `ping`.
2. Muestra la versión del servidor y las colecciones existentes.
3. Ejecuta un CRUD de humo (Create, Read, Update, Delete) sobre la colección
   temporal `_verificacion_conexion`, que **se elimina al terminar**: no
   queda ningún documento de prueba en la base `kopera`.

**Si falla con `SSL handshake failed: tlsv1 alert internal error`**, el
problema **no es el código**: tu IP pública no está en la *IP Access List* del
proyecto de Atlas. Agrégala en *Network Access* (tu IP es dinámica: la
consultas con `curl -s https://api.ipify.org`). Si el cluster aparece como
*Paused* en el panel, hay que reanudarlo.

## 5. El pipeline

### El orden importa

La bitácora se puebla **antes** del ETL, porque los pagos cambian cuotas,
saldos y clasificaciones. Si cargas en Atlas antes de cobrar, la colección
queda desactualizada respecto de Oracle.

```bash
# 0. Revisión estática del código (no necesita base de datos)
.venv/bin/python Kopera/etl/revision_estatica.py

# 1. Pruebas de conexión
.venv/bin/python Kopera/etl/conexion_oracle.py
.venv/bin/python Kopera/etl/conexion_mongodb.py

# 2. Proceso mensual de cobranza en Oracle (puebla la bitácora)
.venv/bin/python Kopera/etl/poblar_bitacora.py --simular   # ensayo en seco
.venv/bin/python Kopera/etl/poblar_bitacora.py             # ejecución real

# 3. ETL completo: Oracle -> Atlas
.venv/bin/python Kopera/etl/etl_principal.py --simular      # sin escribir en Atlas
.venv/bin/python Kopera/etl/etl_principal.py                # carga real

# 4. CRUD en Python (18 casos, con restauración automática)
.venv/bin/python Kopera/etl/crud_mongodb.py

# 5. Correspondencia Oracle <-> Atlas
.venv/bin/python Kopera/etl/verificacion_correspondencia.py
```

### Las cuatro etapas del ETL

`etl_principal.py` corre las cuatro etapas y reporta los conteos de cada una:

| Etapa | Módulo | Qué hace |
|---|---|---|
| 1 · Extracción | `extraccion_oracle.py` | Lee Oracle *set-based* y arma el diccionario de datos planos. |
| 2 · Transformación | `transformacion.py` | Limpia U+FFFD, anida créditos/cuotas e inversiones/movimientos, reclasifica a `OPORTUNIDAD`. |
| 3 · Validación | `validaciones.py` | Aplica las reglas de los triggers **antes** de cargar: si un documento violara una regla, no debe llegar a Atlas. |
| 4 · Carga | `carga_mongodb.py` | Crea las colecciones con `$jsonSchema` e índices, y carga los documentos. |

**Opciones de `etl_principal.py`:**

| Opción | Qué hace |
|---|---|
| *(ninguna)* | Ejecución real: escribe en Atlas. |
| `--simular` | Corre todo el pipeline pero **no** escribe nada en Atlas. |
| `--sin-proceso` | No ejecuta `sp_proceso_mensual`, así que la colección `procesos_mensuales` queda vacía. |

**Resultado esperado de una corrida completa:**

```text
ETAPA 1 - EXTRACCION
  Clientes                           : 130
  Creditos                           : 25
  Cuotas                             : 519
  Inversiones                        : 134
  Movimientos                        : 345

ETAPA 2 - TRANSFORMACION
  Documentos de cliente              : 130
  Cuotas embebidas                   : 519 (de 519 en Oracle)
  Movimientos embebidos              : 345 (de 345 en Oracle)
  Pagos embebidos en el cliente      : 23
  Documentos de catalogo             : 51   (10 productos, 5 créditos, 3 formas
                                             de pago, 2 tipos de movimiento,
                                             5 aportes SBIF, 23 profesiones,
                                             3 tipos de contrato)
  Documentos de bitacora             : 23   eventos de pago
  Documentos de proceso mensual      : 1    informe mensual
  Clientes con texto sin corregir    : 0

ETAPA 3 - VALIDACION
  Documentos validados               : 130
  Documentos con errores             : 1
  Total de observaciones              : 139
```

Los 3 errores y las 139 observaciones son **heredados de la semilla** (ver la
sección 9): son datos históricos que se cargaron sin pasar por los triggers.
No bloquean la carga.

## 6. El CRUD

```bash
.venv/bin/python Kopera/etl/crud_mongodb.py
```

18 casos etiquetados: **C**rear (C1–C4), **R**eer (R1–R7), **U**pdate
(U1–U4), **D**elete (D1–D3). Es **re-ejecutable**: al terminar restaura la
base a su estado original, así que se puede correr las veces que haga falta
sin dejar basura.

La validación del lado del servidor también se ejercita: el CRUD intenta
insertar un documento incompleto a propósito y comprueba que el validador
`$jsonSchema` lo rechaza.

> El tier M0 de Atlas **no admite transacciones multi-documento**. Por eso
> todo el diseño del CRUD trabaja sobre un único documento (el cliente con sus
> arrays embebidos): la atomicidad de MongoDB es por documento.

## 7. Correspondencia Oracle ↔ Atlas

```bash
.venv/bin/python Kopera/etl/verificacion_correspondencia.py
```

Compara, cliente por cliente, 7 campos: deuda total, pagado, saldo
pendiente, total ahorrado, cantidad de créditos, de cuotas y de movimientos.
Debe terminar con `CORRESPONDENCIA TOTAL`.

Para dejar el detalle en un CSV (útil para el anexo del informe):

```bash
.venv/bin/python Kopera/etl/verificacion_correspondencia.py --archivo docs/eva3/correspondencia.csv
```

## 8. Pruebas y revisión estática

```bash
.venv/bin/python -m pytest                              # 60 passed
.venv/bin/python Kopera/etl/revision_estatica.py        # [OK] 14 scripts revisados
```

Las pruebas unitarias cubren las funciones puras (las 4 reglas de negocio y la
transformación) y **no necesitan Oracle ni Atlas**: corren en 0,2 s.

El revisor estático tampoco necesita base de datos: recorre los 14 módulos y
detecta lo que un simple "compila bien" no ve.

## 9. Detalles que conviene conocer

- **El bloque `analisis` está materializado.** En Oracle la clasificación
  siempre es "viva" (las funciones la recalculan en cada consulta); en
  MongoDB queda como un campo del documento. Por eso el CRUD lo recalcula con
  `transformacion.recalcular_analisis()` cuando modifica una cuota o un
  movimiento.
- **La bitácora es un histórico, no un estado.** `procesos_mensuales` **no**
  se borra en cada carga: cada ejecución del ETL agrega un documento. Las
  otras tres colecciones sí se recargan, porque su fuente de verdad es Oracle.
- **`fn_clasifica_cliente` marca `RIESGO` a 129 de 130 clientes**, porque 107
  no tienen crédito y su porcentaje pagado es 0. En la transformación se
  reclasifican a `OPORTUNIDAD`, conservando el valor original en
  `analisis.clasificacion_oracle`.
- **La semilla tiene inconsistencias que los triggers habrían impedido**: 3
  cuotas con un pago mayor que el valor de la cuota (cliente 83, crédito
  3007), 5 con el saldo descuadrado y las 134 inversiones con un saldo inicial
  que no proviene de la suma de sus movimientos. El ETL los **informa** (3
  errores y 139 observaciones) pero no bloquea la carga: son datos históricos,
  no operaciones nuevas.
- **Las fechas se guardan como texto ISO**, no como `BSON date`. La app web
  las parsea en `formato.py`.
