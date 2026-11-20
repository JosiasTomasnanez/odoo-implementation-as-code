"""«Buscar producto» agrupa por producto en general (lo tengamos o no): se recalcula el grupo
de las filas que ya existían, ahora con la clave de palabras («4x40» = «4 X 40»)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    lineas = env["comercio.lista.importacion.linea"].with_context(active_test=False).search([])
    env.add_to_compute(lineas._fields["clave_producto"], lineas)
    lineas.flush_recordset(["clave_producto"])
    env.add_to_compute(lineas._fields["producto_general"], lineas)
    lineas.flush_recordset(["producto_general"])
