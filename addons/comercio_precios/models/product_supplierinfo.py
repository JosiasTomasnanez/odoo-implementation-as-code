from odoo import api, models


class ProductSupplierinfo(models.Model):
    """Un precio de proveedor que cambia mueve el precio sugerido (no el de venta) de las
    categorías calculadas sobre un proveedor."""

    _inherit = "product.supplierinfo"

    @api.model_create_multi
    def create(self, vals_list):
        precios = super().create(vals_list)
        precios.product_tmpl_id._comercio_calcular_precio()
        return precios

    def write(self, vals):
        antes = self.product_tmpl_id
        res = super().write(vals)
        (antes | self.product_tmpl_id)._comercio_calcular_precio()
        return res

    def unlink(self):
        plantillas = self.product_tmpl_id
        res = super().unlink()
        plantillas.exists()._comercio_calcular_precio()
        return res
