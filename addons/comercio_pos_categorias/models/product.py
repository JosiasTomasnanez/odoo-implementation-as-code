import logging

from odoo import models

_logger = logging.getLogger(__name__)

# Lo que el punto de venta muestra o usa para cobrar: si cambia, se avisa a las cajas y puestos
# abiertos para que lo actualicen sin recargar (20/11: Ferretería 1 abrió a las 10:01 y a las 16:01
# cobró una sartén de Omega a $ 37.860 cuando desde las 14:15 valía $ 24.534).
CAMPOS_DEL_POS = {"list_price", "lst_price", "name", "barcode", "default_code", "pos_categ_ids", "taxes_id",
                  "available_in_pos", "active", "uom_id", "to_weight", "is_favorite"}
CLAVE = "comercio_pos_productos_cambiados"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def write(self, vals):
        resultado = super().write(vals)
        if CAMPOS_DEL_POS & set(vals):
            _anotar_para_el_pos(self.env, self.ids)
        return resultado


class ProductProduct(models.Model):
    _inherit = "product.product"

    def write(self, vals):
        resultado = super().write(vals)
        if CAMPOS_DEL_POS & set(vals):
            _anotar_para_el_pos(self.env, self.product_tmpl_id.ids)
        return resultado


def _anotar_para_el_pos(env, plantillas):
    """Junta los productos cambiados en la transacción y avisa una sola vez, al confirmar (una
    actualización de 2.000 precios es un aviso por caja, no 2.000)."""
    if not plantillas:
        return
    datos = env.cr.precommit.data
    if CLAVE not in datos:
        datos[CLAVE] = set()
        env.cr.precommit.add(lambda: _avisar_al_pos(env, datos.pop(CLAVE, set())))
    datos[CLAVE].update(plantillas)


def _avisar_al_pos(env, plantillas):
    """El aviso de Odoo a las cajas abiertas (el mismo que usa para los productos agotados,
    pos.config._notify_synchronisation): les manda los registros nuevos y la pantalla los toma."""
    # Solo las que tienen una sesión abierta de verdad (la búsqueda por current_session_id trae también
    # cajas sin sesión, y ahí el aviso de Odoo falla)
    configs = env["pos.config"].sudo().search([]).filtered(
        lambda c: c.current_session_id and c.current_session_id.state == "opened")
    if not configs or not plantillas:
        return
    productos = env["product.template"].sudo().browse(list(plantillas)).exists()
    registros = {"product.template": productos.ids, "product.product": productos.product_variant_ids.ids}
    for config in configs:
        try:
            config._notify_synchronisation(config.current_session_id.id, False, registros)
        except Exception as error:  # noqa: BLE001 — un aviso que falla no puede frenar el guardado
            _logger.warning("No se pudo avisar a %s de %s productos cambiados: %s", config.name,
                            len(productos), error)
