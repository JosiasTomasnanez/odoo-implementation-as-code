"""Lectura de la lista de un proveedor (Excel o CSV) y conversión a la planilla modelo.

Cada proveedor manda su lista con otras columnas. Un mapeo dice qué columna del
proveedor corresponde a cada columna de la planilla modelo; `sugerir_mapeo` propone uno
a partir de los títulos, para no escribirlo a mano.
"""
from __future__ import annotations

import csv
import io
import re
import statistics
from collections import Counter

from .costo import (
    _pesos,
    cantidad_de_pack,
    costo_desde_lista,
    de_la_fila,
    descuentos_de_celda,
    hay_ajustes,
    leer_promocion,
    normalizar_ajustes,
)
from .similitud import sin_acentos

SUMA = " + "  # en el mapeo, une varias columnas del archivo en una (ver convertir)

COLUMNAS = ["proveedor", "codigo_proveedor", "descripcion_proveedor", "codigo_barras", "nombre",
            "categoria", "unidad", "costo", "cantidad_minima", "plazo_dias", "pesable", "precio_venta",
            "costo_mayor", "cantidad_mayor"]

# Columnas que se pueden tomar del archivo del proveedor y títulos habituales de cada una
SINONIMOS = {
    "codigo_proveedor": ["codigo", "cod", "cod art", "codigo articulo", "articulo", "art", "sku", "id",
                         "referencia", "ref", "cod producto", "codigo interno", "cod articulo", "cod artic",
                         "sinonimo", "codigo empresa", "cd"],
    "descripcion_proveedor": ["descripcion", "producto", "detalle", "nombre", "articulo descripcion",
                              "desc", "item", "descripcion articulo", "descrip", "descripcion del producto",
                              "articulo"],
    "codigo_barras": ["ean", "ean13", "ean 13", "cod ean", "codigo ean", "codigo de barras", "cod barras",
                      "cod de barras", "barras", "codbarra", "upc", "gtin"],
    # En orden de preferencia: el costo antes que el neto y el neto antes que un «precio» a secas
    "costo": ["costo", "precio costo", "precio de costo", "costo unitario", "p costo", "costo neto", "neto",
              "precio neto", "netos", "precio s iva", "precio sin iva", "sin iva", "s iva", "comercios iva",
              "precio lista",
              "precio de lista", "p lista", "lista", "precio unitario", "p unitario", "precio", "precios",
              "importe"],
    "cantidad_minima": ["minimo", "min", "cant minima", "cantidad minima", "compra minima"],
    # Unidades por bulto (30/10): se compra de a bultos enteros (100, 200…), no es lo mismo que un mínimo
    "bulto": ["uxb", "u x b", "unidades por bulto", "unidades x bulto", "unidades por caja",
              "unidades x caja",
              "bulto", "bto", "master", "caja master", "unid x caja", "x caja", "se vende por"],
    # Segundo precio del mismo producto: por mayor, comprando desde cierta cantidad
    "costo_mayor": ["precio mayorista", "precio por mayor", "precio x mayor", "por mayor", "mayorista",
                    "precio bulto", "precio x bulto", "precio por bulto", "precio caja", "precio x caja"],
    "cantidad_mayor": ["cantidad mayor", "cant mayor", "cantidad mayorista", "minimo mayor",
                       "minimo mayorista", "desde", "a partir de"],
    "unidad": ["unidad", "um", "u m", "unidad de medida"],
    # Alícuota de IVA de cada fila (10,5 / 21 / 27): solo sirve si la lista trae el IVA incluido
    "iva": ["iva", "alicuota", "alicuota iva", "alic iva", "tasa iva", "iva %"],
    # Promociones del proveedor en texto («5% DTO. X UNIDAD», «10% DTO. X 2 ROLLOS»): FC
    # Disponibilidad del proveedor: las filas sin stock no se cargan (30/10, pedido del cliente)
    "stock": ["stock", "disponible", "disponibilidad", "hay stock"],
    "promocion": ["descuentos y promociones vigentes", "promociones vigentes", "promociones", "promocion",
                  "promo", "ofertas", "oferta"],
}
# La columna «descuento» no tiene sinónimos a propósito: se elige siempre a mano. Una columna
# «Desc.» puede ser el descuento del proveedor o una cuenta del comercio (30/10: en varias
# listas era el cálculo de Daniel sobre su propio descuento, el IVA y demás).
# Títulos de columnas que agrega el comercio (o precios para el público): nunca son el costo
NO_ES_COSTO = ("publico", "venta", "vta", "margen", "marg", "redondeo", "utilidad", "sugerido", "final",
               "con iva", "c iva", "mas iva", "iva incluido", "total", "dolar", "formula", "ganancia")
# Si el archivo trae una fila de títulos cada tantas filas vacías seguidas, el resto es formato
# copiado hacia abajo (hay Excel que declaran un millón de filas): se deja de leer
MAX_FILAS_VACIAS = 500
# Celdas que no son un precio aunque estén en la columna del precio
SIN_PRECIO = ("sin stock", "consultar", "a consultar", "s/cotizar", "sin cotizar", "#value!", "#ref!",
              "#n/a", "#div/0!", "#name?", "-", "--", "s/p", "agotado", "no disponible")


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))  # 7790000001017.0 → 7790000001017 (códigos guardados como número)
        # Decimal con coma: así «0.125» no se confunde con «125» escrito con punto de miles
        return repr(valor).replace(".", ",")
    return str(valor).strip()


def _decodificar(contenido: bytes) -> str:
    """UTF-8; si no, Windows-1252 (el «CSV delimitado» que guarda Excel en Windows)."""
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenido.decode("cp1252", errors="replace")


def _separador(lineas: list[str]) -> str:
    """El separador que más se repite en forma pareja en las primeras líneas (no solo en la primera,
    que suele ser un título como «Lista de precios, octubre»)."""
    muestra = [linea for linea in lineas[:30] if linea.strip()]
    mejor, puntaje_mejor = ";", -1
    for sep in (";", ",", "\t"):
        cuentas = [linea.count(sep) for linea in muestra]
        con_sep = [x for x in cuentas if x]
        if not con_sep:
            continue
        moda = max(set(con_sep), key=con_sep.count)
        puntaje = con_sep.count(moda) * moda
        if puntaje > puntaje_mejor:
            mejor, puntaje_mejor = sep, puntaje
    return mejor


def _normalizar_titulo(titulo: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_acentos(titulo or "").lower()).split())


def _hasta_el_final(filas) -> list[list[str]]:
    """Las filas hasta donde hay datos: corta tras MAX_FILAS_VACIAS vacías seguidas y saca las
    vacías del final (un Excel con formato copiado hasta la fila 1 048 576 tardaba 30 s)."""
    salida: list[list[str]] = []
    vacias = 0
    for fila in filas:
        textos = [_texto(v) for v in fila]
        if any(textos):
            salida.extend([[]] * vacias)
            salida.append(textos)
            vacias = 0
            continue
        vacias += 1
        if vacias >= MAX_FILAS_VACIAS:
            break
    return salida


_ES_FECHA = re.compile(r"[\d][\d_\-./ ]*")


def _otra_fecha(pedida: str, nombres: list[str]) -> str | None:
    """La hoja que reemplaza a la pedida cuando el proveedor le pone la fecha de la lista
    (Oeste: «02_06_2026» y el mes siguiente otra): la única con nombre de fecha. None si no."""
    if not _ES_FECHA.fullmatch(pedida.strip()):
        return None
    fechas = [n for n in nombres if _ES_FECHA.fullmatch(n.strip())]
    return fechas[0] if len(fechas) == 1 else None


def _hoja_xlsx(libro, hoja):
    """La hoja pedida por nombre o número. Si el nombre ya no existe y el libro tiene una sola
    hoja (hay proveedores que le ponen la fecha), esa; si no, un error claro."""
    if isinstance(hoja, str) and hoja and not hoja.isdigit():
        if hoja in libro.sheetnames:
            return libro[hoja]
        if len(libro.worksheets) == 1:
            return libro.worksheets[0]
        if _otra_fecha(hoja, libro.sheetnames):
            return libro[_otra_fecha(hoja, libro.sheetnames)]
        raise ValueError(f"el Excel no tiene la hoja «{hoja}» (tiene: {', '.join(libro.sheetnames)})")
    indice = int(hoja or 0)
    if indice >= len(libro.worksheets):
        raise ValueError(f"el Excel tiene {len(libro.worksheets)} hojas y se pidió la número {indice + 1}")
    return libro.worksheets[indice]


