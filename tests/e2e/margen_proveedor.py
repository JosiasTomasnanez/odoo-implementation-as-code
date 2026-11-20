"""Prueba de punta a punta del margen por proveedor (comercio_precios, pedido de Daniel 05/11).

Orden: margen especial del producto → margen del proveedor que da el costo (el más barato
vigente) → margen del rubro. Con productos y proveedores FICTICIOS nuevos en cada corrida:

1. Sin margen de proveedor: se usa el del rubro.
2. El proveedor más barato tiene margen propio: se usa ese, y el detalle lo dice.
3. Un margen en el proveedor más caro no cambia nada (no da el costo).
4. «Margen especial» del producto le gana al del proveedor.
5. El margen del proveedor se puede calcular sobre el precio de otro proveedor.
6. «Costo de»: el costo sale solo del proveedor elegido (sigue automático) y vuelve al más barato.

Uso: make e2e-precios
"""

from __future__ import annotations

import sys
import time

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

c = connect(load_environment("lab"))
MARCA = str(int(time.time()))[-6:]


def sugerido(tmpl: int) -> tuple[float, str]:
    d = c.read("product.template", [tmpl], ["comercio_precio_calculado", "comercio_precio_detalle"])[0]
    return d["comercio_precio_calculado"], d["comercio_precio_detalle"] or ""


def main() -> int:
    cat = c.create("product.category", {"name": f"[EJ] Rubro margen {MARCA}", "comercio_margen": 60})
    barato = c.create("res.partner", {"name": f"[EJ] Proveedor barato {MARCA}", "supplier_rank": 1})
    caro = c.create("res.partner", {"name": f"[EJ] Proveedor caro {MARCA}", "supplier_rank": 1})
    tmpl = c.create(
        "product.template",
        {
            "name": f"[EJ] Producto margen {MARCA}",
            "categ_id": cat,
            "taxes_id": [(6, 0, [])],
            "seller_ids": [
                (0, 0, {"partner_id": barato, "price": 100.0, "min_qty": 1}),
                (0, 0, {"partner_id": caro, "price": 120.0, "min_qty": 1}),
            ],
        },
    )
    c.write("product.template", [tmpl], {"standard_price": 100.0, "comercio_costo_manual": False})
    c.write("product.category", [cat], {"comercio_margen": 60})  # recalcula sus productos

    precio, detalle = sugerido(tmpl)
    assert abs(precio - 160) < 0.01, (precio, detalle)
    print("1. Sin margen de proveedor: el del rubro (60 %) → 160 ✓")

    c.write("res.partner", [barato], {"comercio_margen_proveedor": 30})
    precio, detalle = sugerido(tmpl)
    assert abs(precio - 130) < 0.01 and "margen de" in detalle, (precio, detalle)
    print(f"2. El proveedor más barato con 30 %: → 130 («{detalle[:60]}…») ✓")

    c.write("res.partner", [barato], {"comercio_margen_proveedor": 0})
    c.write("res.partner", [caro], {"comercio_margen_proveedor": 10})
    precio, _ = sugerido(tmpl)
    assert abs(precio - 160) < 0.01, precio
    print("3. Margen en el proveedor más caro: no cambia (sigue el del rubro) ✓")

    c.write("res.partner", [barato], {"comercio_margen_proveedor": 30})
    c.write("product.template", [tmpl], {"comercio_margen_especial": True, "comercio_margen_propio": 50})
    precio, detalle = sugerido(tmpl)
    assert abs(precio - 150) < 0.01 and "especial" in detalle, (precio, detalle)
    print("4. «Margen especial» del producto (50 %) le gana al del proveedor → 150 ✓")

    # 5. Sobre qué: el precio de otro proveedor (el caro, 120) en vez del costo (100)
    c.write("product.template", [tmpl], {"comercio_margen_especial": False})
    c.write("res.partner", [barato],
            {"comercio_base_proveedor": "proveedor", "comercio_proveedor_base_id": caro})
    precio, detalle = sugerido(tmpl)
    assert abs(precio - 156) < 0.01, (precio, detalle)
    print("5. Margen del proveedor (30 %) sobre el precio de otro proveedor (120) → 156 ✓")
    c.write("res.partner", [barato], {"comercio_base_proveedor": False, "comercio_proveedor_base_id": False})

    # 6. «Costo de»: el costo sale solo del proveedor elegido (el caro), y su margen pasa a mandar
    c.write("product.template", [tmpl], {"comercio_costo_de_id": caro})
    costo = c.read("product.template", [tmpl], ["standard_price", "comercio_costo_manual"])[0]
    assert abs(costo["standard_price"] - 120) < 0.01 and not costo["comercio_costo_manual"], costo
    precio, detalle = sugerido(tmpl)
    assert abs(precio - 132) < 0.01, (precio, detalle)  # 120 + 10 % (margen del caro)
    print("6. «Costo de» el caro: costo 120 (sigue automático) y manda su margen (10 %) → 132 ✓")
    c.write("product.template", [tmpl], {"comercio_costo_de_id": False})
    costo = c.read("product.template", [tmpl], ["standard_price"])[0]["standard_price"]
    assert abs(costo - 100) < 0.01, costo
    print("   Vacío: vuelve al más barato (100) ✓")

    c.write("product.template", [tmpl], {"active": False})
    print("Margen por proveedor: todo bien ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
