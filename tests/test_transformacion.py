"""
Pruebas de la transformacion: limpieza de caracteres, clasificacion y
recalculo del bloque "analisis".

Son funciones puras: no necesitan Oracle ni Atlas.
"""

import pytest

import transformacion as T


# ==========================================================================
# LIMPIEZA DE CARACTERES
# ==========================================================================

def test_limpia_el_caracter_danado():
    assert T.limpiar_texto("Mart�nez") == "Martínez"
    assert T.limpiar_texto("Tarapac�") == "Tarapacá"
    assert T.limpiar_texto("Biob�o") == "Biobío"


def test_no_toca_el_texto_sano():
    assert T.limpiar_texto("Nicolas") == "Nicolas"
    assert T.limpiar_texto("Banco de Chile") == "Banco de Chile"


def test_el_none_se_preserva():
    assert T.limpiar_texto(None) is None


def test_colapsa_los_espacios_sobrantes():
    assert T.limpiar_texto("Juan   Perez") == "Juan Perez"


def test_cuenta_los_caracteres_sin_corregir():
    assert T.contar_danados("Juan P�rez") == 1
    assert T.contar_danados("Juan Perez") == 0
    assert T.contar_danados(None) == 0


def test_el_diccionario_de_correcciones_no_tiene_claves_repetidas():
    # Una clave repetida haria que la segunda entrada nunca se aplique.
    assert len(T.CORRECCIONES) == len(set(T.CORRECCIONES))


def test_el_diccionario_de_correcciones_cubre_los_tokens_danados():
    # Ningun token danado puede quedar sin corregir.
    for danado, correcto in T.CORRECCIONES.items():
        assert "�" not in correcto, f"{danado!r} -> {correcto!r}"
        assert T.limpiar_texto(danado) == correcto


# ==========================================================================
# RECLASIFICACION
# ==========================================================================

def test_sin_creditos_pasa_a_oportunidad():
    assert T.reclasificar("RIESGO", 0)[0] == "OPORTUNIDAD"


def test_con_creditos_se_conserva_la_clasificacion():
    assert T.reclasificar("REGULAR", 2)[0] == "REGULAR"


def test_sin_productos_no_se_reclasifica():
    # Reemplazar "SIN PRODUCTOS" por "OPORTUNIDAD" perderia el significado
    # del valor original del package.
    clasificacion, motivo = T.reclasificar("SIN PRODUCTOS", 0)
    assert clasificacion == "SIN PRODUCTOS"
    assert "sin productos" in motivo.lower()


def test_clasificar_cliente_riesgo():
    clasificacion, oracle, _ = T.clasificar_cliente(20, 3, 500, True, True)
    assert clasificacion == "RIESGO"
    assert oracle == "RIESGO"


def test_clasificar_cliente_regular():
    clasificacion, oracle, _ = T.clasificar_cliente(80, 0, 500, True, True)
    assert clasificacion == "REGULAR"
    assert oracle == "REGULAR"


def test_clasificar_cliente_bueno():
    clasificacion, oracle, _ = T.clasificar_cliente(100, 0, 0, True, True)
    assert clasificacion == "BUENO"
    assert oracle == "BUENO"


def test_clasificar_cliente_sin_productos():
    clasificacion, oracle, _ = T.clasificar_cliente(0, 0, 0, False, False)
    assert clasificacion == "SIN PRODUCTOS"
    assert oracle == "SIN PRODUCTOS"


def test_clasificar_cliente_sin_creditos_pero_con_inversiones():
    clasificacion, oracle, _ = T.clasificar_cliente(0, 0, 0, False, True)
    assert clasificacion == "OPORTUNIDAD"
    assert oracle == "RIESGO"   # el valor original del package se conserva


# ==========================================================================
# RECALCULO DEL BLOQUE "analisis"
# ==========================================================================

@pytest.fixture
def documento():
    """Un credito con 2 cuotas de 600.000 sobre un principal de 1.000.000."""
    return {
        "creditos": [{
            "nro_solic_credito": 2001,
            "monto_credito": 1000000,
            "cuotas": [
                {"nro_cuota": 1, "valor_cuota": 600000, "monto_pagado": 600000,
                 "saldo_por_pagar": 0, "estado": "PAGADA"},
                {"nro_cuota": 2, "valor_cuota": 600000, "monto_pagado": 0,
                 "saldo_por_pagar": 600000, "estado": "VENCIDA"},
            ],
        }],
        "inversiones": [],
    }


