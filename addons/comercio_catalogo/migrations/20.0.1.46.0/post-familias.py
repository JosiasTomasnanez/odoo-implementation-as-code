"""Familias de cada lista para elegirlas en «Descuentos por familia» (06/11). Las importaciones de
antes no guardaban la familia de cada fila: aparecen al volver a simular («Recalcular costos») o con
la próxima lista; mientras tanto se puede seguir escribiendo el texto."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["comercio.lista.proveedor"].with_context(active_test=False).search([])._actualizar_familias()
