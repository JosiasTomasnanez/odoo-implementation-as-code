"""Prueba de punta a punta de la sincronización Odoo → tienda online (ADR 0033) en el lab.

Usa la tienda de prueba (demo.comercio-ejemplo.example) y el conector del lab (TIENDA=1 en el .env y
claves en infra/docker/conector-tienda.lab.env). Con productos FICTICIOS nuevos en cada corrida:

1. Un producto publicado llega a la tienda con su precio con IVA, su stock libre y su rubro.
2. Un cambio de precio y de stock llega en la vuelta siguiente.
3. Una oferta en la lista «Tienda online» llega con el precio anterior tachado.
4. Mandar todo dos veces no duplica nada (idempotencia).
5. Despublicado: deja de estar publicado en la tienda.
6. El usuario del conector no puede leer clientes ni costos ni escribir productos.
7. La tienda rechaza un lote sin firma.

Uso: make e2e-tienda-sync
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

RAIZ = Path(__file__).resolve().parents[2]
ENV_CONECTOR = RAIZ / "infra/docker/conector-tienda.lab.env"
NODE = f"{Path.home()}/.local/node22/bin"
c = connect(load_environment("lab"))
MARCA = str(int(time.time()))[-6:]


def conector(*args: str) -> None:
    r = subprocess.run(
        [
            "bash",
            "-c",
            "source infra/scripts/lib.sh; compose run --rm -T conector-tienda --una-vez " + " ".join(args),
        ],
        cwd=RAIZ,
        env={**os.environ, "STACK": "lab", "TIENDA": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]


def d1(sql: str) -> list[dict]:
    r = subprocess.run(
        [
            "npx",
            "wrangler",
            "d1",
            "execute",
            "comercio-ejemplo-tienda-demo",
            "--remote",
            "--json",
            "--command",
            sql,
        ],
        cwd=RAIZ / "web/tienda",
        env={**os.environ, "PATH": f"{NODE}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout)[0]["results"]


def en_tienda(pid: int) -> dict:
    filas = d1(f"""SELECT p.publicado, p.consultar, p.categoria_id, s.libre_odoo,
        pr.precio, pr.precio_anterior,
        (SELECT COUNT(*) FROM precios WHERE producto_id = p.id_odoo) AS n_precios,
        (SELECT COUNT(*) FROM listas_precios) AS n_listas
        FROM productos p JOIN stock s ON s.producto_id = p.id_odoo
        LEFT JOIN precios pr ON pr.producto_id = p.id_odoo
            AND pr.lista_id = (SELECT id_odoo FROM listas_precios WHERE publica = 1)
        WHERE p.id_odoo = {int(pid)}""")
    return filas[0] if filas else {}


def poner_stock(pid: int, cantidad: float) -> None:
    loc = c.search_read("stock.warehouse", [], ["lot_stock_id"], limit=1)[0]["lot_stock_id"][0]
    hay = c.search_read("stock.quant", [("product_id", "=", pid), ("location_id", "=", loc)], ["id"], limit=1)
    if hay:
        q = hay[0]["id"]
        c.write("stock.quant", [q], {"inventory_quantity": cantidad})
    else:
        q = c.create("stock.quant", {"product_id": pid, "location_id": loc, "inventory_quantity": cantidad})
    c.call("stock.quant", "action_apply_inventory", [q])


def con_iva(pid: int, precio: float) -> int:
    """Lo que tiene que mostrar la tienda: el precio final con IVA, en centavos."""
    t = c.read("product.product", [pid], ["taxes_id"])[0]["taxes_id"]
    if not t:
        return round(precio * 100)
    incl = c.read("account.tax", t, ["price_include", "amount"])
    final = precio
    for i in incl:
        if not i["price_include"]:
            final += precio * i["amount"] / 100
    return round(final * 100)


def main() -> int:
    tienda = c.search_read("product.pricelist", [("comercio_tienda_publica", "=", True)], ["id"])
    assert tienda, "falta la lista «Tienda online» (make apply ENV=lab)"
    lista = tienda[0]["id"]
    regla = None
    cat = c.create("pos.category", {"name": f"[EJ] Rubro tienda {MARCA}"})
    tmpl = c.create(
        "product.template",
        {
            "name": f"[EJ] Producto tienda {MARCA}",
            "type": "consu",
            "is_storable": True,
            "list_price": 1000.0,
            "pos_categ_ids": [(6, 0, [cat])],
        },
    )
    pid = c.search_read("product.product", [("product_tmpl_id", "=", tmpl)], ["id"])[0]["id"]
    try:
        c.write("product.template", [tmpl], {"comercio_tienda_publicar": True})
        poner_stock(pid, 5)
        conector()
        t = en_tienda(pid)
        assert t and t["publicado"] == 1 and t["categoria_id"] == cat and t["libre_odoo"] == 5, t
        assert t["precio"] == con_iva(pid, 1000.0), t
        print(f"1. Publicado: llega con precio {t['precio'] / 100:.2f}, stock 5 y su rubro ✓")

        c.write("product.template", [tmpl], {"list_price": 1500.0})
        poner_stock(pid, 2)
        conector()
        t = en_tienda(pid)
        assert t["precio"] == con_iva(pid, 1500.0) and t["libre_odoo"] == 2, t
        print("2. Cambio de precio y de stock: llegan en la vuelta siguiente ✓")

        regla = c.create(
            "product.pricelist.item",
            {
                "pricelist_id": lista,
                "applied_on": "1_product",
                "product_tmpl_id": tmpl,
                "compute_price": "fixed",
                "fixed_price": 1200.0,
            },
        )
        conector()
        t = en_tienda(pid)
        assert t["precio"] == con_iva(pid, 1200.0) and t["precio_anterior"] == con_iva(pid, 1500.0), t
        print("3. Oferta en «Tienda online»: precio rebajado y el anterior para tachar ✓")

        proveedor = c.create("res.partner", {"name": f"[EJ] Proveedor tienda {MARCA}", "supplier_rank": 1})
        c.create(
            "product.supplierinfo",
            {"partner_id": proveedor, "product_tmpl_id": tmpl, "price": 700.0, "min_qty": 6},
        )
        poner_stock(pid, 1)
        conector()
        t = en_tienda(pid)
        r = c.read("product.template", [tmpl], ["comercio_tienda_bajo_minimo", "comercio_tienda_reponer"])[0]
        assert (
            t["consultar"] == 1
            and r["comercio_tienda_bajo_minimo"]
            and r["comercio_tienda_reponer"] == "pendiente"
        ), (t, r)
        print("4a. Bajo el mínimo: la tienda lo ofrece «a consultar» y entra a «A reponer» ✓")
        accion = c.call("product.template", "action_comercio_tienda_pedir", [tmpl])
        orden = c.read("purchase.order", [accion["res_id"]], ["partner_id", "order_line", "state"])[0]
        linea = c.read("purchase.order.line", orden["order_line"], ["product_id", "product_qty"])
        assert orden["partner_id"][0] == proveedor and orden["state"] == "draft", orden
        assert any(x["product_id"][0] == pid and x["product_qty"] == 6 for x in linea), linea
        assert (
            c.read("product.template", [tmpl], ["comercio_tienda_reponer"])[0]["comercio_tienda_reponer"]
            == "pedido"
        )
        print("4b. «Pedir al proveedor»: solicitud en borrador con su cantidad mínima; queda «Pedido» ✓")
        poner_stock(pid, 5)
        conector()
        t = en_tienda(pid)
        r = c.read("product.template", [tmpl], ["comercio_tienda_bajo_minimo", "comercio_tienda_reponer"])[0]
        assert (
            t["consultar"] == 0 and not r["comercio_tienda_bajo_minimo"] and not r["comercio_tienda_reponer"]
        ), (t, r)
        c.call("purchase.order", "button_cancel", [orden["id"]])
        print("4c. Repuesto: sale de «A reponer» y se vende normal ✓")

        conector("--todo")
        conector("--todo")
        t = en_tienda(pid)
        assert t["n_precios"] == t["n_listas"], t  # un precio por lista (la de la tienda y las mayoristas)
        print("5. Mandar todo dos veces no duplica nada ✓")

        c.write("product.template", [tmpl], {"comercio_tienda_publicar": False})
        conector()
        assert en_tienda(pid)["publicado"] == 0
        print("6. Despublicado: deja de estar publicado en la tienda ✓")

        clave = next(
            linea.split("=", 1)[1]
            for linea in ENV_CONECTOR.read_text().splitlines()
            if linea.startswith("ODOO_API_KEY=")
        )
        for modelo, metodo, kw in (
            ("res.partner", "search_read", {"domain": [("id", "!=", 0)], "fields": ["email"], "limit": 5}),
            ("product.product", "search_read", {"domain": [], "fields": ["standard_price"], "limit": 1}),
            ("product.template", "write", {"ids": [tmpl], "vals": {"list_price": 1}}),
        ):
            req = urllib.request.Request(
                f"http://localhost:8069/json/2/{modelo}/{metodo}",
                data=json.dumps(kw).encode(),
                method="POST",
                headers={
                    "Authorization": f"bearer {clave}",
                    "X-Odoo-Database": "lab",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req) as r:
                    datos = json.loads(r.read())
                    # Un usuario portal solo se ve a sí mismo: ningún otro contacto ni dato de producto.
                    assert (
                        modelo == "res.partner" and all(not d.get("email") for d in datos) and len(datos) <= 1
                    ), datos
            except urllib.error.HTTPError as e:
                assert e.code == 403, (modelo, e.code)
        print("7. El usuario del conector no ve clientes ni costos ni escribe productos ✓")

        req = urllib.request.Request(
            "https://demo.comercio-ejemplo.example/api/conector/lote",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "e2e"},
        )
        try:
            urllib.request.urlopen(req)
            raise AssertionError("aceptó un lote sin firma")
        except urllib.error.HTTPError as e:
            assert e.code == 401, e.code
        print("8. La tienda rechaza un lote sin firma ✓")
    finally:
        if regla:
            c.call("product.pricelist.item", "unlink", [regla])
        c.write("product.template", [tmpl], {"comercio_tienda_publicar": False, "active": False})
        conector()
    print("Sincronización con la tienda: todo bien ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
