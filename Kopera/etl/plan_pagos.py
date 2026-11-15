"""
Plan de pagos del proceso mensual de cobranza de KOPERA (Evaluacion Parcial 3).

Este archivo es DATA, no logica: define que cuotas se pagan, cuanto y con que
forma de pago. Se edita a mano sin tocar el codigo del script que lo consume
(poblar_bitacora.py).

--------------------------------------------------------------------------------
SEMANTICA DE "monto_objetivo"
--------------------------------------------------------------------------------
Es el PAGO ACUMULADO que la cuota debe tener DESPUES de aplicar el evento, no el
monto del evento en si. El script calcula solo cuanto falta (delta) para alcanzar
el objetivo y lo omite si ya esta cubierto.

    Cuota de 57.292 con evento "monto_objetivo": 57.292  -> pago completo
    Cuota de 57.292 con evento "monto_objetivo": 25.000  -> pago parcial
    Segundo evento sobre la misma cuota con "monto_objetivo": 57.292
        -> complemento: completa el pago anterior (delta = 32.292)

Gracias a esta semantica el proceso es idempotente: al reejecutarlo no vuelve a
pagar lo ya pagado, solo informa que lo omite.

--------------------------------------------------------------------------------
CRITERIO DE SELECCION DE LAS CUOTAS
--------------------------------------------------------------------------------
Solo cuotas VENCIDAS y sin pago (las mas antiguas de cada credito), para que:

  - la bitacora represente un proceso de cobranza real, no un ajuste artificial;
  - la cartera conserve cuotas vencidas y pendientes, de modo que el bloque
    "analisis" de la coleccion y la clasificacion de riesgo sigan teniendo
    contenido;
  - los clientes paguen una parte de su deuda, no toda.

Se eligieron 10 clientes y 12 creditos: 22 eventos en total, con 15 pagos
completos, 5 parciales y 2 complementos que cierran un pago parcial anterior
(generan historial con monto_pagado_anterior distinto de NULL).
"""

# Forma de pago (codigo de FORMA_PAGO):
#   1 = Efectivo
#   2 = Transferencia Electronica
#   3 = Cheque
FORMAS_PAGO = {
    1: "Efectivo",
    2: "Transferencia Electronica",
    3: "Cheque",
}

# Plan de pagos del lote.
#   nro_solic_credito : credito afectado
#   nro_cuota         : cuota dentro del credito
#   nro_cliente       : cliente dueno (se valida contra la base, es informativo)
#   monto_objetivo    : pago acumulado objetivo despues de este evento
#   cod_forma_pago    : forma de pago aplicada
#   concepto          : descripcion legible para el informe
PLAN_PAGOS = [
    # --- Cliente 5 : credito 2001, cuota de 57.292 ---
    {"nro_solic_credito": 2001, "nro_cuota": 6, "nro_cliente": 5,
     "monto_objetivo": 57292, "cod_forma_pago": 2,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 2001, "nro_cuota": 7, "nro_cliente": 5,
     "monto_objetivo": 25000, "cod_forma_pago": 1,
     "concepto": "Pago parcial de cuota vencida"},

    {"nro_solic_credito": 2001, "nro_cuota": 7, "nro_cliente": 5,
     "monto_objetivo": 57292, "cod_forma_pago": 1,
     "concepto": "Complemento del pago parcial anterior"},

    # --- Cliente 6 : credito 2002, cuota de 18.330 ---
    {"nro_solic_credito": 2002, "nro_cuota": 5, "nro_cliente": 6,
     "monto_objetivo": 18330, "cod_forma_pago": 3,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 2002, "nro_cuota": 6, "nro_cliente": 6,
     "monto_objetivo": 10000, "cod_forma_pago": 2,
     "concepto": "Pago parcial de cuota vencida"},

    # --- Cliente 13 : creditos 2003 (23.625) y 2004 (55.560) ---
    {"nro_solic_credito": 2003, "nro_cuota": 5, "nro_cliente": 13,
     "monto_objetivo": 23625, "cod_forma_pago": 1,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 2004, "nro_cuota": 5, "nro_cliente": 13,
     "monto_objetivo": 30000, "cod_forma_pago": 2,
     "concepto": "Pago parcial de cuota vencida"},

    # --- Cliente 26 : credito 2006, cuota de 32.710 ---
    {"nro_solic_credito": 2006, "nro_cuota": 5, "nro_cliente": 26,
     "monto_objetivo": 32710, "cod_forma_pago": 3,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 2006, "nro_cuota": 6, "nro_cliente": 26,
     "monto_objetivo": 15000, "cod_forma_pago": 1,
     "concepto": "Pago parcial de cuota vencida"},

    # --- Cliente 29 : credito 2008, cuota de 129.167 ---
    {"nro_solic_credito": 2008, "nro_cuota": 5, "nro_cliente": 29,
     "monto_objetivo": 129167, "cod_forma_pago": 2,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 2008, "nro_cuota": 6, "nro_cliente": 29,
     "monto_objetivo": 60000, "cod_forma_pago": 3,
     "concepto": "Pago parcial de cuota vencida"},

    # --- Cliente 38 : credito 2011, cuota de 121.667 ---
    {"nro_solic_credito": 2011, "nro_cuota": 4, "nro_cliente": 38,
     "monto_objetivo": 121667, "cod_forma_pago": 1,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 2011, "nro_cuota": 5, "nro_cliente": 38,
     "monto_objetivo": 50000, "cod_forma_pago": 2,
     "concepto": "Pago parcial de cuota vencida"},

    # --- Cliente 39 : credito 2012, cuota de 103.334 ---
    {"nro_solic_credito": 2012, "nro_cuota": 5, "nro_cliente": 39,
     "monto_objetivo": 103334, "cod_forma_pago": 3,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 2012, "nro_cuota": 6, "nro_cliente": 39,
     "monto_objetivo": 45000, "cod_forma_pago": 1,
     "concepto": "Pago parcial de cuota vencida"},

    # --- Cliente 67 : creditos 3001 (175.000) y 3004 (105.555) ---
    {"nro_solic_credito": 3001, "nro_cuota": 5, "nro_cliente": 67,
     "monto_objetivo": 175000, "cod_forma_pago": 2,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 3004, "nro_cuota": 5, "nro_cliente": 67,
     "monto_objetivo": 50000, "cod_forma_pago": 1,
     "concepto": "Pago parcial de cuota vencida"},

    {"nro_solic_credito": 3004, "nro_cuota": 5, "nro_cliente": 67,
     "monto_objetivo": 105555, "cod_forma_pago": 1,
     "concepto": "Complemento del pago parcial anterior"},

    # --- Cliente 85 : credito 3009, cuota de 408.333 ---
    {"nro_solic_credito": 3009, "nro_cuota": 7, "nro_cliente": 85,
     "monto_objetivo": 408333, "cod_forma_pago": 3,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 3009, "nro_cuota": 8, "nro_cliente": 85,
     "monto_objetivo": 200000, "cod_forma_pago": 2,
     "concepto": "Pago parcial de cuota vencida"},

    # --- Cliente 90 : credito 3010, cuota de 333.333 ---
    {"nro_solic_credito": 3010, "nro_cuota": 8, "nro_cliente": 90,
     "monto_objetivo": 333333, "cod_forma_pago": 1,
     "concepto": "Pago completo de cuota vencida"},

    {"nro_solic_credito": 3010, "nro_cuota": 9, "nro_cliente": 90,
     "monto_objetivo": 150000, "cod_forma_pago": 3,
     "concepto": "Pago parcial de cuota vencida"},
]
