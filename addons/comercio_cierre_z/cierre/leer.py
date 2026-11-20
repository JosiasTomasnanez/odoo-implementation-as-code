"""Cierre Z de las registradoras: lo que se lee de la foto y los controles de los números.

Sin Odoo (se prueba con pytest). El modelo `comercio.cierre.z` usa estas funciones:

- `ESQUEMA_IA` / `INSTRUCCIONES_IA`: lo que se le pide a Gemini al leer la foto del Z.
- `desde_ia`: la respuesta de la IA, limpia (números con dos decimales, enteros, fecha ISO).
- `errores`: lo que impide confirmar el Z (las sumas no cierran, falta un dato).
- `iva_esperado`: el IVA que corresponde a un neto, para comparar con el impreso.

Los importes del Z mandan: el comprobante de Odoo se carga con el IVA impreso aunque difiera
unos centavos del neto × alícuota (la registradora redondea ticket por ticket).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Alícuotas del Z: (campo del neto, campo del IVA, alícuota en %)
ALICUOTAS = (("neto_21", "iva_21", 21.0), ("neto_105", "iva_105", 10.5), ("neto_27", "iva_27", 27.0))
SIN_IVA = ("exento", "no_gravado")
MEDIOS = ("efectivo", "debito", "credito", "transferencia", "otro")

# Diferencia admitida entre el IVA impreso y neto × alícuota: la registradora redondea por
# ticket, así que en un día hay algunos centavos; más que esto es un número mal leído o mal tipeado.
TOLERANCIA_IVA_MINIMA = 2.0
TOLERANCIA_IVA_RELATIVA = 0.005
# Diferencia admitida entre el TOTAL impreso y la suma de netos, IVA, exento y no gravado.
TOLERANCIA_TOTAL = 0.05

ESQUEMA_IA = {
    "type": "OBJECT",
    "properties": {
        "numero_z": {"type": "INTEGER", "nullable": True},
        "fecha": {"type": "STRING", "nullable": True, "description": "AAAA-MM-DD"},
        "punto_de_venta": {"type": "INTEGER", "nullable": True},
        "tique_desde": {"type": "INTEGER", "nullable": True},
        "tique_hasta": {"type": "INTEGER", "nullable": True},
        "neto_21": {"type": "NUMBER", "nullable": True},
        "iva_21": {"type": "NUMBER", "nullable": True},
        "neto_105": {"type": "NUMBER", "nullable": True},
        "iva_105": {"type": "NUMBER", "nullable": True},
        "neto_27": {"type": "NUMBER", "nullable": True},
        "iva_27": {"type": "NUMBER", "nullable": True},
        "exento": {"type": "NUMBER", "nullable": True},
        "no_gravado": {"type": "NUMBER", "nullable": True},
        "total": {"type": "NUMBER", "nullable": True},
        "notas_de_credito": {"type": "NUMBER", "nullable": True},
        "medios": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "medio": {"type": "STRING", "enum": list(MEDIOS)},
                    "importe": {"type": "NUMBER"},
                },
                "required": ["medio", "importe"],
            },
        },
        "dudas": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
}

INSTRUCCIONES_IA = """\
La imagen es un cierre diario «Z» de un controlador fiscal argentino (registradora Sam4s o
Hasar) de un comercio Responsable Inscripto. Transcribí SOLO lo que está impreso, sin calcular
ni inventar:
- numero_z: el número del cierre Z. fecha: la fecha del cierre (AAAA-MM-DD).
- punto_de_venta: el punto de venta del controlador, si figura.
- tique_desde / tique_hasta: el primer y el último número de tique (comprobante) del día.
- neto_21 / iva_21, neto_105 / iva_105, neto_27 / iva_27: el neto gravado y el IVA de cada
  alícuota (21 %, 10,5 %, 27 %). Si el Z solo da el total con IVA de una alícuota, poné en el neto
  null y anotalo en dudas.
- exento, no_gravado: ventas exentas y no gravadas. total: el TOTAL vendido del día.
- notas_de_credito: el total de notas de crédito o devoluciones, si el Z las muestra aparte.
- medios: lo cobrado por medio de pago (efectivo, debito, credito, transferencia, otro) si el
  Z lo detalla; si no, una lista vacía.
Importes con punto decimal (12345.67), sin signo $. Lo que no se lee bien o no figura: null.
En dudas, en castellano y corto, todo lo que no estés seguro de haber leído bien.
"""


def importe(valor) -> float | None:
    """Un importe de la IA o de la pantalla: número con 2 decimales, o None."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        texto = valor.strip().replace("$", "").replace(" ", "")
        if "," in texto and "." in texto:
            # «1.234,56» o «1,234.56»: el último separador es el decimal
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            valor = float(texto)
        except ValueError:
            return None
    try:
        return round(float(valor), 2)
    except (TypeError, ValueError):
        return None


def entero(valor) -> int | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        digitos = re.sub(r"\D", "", valor)
        return int(digitos) if digitos else None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def fecha_iso(valor) -> str | None:
    """«2026-11-11», «11/11/2026» o «11/11/26» → «2026-11-11»."""
    if not valor or not isinstance(valor, str):
        return None
    texto = valor.strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", texto)
    if m:
        a, mes, d = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", texto)
        if not m:
            return None
        d, mes, a = (int(x) for x in m.groups())
        if a < 100:
            a += 2000
    if not (1 <= mes <= 12 and 1 <= d <= 31):
        return None
    return f"{a:04d}-{mes:02d}-{d:02d}"


