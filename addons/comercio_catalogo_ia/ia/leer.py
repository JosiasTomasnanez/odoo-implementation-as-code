"""Leer con IA (Gemini) una lista de precios en foto o en PDF escaneado.

La IA solo **transcribe** la tabla (textos y números tal como están impresos); después
la lista sigue el camino de siempre: títulos, columnas, simulación contra la lista
anterior. Una lista leída así nunca se aplica sola (ni los cambios chicos): un dígito mal
leído se vería como una suba o una baja grande y lo revisa una persona.

Qué se manda a Google: la imagen o el PDF de la lista del proveedor (no hay datos del
negocio ni de clientes).
"""
from __future__ import annotations

import base64
import io
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .verificar import EN_PARALELO, TIEMPO_MAXIMO_S, Consumo, ErrorIA, _texto_de, llamar_gemini, pedir

MAX_PAGINAS = 10  # por archivo: cada página es un pedido y todo tiene que entrar en una petición
TIPOS = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".webp": "image/webp"}

INSTRUCCIONES = """Esta es una página de la lista de precios de un proveedor de un comercio argentino.
Transcribí la TABLA de productos tal cual está impresa: una fila por renglón y una celda por
columna, siempre en el mismo orden de columnas, incluida la fila de títulos de las columnas si
está en esta página (y los renglones de rubro o sección, como una fila con una sola celda).
Copiá textos y números EXACTAMENTE como se ven (mismos puntos, comas y signos $), sin calcular,
corregir, completar ni traducir. Celda vacía: "". Si un dígito no se lee con seguridad, poné
"?" en su lugar (no lo adivines). No incluyas logos, datos de la empresa ni pies de página que
no sean parte de la tabla. Si la página no tiene tabla de productos, devolvé "filas" vacío."""

ESQUEMA = {
    "type": "OBJECT",
    "properties": {"filas": {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "STRING"}}}},
    "required": ["filas"],
}


# Modo «productos» (20/11): para listas sin columnas reconocibles (sin títulos, varios formatos en
# el mismo archivo, nombres en dos renglones). La IA no copia la tabla: arma un producto por renglón
# con código, descripción completa y precio, con títulos fijos para que las columnas se reconozcan.
INSTRUCCIONES_PRODUCTOS = """Esta es una página de la lista de precios de un proveedor de un comercio
argentino (ferretería, corralón, bazar, vivero…). La lista puede no tener títulos de columnas, mezclar
formatos o tener varias columnas de productos lado a lado (p. ej. «DESCRIPCION | PRECIO | DESCRIPCION |
PRECIO»): leé cada columna de productos por separado, de arriba a abajo, sin mezclar un producto con el
precio del de al lado. Devolvé cada PRODUCTO con su precio, uno por elemento:
- codigo: el código del producto si la lista lo trae (p. ej. «A9-10»); si no, "".
- descripcion: el nombre completo. Si el nombre sigue en el renglón de abajo (sin precio), unilo
  («PEG. CERAMICO» + «PERFECTO» = «PEG. CERAMICO PERFECTO»). Si arriba hay un título de rubro o
  sección (p. ej. «VIGUETAS T1») y el renglón solo trae la medida, anteponé ese título.
- precio: el precio de venta del producto, copiado EXACTAMENTE como está impreso (con su $, puntos
  y comas), sin calcular. Si el renglón trae otros números (kilos, medidas), el precio es el que
  tiene $ o el último. Si no tiene precio o dice «consultar», no incluyas el producto.
No incluyas títulos, horarios, datos de la empresa, notas ni pies de página. Si un dígito no se lee
con seguridad, poné "?" en su lugar. Si la página no tiene productos, devolvé "productos" vacío."""

ESQUEMA_PRODUCTOS = {
    "type": "OBJECT",
    "properties": {"productos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"codigo": {"type": "STRING"}, "descripcion": {"type": "STRING"},
                       "precio": {"type": "STRING"}},
        "required": ["descripcion", "precio"]}}},
    "required": ["productos"],
}
TITULOS_PRODUCTOS = ["Código", "Descripción", "Precio"]


def tipo_de(nombre_archivo: str) -> str | None:
    nombre = nombre_archivo.lower()
    return next((tipo for ext, tipo in TIPOS.items() if nombre.endswith(ext)), None)


def paginas(contenido: bytes, tipo: str) -> list[bytes]:
    """Un PDF se manda de a una página (la respuesta de una página siempre entra)."""
    if tipo != "application/pdf":
        return [contenido]
    try:
        from pypdf import PdfReader, PdfWriter  # viene con Odoo
    except ImportError:
        return [contenido]
    lector = PdfReader(io.BytesIO(contenido))
    salida = []
    for pagina in lector.pages:
        escritor = PdfWriter()
        escritor.add_page(pagina)
        archivo = io.BytesIO()
        escritor.write(archivo)
        salida.append(archivo.getvalue())
    return salida


def _clave(fila: list[str]) -> str:
    return "|".join(c.strip().lower() for c in fila)


