"""El punto de venta abierto toma los cambios de precio sin recargar (comercio_pos_categorias, 20/11).

Se abre el puesto, se cambia el precio de un producto en el servidor y la pantalla tiene que
mostrar el nuevo en unos segundos (antes había que recargar: se cobraba el precio viejo).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[2] / "src"))
from playwright.sync_api import sync_playwright  # noqa: E402
from pos_pedido_qr import PIN_ATENCION, VER, abrir_pos, asegurar_sesion, login, xmlid  # noqa: E402

from odoo_iac.client import connect  # noqa: E402
from odoo_iac.settings import load_environment  # noqa: E402


def main() -> int:
    c = connect(load_environment("lab"))
    puesto = xmlid(c, "ej_pos_puesto")
    asegurar_sesion(c, puesto)
    prod = c.search_read("product.template", [("available_in_pos", "=", True), ("list_price", ">", 0)],
                         ["id", "name", "list_price"], limit=1)[0]
    nuevo = round(prod["list_price"] + 123, 2)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(**VER)
            pg = b.new_context(viewport={"width": 1366, "height": 768}, locale="es-AR").new_page()
            login(pg)
            abrir_pos(pg, puesto, PIN_ATENCION)
            leer = f"() => posmodel.models['product.template'].get({prod['id']}).list_price"
            c.write("product.template", [prod["id"]], {"list_price": nuevo})
            visto = None
            for _ in range(30):
                pg.wait_for_timeout(500)
                visto = pg.evaluate(leer)
                if abs(visto - nuevo) < 0.01:
                    break
            b.close()
    finally:
        c.write("product.template", [prod["id"]], {"list_price": prod["list_price"]})
    if abs(visto - nuevo) >= 0.01:
        print(f"✗ El puesto abierto sigue con {visto} después de cambiar el precio a {nuevo}")
        return 1
    print(f"1. Puesto abierto: el precio cambiado en el servidor ({nuevo}) se ve sin recargar ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
