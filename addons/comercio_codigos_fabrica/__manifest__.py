{
    "name": "Comercio: códigos de fábrica",
    "summary": "Reemplazar rápido el código propio (20…) por el código de barras de fábrica, escaneando "
    "en una lista; el propio queda como alternativo para las etiquetas ya pegadas.",
    "description": """
Ver ADR 0025 y P-058 en el repositorio de la implementación.

- Pantalla «Códigos de fábrica» (Costos y precios): los productos que todavía tienen el código
  propio 20… y no se marcaron «sin código de fábrica».
- Se escanea el código del envase en la fila: pasa a ser el código de barras del producto y el
  20… queda como código alternativo (por unidad, product.uom), que la caja también lee.
- «No tiene código de fábrica»: sale de la lista sin tocar su código (sueltos, pesables…).
- El próximo 20… tiene en cuenta los alternativos (no se repite un número ya pegado).
""",
    "version": "20.0.1.1.0",
    "category": "Inventory/Inventory",
    "license": "LGPL-3",
    "depends": ["comercio_catalogo"],
    "data": [
        "views/product_views.xml",
    ],
    "installable": True,
}
