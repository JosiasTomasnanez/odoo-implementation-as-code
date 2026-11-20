from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools import format_amount


class StockPicking(models.Model):
    _inherit = "stock.picking"

    comercio_compra_nombre = fields.Char("Orden de compra", compute="_compute_comercio_compra_nombre")

    @api.depends("move_ids.purchase_line_id.order_id")
    def _compute_comercio_compra_nombre(self):
        for recepcion in self:
            recepcion.comercio_compra_nombre = ", ".join(recepcion.move_ids.purchase_line_id.order_id.mapped("name"))

    def action_comercio_ver_compra(self):
        """De la recepción a su orden de compra (como el botón «Compras» de la factura del
        proveedor); desde la orden se llega a la factura."""
        self.ensure_one()
        ordenes = self.move_ids.purchase_line_id.order_id
        accion = {"type": "ir.actions.act_window", "name": _("Orden de compra"), "res_model": "purchase.order"}
        if len(ordenes) == 1:
            return {**accion, "res_id": ordenes.id, "view_mode": "form", "views": [(False, "form")]}
        return {**accion, "view_mode": "list,form", "views": [(False, "list"), (False, "form")],
                "domain": [("id", "in", ordenes.ids)]}

    def _action_done(self):
        res = super()._action_done()
        self._comercio_avisar_fuera_de_lista()
        return res

    def _comercio_avisar_fuera_de_lista(self):
        """Recepción con productos fuera de la lista vigente del proveedor: nota y tarea en la
        orden de compra para revisar el precio antes de facturar. No bloquea la recepción.

        Sin precio vigente de ese proveedor, Odoo pone en la orden el costo general del
        producto, que puede venir de otro proveedor o ser viejo."""
        for recepcion in self.filtered(lambda p: p.picking_type_code == "incoming"):
            lineas = recepcion.move_ids.filtered(
                lambda m: m.state == "done" and m.quantity
            ).purchase_line_id.filtered(lambda li: li.comercio_aviso_lista or li.comercio_aviso_minimo)
            if not lineas:
                continue
            orden = lineas.order_id[:1]
            recibido = {li: sum(recepcion.move_ids.filtered(lambda m, li=li: m.purchase_line_id == li)
                                .mapped("quantity")) for li in lineas}
            items = Markup("").join(
                Markup("<li><b>%s</b> (%s): %s en la orden. %s</li>") % (
                    li.product_id.display_name, f"{recibido[li]:g}",
                    format_amount(self.env, li.price_unit, li.currency_id),
                    li.comercio_aviso_lista or li.comercio_aviso_minimo)
                for li in lineas)
            nota = Markup("<p>%s</p><ul>%s</ul><p>%s</p>") % (
                _("En la recepción %(r)s llegaron productos sin precio de la lista vigente de %(p)s "
                  "(fuera de su lista o por debajo de su cantidad mínima):",
                  r=recepcion.name, p=orden.partner_id.name),
                items,
                _("Ese precio no sale de su lista (es el costo general del producto o uno cargado a "
                  "mano): revisarlo con la factura del proveedor antes de registrarla."))
            orden.message_post(body=nota)
            orden.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Revisar precios: productos fuera de la lista de %s", orden.partner_id.name),
                note=nota,
                user_id=(orden.user_id or self.env.user).id,
            )
