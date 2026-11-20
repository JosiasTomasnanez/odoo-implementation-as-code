"""Listas en PDF (con texto, sin IA) y en foto o PDF escaneado (con IA, sin red)."""
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).parents[1]
sys.path.insert(0, str(RAIZ / "addons" / "comercio_catalogo"))
sys.path.insert(0, str(RAIZ / "addons" / "comercio_catalogo_ia"))
from catalogo.convertir import (  # noqa: E402
    convertir,
    encontrar_encabezado,
    filas_con_titulos,
    leer_tabla,
    sugerir_mapeo,
    tabla_a_csv,
)
from catalogo.pdf import tabla_desde_pdf  # noqa: E402
from catalogo.plan import _numero  # noqa: E402
from ia import leer  # noqa: E402

DATOS = RAIZ / "tests" / "datos"


def test_pdf_con_texto_se_lee_como_un_excel():
    tabla = tabla_desde_pdf((DATOS / "lista_ficticia.pdf").read_bytes())
    fila = encontrar_encabezado(tabla, 60)
    assert tabla[fila - 1] == ["Código", "Descripción", "Precio s/IVA", "Min."]
    assert tabla[fila] == ["P-001", "ALIMENTO PERRO ADULTO X 15 KG", "$ 30.250,50", "1"]
    # Pasa por CSV (como se guarda) y sigue el camino de siempre: títulos, columnas, costo
    tabla = leer_tabla(tabla_a_csv(tabla), "lista.pdf.csv")
    mapeo = {"proveedor": "X", "columnas": sugerir_mapeo(tabla[fila - 1]), "valores_fijos": {}}
    filas = convertir(mapeo, filas_con_titulos(tabla, fila))
    assert len(filas) == 60
    assert filas[0]["codigo_proveedor"] == "P-001" and _numero(filas[0]["costo"]) == 30250.5
    assert {f["descripcion_proveedor"] for f in filas[:3]} >= {"ARENA SANITARIA X 4 KG"}


def test_pdf_sin_texto_queda_para_la_ia():
    # Un PDF con solo una imagen (escaneado): no hay letras
    pdf = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
           b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
           b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
    assert tabla_desde_pdf(pdf) is None


def respuesta(filas):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"filas": filas})}]}}],
            "usageMetadata": {"totalTokenCount": 500}, "modelVersion": "gemini-prueba"}


def test_foto_la_transcribe_la_ia():
    pedidos = []

    def llamar(partes, clave, modelo, esquema=None):
        pedidos.append(partes)
        return respuesta([["Código", "Descripción", "Precio"], ["P-001", "ALIMENTO X 15 KG", "$ 30.250,50"]])

    tabla, consumo, paginas = leer.leer(b"foto", "lista.jpg", "clave", ["m"], llamar)
    assert tabla[1] == ["P-001", "ALIMENTO X 15 KG", "$ 30.250,50"] and paginas == 1
    assert pedidos[0][0]["inline_data"]["mime_type"] == "image/jpeg"  # se manda la foto, nada más
    assert consumo.tokens == 500


def test_paginas_unidas_sin_titulos_repetidos():
    titulos = ["Código", "Descripción", "Precio"]
    tabla = leer.unir([[["Lista Nº 7"], titulos, ["A", "uno", "10"]],
                       [titulos, ["B", "dos", "20", "extra"], []]])
    assert tabla == [["Lista Nº 7", "", "", ""], titulos + [""], ["A", "uno", "10", ""],
                     ["B", "dos", "20", "extra"]]


def test_sin_clave_o_demasiadas_paginas():
    with pytest.raises(leer.ErrorIA, match="GEMINI_API_KEY"):
        leer.leer(b"x", "lista.png", "", ["m"])
    with pytest.raises(leer.ErrorIA, match="no es una foto ni un PDF"):
        leer.leer(b"x", "lista.docx", "clave", ["m"])
