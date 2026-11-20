"""Los márgenes especiales que ya existían, sin base elegida, quedan con la de su rubro
(como los que se marcan de ahora en más), para verla y cambiarla si hace falta."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    productos = env["product.template"].with_context(active_test=False).search(
        [("comercio_margen_especial", "=", True), ("comercio_base_especial", "=", False)])
    productos._comercio_base_del_rubro()
