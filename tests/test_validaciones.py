"""
Pruebas de las reglas de negocio replicadas desde los triggers de Oracle.

Cubre validaciones.py: REGLA 1 (trg_cuota_valida_pago), REGLA 2
(trg_cuota_bitacora), REGLA 3 (trg_movimiento_valida) y REGLA 4
(trg_movimiento_actualiza_ahorro).

Son funciones puras: no necesitan Oracle ni Atlas.
"""

import pytest

import validaciones as v


# ==========================================================================
# REGLA 1 - trg_cuota_valida_pago
# ==========================================================================

def test_pago_fuera_de_rango_se_rechaza():
    resultado = v.validar_pago_cuota(57292, 99999)
    assert not resultado.valido
    assert resultado.errores[0]["codigo"] == v.CODIGO_ERROR_PAGO_FUERA_DE_RANGO


def test_pago_negativo_se_rechaza():
    resultado = v.validar_pago_cuota(57292, -1)
    assert not resultado.valido
    assert resultado.errores[0]["codigo"] == v.CODIGO_ERROR_PAGO_FUERA_DE_RANGO


def test_el_saldo_se_deriva_del_pago():
    resultado = v.validar_pago_cuota(57292, 25000)
    assert resultado.valido
    assert resultado.datos["saldo_por_pagar"] == 32292
    assert resultado.datos["monto_pagado"] == 25000


def test_saldo_almacenado_distinto_del_derivado_es_observacion():
    # No es un error: la inconsistencia ya existia en los datos migrados.
    resultado = v.validar_pago_cuota(57292, 25000, saldo_actual=99999)
    assert resultado.valido
    assert resultado.observaciones
    assert resultado.observaciones[0]["codigo"] == v.CODIGO_ERROR_PAGO_FUERA_DE_RANGO


def test_un_null_no_es_una_observacion():
    resultado = v.validar_pago_cuota(57292, None)
    assert resultado.valido
    assert not resultado.observaciones
    assert resultado.datos["monto_pagado"] == 0


# ==========================================================================
# REGLA 2 - trg_cuota_bitacora
# ==========================================================================

def test_sin_cambio_de_monto_no_hay_evento():
    evento = v.construir_evento_bitacora(
        {"nro_cuota": 7, "valor_cuota": 57292}, 5, 25000, 25000, "Efectivo"
    )
    assert evento is None


def test_con_cambio_de_monto_hay_evento():
    evento = v.construir_evento_bitacora(
        {"nro_cuota": 7, "valor_cuota": 57292}, 5, 25000, 57292, "Efectivo",
        nro_credito=2001,
    )
    assert evento is not None
    assert evento["monto_pagado_anterior"] == 25000
    assert evento["monto_pagado_nuevo"] == 57292
    assert evento["saldo_resultante"] == 0
    assert evento["nro_solic_credito"] == 2001


def test_null_anterior_y_cero_nuevo_son_cambio_real():
    # El trigger usa -1 como centinela del NULL: un NULL anterior y un 0 nuevo
    # SI son un cambio.
    evento = v.construir_evento_bitacora(
        {"nro_cuota": 7, "valor_cuota": 57292}, 5, None, 0, "Efectivo",
    )
    assert evento is not None
    assert evento["monto_pagado_anterior"] is None
    assert evento["monto_pagado_nuevo"] == 0


# ==========================================================================
# REGLA 3 - trg_movimiento_valida
# ==========================================================================

@pytest.fixture
def inversion():
    return {
        "nro_solic_prod": 250001,
        "monto_total_ahorrado": 100000,
        "producto": {"porc_maximo_rescate": 50},
        "movimientos": [],
    }


def test_monto_no_positivo_se_rechaza(inversion):
    resultado = v.validar_movimiento(inversion, -5000, "ABONO")
    assert not resultado.valido
    assert resultado.errores[0]["codigo"] == v.CODIGO_ERROR_MONTO_NO_POSITIVO


def test_tipo_invalido_se_rechaza(inversion):
    resultado = v.validar_movimiento(inversion, 1000, "TRANSFERENCIA")
    assert not resultado.valido
    assert resultado.errores[0]["codigo"] == v.CODIGO_ERROR_TIPO_MOVIMIENTO


