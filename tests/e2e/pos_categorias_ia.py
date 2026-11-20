"""Prueba de punta a punta de las categorías del punto de venta (módulo comercio_pos_categorias).

Llama de verdad a Gemini (pocos tokens; requiere GEMINI_API_KEY en el .env del repo y el lab
levantado con `make lab-up` después de cargarla). Usa los productos FICTICIOS de
config/ejemplos/22-productos-mascotas.yaml y corre las acciones del menú Acciones como desde
la pantalla de Productos:

1. «Categorizar con IA» sobre un producto ya categorizado y dos sin categoría: saltea el
   primero y sugiere «Alimento gato» para las croquetas felinas y «Accesorios mascotas» para la
   pelota. Nada se escribe hasta «Aplicar»; al aplicar quedan con esa categoría.
2. «Categorizar a mano»: agrega una categoría y después reemplaza.
3. Ni el costo ni el precio de venta cambiaron. Al final se dejan los dos productos como
   estaban (sin categoría), para volver a correrla.

Uso: .venv/bin/python tests/e2e/pos_categorias_ia.py
"""
from __future__ import annotations

import sys

from odoo_iac.client import connect
from odoo_iac.settings import load_environment

c = connect(load_environment("lab"))
ASISTENTE = "comercio.pos.categorizar"


def xmlid(nombre: str) -> int:
    modulo, _, name = nombre.rpartition(".")
    return c.search_read("ir.model.data", [("module", "=", modulo or "iac"), ("name", "=", name)],
                         ["res_id"])[0]["res_id"]


def accion(nombre: str, productos: list[int]) -> dict:
    """Corre una acción del menú Acciones sobre los productos elegidos, como la pantalla."""
    return c.call("ir.actions.server", "run", [xmlid(f"comercio_pos_categorias.{nombre}")],
                  context={**c.context, "active_model": "product.template", "active_ids": productos,
                           "active_id": productos[0]})


def categorias(producto: int) -> list[int]:
    return sorted(c.read("product.template", [producto], ["pos_categ_ids"])[0]["pos_categ_ids"])


def main() -> int:
    perro, gato, accesorios = (xmlid(f"ej_pos_cat_{n}")
                               for n in ("alimento_perro", "alimento_gato", "accesorios"))
    ya_categorizado = xmlid("ej_prod_perro_cachorro")
    croquetas, pelota = xmlid("ej_prod_gato_castrado_sin_cat"), xmlid("ej_prod_pelota_sin_cat")
    c.write("product.template", [croquetas, pelota], {"pos_categ_ids": [(5, 0, 0)]})
    antes = c.read("product.template", [croquetas, pelota], ["standard_price", "list_price"])
    try:
        # 1. Con IA
        abierto = accion("action_categorizar_ia", [ya_categorizado, croquetas, pelota])
        asistente = abierto["res_id"]
        datos = c.read(ASISTENTE, [asistente], ["linea_ids", "resumen", "producto_ids"])[0]
        # El que ya tenía categoría se saltea
        assert sorted(datos["producto_ids"]) == sorted([croquetas, pelota]), datos
        assert "se saltearon" in datos["resumen"], datos["resumen"]
        campos = ["producto_id", "categoria_id", "confianza", "motivo", "aplicar"]
        lineas = {li["producto_id"][0]: li
                  for li in c.read("comercio.pos.categorizar.linea", datos["linea_ids"], campos)}
        sugerida = {p: (li["categoria_id"] or [False])[0] for p, li in lineas.items()}
        assert sugerida == {croquetas: gato, pelota: accesorios}, lineas
        assert categorias(croquetas) == [] and categorias(pelota) == []  # nada hasta «Aplicar»
        print(f"1. IA: croquetas → «Alimento gato» ({lineas[croquetas]['confianza']:.2f}), pelota → "
              f"«Accesorios» ({lineas[pelota]['confianza']:.2f}); el ya categorizado se saltea ✓")
        # Se aplican las dos (aunque alguna venga con menos confianza, como haría quien revisa)
        c.write("comercio.pos.categorizar.linea", datos["linea_ids"], {"aplicar": True})
        c.call(ASISTENTE, "action_aplicar", [asistente])
        assert categorias(croquetas) == [gato] and categorias(pelota) == [accesorios]
        print("   «Aplicar»: quedan con esa categoría del punto de venta ✓")

        # 2. A mano: agregar y después reemplazar
        asistente = accion("action_categorizar_manual", [croquetas])["res_id"]
        c.write(ASISTENTE, [asistente], {"categoria_ids": [(6, 0, [perro])]})
        c.call(ASISTENTE, "action_aplicar", [asistente])
        assert categorias(croquetas) == sorted([gato, perro]), categorias(croquetas)
        asistente = accion("action_categorizar_manual", [croquetas])["res_id"]
        c.write(ASISTENTE, [asistente], {"categoria_ids": [(6, 0, [gato])], "reemplazar": True})
        c.call(ASISTENTE, "action_aplicar", [asistente])
        assert categorias(croquetas) == [gato], categorias(croquetas)
        asistente = accion("action_categorizar_manual", [croquetas])["res_id"]
        c.write(ASISTENTE, [asistente], {"reemplazar": True})  # sin categorías: se quitan todas
        c.call(ASISTENTE, "action_aplicar", [asistente])
        assert categorias(croquetas) == [], categorias(croquetas)
        print("2. A mano: agrega «Alimento perro» a lo que tenía;")
        print("   con «Reemplazar» queda solo «Alimento gato»; «Reemplazar» sin ninguna las quita ✓")

        # 3. Costos y precios intactos
        despues = c.read("product.template", [croquetas, pelota], ["standard_price", "list_price"])
        assert despues == antes, (antes, despues)
        print("3. Ni el costo ni el precio de venta cambiaron ✓")
    finally:
        c.write("product.template", [croquetas, pelota], {"pos_categ_ids": [(5, 0, 0)]})
    print("Todo OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
