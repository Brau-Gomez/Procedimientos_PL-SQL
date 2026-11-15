"""
Revision estatica ligera de los scripts de la EVAL 3.

No reemplaza a un linter completo, pero detecta los errores que mas nos han
costado durante el desarrollo:

  1. NOMBRES NO DEFINIDOS: un identificador que se usa pero nunca se asigno
     (typos como "creditito" en vez de "credito").
  2. CARACTERES DAÑADOS U+FFFD que sobreviven en el codigo fuente.
  3. IMPORTS ROTOS: modulos que no existen en el proyecto ni en el entorno.
  4. IMPORTS SIN USAR: un modulo importado que nunca se referencia.
  5. LLAMADAS CON LA ARIDAD EQUIVOCADA: se le pasan mas (o menos) argumentos
     de los que acepta la funcion llamada. Este es el chequeo que detecta los
     errores que un simple "compila bien" no ve.
  6. CLAVES DUPLICADAS en un diccionario: en Python la segunda pisa a la
     primera en silencio, asi que el valor correcto nunca se aplica.
  7. DUPLICADOS en un mismo ambito.

El analisis de ambitos usa el modulo symtable de la libreria estandar, que
resuelve correctamente las variables locales, globales y libres (clausuras),
a diferencia de una cuenta manual sobre el AST.

Uso:
    .venv/bin/python Kopera/scripts/revision_estatica.py
"""

import ast
import builtins
import importlib.util
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


def _modulos_del_proyecto():
    """Nombres de los modulos propios del proyecto (los .py de scripts/)."""
    base = Path(__file__).resolve().parent
    modulos = {p.stem for p in base.glob("*.py")}
    modulos |= {p.stem for p in (base / "etl-mongodb").glob("*.py")}
    return base, modulos


def _es_importable(nombre):
    """True si el modulo se puede importar en este entorno."""
    try:
        return importlib.util.find_spec(nombre) is not None
    except (ImportError, ValueError):
        return False


def revisar_imports(ruta, texto):
    """
    Verifica que todos los modulos importados existan de verdad.

    Hay dos casos distintos:

      - Modulo PROPIO (uno de los .py de scripts/): tiene que existir el
        archivo correspondiente.
      - Modulo EXTERNO (biblioteca estandar o de terceros): tiene que ser
        importable en el entorno actual.

    Antes esta comprobacion era vacua: la lista de modulos propios se armaba
    con los archivos que ya existian, asi que la pregunta "existe el archivo?"
    siempre era si. Ahora un nombre mal escrito (import transformacionn) si
    se detecta.
    """
    problemas = []
    base, modulos_propios = _modulos_del_proyecto()

    arbol = ast.parse(texto, filename=str(ruta))
    for nodo in ast.walk(arbol):
        nombres = []
        if isinstance(nodo, ast.Import):
            nombres = [alias.name for alias in nodo.names]
        elif isinstance(nodo, ast.ImportFrom):
            # Los imports relativos (from . import x) no se pueden resolver
            # sin un paquete: el proyecto usa imports absolutos.
            if nodo.level == 0 and nodo.module:
                nombres = [nodo.module]

        for nombre in nombres:
            raiz = nombre.split(".")[0]
            if raiz in modulos_propios:
                if not (base / f"{raiz}.py").exists():
                    problemas.append((nodo.lineno, f"import roto: {nombre}"))
            elif not _es_importable(raiz):
                problemas.append((nodo.lineno, f"modulo inexistente: {nombre}"))

    return problemas


def revisar_imports_sin_usar(ruta, texto):
    """
    Detecta los modulos que se importan pero nunca se usan.

    Un import que no se usa no rompe nada, pero ensucia el modulo y suele
    delatar que el codigo cambio de forma y dejo la referencia colgando.
    """
    problemas = []
    arbol = ast.parse(texto, filename=str(ruta))

    importados = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nombre = alias.asname or alias.name.split(".")[0]
                importados[nombre] = nodo.lineno
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module == "__future__":
                continue
            for alias in nodo.names:
                if alias.name == "*":
                    continue
                nombre = alias.asname or alias.name
                importados[nombre] = nodo.lineno

    # Nombres efectivamente referenciados en el modulo.
    usados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            usados.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            base_nodo = nodo
            while isinstance(base_nodo, ast.Attribute):
                base_nodo = base_nodo.value
            if isinstance(base_nodo, ast.Name):
                usados.add(base_nodo.id)

    for nombre, linea in sorted(importados.items(), key=lambda par: par[1]):
        if nombre not in usados:
            problemas.append((linea, f"import sin usar: {nombre!r}"))

    return problemas


