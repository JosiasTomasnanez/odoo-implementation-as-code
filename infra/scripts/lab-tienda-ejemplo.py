"""Carga en el Odoo del LAB el catálogo ficticio de la tienda demo y lo publica (ADR 0033).

Para probar la tienda con el circuito real (Odoo → conector → tienda) sin mostrar en una dirección
pública los precios reales del cliente. Datos de web/tienda/src/data/catalogo.ts (marcas
inventadas, precios de ejemplo) y las ilustraciones de web/tienda/public/img (pasadas a PNG).

Idempotente: busca cada producto por su código de barras y cada rubro por su nombre. Solo lab.

Uso: .venv/bin/python infra/scripts/lab-tienda-ejemplo.py   (después: el conector con --todo)

Fotos reales para probar el diseño: --foto "parte del nombre=ruta/a/la/foto.jpg" (se puede repetir).
La foto va a la ficha del producto en el lab en lugar de la ilustración; no se versiona.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

RAIZ = Path(__file__).resolve().parents[2]
TIENDA = RAIZ / "web/tienda"
NODE = f"{Path.home()}/.local/node22/bin"


def catalogo() -> dict:
    r = subprocess.run(
        ["node", "scripts/exportar-ejemplo.ts"],
        cwd=TIENDA,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{NODE}:{os.environ['PATH']}"},
        check=True,
    )
    return json.loads(r.stdout)


def png_de_svgs(rutas: list[str]) -> dict[str, bytes]:
    """Las ilustraciones son SVG; Odoo y la tienda guardan JPEG/PNG/WebP: se dibujan a 800 px."""
    from playwright.sync_api import sync_playwright

    salida = {}
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 800, "height": 800})
        for ruta in rutas:
            svg = (TIENDA / "public" / ruta.lstrip("/")).read_text()
            svg = svg.replace("<svg ", '<svg width="800" height="800" ', 1)
            pag.set_content('<html><body style="margin:0">' + svg + "</body></html>")
            salida[ruta] = pag.screenshot(clip={"x": 0, "y": 0, "width": 800, "height": 800}, type="png")
        nav.close()
    return salida


def fotos_reales(args: list[str]) -> dict[str, bytes]:
    """--foto "texto=ruta": el primer producto cuyo nombre contiene «texto» usa esa foto."""
    fotos = {}
    for i, a in enumerate(args):
        if a == "--foto" and i + 1 < len(args) and "=" in args[i + 1]:
            texto, ruta = args[i + 1].split("=", 1)
            fotos[texto.strip().lower()] = Path(ruta).expanduser().read_bytes()
    return fotos


def main() -> int:
    reales = fotos_reales(sys.argv[1:])
    env = load_environment("lab")
    c = connect(env)
    datos = catalogo()
    lista = c.search_read("product.pricelist", [("comercio_tienda_publica", "=", True)], ["id"])
    if not lista:
        raise SystemExit("Falta la lista «Tienda online»: make apply ENV=lab")
    lista = lista[0]["id"]
    almacen = c.search_read("stock.warehouse", [], ["lot_stock_id"], limit=1)[0]["lot_stock_id"][0]

    cats = {}
    for i, cat in enumerate(datos["categorias"]):
        hay = c.search_read("pos.category", [("name", "=", cat["nombre"])], ["id"], limit=1)
        cats[cat["slug"]] = (
            hay[0]["id"] if hay else c.create("pos.category", {"name": cat["nombre"], "sequence": 10 + i})
        )

    imagenes = png_de_svgs([p["imagen"] for p in datos["productos"] if p.get("imagen")])
    hechos = 0
    for p in datos["productos"]:
        vals = {
            "name": p["nombre"],
            "list_price": (p.get("precioAnterior") or p["precio"]),
            "pos_categ_ids": [(6, 0, [cats[p["categoria"]]])],
            "description_sale": p["descripcion"],
            "comercio_tienda_publicar": True,
            "comercio_tienda_nuevo_hasta": (date.today() + timedelta(days=30)).isoformat()
            if p.get("nuevo")
            else False,
            "sale_ok": True,
        }
        real = next((f for t, f in reales.items() if t in p["nombre"].lower()), None)
        if real:
            vals["image_1920"] = base64.b64encode(real).decode()
        elif p.get("imagen"):
            vals["image_1920"] = base64.b64encode(imagenes[p["imagen"]]).decode()
        hay = c.search_read("product.template", [("barcode", "=", p["codigo"])], ["id"], limit=1)
        if hay:
            tmpl = hay[0]["id"]
            c.write("product.template", [tmpl], vals)
        else:
            tmpl = c.create(
                "product.template", vals | {"barcode": p["codigo"], "type": "consu", "is_storable": True}
            )
        pid = c.search_read("product.product", [("product_tmpl_id", "=", tmpl)], ["id"])[0]["id"]
        # Oferta: regla de precio fijo en «Tienda online» (el precio de venta queda el de siempre)
        reglas = c.search_read(
            "product.pricelist.item", [("pricelist_id", "=", lista), ("product_tmpl_id", "=", tmpl)], ["id"]
        )
        if p.get("precioAnterior"):
            v = {
                "pricelist_id": lista,
                "applied_on": "1_product",
                "product_tmpl_id": tmpl,
                "compute_price": "fixed",
                "fixed_price": p["precio"],
            }
            if reglas:
                c.write("product.pricelist.item", [reglas[0]["id"]], v)
            else:
                c.create("product.pricelist.item", v)
        elif reglas:
            c.call("product.pricelist.item", "unlink", [r["id"] for r in reglas])
        # Stock: los que «hay en el local» con 12; los que no, en 0 (quedan «a consultar»)
        q = c.search_read(
            "stock.quant", [("product_id", "=", pid), ("location_id", "=", almacen)], ["id"], limit=1
        )
        qid = q[0]["id"] if q else c.create("stock.quant", {"product_id": pid, "location_id": almacen})
        c.write("stock.quant", [qid], {"inventory_quantity": 12 if p["stock"] else 0})
        c.call("stock.quant", "action_apply_inventory", [qid])
        hechos += 1
    print(f"{hechos} productos ficticios publicados en el lab; ahora: conector --todo --una-vez")
    return 0


if __name__ == "__main__":
    sys.exit(main())
