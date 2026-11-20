"""CUIT/CUIL: dígito verificador (un dígito mal leído de una foto se detecta acá)."""
from __future__ import annotations

PESOS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def cuit_valido(cuit: str) -> bool:
    digitos = "".join(c for c in str(cuit or "") if c.isdigit())
    if len(digitos) != 11:
        return False
    resto = sum(int(d) * p for d, p in zip(digitos[:10], PESOS, strict=True)) % 11
    verificador = 0 if resto == 0 else 9 if resto == 1 else 11 - resto
    return verificador == int(digitos[10])
