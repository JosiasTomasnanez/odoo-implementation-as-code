from markupsafe import Markup, escape

from odoo import _, api, fields, models

from .purchase_order_line import SALVEDAD


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    comercio_mas_barato_resumen = fields.Html(
        "Más barato en otro proveedor", compute="_compute_comercio_mas_barato_resumen", sanitize=True)

    @api.depends("order_line.comercio_mas_barato")
    def _compute_comercio_mas_barato_resumen(self):
        """Cartel arriba de los productos: en la columna de la línea el texto no entra entero."""
        for orden in self:
            lineas = orden.order_line.filtered("comercio_mas_barato")
            if not lineas:
                orden.comercio_mas_barato_resumen = False
                continue
            items = Markup("").join(
                Markup("<li><b>%s</b> → %s</li>") % (li.product_id.display_name, li.comercio_mas_barato)
                for li in lineas)
            orden.comercio_mas_barato_resumen = Markup("<p>%s <i>(%s)</i>:</p><ul class='mb-0'>%s</ul>") % (
                escape(_("Otro proveedor tiene más barato")), escape(SALVEDAD), items)

    @api.onchange("partner_id")
    def _onchange_comercio_aviso_lista(self):
        """Al cambiar el proveedor de una orden con productos: cuáles no están en la lista del nuevo
        (el aviso de la línea solo salta al elegir el producto)."""
        fuera = self.order_line.filtered("comercio_aviso_lista")
        if not self.partner_id or not fuera:
            return None
        return {"warning": {
            "title": self.partner_id.name,
            "message": _("No están en la lista de %(p)s: %(l)s. Se pueden pedir igual; conviene confirmarlo con "
                         "el proveedor.", p=self.partner_id.name, l=", ".join(fuera.product_id.mapped("display_name"))),
            "type": "notification",
        }}
