"""Motor de similitud (integrations/catalogo/similitud.py), portado de odoo-product-matcher."""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "addons" / "comercio_catalogo"))
from catalogo.plan import NUEVO, POSIBLE_DUPLICADO, VINCULAR, Foto, planificar  # noqa: E402
from catalogo.similitud import (  # noqa: E402
    Buscador,
    Cantidad,
    cantidades,
    normalizar_texto,
    palabras,
    similitud,
)


@pytest.mark.parametrize("texto,esperado", [
    ("Alimento Adulto 20 Kg.", "alimento adulto 20kg"),
    ("ALIMENTO  adulto 20kgs", "alimento adulto 20kg"),
    ("Aceite 1,5 Lts", "aceite 1.5l"),
    ("Café Molido 500 grs", "cafe molido 500g"),
    ("Shampoo (neutro) - 250cc", "shampoo neutro 250ml"),
])
def test_normalizar_texto(texto, esperado):
    assert normalizar_texto(texto) == esperado


def test_palabras_sin_palabras_vacias():
    assert palabras("Alimento para Perro x 20 Kg") == ["alimento", "perro", "20kg"]


def test_cantidades_en_unidad_base():
    assert cantidades("Bolsa 0,5 kg") == {Cantidad("masa", Decimal("500"))}
    assert cantidades("Bolsa 500 g") == {Cantidad("masa", Decimal("500"))}
    assert cantidades("Bidón 1.5 L") == {Cantidad("volumen", Decimal("1500"))}


def test_nombres_parecidos_puntuan_alto():
    assert similitud("Alimento Adulto 20 Kg", "Alimento Perro Adulto 20 Kg") >= 0.85


def test_otra_cantidad_se_penaliza():
    assert similitud("Alimento Perro Adulto 20 Kg", "Alimento Perro Adulto 20 Kg") == 1.0
    assert similitud("Alimento Perro Adulto 20 Kg", "Alimento Perro Adulto 3 Kg") < 0.6


def test_unidades_equivalentes_no_chocan():
    assert similitud("Shampoo Neutro 0,5 lt", "Shampoo Neutro 500 ml") > 0.6


def test_tolera_errores_y_acentos():
    assert similitud("Colar antipulgas perro grande", "Collar Antipulgas Perro Grande") > 0.85


def test_abreviaturas():
    assert similitud("Alim. Cachorro 15 Kg", "Alimento Perro Cachorro 15 Kg") >= 0.8
    assert similitud("Comedero Acero Inox 1 Lt", "Comedero Acero Inoxidable 1 L") >= 0.85


def test_buscador_candidatos_y_ambiguedad():
    b = Buscador()
    b.agregar(1, "Alimento Perro Adulto 20 Kg")
    b.agregar(2, "Alimento Perro Adulto 20 Kg")
    b.agregar(3, "Rueda de bicicleta rodado 26")
    candidatos = b.candidatos("alim perro adulto 20kg")
    assert {c.id for c in candidatos} == {1, 2} and b.es_ambiguo(candidatos)
    assert b.candidatos("Tornillo autoperforante") == []
    assert [c.id for c in b.candidatos("alimento perro adulto 20 kg", excluir={1})] == [2]


def foto(productos=(), prov=()):
    return Foto(list(productos), list(prov), {"Prov A", "Prov B"}, {"Todos"}, hoy="2026-10-08")


def fila(**v):
    base = {"proveedor": "Prov B", "codigo_proveedor": "B1", "descripcion_proveedor": "", "unidad": "u",
            "costo": "100"}
    return {**base, **v}


PRODUCTO = {"id": 7, "barcode": False, "default_code": "7", "name": "Alimento Perro Adulto 20 Kg"}


def test_parecido_sin_codigo_en_comun_es_posible_duplicado():
    a = planificar([fila(descripcion_proveedor="ALIM PERRO ADULTO X 20KG")], foto([PRODUCTO]))[0]
    assert a.tipo == POSIBLE_DUPLICADO and a.candidatos[0].id == 7


def test_es_nuevo_confirmado_o_es_el_mismo_confirmado():
    nuevo = fila(descripcion_proveedor="ALIM PERRO ADULTO X 20KG", nuevo="si")
    assert planificar([nuevo], foto([PRODUCTO]))[0].tipo == NUEVO
    mismo = fila(descripcion_proveedor="ALIM PERRO ADULTO X 20KG", vincular_a="7")
    assert planificar([mismo], foto([PRODUCTO]))[0].tipo == VINCULAR


def test_otra_cantidad_no_es_duplicado():
    a = planificar([fila(descripcion_proveedor="Alimento Perro Adulto 3 Kg")], foto([PRODUCTO]))[0]
    assert a.tipo == NUEVO


def test_dos_proveedores_con_el_mismo_producto_nuevo_en_la_misma_carga():
    primera = fila(proveedor="Prov A", codigo_proveedor="A1", descripcion_proveedor="Collar antipulgas gato")
    acciones = planificar([primera, fila(descripcion_proveedor="COLLAR ANTIPULGAS P/GATO")], foto())
    assert [a.tipo for a in acciones] == [NUEVO, POSIBLE_DUPLICADO]


def test_un_proveedor_no_es_candidato_de_si_mismo_si_el_producto_viene_en_la_lista():
    prov = [{"id": 1, "partner": "Prov B", "tmpl": 7, "product_code": "B0", "product_name": "Alim perro 20kg",
             "price": 1.0, "min_qty": 0.0, "delay": 0, "date_start": None}]
    # El producto 7 viene en la misma planilla con su código B0: la otra fila parecida es nueva
    filas = [fila(codigo_proveedor="B0", descripcion_proveedor="Alim perro 20kg"),
             fila(codigo_proveedor="B9", descripcion_proveedor="ALIM PERRO ADULTO X 20KG")]
    acciones = planificar(filas, foto([PRODUCTO], prov))
    assert acciones[1].tipo == NUEVO
