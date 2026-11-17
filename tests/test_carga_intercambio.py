"""
Prueba del intercambio de colecciones en la carga (carga_mongodb.py).

La regla que se protege: la coleccion viva nunca se borra antes de que la
nueva exista completa. Se usa una base falsa, sin Atlas.
"""

from pymongo.errors import BulkWriteError

import carga_mongodb as carga


class ColeccionFalsa:
    def __init__(self, base, nombre):
        self.base = base
        self.nombre = nombre

    def drop(self):
        self.base.orden.append(("drop", self.nombre))

    def insert_many(self, documentos, ordered=False):
        self.base.orden.append(("insert", self.nombre, len(documentos)))
        return type("Resultado", (), {"inserted_ids": [d["_id"] for d in documentos]})

    def create_indexes(self, indices):
        self.base.orden.append(("indices", self.nombre))
        return indices


class AdminFalso:
    def __init__(self, base):
        self.base = base

    def command(self, comando, origen, **kwargs):
        self.base.orden.append(("rename", comando, origen, kwargs))


class ColeccionQueRechaza(ColeccionFalsa):
    """Simula un documento que el validador $jsonSchema rechaza."""

    def insert_many(self, documentos, ordered=False):
        self.base.orden.append(("insert", self.nombre, len(documentos)))
        raise BulkWriteError({
            "writeErrors": [{
                "index": 0, "code": 121,
                "errmsg": "Document failed validation", "errInfo": {},
            }],
            "nInserted": 0,
        })


class BaseFalsa:
    name = "kopera"

    def __init__(self, existentes=("clientes",), coleccion=ColeccionFalsa):
        self.coleccion = coleccion
        self.colecciones = {n: coleccion(self, n) for n in existentes}
        self.orden = []
        self.client = type("Cliente", (), {"admin": AdminFalso(self)})

    def list_collection_names(self):
        return list(self.colecciones)

    def create_collection(self, nombre, **kwargs):
        self.colecciones[nombre] = self.coleccion(self, nombre)
        self.orden.append(("create", nombre, kwargs))

    def __getitem__(self, nombre):
        return self.colecciones.setdefault(nombre, self.coleccion(self, nombre))


def test_el_intercambio_no_borra_la_coleccion_viva():
    base = BaseFalsa()

    insertados, rechazados, intercambiada = carga._cargar_por_intercambio(
        base, "clientes", [{"_id": 1}, {"_id": 2}]
    )

    assert (insertados, rechazados, intercambiada) == (2, [], True)
    # Nunca se borra "clientes": solo la temporal y despues del rename.
    assert ("drop", "clientes") not in base.orden

    create = next(paso for paso in base.orden if paso[0] == "create")
    assert create[1] == "clientes_nueva"
    assert create[2]["validator"] == carga.VALIDADORES["clientes"]

    rename = next(paso for paso in base.orden if paso[0] == "rename")
    assert rename[2] == "kopera.clientes_nueva"
    assert rename[3] == {"to": "kopera.clientes", "dropTarget": True}
    # Se indexa antes de insertar: el unico de RUN rechaza duplicados como
    # documento (rechazado), no como excepcion al construir el indice.
    posiciones = [paso[0] for paso in base.orden]
    assert posiciones.index("indices") < posiciones.index("insert") < posiciones.index("rename")


def test_la_temporal_se_descarta_antes_de_cargar():
    base = BaseFalsa(existentes=("clientes", "clientes_nueva"))

    carga._cargar_por_intercambio(base, "clientes", [{"_id": 1}])

    assert base.orden[0] == ("drop", "clientes_nueva")


def test_una_carga_rechazada_no_se_intercambia():
    base = BaseFalsa(coleccion=ColeccionQueRechaza)

    insertados, rechazados, intercambiada = carga._cargar_por_intercambio(
        base, "clientes", [{"_id": 1}]
    )

    assert (insertados, len(rechazados), intercambiada) == (0, 1, False)
    assert not any(paso[0] == "rename" for paso in base.orden)
    # La viva queda intacta y la temporal a medias se descarta.
    assert ("drop", "clientes") not in base.orden
    assert ("drop", "clientes_nueva") in base.orden


def test_los_procesos_no_pasan_por_el_intercambio(monkeypatch):
    base = BaseFalsa()
    intercambiadas = []

    def intercambio_falso(base, nombre, documentos):
        intercambiadas.append(nombre)
        return len(documentos), [], True

    monkeypatch.setattr(carga, "_preparar_procesos", lambda base: None)
    monkeypatch.setattr(carga, "_cargar_por_intercambio", intercambio_falso)

    reporte = carga.cargar_todo(
        base, [{"_id": 1}], [{"_id": 2}], [{"_id": 3}], [{"_id": "proceso"}]
    )

    assert intercambiadas == [
        carga.COLECCION_CLIENTES, carga.COLECCION_CATALOGOS, carga.COLECCION_BITACORA
    ]
    # El historico se agrega a la coleccion viva, sin rename.
    assert ("insert", carga.COLECCION_PROCESOS, 1) in base.orden
    assert reporte["colecciones_recargadas"] == intercambiadas