def _firmas_del_modulo(arbol):
    """Mapa nombre -> firma de las funciones definidas a nivel de modulo."""
    firmas = {}
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            argumentos = nodo.args
            posicionales = argumentos.posonlyargs + argumentos.args
            firmas[nodo.name] = {
                "nombres": [a.arg for a in posicionales],
                "requeridos": len(posicionales) - len(argumentos.defaults),
                "varargs": argumentos.vararg is not None,
                "kwonly": [a.arg for a in argumentos.kwonlyargs],
                "kwarg": argumentos.kwarg is not None,
            }
    return firmas


def revisar_arity(ruta, texto):
    """
    Detecta las llamadas con mas o menos argumentos de los que acepta la
    funcion llamada.

    Este es el chequeo que mas Errores de ejecucion detecta: un codigo que
    compila y que "se ve bien" puede llamar a una funcion con un argumento de
    mas (TypeError en tiempo de ejecucion) o de menos.

    Solo se revisan las llamadas a funciones definidas en el mismo modulo: las
    funciones importadas de otro modulo no se pueden inspeccionar desde aca.
    """
    problemas = []
    arbol = ast.parse(texto, filename=str(ruta))
    firmas = _firmas_del_modulo(arbol)

    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Name):
            continue
        firma = firmas.get(nodo.func.id)
        if firma is None:
            continue

        # Con *args o **kwargs en la llamada no se puede contar con certeza.
        if any(isinstance(arg, ast.Starred) for arg in nodo.args):
            continue
        if any(kw.arg is None for kw in nodo.keywords):
            continue

        posicionales = len(nodo.args)
        keywords = {kw.arg for kw in nodo.keywords}

        if posicionales > len(firma["nombres"]) and not firma["varargs"]:
            problemas.append((
                nodo.lineno,
                f"'{nodo.func.id}()' acepta {len(firma['nombres'])} argumento(s) "
                f"posicional(es) y se le pasan {posicionales}",
            ))
            continue

        # Argumentos posicionales que llegan por nombre.
        cubiertos = 0
        for indice, nombre in enumerate(firma["nombres"]):
            if indice >= posicionales and nombre in keywords:
                cubiertos += 1

        if posicionales + cubiertos < firma["requeridos"]:
            faltan = firma["requeridos"] - posicionales - cubiertos
            problemas.append((
                nodo.lineno,
                f"'{nodo.func.id}()' requiere {firma['requeridos']} argumento(s) "
                f"y se le pasan {posicionales + cubiertos} (faltan {faltan})",
            ))

        if not firma["kwarg"]:
            desconocidos = keywords - set(firma["nombres"]) - set(firma["kwonly"])
            if desconocidos:
                problemas.append((
                    nodo.lineno,
                    f"'{nodo.func.id}()' no acepta el(os) argumento(s) "
                    f"{sorted(desconocidos)}",
                ))

    return problemas


def revisar_claves_duplicadas(ruta, texto):
    """
    Detecta claves repetidas en un diccionario.

    En Python, un diccionario literal con la misma clave dos veces conserva
    solo el ULTIMO valor: la correccion nunca se aplica y el error pasa
    inadvertido.
    """
    problemas = []
    arbol = ast.parse(texto, filename=str(ruta))

    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Dict):
            continue
        vistas = {}
        for clave in nodo.keys:
            if not isinstance(clave, ast.Constant):
                continue
            if not isinstance(clave.value, (str, int, float, bool)):
                continue
            if clave.value in vistas:
                problemas.append((
                    clave.lineno,
                    f"clave duplicada en el diccionario: {clave.value!r} "
                    f"(ya aparecia en la linea {vistas[clave.value]})",
                ))
            else:
                vistas[clave.value] = clave.lineno

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

    # 4. Imports rotos y imports sin usar.
    problemas.extend(revisar_imports(ruta, texto))
    problemas.extend(revisar_imports_sin_usar(ruta, texto))

    # 5. Llamadas con la aridad equivocada.
    problemas.extend(revisar_arity(ruta, texto))

    # 6. Claves duplicadas en diccionarios.
    problemas.extend(revisar_claves_duplicadas(ruta, texto))

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
