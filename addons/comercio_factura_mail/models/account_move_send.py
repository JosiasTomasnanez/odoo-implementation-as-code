from odoo import api, models


class AccountMoveSend(models.AbstractModel):
    _inherit = "account.move.send"

    @api.model
    def _get_mail_layout(self):
        """Diseño propio del mail de la factura: sin el botón «Ver Factura» (lleva al portal de
        Odoo, que no está abierto a internet), sin la firma del usuario y sin «Powered by Odoo»."""
        return "comercio_factura_mail.layout_mail_factura"
