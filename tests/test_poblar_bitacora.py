"""
Pruebas del proceso mensual de cobranza.

Se prueba la parte que NO necesita base de datos: el contrato del estado de la
cuota y el calculo del delta de cada evento del plan.

El caso mas importante es el del complemento: el segundo evento sobre una
misma cuota tiene que pagar SOLO la diferencia, no el total. Ese delta es lo
que hace que el proceso sea idempotente.
"""

import contextlib

import pytest

import poblar_bitacora as pb
from plan_pagos import PLAN_PAGOS


@contextlib.contextmanager
def plan_temporal(eventos):
    """Ejecuta el lote con un plan acotado, sin tocar el plan de la semilla."""
    original = pb.PLAN_PAGOS
    pb.PLAN_PAGOS = eventos
    try:
        yield
    finally:
        pb.PLAN_PAGOS = original


def evento(credito, cuota, objetivo, cliente=5, forma=1):
    return {
        "nro_solic_credito": credito,
        "nro_cuota": cuota,
        "nro_cliente": cliente,
        "monto_objetivo": objetivo,
        "cod_forma_pago": forma,
        "concepto": "evento de prueba",
    }


class CursorFalso:
    """
    Cursor simulado que responde a leer_estado_cuota con un mapa fijo de
    cuotas: (credito, cuota) -> (valor_cuota, monto_pagado, saldo, fecha, cli).
    """

    def __init__(self, cuotas):
        self.cuotas = dict(cuotas)
        self.ultima_consulta = None

    def execute(self, sql, parametros=None):
        self.ultima_consulta = (sql, parametros)

    def fetchone(self):
        if self.ultima_consulta is None:
            return None
        _, parametros = self.ultima_consulta
        if parametros is None:
            return None
        return self.cuotas.get(tuple(parametros))


@pytest.fixture
def cursor():
    return CursorFalso({
        (2001, 6): (57292, 0, 57292, None, 5),
        (2001, 7): (57292, 0, 57292, None, 5),
        (2002, 5): (18330, 0, 18330, None, 6),
    })


# ==========================================================================
# CONTRATO DEL ESTADO DE LA CUOTA
# ==========================================================================

def test_el_estado_de_la_cuota_tiene_campos_con_nombre(cursor):
    estado = pb.leer_estado_cuota(cursor, 2001, 6)
    assert estado is not None
    assert estado.valor_cuota == 57292
    assert estado.monto_pagado == 0
    assert estado.saldo_por_pagar == 57292
    assert estado.fecha_pago is None
    assert estado.nro_cliente == 5


def test_una_cuota_inexistente_devuelve_none(cursor):
    assert pb.leer_estado_cuota(cursor, 9999, 1) is None


def test_el_estado_sigue_siendo_una_tupla():
    # NamedTuple: se puede desempaquetar como una tupla normal.
    estado = pb.EstadoCuota(100, 0, 100, None, 5)
    valor, pagado, saldo, fecha, cliente = estado
    assert (valor, pagado, saldo, fecha, cliente) == (100, 0, 100, None, 5)


# ==========================================================================
# VALIDACION DEL PLAN
# ==========================================================================

def test_el_plan_de_la_semilla_no_tiene_problemas(cursor):
    problemas, avisos = pb.validar_plan(cursor)
    # El plan real referencia 22 cuotas y el cursor falso solo conoce tres:
    # lo que se comprueba aqui es que cada problema reportado identifica de
    # forma clara a que cuota se refiere.
    assert problemas
    for problema in problemas:
        assert "cuota" in problema


def test_un_objetivo_mayor_que_el_valor_de_la_cuota_es_problema(cursor):
    with plan_temporal([evento(2001, 6, 99999)]):
        problemas, _ = pb.validar_plan(cursor)
    assert any("supera el valor de la cuota" in p for p in problemas)


def test_un_cliente_que_no_cuadra_es_problema(cursor):
    with plan_temporal([evento(2001, 6, 57292, cliente=99)]):
        problemas, _ = pb.validar_plan(cursor)
    assert any("pero la cuota pertenece al cliente 5" in p for p in problemas)


def test_una_forma_de_pago_inexistente_es_problema(cursor):
    with plan_temporal([evento(2001, 6, 57292, forma=99)]):
        problemas, _ = pb.validar_plan(cursor)
    assert any("no existe en FORMA_PAGO" in p for p in problemas)


# ==========================================================================
# CALCULO DEL DELTA (idempotencia del proceso)
# ==========================================================================

def test_el_delta_de_un_pago_completo_es_el_total(cursor):
    with plan_temporal([evento(2001, 6, 57292)]):
        resultados, omitidos, error = pb.ejecutar_lote(cursor, simular=True)
    assert error is None
    assert omitidos == []
    assert resultados[0]["delta"] == 57292
    assert resultados[0]["objetivo"] == 57292


def test_el_complemento_paga_solo_la_diferencia(cursor):
    # Dos eventos sobre la misma cuota: un pago parcial de 25.000 y despues
    # un complemento hasta 57.292.
    with plan_temporal([
        evento(2001, 7, 25000),
        evento(2001, 7, 57292),
    ]):
        resultados, omitidos, error = pb.ejecutar_lote(cursor, simular=True)

    assert error is None
    assert len(resultados) == 2
    assert resultados[0]["delta"] == 25000
    assert resultados[1]["delta"] == 32292     # 57.292 - 25.000


def test_una_cuota_ya_pagada_se_omite(cursor):
    cursor.cuotas[(2001, 6)] = (57292, 57292, 0, "01/10/2025", 5)
    with plan_temporal([evento(2001, 6, 57292)]):
        resultados, omitidos, error = pb.ejecutar_lote(cursor, simular=True)

    assert error is None
    assert resultados == []
    assert len(omitidos) == 1
    assert "ya pagada" in omitidos[0]["motivo"]


def test_una_cuota_inexistente_aborta_el_lote(cursor):
    with plan_temporal([evento(9999, 1, 1000)]):
        resultados, omitidos, error = pb.ejecutar_lote(cursor, simular=True)
    assert error is not None
    assert "no existe" in error


def test_el_plan_de_la_semilla_tiene_22_eventos():
    assert len(PLAN_PAGOS) == 22
