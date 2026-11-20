"""Importa productos y sus proveedores a Odoo desde la planilla modelo.

Por defecto **simula**: muestra qué productos crearía, a cuáles les agregaría un
proveedor, qué datos cambiarían y qué filas hay que revisar. Con --aplicar lo hace y
después verifica que una nueva simulación ya no tenga cambios (idempotente).

    .venv/bin/python integrations/catalogo/importar.py -e lab data/plantillas/productos.csv
    .venv/bin/python integrations/catalogo/importar.py -e lab planilla.csv --aplicar --informe informe.csv

Reglas de códigos: docs/areas/codigos.md. Columnas: integrations/catalogo/README.md.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import sys
import zipfile
from collections import Counter
from pathlib import Path

# El motor vive en el módulo comercio_catalogo (lo comparte con la pantalla de Odoo)
sys.path.insert(0, str(Path(__file__).parents[2] / "addons" / "comercio_catalogo"))
from catalogo.convertir import leer_tabla  # noqa: E402
from catalogo.odoo_api import actualizar_costos, aplicar, categorias_con_stock, sacar_foto  # noqa: E402
from catalogo.plan import (  # noqa: E402
    ACTUALIZAR,
    BAJA,
    NUEVO,
    POSIBLE_DUPLICADO,
    REVISAR,
    SIN_CAMBIOS,
    VINCULAR,
    planificar,
)

from odoo_iac.client import connect  # noqa: E402
from odoo_iac.settings import load_environment  # noqa: E402


def leer_planilla(ruta: Path) -> list[dict]:
    """La planilla modelo (CSV); misma lectura que el módulo (UTF-8 o Windows, ; o ,)."""
    if ruta.suffix.lower() not in (".csv", ".txt"):
        raise ValueError(f"{ruta.name}: la planilla modelo es un CSV (para un Excel de proveedor, "
                         "usar primero convertir.py)")
    tabla = leer_tabla(ruta.read_bytes(), ruta.name)
    if not tabla:
        raise ValueError(f"{ruta.name} está vacío")
    return [dict(zip(tabla[0], f, strict=False)) for f in tabla[1:] if any(c.strip() for c in f)]


def mostrar(acciones) -> None:
    for a in acciones:
        if a.tipo != SIN_CAMBIOS:
            print(f"  fila {a.fila:>4}  {a.tipo:<11} {a.detalle}")
            for aviso in a.avisos:
                print(f"             aviso: {aviso}")
    resumen = Counter(a.tipo for a in acciones)
    tipos = (NUEVO, VINCULAR, ACTUALIZAR, SIN_CAMBIOS, POSIBLE_DUPLICADO, REVISAR, BAJA)
    print("\nResumen: " + ", ".join(f"{resumen[t]} {t}" for t in tipos))


def guardar_informe(acciones, ruta: Path) -> None:
    with ruta.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["fila", "accion", "detalle", "avisos", "candidatos"])
        for a in acciones:
            candidatos = " | ".join(f"{c.id}: {c.nombre} ({c.puntaje:.0%})" for c in a.candidatos)
            w.writerow([a.fila, a.tipo, a.detalle, " | ".join(a.avisos), candidatos])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("planilla", type=Path)
    parser.add_argument("-e", "--entorno", default="lab")
    parser.add_argument("--aplicar", action="store_true", help="aplicar los cambios (si no, solo simula)")
    parser.add_argument("--informe", type=Path, help="guardar el plan en un CSV (para revisar o archivar)")
    args = parser.parse_args()

    filas = leer_planilla(args.planilla)
    c = connect(load_environment(args.entorno))
    hoy = datetime.date.today().isoformat()
    con_stock = categorias_con_stock(c)
    acciones = planificar(filas, sacar_foto(c, hoy), con_stock)
    print(f"{args.planilla} → {args.entorno}: {len(filas)} filas")
    mostrar(acciones)
    if args.informe:
        guardar_informe(acciones, args.informe)
        print(f"Informe: {args.informe}")
    if not args.aplicar:
        print("\nSimulación: no se cambió nada. Para aplicar: --aplicar")
        return 0

    creados = aplicar(c, acciones, hoy)
    tocados = [creados.get(a.tmpl) if isinstance(a.tmpl, str) else a.tmpl for a in acciones
               if a.tipo in (NUEVO, VINCULAR, ACTUALIZAR, BAJA)]
    costos = actualizar_costos(c, tocados, hoy)  # P-044 (salvo los de costo manual)
    print(f"\nAplicado. Costo actualizado en {len(costos)} productos. Verificando...")
    pendientes = [a for a in planificar(filas, sacar_foto(c, hoy), con_stock)
                  if a.tipo in (NUEVO, VINCULAR, ACTUALIZAR)]
    if pendientes:
        print("✗ La verificación encontró cambios sin aplicar:")
        mostrar(pendientes)
        return 1
    print("✓ Verificado: Odoo coincide con la planilla (las filas a revisar y los posibles "
          "duplicados no se tocaron).")
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
