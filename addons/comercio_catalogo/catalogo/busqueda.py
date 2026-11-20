"""Búsqueda de productos en las listas de los proveedores («Buscar producto»).

Cada fila guarda su texto normalizado (`normalizar`) y la búsqueda arma un patrón por
término (`terminos`). Cada término tiene que aparecer, en cualquier orden:

- las palabras, por su comienzo: «galv» encuentra «galvanizada»;
- los números, enteros: «4x40» encuentra «4 X 40» pero no «2,5 x 10 X 400 un».
"""
from __future__ import annotations

import re

from .similitud import sin_acentos

_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+")


def _tokens(texto: str) -> list[str]:
    texto = sin_acentos(texto or "").lower()
    return [t.replace(",", ".") for t in _TOKEN.findall(texto)]


def normalizar(*textos: str) -> str:
    """« tornillo fix 4 x 40 10269 »: sin acentos, números con punto y espacios a los lados
    (para buscar cada término entero o por su comienzo con un simple «contiene»)."""
    tokens = [t for texto in textos for t in _tokens(texto)]
    return f" {' '.join(tokens)} " if tokens else ""


def terminos(texto: str) -> list[str]:
    """Patrones a buscar en el texto normalizado (todos tienen que estar).

    «Tornillo FIX 4x40» → [" tornillo", " fix", " 4 ", " 40 "]
    Las letras sueltas («x» de «4 x 40», «c» de «c/») no se buscan: están en casi todo."""
    salida: list[str] = []
    for token in _tokens(texto):
        if token[0].isdigit():
            patron = f" {token} "
        elif len(token) >= 2:
            patron = f" {token}"
        else:
            continue
        if patron not in salida:
            salida.append(patron)
    return salida


# Palabras que no cambian el producto para agruparlo («x» de «4 x 40», unidades sueltas)
_SIN_PESO = {"x", "de", "del", "la", "el", "con", "c", "p", "para", "mm", "un", "u", "unid", "und"}


def clave_producto(texto: str) -> str:
    """Para agrupar el mismo artículo escrito distinto por cada proveedor: palabras y números
    sin acentos ni mayúsculas, sin el orden ni los «x»/«mm» sueltos. «TORNILLO FIX 4 X 40» y
    «Fix tornillo 4x40 mm» dan lo mismo; «4 X 50» no."""
    return " ".join(sorted({t for t in _tokens(texto) if t not in _SIN_PESO}))