def test_total_creditos_es_la_suma_de_las_cuotas(documento):
    # fn_porcentaje_pagado del package divide por la SUMA DEL VALOR DE LAS
    # CUOTAS, no por la suma de los montos de los creditos. El recalculo del
    # CRUD tiene que usar la misma base o el porcentaje no coincidiria con
    # el del ETL.
    analisis = T.recalcular_analisis(documento)
    assert analisis["total_creditos"] == 1200000


def test_porcentaje_pagado_coincide_con_el_package(documento):
    # fn_porcentaje_pagado: ROUND(SUM(monto_pagado) / SUM(valor_cuota) * 100, 2)
    analisis = T.recalcular_analisis(documento)
    assert analisis["porcentaje_pagado"] == 50.0


def test_conteo_de_cuotas_por_estado(documento):
    analisis = T.recalcular_analisis(documento)
    assert analisis["cuotas"] == {
        "total": 2, "pagadas": 1, "parciales": 0, "vencidas": 1, "pendientes": 0,
    }


def test_saldo_pendiente_es_la_suma_de_los_saldos(documento):
    analisis = T.recalcular_analisis(documento)
    assert analisis["saldo_pendiente"] == 600000


def test_el_analisis_conserva_la_clasificacion_original(documento):
    analisis = T.recalcular_analisis(documento)
    assert analisis["clasificacion"] == "RIESGO"
    assert analisis["clasificacion_oracle"] == "RIESGO"


def test_ahorro_total_suma_las_inversiones(documento):
    documento["inversiones"] = [
        {"monto_total_ahorrado": 100000, "movimientos": []},
        {"monto_total_ahorrado": 50000, "movimientos": []},
    ]
    analisis = T.recalcular_analisis(documento)
    assert analisis["total_ahorrado"] == 150000


def test_documento_sin_creditos_no_divide_por_cero():
    analisis = T.recalcular_analisis({"creditos": [], "inversiones": []})
    assert analisis["porcentaje_pagado"] == 0
    assert analisis["total_creditos"] == 0


# ==========================================================================
# ALERTAS
# ==========================================================================

def test_las_alertas_estan_limitadas_a_diez():
    creditos = [{
        "nro_solic_credito": 2001,
        "cuotas": [
            {"nro_cuota": n, "estado": "VENCIDA"} for n in range(1, 21)
        ],
    }]
    assert len(T.generar_alertas(creditos)) == T.MAXIMO_ALERTAS


# ==========================================================================
# INFORME DEL PROCESO MENSUAL
# ==========================================================================

def test_parsea_el_resumen_sin_separador_de_miles():
    clientes, saldo = T.parsear_resumen_proceso(
        ["Clientes analizados: 130 | saldo total: $45312345"]
    )
    assert clientes == 130
    assert saldo == 45312345


def test_parsea_el_resumen_con_separador_de_miles():
    # Un int() directo sobre el texto reventaba con ValueError.
    clientes, saldo = T.parsear_resumen_proceso(
        ["Clientes analizados: 130 | saldo total: $45,312,345"]
    )
    assert clientes == 130
    assert saldo == 45312345

    clientes, saldo = T.parsear_resumen_proceso(
        ["Clientes analizados: 130 | saldo total: $45.312.345"]
    )
    assert clientes == 130
    assert saldo == 45312345


def test_toma_la_ultima_linea_del_informe():
    lineas = [
        "Proceso mensual KOPERA | 14/11/2026",
        "1 JUAN PEREZ | creditos $100 | pagado $50 | saldo $50 | RIESGO",
        "Clientes analizados: 130 | saldo total: $45312345",
    ]
    clientes, saldo = T.parsear_resumen_proceso(lineas)
    assert clientes == 130
    assert saldo == 45312345


def test_sin_linea_de_resumen_devuelve_ceros():
    assert T.parsear_resumen_proceso(["otra cosa"]) == (0, 0)


# ==========================================================================
# FORMATO DE FECHAS
# ==========================================================================

def test_iso_de_una_fecha():
    from datetime import date, datetime
    assert T._iso(date(2026, 11, 14)) == "2026-11-14"
    assert T._iso(datetime(2026, 11, 14, 10, 30)) == "2026-11-14T10:30:00"
    assert T._iso(None) is None
