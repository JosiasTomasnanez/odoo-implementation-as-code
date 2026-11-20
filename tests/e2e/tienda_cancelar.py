"""Prueba de punta a punta de la cancelación de un pedido de la tienda online (arrepentimiento) contra
la demo y el Odoo del lab:

1. Pedido pago y en Odoo, sin retirar → «Cancelar el pedido» en la administración: la tienda lo da
   por cancelado y libera la reserva; el conector lo cancela en Odoo (con su entrega), el stock vuelve
   y queda la tarea «Devolver el dinero».
2. Pedido ya retirado (entrega validada) → Odoo deja preparada la devolución al depósito, sin validar,
   con las tareas «Recibir la devolución» y «Devolver el dinero».
3. Solo un arrepentimiento pendiente y de un pedido cobrado se puede cancelar; repetirlo no hace nada.

Uso: make e2e-tienda-cancelar
"""

from __future__ import annotations

import hashlib
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tienda_pedidos as tp  # noqa: E402
from tienda_admin import d1, entrar  # noqa: E402
from tienda_panel import post  # noqa: E402

N = int(time.time())
ADMIN = f"admin-cancelar{N}@example.com"
NOMBRE = "Cinta métrica 5 m × 19 mm"


def comprar(slug: str, email: str) -> tuple[str, int]:
    """Compra aprobada y llevada a Odoo. Devuelve (id del pedido, id de la orden en Odoo)."""
    estado, d = tp.pedir(slug, 1, email=email)
    assert estado == 200 and d.get("ok"), (estado, d)
    pedido_id, token = tp.id_y_token(d["pago"])
    estado, d2 = tp.http(
        "POST", "/api/pago/simulado", form={"id": pedido_id, "t": token, "decision": "aprobar"}
    )
    assert d2["estado"] == "pagado", d2
    tp.conector()
    tp.conector()
    orden = tp.c.search_read("sale.order", [("comercio_tienda_ref", "=", pedido_id)], ["id", "state"])
    assert orden and orden[0]["state"] == "sale", orden
    return pedido_id, orden[0]["id"]


def arrepentimiento(pedido_id: str, email: str) -> str:
    numero = d1(f"SELECT numero FROM pedidos WHERE id = '{pedido_id}'")[0]["numero"]
    codigo = "AR-" + secrets.token_hex(4).upper()
    d1(
        "INSERT INTO arrepentimientos (codigo, creado, nombre, email, telefono, pedido, motivo) VALUES "
        f"('{codigo}', datetime('now'), 'Cliente Prueba', '{email}', NULL, 'W-{numero:04d}', 'e2e')"
    )
    return codigo


def actividades(orden_id: int) -> list[str]:
    return [
        a["summary"]
        for a in tp.c.search_read(
            "mail.activity", [("res_model", "=", "sale.order"), ("res_id", "=", orden_id)], ["summary"]
        )
    ]


def main() -> int:
    d1(
        "INSERT INTO equipo (id, email, nombre, roles, creado) VALUES "
        f"('{hashlib.md5(ADMIN.encode()).hexdigest()}', '{ADMIN}', 'Admin e2e', 'admin', datetime('now'))"
    )
    _, op = entrar(ADMIN)
    pid = tp.poner_stock(NOMBRE, 12)
    tp.conector()
    slug = tp.slug_de("cinta metrica")

    # 1. Sin retirar → cancelado en la tienda y en Odoo, el stock vuelve
    email = f"cancela{N}@example.com"
    pedido, orden = comprar(slug, email)
    libre_antes = tp.c.read("product.product", [pid], ["free_qty"])[0]["free_qty"]
    codigo = arrepentimiento(pedido, email)
    e, loc = post(op, "/api/admin/cancelar", {"codigo": codigo, "nota": "e2e"})
    assert loc.endswith("/admin/arrepentimientos"), (e, loc)
    fila = d1(f"SELECT estado FROM pedidos WHERE id = '{pedido}'")[0]
    assert fila["estado"] == "cancelado", fila
    assert d1(f"SELECT resuelto FROM arrepentimientos WHERE codigo = '{codigo}'")[0]["resuelto"], (
        "sin resolver"
    )
    tp.conector()
    o = tp.c.read("sale.order", [orden], ["state", "comercio_tienda_estado", "picking_ids"])[0]
    assert o["state"] == "cancel" and o["comercio_tienda_estado"] == "cancelado", o
    libre = tp.c.read("product.product", [pid], ["free_qty"])[0]["free_qty"]
    assert libre == libre_antes + 1, (libre_antes, libre)
    assert "Devolver el dinero del pedido de la tienda" in actividades(orden), actividades(orden)
    print("1. Sin retirar: cancelado en la tienda y en Odoo, el stock vuelve, tarea de devolver el dinero ✓")

    # 3. Repetirlo no hace nada (el arrepentimiento ya está resuelto)
    e, loc = post(op, "/api/admin/cancelar", {"codigo": codigo})
    assert loc.endswith("/admin/arrepentimientos"), (e, loc)
    assert (
        tp.c.call(
            "mail.activity", "search_count", domain=[("res_model", "=", "sale.order"), ("res_id", "=", orden)]
        )
        == 1
    )

    # 2. Retirado → devolución preparada, sin validar
    email2 = f"devuelve{N}@example.com"
    pedido2, orden2 = comprar(slug, email2)
    entrega = tp.c.read("sale.order", [orden2], ["picking_ids"])[0]["picking_ids"]
    for mv in tp.c.search_read("stock.move", [("picking_id", "in", entrega)], ["id", "product_uom_qty"]):
        tp.c.write("stock.move", [mv["id"]], {"quantity": mv["product_uom_qty"], "picked": True})
    # Como «listo» del panel: sin el asistente de SMS ni pendientes
    tp.c.call(
        "stock.picking",
        "button_validate",
        entrega,
        context={"skip_sms": True, "skip_backorder": True, "picking_ids_not_to_backorder": entrega},
    )
    assert all(p["state"] == "done" for p in tp.c.read("stock.picking", entrega, ["state"])), (
        "la entrega no se validó"
    )
    d1(f"UPDATE pedidos SET estado = 'retirado', retirado = datetime('now') WHERE id = '{pedido2}'")
    codigo2 = arrepentimiento(pedido2, email2)
    post(op, "/api/admin/cancelar", {"codigo": codigo2})
    assert d1(f"SELECT estado FROM pedidos WHERE id = '{pedido2}'")[0]["estado"] == "devolucion"
    tp.conector()
    o2 = tp.c.read("sale.order", [orden2], ["state", "comercio_tienda_estado", "picking_ids"])[0]
    assert o2["comercio_tienda_estado"] == "devolucion" and o2["state"] == "sale", o2
    devoluciones = tp.c.search_read(
        "stock.picking", [("return_id", "in", entrega)], ["state", "picking_type_code"]
    )
    assert devoluciones and all(d["state"] not in ("done", "cancel") for d in devoluciones), devoluciones
    tareas = actividades(orden2)
    assert {"Recibir la devolución de la tienda", "Devolver el dinero del pedido de la tienda"} <= set(
        tareas
    ), tareas
    print("2. Retirado: devolución preparada sin validar, tareas de recibirla y de devolver el dinero ✓")
    print("3. Un arrepentimiento ya resuelto no cancela otra vez ✓")
    print("Cancelación de pedidos de la tienda: todo bien ✓")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        tp.limpiar()
