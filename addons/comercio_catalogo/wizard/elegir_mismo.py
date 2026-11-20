import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def igual_letra(texto):
    """«ABRAZADERA SINFIN  10-16 MM» y «Abrazadera sinfín 10-16 mm» escritos igual, para comparar:
    minúsculas, la primera en mayúscula y sin espacios de más."""
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    # Lo que va entre corchetes («[EJ]», una referencia) queda como está
    partes = re.split(r"(\[[^\]]*\])", texto)
    texto = "".join(parte if parte.startswith("[") else parte.lower() for parte in partes)
    primera = next((i for i, ch in enumerate(texto) if ch.isalpha() and not _entre_corchetes(texto, i)), None)
    return texto if primera is None else texto[:primera] + texto[primera].upper() + texto[primera + 1:]


def _entre_corchetes(texto, i):
    return texto.rfind("[", 0, i) > texto.rfind("]", 0, i)


class ComercioElegirMismoWizard(models.TransientModel):
    """«Es el mismo» con varios parecidos: elegir cuál de nuestros productos es (30/10, pedido del
    cliente). Los nombres se muestran escritos igual que la descripción del proveedor."""

    _name = "comercio.elegir.mismo.wizard"
    _description = "Elegir el producto que es el mismo"

    linea_id = fields.Many2one("comercio.lista.importacion.linea", required=True, ondelete="cascade")
    del_proveedor = fields.Char("En la lista del proveedor", compute="_compute_del_proveedor")
    opcion_ids = fields.One2many("comercio.elegir.mismo.opcion", "wizard_id")
    opcion_id = fields.Many2one("comercio.elegir.mismo.opcion", "Es el mismo que",
                                domain="[('wizard_id', '=', id)]")

    @api.model_create_multi
    def create(self, vals_list):
        asistentes = super().create(vals_list)
        for w in asistentes:  # una opción por parecido, con el nombre escrito igual
            w.opcion_ids = [(0, 0, {"producto_id": p.id, "name": igual_letra(p.name)})
                            for p in w.linea_id.candidato_ids]
        return asistentes

    @api.depends("linea_id")
    def _compute_del_proveedor(self):
        for w in self:
            w.del_proveedor = igual_letra(w.linea_id.descripcion)

    def action_confirmar(self):
        self.ensure_one()
        if not self.opcion_id:
            raise UserError(_("Elegí cuál de los productos es (o «Cancelar» y «Agregar como nuevo» si no es ninguno)."))
        self.linea_id.producto_elegido_id = self.opcion_id.producto_id
        self.linea_id.action_es_el_mismo()
        return {"type": "ir.actions.client", "tag": "soft_reload"}


class ComercioElegirMismoOpcion(models.TransientModel):
    _name = "comercio.elegir.mismo.opcion"
    _description = "Un producto parecido para elegir"

    wizard_id = fields.Many2one("comercio.elegir.mismo.wizard", required=True, ondelete="cascade")
    producto_id = fields.Many2one("product.template", required=True, ondelete="cascade")
    name = fields.Char(required=True)