def unir(paginas_leidas: list[list[list[str]]]) -> list[list[str]]:
    """Junta las páginas en una tabla. Los títulos repetidos al principio de cada página se
    sacan (quedan los de la primera) y todas las filas quedan del mismo ancho."""
    tabla: list[list[str]] = []
    vistos: set[str] = set()
    for filas in paginas_leidas:
        for i, fila in enumerate(filas):
            fila = [str(c or "").strip() for c in fila]
            if not any(fila):
                continue
            # Una fila con varias celdas que ya apareció arriba de otra página: es el título repetido
            if i < 5 and sum(1 for c in fila if c) >= 2 and _clave(fila) in vistos:
                continue
            if i < 5:
                vistos.add(_clave(fila))
            tabla.append(fila)
    ancho = max((len(f) for f in tabla), default=0)
    return [f + [""] * (ancho - len(f)) for f in tabla]


def leer(contenido: bytes, nombre_archivo: str, clave: str, modelos: list[str],
         llamar: Callable[..., dict] = llamar_gemini, esperar: Callable[[float], None] = time.sleep,
         productos: bool = False, plazo: float | None = None) -> tuple[list[list[str]], Consumo, int]:
    """(tabla, consumo, páginas) de una foto o un PDF escaneado. Con `productos`, en vez de copiar
    la tabla arma una fila por producto con títulos fijos (Código, Descripción, Precio). Con `plazo`
    (segundos), si Google no termina a tiempo se corta con ErrorIA (20/11: con la IA saturada, un
    PDF que igual se podía leer del texto tardaba 5 minutos en reintentos)."""
    limite = time.monotonic() + plazo if plazo else None

    def restante() -> float | None:
        if limite is None:
            return None
        resto = limite - time.monotonic()
        if resto <= 1:
            raise ErrorIA("la IA tardó demasiado")
        return resto

    def esperar_con_plazo(segundos: float) -> None:
        resto = restante()
        if resto is not None and segundos >= resto:
            raise ErrorIA("la IA tardó demasiado")
        esperar(segundos)

    def llamar_con_plazo(partes, modelo, esquema):
        resto = restante()
        if resto is not None and llamar is llamar_gemini:
            return llamar(partes, clave, modelo, tiempo_maximo=min(TIEMPO_MAXIMO_S, resto), esquema=esquema)
        return llamar(partes, clave, modelo, esquema=esquema)

    if not clave:
        raise ErrorIA("falta la clave de la IA (GEMINI_API_KEY en el servidor)")
    tipo = tipo_de(nombre_archivo)
    if not tipo:
        raise ErrorIA(f"«{nombre_archivo}» no es una foto ni un PDF")
    hojas = paginas(contenido, tipo)
    if len(hojas) > MAX_PAGINAS:
        raise ErrorIA(f"el PDF tiene {len(hojas)} páginas y la IA lee hasta {MAX_PAGINAS} por vez: "
                      "dividilo o pedile al proveedor el Excel o el PDF original")
    consumo = Consumo()
    instrucciones, esquema = ((INSTRUCCIONES_PRODUCTOS, ESQUEMA_PRODUCTOS) if productos
                              else (INSTRUCCIONES, ESQUEMA))

    def leer_pagina(hoja):
        partes = [{"inline_data": {"mime_type": tipo, "data": base64.b64encode(hoja).decode()}},
                  {"text": instrucciones}]
        respuesta = pedir(lambda modelo: llamar_con_plazo(partes, modelo, esquema),
                          modelos, consumo, esperar_con_plazo)
        datos = _texto_de(respuesta)
        if productos:
            items = datos.get("productos") if isinstance(datos, dict) else None
            if not isinstance(items, list):
                raise ErrorIA("la IA no devolvió los productos")
            return [[str(i.get("codigo") or "").strip(), str(i.get("descripcion") or "").strip(),
                     str(i.get("precio") or "").strip()]
                    for i in items
                    if isinstance(i, dict) and i.get("descripcion") and i.get("precio")]
        filas = datos.get("filas") if isinstance(datos, dict) else None
        if not isinstance(filas, list):
            raise ErrorIA("la IA no devolvió una tabla")
        return [f for f in filas if isinstance(f, list)]

    # Las páginas en paralelo (20/11: un PDF de 6 páginas tardaba ~3 minutos de a una), en orden
    with ThreadPoolExecutor(max_workers=min(EN_PARALELO, len(hojas) or 1)) as hilos:
        leidas = list(hilos.map(leer_pagina, hojas))
    if productos:
        filas = [f for pagina in leidas for f in pagina]
        if not filas:
            raise ErrorIA("la IA no encontró productos con precio en el archivo")
        return [TITULOS_PRODUCTOS] + filas, consumo, len(hojas)
    tabla = unir(leidas)
    if not tabla:
        raise ErrorIA("la IA no encontró una tabla de productos en el archivo")
    return tabla, consumo, len(hojas)
