"""El nombre de cada importación lleva la parte de la lista («(General)», «(Bulones)»): se
recalcula el de las que ya existían (si no, las partes del mismo día se llamaban igual)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    importaciones = env["comercio.lista.importacion"].search([])
    env.add_to_compute(importaciones._fields["name"], importaciones)
    importaciones.flush_recordset(["name"])
