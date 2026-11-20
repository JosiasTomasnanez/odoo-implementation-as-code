from odoo import fields, models
from odoo.fields import Domain


def dominio_vigente(partners, fecha):
    """Precios de proveedor vigentes en `fecha` (sin fin, o con fin desde esa fecha)."""
    return [("partner_id", "in", partners.ids),
            "|", ("date_end", "=", False), ("date_end", ">=", fecha),
            "|", ("date_start", "=", False), ("date_start", "<=", fecha)]


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _search_sold_by_vendor(self, operator, value):
        """Filtro «Proveedor» del catálogo de compras: solo lo de la lista vigente.

        Odoo muestra también los productos con un precio ya cerrado de ese proveedor y
        todo lo que alguna vez se le compró. Acá: precio vigente; o, si el proveedor nunca
        tuvo precio cargado para ese producto, lo que se le compró antes (proveedores sin
        lista)."""
        if operator in Domain.NEGATIVE_OPERATORS:
            return NotImplemented
        partners = self.env["res.partner"].search([("id", operator, value)])
        partners |= partners.parent_id
        if not partners:
            return Domain.FALSE
        hoy = fields.Date.context_today(self)
        Info = self.env["product.supplierinfo"]
        vigentes = Info.search(dominio_vigente(partners, hoy))
        con_vigente = set(vigentes.product_tmpl_id.product_variant_ids.ids)
        con_precio = Info.search([("partner_id", "in", partners.ids)])
        con_precio = set(con_precio.product_tmpl_id.product_variant_ids.ids)
        comprados = set(self.env["purchase.order.line"].sudo().search([
            ("order_id.partner_id", "child_of", partners.ids),
            ("order_id.state", "=", "purchase"),
            ("order_id.company_id", "in", self.env.companies.ids),
        ]).product_id.ids)
        return [("id", "in", list(con_vigente | (comprados - con_precio)))]
