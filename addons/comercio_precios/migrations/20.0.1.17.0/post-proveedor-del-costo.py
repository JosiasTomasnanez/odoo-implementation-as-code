"""Guarda en cada producto el proveedor que hoy da el costo (para agrupar «Precios a actualizar»
por proveedor). Recalcula el sugerido como «Recalcular»: no cambia ningún precio de venta."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["product.template"].with_context(active_test=False).search([])._comercio_calcular_precio()
