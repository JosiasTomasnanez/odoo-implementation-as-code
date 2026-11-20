{
    "name": "Comercio: mail de la factura",
    "summary": "El mail con que se manda la factura al cliente, sin el botón al portal de Odoo, "
    "sin la firma del usuario ni «Powered by Odoo».",
    "description": """
Pedido del 09/11 (docs/areas/facturacion-contabilidad.md). Odoo arma el mail de la factura con un
diseño fijo en el código (account.move.send._get_mail_layout): botón «Ver Factura» al portal (el
Odoo del local no está abierto a internet: al cliente no le abriría), la firma del usuario que lo
manda y «Powered by Odoo». Este módulo usa un diseño propio: el texto de la plantilla y un pie con
los datos de la empresa. El texto está en config/base/08-mail-factura.yaml.
""",
    "version": "20.0.1.0.0",
    "category": "Accounting/Accounting",
    "license": "LGPL-3",
    "depends": ["account", "mail"],
    "data": ["data/mail_layout.xml"],
    "installable": True,
}
