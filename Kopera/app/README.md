# Interfaz web de KOPERA (Streamlit)

Aplicación local para consultar los resultados del ETL `Oracle → MongoDB Atlas`
y hacer demostraciones en vivo del CRUD sobre la base `kopera`.

## Levantar la app

Desde la raíz del repositorio:

```bash
docker compose -f docker-compose.app.yml up -d --build
```

Abrir <http://localhost:8501>

```bash
docker compose -f docker-compose.app.yml logs -f web   # logs
docker compose -f docker-compose.app.yml down          # detener
```

El código está montado como volumen: al guardar un archivo de `Kopera/app/`,
Streamlit recarga solo (no hace falta rebuild, solo si cambian dependencias).

## Requisitos

- Docker y Docker Compose.
- El archivo `.env` de la raíz con `MONGODB_URI` y `MONGODB_DATABASE`
  (el mismo que usa el ETL). Está en `.gitignore`.
- La IP pública de la máquina debe estar en la **IP Access List** del proyecto
  en MongoDB Atlas. Si no, la app muestra "Sin conexión a MongoDB".

## Ejecución sin Docker (opcional)

```bash
python -m venv .venv-web
source .venv-web/bin/activate
pip install -r Kopera/app/requirements.txt
streamlit run Kopera/app/main.py
```

## Estructura

```text
Kopera/app/
├── main.py           # navegación y estado de la conexión
├── config_app.py     # cliente MongoDB (cacheado) y nombres de colecciones
├── consultas.py      # agregaciones de LECTURA
├── operaciones.py    # ESCRITURA: pagos y movimientos (reutiliza el ETL)
├── formato.py        # moneda CLP, fechas ISO, semáforos de estado
├── ui.py             # paleta, CSS, tarjetas KPI, tablas e insignias
├── graficos.py       # dona, barras de estado/atraso, barras horizontales
├── vistas/           # una función render() por pantalla
│   ├── panel.py
│   ├── clientes.py
│   ├── ficha.py
│   ├── cartera.py
│   ├── inversiones.py
│   ├── catalogos.py
│   ├── procesos.py
│   └── operaciones.py
├── requirements.txt
├── Dockerfile
└── .streamlit/config.toml
```

### Escrituras

`operaciones.py` **no reimplementa** las reglas del negocio: importa
`Kopera/etl/validaciones.py` (réplica de los triggers) y
`Kopera/etl/transformacion.py` (`recalcular_analisis`). El compose monta
esa carpeta como `/etl` en modo lectura, así la app y el ETL nunca divergen.
Nunca se importa `Kopera/etl/config.py`, que arrastra el driver de Oracle.

## Colecciones que consume

| Colección | Uso en la app |
|---|---|
| `clientes` | documento agregado: datos, `creditos[].cuotas[]`, `inversiones[].movimientos[]`, `historial_pagos[]`, `analisis` |
| `catalogos` | 7 categorías de tablas maestras |
| `bitacora_pagos` | auditoría de pagos |
| `procesos_mensuales` | historial de ejecuciones del proceso mensual |

## Notas de implementación

- **Fechas**: `transformacion.py` guarda fechas como *texto* ISO
  (`_iso()`), no como `BSON date`; se parsean en `formato.py`.
- **Conexión**: un solo `MongoClient` por proceso vía `@st.cache_resource`,
  para no agotar las conexiones del tier M0 de Atlas.
- **Listas vs. ficha**: las vistas de listado proyectan solo campos de
  resumen; la ficha trae el documento completo.
