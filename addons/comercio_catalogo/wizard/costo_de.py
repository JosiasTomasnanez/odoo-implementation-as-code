"""«Tomar el costo de…» (06/11): para varios productos a la vez, de qué proveedor sale el costo, sin
perder el cálculo automático (cada lista lo sigue actualizando). «El más barato» vuelve al normal."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ComercioCostoDeWizard(models.TransientModel):
    _name = "comercio.costo.de.wizard"
    _description = "Tomar el costo de un proveedor"

    producto_ids = fields.Many2many("product.template", string="Productos")
    modo = fields.Selection([("proveedor", "De este proveedor"), ("barato", "Del más barato (normal)")],
                            "El costo sale", default="proveedor", required=True)
    proveedor_id = fields.Many2one("res.partner", "Proveedor", domain="[('id', 'in', proveedores_ids)]")
    proveedores_ids = fields.Many2many("res.partner", compute="_compute_proveedores")
    resumen = fields.Char(compute="_compute_resumen")

    @api.depends("producto_ids")
    def _compute_proveedores(self):
        for wizard in self:
            wizard.proveedores_ids = wizard.producto_ids.seller_ids.partner_id.commercial_partner_id

    @api.depends("producto_ids", "modo", "proveedor_id")
    def _compute_resumen(self):
        for wizard in self:
            if wizard.modo == "proveedor" and wizard.proveedor_id:
                lo_venden = wizard._de_ese_proveedor()
                wizard.resumen = _("%(n)s de %(t)s productos los vende %(p)s: a esos se les cambia. Los que tienen "
                                   "«Costo manual» no se tocan.", n=len(lo_venden), t=len(wizard.producto_ids),
                                   p=wizard.proveedor_id.name)
            else:
                wizard.resumen = _("%s productos vuelven a tomar el costo del proveedor más barato.",
                                   len(wizard.producto_ids))

    def _de_ese_proveedor(self):
        return self.producto_ids.filtered(
            lambda p: self.proveedor_id in p.seller_ids.partner_id.commercial_partner_id)

    @api.model
    def abrir(self, productos):
        if not productos:
            raise UserError(_("Elegí los productos con las casillas."))
        asistente = self.create({"producto_ids": [(6, 0, productos.ids)]})
        return {"type": "ir.actions.act_window", "name": _("Tomar el costo de…"), "res_model": self._name,
                "res_id": asistente.id, "view_mode": "form", "target": "new"}

    def action_aplicar(self):
        self.ensure_one()
        if self.modo == "proveedor":
            if not self.proveedor_id:
                raise UserError(_("Elegí el proveedor."))
            productos, valor = self._de_ese_proveedor(), self.proveedor_id.id
        else:
            productos, valor = self.producto_ids, False
        # Como el sistema (el grupo «Costos y precios» no edita productos): queda en el chatter del producto
        productos.sudo().write({"comercio_costo_de_id": valor})  # recalcula el costo y el precio sugerido
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Costo"), "type": "success",
            "message": _("%s productos actualizados. El precio de venta nuevo queda en «Precios a actualizar».",
                         len(productos)),
            "next": {"type": "ir.actions.act_window_close"}}}
