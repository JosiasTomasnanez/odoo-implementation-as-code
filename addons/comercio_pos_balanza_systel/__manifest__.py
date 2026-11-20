{
    "name": "Comercio: balanza Systel Cuora conectada al POS",
    "summary": "El POS lee el peso de una Systel Cuora Max por USB (WebSerial), sin IoT.",
    "description": """
Ver docs/areas/balanzas-lectores.md y P-040 en el repositorio de la implementación.

- Habla el protocolo oficial de Systel («Protocolo de comunicaciones MAX CUORA V7»,
  función 1: peso, estabilidad y tara) por el puerto USB de la balanza (conversor
  serie FT232), desde Chrome o Edge con WebSerial. No necesita IoT.
- Pesaje automático: al elegir un producto pesable, se agrega solo cuando el peso
  queda estable.
- Sin pesaje automático: el peso se ve en vivo y se agrega con «Pedido» o Enter.
- «Escribir el peso»: en la pantalla de la balanza, para poner el peso a mano.
- En Ajustes del POS: número de la balanza y botón para conectarla en cada computadora.
- Requiere HTTPS (o localhost en el laboratorio).
""",
    "version": "20.0.1.3.0",
    "category": "Sales/Point of Sale",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "comercio_pos_balanza_systel/static/src/lib/**/*",
            "comercio_pos_balanza_systel/static/src/pos/**/*",
        ],
        "web.assets_backend": [
            "comercio_pos_balanza_systel/static/src/lib/**/*",
            "comercio_pos_balanza_systel/static/src/backend/**/*",
        ],
    },
    "installable": True,
}
