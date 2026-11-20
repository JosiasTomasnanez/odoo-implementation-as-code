"""Cálculo del precio de venta (addons/comercio_precios/calculo.py), sin Odoo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_precios"))
from calculo import precio_de_lista, precio_final, redondear_arriba  # noqa: E402


def test_redondeo_siempre_para_arriba():
    assert redondear_arriba(45_991, 10) == 46_000
    assert redondear_arriba(46_000, 10) == 46_000
    assert redondear_arriba(45_001, 100) == 45_100
    assert redondear_arriba(123.456, 0) == 123.46


def test_precio_final_costo_margen_iva():
    # 25.000 + 25 % = 31.250; + IVA 21 % = 37.812,50 → redondeo $10 = 37.820
    assert precio_final(25_000, 25, 21, 10) == 37_820


def test_precio_de_lista_con_y_sin_iva_incluido():
    assert precio_de_lista(37_820, 21, True) == 37_820
    assert precio_de_lista(12_100, 21, False) == 10_000


def test_redondeo_por_tramos():
    # 20/11: hasta $ 1.000 a $ 10, desde $ 1.000 a $ 100, desde $ 10.000 a $ 500 (siempre hacia arriba)
    from calculo import leer_tramos, precio_final, texto_redondeo

    tramos = leer_tramos("10; 1000:100; 10000:500")
    assert tramos == [(0, 10), (1000, 100), (10000, 500)]
    assert precio_final(12, 0, 0, tramos) == 20            # un soporte de $ 12 no pasa a $ 100
    assert precio_final(146.73, 0, 0, tramos) == 150
    assert precio_final(1055, 0, 0, tramos) == 1100
    assert precio_final(15028.2, 0, 0, tramos) == 15500
    assert precio_final(15000, 0, 0, tramos) == 15000      # ya redondo: no cambia
    assert precio_final(1055, 0, 0, 100) == 1100           # el redondeo único sigue igual
    assert texto_redondeo(tramos) == "$ 10 / desde $ 1000: $ 100 / desde $ 10000: $ 500"
    try:
        leer_tramos("10; mil:100")
        raise AssertionError("aceptó un tramo mal escrito")
    except ValueError:
        pass
