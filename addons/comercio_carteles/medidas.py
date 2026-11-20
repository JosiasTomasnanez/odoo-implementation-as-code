"""Cuentas del cartel, sin Odoo (se prueban en tests/test_carteles.py)."""
import math

# Tamaños en una hoja A4 vertical (210 × 297 mm) con 5 mm de margen: (columnas, filas). La hoja
# es siempre la misma; cambia cuántos carteles entran y el tamaño de las letras.
FORMATOS = {"1": (1, 1), "2": (1, 2), "4": (2, 2), "8": (2, 4)}
ANCHO_UTIL, ALTO_UTIL, MARGEN = 200.0, 287.0, 5.0
# Tope de las letras (pt) por formato: título y precio (se achican para que entren)
LETRAS = {"1": (72, 200), "2": (54, 140), "4": (36, 90), "8": (24, 52)}
REDONDEOS = [("1", "Sin redondear"), ("10", "A $ 10"), ("50", "A $ 50"), ("100", "A $ 100"),
             ("1000", "A $ 1.000")]


def redondear_arriba(valor: float, paso: float) -> float:
    """Hacia arriba al múltiplo de `paso` (un cartel nunca baja el precio): 15.028 a $ 100 = 15.100."""
    if not paso or paso <= 1:
        return round(valor, 2)
    return math.ceil(round(valor, 2) / paso) * paso


def pesos(valor: float) -> str:
    """«$ 15.100» (sin decimales si es entero) o «$ 1.234,50»."""
    if abs(valor - round(valor)) < 0.005:
        return "$ " + f"{round(valor):,}".replace(",", ".")
    entero, decimales = f"{valor:,.2f}".split(".")
    return "$ " + entero.replace(",", ".") + "," + decimales


MM_POR_PT = 0.3528
ANCHO_LETRA = 0.62  # ancho medio de una letra en negrita, en «em»


def letra_que_entra(texto: str, ancho_mm: float, alto_mm: float, maximo: float, interlineado=1.1,
                    una_linea=False) -> float:
    """El tamaño (pt) más grande con el que `texto` entra en el lugar (cortando en palabras, o en
    una sola línea con `una_linea`: el precio no se parte), sin pasar de `maximo`. Los saltos de
    línea del texto se respetan."""
    lineas_texto = [linea for linea in (texto or "").split("\n")] or [""]
    pt = maximo
    while pt > 6:
        por_linea = max(1, int(ancho_mm / (pt * MM_POR_PT * ANCHO_LETRA)))
        if una_linea:
            if len(texto or "") <= por_linea and pt * MM_POR_PT * interlineado <= alto_mm:
                return round(pt, 1)
            pt *= 0.92
            continue
        lineas = 0
        for linea in lineas_texto:
            palabras, actual = linea.split(), 0
            cuenta = 1
            for palabra in palabras:
                if len(palabra) > por_linea:
                    cuenta = 999  # una palabra sola no entra: hay que achicar
                    break
                if actual and actual + 1 + len(palabra) > por_linea:
                    cuenta += 1
                    actual = len(palabra)
                else:
                    actual += (1 if actual else 0) + len(palabra)
            lineas += cuenta
        if lineas * pt * MM_POR_PT * interlineado <= alto_mm:
            return round(pt, 1)
        pt *= 0.92
    return 6.0


def ubicaciones(formato: str) -> list[dict]:
    """Posición (mm) de cada cartel en la hoja, de izquierda a derecha y de arriba a abajo."""
    columnas, filas = FORMATOS[formato]
    ancho, alto = ANCHO_UTIL / columnas, ALTO_UTIL / filas
    return [{"x": MARGEN + c * ancho, "y": MARGEN + f * alto, "ancho": ancho, "alto": alto}
            for f in range(filas) for c in range(columnas)]
