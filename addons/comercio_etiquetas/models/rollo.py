from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Rollo(models.Model):
    """Un tipo de rollo de la Zebra: se elige al imprimir y la etiqueta se acomoda a su medida.
    Se declaran en config/ (valores.yaml → etiquetas.rollos)."""

    _name = "comercio.etiqueta.rollo"
    _description = "Rollo de etiquetas"
    _order = "sequence, id"

    name = fields.Char("Rollo", required=True, translate=False)
    ancho_mm = fields.Float("Ancho (mm)", required=True,
                            help="De costado a costado de la etiqueta.")
    alto_mm = fields.Float("Alto (mm)", required=True, help="De corte a corte, sin el espacio entre etiquetas.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.depends("name", "ancho_mm", "alto_mm")
    def _compute_display_name(self):
        # «Chico · 40 × 25 mm»: la medida a la vista para elegir bien
        for rollo in self:
            rollo.display_name = f"{rollo.name} · {rollo.ancho_mm:g} × {rollo.alto_mm:g} mm"

    @api.constrains("ancho_mm", "alto_mm")
    def _check_medida(self):
        for rollo in self:
            if not (10 <= rollo.ancho_mm <= 120 and 10 <= rollo.alto_mm <= 200):
                raise ValidationError(self.env._("Medida fuera de rango para la Zebra: %s × %s mm.",
                                                 rollo.ancho_mm, rollo.alto_mm))
