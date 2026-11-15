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

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTENEDOR="${ORACLE_CONTENEDOR:-oracle-free}"
SERVICIO="${ORACLE_SERVICE_NAME:-FREEPDB1}"
USUARIO="${ORACLE_USER:-ADMIN_PROYECTO}"

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

# ==========================================================================
# DIAGNÓSTICO PREVIO
#
# Oracle devuelve ORA-01017 "invalid credential" en DOS casos distintos:
#   1. el usuario no existe todavia;
#   2. el usuario existe pero la clave esta mal.
# Oracle no dice cual de los dos es, asi que se comprueba aparte: si el
# usuario esta en la PDB, el problema es la clave; si no esta, es que
# falta crear el usuario.
# ==========================================================================
existe_en_pdb() {
    docker exec -i "$CONTENEDOR" bash -lc "sqlplus -S / as sysdba@$SERVICIO" <<SQL 2>/dev/null
SET HEADING OFF FEEDBACK OFF
SELECT COUNT(*) FROM cdb_users u JOIN v\$containers c ON u.con_id = c.con_id
 WHERE u.username = '$USUARIO' AND c.name = '$SERVICIO';
EXIT
SQL
}

diagnosticar_conexion() {
    local salida
    salida=$(
        {
            echo "SELECT 1 FROM dual;"
            echo "EXIT"
        } | docker exec -i -e CLAVE="$CLAVE" "$CONTENEDOR" \
            bash -lc "sqlplus -S -L \"$USUARIO/\$CLAVE@localhost:1521/$SERVICIO\"" 2>&1
    ) || true

    if echo "$salida" | grep -q "ORA-01017"; then
        echo "ERROR: no se pudo conectar a Oracle como $USUARIO (ORA-01017)." >&2
        echo "" >&2
        if [[ "$(existe_en_pdb | tr -dc '0-9')" == "0" ]]; then
            echo "  El usuario $USUARIO NO existe todavía en la base de datos." >&2
            echo "  -> Corrê el Paso 4 de la guía para crearlo:" >&2
            echo "       ./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/CreacionUsuarios.sql.example" >&2
        else
            echo "  El usuario $USUARIO existe, pero la clave no coincide." >&2
            echo "  -> La clave de ORACLE_PASSWORD en tu .env es distinta de la del usuario." >&2
            echo "     Opción 1: corregí ORACLE_PASSWORD en el .env." >&2
            echo "     Opción 2: recreá el usuario con la clave del .env (Paso 4):" >&2
            echo "       ./Kopera/sql/ejecutar-sql.sh Kopera/sql/base/CreacionUsuarios.sql.example" >&2
            echo "     Ojo: recrear el usuario BORRA las tablas y los datos que tengas." >&2
        fi
        exit 1
    fi

    if echo "$salida" | grep -qE "ORA-12541|SP2-0313|SP2-1251|SP2-0751"; then
        echo "ERROR: no se pudo conectar a Oracle." >&2
        echo "       ¿El contenedor '$CONTENEDOR' está terminando de arrancar?" >&2
        echo "       Esperá a que 'docker compose ps' muestre 'healthy' y probá de nuevo." >&2
        exit 1
    fi
}

diagnosticar_conexion

# --------------------------------------------------------------- ejecución
for archivo in "$@"; do
    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo "  Ejecutando: $archivo"
    echo "════════════════════════════════════════════════════════════════════"
    # El DEFINE reemplaza &ORACLE_PASSWORD por la clave del .env, sin que
    # quede escrita en ningun archivo.
    # El -L (logon once) evita que SQL*Plus reintente el login y se coma la
    # linea siguiente del script como si fuera la contrasena.
    {
        echo "DEFINE ORACLE_PASSWORD = '$CLAVE'"
        cat "$archivo"
        echo "EXIT"
    } | docker exec -i -e CLAVE="$CLAVE" -e NLS_LANG=AMERICAN_AMERICA.AL32UTF8 "$CONTENEDOR" \
        bash -lc "sqlplus -S -L \"$USUARIO/\$CLAVE@localhost:1521/$SERVICIO\"" || {
            echo ""
            echo "ERROR: el script devolvió un error. Revisá el mensaje de arriba." >&2
            exit 1
        }
done

echo ""
echo "Listo. Si el script imprime DBMS_OUTPUT, ese es el resultado esperado."
