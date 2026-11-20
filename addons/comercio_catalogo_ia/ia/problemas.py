"""Filas con problemas de una lista de proveedor (sin precio, precio 0, código repetido, mal
copiadas): la IA explica qué pasó y sugiere qué hacer. Solo sugiere; nada se aplica.

Python puro, sin Odoo. A Google se manda lo mismo que en la verificación (ADR 0018): la
descripción y el código de la fila, el problema que encontró el programa y, si la celda del
precio traía un texto («SIN STOCK», «Consultar»), ese texto. Nunca precios ni costos.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .verificar import EN_PARALELO, Consumo, ErrorIA, _clave, _texto_de, llamar_gemini_texto, pedir

TANDA = 30
CORREGIR_PRECIO, CORREGIR_DESCRIPCION, IGNORAR, CONSULTAR, REVISAR = (
    "corregir_precio", "corregir_descripcion", "ignorar", "consultar_proveedor", "revisar_a_mano")
QUE_HACER = {
    CORREGIR_PRECIO: "Corregir: cargar el precio a mano",
    CORREGIR_DESCRIPCION: "Corregir: arreglar la descripción",
    IGNORAR: "Ignorar la fila",
    CONSULTAR: "Preguntarle al proveedor",
    REVISAR: "Revisar a mano",
}

INSTRUCCIONES = """Sos un asistente de un comercio argentino (ferretería, mascotas, veterinaria) que carga
en su sistema las listas de precios de sus proveedores. Estas filas de una lista tienen un
problema que el programa no pudo resolver solo. Para cada una explicá en una frase corta, en
español rioplatense y sin tecnicismos, qué pasó y qué conviene hacer, eligiendo una acción:

- corregir_precio: el precio falta o vino mal pero el producto existe (p. ej. una celda vacía
  o un 0 que parece error de la lista); la persona lo carga a mano si lo sabe.
- corregir_descripcion: la descripción vino cortada, con basura o mezclada.
- ignorar: no es un producto que se pueda comprar ahora (sin stock, discontinuado, una nota,
  un título, una fila repetida del proveedor).
- consultar_proveedor: el precio dice «consultar» o similar: hay que pedírselo.
- revisar_a_mano: no queda claro.

Respondé una entrada por fila, con su número de fila, y copiá su descripción tal cual."""

ESQUEMA = {
    "type": "OBJECT",
    "properties": {"filas": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {
            "fila": {"type": "INTEGER"},
            "descripcion": {"type": "STRING"},
            "accion": {"type": "STRING", "enum": list(QUE_HACER)},
            "explicacion": {"type": "STRING"},
        },
        "required": ["fila", "descripcion", "accion", "explicacion"],
    }}},
    "required": ["filas"],
}


@dataclass
class Sugerencia:
    fila: int
    accion: str
    explicacion: str


def armar_pedido(filas: list[dict]) -> str:
    """`filas`: [{fila, descripcion, codigo, problema, texto_precio}]."""
    datos = [{"fila": f["fila"], "descripcion": f["descripcion"], "codigo": f.get("codigo") or "",
              "problema": f["problema"], "celda_del_precio": f.get("texto_precio") or ""} for f in filas]
    return INSTRUCCIONES + "\n\nFilas:\n" + json.dumps(datos, ensure_ascii=False)


def validar(respuesta: dict, filas: list[dict]) -> list[Sugerencia]:
    """Solo filas pedidas, con su misma descripción; lo demás, «revisar a mano»."""
    descripcion = {f["fila"]: f["descripcion"] for f in filas}
    salida: dict[int, Sugerencia] = {}
    for r in respuesta.get("filas", []):
        fila = r.get("fila")
        if fila not in descripcion or fila in salida:
            continue
        accion = r.get("accion") if r.get("accion") in QUE_HACER else REVISAR
        explicacion = str(r.get("explicacion") or "").strip()[:300]
        if _clave(r.get("descripcion", "")) != _clave(descripcion[fila]):
            accion, explicacion = REVISAR, "La IA respondió sobre otra fila: revisar a mano."
        salida[fila] = Sugerencia(fila, accion, explicacion)
    for fila in descripcion:
        salida.setdefault(fila, Sugerencia(fila, REVISAR, "La IA no respondió esta fila."))
    return [salida[f["fila"]] for f in filas]


def sugerir(filas: list[dict], clave: str, modelos: list[str],
            llamar: Callable[..., dict] = llamar_gemini_texto,
            esperar: Callable[[float], None] = time.sleep) -> tuple[list[Sugerencia], Consumo]:
    if not clave:
        raise ErrorIA("falta la clave de la IA (GEMINI_API_KEY en el servidor)")
    tandas = [filas[inicio:inicio + TANDA] for inicio in range(0, len(filas), TANDA)]

    def una_tanda(tanda: list[dict]) -> tuple[list[Sugerencia], Consumo]:
        consumo = Consumo()  # uno por tanda: los hilos no comparten contadores
        texto = armar_pedido(tanda)
        respuesta = pedir(lambda modelo: llamar(texto, clave, modelo, ESQUEMA), modelos, consumo, esperar)
        return validar(_texto_de(respuesta), tanda), consumo

    # En paralelo, como la verificación (06/11: antes iban de a una tanda y tardaba)
    with ThreadPoolExecutor(max_workers=min(EN_PARALELO, len(tandas) or 1)) as hilos:
        hechas = list(hilos.map(una_tanda, tandas))
    total, sugerencias = Consumo(), []
    for parciales, consumo in hechas:
        sugerencias += parciales
        total.pedidos += consumo.pedidos
        total.tokens += consumo.tokens
        total.modelo = consumo.modelo or total.modelo
    return sugerencias, total
