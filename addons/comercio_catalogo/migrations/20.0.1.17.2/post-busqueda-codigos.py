"""«Buscar producto» ahora también encuentra por el código de barras y la referencia de
nuestro producto: se recalcula el texto de búsqueda de las filas que ya existían."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    lineas = env["comercio.lista.importacion.linea"].with_context(active_test=False).search(
        [("producto_id", "!=", False)])
    env.add_to_compute(lineas._fields["texto_busqueda"], lineas)
    lineas.flush_recordset(["texto_busqueda"])
