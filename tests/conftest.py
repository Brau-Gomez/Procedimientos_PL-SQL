"""
Configuracion de pytest.

Los modulos de la EVAL 3 viven en Kopera/etl/ y se importan entre ellos
por nombre plano (from config import ...), asi que esa carpeta tiene que estar
en el path para que los tests puedan importarlos.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ETL = RAIZ / "Kopera" / "etl"

if str(ETL) not in sys.path:
    sys.path.insert(0, str(ETL))
