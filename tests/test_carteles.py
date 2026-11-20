"""Cuentas de los carteles de precio (comercio_carteles/medidas.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_carteles"))
from medidas import letra_que_entra, pesos, redondear_arriba, ubicaciones  # noqa: E402


def test_redondeo_siempre_hacia_arriba():
    assert redondear_arriba(15028.2, 100) == 15100
    assert redondear_arriba(15000, 100) == 15000
    assert redondear_arriba(5227.2, 10) == 5230
    assert redondear_arriba(1234.567, 1) == 1234.57  # sin redondear: el precio tal cual


def test_formato_del_precio():
    assert pesos(15100) == "$ 15.100"
    assert pesos(1234.5) == "$ 1.234,50"
    assert pesos(990) == "$ 990"


def test_ubicaciones_en_a4():
    assert len(ubicaciones("8")) == 8 and len(ubicaciones("1")) == 1
    ultimo = ubicaciones("4")[-1]
    # dentro del margen de 5 mm
    assert ultimo["x"] + ultimo["ancho"] <= 205.01 and ultimo["y"] + ultimo["alto"] <= 292.01


def test_letras_lo_mas_grandes_que_entran():
    # Una palabra corta en una hoja entera: el tope
    assert letra_que_entra("LEÑA", 160, 100, 72) == 72
    # El precio de una hoja entera tiene que entrar a lo ancho (antes se cortaba «$ 7.50»)
    pt = letra_que_entra("$ 7.500", 160, 80, 200, interlineado=1.0, una_linea=True)
    assert 7 * pt * 0.3528 * 0.62 <= 160
    # Un nombre largo en un cartel chico: más chico, pero legible
    assert 8 < letra_que_entra("ABRAZADERA CIERRE RAPIDO 10-20 MM F12 PERFECTO", 80, 27, 24) < 24
