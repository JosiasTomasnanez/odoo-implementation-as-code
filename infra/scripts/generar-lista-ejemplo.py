"""Genera la lista de ejemplo de «[EJ] Ferretera Ejemplo» (FICTICIA, parecida a la de FC), en dos
versiones, para mostrarle al negocio todo lo que puede pasar con una lista de proveedor:

    data/ejemplos/listas/ferretera-ejemplo-1.xlsx   la primera lista
    data/ejemplos/listas/ferretera-ejemplo-2.xlsx   la siguiente: subas, bajas, un producto nuevo,
                                                    uno que vuelve y una columna que cambió de nombre

Tres hojas, cada una se importa como una «parte» de la lista:

- «Lista general»: en pesos, sin IVA. Títulos y notas arriba de los encabezados; familias en
  una fila aparte («ABRAZADERAS») con solo la medida debajo; descripción partida en dos
  columnas; un código de barras de fábrica; «Desc. %» del proveedor en algunas filas (ofertas);
  filas sin precio («SIN STOCK», «Consultar», 0); un código repetido; «Promociones vigentes»
  en texto, como FC (por unidad y por cantidad); y una columna «PRECIO FINAL (cálculo
  interno)» que agregó el comercio y que NO es el costo.
- «Bulones»: precio por unidad suelta y precio por unidad comprando la caja cerrada, con las
  unidades de la caja (dos precios).
- «Importados USD»: en dólares, con IVA incluido y alícuota por fila (10,5 y 21).

Lo usa infra/scripts/lab-lista-ejemplo.py (make lab-completo) y la prueba a mano
(docs/runbooks/prueba-visual.md, sección 2).

    .venv/bin/python infra/scripts/generar-lista-ejemplo.py
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Font

DESTINO = Path(__file__).resolve().parents[2] / "data" / "ejemplos" / "listas"


def ean13(doce: str) -> str:
    """Los 12 primeros dígitos + el dígito verificador."""
    suma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(doce))
    return doce + str((10 - suma % 10) % 10)


# (familia o None, código, detalle, descripción, código de barras, precio, desc. %) - None en
# código = fila de familia. El precio puede ser texto («SIN STOCK»).
GENERAL_1 = [
    ("ABRAZADERAS", None),
    ("EJ-1001", "Abrazadera sinfín", "10-16 mm", "", 120.0, None),
    ("EJ-1002", "Abrazadera sinfín", "16-25 mm", "", 135.5, 10),       # oferta del proveedor
    ("CANDADOS", None),
    ("EJ-2001", "Candado bronce", "40 mm", "", 4850.0, None),
    ("EJ-2002", "Candado bronce", "50 mm", "", "SIN STOCK", None),
    ("EJ-2003", "Candado acero", "60 mm", "", "Consultar", None),
    ("CINTAS", None),
    ("EJ-3001", "Cinta métrica", "5 m", ean13("779123400001"), 2300.0, None),
    ("EJ-3002", "Cinta aisladora negra", "20 m", "", 0, None),
    ("HERRAMIENTAS", None),
    ("EJ-4001", "Martillo carpintero", "27 mm", "", 9870.0, None),
    ("EJ-4002", "Pinza universal", '8"', "", 7450.0, 5),
    ("EJ-4002", "Pinza universal", '8" (repetida)', "", 7450.0, 5),    # el proveedor repite el código
    ("EJ-4003", "Destornillador Phillips", "1/4 x 4", "", 1980.0, None),
    ("TORNILLOS", None),
    ("EJ-5001", "Tornillo fix", "4 x 40", "", 18.4, None),
    ("EJ-5002", "Tornillo fix", "5 x 50", "", 26.9, None),
]


def general_2():
    """La lista siguiente: suba chica (se aplica sola), suba grande (espera), el candado de 50 vuelve
    a tener precio, la cinta métrica ya no está (baja) y aparece una llave francesa (nueva)."""
    cambios = {"EJ-4001": 1.03, "EJ-2001": 1.25, "EJ-5001": 1.04, "EJ-5002": 1.04}
    filas = []
    for fila in GENERAL_1:
        if fila[1] is None:
            filas.append(fila)
            continue
        codigo, detalle, desc, barras, precio, oferta = fila
        if codigo == "EJ-3001":
            continue
        if codigo == "EJ-2002":
            precio = 6100.0
        elif isinstance(precio, float) and codigo in cambios:
            precio = round(precio * cambios[codigo], 2)
        filas.append((codigo, detalle, desc, barras, precio, oferta))
        if codigo == "EJ-4003":
            filas.append(("EJ-4004", "Llave francesa", '10"', "", 11250.0, None))
    return filas


# Promociones del proveedor en texto, como las de FC: por unidad (baja el costo) y por
# cantidad (precio por mayor). En la lista 2 se termina la del martillo: el costo sube por eso.
PROMOCIONES_1 = {"EJ-4001": "5% DTO. X UNIDAD",
                 "EJ-4003": "10% DTO. X 6 UNIDADES / 15% DTO. X 12 UNIDADES"}
PROMOCIONES_2 = {"EJ-4003": PROMOCIONES_1["EJ-4003"]}

BULONES_1 = [
    ("BULONES", None),
    ("BU-0101", "Bulón cabeza hexagonal", "1/4 x 1", 100, 42.0, 36.0),
    ("BU-0102", "Bulón cabeza hexagonal", "1/4 x 2", 100, 51.0, 44.0),
    ("BU-0201", "Bulón carrocero", "5/16 x 2", 50, 88.0, 78.0),
    ("TUERCAS", None),
    ("TU-0101", "Tuerca hexagonal", "1/4", 200, 9.5, 8.0),
    ("TU-0102", "Tuerca autofrenante", "5/16", 100, 21.0, 18.5),
    ("ARANDELAS", None),
    ("AR-0101", "Arandela plana", "1/4", 500, 3.2, 2.7),
]

# (código, descripción, precio en dólares con IVA, IVA %)
IMPORTADOS_1 = [
    ("IM-01", "Taladro percutor 13 mm 650 W", 85.0, 21),
    ("IM-02", "Amoladora angular 115 mm 850 W", 62.0, 21),
    ("IM-03", "Juego de mechas acero rápido x 13", 15.0, 21),
    ("IM-04", "Cinta de embalar transparente 48 mm (caja x 36)", 24.0, 10.5),
]


def hoja_general(libro, filas, titulo_precio, promociones):
    h = libro.create_sheet("Lista general")
    h.append(["FERRETERA EJEMPLO S.A. (ficticia)"])
    h.append(["Lista de precios - precios SIN IVA. Bonificación 5 % en factura. Flete 2,5 %."])
    h.append(["Consultas: ventas@ferretera-ejemplo.invalid"])
    h.append([])
    h.append(["Código", "Detalle", "Descripción del producto", "Código de barras", titulo_precio, "Desc. %",
              "Promociones vigentes", "PRECIO FINAL (cálculo interno)"])
    for c in h[5]:
        c.font = Font(bold=True)
    for fila in filas:
        if fila[1] is None:
            h.append(["", fila[0]])  # la familia, sola en su fila
            h.cell(h.max_row, 2).font = Font(bold=True)
            continue
        codigo, detalle, desc, barras, precio, oferta = fila
        # La cuenta que hacía el comercio en su planilla (5 %, IVA, margen): no es del proveedor
        final = round(precio * 0.95 * 1.21 * 1.4, 2) if isinstance(precio, float) and precio else ""
        h.append([codigo, detalle, desc, barras, precio, oferta, promociones.get(codigo, ""), final])


def hoja_bulones(libro, filas, suba=1.0):
    h = libro.create_sheet("Bulones")
    h.append(["FERRETERA EJEMPLO S.A. - LISTA DE PRECIOS BULONES (sin IVA)"])
    h.append([])
    # Dos precios por unidad: suelta, o comprando la caja cerrada (más barato)
    h.append(["Código", "Detalle", "Descripción / medidas", "Unidades x caja", "Precio Unit. sin IVA",
              "Precio x caja (c/u)"])
    for c in h[3]:
        c.font = Font(bold=True)
    for fila in filas:
        if fila[1] is None:
            h.append(["", fila[0]])
            continue
        codigo, detalle, desc, por_caja, unidad, caja = fila
        h.append([codigo, detalle, desc, por_caja, round(unidad * suba, 2), round(caja * suba, 2)])


def hoja_importados(libro, filas):
    h = libro.create_sheet("Importados USD")
    h.append(["Importados - precios en DÓLARES con IVA incluido"])
    h.append([])
    h.append(["Código", "Descripción", "Precio U$S c/IVA", "IVA %"])
    for c in h[3]:
        c.font = Font(bold=True)
    for fila in filas:
        h.append(list(fila))


def generar() -> list[Path]:
    DESTINO.mkdir(parents=True, exist_ok=True)
    salida = []
    for version, general, titulo, suba in ((1, GENERAL_1, "Precio de lista", 1.0),
                                           (2, general_2(), "P. Lista $", 1.08)):
        libro = openpyxl.Workbook()
        libro.remove(libro.active)
        # En la 2 el título del precio cambió («formato cambiado») y se terminó la promoción del martillo
        hoja_general(libro, general, titulo, PROMOCIONES_1 if version == 1 else PROMOCIONES_2)
        hoja_bulones(libro, BULONES_1, suba)
        hoja_importados(libro, IMPORTADOS_1)
        ruta = DESTINO / f"ferretera-ejemplo-{version}.xlsx"
        libro.save(ruta)
        salida.append(ruta)
    return salida


if __name__ == "__main__":
    for ruta in generar():
        print(ruta.relative_to(DESTINO.parents[2]))
