"""Categorizar productos del punto de venta con IA (Gemini).

Python puro, sin Odoo: arma el pedido, llama a la API y valida la respuesta. La IA elige,
entre las categorías del punto de venta que YA existen, la que mejor le corresponde a cada
producto (o ninguna). Es solo una **sugerencia**: una persona la revisa y la aplica.

Qué se manda a Google (ADR 0018): el nombre de cada producto, su rubro y los nombres de las
categorías del punto de venta. Nada de costos, precios, clientes ni ventas.

El cliente de Gemini (reintentos, modelo de respaldo, errores en castellano) es el de
`comercio_catalogo_ia`: no se duplica.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from odoo.addons.comercio_catalogo_ia.ia import verificar as gemini

TANDA = 50  # productos por pedido: elegir una categoría es corto
EN_PARALELO = 10
MAXIMO_POR_VEZ = 500  # por clic: 10 tandas de 50 en paralelo tardan lo que una

INSTRUCCIONES = """Sos un asistente de un comercio argentino (alimento y accesorios para mascotas,
ferretería, veterinaria, forrajería, vivero) que ordena sus productos en las categorías de los
botones del punto de venta, para que el cajero los encuentre rápido.

Para cada producto, elegí UNA categoría de la lista de categorías disponibles: la que mejor le
corresponde según su nombre (y su rubro, que es una pista). Usá solo las categorías de la lista,
por su categoria_id. Si ninguna corresponde de verdad (p. ej. un tornillo y solo hay categorías
de mascotas), devolvé categoria_id null: es preferible a forzar una. Ante la duda entre dos,
elegí la más probable y bajá la confianza.

confianza entre 0 y 1. motivo: una frase corta en español rioplatense. Respondé una entrada por
cada producto, con su mismo número de fila, y copiá en «descripcion» el nombre del producto tal
cual (sirve para controlar que no se mezclen filas)."""

ESQUEMA = {
    "type": "OBJECT",
    "properties": {
        "filas": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "fila": {"type": "INTEGER"},
                    "descripcion": {"type": "STRING"},
                    "categoria_id": {"type": "INTEGER", "nullable": True},
                    "confianza": {"type": "NUMBER"},
                    "motivo": {"type": "STRING"},
                },
                "required": ["fila", "descripcion", "confianza", "motivo"],
            },
        },
    },
    "required": ["filas"],
}


@dataclass
class Sugerencia:
    fila: int
    categoria_id: int | None
    confianza: float
    motivo: str


def armar_pedido(productos: list[dict], categorias: list[dict]) -> str:
    """`productos`: [{fila, nombre, rubro}]; `categorias`: [{id, nombre}]. Solo eso viaja."""
    datos = {
        "categorias_disponibles": [{"categoria_id": c["id"], "nombre": c["nombre"]} for c in categorias],
        "productos": [{"fila": p["fila"], "nombre": p["nombre"], "rubro": p.get("rubro") or ""}
                      for p in productos],
    }
    return INSTRUCCIONES + "\n\nDatos:\n" + json.dumps(datos, ensure_ascii=False)


def _mismo_nombre(a: str, b: str) -> bool:
    """Sin importar mayúsculas, acentos, signos ni espacios («3kg» = «3 kg»)."""
    return gemini._clave(a).replace(" ", "") == gemini._clave(b).replace(" ", "")


def validar(respuesta: dict, productos: list[dict], categorias: list[dict]) -> list[Sugerencia]:
    """Solo filas pedidas y categorías de la lista; lo demás, sin categoría (nunca se inventa).

    Control que no depende de la IA: que repita el nombre del producto que categoriza (si no,
    mezcló filas)."""
    nombres = {p["fila"]: p["nombre"] for p in productos}
    validas = {c["id"] for c in categorias}
    sugerencias: dict[int, Sugerencia] = {}
    for r in respuesta.get("filas", []):
        fila = r.get("fila")
        if fila not in nombres or fila in sugerencias:
            continue
        categoria = r.get("categoria_id")
        confianza = max(0.0, min(1.0, float(r.get("confianza") or 0)))
        motivo = str(r.get("motivo") or "").strip()[:300]
        if not _mismo_nombre(r.get("descripcion", ""), nombres[fila]):
            categoria, confianza = None, 0.0
            otro = str(r.get("descripcion"))[:60]
            motivo = f"La IA respondió sobre otro producto («{otro}»): elegir a mano."
        elif categoria is not None and categoria not in validas:
            categoria, confianza = None, 0.0
            motivo = f"La IA propuso una categoría que no existe: elegir a mano. ({motivo})"
        sugerencias[fila] = Sugerencia(fila, categoria, confianza, motivo)
    for fila in nombres:  # la IA se salteó un producto
        sugerencias.setdefault(fila, Sugerencia(fila, None, 0.0, "La IA no respondió este producto."))
    return [sugerencias[p["fila"]] for p in productos]


def categorizar(productos: list[dict], categorias: list[dict], clave: str, modelos: list[str],
                llamar: Callable[..., dict] = gemini.llamar_gemini_texto,
                esperar: Callable[[float], None] = time.sleep,
                ) -> tuple[list[Sugerencia], gemini.Consumo]:
    """Pide la categoría de cada producto por tandas, en paralelo."""
    if not clave:
        raise gemini.ErrorIA("falta la clave de la IA (GEMINI_API_KEY en el servidor)")
    if not categorias:
        raise gemini.ErrorIA("no hay categorías del punto de venta para elegir")
    tandas = [productos[inicio:inicio + TANDA] for inicio in range(0, len(productos), TANDA)]

    def una_tanda(tanda: list[dict]) -> tuple[list[Sugerencia], gemini.Consumo]:
        consumo = gemini.Consumo()
        texto = armar_pedido(tanda, categorias)
        respuesta = gemini.pedir(lambda modelo: llamar(texto, clave, modelo, esquema=ESQUEMA),
                                 modelos, consumo, esperar)
        return validar(gemini._texto_de(respuesta), tanda, categorias), consumo

    with ThreadPoolExecutor(max_workers=min(EN_PARALELO, len(tandas) or 1)) as hilos:
        hechas = list(hilos.map(una_tanda, tandas))
    total = gemini.Consumo()
    sugerencias: list[Sugerencia] = []
    for parciales, consumo in hechas:
        sugerencias += parciales
        total.pedidos += consumo.pedidos
        total.tokens += consumo.tokens
        total.modelo = consumo.modelo or total.modelo
    return sugerencias, total
