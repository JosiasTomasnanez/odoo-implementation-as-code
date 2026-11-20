from odoo import models

from ..models.pos_order import TITULO_TRANSPARENCIA


class PosOrderReceipt(models.AbstractModel):
    _inherit = "pos.order.receipt"

    def order_receipt_generate_data(self, basic_receipt=False):
        """Los datos de la factura al pie del ticket (reimpresión y mail; la caja hace lo mismo en JS)."""
        data = super().order_receipt_generate_data(basic_receipt)
        if self.comercio_ticket_cae:
            data["conditions"]["comercio_factura_ar"] = True
            # Ya está facturada: sin el «¿Necesita factura?» de Odoo (otro QR, que confunde con el de ARCA)
            data["conditions"]["use_self_invoicing"] = False
            data["extra_data"]["comercio_factura_ar"] = {
                "factura": self.comercio_ticket_factura,
                "cae": self.comercio_ticket_cae,
                "vto": self.comercio_ticket_cae_vto,
                "titulo": TITULO_TRANSPARENCIA,
                "impuestos": [linea.split("|", 1) for linea in (self.comercio_ticket_transparencia or "").splitlines()],
            }
            if self.comercio_ticket_qr:
                data["image"]["comercio_qr_arca"] = self._order_receipt_generate_qr_code(self.comercio_ticket_qr)
        elif self.comercio_factura_pendiente:
            data["conditions"]["comercio_factura_pendiente"] = True
            data["conditions"]["use_self_invoicing"] = False
        return data
