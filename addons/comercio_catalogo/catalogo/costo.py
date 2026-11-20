"""Del precio de la lista del proveedor al costo (30/10).

La lista trae un precio; el costo es lo que de verdad le cuesta al comercio. En el medio:

1. **Moneda**: si la lista está en dólares, se pasa a pesos con la cotización (la del día
   del Banco Nación que publica ARCA, o una fija si se eligió).
2. **Descuentos**, todos en cadena (uno después del otro, «30+10» = 30 % y sobre lo que
   queda otro 10 %):
   - los de toda la lista,
   - el de la familia (la primera regla cuyo texto aparece en la descripción o el código),
   - el del producto (por código del proveedor),
   - el de la columna «descuento» del archivo, si se eligió (solo si es del proveedor),
   - la promoción del proveedor por unidad («5% DTO. X UNIDAD», columna «promociones»).
     Las promociones por cantidad («10% DTO. X 2 ROLLOS») no cambian el costo: son el
     precio por mayor (ver leer_promocion).
3. **Recargo** (flete u otro), en porcentaje.
4. **IVA**: si la lista trae el IVA incluido se saca, porque el costo va sin IVA. La alícuota
   es la del IVA de compra del producto que ya tenemos (manda la del producto); si no, la de la
   columna «IVA» del archivo; si no, la de la lista (por defecto 21).

Todo es opcional: sin nada cargado, el precio de la lista es el costo.
"""
from __future__ import annotations

import re

from .similitud import sin_acentos


def _numero(texto) -> float:
    from .plan import _numero as numero  # plan no importa este módulo

    if isinstance(texto, (int, float)):
        return float(texto)  # 1.105 como número no es «mil ciento cinco»
    return numero(texto)


def cadena(texto) -> list[float]:
    """«30+10+10» → [30, 10, 10]. Admite «%» y coma decimal. ValueError si no se entiende."""
    salida = []
    for parte in str(texto or "").replace("%", "").split("+"):
        parte = parte.strip().replace(",", ".")
        if not parte:
            continue
        valor = float(parte)
        if not 0 <= valor < 100:
            raise ValueError(f"descuento fuera de rango: {parte} %")
        salida.append(valor)
    return salida


def porcentaje(texto) -> float | None:
    """Un porcentaje escrito en una celda: «10», «10 %», «10,5», o 0,105 (celda de Excel con
    formato de porcentaje, que guarda la fracción). None si está vacía o no es un número."""
    limpio = str(texto or "").replace("%", "").strip()
    if not limpio:
        return None
    try:
        valor = _numero(limpio)
    except ValueError:
        return None
    if 0 < valor < 1:
        valor *= 100  # 0,21 → 21 %
    return round(valor, 4)


def descuentos_de_celda(texto) -> list[float]:
    """La celda «descuento» de la fila: «10», «0,1» (formato porcentaje) o «10+5»."""
    if "+" in str(texto or ""):
        try:
            return cadena(texto)
        except ValueError:
            return []
    valor = porcentaje(texto)
    return [valor] if valor and 0 < valor < 100 else []


def _clave(texto: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_acentos(str(texto or "")).lower()).split())


def regla_de_familia(reglas: list[dict], texto: str, codigo: str) -> dict | None:
    """La primera regla (en su orden) cuyo «contiene» aparece en la descripción (con la
    familia) o en el código. «contiene» admite varias opciones separadas por coma."""
    donde = f" {_clave(texto)} {_clave(codigo)} "
    for regla in reglas or []:
        opciones = [_clave(o) for o in str(regla.get("contiene") or "").split(",")]
        if any(o and f" {o} " in donde or (o and len(o) >= 4 and o in donde) for o in opciones):
            return regla
    return None


