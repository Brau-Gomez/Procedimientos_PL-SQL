@echo off
rem ============================================================
rem  Ejecuta scripts .sql dentro del contenedor de Oracle.
rem  Equivalente a ejecutar-sql.sh, para Windows (cmd.exe).
rem
rem  Uso (desde la raiz del repositorio):
rem    Kopera\sql\ejecutar-sql.bat Kopera\sql\01_tablas_apoyo.sql
rem    Kopera\sql\ejecutar-sql.bat Kopera\sql\03_package_analisis_kopera.sql
rem
rem  Requisitos:
rem    - Docker Desktop iniciado.
rem    - El contenedor "oracle-free" corriendo (docker compose up -d).
rem    - El archivo .env en la raiz del repositorio, con ORACLE_PASSWORD.
rem
rem  La clave se toma del .env, se pasa al contenedor como variable de
rem  entorno y se define dentro de SQL*Plus: no queda escrita en ningun
rem  archivo.
rem
rem  Limitacion: si la clave tiene caracteres especiales de cmd (& | % ^
rem  o comillas), usa SQL Developer o cambiala por una alfanumerica.
rem ============================================================
setlocal EnableExtensions DisableDelayedExpansion

if "%~1"=="" goto uso

set "CONTENEDOR=%ORACLE_CONTENEDOR%"
if not defined CONTENEDOR set "CONTENEDOR=oracle-free"
set "SERVICIO=%ORACLE_SERVICE_NAME%"
if not defined SERVICIO set "SERVICIO=FREEPDB1"
set "USUARIO=%ORACLE_USER%"
if not defined USUARIO set "USUARIO=ADMIN_PROYECTO"

rem Raiz del repositorio: dos carpetas arriba de este .bat
set "RAIZ=%~dp0..\.."
for %%R in ("%RAIZ%") do set "RAIZ=%%~fR"

if not exist "%RAIZ%\.env" goto sin_env

rem El .env entrecomilla la clave; %%~B quita las comillas.
set "CLAVE="
for /f "usebackq tokens=1,* delims==" %%A in ("%RAIZ%\.env") do (
    if /i "%%A"=="ORACLE_PASSWORD" set "CLAVE=%%~B"
)
if not defined CLAVE goto sin_clave

where docker >nul 2>&1
if errorlevel 1 goto sin_docker

docker ps --format "{{.Names}}" | findstr /x /c:"%CONTENEDOR%" >nul
if errorlevel 1 goto sin_contenedor

for %%F in (%*) do if not exist "%%~F" (
    echo ERROR: no existe el archivo "%%~F".
    echo        Ejecuta este .bat desde la raiz del repositorio.
    exit /b 1
)

rem ---------------------------------------------------- diagnostico
rem Se prueba la conexion antes de correr nada, para avisar si el usuario
rem no existe o si la clave del .env no coincide (ORA-01017).
set "DIAG=%TEMP%\kopera_sql_%RANDOM%.log"
docker exec -i -e CLAVE -e USUARIO -e SERVICIO "%CONTENEDOR%" bash -lc "echo 'SELECT 1 AS kopera_ok FROM dual;' | sqlplus -S -L $USUARIO/$CLAVE@localhost:1521/$SERVICIO" > "%DIAG%" 2>&1

findstr /c:"ORA-01017" "%DIAG%" >nul
if not errorlevel 1 goto error_credenciales

findstr /c:"KOPERA_OK" "%DIAG%" >nul
if errorlevel 1 goto error_conexion

del "%DIAG%" >nul 2>&1

rem ------------------------------------------------------ ejecucion
for %%F in (%*) do call :ejecutar "%%~F"
goto fin

:ejecutar
echo.
echo ================================================================
echo   Ejecutando: %~1
echo ================================================================
docker cp "%~1" "%CONTENEDOR%:/tmp/_kopera_script.sql" >nul
if errorlevel 1 goto error_copia
rem El DEFINE inyecta la clave sin que este en el archivo .sql; el tr
rem borra el CR de los archivos guardados con finales de linea Windows.
docker exec -i -e CLAVE -e USUARIO -e SERVICIO -e NLS_LANG=AMERICAN_AMERICA.AL32UTF8 "%CONTENEDOR%" bash -lc "{ echo DEFINE ORACLE_PASSWORD = \'$CLAVE\'; tr -d '\r' < /tmp/_kopera_script.sql; echo EXIT; } | sqlplus -S -L $USUARIO/$CLAVE@localhost:1521/$SERVICIO"
if errorlevel 1 goto error_sql
goto :eof

:uso
echo Uso: %~nx0 archivo.sql [mas archivos.sql ...]
echo.
echo Ejemplo:
echo   %~nx0 Kopera\sql\01_tablas_apoyo.sql
echo.
echo Ejecutalo desde la raiz del repositorio, donde esta el .env.
exit /b 1

:sin_env
echo ERROR: no existe "%RAIZ%\.env".
echo        Copia .env.example a .env y completa ORACLE_PASSWORD.
exit /b 1

:sin_clave
echo ERROR: ORACLE_PASSWORD vacio o ausente en "%RAIZ%\.env".
exit /b 1

:sin_docker
echo ERROR: no se encontro "docker". Instala Docker Desktop y abrilo.
exit /b 1

:sin_contenedor
echo ERROR: el contenedor "%CONTENEDOR%" no esta corriendo.
echo        Levantalo con:  docker compose up -d
echo        y espera a que el estado diga "healthy".
exit /b 1

:error_credenciales
echo.
echo ERROR: no se pudo conectar a Oracle como %USUARIO% (ORA-01017).
echo.
echo   Puede ser que el usuario %USUARIO% no exista todavia, o que la
echo   clave de ORACLE_PASSWORD en el .env no coincida con la del usuario.
echo.
echo   Si es la primera vez, corre el Paso 4:
echo     Kopera\sql\ejecutar-sql.bat Kopera\sql\base\CreacionUsuarios.sql.example
echo   Ojo: recrear el usuario BORRA las tablas y los datos que tengas.
del "%DIAG%" >nul 2>&1
exit /b 1

:error_conexion
echo.
echo ERROR: no se pudo conectar a Oracle.
echo   El contenedor "%CONTENEDOR%" puede estar terminando de arrancar.
echo   Espera a que "docker compose ps" muestre "healthy" y reintenta.
echo.
echo   Salida de SQL*Plus:
type "%DIAG%"
del "%DIAG%" >nul 2>&1
exit /b 1

:error_copia
echo.
echo ERROR: no se pudo copiar el archivo al contenedor.
echo        Revisa que Docker Desktop siga corriendo.
exit /b 1

:error_sql
echo.
echo ERROR: el script devolvio un error. Revisa el mensaje de arriba.
exit /b 1

:fin
echo.
echo Listo. Si el script imprime DBMS_OUTPUT, ese es el resultado esperado.
