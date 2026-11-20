"""Listas de precios en PDF con texto (las que se exportan de Excel o de un sistema).

Sin IA y sin adivinar números: se toma cada letra con su posición (pdfminer, viene con
Odoo), se arman los renglones por altura y las celdas por los espacios grandes, y cada
celda se ubica en la columna del título que tiene encima. El resultado es la misma tabla
que daría el Excel, y sigue el camino de siempre (títulos, columnas, simulación).

Un PDF escaneado (una foto dentro de un PDF) no tiene texto: `tabla_desde_pdf` devuelve
None y lo resuelve la IA (módulo comercio_catalogo_ia).
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from .convertir import encontrar_encabezado

MIN_LETRAS = 20  # menos que esto en todo el PDF: es una imagen escaneada


@dataclass
class _Celda:
    texto: str
    x0: float
    x1: float

    @property
    def centro(self) -> float:
        return (self.x0 + self.x1) / 2


def _letras(pagina) -> list:
    from pdfminer.layout import LTChar

    salida = []

    def recorrer(objeto):
        if isinstance(objeto, LTChar):
            if objeto.get_text().strip():
                salida.append(objeto)
            return
        for hijo in getattr(objeto, "_objs", ()) or ():
            recorrer(hijo)

    recorrer(pagina)
    return salida


def _renglones(letras: list) -> list[list[_Celda]]:
    """Agrupa las letras por altura (renglón) y las corta en celdas donde hay un hueco
    grande (más que un par de espacios)."""
    letras = sorted(letras, key=lambda c: (-round(c.y0), c.x0))
    renglones: list[list] = []
    for letra in letras:
        alto = max(letra.height, 1)
        if renglones and abs(renglones[-1][0].y0 - letra.y0) <= alto * 0.4:
            renglones[-1].append(letra)
        else:
            renglones.append([letra])
    salida = []
    for renglon in renglones:
        renglon.sort(key=lambda c: c.x0)
        celdas: list[_Celda] = []
        anterior = None
        for letra in renglon:
            ancho = max(letra.width, letra.size * 0.3, 1)
            hueco = letra.x0 - anterior.x1 if anterior else None
            if anterior is None or hueco > ancho * 1.6:
                celdas.append(_Celda(letra.get_text(), letra.x0, letra.x1))
            else:
                celda = celdas[-1]
                if hueco > ancho * 0.25:
                    celda.texto += " "
                celda.texto += letra.get_text()
                celda.x1 = letra.x1
            anterior = letra
        salida.append(celdas)
    return salida


def _columna(celda: _Celda, columnas: list[_Celda]) -> int:
    """La del título que más se superpone con la celda (o la más cercana)."""
    def superposicion(titulo: _Celda) -> float:
        return min(celda.x1, titulo.x1) - max(celda.x0, titulo.x0)

    mejor = max(range(len(columnas)), key=lambda i: superposicion(columnas[i]))
    if superposicion(columnas[mejor]) > 0:
        return mejor
    return min(range(len(columnas)), key=lambda i: abs(columnas[i].centro - celda.centro))


def renglones_desde_pdf(contenido: bytes) -> list[list[tuple[str, float, float]]]:
    """Todos los renglones del PDF (página tras página), cada celda con su texto y dónde
    empieza y termina (x0, x1): para leer lo que no es una tabla, como el pie de una factura."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams

    return [[(c.texto.strip(), c.x0, c.x1) for c in renglon]
            for pagina in extract_pages(io.BytesIO(contenido), laparams=LAParams())
            for renglon in _renglones(_letras(pagina))]


def tabla_desde_pdf(contenido: bytes) -> list[list[str]] | None:
    """Filas del PDF como listas de textos, alineadas con los títulos. None si no tiene
    texto (escaneado)."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams

    renglones: list[list[_Celda]] = []
    for pagina in extract_pages(io.BytesIO(contenido), laparams=LAParams()):
        renglones.extend(_renglones(_letras(pagina)))
    if sum(len(c.texto) for r in renglones for c in r) < MIN_LETRAS:
        return None
    crudo = [[c.texto.strip() for c in r] for r in renglones]
    fila_titulos = encontrar_encabezado(crudo, maximo=60)
    columnas = renglones[fila_titulos - 1] if fila_titulos else []
    if len(columnas) < 2:
        return crudo
    tabla = [[c.texto.strip() for c in r] for r in renglones[:fila_titulos]]
    for renglon in renglones[fila_titulos:]:
        fila = [""] * len(columnas)
        for celda in renglon:
            i = _columna(celda, columnas)
            fila[i] = f"{fila[i]} {celda.texto.strip()}".strip()
        tabla.append(fila)
    return tabla
