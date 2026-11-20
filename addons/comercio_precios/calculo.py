"""Cálculo del precio de venta, sin Odoo (se prueba con `make test`)."""
from __future__ import annotations

import math


def redondear_arriba(valor: float, multiplo: float) -> float:
    """Al múltiplo siguiente (nunca para abajo: el redondeo no se come el margen)."""
    if not multiplo or multiplo <= 0:
        return round(valor, 2)
    return round(math.ceil(round(valor / multiplo, 6)) * multiplo, 2)


def leer_tramos(texto: str | None) -> list[tuple[float, float]]:
    """«10; 1000:100; 10000:500» → [(0, 10), (1000, 100), (10000, 500)]: hasta $ 1.000 se redondea
    a $ 10, desde $ 1.000 a $ 100 y desde $ 10.000 a $ 500 (20/11). Vacío: []. ValueError si no se
    entiende (lo avisa la categoría al guardar)."""
    tramos = []
    for parte in (texto or "").replace(",", ".").split(";"):
        parte = parte.strip()
        if not parte:
            continue
        desde, _, multiplo = parte.rpartition(":")
        tramos.append((float(desde.strip() or 0), float(multiplo.strip())))
    if any(m <= 0 or d < 0 for d, m in tramos):
        raise ValueError("los montos tienen que ser positivos")
    return sorted(tramos)


def multiplo_para(valor: float, redondeo) -> float:
    """El múltiplo que corresponde: un número (el mismo para todo) o tramos (leer_tramos)."""
    if isinstance(redondeo, (list, tuple)):
        elegido = 0.0
        for desde, multiplo in redondeo:
            if valor >= desde:
                elegido = multiplo
        return elegido
    return redondeo or 0.0


def texto_redondeo(redondeo) -> str:
    """Para mostrar la regla: «$ 100» o «$ 10 / desde $ 1000: $ 100 / desde $ 10000: $ 500»."""
    if isinstance(redondeo, (list, tuple)):
        return " / ".join(f"desde $ {d:g}: $ {m:g}" if d else f"$ {m:g}" for d, m in redondeo)
    return f"$ {redondeo:g}" if redondeo else "-"


def precio_final(base: float, margen: float, iva: float, redondeo) -> float:
    """Precio que paga el cliente: base × (1 + margen %) × (1 + IVA %), redondeado (un múltiplo o
    tramos según el precio)."""
    valor = base * (1 + margen / 100) * (1 + iva / 100)
    return redondear_arriba(valor, multiplo_para(valor, redondeo))


def precio_de_lista(final: float, iva: float, iva_incluido: bool) -> float:
    """Lo que se guarda en el precio de venta de Odoo según la empresa cargue los precios
    con IVA incluido o sin IVA."""
    return final if iva_incluido else round(final / (1 + iva / 100), 2)