def _pesos(valor: float) -> str:
    """1234.5 → «1.234,50» (como se escribe en Argentina)."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(valor: float) -> str:
    return f"{valor:g}".replace(".", ",") + " %"


def normalizar_ajustes(ajustes: dict | None) -> dict:
    """Ajustes con todas sus claves. Acepta los de antes (`iva_incluido`: 21 = trae IVA 21 %;
    `cotizacion` sin `moneda` = lista en dólares a esa cotización)."""
    a = dict(ajustes or {})
    if "trae_iva" not in a and a.get("iva_incluido"):
        a["trae_iva"], a["iva"] = True, _numero(a["iva_incluido"])
    if "moneda" not in a:
        a["moneda"] = "usd" if _numero(a.get("cotizacion") or 0) else "ars"
    a.setdefault("descuentos", "")
    a.setdefault("descuentos_neto", "")
    a.setdefault("recargo", 0)
    a.setdefault("cotizacion", 0)
    a.setdefault("trae_iva", False)
    a.setdefault("iva", 21)
    a.setdefault("iva_por_codigo", {})
    a.setdefault("reglas", [])
    a.setdefault("excepciones", {})
    a.setdefault("pack", 0)
    return a


def de_la_fila(ajustes: dict, moneda_fila: str | None) -> dict:
    """Los ajustes con la moneda de la fila, en una lista con pesos y dólares mezclados
    («mixta»: cada fila dice la suya; ver convertir.leer_tabla con monedas). Sin moneda de la
    fila, pesos."""
    if ajustes["moneda"] != "mixta":
        return ajustes
    return {**ajustes, "moneda": "usd" if moneda_fila == "usd" else "ars"}


def hay_ajustes(ajustes: dict) -> bool:
    """¿Hay algo para calcular, o el precio de la lista ya es el costo?"""
    return bool(ajustes["moneda"] in ("usd", "mixta") or cadena(ajustes["descuentos"])
                or _numero(ajustes["recargo"] or 0)
                or ajustes["trae_iva"] or ajustes["reglas"] or ajustes["excepciones"])


def costo_desde_lista(precio: float, ajustes: dict, descuento_fila="", iva_fila="", texto: str = "",
                      codigo: str = "", promocion="") -> tuple[float, str]:
    """(costo, cómo se calculó). `ajustes` ya normalizados (normalizar_ajustes).

    `texto`: descripción con la familia, para las reglas por familia; `codigo`: código del
    proveedor, para las excepciones por producto y el IVA del producto que ya tenemos."""
    pasos = []
    valor = precio
    if ajustes["moneda"] == "usd":
        cotizacion = _numero(ajustes["cotizacion"] or 0)
        if cotizacion <= 0:
            raise ValueError("la lista está en dólares y no hay cotización")
        valor *= cotizacion
        pasos.append(f"US$ {precio:g} × {_pesos(cotizacion)} = $ {_pesos(valor)}")
    else:
        pasos.append(f"$ {_pesos(precio)}")

    def descontar(lista, de):
        nonlocal valor
        for d in lista:
            valor *= 1 - d / 100
            pasos.append(f"−{_pct(d)} {de}")

    promo = leer_promocion(promocion)
    if promo["neto"]:
        # «NETO $ 6900» (Omega, 20/11): el precio de oferta ya trae los descuentos comerciales; solo
        # valen los de la ficha que también se aplican a los netos (p. ej. el 10 % por pago)
        valor = promo["neto"] * (_numero(ajustes["cotizacion"] or 0) if ajustes["moneda"] == "usd" else 1)
        pasos.append(f"oferta neto $ {_pesos(valor)} (en lugar del precio de lista)")
        descontar(cadena(ajustes["descuentos_neto"]), "(sobre el neto)")
    else:
        descontar(cadena(ajustes["descuentos"]), "(lista)")
        regla = regla_de_familia(ajustes["reglas"], texto, codigo)
        if regla:
            descontar(cadena(regla.get("descuentos")), f"({regla.get('nombre') or regla.get('contiene')})")
        excepcion = ajustes["excepciones"].get(str(codigo).strip()) if codigo else None
        if excepcion:
            descontar(cadena(excepcion), "(producto)")
        descontar(descuentos_de_celda(descuento_fila), "(columna de la lista)")
        descontar(promo["unidad"], "(promoción del proveedor)")
    recargo = _numero(ajustes["recargo"] or 0)
    if recargo:
        valor *= 1 + recargo / 100
        pasos.append(f"+{_pct(recargo)} recargo")
    if ajustes["trae_iva"]:
        # Manda el IVA del producto que ya tenemos; si no, el de la columna; si no, el de la lista
        iva, de = ajustes["iva_por_codigo"].get(str(codigo).strip()) if codigo else None, "del producto"
        if iva is None:
            iva, de = porcentaje(iva_fila), "columna"
        if iva is None:
            iva, de = _numero(ajustes["iva"] or 0), "de la lista"
        if iva:
            valor /= 1 + iva / 100
            pasos.append(f"sin IVA {_pct(iva)} ({de})")
    return valor, " · ".join(pasos) + f" → $ {_pesos(valor)}"


# «5% DTO. X UNIDAD», «10% DTO. X 2 ROLLOS», «15% DTO. X 5P», «23,5% DTO. X 25 KG.»
_PROMO = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*%\s*(?:de\s+)?(?:dto|desc|descuento|bonif|bonificacion|off)\.?\s*"
    r"(?:x|por|p/|llevando|comprando|desde)\s*(unidad|unid|u\b|\d+(?:[.,]\d+)?)", re.I)


# «OFERTA: 15%», «OFERTA 15 %», «15% OFF», «PROMO 10%» (un descuento más, comprando una unidad)
_OFERTA_PCT = re.compile(r"^(?:oferta|promo(?:cion)?|off)\s*:?\s*(\d+(?:[.,]\d+)?)\s*%$"
                         r"|^(\d+(?:[.,]\d+)?)\s*%\s*(?:off|de descuento|dto\.?|desc\.?)$", re.I)
# «NETO $ 6900», «NETO: $ 12.810,50», «PRECIO NETO $ 2400»: el precio de oferta, ya neto
_OFERTA_NETO = re.compile(r"neto\s*:?\s*\$\s*([\d.,]+)", re.I)


def leer_promocion(texto) -> dict:
    """Las promociones que un proveedor escribe en texto (FC: «Descuentos y Promociones
    Vigentes»; Omega: «OFERTA: 15%», «NETO $ 6900»). Devuelve {"unidad": [porcentajes que
    valen comprando una sola unidad], "escalones": [(cantidad, porcentaje), …] de menor a mayor
    cantidad, "neto": precio de oferta ya neto o None}. Lo que no se entiende no se usa (queda el
    texto como aviso)."""
    unidad, escalones, neto = [], [], None
    limpio = " ".join(sin_acentos(str(texto or "")).split())
    hallado = _OFERTA_NETO.search(limpio)
    if hallado:
        try:
            neto = _numero(hallado.group(1)) or None
        except ValueError:
            neto = None
    oferta = _OFERTA_PCT.match(limpio)
    if oferta and not neto:
        porcentaje_ = float((oferta.group(1) or oferta.group(2)).replace(",", "."))
        if 0 < porcentaje_ < 100:
            unidad.append(porcentaje_)
    for pct, cuanto in _PROMO.findall(limpio):
        porcentaje_ = float(pct.replace(",", "."))
        if not 0 < porcentaje_ < 100:
            continue
        if cuanto.lower().startswith("u"):
            unidad.append(porcentaje_)
            continue
        cantidad = float(cuanto.replace(",", "."))
        if cantidad <= 1:
            unidad.append(porcentaje_)
        else:
            escalones.append((cantidad, porcentaje_))
    return {"unidad": unidad, "escalones": sorted(escalones), "neto": neto}


# «(pack x 12)», «(PACK X 250)», «(pack x 20 kg)» en la descripción (Nortex)
_PACK = re.compile(r"\bpack\s*x\s*(\d+(?:[.,]\d+)?)", re.I)


def cantidad_de_pack(texto) -> float:
    """Cuántas unidades trae el pack que dice la descripción; 0 si no dice o es de 1."""
    hallado = _PACK.search(str(texto or ""))
    cantidad = float(hallado.group(1).replace(",", ".")) if hallado else 0
    return cantidad if cantidad > 1 else 0
