"""Tope de pedidos por minuto a Gemini (plan gratis, 06/11)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addons" / "comercio_catalogo_ia"))

from ia.verificar import Ritmo  # noqa: E402


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def esperar(self, segundos):
        self.t += segundos


def test_los_primeros_salen_enseguida_y_el_siguiente_espera_el_minuto():
    reloj = Reloj()
    ritmo = Ritmo(3, reloj=reloj, esperar=reloj.esperar)
    for _ in range(3):
        ritmo.turno()
    assert reloj.t == 0
    ritmo.turno()
    assert 60 <= reloj.t < 61


def test_cero_es_sin_tope():
    reloj = Reloj()
    ritmo = Ritmo(0, reloj=reloj, esperar=reloj.esperar)
    for _ in range(100):
        ritmo.turno()
    assert reloj.t == 0
