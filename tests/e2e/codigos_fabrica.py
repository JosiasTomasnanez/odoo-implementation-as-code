"""Prueba de punta a punta de «Códigos de fábrica» (módulo comercio_codigos_fabrica) en el lab.

Con productos FICTICIOS nuevos en cada corrida:

1. Un producto nuevo recibe el código propio 20… y aparece en «Códigos de fábrica».
2. Escanear el código de fábrica: pasa a ser su código de barras, el 20… queda como
   alternativo (la caja lo sigue leyendo) y sale de la lista.
3. Un código que ya es de otro producto o con el dígito verificador mal: no se acepta.
4. «No tiene código de fábrica»: sale de la lista sin tocar su código; «Volver» lo devuelve.
5. El próximo 20… no repite el número que quedó como alternativo.

Uso: .venv/bin/python tests/e2e/codigos_fabrica.py
"""
from __future__ import annotations

import sys
import time

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

sys.path.insert(0, "addons/comercio_catalogo")
from catalogo.codigos import digito_verificador  # noqa: E402

c = connect(load_environment("lab"))
MARCA = str(int(time.time()))[-6:]
PENDIENTES = [("barcode", "=like", "20%"), ("comercio_sin_codigo_fabrica", "=", False)]


def ean(cuerpo: str) -> str:
    return cuerpo + str(digito_verificador(cuerpo))


def en_la_lista(tmpl: int) -> bool:
    return bool(c.search_read("product.template", [("id", "=", tmpl), *PENDIENTES], ["id"]))


def main() -> int:
    productos = []
    try:
        a = c.create("product.template", {"name": f"[EJ] Código fábrica A {MARCA}", "type": "consu"})
        b = c.create("product.template", {"name": f"[EJ] Código fábrica B {MARCA}", "type": "consu"})
        productos += [a, b]
        propio = c.read("product.template", [a], ["barcode"])[0]["barcode"]
        assert propio.startswith("20") and en_la_lista(a), propio
        print("1. Producto nuevo con código propio", propio, "en «Códigos de fábrica» ✓")

        fabrica = ean(f"779{MARCA}111")
        c.write("product.template", [a], {"comercio_codigo_fabrica": fabrica})
        d = c.read("product.template", [a], ["barcode", "comercio_codigos_alternativos"])[0]
        assert d["barcode"] == fabrica and d["comercio_codigos_alternativos"] == propio, d
        assert not en_la_lista(a)
        print(f"2. Escaneado {fabrica}: es su código; {propio} queda como alternativo; sale de la lista ✓")

        for malo in (fabrica, fabrica[:-1] + str((int(fabrica[-1]) + 1) % 10), propio):
            try:
                c.write("product.template", [b], {"comercio_codigo_fabrica": malo})
            except Exception as error:  # noqa: BLE001 - el servidor devuelve UserError
                assert "ya es de" in str(error) or "no es un código" in str(error), error
            else:
                raise AssertionError(f"aceptó {malo}")
        print("3. Código de otro producto, dígito mal o el propio de otro: no se aceptan ✓")

        c.call("product.template", "action_comercio_sin_codigo_fabrica", [b])
        assert not en_la_lista(b)
        c.call("product.template", "action_comercio_con_codigo_fabrica", [b])
        assert en_la_lista(b)
        print("4. «No tiene código de fábrica» lo saca de la lista; «Volver» lo devuelve ✓")

        n = c.create("product.template", {"name": f"[EJ] Código fábrica C {MARCA}", "type": "consu"})
        productos.append(n)
        nuevo = c.read("product.template", [n], ["barcode"])[0]["barcode"]
        assert nuevo != propio and int(nuevo[2:12]) > int(propio[2:12]), (nuevo, propio)
        print(f"5. El próximo código propio es {nuevo}: no repite {propio} ✓")
        print("Todo OK.")
        return 0
    finally:
        variantes = c.search_read("product.product", [("product_tmpl_id", "in", productos)], ["id"])
        dominio = [("product_id", "in", [v["id"] for v in variantes])]
        alternativos = [u["id"] for u in c.search_read("product.uom", dominio, ["id"])]
        if alternativos:
            c.call("product.uom", "unlink", alternativos)
        if productos:
            c.call("product.template", "unlink", productos)
        print("   (datos de la prueba borrados: el lab queda limpio)")


if __name__ == "__main__":
    sys.exit(main())
