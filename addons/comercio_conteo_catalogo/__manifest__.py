{
    "name": "Comercio: contar y agregar desde las listas",
    "summary": "Al contar el stock con el lector, un código que no está en nuestro catálogo se busca "
    "en las listas de los proveedores y se ofrece agregarlo ahí mismo.",
    "description": """
Pedido del 02/11 (contar por estante con la app «Código de barras», Enterprise).

- En «Contar inventario», si el código escaneado no es de ningún producto nuestro, se busca en
  la lista vigente de cada proveedor (código de barras o código del proveedor).
- Si está: cartel «¿Agregar a nuestro catálogo?» (con varios proveedores, uno solo con todos).
  Agregado, se suma al conteo como si se hubiera escaneado.
- Si la fila se parece a un producto nuestro: «Es …» lo une a ese producto y el código
  escaneado pasa a ser su código de fábrica (el 20… queda como alternativo).
- Si no está en ninguna lista: el aviso de siempre («Este producto no existe»).
""",
    "version": "20.0.1.0.0",
    "category": "Inventory/Inventory",
    "license": "OPL-1",
    "depends": ["stock_barcode", "comercio_catalogo", "comercio_codigos_fabrica"],
    "assets": {
        "web.assets_backend": [
            "comercio_conteo_catalogo/static/src/**/*",
        ],
    },
    "installable": True,
}
