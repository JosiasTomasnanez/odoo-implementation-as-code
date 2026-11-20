"""Categorizar productos del punto de venta con IA (ADR 0018, ampliación): pedido, validación,
tandas y errores.

Sin red ni Odoo: la llamada a Gemini se reemplaza por funciones de prueba, y el cliente de
Gemini de comercio_catalogo_ia se carga desde su archivo con el nombre que usa Odoo."""
import importlib.util
import json
import sys
import types
import urllib.error
from pathlib import Path

import pytest

ADDONS = Path(__file__).parents[1] / "addons"


def _cargar(nombre: str, archivo: Path):
    spec = importlib.util.spec_from_file_location(nombre, archivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# odoo.addons.comercio_catalogo_ia.ia.verificar sin instalar Odoo
PAQUETE = "odoo.addons.comercio_catalogo_ia.ia"
for paquete in ("odoo", "odoo.addons", "odoo.addons.comercio_catalogo_ia", PAQUETE):
    sys.modules.setdefault(paquete, types.ModuleType(paquete))
gemini = _cargar(f"{PAQUETE}.verificar", ADDONS / "comercio_catalogo_ia/ia/verificar.py")
sys.modules[PAQUETE].verificar = gemini
ia = _cargar("pos_categorias_ia", ADDONS / "comercio_pos_categorias/ia/categorizar.py")

CATEGORIAS = [{"id": 1, "nombre": "Alimento perro"}, {"id": 2, "nombre": "Alimento gato"},
              {"id": 3, "nombre": "Accesorios mascotas"}]
PRODUCTOS = [{"fila": 10, "nombre": "Croquetas felinas castrados 3 kg", "rubro": "Mascotas / Alimento"},
             {"fila": 11, "nombre": "Pelota de goma con sonido", "rubro": "Mascotas"}]
NOMBRE = {p["fila"]: p["nombre"] for p in PRODUCTOS}


def respuesta(filas: list[dict], tokens=50) -> dict:
    filas = [{"descripcion": NOMBRE.get(f["fila"], "otro"), **f} for f in filas]
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"filas": filas})}]}}],
            "usageMetadata": {"totalTokenCount": tokens}, "modelVersion": "gemini-prueba"}


def test_pedido_solo_lleva_nombres_rubros_y_categorias():
    texto = ia.armar_pedido(PRODUCTOS, CATEGORIAS)
    datos = json.loads(texto.split("Datos:\n", 1)[1])
    assert datos["productos"][0] == {"fila": 10, "nombre": "Croquetas felinas castrados 3 kg",
                                     "rubro": "Mascotas / Alimento"}
    assert [c["categoria_id"] for c in datos["categorias_disponibles"]] == [1, 2, 3]
    datos_texto = texto.split("Datos:\n", 1)[1].lower()
    assert not any(p in datos_texto for p in ("costo", "precio", "cliente", "venta"))


def test_valida_categoria_eco_y_filas_faltantes():
    sugerencias = ia.validar({"filas": [
        {"fila": 10, "descripcion": "Croquetas felinas castrados 3 kg", "categoria_id": 9, "confianza": 0.9,
         "motivo": "gato"},
        {"fila": 77, "descripcion": "otro", "categoria_id": 1, "confianza": 1, "motivo": "no pedida"},
    ]}, PRODUCTOS, CATEGORIAS)
    assert [(s.fila, s.categoria_id) for s in sugerencias] == [(10, None), (11, None)]
    assert "no existe" in sugerencias[0].motivo and "no respondió" in sugerencias[1].motivo


def test_otro_producto_en_la_respuesta_queda_sin_categoria():
    sugerencias = ia.validar({"filas": [
        {"fila": 10, "descripcion": "Pelota de goma con sonido", "categoria_id": 3, "confianza": 0.9,
         "motivo": "x"},
    ]}, PRODUCTOS[:1], CATEGORIAS)
    assert sugerencias[0].categoria_id is None and "otro producto" in sugerencias[0].motivo


def test_ninguna_categoria_es_valida_y_confianza_acotada():
    sugerencias = ia.validar({"filas": [
        {"fila": 10, "descripcion": "CROQUETAS felinas castrados 3kg", "categoria_id": 2, "confianza": 3,
         "motivo": "gato castrado"},
        {"fila": 11, "categoria_id": None, "confianza": 0.4, "motivo": "ninguna"},
    ]}, PRODUCTOS, CATEGORIAS)
    # Mayúsculas y espacios no importan; la confianza se acota a 1
    assert (sugerencias[0].categoria_id, sugerencias[0].confianza) == (2, 1.0)
    assert sugerencias[1].categoria_id is None


def test_tandas_en_paralelo_y_consumo():
    productos = [{"fila": i, "nombre": f"Producto {i}", "rubro": ""} for i in range(120)]
    pedidos = []

    def llamar(texto, clave, modelo, esquema=None):
        assert esquema is ia.ESQUEMA
        filas = json.loads(texto.split("Datos:\n", 1)[1])["productos"]
        pedidos.append(len(filas))
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"filas": [
            {"fila": f["fila"], "descripcion": f["nombre"], "categoria_id": 1, "confianza": 0.9,
             "motivo": "ok"}
            for f in filas]})}]}}], "usageMetadata": {"totalTokenCount": 10}}

    sugerencias, consumo = ia.categorizar(productos, CATEGORIAS, "clave", ["m"], llamar=llamar)
    assert sorted(pedidos) == [20, 50, 50] and consumo.pedidos == 3 and consumo.tokens == 30
    assert [s.fila for s in sugerencias] == list(range(120))  # en el orden de los productos


def test_sin_clave_sin_categorias_o_error_avisa_en_castellano():
    with pytest.raises(gemini.ErrorIA, match="falta la clave"):
        ia.categorizar(PRODUCTOS, CATEGORIAS, "", ["m"])
    with pytest.raises(gemini.ErrorIA, match="no hay categorías"):
        ia.categorizar(PRODUCTOS, [], "clave", ["m"])

    def rechaza(texto, clave, modelo, esquema=None):
        raise urllib.error.HTTPError("https://x", 403, "error", {}, None)

    with pytest.raises(gemini.ErrorIA, match="clave de la IA no es válida"):
        ia.categorizar(PRODUCTOS, CATEGORIAS, "clave", ["m"], llamar=rechaza, esperar=lambda s: None)


def test_respuesta_correcta():
    def llamar(texto, clave, modelo, esquema=None):
        return respuesta([{"fila": 10, "categoria_id": 2, "confianza": 0.95, "motivo": "alimento de gato"},
                          {"fila": 11, "categoria_id": 3, "confianza": 0.85, "motivo": "juguete"}])

    sugerencias, _ = ia.categorizar(PRODUCTOS, CATEGORIAS, "clave", ["m"], llamar=llamar)
    assert [(s.fila, s.categoria_id) for s in sugerencias] == [(10, 2), (11, 3)]
