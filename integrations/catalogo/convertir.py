"""Convierte la lista de precios de un proveedor (Excel o CSV) a la planilla modelo.

Cada proveedor manda su Excel con otras columnas. Un mapeo YAML por proveedor
(integrations/catalogo/proveedores/<proveedor>.yaml) dice qué columna es cuál. Sin
mapeo (--sugerir), propone uno a partir de los títulos del archivo.

    .venv/bin/python integrations/catalogo/convertir.py --sugerir data/privado/lista.xlsx
    .venv/bin/python integrations/catalogo/convertir.py \\
        integrations/catalogo/proveedores/ejemplo.yaml data/privado/lista.xlsx -o data/privado/lista.csv

En Odoo, lo mismo se hace desde la app «Costos y precios» → Listas de proveedores (módulo comercio_catalogo).
"""
from __future__ import annotations

import argparse
import csv
import sys
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parents[2] / "addons" / "comercio_catalogo"))
from catalogo.convertir import (  # noqa: E402
    COLUMNAS,
    convertir,
    encontrar_encabezado,
    filas_con_titulos,
    leer_tabla,
    sugerir_mapeo,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mapeo", type=Path, nargs="?")
    parser.add_argument("archivo", type=Path)
    parser.add_argument("-o", "--salida", type=Path)
    parser.add_argument("--sugerir", action="store_true", help="proponer un mapeo según los títulos")
    args = parser.parse_args()
    if args.sugerir:
        tabla = leer_tabla(args.archivo.read_bytes(), args.archivo.name)
        fila = encontrar_encabezado(tabla)
        print(yaml.safe_dump({"fila_encabezado": fila, "columnas": sugerir_mapeo(tabla[fila - 1])},
                             allow_unicode=True, sort_keys=False))
        return 0
    if not args.mapeo or not args.salida:
        parser.error("hace falta el mapeo y -o salida (o --sugerir)")
    mapeo = yaml.safe_load(args.mapeo.read_text(encoding="utf-8"))
    tabla = leer_tabla(args.archivo.read_bytes(), args.archivo.name, mapeo.get("hoja"),
                       monedas=(mapeo.get("ajustes") or {}).get("moneda") == "mixta")
    salida = convertir(mapeo, filas_con_titulos(tabla, mapeo.get("fila_encabezado", 1)))
    with args.salida.open("w", newline="", encoding="utf-8-sig") as f:
        # Sin las columnas de la cuenta del costo («precio_lista», «calculo»…)
        w = csv.DictWriter(f, COLUMNAS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(salida)
    print(f"{len(salida)} productos de {mapeo['proveedor']} → {args.salida}")
    return 0


def principal() -> int:
    """main() con mensajes claros en vez de trazas de Python para los errores de archivo."""
    try:
        return main()
    except (OSError, ValueError, KeyError, IndexError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        print(f"Error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(principal())
