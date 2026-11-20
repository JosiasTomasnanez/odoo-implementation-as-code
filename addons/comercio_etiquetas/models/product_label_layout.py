from odoo import fields, models

PLANTILLA = "comercio"
# Medida si no hay ningún rollo cargado: la etiqueta de Odoo (2,25" x 1,25")
ANCHO_MM, ALTO_MM = 57.0, 32.0
PUNTOS_POR_MM = 8  # Zebra de 203 dpi (ZD420)


class ProductLabelLayout(models.TransientModel):
    _inherit = "product.label.layout"

    zpl_template = fields.Selection(
        selection_add=[(PLANTILLA, "Comercio Ejemplo (nombre en 2 líneas)")],
        ondelete={PLANTILLA: "set default"}, default=PLANTILLA)
    # El último que eligió cada usuario queda como predeterminado (ir.default, como el formato)
    comercio_rollo_id = fields.Many2one(
        "comercio.etiqueta.rollo", string="Rollo",
        default=lambda self: self.env["comercio.etiqueta.rollo"].search([], limit=1))

    def _get_label_template_xml_id(self):
        self.ensure_one()
        if self.print_format == "zpl" and self.zpl_template == PLANTILLA:
            # Con QR, la plantilla de Odoo de tamaño normal (la propia es solo de código de barras)
            return ("comercio_etiquetas.barcode_comercio_label" if self.barcode_format == "barcode"
                    else "product.qr_normal_label")
        return super()._get_label_template_xml_id()

    def _comercio_medida(self):
        """(ancho, alto) en puntos de la Zebra, según el rollo elegido."""
        rollo = self.comercio_rollo_id
        ancho, alto = (rollo.ancho_mm, rollo.alto_mm) if rollo else (ANCHO_MM, ALTO_MM)
        return round(ancho * PUNTOS_POR_MM), round(alto * PUNTOS_POR_MM)

    def _comercio_posiciones(self):
        """Posiciones y tamaños (en puntos) de la etiqueta propia: diseñada para 57 x 32 mm (456 x 256
        puntos) y escalada a la medida del rollo, sin deformarla."""
        ancho, alto = self._comercio_medida()
        e = min(ancho / 456.0, alto / 256.0)

        # Las barras nunca más finas que 2 puntos (0,25 mm): con 1 punto el lector no las lee bien.
        # Un código de 13 dígitos en Code 128 mide ~130 módulos: 260 puntos, entra en 40 mm (320).
        def s(v):
            return max(1, round(v * e))

        return {"ancho": ancho, "alto": alto, "margen": s(8),
                "nombre_y": s(8), "nombre_letra": s(26), "nombre_ancho": ancho - 2 * s(8), "nombre_interlinea": s(2),
                "barras_x": s(40), "barras_y": s(70), "barras_modulo": max(2, s(2)), "barras_alto": s(90),
                "ref_y": s(220), "ref_letra": s(22),
                "precio_x": ancho - s(8), "precio_y": s(212), "precio_letra": s(36)}

    def _prepare_report_data(self):
        xml_id, data = super()._prepare_report_data()
        data["comercio_zpl"] = self._comercio_posiciones()
        return xml_id, data

    def _save_user_defaults(self):
        super()._save_user_defaults()
        if self.comercio_rollo_id:
            self.env["ir.default"].sudo().set(self._name, "comercio_rollo_id", self.comercio_rollo_id.id,
                                              user_id=self.env.uid)
