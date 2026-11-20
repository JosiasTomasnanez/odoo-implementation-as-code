import logging

from odoo import _, api, fields, models
from odoo.addons.comercio_catalogo_ia.ia import verificar as gemini
from odoo.addons.comercio_catalogo_ia.models.importacion import _configuracion
from odoo.exceptions import UserError

from ..ia import categorizar as ia

_logger = logging.getLogger(__name__)

# Con esta confianza o más, la sugerencia de la IA viene marcada para aplicar (igual se revisa)
CONFIANZA_PARA_MARCAR = 0.8


class ComercioPosCategorizar(models.TransientModel):
    """Poner la categoría del punto de venta (los botones de arriba del POS) a varios productos:
    a mano (se eligen las categorías) o con la sugerencia de la IA, que se revisa antes de
    aplicar. No toca costos ni precios."""

    _name = "comercio.pos.categorizar"
    _description = "Categorizar productos del punto de venta"

    modo = fields.Selection([("manual", "A mano"), ("ia", "Con IA")], required=True, default="manual")
    producto_ids = fields.Many2many("product.template", string="Productos")
    categoria_ids = fields.Many2many("pos.category", string="Categorías del punto de venta",
                                     help="Se agregan a cada producto elegido.")
    reemplazar = fields.Boolean(
        "Reemplazar las que ya tienen",
        help="Marcado: cada producto queda solo con estas categorías (sin ninguna elegida, quedan sin "
             "categoría). Sin marcar: se agregan a las que ya tenga (un producto puede estar en varios "
             "botones).")
    linea_ids = fields.One2many("comercio.pos.categorizar.linea", "asistente_id", string="Sugerencias")
    resumen = fields.Text(readonly=True)

    # ------------------------------------------------------------------ apertura

    @api.model
    def _abrir(self, asistente, titulo):
        return {"type": "ir.actions.act_window", "name": titulo, "res_model": self._name,
                "res_id": asistente.id, "view_mode": "form", "target": "new",
                "context": {"dialog_size": "extra-large"}}  # que se lean nombre, categoría y motivo

    @api.model
    def abrir_a_mano(self, productos):
        if not productos:
            raise UserError(_("Elegí los productos a categorizar."))
        asistente = self.create({"modo": "manual", "producto_ids": [(6, 0, productos.ids)]})
        return self._abrir(asistente, _("Categorizar a mano"))

    @api.model
    def abrir_con_ia(self, productos):
        """Pide a la IA la categoría de los elegidos que todavía no tienen ninguna y abre las
        sugerencias para revisarlas. Nada se escribe en los productos hasta «Aplicar»."""
        if not productos:
            raise UserError(_("Elegí los productos a categorizar."))
        sin_categoria = productos.filtered(lambda p: not p.pos_categ_ids)
        salteados = len(productos) - len(sin_categoria)
        if not sin_categoria:
            raise UserError(_("Los %s productos elegidos ya tienen categoría del punto de venta. Para "
                              "cambiarla, usá «Categorizar a mano».", len(productos)))
        if len(sin_categoria) > ia.MAXIMO_POR_VEZ:
            raise UserError(_("Son %(n)s productos sin categoría: la IA categoriza hasta %(m)s por vez. "
                              "Elegí menos (por ejemplo, filtrando por rubro).",
                              n=len(sin_categoria), m=ia.MAXIMO_POR_VEZ))
        categorias = self.env["pos.category"].search([])
        if not categorias:
            raise UserError(_("Todavía no hay categorías del punto de venta: creálas en Punto de venta → "
                              "Configuración → Categorías del PdV y volvé a probar."))
        clave, modelos = _configuracion()
        if not clave:
            raise UserError(_("Falta la clave de la IA (GEMINI_API_KEY) en el servidor."))
        filas = [{"fila": p.id, "nombre": p.name, "rubro": p.categ_id.complete_name or ""} for p in sin_categoria]
        try:
            sugerencias, consumo = ia.categorizar(
                filas, [{"id": c.id, "nombre": c.complete_name} for c in categorias], clave, modelos)
        except gemini.ErrorIA as error:
            raise UserError(_("No se pudo consultar a la IA: %s", error)) from error
        _logger.info("IA categorías POS: %s productos, %s pedidos, %s tokens (%s)", len(filas),
                     consumo.pedidos, consumo.tokens, consumo.modelo)
        resumen = _("La IA (%(modelo)s) sugirió categoría para %(con)s de %(n)s productos; revisá y "
                    "tocá «Aplicar». Consumo: %(p)s pedidos, %(t)s tokens.",
                    modelo=consumo.modelo or "-", con=len([s for s in sugerencias if s.categoria_id]),
                    n=len(filas), p=consumo.pedidos, t=consumo.tokens)
        if salteados:
            resumen += "\n" + _("%s ya tenían categoría y se saltearon (se cambian con «Categorizar a mano»).",
                                salteados)
        asistente = self.create({
            "modo": "ia", "producto_ids": [(6, 0, sin_categoria.ids)], "resumen": resumen,
            "linea_ids": [(0, 0, {
                "producto_id": s.fila, "categoria_id": s.categoria_id or False, "confianza": s.confianza,
                "motivo": s.motivo,
                "aplicar": bool(s.categoria_id) and s.confianza >= CONFIANZA_PARA_MARCAR,
            }) for s in sugerencias],
        })
        return self._abrir(asistente, _("Categorizar con IA"))

    # ------------------------------------------------------------------ aplicar

    def action_aplicar(self):
        """Escribe solo la categoría del punto de venta. Como sistema: el encargado del punto de
        venta (grupo de las acciones) puede leer los productos pero no editarlos; en el chatter
        queda quién fue."""
        self.ensure_one()
        usuario = self.env.user.name
        autor = self.env.user.partner_id.id
        # Antes del sudo: los productos y categorías tienen que ser visibles para quien aplica
        # (reglas de acceso, p. ej. de empresa), y las sugerencias, de los productos del asistente
        self.producto_ids.check_access("read")
        (self.categoria_ids | self.linea_ids.categoria_id).check_access("read")
        if self.linea_ids.producto_id - self.producto_ids:
            raise UserError(_("Hay sugerencias de productos que no están en este asistente."))
        if self.modo == "manual":
            if not self.categoria_ids and not self.reemplazar:
                raise UserError(_("Elegí al menos una categoría del punto de venta. Para quitarles todas, "
                                  "dejá las categorías vacías y marcá «Reemplazar las que ya tienen»."))
            # Reemplazar sin categorías = quedan sin ninguna (para quitarlas)
            comando = [(6, 0, self.categoria_ids.ids)] if self.reemplazar else \
                [(4, c.id) for c in self.categoria_ids]
            productos = self.producto_ids.sudo()
            productos.write({"pos_categ_ids": comando})
            nombres = ", ".join(self.categoria_ids.mapped("name")) or _("ninguna (se quitaron)")
            for producto in productos:
                producto.message_post(author_id=autor, body=_(
                    "Categoría del punto de venta: %(c)s (a mano, %(u)s).", c=nombres, u=usuario))
            aplicados = len(self.producto_ids)
        else:
            lineas = self.linea_ids.filtered(lambda li: li.aplicar and li.categoria_id)
            if not lineas:
                raise UserError(_("No hay sugerencias marcadas para aplicar (o les falta la categoría)."))
            for linea in lineas:
                producto = linea.producto_id.sudo()
                producto.write({"pos_categ_ids": [(4, linea.categoria_id.id)]})
                producto.message_post(author_id=autor, body=_(
                    "Categoría del punto de venta: %(c)s (sugerida por la IA, aplicada por %(u)s).",
                    c=linea.categoria_id.name, u=usuario))
            aplicados = len(lineas)
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Categorías del punto de venta"),
            "message": _("%s productos categorizados.", aplicados), "type": "success",
            "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}


class ComercioPosCategorizarLinea(models.TransientModel):
    _name = "comercio.pos.categorizar.linea"
    _description = "Sugerencia de categoría del punto de venta"

    asistente_id = fields.Many2one("comercio.pos.categorizar", required=True, ondelete="cascade")
    aplicar = fields.Boolean("Aplicar")
    producto_id = fields.Many2one("product.template", "Producto", required=True, readonly=True)
    rubro = fields.Char(related="producto_id.categ_id.complete_name", string="Rubro")
    categoria_id = fields.Many2one("pos.category", "Categoría del PdV",
                                   help="La que sugirió la IA; se puede cambiar antes de aplicar.")
    confianza = fields.Float("Confianza", readonly=True, digits=(3, 2))
    motivo = fields.Char("Motivo", readonly=True)

    @api.onchange("categoria_id")
    def _onchange_categoria_id(self):
        # Elegir o cambiar la categoría a mano la deja marcada para aplicar
        for linea in self:
            linea.aplicar = bool(linea.categoria_id)
