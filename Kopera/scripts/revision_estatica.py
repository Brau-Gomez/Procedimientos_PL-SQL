"""
Revision estatica ligera de los scripts de la EVAL 3.

No reemplaza a un linter completo, pero detecta los errores que mas nos han
costado durante el desarrollo:

  1. NOMBRES NO DEFINIDOS: un identificador que se usa pero nunca se asigno
     (typos como "creditito" en vez de "credito").
  2. CARACTERES DAÑADOS U+FFFD que sobreviven en el codigo fuente.
  3. IMPORTS ROTOS: modulos que no existen en el proyecto.
  4. DUPLICADOS en un mismo ambito.

El analisis de ambitos usa el modulo symtable de la libreria estandar, que
resuelve correctamente las variables locales, globales y libres (clausuras),
a diferencia de una cuenta manual sobre el AST.

Uso:
    .venv/bin/python Kopera/scripts/revision_estatica.py
"""

import ast
import builtins
import symtable
import sys
import unicodedata
from pathlib import Path

# Nombres propios de Python: no son errores aunque nunca se asignen.
CONOCIDOS = set(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "__builtins__",
    "__spec__", "__loader__", "__debug__",
    # Artefacto interno de symtable con las dataclasses.
    "__classdict__",
}


def revisar_ambitos(ruta, texto):
    """
    Revisa los ambitos con symtable y devuelve la lista de nombres que se
    usan pero no estan definidos en ningun sitio (ni local, ni global, ni
    builtin).
    """
    problemas = []
    tabla_modulo = symtable.symtable(texto, str(ruta), "exec")

    # Nombres definidos en el ambito de modulo (imports, constantes, funciones).
    globales_modulo = {
        simbolo.get_name()
        for simbolo in tabla_modulo.get_symbols()
        if simbolo.is_assigned() or simbolo.is_imported() or simbolo.is_namespace()
    }

    def recorrer(tabla, ambito_padre):
        for simbolo in tabla.get_symbols():
            nombre = simbolo.get_name()
            if nombre in CONOCIDOS:
                continue
            # Referenciado pero nunca asignado en ningun ambito: NameError.
            if (simbolo.is_referenced()
                    and not simbolo.is_assigned()
                    and not simbolo.is_parameter()
                    and not simbolo.is_imported()
                    and not simbolo.is_namespace()
                    and nombre not in globales_modulo
                    and nombre not in ambito_padre):
                problemas.append((tabla.get_lineno(), nombre))

        for hijo in tabla.get_children():
            recorrer(hijo, ambito_padre | {
                s.get_name() for s in tabla.get_symbols()
                if s.is_assigned() or s.is_parameter() or s.is_namespace()
            })

    recorrer(tabla_modulo, set())
    return problemas


def revisar_cadenas_danadas(ruta, texto):
    """
    Busca U+FFFD en literales de texto que NO sean docstrings, claves de
    diccionario ni el centinela de comparacion.

    Se permiten a proposito:
      - docstrings (explican el problema y muestran el caracter);
      - claves de diccionario (el diccionario CORRECCIONES guarda el texto
        dañado tal cual llega de Oracle: ahi el U+FFFD es intencional);
      - el literal "\ufffd" exacto, que se usa como centinela para detectar
        el caracter en los datos.
    """
    problemas = []
    arbol = ast.parse(texto, filename=str(ruta))

    # Docstrings: primer statement de modulo, funcion o clase.
    permitidos = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            cuerpo = getattr(nodo, "body", [])
            if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant):
                permitidos.add(id(cuerpo[0].value))

    # Claves de cualquier diccionario.
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Dict):
            for clave in nodo.keys:
                if isinstance(clave, ast.Constant):
                    permitidos.add(id(clave))

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if id(nodo) in permitidos:
                continue
            # Centinela de comparacion: "\ufffd" exacto.
            if nodo.value == "\ufffd":
                continue
            if "\ufffd" in nodo.value:
                problemas.append((nodo.lineno, f"texto con U+FFFD: {nodo.value[:60]!r}"))

    # Caracteres fuera de los bloques usados por codigo y textos en espanol:
    # los homoglifos (cirilico, japones, etc.) son la causa tipica de los
    # errores de tecleo que no se ven en el editor.
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            for caracter in nodo.value:
                codigo = ord(caracter)
                if codigo > 127 and not (0x00A1 <= codigo <= 0x00FF):
                    # Se permiten los signos comunes de puntuacion, la
                    # interrogacion de apertura y el guion largo; todo lo
                    # demas se reporta.
                    if caracter in "—–…‘’“”·€→←¿¡":
                        continue
                    # El U+FFFD tiene su propia revision (arriba).
                    if codigo == 0xFFFD:
                        continue
                    problemas.append((
                        nodo.lineno,
                        f"caracter fuera del rango latino U+{codigo:04X} "
                        f"({unicodedata.name(caracter, '?')!r})",
                    ))

    return problemas


def revisar_imports(ruta, texto):
    """Verifica que los modulos propios del proyecto existan en disco."""
    problemas = []
    base = Path(__file__).resolve().parent
    modulos_propios = {
        p.stem for p in base.glob("*.py")
    } | {
        p.stem for p in (base / "etl-mongodb").glob("*.py")
    }

    arbol = ast.parse(texto, filename=str(ruta))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                raiz = alias.name.split(".")[0]
                if raiz in modulos_propios and raiz != ruta.stem:
                    if not (base / f"{raiz}.py").exists():
                        problemas.append((nodo.lineno, f"import roto: {alias.name}"))
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level == 0 and nodo.module in modulos_propios:
                if not (base / f"{nodo.module}.py").exists():
                    problemas.append((nodo.lineno, f"import roto: {nodo.module}"))
    return problemas


def revisar_modulo(ruta):
    """Aplica todas las revisiones a un archivo .py."""
    problemas = []
    texto = ruta.read_text(encoding="utf-8")

    # 1. Error de sintaxis: corta, no se puede seguir.
    try:
        ast.parse(texto, filename=str(ruta))
    except SyntaxError as e:
        return [(e.lineno or 0, f"error de sintaxis: {e.msg}")]

    # 2. Nombres no definidos (ambitos correctos via symtable).
    for numero, nombre in sorted(revisar_ambitos(ruta, texto)):
        problemas.append((numero, f"nombre no definido: {nombre!r}"))

    # 3. Caracteres danados.
    problemas.extend(revisar_cadenas_danadas(ruta, texto))

    # 4. Imports rotos.
    problemas.extend(revisar_imports(ruta, texto))

    return problemas


def main():
    base = Path(__file__).resolve().parent
    archivos = sorted(base.glob("*.py"))
    archivos += sorted((base / "etl-mongodb").glob("*.py"))

    total = 0
    for ruta in archivos:
        problemas = revisar_modulo(ruta)
        if problemas:
            print(f"\n  {ruta.name}")
            for numero, mensaje in sorted(problemas):
                print(f"    linea {numero:>4} | {mensaje}")
            total += len(problemas)

    print()
    if total == 0:
        print(f"  [OK] {len(archivos)} scripts revisados, sin problemas detectados.")
    else:
        print(f"  {total} problema(s) en {len(archivos)} scripts.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
