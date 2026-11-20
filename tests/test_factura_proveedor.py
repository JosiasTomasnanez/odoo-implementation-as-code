"""Lector de facturas de proveedor (comercio_factura_proveedor/factura): sin Odoo.

La tabla imita la de una factura real (FC, 13/10) con datos inventados: el código va al
principio de la descripción o en el renglón de abajo junto al despacho, la bonificación a
veces en el renglón de abajo, y la descripción larga se corta en dos renglones.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_factura_proveedor"))
from factura.cuit import cuit_valido  # noqa: E402
from factura.leer import (  # noqa: E402
    Factura,
    Linea,
    Totales,
    clave,
    datos_generales,
    desde_ia,
    desde_tabla,
    numero,
    percepciones_del_texto,
    totales_desde_renglones,
)

TITULOS = ["CANTIDAD", "ARTÍCULO", "T.IVA", "PRECIO", "% BONIF.", "P.BONIF.", "IMPORTE"]
TABLA = [
    ["FACTURA", "ORIGINAL"],
    ["A", "Nº A 0009-00012345"],
    ["Código: 1", "Fecha: 13/10/2026"],
    ["CUIT: 30-71234567-1"],
    TITULOS,
    ["", "COD BAR..", "DESPACHO", "", "", "", ""],
    ["2,00", "MORSA GARDEX - 60mm", "21,00", "1000,00", "", "950,00", "1900,00"],
    ["", "01710", "13017IC05004352N", "", "5", "", ""],
    ["4,00", "06687 - REGULADOR GAS - ECONOMICO", "21,00", "100,00", "5", "95,00", "380,00"],
    ["1,00", "59623 - TARUGO NYLON - STD bolsa", "8x1000 21,00", "200,00", "5", "190,00", "190,00"],
    ["5,00", "40482 - REPUESTO GIBER - KIT 1", "21,00", "10,00", "5", "9,50", "47,50"],
    ["", ".5 LTS", "", "", "", "", ""],
    ["TRANSFERENCIA - ECHEQ 30-60 10%: 1.005.895,49", "", "", "", "", "", ""],
    ["Subtotal", "Flete 2,50%", "Neto Gravado", "", "", "", "TOTAL"],
    ["2.517,50", "", "", "", "", "", ""],
    ["FACTURA", "ORIGINAL"],  # segunda página: los títulos otra vez
    TITULOS,
    ["20,00", "ESCOBA GARDEX - 22 D", "21,00", "10,00", "", "9,50", "190,00"],
    ["", "03599", "25042IC050254478D", "", "5", "", ""],
]


def test_lee_los_articulos_de_todas_las_paginas():
    lineas = desde_tabla(TABLA)
    assert [li.cantidad for li in lineas] == [2, 4, 1, 5, 20]
    assert sum(li.importe for li in lineas) == pytest.approx(2707.5)


def test_codigo_al_principio_o_en_el_renglon_de_abajo():
    morsa, regulador, tarugo, repuesto, escoba = desde_tabla(TABLA)
    assert morsa.codigos[0] == "01710" and morsa.descripcion == "MORSA GARDEX - 60mm"
    assert regulador.codigos == ["06687"] and regulador.descripcion == "REGULADOR GAS - ECONOMICO"
    assert escoba.codigos[0] == "03599"


def test_bonificacion_en_el_renglon_de_abajo_y_descripcion_cortada():
    morsa, _r, tarugo, repuesto, _e = desde_tabla(TABLA)
    assert morsa.bonificacion == 5 and morsa.iva == 21
    assert tarugo.descripcion == "TARUGO NYLON - STD bolsa 8x1000" and tarugo.iva == 21
    assert repuesto.descripcion == "REPUESTO GIBER - KIT 1 .5 LTS"


def test_leyenda_de_pago_no_se_pega_al_articulo():
    assert "TRANSFERENCIA" not in desde_tabla(TABLA)[3].descripcion


def test_aviso_si_cantidad_por_precio_no_da_el_importe():
    tabla = [TITULOS, ["2,00", "TUERCA", "21,00", "100,00", "", "", "500,00"]]
    assert desde_tabla(tabla)[0].avisos


def test_datos_generales():
    factura = Factura(lineas=[])
    datos_generales(
        "\n".join(" ".join(f) for f in TABLA[:4]) + "\nCliente CUIT: 20-12345678-6\n"
        "Vto.: 27/11/2026\nCAE: 86417440114362 - Vto.:23/10/2026",
        factura,
    )
    assert factura.numero == "0009-00012345" and factura.letra == "A" and factura.codigo_tipo == "1"
    assert factura.fecha == "2026-10-13" and factura.vencimiento == "2026-11-27"
    assert factura.cae == "86417440114362"
    assert factura.cuits[0] == "30712345671"
    assert factura.cuit_proveedor({"30712345671"}) == "20123456786"


def test_respuesta_de_la_ia():
    factura = desde_ia(
        {
            "cuits": ["30-71234567-1"],
            "letra": "A",
            "codigo_comprobante": "01",
            "numero": "0003-00001234",
            "fecha": "13/10/2026",
            "vencimiento": "",
            "articulos": [
                {
                    "cantidad": "6,00",
                    "codigo": "",
                    "descripcion": "10283 - TORNILLO FIX - 5 X 50",
                    "precio_unitario": "1000,00",
                    "bonificacion": "5",
                    "importe": "5700,00",
                    "iva": "21,00",
                },
                {"cantidad": "", "descripcion": "Subtotal"},  # sin cantidad: no es un artículo
            ],
        }
    )
    assert len(factura.lineas) == 1 and factura.leida_con_ia
    linea = factura.lineas[0]
    assert linea.codigos == ["10283"] and linea.descripcion == "TORNILLO FIX - 5 X 50" and not linea.avisos
    assert factura.codigo_tipo == "1" and factura.numero == "0003-00001234" and factura.vencimiento is None


@pytest.mark.parametrize(
    ("texto", "valor"),
    [("1.234,56", 1234.56), ("12,50", 12.5), ("$ 35", 35), ("5%", 5), ("abc", None), ("", None)],
)
def test_numeros(texto, valor):
    assert numero(texto) == valor


def test_cuit():
    assert cuit_valido("30-71234567-1") and cuit_valido("20123456786")
    assert not cuit_valido("30712345672") and not cuit_valido("123")


def test_clave_de_descripcion():
    assert clave("TORNILLO FIX - 5  X  50") == clave("Tornillo fix 5 x 50")


# ------------------------------------------------------------------ el pie de la factura
# Como el de FC (posiciones reales, importes inventados): los títulos en un renglón y cada importe
# debajo de su título, en renglones desparejos; «IVA IIBB» y «Muni.» son subtítulos de Percepciones
PIE = [
    [("4,00", 43, 60), ("TORNILLO FIX - 4", 68, 135), ("8113,96", 554, 584)],  # último artículo
    [("TRANSFERENCIA - ECHEQ 30-60 10%: 905,40", 22, 246)],
    [("Subtotal", 40, 69), ("Flete 2,50%", 144, 190), ("Neto Gravado", 208, 257), ("Exento", 283, 308),
     ("IVA", 348, 361), ("Percepciones", 416, 465), ("TOTAL", 521, 548)],
    [("IVA", 413, 424), ("IIBB", 431, 444), ("35,00", 454, 494)],
    [("1.000,00", 35, 75), ("25,00", 151, 187)],
    [("1.025,00", 220, 260), ("215,25", 338, 378), ("1.275,25", 510, 568)],
    [("Muni.", 431, 448)],
    [("Perc.IIBB: CORDOBA 35,00", 23, 124)],
]


def test_pie_con_titulos_arriba_y_los_importes_debajo():
    totales = totales_desde_renglones(PIE)
    assert (totales.subtotal, totales.flete, totales.neto_gravado, totales.iva, totales.percepciones,
            totales.total) == (1000, 25, 1025, 215.25, 35, 1275.25)
    assert totales.flete_texto == "flete 2,50%" and totales.exento is None


def test_pie_repetido_en_cada_pagina_vale_el_ultimo():
    primera = [PIE[2], [("810,00", 35, 75)], PIE[6]]  # la primera página solo trae el subtotal parcial
    assert totales_desde_renglones(primera + PIE).subtotal == 1000


def test_pie_con_titulo_e_importe_en_el_mismo_renglon():
    renglones = [
        [("Subtotal:", 300, 340), ("$ 2.000,00", 450, 500)],
        [("IVA 21%: 420,00", 300, 500)],
        [("IVA 10,5%: 52,50", 300, 500)],  # dos alícuotas: se suman
        [("Perc. IIBB Bs. As. 3,00%: 30,00", 300, 500)],  # detalle: va aparte, no al pie
        [("TOTAL $ 2.502,50", 300, 500)],
    ]
    totales = totales_desde_renglones(renglones)
    assert (totales.subtotal, totales.iva, totales.percepciones, totales.total) == (2000, 472.5, None, 2502.5)


def test_detalle_de_percepciones():
    texto = "Perc.IIBB: CORDOBA 35.765,17\nPercepciones IVA IIBB 35.765,17\nPerc. IVA 3,00%: 120,50\n" \
            "Perc.IIBB: CORDOBA 35.765,17"
    detalle = percepciones_del_texto(texto)
    assert [(p.tipo, p.jurisdiccion, p.importe) for p in detalle] == [
        ("iibb", "cordoba", 35765.17), ("iva", None, 120.5)]


def test_iva_del_flete():
    lineas = [Linea("A", iva=21.0), Linea("B", iva=10.5), Linea("C", iva=21.0)]
    assert Totales(subtotal=1000, flete=25, neto_gravado=1025, iva=215.25).iva_del_flete(lineas, "A") == 21
    # El neto gravado no incluye el flete: va sin IVA
    assert Totales(subtotal=1000, flete=25, neto_gravado=1000).iva_del_flete(lineas, "A") == 0
    assert Totales(flete=25).iva_del_flete(lineas, "A") == 21  # la más común de los artículos
    assert Totales(flete=25).iva_del_flete(lineas, "B") == 0  # factura B: no discrimina IVA


def test_pie_leido_con_ia():
    factura = desde_ia({"articulos": [], "flete": "25,00", "total": "1.275,25",
                        "percepciones": [{"texto": "Perc. IIBB Córdoba", "importe": "35,00"}]})
    totales = factura.totales
    assert (totales.flete, totales.total, totales.percepciones) == (25, 1275.25, 35)
    assert [(p.tipo, p.jurisdiccion) for p in totales.detalle_percepciones] == [("iibb", "cordoba")]