@dataclass
class Leido:
    """Lo leído de la foto, listo para completar el formulario del Z."""

    valores: dict = field(default_factory=dict)
    medios: list[tuple[str, float]] = field(default_factory=list)
    dudas: list[str] = field(default_factory=list)


def desde_ia(datos: dict) -> Leido:
    leido = Leido()
    if not isinstance(datos, dict):
        leido.dudas.append("La IA no devolvió datos.")
        return leido
    for campo in ("numero_z", "punto_de_venta", "tique_desde", "tique_hasta"):
        leido.valores[campo] = entero(datos.get(campo))
    leido.valores["fecha"] = fecha_iso(datos.get("fecha"))
    for neto, iva, _alicuota in ALICUOTAS:
        leido.valores[neto] = importe(datos.get(neto))
        leido.valores[iva] = importe(datos.get(iva))
    for campo in (*SIN_IVA, "total", "notas_de_credito"):
        leido.valores[campo] = importe(datos.get(campo))
    for medio in datos.get("medios") or []:
        if not isinstance(medio, dict):
            continue
        nombre = str(medio.get("medio") or "").strip().lower()
        monto = importe(medio.get("importe"))
        if nombre in MEDIOS and monto:
            leido.medios.append((nombre, monto))
    leido.dudas = [str(d).strip() for d in datos.get("dudas") or [] if str(d).strip()]
    if leido.valores.get("notas_de_credito"):
        leido.dudas.append(
            "El Z muestra notas de crédito o devoluciones: revisá si los importes de las ventas "
            "ya las restan."
        )
    return leido


def iva_esperado(neto: float, alicuota: float) -> float:
    return round(neto * alicuota / 100.0, 2)


def tolerancia_iva(iva: float) -> float:
    return max(TOLERANCIA_IVA_MINIMA, abs(iva) * TOLERANCIA_IVA_RELATIVA)


def suma_comprobante(v: dict) -> float:
    """Netos + IVA + exento + no gravado: lo que tiene que dar el TOTAL del Z."""
    total = sum((v.get(neto) or 0.0) + (v.get(iva) or 0.0) for neto, iva, _a in ALICUOTAS)
    total += sum(v.get(campo) or 0.0 for campo in SIN_IVA)
    return round(total, 2)


def _pesos(valor: float) -> str:
    entero_, decimales = f"{abs(valor):,.2f}".split(".")
    signo = "−" if valor < 0 else ""
    return f"{signo}$ {entero_.replace(',', '.')},{decimales}"


def errores(v: dict, cobros: list[float]) -> list[str]:
    """Lo que impide confirmar el Z. `v` tiene los campos del formulario; `cobros`, los importes
    de cada medio de pago cargado (puede estar vacío: el Z queda sin cobrar)."""
    problemas = []
    if not v.get("numero_z"):
        problemas.append("Falta el número del Z.")
    if not v.get("fecha"):
        problemas.append("Falta la fecha del Z.")
    desde, hasta = v.get("tique_desde"), v.get("tique_hasta")
    if not desde or not hasta:
        problemas.append("Faltan el primer y el último tique del día (los pide el Libro IVA).")
    elif hasta < desde:
        problemas.append("El último tique es menor que el primero.")
    for neto, iva, alicuota in ALICUOTAS:
        n, i = v.get(neto) or 0.0, v.get(iva) or 0.0
        if n < 0 or i < 0:
            problemas.append(f"Las ventas al {alicuota:g} % no pueden ser negativas.")
            continue
        if not n and not i:
            continue
        esperado = iva_esperado(n, alicuota)
        if abs(esperado - i) > tolerancia_iva(i):
            problemas.append(
                f"Al {alicuota:g} %: el IVA {_pesos(i)} no corresponde al neto {_pesos(n)} "
                f"(daría {_pesos(esperado)}). Revisá los dos números contra el Z."
            )
    for campo in SIN_IVA:
        if (v.get(campo) or 0.0) < 0:
            problemas.append("Exento y no gravado no pueden ser negativos.")
    suma = suma_comprobante(v)
    if suma <= 0:
        problemas.append("El Z no tiene ventas cargadas.")
    total = v.get("total")
    if total is None:
        problemas.append("Falta el TOTAL del Z.")
    elif abs(total - suma) > TOLERANCIA_TOTAL:
        problemas.append(
            f"Netos + IVA + exento + no gravado dan {_pesos(suma)} y el TOTAL del Z es {_pesos(total)}."
        )
    if cobros:
        if any(c <= 0 for c in cobros):
            problemas.append("Cada medio de pago tiene que tener un importe mayor que cero.")
        cobrado = round(sum(cobros), 2)
        if total is not None and abs(cobrado - total) > TOLERANCIA_TOTAL:
            problemas.append(
                f"Los medios de pago suman {_pesos(cobrado)} y el TOTAL del Z es {_pesos(total)}."
            )
    return problemas


def tipo_de_imagen(contenido: bytes) -> str | None:
    """El tipo MIME de la foto o PDF del Z, por sus primeros bytes."""
    if contenido.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if contenido.startswith(b"\x89PNG"):
        return "image/png"
    if contenido.startswith(b"%PDF"):
        return "application/pdf"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    if contenido[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "image/heic"
    return None