# Formato de celda de Excel en dólares («"U$S" #.##0,00», «[$USD] 0.00»); el resto con «$» es pesos
_FORMATO_DOLAR = re.compile(r"u\$s|u\$d|us\$|usd", re.I)


def _con_moneda(valor, formato: str | None):
    """Un número con la moneda de su formato de celda delante («$ 214,2», «US$ 0,74»); el resto,
    igual. Para las listas que mezclan pesos y dólares en la misma columna (LTX)."""
    if not isinstance(valor, (int, float)) or isinstance(valor, bool) or not formato:
        return valor
    if _FORMATO_DOLAR.search(formato):
        return f"US$ {_texto(float(valor))}"
    if "$" in formato:
        return f"$ {_texto(float(valor))}"
    return valor


_TEXTO_DOLAR = re.compile(r"u\$s|u\$d|us\$|\busd\b|d[oó]lar", re.I)


def sugerir_moneda(tabla: list[list[str]], fila_encabezado: int, titulo_costo: str | None) -> str | None:
    """Moneda que parece tener la lista (06/11): «usd», «ars», «mixta» o None si no se sabe.
    `tabla` leída con monedas=True (cada precio con «US$ » o «$ » según el formato de su celda).
    Mira el título de la columna del precio, el texto de arriba del encabezado y los formatos."""
    if not tabla or not fila_encabezado:
        return None
    titulos = tabla[fila_encabezado - 1] if len(tabla) >= fila_encabezado else []
    arriba = " ".join(" ".join(c for c in f if c) for f in tabla[:fila_encabezado - 1])
    buscado = " ".join((titulo_costo or "").split())
    idx = next((i for i, t in enumerate(titulos) if buscado and " ".join(str(t).split()) == buscado), None)
    if idx is not None and _TEXTO_DOLAR.search(str(titulos[idx])):
        return "usd"
    dolares = pesos = 0
    if idx is not None:
        for f in tabla[fila_encabezado:fila_encabezado + 2000]:
            v = str(f[idx]).strip() if idx < len(f) else ""
            if v.startswith("US$"):
                dolares += 1
            elif v.startswith("$"):
                pesos += 1
    total = dolares + pesos
    if total >= 5:
        if dolares / total >= 0.8:
            return "usd"
        if pesos / total >= 0.8:
            return "ars"
        return "mixta"
    if _TEXTO_DOLAR.search(arriba):
        return "usd"
    return None


def leer_tabla(contenido: bytes, nombre_archivo: str, hoja=None, monedas: bool = False) -> list[list[str]]:
    """Filas del archivo como listas de textos (todas, incluidos títulos y separadores).

    `monedas`: los números de un Excel llevan delante la moneda de su formato de celda («$ 214,2»,
    «US$ 0,74»): para las listas con pesos y dólares mezclados (moneda «mixta»)."""
    if not contenido:
        raise ValueError("el archivo está vacío")
    if nombre_archivo.lower().endswith((".xlsx", ".xlsm")):
        import zipfile

        import openpyxl

        try:
            libro = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        except zipfile.BadZipFile as error:
            raise ValueError("no es un Excel válido (¿está dañado o es otro tipo de archivo?)") from error
        filas = _hoja_xlsx(libro, hoja).iter_rows(values_only=not monedas)
        if monedas:
            filas = ([_con_moneda(c.value, getattr(c, "number_format", None)) for c in fila]
                     for fila in filas)
        return _hasta_el_final(filas)
    if nombre_archivo.lower().endswith(".xls"):
        return _leer_xls(contenido, hoja, monedas)
    lineas = _decodificar(contenido).splitlines()
    return list(csv.reader(lineas, delimiter=_separador(lineas)))


def hojas(contenido: bytes, nombre_archivo: str) -> list[tuple[str, int]]:
    """(nombre, filas con datos) de cada hoja de un Excel; [] si no es Excel o no se puede leer.

    Una fila «con datos» tiene al menos dos celdas escritas (descarta títulos y separadores):
    sirve para ofrecer las hojas con productos cuando el proveedor manda la lista en partes."""
    nombre = nombre_archivo.lower()
    try:
        if nombre.endswith((".xlsx", ".xlsm")):
            import openpyxl

            libro = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
            return [(h.title, sum(1 for fila in _hasta_el_final(h.iter_rows(values_only=True))
                                  if sum(1 for v in fila if v) >= 2)) for h in libro.worksheets]
        if nombre.endswith(".xls"):
            import xlrd

            libro = xlrd.open_workbook(file_contents=contenido)
            return [(h.name, sum(1 for i in range(h.nrows)
                                 if sum(1 for v in h.row_values(i) if _texto(v)) >= 2))
                    for h in libro.sheets()]
    except Exception:  # noqa: BLE001 - el error claro lo da después la lectura de la hoja
        return []
    return []


def _leer_xls(contenido: bytes, hoja=None, monedas: bool = False) -> list[list[str]]:
    """Excel 97-2003 (.xls), el formato en que todavía mandan la lista muchos proveedores.

    Se lee directo con xlrd (viene con Odoo): no hace falta convertirlo a .xlsx antes."""
    import xlrd

    try:
        libro = xlrd.open_workbook(file_contents=contenido, formatting_info=monedas)
    except xlrd.XLRDError as error:
        raise ValueError("no es un Excel .xls válido (¿está dañado o es otro tipo de archivo?)") from error
    if isinstance(hoja, str) and hoja and not hoja.isdigit():
        try:
            hoja_xl = libro.sheet_by_name(hoja)
        except xlrd.XLRDError as error:
            otra = _otra_fecha(hoja, libro.sheet_names())
            if otra:
                hoja_xl = libro.sheet_by_name(otra)  # la misma lista con la fecha nueva
            elif libro.nsheets != 1:
                raise ValueError(f"el Excel no tiene la hoja «{hoja}» "
                                 f"(tiene: {', '.join(libro.sheet_names())})") from error
            else:
                hoja_xl = libro.sheet_by_index(0)  # una sola hoja con otro nombre (la fecha, p. ej.)
    else:
        if int(hoja or 0) >= libro.nsheets:
            raise ValueError(f"el Excel tiene {libro.nsheets} hojas y se pidió la número "
                             f"{int(hoja or 0) + 1}")
        hoja_xl = libro.sheet_by_index(int(hoja or 0))
    if monedas:
        def formato(i, j):
            xf = libro.xf_list[hoja_xl.cell_xf_index(i, j)]
            return libro.format_map[xf.format_key].format_str

        return _hasta_el_final([_con_moneda(v, formato(i, j)) for j, v in enumerate(hoja_xl.row_values(i))]
                               for i in range(hoja_xl.nrows))
    return _hasta_el_final(hoja_xl.row_values(i) for i in range(hoja_xl.nrows))


def tabla_a_csv(tabla: list[list[str]]) -> bytes:
    """La tabla leída de un PDF o una foto como CSV (así se guarda y se vuelve a simular igual
    que un Excel, sin leer el original otra vez)."""
    salida = io.StringIO()
    csv.writer(salida, delimiter=";").writerows(tabla)
    return salida.getvalue().encode("utf-8")


def letra_columna(indice: int) -> str:
    """0 → A, 25 → Z, 26 → AA (como en Excel)."""
    letras = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def titulos_unicos(fila: list[str], con_datos: set[int] | None = None) -> list[str]:
    """Títulos de la fila de encabezado, sin repetidos: el segundo «NETO» pasa a «NETO (2)».

    Si no, el último pisaba al primero y no había forma de elegir el primero. Una columna sin
    título pero con datos (`con_datos`: sus posiciones) se llama «Columna B», como en Excel:
    hay listas que no le ponen título al código."""
    usados: set[str] = set()
    salida = []
    for i, titulo in enumerate(fila):
        if not titulo and con_datos and i in con_datos:
            titulo = f"Columna {letra_columna(i)}"
        if titulo:
            base, n = titulo, 1
            while titulo in usados:  # «NETO (2)» puede ser también el título de otra columna
                n += 1
                titulo = f"{base} ({n})"
            usados.add(titulo)
        salida.append(titulo)
    return salida


