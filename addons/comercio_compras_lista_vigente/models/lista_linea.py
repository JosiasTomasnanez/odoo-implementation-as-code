from odoo import Command, _, fields, models
from odoo.exceptions import AccessError, UserError


class ComercioListaImportacionLinea(models.Model):
    _inherit = "comercio.lista.importacion.linea"

    def _cantidad_para_pedir(self):
        """(cantidad, unidad): la cantidad mínima de la lista vigente de ese proveedor (por lo
        menos 1), en la unidad en que él lo vende (p. ej. 1 «Caja 1000» de un producto en kg)."""
        self.ensure_one()
        hoy = fields.Date.context_today(self)
        precios = self.producto_id.seller_ids.filtered(
            lambda s: s.partner_id == self.partner_id and (not s.date_start or s.date_start <= hoy)
            and (not s.date_end or s.date_end >= hoy) and not s.comercio_escala_de_id)
        principal = precios.sorted("min_qty")[:1]
        unidad = principal.uom_id or self.producto_id.uom_id
        return max(principal.min_qty or 1, 1), unidad

    def action_agregar_a_pedido(self):
        """«Buscar producto» → al pedido de ese proveedor: se suma a su solicitud de cotización en
        borrador (o se crea una), con la cantidad mínima de su lista. El precio lo pone Compras
        según la lista. La solicitud queda en borrador: alguien la revisa y la confirma."""
        if not self.env.user.has_group("purchase.group_purchase_user"):
            raise AccessError(_("Para armar pedidos hace falta el permiso de Compras."))
        afuera = self.filtered(lambda li: not li.producto_id)
        if afuera:
            raise UserError(_("«%s» no está en nuestro catálogo: primero tocá «Agregar» (y elegí su categoría).",
                              afuera[0].descripcion))
        Orden = self.env["purchase.order"]
        ordenes = Orden
        # Abierto desde una orden («Lista del proveedor»): se suma a esa orden
        desde = Orden.browse(self.env.context.get("comercio_pedido_id")).exists()
        for proveedor in self.partner_id:
            if desde and desde.partner_id.commercial_partner_id == proveedor and desde.state in ("draft", "sent"):
                orden = desde
            else:
                orden = Orden.search([("partner_id", "=", proveedor.id), ("state", "=", "draft")],
                                     order="id desc", limit=1) or Orden.create({"partner_id": proveedor.id})
            for linea in self.filtered(lambda li, p=proveedor: li.partner_id == p):
                producto = linea.producto_id.product_variant_id
                cantidad, unidad = linea._cantidad_para_pedir()
                ya = orden.order_line.filtered(lambda o, p=producto, u=unidad: o.product_id == p and o.uom_id == u)[:1]
                if ya:
                    ya.product_qty += cantidad
                else:
                    orden.order_line = [Command.create({"product_id": producto.id, "product_qty": cantidad,
                                                        "uom_id": unidad.id})]
            ordenes |= orden
        if desde and ordenes == desde:
            # Se queda en la lista para seguir eligiendo; la orden se ve al volver (migas de pan)
            return {"type": "ir.actions.client", "tag": "display_notification", "params": {
                "type": "success", "message": _("Sumado a %(o)s: %(p)s", o=desde.name,
                                                p=", ".join(self.producto_id.mapped("name")[:3]))}}
        accion = {"type": "ir.actions.act_window", "res_model": "purchase.order",
                  "name": _("Pedidos a proveedores")}
        if len(ordenes) == 1:
            return accion | {"view_mode": "form", "views": [(False, "form")], "res_id": ordenes.id}
        return accion | {"view_mode": "list,form", "views": [(False, "list"), (False, "form")],
                         "domain": [("id", "in", ordenes.ids)]}
