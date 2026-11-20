"""Cierre Z (comercio_cierre_z/cierre): lectura de la IA y controles de los números, sin Odoo.

Los números imitan un Z de un día de ferretería, inventados.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_cierre_z"))
from cierre.leer import (  # noqa: E402
    desde_ia,
    entero,
    errores,
    fecha_iso,
    importe,
    iva_esperado,
    suma_comprobante,
    tipo_de_imagen,
)

Z_BIEN = {
    "numero_z": 1520,
    "fecha": "2026-11-11",
    "tique_desde": 4501,
    "tique_hasta": 4620,
    "neto_21": 100000.0,
    "iva_21": 21000.37,
    "neto_105": 20000.0,
    "iva_105": 2100.0,
    "neto_27": 0.0,
    "iva_27": 0.0,
    "exento": 0.0,
    "no_gravado": 0.0,
    "total": 143100.37,
}


def test_importe_admite_formatos_argentino_e_ingles():
    assert importe("1.234,56") == 1234.56
    assert importe("1,234.56") == 1234.56
    assert importe("$ 21000,4") == 21000.4
    assert importe(12.344) == 12.34
    assert importe("") is None
    assert importe("abc") is None


def test_entero_y_fecha():
    assert entero("Nº 001520") == 1520
    assert entero(None) is None
    assert fecha_iso("11/11/2026") == "2026-11-11"
    assert fecha_iso("11/11/26") == "2026-11-11"
    assert fecha_iso("2026-11-1") == "2026-11-01"
    assert fecha_iso("31/13/2026") is None


def test_suma_e_iva():
    assert suma_comprobante(Z_BIEN) == 143100.37
    assert iva_esperado(100000, 21) == 21000.0


def test_z_correcto_no_tiene_errores():
    assert errores(Z_BIEN, [60000.0, 83100.37]) == []
    assert errores(Z_BIEN, []) == []  # sin cobros: se puede confirmar y cobrar después


def test_total_que_no_cierra():
    malo = dict(Z_BIEN, total=150000.0)
    assert any("TOTAL del Z" in e for e in errores(malo, []))


def test_iva_mal_leido():
    # un dígito mal leído: 12.000 en lugar de 21.000
    malo = dict(Z_BIEN, iva_21=12000.37, total=134100.37)
    problemas = errores(malo, [])
    assert any("21 %" in e and "no corresponde" in e for e in problemas)


def test_iva_con_centavos_de_redondeo_se_acepta():
    # la registradora redondea ticket por ticket: unos pesos de diferencia en el día se aceptan
    redondeo = dict(Z_BIEN, iva_21=21001.5, total=143101.5)
    assert errores(redondeo, []) == []


def test_cobros_que_no_suman_el_total():
    assert any("medios de pago" in e for e in errores(Z_BIEN, [60000.0, 80000.0]))
    assert any("mayor que cero" in e for e in errores(Z_BIEN, [143100.37, 0.0]))


def test_faltan_datos_y_tiques_al_reves():
    problemas = errores(dict(Z_BIEN, numero_z=None, tique_desde=4620, tique_hasta=4501), [])
    assert "Falta el número del Z." in problemas
    assert any("último tique es menor" in e for e in problemas)
    vacio = errores(
        {"numero_z": 1, "fecha": "2026-11-11", "tique_desde": 1, "tique_hasta": 2, "total": 0}, []
    )
    assert any("no tiene ventas" in e for e in vacio)


def test_desde_ia_limpia_lo_leido():
    leido = desde_ia(
        {
            "numero_z": "1520",
            "fecha": "11/11/2026",
            "punto_de_venta": 8,
            "tique_desde": 4501,
            "tique_hasta": 4620,
            "neto_21": "100.000,00",
            "iva_21": 21000.37,
            "neto_105": None,
            "total": 143100.37,
            "notas_de_credito": 500,
            "medios": [
                {"medio": "efectivo", "importe": 60000},
                {"medio": "cheque", "importe": 1},
                {"medio": "credito", "importe": "83.100,37"},
            ],
            "dudas": ["el último dígito del IVA 10,5 se ve borroso", " "],
        }
    )
    assert leido.valores["numero_z"] == 1520
    assert leido.valores["fecha"] == "2026-11-11"
    assert leido.valores["neto_21"] == 100000.0
    assert leido.valores["neto_105"] is None
    assert leido.medios == [("efectivo", 60000.0), ("credito", 83100.37)]  # «cheque» no es un medio conocido
    assert leido.dudas[0].startswith("el último dígito")
    assert any("notas de crédito" in d for d in leido.dudas)


def test_desde_ia_sin_datos():
    assert desde_ia(None).dudas


def test_tipo_de_imagen():
    assert tipo_de_imagen(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert tipo_de_imagen(b"\x89PNG\r\n") == "image/png"
    assert tipo_de_imagen(b"%PDF-1.7") == "application/pdf"
    assert tipo_de_imagen(b"RIFF1234WEBPVP8 ") == "image/webp"
    assert tipo_de_imagen(b"\x00\x00\x00\x18ftypheic") == "image/heic"
    assert tipo_de_imagen(b"hola") is None
