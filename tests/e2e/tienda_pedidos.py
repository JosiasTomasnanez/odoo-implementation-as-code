"""Prueba de punta a punta de la compra en la tienda online (fase 3, ADR 0033) contra la demo.

Con los productos ficticios del lab (infra/scripts/lab-tienda-ejemplo.py) y el conector del lab:

1. Compra con pago simulado aprobado → el pedido queda pago y el conector lo crea CONFIRMADO en
   Odoo (con su entrega), una sola vez, con el total que pagó el cliente.
2. La última unidad: varios pedidos a la vez → uno solo la reserva; los demás «no alcanza».
3. Pago rechazado → se libera la reserva (el stock vuelve a estar disponible).
4. Lo que manda el navegador no cambia el precio (un campo de precio de más se rechaza) y sin
   Turnstile o desde otro origen no se arma nada.

Uso: make e2e-tienda-pedidos
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

RAIZ = Path(__file__).resolve().parents[2]
TIENDA = "https://demo.comercio-ejemplo.example"
TOKEN_PRUEBA = "XXXX.DUMMY.TOKEN.XXXX"  # Turnstile con las claves de prueba de Cloudflare
c = connect(load_environment("lab"))


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


def http(metodo: str, ruta: str, datos: dict | None = None, origen: str = TIENDA, form: dict | None = None):
    cuerpo, tipo = None, "application/json"
    if datos is not None:
        cuerpo = json.dumps(datos).encode()
    if form is not None:
        cuerpo, tipo = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    req = urllib.request.Request(
        TIENDA + ruta,
        data=cuerpo,
        method=metodo,
        headers={
            "Content-Type": tipo,
            "Origin": origen,
            "Accept": "application/json",
            "User-Agent": "e2e-tienda",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# Pedidos de esta corrida: al final se rechazan los que quedaron sin pagar
PENDIENTES: list[tuple[str, str]] = []


def pedir(slug: str, cantidad: int = 1, **extra):
    datos = {
        "lineas": [{"slug": slug, "cantidad": cantidad}],
        "nombre": "Cliente Prueba",
        "email": "prueba@example.com",
        "telefono": "351 000-0000",
        "turnstile": TOKEN_PRUEBA,
    } | extra
    estado, d = http("POST", "/api/pedido", datos)
    if estado == 200 and d.get("pago"):
        PENDIENTES.append(id_y_token(d["pago"]))
    return estado, d


def id_y_token(url_pago: str) -> tuple[str, str]:
    m = re.search(r"/pago/simulado/([0-9a-f]{32})\?t=([0-9a-f]{32})", url_pago)
    assert m, url_pago
    return m.group(1), m.group(2)


def slug_de(nombre: str) -> str:
    html = (
        urllib.request.urlopen(
            urllib.request.Request(
                f"{TIENDA}/buscar/?q={urllib.parse.quote(nombre)}", headers={"User-Agent": "e2e-tienda"}
            )
        )
        .read()
        .decode()
    )
    m = re.search(r"/producto/([a-z0-9-]+)/", html)
    assert m, nombre
    return m.group(1)


def poner_stock(tmpl_nombre: str, cantidad: float) -> int:
    # Puede haber otro producto con el mismo nombre (de las listas de proveedores): el publicado
    campos = ["id", "comercio_tienda_publicar"]
    hallados = c.search_read("product.template", [("name", "=", tmpl_nombre)], campos)
    t = sorted(hallados, key=lambda x: not x["comercio_tienda_publicar"])[0]["id"]
    pid = c.search_read("product.product", [("product_tmpl_id", "=", t)], ["id"])[0]["id"]
    loc = c.search_read("stock.warehouse", [], ["lot_stock_id"], limit=1)[0]["lot_stock_id"][0]
    q = c.search_read("stock.quant", [("product_id", "=", pid), ("location_id", "=", loc)], ["id"], limit=1)
    qid = q[0]["id"] if q else c.create("stock.quant", {"product_id": pid, "location_id": loc})
    # «cantidad» es lo LIBRE que tiene que quedar: se suma lo que ya está reservado por pedidos de
    # corridas anteriores (el lab se comparte y esos pedidos siguen confirmados sin entregar).
    p = c.search_read("product.product", [("id", "=", pid)], ["qty_available", "free_qty"])[0]
    cantidad += max(0.0, p["qty_available"] - p["free_qty"])
    c.write("stock.quant", [qid], {"inventory_quantity": cantidad})
    c.call("stock.quant", "action_apply_inventory", [qid])
    return pid


def main() -> int:
    nombre = "Cinta métrica 5 m × 19 mm"
    pid = poner_stock(nombre, 12)
    conector()
    slug = slug_de("cinta metrica")

    # 1. Compra aprobada → Odoo
    estado, d = pedir(slug, 2)
    assert estado == 200 and d.get("ok"), (estado, d)
    pedido_id, token = id_y_token(d["pago"])
    estado, d2 = http("POST", "/api/pago/simulado", form={"id": pedido_id, "t": token, "decision": "aprobar"})
    assert estado == 200 and d2["estado"] == "pagado", (estado, d2)
    estado, d3 = http("POST", "/api/pago/simulado", form={"id": pedido_id, "t": token, "decision": "aprobar"})
    # El mismo aviso dos veces no cambia nada (si el conector del lab ya lo llevó, figura «en_odoo»)
    assert d3["estado"] in ("pagado", "en_odoo"), d3
    conector()
    conector()
    ordenes = c.search_read(
        "sale.order",
        [("comercio_tienda_ref", "=", pedido_id)],
        ["state", "amount_total", "picking_ids", "name"],
    )
    assert len(ordenes) == 1 and ordenes[0]["state"] == "sale" and ordenes[0]["picking_ids"], ordenes
    precio = c.read("product.product", [pid], ["lst_price"])[0]["lst_price"]
    assert abs(ordenes[0]["amount_total"] - 2 * precio) < 1, (ordenes[0]["amount_total"], precio)
    print(f"1. Pagado → {ordenes[0]['name']} confirmado en Odoo con su entrega, una sola vez ✓")

    # 2. Última unidad: margen 1 + 1 disponible
    poner_stock(nombre, 2)  # libre: margen 1 + 1 para vender (lo reservado en Odoo se suma solo)
    conector()
    with ThreadPoolExecutor(max_workers=6) as ex:
        resultados = list(ex.map(lambda _: pedir(slug, 1), range(6)))
    ok = [d for e, d in resultados if e == 200]
    sin = [d for e, d in resultados if e == 409]
    assert len(ok) == 1 and len(sin) == 5, [e for e, _ in resultados]
    print("2. Seis compras a la vez de la última unidad: una la reserva, cinco «no alcanza» ✓")

    # 3. Rechazo → se libera
    pid2, tok2 = id_y_token(ok[0]["pago"])
    estado, d4 = http("POST", "/api/pago/simulado", form={"id": pid2, "t": tok2, "decision": "rechazar"})
    assert d4["estado"] == "rechazado", d4
    estado, d5 = pedir(slug, 1)
    assert estado == 200, (estado, d5)
    pid3, tok3 = id_y_token(d5["pago"])
    http("POST", "/api/pago/simulado", form={"id": pid3, "t": tok3, "decision": "rechazar"})
    print("3. Pago rechazado: se libera la reserva y la unidad se puede volver a comprar ✓")

    # 4. Precios y protecciones
    e1, _ = pedir(slug, 1, precio=1)
    e2, _ = http(
        "POST",
        "/api/pedido",
        {
            "lineas": [{"slug": slug, "cantidad": 1, "precio": 1}],
            "nombre": "X Y",
            "email": "a@b.com",
            "turnstile": TOKEN_PRUEBA,
        },
    )
    e3, _ = http(
        "POST",
        "/api/pedido",
        {
            "lineas": [{"slug": slug, "cantidad": 1}],
            "nombre": "X Y",
            "email": "a@b.com",
            "turnstile": TOKEN_PRUEBA,
        },
        origen="https://otro.example",
    )
    e4, _ = http(
        "POST",
        "/api/pedido",
        {"lineas": [{"slug": slug, "cantidad": 1}], "nombre": "X Y", "email": "a@b.com", "turnstile": ""},
    )
    assert (e1, e2, e3) == (422, 422, 403) and e4 in (403, 422), (e1, e2, e3, e4)
    print("4. Un precio mandado por el navegador se rechaza; otro origen o sin Turnstile, tampoco ✓")
    print("Compra en la tienda: todo bien ✓")
    return 0


def limpiar() -> None:
    """Rechaza lo que quedó sin pagar (si no, sus reservas le restan stock a la próxima corrida)."""
    for pedido_id, token in PENDIENTES:
        http("POST", "/api/pago/simulado", form={"id": pedido_id, "t": token, "decision": "rechazar"})


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        limpiar()
