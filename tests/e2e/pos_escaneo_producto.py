"""Escanear un producto en el puesto después de entrar con el PIN (comercio_pos_pedido_qr).

Error de Odoo 20 (pos_hr, 18/11): la pantalla de ingreso dejaba el lector tomado para las
tarjetas de cajero y todo producto escaneado daba «Código de barras desconocido».
Se verifica que, tras entrar con el PIN, escanear un código de fábrica agrega el producto.

Usa un producto ficticio del lab con un código de fábrica (lo crea si no está).
Uso: .venv/bin/python tests/e2e/pos_escaneo_producto.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from pos_pedido_qr import PIN_ATENCION, VER, abrir_pos, asegurar_sesion, login, xmlid  # noqa: E402

from odoo_iac.client import connect  # noqa: E402
from odoo_iac.settings import load_environment  # noqa: E402

CODIGO = "4710088321008"  # EAN-13 válido que no empieza con 2 (no es pesable ni propio)
NOMBRE = "[EJ] Soporte de pared (escaneo)"


def main() -> int:
    c = connect(load_environment("lab"))
    puesto_id = xmlid(c, "ej_pos_puesto")
    if not c.search_read("product.product", [("barcode", "=", CODIGO)], ["id"]):
        c.call("product.product", "create", vals_list=[{
            "name": NOMBRE, "barcode": CODIGO, "available_in_pos": True, "sale_ok": True, "list_price": 12}])
    asegurar_sesion(c, puesto_id)
    with sync_playwright() as p:
        b = p.chromium.launch(**VER)
        pg = b.new_context(viewport={"width": 1366, "height": 768}, locale="es-AR").new_page()
        login(pg)
        abrir_pos(pg, puesto_id, PIN_ATENCION)
        pg.evaluate("posmodel.getOrder().lines.forEach(l => posmodel.getOrder().removeOrderline(l))")
        pg.keyboard.type(CODIGO + "\n", delay=5)  # así «tipea» un lector USB
        pg.wait_for_timeout(3000)
        lineas = pg.evaluate("posmodel.getOrder().lines.map(l => l.product_id.barcode)")
        b.close()
    if CODIGO not in lineas:
        print(f"✗ Escaneado {CODIGO} tras el PIN: el producto no se agregó (líneas: {lineas})")
        return 1
    print("1. Puesto: tras entrar con el PIN, el lector agrega el producto escaneado ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
