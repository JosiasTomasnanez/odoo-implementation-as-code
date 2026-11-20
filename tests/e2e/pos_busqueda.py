"""Punto de venta más ágil (comercio_pos_categorias, 20/11): búsqueda por palabras, más productos a
la vista y ordenados, Enter sin el aviso falso «No se encontraron otros productos» y sin protector
de pantalla."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[2] / "src"))
from playwright.sync_api import sync_playwright  # noqa: E402
from pos_pedido_qr import PIN_ATENCION, VER, abrir_pos, asegurar_sesion, login, xmlid  # noqa: E402

from odoo_iac.client import connect  # noqa: E402
from odoo_iac.settings import load_environment  # noqa: E402

NOMBRE = "[EJ] CEPILLO DE ACERO CURVO"


def main() -> int:
    c = connect(load_environment("lab"))
    puesto = xmlid(c, "ej_pos_puesto")
    if not c.search_read("product.template", [("name", "=", NOMBRE)], ["id"]):
        c.call("product.template", "create", vals_list=[{"name": NOMBRE, "available_in_pos": True,
                                                        "sale_ok": True, "list_price": 1500}])
    asegurar_sesion(c, puesto)
    fallas = []
    with sync_playwright() as p:
        b = p.chromium.launch(**VER)
        pg = b.new_context(viewport={"width": 1366, "height": 768}, locale="es-AR").new_page()
        login(pg)
        abrir_pos(pg, puesto, PIN_ATENCION)

        def buscar(texto):
            return pg.evaluate("(t) => { posmodel.searchProductWord = t; "
                               "return posmodel.productsToDisplay.map(p => p.name); }", texto)

        for texto in ("cepillo acero", "acero cepillo", "cep acer", "CEPILLO curvo"):
            if NOMBRE not in buscar(texto):
                fallas.append(f"«{texto}» no encuentra {NOMBRE}")
        if not fallas:
            print("1. Búsqueda por palabras: «cepillo acero», «acero cepillo», «cep acer» lo encuentran ✓")

        buscar("cepillo acero")
        pg.evaluate("posmodel.searchProductsFromDB()")
        pg.wait_for_timeout(2500)
        avisos = pg.locator(".o_notification").all_inner_texts()
        if any("otros productos" in a or "No hay productos" in a for a in avisos):
            fallas.append(f"Enter con resultados en pantalla avisa: {avisos}")
        else:
            print("2. Enter con resultados en pantalla: sin el aviso «No se encontraron otros productos» "
                  "✓")

        nombres = buscar("")
        favoritos = pg.evaluate("posmodel.productsToDisplay.filter(p => p.is_favorite).length")
        resto = nombres[favoritos:]
        # Con la misma comparación que usa el PdV (la de Odoo: «Nº 9» antes que «Nº 10»)
        js = ("(l) => { const cmp = odoo.loader.modules.get('@web/core/l10n/utils').localeCompare; "
              "return l.every((n, i) => !i || cmp(l[i - 1], n) <= 0); }")
        ordenado = pg.evaluate(js, resto)
        if len(nombres) <= 100 or not ordenado:
            fallas.append(f"Grilla: {len(nombres)} productos, ordenados: {ordenado}")
        else:
            print(f"3. Grilla: {len(nombres)} productos a la vista (antes 100), en orden alfabético ✓")

        if pg.evaluate("posmodel.idleTimeout.length") != 0:
            fallas.append("El protector de pantalla sigue activo")
        else:
            print("4. Sin protector de pantalla (no vuelve a pedir el usuario por inactividad) ✓")
        b.close()
    for f in fallas:
        print("✗", f)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
