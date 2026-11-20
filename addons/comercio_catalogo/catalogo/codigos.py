"""Códigos de barras: validación GTIN (EAN/UPC) y código propio con prefijo 20.

Ver docs/areas/codigos.md. Funciones puras, sin Odoo.
"""
from __future__ import annotations

import re

PREFIJO_PROPIO = "20"
LARGO_NUMERO_PROPIO = 10  # 20 + 10 dígitos + verificador = EAN-13

# Tipos de código que puede traer una fila
FABRICANTE = "fabricante"  # GTIN válido que no es de uso interno: se carga tal cual
INTERNO = "interno"  # GTIN válido con prefijo 2: código de uso interno de alguien
INVALIDO = "invalido"  # no se puede usar: a revisar


def digito_verificador(cuerpo: str) -> int:
    """Dígito verificador GTIN (EAN-8/UPC-A/EAN-13/GTIN-14) del cuerpo sin verificador."""
    suma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(cuerpo)))
    return (10 - suma % 10) % 10


def es_gtin_valido(codigo: str) -> bool:
    return (
        codigo.isdigit()
        and len(codigo) in (8, 12, 13, 14)
        and digito_verificador(codigo[:-1]) == int(codigo[-1])
    )


def normalizar(texto: str | None) -> tuple[str | None, str | None]:
    """Devuelve (código, tipo) o (None, None) si la celda está vacía.

    Repara lo que suele romper Excel: espacios, «.0» final y ceros a la izquierda
    perdidos (un UPC-A de 12 dígitos guardado como número queda en 11).
    """
    if texto is None:
        return None, None
    crudo = str(texto).strip()
    if not crudo:
        return None, None
    if re.search(r"[eE][+-]?\d", crudo):  # notación científica: ya se perdieron dígitos
        return crudo, INVALIDO
    crudo = re.sub(r"\.0+$", "", crudo).replace(" ", "")
    crudo = _gtin_de_gs1(crudo) or crudo
    if not crudo.isdigit():
        return crudo, INVALIDO
    candidatos = [crudo] + [crudo.zfill(n) for n in (8, 12, 13) if len(crudo) < n]
    for codigo in candidatos:
        if es_gtin_valido(codigo):
            # EAN-13 de uso interno (20-29); un UPC-A de 12 dígitos empieza con «0» (el
            # prefijo 2 de UPC también es interno), por eso se mira el largo.
            interno = (len(codigo) == 13 and codigo.startswith("2")) or (
                len(codigo) == 12 and codigo.startswith("2")
            )
            return codigo, INTERNO if interno else FABRICANTE
    return crudo, INVALIDO


def _gtin_de_gs1(crudo: str) -> str | None:
    """Código GS1 completo (el de las cajas y los DataMatrix): «01» + GTIN-14 + otros datos, como
    «17» + vencimiento. Devuelve el código de barras de adentro (EAN-13 si el GTIN-14 empieza con 0),
    o None si no es uno de esos (Rho, 26/10)."""
    # El lote («10…») puede traer letras: solo el GTIN de adentro tiene que ser válido
    if len(crudo) < 18 or not crudo.startswith("01") or not es_gtin_valido(crudo[2:16]):
        return None
    gtin = crudo[2:16]
    return gtin[1:] if gtin.startswith("0") else gtin


def codigo_propio(numero: int) -> str:
    """Código de barras propio: «20» + número (10 dígitos) + verificador."""
    cuerpo = PREFIJO_PROPIO + str(numero).zfill(LARGO_NUMERO_PROPIO)
    if len(cuerpo) != 12:
        raise ValueError(f"número fuera de rango para el código propio: {numero}")
    return cuerpo + str(digito_verificador(cuerpo))


def numero_de_codigo_propio(codigo: str | None) -> int | None:
    """Número correlativo de un código propio, o None si no es propio."""
    if codigo and len(codigo) == 13 and codigo.startswith(PREFIJO_PROPIO) and es_gtin_valido(codigo):
        return int(codigo[2:12])
    return None
