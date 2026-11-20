from odoo import _, fields, models
from odoo.exceptions import UserError


class ComercioCorregirFilaWizard(models.TransientModel):
    """Corregir a mano una fila que la lista trajo mal (sin precio, precio 0, mal copiada)."""

    _name = "comercio.corregir.fila.wizard"
    _description = "Corregir una fila de la lista del proveedor"

    linea_id = fields.Many2one("comercio.lista.importacion.linea", required=True, ondelete="cascade")
    problema = fields.Char(related="linea_id.detalle", string="Qué pasó")
    codigo = fields.Char(related="linea_id.codigo_proveedor", string="Código del proveedor")
    original = fields.Char("La lista dice", readonly=True)
    descripcion = fields.Char("Descripción")
    precio = fields.Float(
        "Precio de la lista", digits="Product Price",
        help="El precio como figura (o tendría que figurar) en la lista del proveedor: se le aplican los "
             "descuentos, el recargo, el IVA y el dólar de la lista, como a las demás filas. 0 = no cambiarlo.")

    precio_antes = fields.Float(digits="Product Price")  # el que traía la fila, para saber si cambió
    repetida = fields.Boolean(compute="_compute_repetida")
    mismo_barras = fields.Boolean(compute="_compute_repetida")

    def _compute_repetida(self):
        for w in self:
            w.repetida = "dos veces" in (w.linea_id.detalle or "")
            w.mismo_barras = "dos productos distintos" in (w.linea_id.detalle or "")

    def action_corregir(self):
        self.ensure_one()
        cambio_precio = self.precio and abs(self.precio - self.precio_antes) > 0.00001
        sin_cambios = not cambio_precio and (self.descripcion or "") == (self.linea_id.descripcion or "")
        if sin_cambios and self.repetida:
            # Código repetido en la lista: se queda la primera fila y esta queda resuelta (ignorada)
            self.linea_id.action_ignorar()
            self.linea_id.sudo().avisos = ((self.linea_id.avisos or "") + "\n" + _(
                "Repetida en la lista: se usa la primera fila (resuelto por %s).", self.env.user.name)).strip()
            return {"type": "ir.actions.client", "tag": "soft_reload"}
        if sin_cambios and self.mismo_barras:
            # Dos productos distintos con el mismo código de barras en la lista: este se carga como
            # otro producto, sin ese código (recibe el propio 20…; después se escanea el del envase)
            self.linea_id._corregir(sin_codigo_barras=True)
            return {"type": "ir.actions.client", "tag": "soft_reload"}
        if sin_cambios:
            raise UserError(_("No cambiaste nada: escribí el precio de la lista o corregí la descripción."))
        self.linea_id._corregir(descripcion=self.descripcion, precio=self.precio if cambio_precio else None)
        return {"type": "ir.actions.client", "tag": "soft_reload"}
