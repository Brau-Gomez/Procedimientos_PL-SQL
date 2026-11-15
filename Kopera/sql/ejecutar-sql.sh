#!/usr/bin/env bash
#
# Ejecuta un script .sql dentro del contenedor de Oracle.
#
# ¿Por qué existe esto?
#   Para no obligar a instalar Oracle SQL Developer. El contenedor de Oracle
#   ya trae SQL*Plus adentro, asi que este script te conecta y te pasa el
#   archivo, tal cual.
#
# Uso:
#   ./Kopera/sql/ejecutar-sql.sh Kopera/sql/01_tablas_apoyo.sql
#   ./Kopera/sql/ejecutar-sql.sh Kopera/sql/03_package_analisis_kopera.sql
#
# Si el script usa la variable &ORACLE_PASSWORD (como
# base/CreacionUsuarios.sql.example), se reemplaza sola con la clave que
# tienes en el .env de la raiz. No tenes que escribirla en ningun archivo.
#
# Requisitos:
#   - El contenedor "oracle-free" corriendo (docker compose up -d).
#   - El archivo .env en la raiz del repositorio, con ORACLE_PASSWORD.
#
# Los acentos se ven bien: el script le pasa NLS_LANG=AMERICAN_AMERICA.AL32UTF8
# a SQL*Plus. Sin eso, la consola muestra "An?lisis" en vez de "Análisis".

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTENEDOR="${ORACLE_CONTENEDOR:-oracle-free}"
SERVICIO="${ORACLE_SERVICE_NAME:-FREEPDB1}"

# ---------------------------------------------------------------- argumentos
if [[ $# -lt 1 ]]; then
    echo "Uso: $0 <archivo.sql> [más archivos.sql ...]" >&2
    echo "" >&2
    echo "Ejemplo:" >&2
    echo "  $0 Kopera/sql/01_tablas_apoyo.sql" >&2
    exit 1
fi

for archivo in "$@"; do
    if [[ ! -f "$archivo" ]]; then
        echo "ERROR: no existe el archivo '$archivo'." >&2
        echo "       ¿Lo ejecutaste desde la raiz del repositorio?" >&2
        exit 1
    fi
done

# ------------------------------------------------------------- .env y clave
ENV_FILE="$RAIZ/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: no existe el archivo .env en la raiz del repositorio." >&2
    echo "       Creálo con:  cp .env.example .env" >&2
    echo "       y completá ORACLE_PASSWORD." >&2
    exit 1
fi

CLAVE="$(grep -E '^ORACLE_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" | tr -d "'")"
if [[ -z "$CLAVE" ]]; then
    echo "ERROR: ORACLE_PASSWORD vacio o ausente en el .env." >&2
    exit 1
fi

# -------------------------------------------------------------- contenedor
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTENEDOR"; then
    echo "ERROR: el contenedor '$CONTENEDOR' no está corriendo." >&2
    echo "       Levantálo con:  docker compose up -d" >&2
    echo "       y esperá a que la columna STATUS diga 'healthy'." >&2
    exit 1
fi

# --------------------------------------------------------------- ejecución
for archivo in "$@"; do
    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo "  Ejecutando: $archivo"
    echo "════════════════════════════════════════════════════════════════════"
    # El DEFINE reemplaza &ORACLE_PASSWORD por la clave del .env, sin que
    # quede escrita en ningun archivo.
    {
        echo "DEFINE ORACLE_PASSWORD = '$CLAVE'"
        cat "$archivo"
        echo "EXIT"
    } | docker exec -i -e CLAVE="$CLAVE" -e NLS_LANG=AMERICAN_AMERICA.AL32UTF8 "$CONTENEDOR" \
        bash -lc "sqlplus -S \"ADMIN_PROYECTO/\$CLAVE@localhost:1521/$SERVICIO\"" || {
            echo ""
            echo "ERROR: el script devolvió un error. Revisá el mensaje de arriba." >&2
            exit 1
        }
done

echo ""
echo "Listo. Si el script imprime DBMS_OUTPUT, ese es el resultado esperado."
