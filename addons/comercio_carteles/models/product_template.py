from odoo import _, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _comercio_precio_con_iva(self) -> float:
        """El precio de venta que ve el cliente: con IVA, sirva el impuesto con IVA incluido o no."""
        self.ensure_one()
        impuestos = self.taxes_id.filtered(lambda i: i.company_id == self.env.company)
        if not impuestos:
            return self.list_price
        return impuestos.compute_all(self.list_price, product=self, quantity=1.0)["total_included"]

    def _comercio_aclaracion_cartel(self) -> str:
        """«x kg», «x m», «x l» según la unidad de venta; «c/u» por unidad."""
        self.ensure_one()
        nombre = (self.uom_id.name or "").lower()
        for clave, texto in (("kg", "x kg"), ("gram", "x g"), ("litro", "x l"), (" l", "x l"), ("metro", "x m"),
                             ("m²", "x m²"), ("m2", "x m²")):
            if clave in f" {nombre}":
                return texto
        return "c/u"

    def action_comercio_hacer_carteles(self):
        """Productos → Acciones → «Hacer carteles»: un cartel por producto elegido (si ya tenía uno,
        se usa ese) y se abren para revisar el texto y el tamaño antes de imprimir."""
        if not self:
            raise UserError(_("Elegí los productos."))
        Cartel = self.env["comercio.cartel"]
        carteles = Cartel
        for producto in self:
            existente = Cartel.search([("product_tmpl_id", "=", producto.id)], limit=1)
            carteles |= existente or Cartel.create({
                "name": producto.name, "product_tmpl_id": producto.id,
                "aclaracion": producto._comercio_aclaracion_cartel()})
        accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_carteles.action_carteles")
        accion["domain"] = [("id", "in", carteles.ids)]
        accion["context"] = {}
        return accion
