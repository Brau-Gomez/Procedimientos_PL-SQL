"""
Utilidades de formato compartidas por las vistas.

Todo lo que sea "como se muestra un dato" vive aca, no en las vistas: montos,
fechas ISO del ETL y etiquetas de estado. Asi un cambio de formato se hace en
un solo lugar.
"""

from datetime import datetime

# --------------------------------------------------------------------------
# Montos
# --------------------------------------------------------------------------

def clp(valor) -> str:
    """
    Formatea un numero como peso chileno: 52844678 -> $52.844.678.

    Los montos del ETL son enteros (no floats): se evita cualquier redondeo
    raro usando int(round()).
    """
    if valor is None:
        return "—"
    try:
        return f"${int(round(float(valor))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


def numero(valor) -> str:
    """Numero con separador de miles, sin simbolo de moneda."""
    if valor is None:
        return "—"
    try:
        return f"{int(round(float(valor))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


def porcentaje(valor, decimales=2) -> str:
    """Formatea un porcentaje que ya viene expresado en base 100 (14.58 -> 14,58%)."""
    if valor is None:
        return "—"
    try:
        return f"{float(valor):.{decimales}f}%".replace(".", ",")
    except (TypeError, ValueError):
        return str(valor)


def tasa(valor) -> str:
    """
    Numero decimal sin ceros de relleno (0.5 -> 0,5).

    Se usa para la tasa de interes, que en el documento viene como fraccion
    (0.5, 0.25) y no como porcentaje; agregarle '%' seria enganoso.
    """
    if valor is None:
        return "—"
    try:
        return f"{float(valor):g}".replace(".", ",")
    except (TypeError, ValueError):
        return str(valor)


# --------------------------------------------------------------------------
# Fechas
# --------------------------------------------------------------------------

def fecha(valor) -> str:
    """
    Convierte a dd/mm/aaaa el string ISO que guarda el ETL.

    Ojo: transformacion.py guarda las fechas con _iso(), o sea como TEXTO
    ("2026-11-14T00:00:00"), no como BSON date. Por eso hay que parsearlas
    aca en vez de esperar un datetime desde PyMongo.
    """
    dt = _parsear(valor)
    return dt.strftime("%d/%m/%Y") if dt else (str(valor) if valor else "—")


def fecha_hora(valor) -> str:
    """Igual que fecha() pero incluye la hora."""
    dt = _parsear(valor)
    if not dt:
        return str(valor) if valor else "—"
    return dt.strftime("%d/%m/%Y %H:%M")


def _parsear(valor):
    """Intenta convertir un string ISO a datetime. Devuelve None si no puede."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------

def texto(valor, vacio="No informado") -> str:
    """
    Devuelve el texto o un marcador cuando viene nulo o vacio.

    Es necesario porque en los datos reales `contacto.correo` y
    `contacto.fono_contacto` vienen en null para la mayoria de los clientes.
    """
    if valor is None:
        return vacio
    texto_limpio = str(valor).strip()
    return texto_limpio if texto_limpio else vacio


# --------------------------------------------------------------------------
# Etiquetas de estado
# --------------------------------------------------------------------------

# Estados posibles de una cuota (enum del validador $jsonSchema).
SEMAFORO_CUOTA = {
    "PAGADA": "🟢",
    "PARCIAL": "🟡",
    "VENCIDA": "🔴",
    "PENDIENTE": "⚪",
}

# Clasificaciones del bloque analisis.
SEMAFORO_CLASIFICACION = {
    "RIESGO": "🔴",
    "REGULAR": "🟠",
    "BUENO": "🟢",
    "OPORTUNIDAD": "🔵",
    "SIN PRODUCTOS": "⚪",
}


def estado_cuota(estado) -> str:
    """Etiqueta con semaforo de una cuota: PAGADA -> 🟢 PAGADA."""
    if not estado:
        return "—"
    return f"{SEMAFORO_CUOTA.get(estado, '⚪')} {estado}"


def clasificacion(valor) -> str:
    """Etiqueta con semaforo de la clasificacion financiera."""
    if not valor:
        return "—"
    return f"{SEMAFORO_CLASIFICACION.get(valor, '⚪')} {valor}"


def tipo_movimiento(tipo) -> str:
    """Movimiento de inversion con signo visible: ABONO / RESCATE."""
    if tipo == "ABONO":
        return "➕ ABONO"
    if tipo == "RESCATE":
        return "➖ RESCATE"
    return texto(tipo, "—")


# --------------------------------------------------------------------------
# Semáforos para las tablas de la ficha
# --------------------------------------------------------------------------
# Estas funciones NO devuelven HTML: devuelven (texto, tono) para que ui.badge
# arme la insignia. Asi el formato no depende del sistema visual.

TONO_ESTADO_CUOTA = {
    "PAGADA": "verde",
    "PARCIAL": "amarillo",
    "VENCIDA": "rojo",
    "PENDIENTE": "gris",
}

TONO_MOVIMIENTO = {"ABONO": "verde", "RESCATE": "naranja"}


def tono_estado_cuota(estado) -> str:
    """Tono del semaforo segun el estado de la cuota."""
    return TONO_ESTADO_CUOTA.get(estado, "gris")


def badge_atraso(dias, pagada: bool = False) -> tuple[str, str]:
    """
    Semaforo de atraso de una cuota.

    Escala (la misma en todas las pantallas):
        pagada          -> verde    "Pagada"
        sin atraso      -> verde    "Al día"
        1 a 30 dias     -> amarillo
        31 a 60 dias    -> naranja
        mas de 60 dias  -> rojo

    Se devuelve (texto, tono) y no HTML para mantener el formato desacoplado
    de la capa visual.
    """
    if pagada:
        return "Pagada", "verde"

    try:
        d = int(dias or 0)
    except (TypeError, ValueError):
        d = 0

    if d <= 0:
        return "Al día", "verde"
    if d <= 30:
        return f"{d} días", "amarillo"
    if d <= 60:
        return f"{d} días", "naranja"
    return f"{d} días", "rojo"


def badge_movimiento(tipo) -> tuple[str, str]:
    """Tono del semaforo de un movimiento de inversion."""
    return (tipo or "—"), TONO_MOVIMIENTO.get(tipo, "gris")
