{
    "name": "Comercio: categorías del punto de venta, a mano o con IA",
    "summary": "Poner a varios productos la categoría del POS (los botones de arriba) a mano o con la "
    "sugerencia de Gemini, revisada antes de aplicar; productos del POS en orden alfabético.",
    "description": """
Ver ADR 0018 (ampliación «Categorizar productos del punto de venta») en el repositorio de la
implementación.

- En el menú Acciones de Productos (también desde Punto de venta → Productos):
  «Categorizar a mano» (elegir categorías; agregar o reemplazar) y «Categorizar con IA».
- La IA elige, entre las categorías del punto de venta que existen, la que más se acerca a
  cada producto (o ninguna). Saltea los que ya tienen categoría. Solo **sugiere**: se revisa,
  se puede cambiar y se aplica con «Aplicar».
- A Google va solo el nombre del producto, su rubro y los nombres de las categorías del POS:
  nada de costos, precios, clientes ni ventas. No cambia costos ni precios.
- En la lista de Punto de venta → Productos, la columna «Categoría del PdV» al lado del
  nombre y el filtro «Sin categoría del PdV».
- En el punto de venta, los productos salen con los favoritos (estrellita) primero y el
  resto por orden alfabético (Odoo los deja en el orden de carga); sin reordenar arrastrando.
- Las cajas y puestos abiertos se enteran solos de los cambios de precio, nombre, código o categoría
  de los productos (sin recargar la pantalla), con el aviso de sincronización del punto de venta.
- Usa el cliente de Gemini y la clave (GEMINI_API_KEY en el servidor) de comercio_catalogo_ia.
""",
    "version": "20.0.1.5.1",
    "category": "Sales/Point of Sale",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "comercio_catalogo_ia"],
    "data": [
        "security/ir.access.csv",
        "views/categorizar_views.xml",
        "views/product_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "comercio_pos_categorias/static/src/app/**/*",
        ],
    },
    "installable": True,
}
