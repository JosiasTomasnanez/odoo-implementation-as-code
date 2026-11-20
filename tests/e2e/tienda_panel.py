"""Prueba de punta a punta del panel de pedidos de la tienda (fase 4) contra la demo y el lab.

1. Alta del dispositivo: con un código equivocado no; con el código de alta sí (cookie del equipo).
2. Entrar: PIN equivocado no; el PIN del empleado (de Odoo, «Usa el panel») sí. Sin dispositivo,
   el panel manda al alta.
3. Un pedido pago aparece en «Para preparar»; preparar → listo: el conector valida la entrega en
   Odoo y el pedido de venta queda «Listo para retirar»; el mail queda anotado (o enviado).
4. Retirado → Odoo «Retirado».
5. Sin sesión o desde otro origen no se puede tocar nada; muchos PIN equivocados bloquean.

El código de alta de la demo está en ~/panel-tienda-demo.txt (fuera de git).
Uso: make e2e-tienda-panel
"""

from __future__ import annotations

import http.cookiejar
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tienda_pedidos as tp  # noqa: E402  (reusa pedir, conector, http)

TIENDA = tp.TIENDA
c = tp.c
PIN = "2222"  # PIN ficticio del cajero de ejemplo (config/ejemplos/25-empleados.yaml)
CODIGO = Path.home().joinpath("panel-tienda-demo.txt").read_text().rsplit(":", 1)[1].strip()


class SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def navegador():
    jar = http.cookiejar.CookieJar()
    return jar, urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), SinRedireccion())


def post(op, ruta: str, datos: dict, origen: str = TIENDA, base: str = TIENDA) -> tuple[int, str]:
    req = urllib.request.Request(
        base + ruta,
        data=urllib.parse.urlencode(datos).encode(),
        method="POST",
        headers={
            "Origin": origen,
            "User-Agent": "e2e-panel",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        r = op.open(req, timeout=60)
        return r.status, r.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "")


def get(op, ruta: str, base: str = TIENDA) -> tuple[int, str, str]:
    try:
        r = op.open(urllib.request.Request(base + ruta, headers={"User-Agent": "e2e-panel"}), timeout=60)
        return r.status, r.read().decode(), ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), e.headers.get("Location", "")


def main() -> int:
    emp = c.search_read("hr.employee", [("name", "=", "[EJ] Cajero")], ["id"], limit=1)[0]["id"]
    c.write("hr.employee", [emp], {"comercio_tienda_panel": True})  # lo declara config/ejemplos (make apply)
    tp.conector()

    jar, op = navegador()
    e, _, loc = get(op, "/panel")
    assert e == 303 and loc.endswith("/panel/alta"), (e, loc)
    e, loc = post(op, "/api/panel/alta", {"codigo": "equivocado", "nombre": "PC de prueba"})
    assert "e=codigo" in loc, loc
    e, loc = post(op, "/api/panel/alta", {"codigo": CODIGO, "nombre": "PC de prueba"})
    assert e == 303 and loc.endswith("/panel") and any(k.name == "cf_disp" for k in jar), (e, loc)
    print("1. Alta del dispositivo: código equivocado no; el de alta sí ✓")

    e, html, _ = get(op, "/panel")
    assert "[EJ] Cajero" in html and 'name="pin"' in html, html[:300]
    e, loc = post(op, "/api/panel/entrar", {"empleado": emp, "pin": "0000"})
    assert "e=pin" in loc, loc
    e, loc = post(op, "/api/panel/entrar", {"empleado": emp, "pin": PIN})
    assert any(k.name == "cf_panel" for k in jar), [k.name for k in jar]
    print("2. Entrar: PIN equivocado no; el del empleado sí ✓")

    slug = tp.slug_de("candado")
    estado, d = tp.pedir(slug, 1)
    assert estado == 200, (estado, d)
    pid, tok = tp.id_y_token(d["pago"])
    tp.http("POST", "/api/pago/simulado", form={"id": pid, "t": tok, "decision": "aprobar"})
    tp.conector()
    numero = d["pedido"]
    e, html, _ = get(op, "/panel")
    assert numero in html, numero
    for tipo in ("preparar", "listo"):
        e, loc = post(op, "/api/panel/accion", {"pedido": pid, "tipo": tipo})
        assert e == 303, (tipo, e)
    tp.conector()
    so = c.search_read(
        "sale.order", [("comercio_tienda_ref", "=", pid)], ["comercio_tienda_estado", "picking_ids"]
    )[0]
    entregas = c.read("stock.picking", so["picking_ids"], ["state"])
    assert so["comercio_tienda_estado"] == "listo" and all(p["state"] == "done" for p in entregas), (
        so,
        entregas,
    )
    print(
        f"3. {numero}: preparar → listo; en Odoo la entrega quedó validada y el pedido «Listo para retirar» ✓"
    )

    post(op, "/api/panel/accion", {"pedido": pid, "tipo": "retirado"})
    tp.conector()
    assert (
        c.read("sale.order", [so["id"]], ["comercio_tienda_estado"])[0]["comercio_tienda_estado"]
        == "retirado"
    )
    print("4. Retirado: Odoo «Retirado» ✓")

    # Faltante: pide 2, hay 1 → el cliente elige desde el link del mail → nota en Odoo
    estado, d = tp.pedir(slug, 2)
    pid2, tok2 = tp.id_y_token(d["pago"])
    tp.http("POST", "/api/pago/simulado", form={"id": pid2, "t": tok2, "decision": "aprobar"})
    tp.conector()
    prod = c.search_read("sale.order", [("comercio_tienda_ref", "=", pid2)], ["order_line"])[0]
    pid_prod = c.read("sale.order.line", prod["order_line"], ["product_id"])[0]["product_id"][0]
    post(op, "/api/panel/accion", {"pedido": pid2, "tipo": "preparar"})
    post(op, "/api/panel/accion", {"pedido": pid2, "tipo": "faltante", f"hay_{pid_prod}": 1})
    _, cli = navegador()
    _, html, _ = get(cli, f"/pedido/{pid2}?t={tok2}")
    assert "Espero a que llegue" in html and "Hay 1 de 2" in html, html[:300]
    post(cli, "/api/pedido/eleccion", {"id": pid2, "t": tok2, "opcion": "esperar"})
    tp.conector()
    so2 = c.search_read(
        "sale.order", [("comercio_tienda_ref", "=", pid2)], ["comercio_tienda_estado", "message_ids"]
    )[0]
    textos = " ".join(m["body"] for m in c.read("mail.message", so2["message_ids"], ["body"]))
    assert so2["comercio_tienda_estado"] == "faltante" and "eligió esperar" in textos, (
        so2["comercio_tienda_estado"],
        textos[:300],
    )
    print("4b. Falta algo: el cliente ve «hay 1 de 2», elige esperar y queda anotado en Odoo ✓")

    _, otro = navegador()
    e, loc = post(otro, "/api/panel/accion", {"pedido": pid, "tipo": "listo"})
    assert e == 303 and loc.endswith("/panel"), (e, loc)
    e, _ = post(op, "/api/panel/accion", {"pedido": pid, "tipo": "retirado"}, origen="https://otro.example")
    assert e == 403, e
    for _ in range(5):
        post(op, "/api/panel/entrar", {"empleado": emp, "pin": "9999"})
    e, loc = post(op, "/api/panel/entrar", {"empleado": emp, "pin": PIN})
    assert "e=bloqueado" in loc, loc
    print("5. Sin sesión u otro origen: no; 5 PIN equivocados bloquean (aun con el PIN bueno) ✓")
    print("Panel de pedidos: todo bien ✓")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        tp.limpiar()
