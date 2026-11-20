{
    "name": "Comercio: pedido del puesto con QR, cobrado en la caja",
    "summary": "Puestos que arman pedidos e imprimen un proforma con QR; la caja lo escanea y cobra.",
    "description": """
Ver docs/decisiones/0009-modulo-pedido-qr-puesto-caja.md en el repositorio de la implementación.

- Puesto («arma pedidos»): el botón principal imprime el pedido (lo sube al servidor y
  agrega un QR al proforma) en lugar de «Pago».
- Caja: al escanear el QR con el lector abre ese pedido; si el lector falla, el botón
  «Abrir pedido» permite tipear el número impreso.
- Pedidos enviados a caja que nadie cobra: se cancelan al cerrar la última caja.
- Todas las noches cierra los puestos que quedaron abiertos (la caja nunca).
- En los puestos, cualquier empleado puede abrir y cerrar la sesión (no manejan plata).
- Varias cajas: si otra caja ya cobró el pedido, la caja avisa y no lo cobra de nuevo.
- «Se cobra en la registradora» (P-046, temporal): el puesto, al imprimir, da el pedido
  por cobrado con el medio «Cobrado en registradora» (baja el stock), sin pedir medio de
  pago; el ticket sale sin QR.
- El ticket del puesto no muestra nada del IVA (ni impuestos ni subtotal, solo el total),
  ni el CUIT, el cliente, quien atiende, «Recibo proforma», el precio por unidad ni
  «Con la tecnología de Odoo»; lo pesado muestra los kilos. Sin margen de hoja, así
  Chrome no imprime su encabezado y pie («localhost…»).
- La pantalla de entrada del POS muestra el logo de la empresa (en color), no el del
  ticket (blanco y negro).
- Arreglo temporal de Odoo 20 (pos_hr): después de entrar con el PIN, el lector vuelve a leer
  productos (Odoo lo dejaba tomado por la pantalla de ingreso; ya corregido en 20.0).
""",
    "version": "20.0.1.13.0",
    "category": "Sales/Point of Sale",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "pos_hr"],
    "data": [
        "views/pos_order_receipt.xml",
        "data/ir_cron.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "comercio_pos_pedido_qr/static/src/app/**/*",
        ],
    },
    "installable": True,
}