def test_rescate_que_excede_el_saldo_se_rechaza(inversion):
    resultado = v.validar_movimiento(inversion, 200000, "RESCATE")
    assert not resultado.valido
    codigos = {e["codigo"] for e in resultado.errores}
    assert v.CODIGO_ERROR_RESCATE_EXCEDE_SALDO in codigos


def test_rescate_que_excede_el_porcentaje_se_rechaza(inversion):
    # Con 50% de maximo, un rescate de 60.000 esta bajo el saldo pero sobre
    # el limite porcentual: debe dispararse solo el codigo -20013.
    resultado = v.validar_movimiento(inversion, 60000, "RESCATE")
    assert not resultado.valido
    codigos = {e["codigo"] for e in resultado.errores}
    assert v.CODIGO_ERROR_RESCATE_EXCEDE_PORCENTAJE in codigos
    assert v.CODIGO_ERROR_RESCATE_EXCEDE_SALDO not in codigos


def test_abono_valido_calcula_el_saldo_nuevo(inversion):
    resultado = v.validar_movimiento(inversion, 30000, "ABONO")
    assert resultado.valido
    assert resultado.datos["saldo_actualizado"] == 130000
    assert resultado.datos["signo"] == 1


def test_el_tipo_se_normaliza_a_mayusculas(inversion):
    resultado = v.validar_movimiento(inversion, 1000, "abono")
    assert resultado.valido


# ==========================================================================
# REGLA 4 - trg_movimiento_actualiza_ahorro
# ==========================================================================

def test_abono_suma_al_saldo(inversion):
    assert v.calcular_ahorro_actualizado(inversion, 30000, "ABONO") == 130000


def test_rescate_resta_al_saldo(inversion):
    assert v.calcular_ahorro_actualizado(inversion, 10000, "RESCATE") == 90000


def test_tipo_invalido_no_toca_el_saldo(inversion):
    assert v.calcular_ahorro_actualizado(inversion, 10000, "TRANSFERENCIA") == 100000


def test_regla_3_y_regla_4_coinciden(inversion):
    # El saldo que calcula la REGLA 3 debe ser el mismo que el de la REGLA 4.
    validacion = v.validar_movimiento(inversion, 30000, "ABONO")
    assert validacion.datos["saldo_actualizado"] == \
        v.calcular_ahorro_actualizado(inversion, 30000, "ABONO")


# ==========================================================================
# CONTROL DE CALIDAD DEL DOCUMENTO YA MIGRADO
# ==========================================================================

def test_documento_con_datos_sanos_no_reporta_errores():
    documento = {
        "creditos": [{
            "nro_solic_credito": 2001,
            "cuotas": [{
                "nro_cuota": 1, "valor_cuota": 1000, "monto_pagado": 1000,
                "saldo_por_pagar": 0,
            }],
        }],
        "inversiones": [{
            "nro_solic_prod": 250001,
            "monto_total_ahorrado": 100000,
            "producto": {"porc_maximo_rescate": 50},
            "movimientos": [{"tipo_movimiento": "ABONO", "monto": 100000, "signo": 1}],
        }],
    }
    resultado = v.validar_documento_cliente(documento)
    assert resultado.valido
    assert not resultado.errores


def test_resumen_cuenta_errores_y_observaciones():
    resultados = [
        v.ResultadoValidacion(),
        v.ResultadoValidacion(),
    ]
    resultados[0].agregar_error(-20001, "error")
    resultados[1].agregar_observacion(-20014, "observacion")

    resumen = v.resumir_validaciones(resultados)
    assert resumen["documentos_validados"] == 2
    assert resumen["documentos_validos"] == 1
    assert resumen["documentos_con_errores"] == 1
    assert resumen["documentos_con_observaciones"] == 1
    assert resumen["total_errores"] == 1
    assert resumen["total_observaciones"] == 1
    assert resumen["errores_por_codigo"] == {"-20001": 1}
    assert resumen["observaciones_por_codigo"] == {"-20014": 1}