def columnas_con_datos(tabla: list[list[str]], fila_encabezado: int, muestra: int = 200) -> set[int]:
    """Posiciones de las columnas que tienen algo escrito debajo de los títulos."""
    return {i for fila in tabla[fila_encabezado:fila_encabezado + muestra] for i, v in enumerate(fila) if v}


def apilar_lado_a_lado(tabla: list[list[str]], fila_encabezado: int) -> list[list[str]]:
    """Productos en varias columnas lado a lado con los mismos títulos (20/11, Nu: «DESCRIPCION |
    PRECIO | DESCRIPCION | PRECIO | DESCRIPCION | PRECIO», una línea de macetas por columna): se
    ponen una debajo de la otra, como una lista común. Si los títulos no se repiten, la tabla tal cual.
    Las filas de arriba de los títulos se dejan como están."""
    if len(tabla) < fila_encabezado or fila_encabezado < 1:
        return tabla
    encabezado = tabla[fila_encabezado - 1]
    con_titulo = [(i, _normalizar_titulo(c)) for i, c in enumerate(encabezado) if str(c).strip()]
    nombres = [n for _, n in con_titulo]
    bloque = None
    for largo in range(2, len(nombres) // 2 + 1):
        if len(nombres) % largo == 0 and all(nombres[j] == nombres[j % largo] for j in range(len(nombres))) \
                and len(set(nombres[:largo])) == largo:
            bloque = largo
            break
    if not bloque:
        return tabla
    grupos = [[i for i, _ in con_titulo[g:g + bloque]] for g in range(0, len(con_titulo), bloque)]

    def tomar(fila, columnas):
        return [fila[c] if c < len(fila) else "" for c in columnas]

    salida = [tomar(fila, grupos[0]) for fila in tabla[:fila_encabezado - 1]]
    salida.append(tomar(encabezado, grupos[0]))
    for columnas in grupos:
        salida.extend(tomar(fila, columnas) for fila in tabla[fila_encabezado:])
    return salida


def titulos_de(tabla: list[list[str]], fila_encabezado: int) -> list[str]:
    """Los títulos (únicos, con «Columna X» para las sin título con datos) de la fila elegida."""
    tabla = apilar_lado_a_lado(tabla, fila_encabezado)
    if len(tabla) < fila_encabezado:
        return []
    return titulos_unicos(tabla[fila_encabezado - 1], columnas_con_datos(tabla, fila_encabezado))


def encontrar_encabezado(tabla: list[list[str]], maximo: int = 30) -> int:
    if not tabla:
        raise ValueError("el archivo no tiene filas")
    """Número de fila (desde 1) que más se parece a una fila de títulos."""
    mejor, puntaje_mejor = 1, -1
    for i, fila in enumerate(tabla[:maximo], start=1):
        titulos = {_normalizar_titulo(c) for c in fila if c}
        puntaje = sum(1 for sinonimos in SINONIMOS.values() if titulos & set(sinonimos))
        if puntaje > puntaje_mejor:
            mejor, puntaje_mejor = i, puntaje
    return mejor


def _con_palabra(titulo: str, palabra: str) -> bool:
    """La palabra (o frase) aparece entera en el título normalizado."""
    return f" {palabra} " in f" {titulo} "


def _es_numero(texto) -> bool:
    from .plan import _numero  # plan no importa este módulo

    try:
        _numero(texto)
    except ValueError:
        return False
    return bool(str(texto or "").strip())


def _parece(columna: str, titulo: str) -> bool:
    """Descarta títulos que contienen la palabra pero son otra cosa."""
    if columna in ("costo", "costo_mayor"):
        return not any(_con_palabra(titulo, x) for x in NO_ES_COSTO)
    if columna == "codigo_proveedor":
        return not any(_con_palabra(titulo, x) for x in ("barra", "barras", "ean", "descripcion", "detalle",
                                                          "nombre", "precio"))
    if columna in ("cantidad_minima", "cantidad_mayor", "unidad", "iva"):
        return not any(_con_palabra(titulo, x) for x in ("precio", "costo", "neto", "importe"))
    return True


FACTORES_IVA = (1.0, 1.105, 1.21, 1.27)
# Columnas que completan una descripción que se repite (Bazar Alfa: «Chapa sin Enlozar» con «Nº» 14,
# 16, 18…), en orden de preferencia
MEDIDAS = ("medida", "medidas", "dimension", "dimensiones", "tamano", "talle", "capacidad",
           # 20/11 (vivero: «Tierra Mejorada» | PRESENTACIÓN 5 dm³, 10 dm³, 25 dm³)
           "presentacion", "presentaciones", "envase", "contenido", "peso", "volumen",
           "variedad", "modelo", "color",
           "no", "n", "nro", "numero")


def _columna_de_texto(pares: list[tuple[str, str]], usados, muestra: list[dict]) -> str | None:
    """La columna de la descripción cuando su título no lo dice (Bazar Alfa la titula con la sección:
    «GASTRONOMICO», «FUNDICION»): la de textos más largos entre las que tienen letras en casi
    todas las filas. Ni las del comercio ni las que son casi todas números."""
    mejor, puntaje_mejor = None, 0.0
    for normal, original in pares:
        if (original in usados or original.startswith("Columna ")
                or any(_con_palabra(normal, x) for x in NO_ES_COSTO)):
            continue
        valores = [str(f.get(original) or "").strip() for f in muestra]
        valores = [v for v in valores if v]
        if len(valores) < 3:
            continue
        con_letras = [v for v in valores if any(c.isalpha() for c in v) and not _es_numero(v)]
        if len(con_letras) < len(valores) * 0.8:
            continue
        largo = sum(len(v) for v in con_letras) / len(con_letras)
        if largo < 8:
            continue  # «20 x 30», «15 div», «Si»: atributos cortos, no la descripción
        puntaje = largo * len(con_letras)
        if puntaje > puntaje_mejor:
            mejor, puntaje_mejor = original, puntaje
    return mejor


def _medida_para(descripcion: str, pares: list[tuple[str, str]], usados, muestra: list[dict]) -> str | None:
    """La columna de la medida o el número que distingue descripciones repetidas («Chapa sin Enlozar»
    14, 16, 18…). None si la descripción casi no se repite (ya trae la medida) o no hay esa columna."""
    descripciones = [str(f.get(descripcion) or "").strip() for f in muestra]
    descripciones = [d for d in descripciones if d]
    if not descripciones:
        return None
    repetidas = sum(n for n in Counter(descripciones).values() if n > 1)
    if repetidas < len(descripciones) * 0.1:
        return None
    libres = {normal: original for normal, original in pares if original not in usados}
    for nombre in MEDIDAS:
        original = libres.get(nombre)
        if original and any(str(f.get(original) or "").strip() for f in muestra):
            return original
    return None



def _valores_numericos(filas: list[dict], titulo: str) -> list[float | None]:
    from .plan import _numero

    salida = []
    for f in filas:
        texto = str(f.get(titulo) or "").strip()
        try:
            valor = _numero(texto) if texto else None
        except ValueError:
            valor = None
        salida.append(valor if valor and valor > 0 else None)
    return salida


def analizar_cuentas(titulos: list[str], filas: list[dict] | None) -> dict:
    """Columnas que son cuentas de otras (las agrega el comercio en su planilla) y la columna de
    precio con IVA de cada producto, aunque el archivo sea .xls y no se vean las fórmulas (30/10,
    Gas del Sur):

    - «derivadas»: {título: (base, factor)} si casi todas sus filas son la base × el mismo número
      («C/ Dto.» = LISTA × 0,75; «PÚBLICO» = NETO × 1,5).
    - «con_iva»: (título, base, factor) si la columna es la base × un factor común × el IVA de
      cada fila (NETO = LISTA × 0,75 × 1,105 o × 1,21): sirve para sacar el IVA de cada producto.
    """
    muestra = [f for f in (filas or [])[:400]]
    numericas = {}
    for t in titulos:
        if not t:
            continue
        valores = _valores_numericos(muestra, t)
        if sum(1 for v in valores if v) >= 10:
            numericas[t] = valores
    orden = {t: i for i, t in enumerate(titulos)}
    derivadas: dict[str, tuple[str, float]] = {}
    for b, vb in numericas.items():
        for a, va in numericas.items():
            # La cuenta es la de la derecha (la planilla agrega sus columnas al lado de las del proveedor);
            # puede ser una cuenta de otra cuenta (Chi: DÓLAR = precio × 1.550 y descuento = DÓLAR × 0,567)
            if a == b or orden[a] > orden[b]:
                continue
            # 4 cifras significativas: sirve igual para × 0,75 que para × 1.550 (un dólar)
            cocientes = [float(f"{y / x:.4g}") for x, y in zip(va, vb, strict=True) if x and y]
            if len(cocientes) < 10:
                continue
            factor, veces = max(((c, cocientes.count(c)) for c in set(cocientes)), key=lambda par: par[1])
            # ÷ IVA no es una cuenta de la planilla: es el precio sin IVA de un archivo que trae primero
            # el precio con IVA (Mu: «IVA» y después «PRECIOS» = IVA ÷ 1,21)
            sin_iva = any(abs(factor * k - 1) < 0.001 for k in FACTORES_IVA[1:])
            if veces >= 0.9 * len(cocientes) and abs(factor - 1) > 1e-6 and factor > 1e-4 and not sin_iva:
                derivadas[b] = (a, factor)
                break
    con_iva = None
    for b, vb in numericas.items():
        if b in derivadas or con_iva:
            continue
        for a, va in numericas.items():
            if a == b or a in derivadas or orden[a] > orden[b]:
                continue
            cocientes = [y / x for x, y in zip(va, vb, strict=True) if x and y]
            base_factor = factor_comun_iva(cocientes) if len(cocientes) >= 10 else None
            if base_factor is not None:
                con_iva = (b, a, base_factor)
                break
    return {"derivadas": derivadas, "con_iva": con_iva}


def _iva_de(cociente: float, base_factor: float) -> float | None:
    return next((k for k in FACTORES_IVA if abs(cociente / base_factor - k) < 0.003), None)


def factor_comun_iva(cocientes: list[float]) -> float | None:
    """Si los cocientes «precio con IVA ÷ precio de lista» son un factor común × el IVA de cada fila
    (1; 1,105; 1,21; 1,27, con al menos dos IVA distintos), ese factor común; si no, None."""
    # El factor común: sale de los cocientes que más se repiten, divididos por cada IVA posible
    frecuentes = Counter(round(c, 3) for c in cocientes).most_common(3)
    # Tiene que ser un descuento (o nada): la planilla no sube la lista antes del IVA
    candidatos = sorted({round(c / k, 4) for c, _n in frecuentes for k in FACTORES_IVA
                         if 0.05 < c / k <= 1.0001})
    for base_factor in candidatos:
        usados = Counter(k for k in (_iva_de(c, base_factor) for c in cocientes) if k is not None)
        distintos = [k for k, n in usados.items() if n >= 0.05 * len(cocientes)]
        con_iva = len(distintos) >= 2 and any(k > 1 for k in distintos)
        if sum(usados.values()) >= 0.9 * len(cocientes) and con_iva:
            # Afinado con todas las filas (el candidato sale de cocientes redondeados)
            exactos = sorted(c / k for c in cocientes if (k := _iva_de(c, base_factor)) is not None)
            return round(exactos[len(exactos) // 2], 4)
    return None


def descuento_detectado(analisis: dict, costo: str | None = None) -> float | None:
    """El descuento que la planilla aplica a la columna del costo (con IVA: NETO = LISTA × 0,75 ×
    IVA → 25 %; o una derivada «C/ Dto.» = LISTA × 0,75). None si no hay o no es redondo. Las cuentas
    sobre otras cuentas (LUMINA: × 0,76 sobre el precio con IVA) no son un descuento de la lista."""
    factores = []
    if analisis.get("con_iva") and analisis["con_iva"][1] == (costo or analisis["con_iva"][1]):
        factores.append(analisis["con_iva"][2])
    factores += [f for _b, (a, f) in analisis.get("derivadas", {}).items()
                 if f < 1 and (costo is None or a == costo)]
    for factor in factores:
        porcentaje = round((1 - factor) * 100, 2)
        if 0 < porcentaje < 90 and abs(porcentaje * 4 - round(porcentaje * 4)) < 0.01:  # 25, 12,5…
            return porcentaje
    return None


def sugerir_mapeo(titulos: list[str], filas: list[dict] | None = None) -> dict[str, str]:
    """Propone qué título del archivo corresponde a cada columna de la planilla modelo.

    Por cada sinónimo (en orden de preferencia), el título igual y si no, uno que lo contenga
    («Precio Unit. sin IVA»). Nunca propone como costo una columna del comercio
    (público, margen, redondeo, con IVA…). Con `filas` (las del archivo) descarta columnas
    vacías y, para precios, las que no traen números."""
    # Todos los títulos, aunque dos se escriban igual («IVA» de LUMINA e «iva» de Daniel)
    pares = [(_normalizar_titulo(t), t) for t in titulos if t]
    normalizados = dict(pares)
    muestra = (filas or [])[:300]
    analisis = analizar_cuentas(titulos, filas) if filas else {"derivadas": {}, "con_iva": None}
    no_costo = set(analisis["derivadas"]) | ({analisis["con_iva"][0]} if analisis["con_iva"] else set())

    def sirve(columna: str, original: str) -> bool:
        if not muestra:
            return True
        valores = [str(f.get(original) or "").strip() for f in muestra]
        valores = [v for v in valores if v]
        if not valores:
            return False
        if columna in ("costo", "costo_mayor") and original in no_costo:
            return False  # una cuenta de la planilla o el precio con IVA: no es el costo del proveedor
        if columna == "iva":  # alícuotas (21, 10,5, 0,21), no el precio con IVA (Epsilon: «IVA» = $ 1.115)
            return sum(1 for v in valores if _es_alicuota(v)) >= len(valores) * 0.9
        if columna in ("costo", "costo_mayor"):
            return sum(1 for v in valores if _es_numero(v)) >= len(valores) / 2
        if columna == "stock":  # «SI» / «NO», o cantidades: textos cortos
            return sum(1 for v in valores if len(v) <= 12) >= len(valores) * 0.9
        if columna == "promocion":  # texto con «%» (no una columna de números ni de notas)
            return sum(1 for v in valores if "%" in v) >= len(valores) / 2
        if columna == "descripcion_proveedor":
            # «desc» puede ser «descuento» (LUMINA): una descripción no es casi toda números
            return sum(1 for v in valores if _es_numero(v)) < len(valores) / 2
        return True

    mapeo: dict[str, str] = {}
    usados: set[str] = set()
    if analisis["con_iva"]:
        # Precio con el IVA de cada producto (Gas del Sur: NETO): el costo es su base (LISTA) y esa columna
        # da el IVA de cada fila
        con_iva, base, _factor = analisis["con_iva"]
        mapeo.update({"costo": base, "precio_con_iva": con_iva})
        usados.update({base, con_iva})
    for columna, sinonimos in SINONIMOS.items():
        if columna in mapeo:
            continue
        elegido = None
        for sinonimo in sinonimos:  # en orden de preferencia: «neto» antes que «precio de lista»
            for exacto in (True, False):
                if not exacto and len(sinonimo) < 5:
                    continue  # «cod», «desc», «min»: solo como título entero
                for normal, original in pares:
                    coincide = normal == sinonimo if exacto else _con_palabra(normal, sinonimo)
                    if (coincide and original not in usados and _parece(columna, normal)
                            and sirve(columna, original)):
                        elegido = original
                        break
                if elegido:
                    break
            if elegido:
                break
        if elegido:
            mapeo[columna] = elegido
            usados.add(elegido)
    # Una sola columna de precio llamada «mayorista»: es el costo (no hay dos precios)
    if "costo" not in mapeo and "costo_mayor" in mapeo and "cantidad_mayor" not in mapeo:
        mapeo["costo"] = mapeo.pop("costo_mayor")
    # Precio por bulto con «unidades por bulto»: esa cantidad es la del precio por mayor (se puede
    # comprar suelto a un precio y por bulto a otro), no un bulto obligatorio
    if "costo_mayor" in mapeo and "cantidad_mayor" not in mapeo and "bulto" in mapeo:
        mapeo["cantidad_mayor"] = mapeo.pop("bulto")
    # Descripción con un título que no lo dice (Bazar Alfa: «GASTRONOMICO»): la columna de textos largos
    if "descripcion_proveedor" not in mapeo and muestra:
        texto = _columna_de_texto(pares, usados, muestra)
        if texto:
            mapeo["descripcion_proveedor"] = texto
            usados.add(texto)
    # Descripción repetida con la medida aparte (Bazar Alfa: «Chapa sin Enlozar» | Nº 14): se suman
    if "descripcion_proveedor" in mapeo and muestra:
        medida = _medida_para(mapeo["descripcion_proveedor"], pares, usados, muestra)
        if medida:
            mapeo["descripcion_proveedor"] = f"{mapeo['descripcion_proveedor']}{SUMA}{medida}"
            usados.add(medida)
    # «Detalle» + «Descripción»: la lista parte la descripción en dos (FC: «ABRAZADERA» | «10-16 mm»)
    if "descripcion_proveedor" in mapeo:
        libres = {n: t for n, t in normalizados.items() if t not in mapeo.values()}
        detalle = libres.get("detalle")
        if detalle and detalle != mapeo["descripcion_proveedor"]:
            mapeo["descripcion_proveedor"] = f"{detalle}{SUMA}{mapeo['descripcion_proveedor']}"
    # Una columna sin título de IVA pero con la alícuota en cada fila (FC: «Precio con I.V.A» trae
    # 21 o 10,5 y el precio va al lado): casi todos sus valores son 10,5, 21 o 27
    if "iva" not in mapeo and muestra:
        for original in titulos:
            if not original or original in mapeo.values():
                continue
            valores = [str(f.get(original) or "").strip() for f in muestra]
            valores = [v for v in valores if v]
            if len(valores) >= 5 and sum(1 for v in valores if _es_alicuota(v)) >= len(valores) * 0.95:
                mapeo["iva"] = original
                break
    return mapeo


def _es_alicuota(texto: str) -> bool:
    """10,5, 21 o 27 (con o sin «%»), o la fracción de una celda con formato de porcentaje (0,105)."""
    from .plan import _numero

    try:
        valor = _numero(texto.replace("%", ""))
    except ValueError:
        return False
    return round(valor * 100 if 0 < valor < 1 else valor, 4) in (10.5, 21.0, 27.0)


def redetectar(tabla: list[list[str]]) -> tuple[int, dict[str, str]] | None:
    """Vuelve a detectar fila de títulos y columnas (el proveedor cambió el formato).

    Devuelve (fila, mapeo) solo si encuentra el costo y el código o la descripción; si no,
    None (lo tiene que resolver una persona)."""
    fila = encontrar_encabezado(tabla)
    titulos = titulos_de(tabla, fila)
    mapeo = sugerir_mapeo(titulos, filas_con_titulos(tabla, fila)) if titulos else {}
    if "costo" in mapeo and ("codigo_proveedor" in mapeo or "descripcion_proveedor" in mapeo):
        return fila, mapeo
    return None


def filas_con_titulos(tabla: list[list[str]], fila_encabezado: int = 1) -> list[dict]:
    """Las filas de datos como {título: valor}. La fila de títulos repetida más abajo (listas
    hechas de varias partes pegadas) no es un producto: se saltea."""
    if len(tabla) < fila_encabezado:
        raise ValueError(f"el archivo tiene {len(tabla)} filas y los títulos van en la fila "
                         f"{fila_encabezado}")
    tabla = apilar_lado_a_lado(tabla, fila_encabezado)
    encabezados = titulos_de(tabla, fila_encabezado)
    titulo = [_normalizar_titulo(t) for t in tabla[fila_encabezado - 1]]
    salida = []
    for fila in tabla[fila_encabezado:]:
        if not any(str(c).strip() for c in fila):
            continue
        normal = [_normalizar_titulo(c) for c in fila]
        iguales = [i for i, t in enumerate(titulo) if t and i < len(normal) and normal[i] == t]
        con_titulo = sum(1 for t in titulo if t)
        if len(iguales) >= min(2, con_titulo) and len(iguales) * 2 > con_titulo:
            continue  # los títulos otra vez (aunque tenga algo más al costado, como el número de página)
        if _es_titulo_repetido(normal):
            continue
        datos = dict(zip(encabezados, fila, strict=False))
        datos[POSICIONES] = list(fila)  # para elegir una columna por su letra (ver valor_de)
        salida.append(datos)
    return salida


POSICIONES = "__fila__"  # en cada fila leída: las celdas en orden (no es un título del archivo)
_POR_LETRA = re.compile(r"^Columna ([A-Z]{1,3})$")


def _indice_de_letra(letras: str) -> int:
    indice = 0
    for letra in letras:
        indice = indice * 26 + ord(letra) - 64
    return indice - 1


def valor_de(fila: dict, titulo: str):
    """La celda de ese título; «Columna B» también por posición (listas que cambian el título
    de una columna cada mes, como la descripción de Nortex). None si no está."""
    if titulo in fila and titulo != POSICIONES:
        return fila[titulo]
    letra = _POR_LETRA.match(titulo or "")
    celdas = fila.get(POSICIONES)
    if letra and celdas is not None:
        i = _indice_de_letra(letra.group(1))
        return celdas[i] if i < len(celdas) else ""
    return None


def _es_titulo_repetido(normal: list[str]) -> bool:
    """Una fila con dos o más títulos conocidos y ningún número (otra fila de títulos)."""
    escritos = [c for c in normal if c]
    return (sum(1 for c in escritos if c in _TITULOS_CONOCIDOS) >= 2
            and not any(any(ch.isdigit() for ch in c) for c in escritos))


def leer_filas(ruta, hoja=None, fila_encabezado: int = 1) -> list[dict]:
    """Compatibilidad: lee un archivo del disco y devuelve sus filas con títulos."""
    from pathlib import Path

    ruta = Path(ruta)
    return filas_con_titulos(leer_tabla(ruta.read_bytes(), ruta.name, hoja), fila_encabezado)


class FormatoCambiado(ValueError):
    """El archivo ya no tiene las columnas del mapeo: el proveedor cambió el formato."""


def factor_de_ajustes(ajustes: dict | None) -> float:
    """Compatibilidad: cuánto se multiplica el precio de la lista para tener el costo, con
    los ajustes de toda la lista (sin reglas por familia ni columnas de la fila)."""
    a = normalizar_ajustes(ajustes)
    if a["moneda"] == "usd" and not _numero_o_cero(a["cotizacion"]):
        a["moneda"] = "ars"
    return costo_desde_lista(1.0, a)[0]


def _numero_o_cero(texto) -> float:
    from .plan import _numero

    return texto if isinstance(texto, (int, float)) else _numero(texto)


def _calcular(nueva: dict, ajustes: dict, familia: str | None) -> None:
    """Pasa el precio de la lista (y el precio por mayor) al costo con los ajustes. Guarda en
    la fila el precio original («precio_lista») y la cuenta hecha («calculo»)."""
    from .plan import _numero

    texto_precio = nueva["costo"]
    descuento, iva = nueva.pop("descuento", ""), nueva.pop("iva", "")
    promocion = str(nueva.pop("promocion", "") or "").strip()
    # Lo que trae la fila queda guardado para volver a calcular (ejemplo en la pantalla de la lista)
    if descuento:
        nueva["descuento_fila"] = descuento
    if iva:
        nueva["iva_fila"] = iva
    promo = leer_promocion(promocion)
    if promocion:
        nueva["promocion"] = promocion  # el texto tal cual: se muestra como aviso en la fila
    con_promo = promo["unidad"] or promo["escalones"] or promo["neto"]
    # Descuento por pack completo (Nortex: «PACK 5% descuento» y «(pack x 12)» en la descripción)
    pct_pack = _numero_o_cero(ajustes["pack"] or 0)
    pack = cantidad_de_pack(nueva["descripcion_proveedor"]) if pct_pack and not nueva["costo_mayor"] else 0
    calcular = hay_ajustes(ajustes)  # en una lista mixta, siempre (el precio trae el «$» delante)
    if ajustes["moneda"] == "mixta" and texto_precio:
        # Pesos y dólares mezclados: «$ 214,2» es pesos; sin «$» (o «US$»), dólares
        nueva["moneda_fila"] = "ars" if texto_precio.lstrip().startswith("$") else "usd"
        ajustes = de_la_fila(ajustes, nueva["moneda_fila"])
    if not texto_precio or not (calcular or descuentos_de_celda(descuento) or con_promo or pack):
        return
    try:
        precio = _numero(texto_precio)
    except ValueError:
        return  # lo marca después el plan («no es un número»)
    texto = " ".join(filter(None, [familia, nueva["descripcion_proveedor"]]))
    costo, calculo = costo_desde_lista(precio, ajustes, descuento, iva, texto, nueva["codigo_proveedor"],
                                       promocion)
    nueva["precio_lista"] = texto_precio
    nueva["costo"] = f"{costo:.4f}"  # con punto y 4 decimales: _numero no lo confunde con miles
    if promo["escalones"] and not nueva["costo_mayor"]:
        # Promoción por cantidad («10% DTO. X 2 ROLLOS»): el precio por mayor desde esa cantidad
        # (Compras lo usa al pedir esa cantidad o más). Un solo escalón: el primero.
        cantidad, pct = promo["escalones"][0]
        mayor = costo * (1 - pct / 100)
        nueva["costo_mayor"] = f"{mayor:.2f}"
        nueva["cantidad_mayor"] = f"{cantidad:g}"
        calculo += f" · por mayor desde {cantidad:g}: −{pct:g} % (promoción) → $ {_pesos(mayor)}"
        precio = 0  # el precio por mayor ya está calculado sobre el costo
    elif pack:
        mayor = costo * (1 - pct_pack / 100)
        nueva["costo_mayor"] = f"{mayor:.2f}"
        nueva["cantidad_mayor"] = f"{pack:g}"
        calculo += f" · por mayor desde {pack:g}: −{pct_pack:g} % (pack completo) → $ {_pesos(mayor)}"
        precio = 0
    nueva["calculo"] = calculo
    if nueva["costo_mayor"] and precio:
        try:
            # Con 2 decimales: así lo guarda Odoo (si no, la verificación ve una diferencia)
            nueva["costo_mayor"] = f"{_numero(nueva['costo_mayor']) * costo / precio:.2f}"
        except ValueError:
            pass


# Lo que dice la columna del código en una fila de subtítulos, no un código de producto
TITULOS_DE_CODIGO = {"codigo", "cod", "codigos", "articulo", "art", "sku", "referencia", "ref"}


def _repite_titulos(fila: dict, titulos: set[str]) -> bool:
    """La fila repite dos o más títulos del archivo («U/M», «PUBLICO», «CAMBIOS»): es otra fila
    de títulos, aunque en la columna del precio diga otra cosa («COMERCIO»)."""
    return sum(1 for k, v in fila.items() if k != POSICIONES and isinstance(v, str) and not _es_numero(v)
               and _normalizar_titulo(v) in titulos) >= 2


SIN_STOCK = ("no", "n", "sin stock", "sin", "agotado", "no hay", "0", "no disponible", "falta", "s/stock")


def _sin_stock(texto) -> bool:
    """La celda de stock dice que el proveedor no lo tiene («NO», «Agotado», 0)."""
    limpio = " ".join(str(texto or "").lower().replace(".", " ").split())
    return limpio in SIN_STOCK


# En la columna del precio, el proveedor dice que ya no lo fabrica o vende (20/11, Xi: «DISC.»):
# la fila no se carga (si lo teníamos, sale como baja). «Sin stock» o «Consultar» siguen a revisar.
NO_LO_VENDE = ("disc", "discontinuado", "discontinuada", "discontinuados", "discontinuadas", "descontinuado",
               "discont", "fuera de linea", "fuera de línea", "no se fabrica")


def _no_lo_vende(texto: str) -> bool:
    limpio = " ".join(str(texto or "").lower().replace(".", " ").split())
    return limpio in NO_LO_VENDE


def _sin_precio(texto: str) -> bool:
    """«SIN STOCK», «Consultar», «#VALUE!», «-», o un 0: la lista no trae precio para esa fila."""
    from .plan import _numero

    limpio = " ".join(str(texto or "").lower().split())
    if limpio in SIN_PRECIO or "consult" in limpio or "cotizar" in limpio:
        return True
    try:
        return limpio != "" and _numero(limpio) <= 0
    except ValueError:
        return False


def _es_titulo_de_precio(texto: str) -> bool:
    """«PRECIO», «Precio p/Metro», «2025-04-10 00:00:00» (fecha de la lista) en la columna del
    precio: es una fila de títulos de una sección, no un producto."""
    normal = _normalizar_titulo(texto)
    if not normal or _es_numero(texto):
        return False
    if re.fullmatch(r"\d{4} \d{2} \d{2}( \d{2} \d{2} \d{2})?", normal):
        return True
    return normal.split(" ")[0] in ("precio", "precios", "costo", "importe", "lista", "neto")


# El envase al final de la descripción: «… 100u», «… x 12 UN.», «… 500 unidades»
_ENVASE_AL_FINAL = re.compile(r"(?:\bx\s*)?\b(\d+)\s*(?:u|un|und|unid|unidades|uds)\.?\s*$", re.I)
# Un punto suelto al final, después de espacios de relleno («Baguetera 40 x 60 lisa        .»)
_RELLENO_FINAL = re.compile(r"\s+\.$")
_TITULOS_CONOCIDOS = {sin for sinonimos in SINONIMOS.values() for sin in sinonimos}


def _familia(fila: dict) -> str | None:
    """El título de una familia o rubro («ABRAZADERAS», «LAMPARAS Y TUBOS»): una sola celda con
    texto (los ceros de fórmulas vacías no cuentan). None si la fila es otra cosa."""
    escritos = [str(v).strip() for k, v in fila.items()
                if k != POSICIONES and str(v or "").strip() and not _sin_precio(v)]
    if len(escritos) != 1:
        return None
    titulo = " ".join(escritos[0].split())  # en dos renglones: «CARRO DE TRANSPORTE\nC/ PINTURA EPOXI»
    return titulo if _puede_ser_familia(titulo) else None


# Dos oraciones («… simple uso. Funcionamiento continuo…»): la ficha técnica, no un título. Las
# abreviaturas en mayúsculas («ART. ESPECIAL», «CAB. BOTON»: FC) no cuentan.
_FRASE = re.compile(r"[a-záéíóúñ]{3,}\.\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]")
# «Velita 100 unidades por caja / Gota…», «20 uni. x caja»: cómo viene embalado, no una familia
_NOTA_DE_EMBALAJE = re.compile(r"\bunid|\buni\.|\bx caja|por caja|por bolsa", re.I)


def _puede_ser_familia(texto: str) -> bool:
    """¿Este texto suelto puede ser el título de una familia? No lo son «5 unidades por caja»,
    «Link: …», «C/U $2800» (nota del comercio), «LISTA DE PRECIOS…», «PRECIOS NETOS…», las notas
    largas, las frases de una ficha técnica
    («Fácil programación y simple uso. …»: LUMINA) ni un título de la tabla que se repite solo
    («DESCRIPCIÓN», «CODIGO»: LTX)."""
    return bool(texto[:1].isalpha() and ":" not in texto and "$" not in texto and len(texto) <= 80
                and not _FRASE.search(texto)
                and not _NOTA_DE_EMBALAJE.search(texto)
                and not _normalizar_titulo(texto).startswith(("lista de precio", "precios ", "precio "))
                and _normalizar_titulo(texto) not in _TITULOS_CONOCIDOS)


def _descripcion_armada(fila: dict, columnas: dict, familia: str | None, arriba: dict | None = None) -> str:
    """Listas sin columna de descripción (LUMINA: SKU, Potencia, Luz, Rosca…, con la familia en una
    fila aparte): la familia y los textos de las columnas que no se usan para otra cosa ni son
    del comercio («LÁMPARA GLOBO 9W Fría E27»). Los números sueltos y las fichas técnicas (texto
    de varios renglones) no se suman.

    `arriba`: lo último escrito en cada columna. Una celda vacía toma ese valor: en LUMINA son celdas
    combinadas («3120 6W 3000K» y debajo «3120N 4000K» es también de 6W)."""
    usados = {t for titulos in columnas.values() for t in titulos}
    partes = []
    for k, v in fila.items():
        if (k == POSICIONES or k in usados or k.startswith("Columna ")
                or any(_con_palabra(_normalizar_titulo(k), x) for x in NO_ES_COSTO)
                or _normalizar_titulo(k).split(" ")[0] in ("iva", "desc", "descuento")):
            continue  # ni las del comercio ni el IVA o el descuento (LUMINA: «iva» de Daniel dice «Stock»)
        texto = str(v or "").strip()
        if arriba is not None:
            if texto:
                arriba[k] = texto
            else:
                texto = arriba.get(k, "")
        if texto and not _es_numero(texto) and "\n" not in texto:
            partes.append(texto)
    return " ".join(([familia] if familia else []) + partes)


# Títulos de una columna que es la familia, cuando la descripción se arma sumándola («Detalle +
# Descripción del producto»: FC)
_TITULOS_DE_FAMILIA = ("detalle", "familia", "rubro", "linea", "categoria", "grupo", "seccion")


def _familia_de_columna(fila: dict, columnas: dict) -> str | None:
    """La familia de la fila cuando la descripción suma una columna de familia al principio (FC:
    «Detalle» = «ABRAZADERA CIERRE RAPIDO»). None si la descripción es una sola columna o la primera
    no es de familia («Descripción + Medida»)."""
    titulos = columnas.get("descripcion_proveedor") or []
    if len(titulos) < 2 or not _normalizar_titulo(titulos[0]).startswith(_TITULOS_DE_FAMILIA):
        return None
    return " ".join(str(valor_de(fila, titulos[0]) or "").split()) or None


def _sumar_familia(familia: str | None, titulo: str, seguidos: bool) -> str:
    """La familia después de un título. Un título en mayúsculas seguido de un subtítulo que no lo
    está, sin productos en medio, se juntan (LUMINA: «TEMPORIZADORES» + «Mecánicos y Digitales»).
    Si no, manda el último (dos títulos en mayúsculas seguidos son una sección vacía y la que
    sigue: FC «AROMATIZANTE AMBIENTE», «ART. ESPECIAL»)."""
    if (seguidos and familia and familia.isupper() and not titulo.isupper()
            and _normalizar_titulo(titulo) not in _normalizar_titulo(familia)):
        junta = f"{familia} {titulo}"
        if len(junta) <= 80:
            return junta
    return titulo


def _distinguir_repetidas(filas: list[dict]) -> None:
    """Descripciones armadas iguales (veladores de LUMINA que solo cambian en la foto): se les suma
    el código del proveedor, para que no queden dos productos con el mismo nombre."""
    cuantas = Counter(f["descripcion_proveedor"] for f in filas)
    for fila in filas:
        if cuantas[fila["descripcion_proveedor"]] > 1 and fila["codigo_proveedor"]:
            fila["descripcion_proveedor"] = f"{fila['descripcion_proveedor']} {fila['codigo_proveedor']}"


def _ivas_por_fila(filas: list[dict], columnas: dict) -> dict[int, str]:
    """{n.º de fila: IVA} sacado de la columna con IVA del comercio (Gas del Sur: NETO = LISTA × 0,75 × IVA):
    «21», «10,5», «27» o «» si esa fila no suma IVA. Vacío si la columna no es esa cuenta."""
    from .plan import _numero

    pares = {}
    for i, fila in enumerate(filas):
        try:
            base = _numero(str(valor_de(fila, columnas["costo"][0]) or "").strip() or "0")
            con = _numero(str(valor_de(fila, columnas["precio_con_iva"][0]) or "").strip() or "0")
        except (ValueError, KeyError):
            continue
        if base > 0 and con > 0:
            pares[i] = con / base
    base_factor = factor_comun_iva(list(pares.values())) if len(pares) >= 10 else None
    if base_factor is None:
        return {}
    salida = {}
    for i, cociente in pares.items():
        k = _iva_de(cociente, base_factor)
        if k is not None:
            salida[i] = f"{(k - 1) * 100:g}".replace(".", ",") if k > 1 else ""
    return salida


def convertir(mapeo: dict, filas: list[dict]) -> list[dict]:
    """Filas del proveedor → filas de la planilla modelo.

    `mapeo`: {"proveedor": nombre, "columnas": {columna_modelo: título}, "valores_fijos": {...}}

    Un título puede juntar varias columnas con « + » (p. ej. «Detalle + Descripción»):
    se unen los textos con un espacio, para listas que parten la descripción en dos (salvo
    que el archivo tenga una columna que se llame así, con el « + » en el título).

    Opcional en el mapeo: `envase_en_descripcion` (el precio es por el envase que dice el final de
    la descripción: «… 100u», Mu), `familia_en_descripcion` (el título de la familia que va en una
    fila aparte se antepone a la descripción) y `ajustes` (del precio de la lista al costo:
    ver catalogo/costo.py). Las columnas «descuento» e «iva» del mapeo se usan en esa cuenta.
    Una fila sin precio («SIN STOCK», 0, «#VALUE!») queda con el costo vacío: va a revisar.
    """
    existentes = set(filas[0]) - {POSICIONES} if filas else set()
    columnas = {destino: [t.strip() for t in origen.split(SUMA)]
                if SUMA in origen and origen not in existentes else [origen]
                for destino, origen in mapeo.get("columnas", {}).items()}
    fijos = mapeo.get("valores_fijos", {})
    ajustes = normalizar_ajustes(mapeo.get("ajustes"))
    con_familia = bool(mapeo.get("familia_en_descripcion"))
    envase_en_descripcion = bool(mapeo.get("envase_en_descripcion"))
    familia = None
    con_iva = _ivas_por_fila(filas, columnas) if "precio_con_iva" in columnas else {}
    armadas, arriba, familia_de_arriba = [], {}, None  # descripciones armadas (listas sin columna)
    titulos_seguidos = False  # la fila anterior fue un título de familia (sin productos en medio)
    titulos_archivo = {_normalizar_titulo(t) for t in existentes if not t.startswith("Columna ")} - {""}
    faltan = [t for titulos in columnas.values() for t in titulos if filas and valor_de(filas[0], t) is None]
    if faltan:
        raise FormatoCambiado(
            f"El archivo no tiene las columnas {faltan}: ¿cambió el formato del proveedor?"
        )
    salida = []
    for i, fila in enumerate(filas):
        nueva = {c: "" for c in COLUMNAS}
        nueva["proveedor"] = mapeo["proveedor"]
        nueva.update({k: str(v) for k, v in fijos.items() if v not in (None, "")})
        for destino, titulos in columnas.items():
            nueva[destino] = " ".join(v for v in (str(valor_de(fila, t) or "").strip() for t in titulos) if v)
        if "descripcion_proveedor" in columnas:
            # En varios renglones o con espacios de relleno y un punto al final («… lisa       .»: Bazar Alfa)
            partes = (_RELLENO_FINAL.sub("", " ".join(str(valor_de(fila, t) or "").split()))
                      for t in columnas["descripcion_proveedor"])
            nueva["descripcion_proveedor"] = " ".join(v for v in partes if v)
        con_iva_fila = nueva.pop("precio_con_iva", "")
        if con_iva_fila and i in con_iva and not nueva.get("iva"):
            if con_iva[i]:
                nueva["iva"] = con_iva[i]
            else:
                nueva["aviso_iva"] = "IVA a confirmar: la columna con IVA de la planilla no le suma IVA"
        if _repite_titulos(fila, titulos_archivo):
            continue  # otra fila de títulos a mitad de la lista (Nortex, al empezar cada marca)
        if _sin_stock(nueva.pop("stock", "")) or _no_lo_vende(nueva["costo"]):
            continue  # el proveedor no lo tiene: no se carga (si vuelve a tenerlo, aparece en otra lista)
        for precio in ("costo", "costo_mayor"):
            if _sin_precio(nueva[precio]):
                if precio == "costo" and nueva[precio]:
                    # «SIN STOCK», «Consultar», 0: se guarda para mostrarlo al corregir la fila
                    nueva["precio_original"] = nueva[precio]
                nueva[precio] = ""
        if nueva["codigo_barras"] and sum(ch.isdigit() for ch in nueva["codigo_barras"]) < 6:
            # «STOCK», «S/C» o una medida de una fila con las columnas corridas («16cm»: Bazar Alfa)
            nueva["codigo_barras"] = ""
        codigo = nueva["codigo_proveedor"]
        if "\n" in codigo or len(codigo) > 30 or ":" in codigo:
            # una nota («Link:», la ficha técnica: «Vida útil: 15.000 horas» en LUMINA), no un código
            nueva["codigo_proveedor"] = ""
            if not nueva["costo"]:
                # …o el título largo de una sección en la columna del código (LTX: «PVC - CAÑOS - …»)
                if _familia(fila):
                    familia = _sumar_familia(familia, _familia(fila), titulos_seguidos)
                    titulos_seguidos = True
                continue
        if _normalizar_titulo(codigo) in TITULOS_DE_CODIGO:
            # Subtítulo de una sección con sus propios títulos («MOLDE PAN | U / B | CÓDIGO», Aluminio Phi)
            if _puede_ser_familia(nueva["descripcion_proveedor"]):
                familia = nueva["descripcion_proveedor"]
            continue
        if _es_titulo_de_precio(nueva["costo"]):
            # Subtítulo de una sección («MACETA CUADRADA | PRECIO», «DESCRIPCIÓN | Precio p/Metro»)
            if (nueva["descripcion_proveedor"] and not nueva["codigo_proveedor"]
                    and _puede_ser_familia(nueva["descripcion_proveedor"])):  # no «DESCRIPCIÓN» (LTX)
                familia = nueva["descripcion_proveedor"]
            continue
        if nueva["descripcion_proveedor"].lower().startswith(("http://", "https://")) and not nueva["costo"]:
            continue
        titulo_familia = _familia(fila) if not nueva["costo"] else None
        if titulo_familia:
            familia = _sumar_familia(familia, titulo_familia, titulos_seguidos)
            titulos_seguidos = True
            continue  # título de una familia o rubro («ABRAZADERAS», «ELECTRICIDAD»): no es un producto
        if (con_familia and "descripcion_proveedor" in columnas and not nueva["codigo_proveedor"]
                and not nueva["costo"] and _puede_ser_familia(nueva["descripcion_proveedor"])):
            # Título de familia con una marca en otra columna (Bazar Alfa: «NUEVO» | «BANDEJA HAMBURGUESERA»)
            familia = _sumar_familia(familia, nueva["descripcion_proveedor"], titulos_seguidos)
            titulos_seguidos = True
            continue
        if not nueva["codigo_proveedor"] and not nueva["descripcion_proveedor"]:
            continue  # filas de títulos o separadores de la lista
        if ("descripcion_proveedor" in columnas and nueva["codigo_proveedor"]
                and not nueva["descripcion_proveedor"] and not nueva["costo"]):
            if not _puede_ser_familia(nueva["codigo_proveedor"]):
                continue  # un 0 suelto (Clorosur), «CODIGO» o «100 unidades por caja» (LTX)
            # Título de familia en la columna del código, con la marca al lado (Tau: «Adhesivo de
            # contacto | SUPRABOND»): sin descripción ni precio no es un producto que se pueda cargar
            familia = _sumar_familia(familia, nueva["codigo_proveedor"], titulos_seguidos)
            titulos_seguidos = True
            continue
        if "costo" in columnas and not nueva["codigo_proveedor"] and not nueva["costo"]:
            continue  # nota o separador sin código ni precio
        if not nueva["descripcion_proveedor"]:
            # Sin columna de descripción, o vacía en esta fila (la descripción va en la familia).
            # Sin columna, las celdas vacías valen lo de arriba (combinadas) y, si no hay familia,
            # el nombre empieza con el de la parte de la lista («Lámparas 6W 3000K E27»).
            sin_columna = "descripcion_proveedor" not in columnas
            if familia != familia_de_arriba:
                arriba, familia_de_arriba = {}, familia
            nueva["descripcion_proveedor"] = _descripcion_armada(
                fila, columnas, familia or (mapeo.get("parte") if sin_columna else None),
                arriba if sin_columna else None)
            if sin_columna:
                armadas.append(nueva)
        elif con_familia and familia:
            # «LINEA DENISE» + «DENISE 15 cm.» = «DENISE 15 cm.» (no se repite); «LINEA» no suma (20/11)
            nombre_familia = re.sub(r"^l[ií]nea\s+", "", familia, flags=re.I).strip() or familia
            ya_la_dice = _normalizar_titulo(nueva["descripcion_proveedor"]).startswith(
                _normalizar_titulo(nombre_familia))
            if not ya_la_dice:
                nueva["descripcion_proveedor"] = f"{nombre_familia} {nueva['descripcion_proveedor']}".strip()
        if envase_en_descripcion and nueva.get("unidad", "u").strip().lower() in ("", "u"):
            # «ABRAZADERA 12MM 12-22MM 100u» (Mu): el precio es por ese envase; el plan lo guarda
            # por unidad, con esa compra mínima (como la unidad «100 u.» de otras listas)
            envase = _ENVASE_AL_FINAL.search(nueva["descripcion_proveedor"])
            if envase and int(envase.group(1)) > 1:
                nueva["unidad"] = f"{envase.group(1)} u."
        _calcular(nueva, ajustes, familia)
        # La familia de la fila (título de arriba o columna de familia): para elegirla en «Descuentos
        # por familia» y contar a cuántas filas les toca (06/11)
        familia_fila = familia or _familia_de_columna(fila, columnas)
        if familia_fila:
            nueva["familia"] = familia_fila
        nueva.pop("descuento", None)
        nueva.pop("iva", None)
        salida.append(nueva)
        titulos_seguidos = False
    _distinguir_repetidas(armadas)
    _marcar_precios_simbolicos([f for f in salida if (f.get("moneda_fila") or ajustes["moneda"]) == "ars"])
    if ajustes["moneda"] == "usd":
        _marcar_precios_en_pesos(salida)
    elif ajustes["moneda"] == "mixta":
        _marcar_precios_en_pesos([f for f in salida if f.get("moneda_fila") == "usd"])
        _marcar_precios_en_dolares([f for f in salida if f.get("moneda_fila") == "ars"])
    return salida


def _marcar_precios_simbolicos(salida: list[dict]) -> None:
    """Marca para corregir los precios en pesos por debajo de $ 1 (FC: «TUBO EXHIBIDOR VACIO» a
    $ 0,02; Nortex: «LAPIZ DE WIDIA» a $ 0,01): son de regalo o un precio puesto para que la
    fila no quede vacía, y como costo darían un precio de venta de centavos."""
    for i, precio in _precios(salida).items():
        if precio < PRECIO_SIMBOLICO:
            salida[i]["precio_dudoso"] = (
                f"¿precio simbólico? $ {_pesos(precio)}: si va de regalo o es a consultar, «Ignorar»; "
                f"si no, «Corregir» con el precio de verdad")


PRECIO_SIMBOLICO = 1  # pesos; el precio de verdad más bajo en las listas revisadas es de $ 1,77 (C. Kappa)


# En una lista en dólares, un precio de más de tantas veces la mediana es casi seguro un precio en
# pesos (Clorosur: US$ 21.408 con la mitad de la lista por debajo de US$ 7,19). La lista en
# dólares más despareja revisada (Chi) llega a 76 veces.
VECES_LA_MEDIANA = 200


# En una lista mezclada, un precio «en pesos» de menos de la centésima parte de la mediana de los
# pesos es casi seguro uno en dólares con el formato de pesos (LTX: «$ 1,85» entre precios de
# $ 1.456 de mediana).
PARTE_DE_LA_MEDIANA = 100


def _precios(salida: list[dict]) -> dict[int, float]:
    from .plan import _numero

    precios = {}
    for i, fila in enumerate(salida):
        try:
            precio = _numero(fila.get("precio_lista") or fila.get("costo") or "")
        except ValueError:
            continue
        if precio > 0:
            precios[i] = precio
    return precios


def _marcar_precios_en_dolares(salida: list[dict]) -> None:
    """Marca para corregir los precios en pesos de una lista mezclada que parecen en dólares."""
    precios = _precios(salida)
    if len(precios) < 10:
        return
    mediana = statistics.median(precios.values())
    for i, precio in precios.items():
        if precio * PARTE_DE_LA_MEDIANA < mediana:
            salida[i]["precio_dudoso"] = (
                f"¿precio en dólares? La lista lo marca en pesos ($ {_pesos(precio)}), pero la mitad de "
                f"sus precios en pesos pasa de $ {_pesos(mediana)}: si es en dólares, «Corregir» con el "
                f"precio en pesos (US$ {_pesos(precio)} × el dólar)")


def _marcar_precios_en_pesos(salida: list[dict]) -> None:
    """Marca para corregir los precios de una lista en dólares que parecen estar en pesos."""
    precios = _precios(salida)
    if len(precios) < 10:
        return
    mediana = statistics.median(precios.values())
    for i, precio in precios.items():
        if precio > VECES_LA_MEDIANA * mediana:
            salida[i]["precio_dudoso"] = (
                f"¿precio en pesos? US$ {_pesos(precio)} en una lista en dólares donde la mitad cuesta "
                f"menos de US$ {_pesos(mediana)}: «Corregir» con el precio en dólares")
