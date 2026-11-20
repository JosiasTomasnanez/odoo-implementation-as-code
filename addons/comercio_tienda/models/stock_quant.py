"""El stock libre cambia con cada movimiento o reserva: se anota el producto si está publicado."""
from __future__ import annotations

from odoo import api, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    @api.model_create_multi
    def create(self, vals_list):
        quants = super().create(vals_list)
        self.env["comercio.tienda.cambio"]._anotar_productos(quants.mapped("product_id"))
        return quants

    def write(self, vals):
        res = super().write(vals)
        if {"quantity", "reserved_quantity", "location_id", "product_id"} & set(vals):
            self.env["comercio.tienda.cambio"]._anotar_productos(self.mapped("product_id"))
        return res

    def unlink(self):
        productos = self.mapped("product_id")
        res = super().unlink()
        self.env["comercio.tienda.cambio"]._anotar_productos(productos)
        return res
