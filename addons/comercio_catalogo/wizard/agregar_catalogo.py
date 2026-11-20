from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..catalogo import plan as motor


class ComercioAgregarCatalogoWizard(models.TransientModel):
    """«Agregar a nuestro catálogo» en *Buscar producto* (02/11, pedido del cliente): un solo botón
    arriba que pregunta cómo agregar las filas marcadas, en vez de cuatro botones a la vez."""

    _name = "comercio.agregar.catalogo.wizard"
    _description = "Agregar a nuestro catálogo"

    linea_ids = fields.Many2many("comercio.lista.importacion.linea", "comercio_agregar_catalogo_linea_rel",
                                 string="Filas", required=True)
    resumen = fields.Char(compute="_compute_resumen")
    varias = fields.Boolean(compute="_compute_resumen")
    con_parecidos = fields.Boolean(compute="_compute_resumen")
    opcion = fields.Selection([
        ("uno", "Son el mismo producto: agregarlo una sola vez, con todos esos proveedores"),
        ("nuevos", "Son productos distintos: agregar cada fila como un producto nuevo"),
        ("mismo", "Ya los tenemos: unir cada fila al producto nuestro más parecido («Se parece a»)"),
    ], "¿Cómo?")  # obligatorio en la ventanita (se crea sin elegir)

    @api.depends("linea_ids")
    def _compute_resumen(self):
        for w in self:
            proveedores = w.linea_ids.partner_id
            w.resumen = _("%(n)s fila(s) de %(p)s proveedor(es): %(nombres)s", n=len(w.linea_ids),
                          p=len(proveedores), nombres=", ".join(proveedores.mapped("name")))
            w.varias = len(w.linea_ids) > 1
            w.con_parecidos = bool(w.linea_ids.filtered("candidato_ids"))

    def action_confirmar(self):
        resultado = self._agregar()
        cerrar = {"type": "ir.actions.act_window_close"}  # cierra la ventanita y refresca la lista
        if isinstance(resultado, dict) and resultado.get("tag") == "display_notification":
            resultado["params"]["next"] = cerrar
            return resultado
        return resultado if isinstance(resultado, dict) and resultado.get("res_model") else cerrar

    def _agregar(self):
        self.ensure_one()
        if not self.opcion:
            raise UserError(_("Elegí cómo agregarlas."))
        lineas = self.linea_ids
        if self.opcion == "uno":
            return lineas.action_agregar_como_uno()
        if self.opcion == "mismo":
            if not lineas.filtered("candidato_ids"):
                raise UserError(_("Ninguna de las filas marcadas se parece a un producto nuestro."))
            return lineas.action_es_el_mismo()
        # Cada fila, un producto nuevo: «Agregar» y, en los posibles duplicados, «Agregar como nuevo»
        posibles = lineas.filtered(lambda li: li.accion == motor.POSIBLE_DUPLICADO)
        resultado = (lineas - posibles).action_aplicar() if lineas - posibles else True
        if posibles:
            resultado = posibles.action_es_nuevo()
        return resultado
