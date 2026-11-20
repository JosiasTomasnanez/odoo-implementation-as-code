"""Los rubros de la tienda son las categorías del PdV (P-054)."""
from __future__ import annotations

from odoo import api, models


class PosCategory(models.Model):
    _inherit = "pos.category"

    @api.model_create_multi
    def create(self, vals_list):
        cats = super().create(vals_list)
        self.env["comercio.tienda.cambio"]._anotar("categoria", cats.ids)
        return cats

    def write(self, vals):
        res = super().write(vals)
        if {"name", "parent_id", "sequence"} & set(vals):
            self.env["comercio.tienda.cambio"]._anotar("categoria", self.ids)
        return res

    def unlink(self):
        ids = self.ids
        res = super().unlink()
        self.env["comercio.tienda.cambio"]._anotar("categoria", ids)
        return res

    def _comercio_tienda_datos(self) -> list[dict]:
        return [{"id": c.id, "nombre": c.name, "padre_id": c.parent_id.id or None, "orden": c.sequence or 0}
                for c in self]
