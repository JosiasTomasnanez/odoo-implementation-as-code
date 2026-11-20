"""Leer la factura de un proveedor (PDF o foto) sin la digitalización paga de Odoo.

Python puro, sin Odoo: se prueba sin servidor.

- **PDF con texto** (el que manda el sistema del proveedor): se arma la tabla con las
  posiciones de las letras (el mismo lector de las listas, catalogo/pdf.py) y se buscan
  los renglones de artículos: cantidad, código, descripción, precio, bonificación e
  importe. Sin IA.
- **Foto o PDF escaneado**: lo transcribe Gemini (`ESQUEMA_IA`, `desde_ia`). Lo leído con
  IA siempre se revisa: un dígito mal leído es un precio mal cargado.
- **El pie** (`Totales`): subtotal, flete, IVA, percepciones y el TOTAL a pagar. No pasan a
  la orden de compra, pero la factura de Odoo tiene que dar lo mismo que la del proveedor.

No se adivina nada: lo que no se reconoce queda vacío y la factura se revisa en Odoo.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

# Títulos habituales de cada columna de la tabla de artículos de una factura
TITULOS = {
    "cantidad": ["cantidad", "cant", "cant.", "cdad", "unidades"],
    "codigo": ["codigo", "cod", "cod.", "cod art", "cod. art", "articulo cod", "art", "sku", "ref"],
    "descripcion": ["articulo", "descripcion", "detalle", "producto", "concepto", "desc"],
    "precio": ["precio", "p unitario", "p. unitario", "precio unitario", "precio unit", "unitario", "p.unit",
               "p. unit", "precio lista", "p. lista"],
    "bonificacion": ["% bonif", "% bonif.", "bonif", "bonif.", "% dto", "dto", "dto.", "% desc", "desc.",
                     "bonificacion", "descuento", "%"],
    "precio_neto": ["p.bonif", "p.bonif.", "p. bonif", "precio neto", "p. neto", "neto unit", "precio bonif",
                    "p.neto"],
    "importe": ["importe", "subtotal", "total", "importe neto", "total item", "imp."],
    "iva": ["t.iva", "iva", "% iva", "alic", "alic.", "alicuota", "tasa iva"],
}
# Donde termina la tabla de artículos (renglón de totales)
FIN_TABLA = ("subtotal", "neto gravado", "total", "importe neto gravado", "transporte")
_CUIT = re.compile(r"\b(20|23|24|27|30|33|34)-?(\d{8})-?(\d)\b")
_NUMERO = re.compile(r"N\s*[º°o]?\.?\s*:?\s*([ABCM])?\s*(\d{4,5})\s*-\s*(\d{8})\b", re.IGNORECASE)
_FECHA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_CAE = re.compile(r"C\.?\s*A\.?\s*E\.?\D{0,12}(\d{14})")
_CODIGO_TIPO = re.compile(r"C[oó]d(?:igo|\.)?\s*:?\s*N?[º°]?\s*0?(\d{1,3})\b", re.IGNORECASE)
_LETRA = re.compile(r"^\s*([ABCM])\s*$")
# «06687 - REGULADOR GAS…»: el código del proveedor al principio de la descripción
_CODIGO_AL_PRINCIPIO = re.compile(r"^\s*([A-Z0-9][A-Z0-9./-]{2,19})\s+-\s+(.+)$", re.IGNORECASE)


@dataclass
class Linea:
    """Un artículo de la factura, tal como viene (los números ya como números)."""

    descripcion: str
    cantidad: float | None = None
    codigos: list[str] = field(default_factory=list)  # posibles códigos (del proveedor o de barras)
    precio: float | None = None  # unitario, antes de la bonificación
    bonificacion: float | None = None  # %
    importe: float | None = None
    iva: float | None = None  # %
    avisos: list[str] = field(default_factory=list)

    @property
    def precio_neto(self) -> float | None:
        if self.precio is None:
            return None
        return self.precio * (1 - (self.bonificacion or 0) / 100)


@dataclass
class Percepcion:
    """Una percepción sufrida, tal como la detalla la factura («Perc.IIBB: CORDOBA 35.765,17»)."""

    tipo: str  # "iibb", "iva" o "ganancias"
    jurisdiccion: str | None  # «cordoba» (sin acentos, en minúscula); solo IIBB
    importe: float
    texto: str


@dataclass
class Totales:
    """El pie de la factura: lo que no son artículos y el total a pagar."""

    subtotal: float | None = None
    flete: float | None = None
    flete_texto: str | None = None  # «Flete 2,50%»: el nombre de la línea en la factura
    neto_gravado: float | None = None
    exento: float | None = None
    iva: float | None = None
    percepciones: float | None = None
    otros: float | None = None  # otros tributos, impuestos internos
    total: float | None = None
    detalle_percepciones: list[Percepcion] = field(default_factory=list)

    def iva_del_flete(self, lineas: list[Linea], letra: str | None) -> float:
        """La alícuota del flete: 0 si no está gravado (o la factura no discrimina IVA); si no,
        la que da el pie (IVA / neto gravado) o la más común de los artículos (21 % si no hay)."""
        if letra in ("B", "C"):
            return 0.0
        if self.neto_gravado is not None and self.subtotal is not None and self.flete:
            sin_flete = abs(self.neto_gravado - self.subtotal)
            if sin_flete < 1 <= abs(sin_flete - self.flete):
                return 0.0  # el neto gravado no incluye el flete
        if self.iva and self.neto_gravado:
            real = self.iva / self.neto_gravado * 100
            for alicuota in (21.0, 10.5, 27.0):
                if abs(real - alicuota) < 0.05:
                    return alicuota
        comunes = Counter(li.iva for li in lineas if li.iva).most_common(1)
        return comunes[0][0] if comunes else 21.0


@dataclass
class Factura:
    lineas: list[Linea]
    cuits: list[str] = field(default_factory=list)  # todos los que aparecen (el del proveedor y el nuestro)
    letra: str | None = None
    codigo_tipo: str | None = None  # código ARCA del comprobante («1» = factura A)
    numero: str | None = None  # «0003-00001234»
    fecha: str | None = None  # AAAA-MM-DD
    vencimiento: str | None = None
    cae: str | None = None
    leida_con_ia: bool = False
    avisos: list[str] = field(default_factory=list)
    totales: Totales = field(default_factory=Totales)

    def cuit_proveedor(self, nuestros: set[str]) -> str | None:
        """El primer CUIT que no es el nuestro (el emisor va arriba, el cliente abajo)."""
        return next((c for c in self.cuits if c not in nuestros), None)


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))


def clave(texto: str) -> str:
    """Para comparar descripciones: sin acentos, sin guiones sueltos ni espacios de más
    («TORNILLO FIX - 5  X  50» = «TORNILLO FIX 5 X 50»)."""
    texto = sin_acentos(str(texto or "")).casefold()
    texto = re.sub(r"\s[-–]\s|\s[-–]$|^[-–]\s", " ", texto)
    return " ".join(texto.split())


def solo_digitos(texto: str) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def numero(texto) -> float | None:
    """«1.234,56», «1234,56», «12,50», «$ 35», «1,234.56» → número; None si no es un número."""
    texto = str(texto or "").replace("\xa0", "").replace("$", "").replace(" ", "").strip()
    if texto.endswith("%"):
        texto = texto[:-1]
    if not texto or not re.fullmatch(r"-?[\d.,]+", texto) or not re.search(r"\d", texto):
        return None
    if "," in texto and "." in texto:
        if texto.rfind(",") < texto.rfind("."):
            texto = texto.replace(",", "")
        else:
            texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        if texto.count(",") > 1:
            return None
        texto = texto.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    try:
        return float(texto)
    except ValueError:
        return None


def _fecha(texto: str) -> str | None:
    m = _FECHA.search(texto or "")
    if not m:
        return None
    dia, mes, anio = (int(x) for x in m.groups())
    if not (1 <= dia <= 31 and 1 <= mes <= 12):
        return None
    return f"{anio:04d}-{mes:02d}-{dia:02d}"


def _normal(titulo: str) -> str:
    return " ".join(sin_acentos(titulo or "").lower().replace("..", ".").split())


def _columna_de(titulo: str) -> str | None:
    t = _normal(titulo)
    for columna, sinonimos in TITULOS.items():
        if t in sinonimos or t.rstrip(".") in sinonimos:
            return columna
    return None


def _encabezado(fila: list[str]) -> dict[str, int] | None:
    """{columna: índice} si el renglón es el título de la tabla de artículos (cantidad,
    descripción y algún importe o precio)."""
    columnas: dict[str, int] = {}
    for i, celda in enumerate(fila):
        col = _columna_de(celda)
        if col and col not in columnas:
            columnas[col] = i
    if "cantidad" in columnas and "descripcion" in columnas and ({"precio", "importe"} & set(columnas)):
        return columnas
    return None


def _es_codigo(texto: str) -> bool:
    """Una sola «palabra» con algún dígito: 01710, 40519, AB-123, 7790001234567."""
    texto = texto.strip()
    return bool(texto) and " " not in texto and len(texto) <= 20 and bool(re.search(r"\d", texto))


def _dividir_numero_final(texto: str) -> tuple[str, float | None]:
    """«8x1000 21,00» → («8x1000», 21.0): la descripción larga se metió en la columna de al lado."""
    partes = texto.rsplit(" ", 1)
    if len(partes) == 2 and numero(partes[1]) is not None:
        return partes[0], numero(partes[1])
    return texto, None


NUMERICAS = ("cantidad", "precio", "bonificacion", "precio_neto", "importe", "iva")


def desde_tabla(tabla: list[list[str]]) -> list[Linea]:
    """Los artículos de la tabla de la factura (puede tener varias páginas, con el título
    repetido en cada una). Los renglones sin cantidad que siguen a un artículo lo completan:
    un código suelto se suma a sus posibles códigos, un texto a su descripción y un número
    a la columna que le falte."""
    lineas: list[Linea] = []
    columnas: dict[str, int] | None = None
    actual: Linea | None = None
    netos: dict[int, float] = {}  # id(linea) → precio neto leído (para controlar)
    for fila in tabla:
        celdas = [str(c or "").strip() for c in fila]
        nuevo = _encabezado(celdas)
        if nuevo:
            columnas, actual = nuevo, None
            continue
        if columnas is None or not any(celdas):
            continue
        primera = _normal(next((c for c in celdas if c), ""))
        if any(primera.startswith(f) for f in FIN_TABLA):
            columnas, actual = None, None  # totales: hasta el próximo título (otra página)
            continue

        def celda(col: str, celdas=celdas, columnas=columnas) -> str:
            i = columnas.get(col)
            return celdas[i] if i is not None and i < len(celdas) else ""

        valores: dict[str, float | None] = {}
        sobrante: list[str] = []
        for col in NUMERICAS:
            texto = celda(col)
            valor = numero(texto)
            if valor is None and texto:
                resto, valor = _dividir_numero_final(texto)
                if valor is not None:
                    sobrante.append(resto)
                elif col != "cantidad":
                    sobrante.append(texto)
            valores[col] = valor
        descripcion = celda("descripcion")
        codigo = celda("codigo")
        con_precio = valores["importe"] is not None or valores["precio"] is not None
        es_articulo = valores["cantidad"] and con_precio
        if es_articulo:
            codigos = [codigo] if _es_codigo(codigo) else []
            m = _CODIGO_AL_PRINCIPIO.match(descripcion)
            if m and _es_codigo(m.group(1)):
                codigos.append(m.group(1))
                descripcion = m.group(2)
            descripcion = " ".join([descripcion, *sobrante]).strip()
            actual = Linea(descripcion=" ".join(descripcion.split()), cantidad=valores["cantidad"],
                           codigos=codigos, precio=valores["precio"], bonificacion=valores["bonificacion"],
                           importe=valores["importe"], iva=valores["iva"])
            if valores["precio_neto"] is not None:
                netos[id(actual)] = valores["precio_neto"]
            lineas.append(actual)
            continue
        if actual is None:
            continue  # subtítulos de la tabla («COD BAR.. DESPACHO»)
        # Renglón que completa al artículo de arriba
        for i, texto in enumerate(celdas):
            if not texto:
                continue
            col = next((c for c, j in columnas.items() if j == i), None)
            valor = numero(texto)
            if col in NUMERICAS and valor is not None:
                if col == "bonificacion" and actual.bonificacion is None:
                    actual.bonificacion = valor
                elif col == "iva" and actual.iva is None:
                    actual.iva = valor
                continue
            if _es_codigo(texto):
                actual.codigos.append(texto)
            elif ":" not in texto and (col == "descripcion" or len(texto) <= 12):
                # Lo que no entró en el renglón de arriba. Una leyenda («TRANSFERENCIA - ECHEQ…:
                # 1.005.895,49») o un texto largo en otra columna no es parte del artículo
                actual.descripcion = f"{actual.descripcion} {texto}".strip()
    for linea in lineas:
        _controlar(linea, netos.get(id(linea)))
    return lineas


def _controlar(linea: Linea, neto_leido: float | None) -> None:
    """Completa lo que se deduce con seguridad y avisa lo que no cierra."""
    if linea.precio is None and linea.importe is not None and linea.cantidad:
        linea.precio = round(linea.importe / linea.cantidad, 4)
    if linea.bonificacion is None and neto_leido and linea.precio:
        bonif = round((1 - neto_leido / linea.precio) * 100, 2)
        if 0 < bonif < 100:
            linea.bonificacion = bonif
    if linea.importe is not None and linea.cantidad and linea.precio_neto is not None:
        esperado = linea.cantidad * linea.precio_neto
        if abs(esperado - linea.importe) > max(1.0, abs(linea.importe) * 0.01):
            linea.avisos.append(f"cantidad × precio da {esperado:,.2f} y la factura dice "
                                f"{linea.importe:,.2f}")


def datos_generales(texto: str, factura: Factura) -> None:
    """CUIT, número, letra, código de comprobante, fecha, vencimiento y CAE del texto
    completo de la factura."""
    vistos = []
    for m in _CUIT.finditer(texto):
        cuit = "".join(m.groups())
        if cuit not in vistos:
            vistos.append(cuit)
    factura.cuits = vistos
    m = _NUMERO.search(texto)
    if m:
        factura.letra = (m.group(1) or "").upper() or None
        factura.numero = f"{m.group(2)}-{m.group(3)}"
    if not factura.letra:
        for renglon in texto.splitlines()[:40]:
            letra = _LETRA.match(renglon)
            if letra:
                factura.letra = letra.group(1).upper()
                break
    m = _CODIGO_TIPO.search(texto[:3000])
    if m:
        factura.codigo_tipo = str(int(m.group(1)))
    m = _CAE.search(texto)
    if m:
        factura.cae = m.group(1)
    for renglon in texto.splitlines():
        bajo = _normal(renglon)
        if factura.fecha is None and "fecha" in bajo and "inicio" not in bajo and "vto" not in bajo:
            factura.fecha = _fecha(renglon)
        if factura.vencimiento is None and ("vto" in bajo or "vencimiento" in bajo) and "cae" not in bajo:
            factura.vencimiento = _fecha(renglon)
    if factura.fecha is None:
        factura.fecha = _fecha(texto)


# ---------------------------------------------------------------------------- el pie
# Un importe con centavos («35.765,17», «1117661,66», «1,234.56»): en el pie, un número sin
# centavos al lado de un título suele ser una alícuota («IVA 21»), no un importe
_IMPORTE = r"-?(?:\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}|\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})"
_ETIQUETA_E_IMPORTE = re.compile(rf"^(.*?[^\d\s:$])[\s:$]*({_IMPORTE})$")
_PERCEPCION = re.compile(rf"(perc.*?)[\s:$]*({_IMPORTE})(?![\d%]|\s*%)")
SUMAN = ("iva", "percepciones", "otros")  # varias columnas («IVA 21%», «IVA 10,5%») se suman
VENTANA_PIE = 5  # renglones debajo de los títulos del pie donde están sus importes
TOTAL = ("total", "total $", "importe total", "total factura", "total a pagar", "total general",
         "total final")


def _tipo_total(texto: str) -> str | None:
    """Qué es ese título del pie: subtotal, flete, neto_gravado, exento, iva, percepciones,
    otros o total. None si no es un título del pie."""
    t = _normal(texto).rstrip(" :$")
    if not t or re.search(r"\d{3}", t):
        return None  # «Flete 2,50%» sí; «TRANSFERENCIA… 30-60 10%: 1.005.895,49» tampoco llega acá
    if t.startswith(("subtotal", "sub total", "sub-total")):
        return "subtotal"
    if t.startswith(("flete", "transporte", "gastos de envio", "envio", "acarreo")):
        return "flete"
    if t.startswith(("neto gravado", "importe neto gravado", "neto")):
        return "neto_gravado"
    if t.startswith(("exento", "importe exento", "no gravado", "importe no gravado")):
        return "exento"
    if t.startswith("perc") or "percep" in t:
        return "percepciones"
    if t.startswith(("otros tributos", "imp. internos", "impuestos internos", "imp internos")):
        return "otros"
    if re.match(r"^iva\b", t) and "iibb" not in t:
        return "iva"
    if t in TOTAL:
        return "total"
    return None


def _clasificar_percepcion(texto: str) -> tuple[str | None, str | None]:
    """(tipo, jurisdicción) de «Perc.IIBB: CORDOBA», «Percepción IVA 3%», «Perc. Ganancias»."""
    t = _normal(texto)
    if re.search(r"\b(iibb|ii\.?\s?bb\.?|ingresos brutos|i\.\s?b\.?)(?=\W|$)", t):
        tipo = "iibb"
    elif re.search(r"\biva\b", t):
        return "iva", None
    elif "ganancia" in t:
        return "ganancias", None
    else:
        return None, None
    resto = re.sub(r"\b(perc\w*|iibb|ii\.?\s?bb|ingresos brutos|i\.\s?b|de|sufrida|iva|muni\w*)\b", " ", t)
    resto = re.sub(r"[\d.,]+\s*%|[^a-z ]", " ", resto)
    return tipo, " ".join(resto.split()) or None


def percepciones_del_texto(texto: str) -> list[Percepcion]:
    """El detalle de las percepciones («Perc.IIBB: CORDOBA 35.765,17»), una vez cada una
    (la factura las repite en cada página)."""
    vistas: dict[tuple, Percepcion] = {}
    for renglon in (texto or "").splitlines():
        for m in _PERCEPCION.finditer(_normal(renglon)):
            tipo, jurisdiccion = _clasificar_percepcion(m.group(1))
            importe = numero(m.group(2))
            # IIBB sin provincia es el título de la columna («Percepciones IVA IIBB»), no un detalle
            if tipo and importe and (tipo != "iibb" or jurisdiccion):
                vistas[(tipo, jurisdiccion)] = Percepcion(tipo, jurisdiccion, importe, m.group(1).strip(" :"))
    return list(vistas.values())


def _mas_cercano(x0: float, x1: float, titulos: list[tuple[str, float, float]]) -> int | None:
    """El título que más se superpone con el importe (o el más cercano, si está cerca)."""
    def superposicion(t):
        return min(x1, t[2]) - max(x0, t[1])

    mejor = max(range(len(titulos)), key=lambda i: superposicion(titulos[i]))
    if superposicion(titulos[mejor]) > 0:
        return mejor
    centro = (x0 + x1) / 2
    cerca = min(range(len(titulos)), key=lambda i: abs((titulos[i][1] + titulos[i][2]) / 2 - centro))
    return cerca if abs((titulos[cerca][1] + titulos[cerca][2]) / 2 - centro) < 60 else None


def totales_desde_renglones(renglones: list[list[tuple[str, float, float]]]) -> Totales:
    """El pie de la factura desde los renglones del PDF con la posición de cada celda
    (texto, x0, x1). Dos formas: los títulos en un renglón y los importes debajo, cada uno en
    la columna de su título (FC), o «Título: importe» en el mismo renglón. Si el pie se
    repite en cada página, vale el último."""
    valores: dict[str, dict[str, float]] = {}

    def poner(clave: str, etiqueta: str, valor: float) -> None:
        if clave not in SUMAN:
            valores[clave] = {}
        valores.setdefault(clave, {})[_normal(etiqueta)] = valor

    def titulos_de(renglon) -> list[tuple[str, float, float, str]] | None:
        titulos = [(t, x0, x1, k) for t, x0, x1 in renglon if (k := _tipo_total(t))]
        articulos = any(_columna_de(t) in ("cantidad", "descripcion") for t, _x0, _x1 in renglon)
        con_numeros = any(numero(t) is not None for t, _x0, _x1 in renglon)
        return titulos if len(titulos) >= 3 and not articulos and not con_numeros else None

    i = 0
    while i < len(renglones):
        titulos = titulos_de(renglones[i])
        if titulos:
            usados: set[int] = set()
            j = i + 1
            while j < len(renglones) and j <= i + VENTANA_PIE and not titulos_de(renglones[j]):
                for texto, x0, x1 in renglones[j]:
                    valor = numero(texto)
                    k = _mas_cercano(x0, x1, titulos) if valor is not None else None
                    if k is not None and k not in usados:
                        usados.add(k)
                        poner(titulos[k][3], titulos[k][0], valor)
                j += 1
            i = j
            continue
        renglon = renglones[i]
        for n, (texto, _x0, _x1) in enumerate(renglon):
            clave, etiqueta, valor = _tipo_total(texto), texto, None
            siguiente = renglon[n + 1][0].replace("$", "").strip() if n + 1 < len(renglon) else ""
            if clave and re.fullmatch(_IMPORTE, siguiente):
                valor = numero(siguiente)
            elif (m := _ETIQUETA_E_IMPORTE.match(texto.strip())) and (clave := _tipo_total(m.group(1))):
                etiqueta, valor = m.group(1), numero(m.group(2))
            if clave and valor is not None:
                if clave == "percepciones" and _clasificar_percepcion(etiqueta)[0]:
                    continue  # detalle de una percepción («Perc.IIBB: CORDOBA …»): va aparte
                poner(clave, etiqueta, valor)
        i += 1
    totales = Totales(**{k: round(sum(v.values()), 2) for k, v in valores.items() if v})
    if totales.flete is not None:
        totales.flete_texto = next(iter(valores["flete"]), None)
    return totales


def _con_mayuscula(texto: str | None) -> str | None:
    return texto[:1].upper() + texto[1:] if texto else texto


def leer_pdf(contenido: bytes, tabla_desde_pdf, renglones_desde_pdf=None) -> Factura | None:
    """La factura de un PDF con texto; None si es escaneado (sin texto) o no se encuentra
    la tabla de artículos. `tabla_desde_pdf`: el lector de las listas (catalogo/pdf.py);
    `renglones_desde_pdf`: los renglones con la posición de cada celda, para el pie."""
    import io

    from pdfminer.high_level import extract_text

    tabla = tabla_desde_pdf(contenido)
    if not tabla:
        return None
    lineas = desde_tabla(tabla)
    if not lineas:
        return None
    factura = Factura(lineas=lineas)
    # El texto plano (en orden de lectura) para los datos de arriba; la tabla junta celdas
    texto = extract_text(io.BytesIO(contenido)) + "\n" + "\n".join(" ".join(f) for f in tabla)
    datos_generales(texto, factura)
    if renglones_desde_pdf is not None:
        factura.totales = totales_desde_renglones(renglones_desde_pdf(contenido))
        factura.totales.flete_texto = _con_mayuscula(factura.totales.flete_texto)
    factura.totales.detalle_percepciones = percepciones_del_texto(texto)
    return factura


# ---------------------------------------------------------------------------- con IA
INSTRUCCIONES_IA = """Esta es una factura (o remito) de un proveedor de un comercio argentino.
Transcribí los ARTÍCULOS tal cual están impresos, uno por renglón: cantidad, código del artículo
(si lo trae), descripción, precio unitario, porcentaje de bonificación o descuento, importe del
renglón y alícuota de IVA. Copiá textos y números EXACTAMENTE como se ven (mismos puntos y comas),
sin calcular, corregir ni completar. Lo que no está o no se lee con seguridad: "" (no lo adivines).
Además: los CUIT que aparecen (todos, como están), la letra del comprobante (A, B, C o M), el código
del comprobante si figura («Código: 1», «Cod. 01»), el número (punto de venta y número, p. ej.
«0003-00001234»), la fecha de emisión, la fecha de vencimiento del PAGO (si figura; no la del CAE:
«CAE … Vto.» es otra cosa) y el CAE.
No incluyas totales, percepciones, fletes ni leyendas como artículos: van en el pie (subtotal,
flete, neto gravado, IVA, cada percepción con su texto tal cual, p. ej. «Perc. IIBB Córdoba», y el
TOTAL de la factura)."""

ESQUEMA_IA = {
    "type": "OBJECT",
    "properties": {
        "cuits": {"type": "ARRAY", "items": {"type": "STRING"}},
        "letra": {"type": "STRING"},
        "codigo_comprobante": {"type": "STRING"},
        "numero": {"type": "STRING"},
        "fecha": {"type": "STRING"},
        "vencimiento": {"type": "STRING"},
        "cae": {"type": "STRING"},
        "subtotal": {"type": "STRING"},
        "flete": {"type": "STRING"},
        "neto_gravado": {"type": "STRING"},
        "iva": {"type": "STRING"},
        "percepciones": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"texto": {"type": "STRING"}, "importe": {"type": "STRING"}},
            },
        },
        "total": {"type": "STRING"},
        "articulos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "cantidad": {"type": "STRING"},
                    "codigo": {"type": "STRING"},
                    "descripcion": {"type": "STRING"},
                    "precio_unitario": {"type": "STRING"},
                    "bonificacion": {"type": "STRING"},
                    "importe": {"type": "STRING"},
                    "iva": {"type": "STRING"},
                },
                "required": ["cantidad", "descripcion"],
            },
        },
    },
    "required": ["articulos"],
}


def desde_ia(datos: dict) -> Factura:
    """La respuesta de la IA (ESQUEMA_IA) como Factura, con los mismos controles que el PDF."""
    lineas = []
    for art in datos.get("articulos") or []:
        if not isinstance(art, dict):
            continue
        descripcion = " ".join(str(art.get("descripcion") or "").split())
        cantidad = numero(art.get("cantidad"))
        if not descripcion or not cantidad:
            continue
        codigo = str(art.get("codigo") or "").strip()
        codigos = [codigo] if _es_codigo(codigo) else []
        m = _CODIGO_AL_PRINCIPIO.match(descripcion)
        if m and _es_codigo(m.group(1)):
            codigos.append(m.group(1))
            descripcion = m.group(2)
        linea = Linea(descripcion=descripcion, cantidad=cantidad, codigos=codigos,
                      precio=numero(art.get("precio_unitario")), bonificacion=numero(art.get("bonificacion")),
                      importe=numero(art.get("importe")), iva=numero(art.get("iva")))
        _controlar(linea, None)
        lineas.append(linea)
    factura = Factura(lineas=lineas, leida_con_ia=True)
    texto = "\n".join([
        " ".join(str(c) for c in datos.get("cuits") or []),
        f"Nº {datos.get('letra') or ''} {datos.get('numero') or ''}",
        f"Fecha: {datos.get('fecha') or ''}",
        f"Vto.: {datos.get('vencimiento') or ''}",
        f"CAE: {datos.get('cae') or ''}",
    ])
    datos_generales(texto, factura)
    letra = str(datos.get("letra") or "").strip().upper()
    if letra in ("A", "B", "C", "M"):
        factura.letra = letra
    tipo = solo_digitos(datos.get("codigo_comprobante"))
    if tipo:
        factura.codigo_tipo = str(int(tipo))
    totales = Totales(subtotal=numero(datos.get("subtotal")), flete=numero(datos.get("flete")),
                      neto_gravado=numero(datos.get("neto_gravado")), iva=numero(datos.get("iva")),
                      total=numero(datos.get("total")))
    if totales.flete:
        totales.flete_texto = "Flete"
    for p in datos.get("percepciones") or []:
        if not isinstance(p, dict):
            continue
        tipo_p, jurisdiccion = _clasificar_percepcion(f"perc {p.get('texto') or ''}")
        importe = numero(p.get("importe"))
        if importe:
            totales.percepciones = round((totales.percepciones or 0) + importe, 2)
            if tipo_p:
                totales.detalle_percepciones.append(
                    Percepcion(tipo_p, jurisdiccion, importe, str(p.get("texto") or "").strip()))
    factura.totales = totales
    return factura
