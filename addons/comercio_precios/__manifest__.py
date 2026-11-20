{
    "name": "Comercio: precios de venta por margen",
    "summary": "Precio de venta sugerido = costo (o precio de un proveedor) + margen de la categoría "
    "+ IVA, redondeado; se revisa y se aplica, y se reimprimen las etiquetas.",
    "description": """
Ver docs/areas/precios-promociones.md (P-030) y ADR 0016 en el repositorio de la implementación.

- En cada categoría: margen (%), base (costo del producto o precio de un proveedor), IVA
  de venta y redondeo. Una subcategoría sin dato usa el de su categoría madre.
- Cada producto tiene su «Precio sugerido»; el precio de venta NO cambia solo. Excepción:
  un producto nuevo sin precio de venta (p. ej. creado desde una lista) toma el sugerido.
- «Márgenes por categoría»: todas las reglas en una tabla, editable, con la regla que
  termina usando cada categoría (incluido lo heredado).
- «Precios a actualizar»: los productos cuyo precio de venta difiere del sugerido. Se
  aplican (todos o los marcados) y quedan en «Etiquetas a reimprimir».
- «Precio manual»: si alguien escribe el precio de venta a mano, no se sugiere cambiarlo
  hasta desmarcarlo.
- «Margen especial» por producto: su propio margen y, si se elige, su propia base (costo o
  precio de un proveedor), como en las categorías. Al marcarlo arranca con lo de su rubro.
- Aviso si el proveedor de referencia (de un margen especial o de una categoría) no tiene
  el producto en su lista: se calcula sobre el costo y «Cómo se calculó» lo dice.
""",
    "version": "20.0.1.20.0",
    "category": "Sales",
    "license": "LGPL-3",
    "depends": ["comercio_catalogo", "account"],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron.xml",
        "views/product_category_views.xml",
        "views/margen_especial_views.xml",
        "views/diferencia_chica_views.xml",
        "views/product_template_views.xml",
        "views/margen_proveedor_views.xml",
        "views/lista_views.xml",
        "views/importar_lista_views.xml",
    ],
    "installable": True,
}
