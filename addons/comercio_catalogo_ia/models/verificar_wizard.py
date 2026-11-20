from odoo import _, api, fields, models
from odoo.addons.comercio_catalogo.catalogo import plan as motor
from odoo.exceptions import UserError

from .importacion import MAXIMO_POR_VEZ


class ComercioVerificarIaWizard(models.TransientModel):
    """«Revisar con IA» (06/11, pedido del implementador): un solo botón con casillas, todas
    marcadas, que revisa de una vez lo que haga falta (antes había que elegir una opción por vez).
    Las filas de las casillas de producto se juntan en UNA corrida (tandas en paralelo) y solo las
    que no tienen sugerencia; las filas con problema van en otra, también en paralelo.
    Lo que la IA confirma con seguridad se une solo (ADR 0034); el resto, «Aceptar lo que sugirió la IA»."""

    _name = "comercio.verificar.ia.wizard"
    _description = "Revisar con IA una lista de proveedor"

    importacion_id = fields.Many2one("comercio.lista.importacion", "Lista")
    # Nombre de tabla corto: el automático pasa el máximo de PostgreSQL (63 caracteres)
    linea_ids = fields.Many2many("comercio.lista.importacion.linea", "comercio_verificar_ia_linea_rel",
                                 "wizard_id", "linea_id", string="Filas marcadas")
    revisar_marcadas = fields.Boolean("Las filas marcadas", default=True)
    revisar_duplicados = fields.Boolean("Posibles duplicados: ¿ya lo tenemos?", default=True)
    revisar_nuestros = fields.Boolean("Lo que ya tenemos: ¿sigue siendo el mismo producto?", default=True)
    revisar_problemas = fields.Boolean("Filas con problemas: qué pasó y qué hacer", default=True)
    cant_marcadas = fields.Integer(compute="_compute_cantidades")
    cant_duplicados = fields.Integer(compute="_compute_cantidades")
    cant_nuestros = fields.Integer(compute="_compute_cantidades")
    cant_problemas = fields.Integer(compute="_compute_cantidades")
    cant_sugeridas = fields.Integer(compute="_compute_cantidades")

    @api.model
    def _abrir(self, importacion=None, lineas=None):
        if importacion is None and lineas and len(lineas.importacion_id) == 1:
            importacion = lineas.importacion_id
        asistente = self.create({"importacion_id": importacion.id if importacion else False,
                                 "linea_ids": [(6, 0, lineas.ids if lineas else [])]})
        return {"type": "ir.actions.act_window", "name": _("Revisar con IA"), "res_model": self._name,
                "res_id": asistente.id, "view_mode": "form", "target": "new"}

    def _filas_de(self):
        return self.importacion_id.linea_ids if self.importacion_id else self.env["comercio.lista.importacion.linea"]

    def _sin_sugerencia(self, tipo):
        return self._filas_de().filtered(lambda li: not li.ia_veredicto and li._tipo_ia() == tipo)

    def _con_problema(self):
        return self._filas_de().filtered(lambda li: li.accion == motor.REVISAR and li.estado == "pendiente"
                                         and not li.ia_motivo)

    @api.depends("importacion_id", "linea_ids")
    def _compute_cantidades(self):
        for w in self:
            w.cant_marcadas = len(w.linea_ids)
            w.cant_duplicados = len(w._sin_sugerencia("duplicado"))
            w.cant_nuestros = len(w._sin_sugerencia("vinculo"))
            w.cant_problemas = len(w._con_problema())
            base = w.linea_ids or w._filas_de()
            w.cant_sugeridas = len(base.filtered(lambda li: li._tipo_ia() in ("duplicado", "nuevo")
                                                 and li.ia_veredicto in ("mismo", "distinto")))

    def action_revisar(self):
        """Revisa todo lo marcado en las casillas, en una sola vez."""
        self.ensure_one()
        Linea = self.env["comercio.lista.importacion.linea"]
        productos = Linea
        if self.revisar_marcadas:
            productos |= self.linea_ids.filtered(lambda li: li._tipo_ia())
        if self.revisar_duplicados:
            productos |= self._sin_sugerencia("duplicado")
        if self.revisar_nuestros:
            productos |= self._sin_sugerencia("vinculo")
        problemas = self._con_problema() if self.revisar_problemas else Linea
        if self.revisar_marcadas:
            problemas |= self.linea_ids.filtered(lambda li: li.accion == motor.REVISAR and li.estado == "pendiente")
        if not productos and not problemas:
            raise UserError(_("No hay nada para revisar con lo marcado: todo ya tiene sugerencia de la IA."))
        mensajes, faltan, tipo = [], 0, "info"
        if productos:
            faltan += max(0, len(productos) - MAXIMO_POR_VEZ)
            r = productos[:MAXIMO_POR_VEZ].action_verificar_ia()
            mensajes.append(r["params"]["message"])
            tipo = r["params"].get("type", tipo)
        if problemas:
            faltan += max(0, len(problemas) - MAXIMO_POR_VEZ)
            r = problemas[:MAXIMO_POR_VEZ]._sugerir_problemas_ia()
            mensajes.append(r["params"]["message"])
        if faltan:
            mensajes.append(_("Quedan %s filas: volvé a tocar «Revisar con IA» para seguir (van de a %s por "
                              "vez para no tardar ni gastar de más).", faltan, MAXIMO_POR_VEZ))
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Revisión con IA"), "message": " ".join(mensajes), "type": tipo, "sticky": bool(faltan),
            "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def action_aceptar(self):
        """«Aceptar lo que sugirió la IA»: une lo que es el mismo (nunca agrega productos)."""
        self.ensure_one()
        filas = (self.linea_ids or self._filas_de()).filtered(
            lambda li: li._tipo_ia() in ("duplicado", "nuevo") and li.ia_veredicto)
        if not filas:
            raise UserError(_("No hay sugerencias de la IA para aceptar: primero revisá con la IA."))
        return filas[:MAXIMO_POR_VEZ].action_aceptar_ia()
