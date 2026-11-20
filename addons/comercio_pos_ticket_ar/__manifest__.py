{
    "name": "Comercio: ticket fiscal de la caja (Argentina) y ARCA caído",
    "summary": "El ticket de la caja con los datos de la factura (número, CAE, vencimiento, QR de ARCA y "
    "Ley 27.743); si ARCA no responde, la venta queda cobrada sin factura de Odoo y la caja avisa.",
    "description": """
Pedido del 02/11 (docs/areas/facturacion-contabilidad.md). Odoo 20 no imprime en el ticket de la
caja los datos de la factura electrónica.

- Ticket: con la venta facturada con CAE, al pie: «Factura B Nº …», CAE y vencimiento, el QR de
  ARCA (RG 4892, el que ya arma l10n_ar_edi) y el bloque «Régimen de Transparencia Fiscal al
  Consumidor (Ley 27.743)» con el IVA contenido. Igual en la caja, la reimpresión y el mail.
- ARCA caído (o rechaza el comprobante): en vez del error técnico y la venta trabada en el
  navegador, la venta queda cobrada sin factura de Odoo, marcada «Sin factura: ARCA no
  respondió», y la caja avisa que el comprobante se hace en la registradora.
- Sin registradoras (09/11, facturacion.arca_caido = facturar_despues en config/valores.yaml): la venta
  cobrada con «Factura» marcado queda «Factura pendiente»; el ticket lo dice y una tarea cada 10 minutos
  (o el botón «Reintentar facturas pendientes») la factura con CAE cuando ARCA vuelve. Las ventas
  cobradas sin «Factura» nunca se facturan solas.
""",
    "version": "20.0.1.1.0",
    "category": "Sales/Point of Sale",
    "license": "OPL-1",
    "depends": ["comercio_pos_factura", "l10n_ar_edi"],
    "data": [
        "receipt/pos_order_receipt.xml",
        "views/pos_order_views.xml",
        "data/ir_cron.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "comercio_pos_ticket_ar/static/src/app/**/*",
        ],
    },
    "installable": True,
}
