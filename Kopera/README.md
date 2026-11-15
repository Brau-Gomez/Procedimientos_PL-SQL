# KOPERA

Raíz del proyecto. Tres carpetas, una por capa:

```text
Kopera/
├── sql/    la base de datos: esquema, semilla y PL/SQL   (Evaluación 2)
├── etl/    el puente en Python: Oracle → MongoDB Atlas    (Evaluación 3)
└── app/    la interfaz web en Streamlit                  (Evaluación 3)
```

## Qué leer primero

| Quiero… | Lee |
|---|---|
| Levantar todo el proyecto | [README general](../README.md) |
| Instalar y ejecutar el PL/SQL | **[sql/README.md](sql/README.md)** |
| Instalar y ejecutar el ETL | **[etl/README.md](etl/README.md)** |
| Levantar la interfaz web | **[app/README.md](app/README.md)** |

## Las tres capas

### `sql/` — Oracle y PL/SQL (Evaluación 2)

El modelo relacional (16 tablas + la de auditoría) y los objetos PL/SQL que
automatizan las reglas del negocio: un package con 8 funciones y 3
procedimientos, 2 procedimientos sueltos y 4 triggers.

Oracle es la **fuente de verdad** del proyecto. Nada de lo que hay aquí se
modifica desde la EVAL 3: el ETL solo lo lee.

```
sql/
├── 01_tablas_apoyo.sql          BITACORA_PAGO_CUOTA
├── 02_procedimientos.sql        sp_reporte_cartera, sp_registra_pago
├── 03_package_analisis_kopera.sql   package + body
├── 04_triggers.sql              las 4 reglas automáticas
├── 05_pruebas_integracion.sql   pruebas de todo lo anterior
├── ejecutar-sql.sh              corre un .sql sin instalar SQL Developer
└── base/
    ├── CreacionUsuarios.sql.example   crea el usuario ADMIN_PROYECTO
    ├── BD_KOPERA.SQL                  tablas, relaciones y datos de ejemplo
    ├── verificar.sql                  comprueba que todo quedó instalado
    └── resumen_financiero_kopera.sql  reporte financiero de solo lectura
```

### `etl/` — pipeline en Python (Evaluación 3)

Extrae de Oracle, transforma, carga en Atlas y ejecuta el CRUD. Los módulos
se importan entre ellos por nombre plano, así que se ejecutan desde esa
carpeta o con la ruta completa desde la raíz del repositorio.

```
etl/
├── config.py            configuración + las dos conexiones
├── dbms_output.py       captura de DBMS_OUTPUT
├── conexion_oracle.py   prueba de conexión a Oracle
├── conexion_mongodb.py  prueba de conexión a Atlas
├── plan_pagos.py        DATA: plan de cobranza editable
├── poblar_bitacora.py   proceso mensual de cobranza
├── extraccion_oracle.py ETAPA 1: lectura desde Oracle
├── transformacion.py    ETAPA 2: limpieza y anidado
├── validaciones.py      reglas replicadas de los triggers
├── carga_mongodb.py     ETAPA 3: carga con $jsonSchema e índices
├── crud_mongodb.py      CRUD en Python (18 casos)
├── verificacion_correspondencia.py   prueba Oracle ↔ Atlas
├── revision_estatica.py verificador de typos, imports y aridad
└── etl_principal.py     orquestador del pipeline
```

### `app/` — interfaz web (Evaluación 3)

Streamlit, para consultar los resultados del ETL y hacer demostraciones en
vivo del CRUD. **No reimplementa** las reglas del negocio: importa
`validaciones.py` y `transformacion.py` desde `../etl`, que el compose monta
como `/etl` en modo solo lectura.

```
app/
├── main.py              navegación y estado de la conexión
├── config_app.py        cliente MongoDB (cacheado) y nombres de colecciones
├── consultas.py         agregaciones de LECTURA
├── operaciones.py       ESCRITURA: pagos y movimientos
├── formato.py           moneda CLP, fechas ISO, semáforos de estado
├── ui.py                paleta, CSS, tarjetas KPI, tablas e insignias
├── graficos.py          dona, barras de estado/atraso, barras horizontales
└── vistas/              una función render() por pantalla
    ├── panel.py         resumen general
    ├── clientes.py      listado de clientes
    ├── ficha.py         ficha de un cliente
    ├── cartera.py       cartera de créditos
    ├── inversiones.py   inversiones y movimientos
    ├── catalogos.py     catálogos maestros
    ├── procesos.py      historial de procesos mensuales
    └── operaciones.py   registro de pagos y movimientos
```

## Regla de oro

> **La lógica de negocio vive en un solo lugar.**
>
> En Oracle, en el package `pk_analisis_kopera` y en los triggers. El ETL la
> **reutiliza** (llama a las funciones escalares) y la replica en
> `validaciones.py` **solo** porque MongoDB Atlas M0 no tiene triggers. La app
> web importa esa misma réplica en vez de reescribirla.
>
> Si someday la app y el ETL dicen cosas distintas, el error está en una
> copia: en `validaciones.py` o en `transformacion.py`.
