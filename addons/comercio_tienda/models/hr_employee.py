"""Empleados que entran al panel de pedidos de la tienda con su PIN (el mismo de la caja)."""
from __future__ import annotations

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    comercio_tienda_panel = fields.Boolean(
        "Usa el panel de pedidos de la tienda", groups="hr.group_hr_user",
        help="Puede entrar al panel de pedidos online (en la PC o tablet del local) con su nombre y su PIN.")

    @api.model_create_multi
    def create(self, vals_list):
        emps = super().create(vals_list)
        self.env["comercio.tienda.cambio"]._anotar("empleado", emps.sudo().filtered("comercio_tienda_panel").ids)
        return emps

    def write(self, vals):
        antes = self.sudo().filtered("comercio_tienda_panel")
        res = super().write(vals)
        if {"comercio_tienda_panel", "pin", "name", "active"} & set(vals):
            self.env["comercio.tienda.cambio"]._anotar("empleado", (antes | self.sudo().filtered("comercio_tienda_panel")).ids)
        return res

    def _comercio_tienda_datos(self) -> list[dict]:
        """Para el panel: nombre y PIN (viaja por HTTPS firmado; la tienda guarda solo un HMAC)."""
        out = []
        for e in self.sudo().with_context(active_test=False):
            habilitado = bool(e.active and e.comercio_tienda_panel and e.pin and e.pin.isdigit() and 4 <= len(e.pin) <= 8)
            out.append({"id": e.id, "nombre": e.name[:80], "pin": e.pin if habilitado else None, "activo": habilitado})
        return out
