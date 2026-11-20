import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..catalogo.costo import cadena, regla_de_familia


class ComercioListaRegla(models.Model):
    """Descuento extra de un proveedor para una familia de su lista o para un producto (30/10).

    Se suma en cadena a los descuentos de toda la lista: «sobre el 30 % de la lista, a los
    bulones les hacen otro 10 %». Una regla por familia vale para la primera fila cuya
    descripción (con la familia) o código contiene su texto; una por producto, para el
    código del proveedor exacto. Se aplica al importar o al «Recalcular costos».
    """

    _name = "comercio.lista.regla"
    _description = "Descuento extra de una lista de proveedor"
    _order = "lista_id, tipo, sequence, id"

    lista_id = fields.Many2one("comercio.lista.proveedor", "Lista", required=True, ondelete="cascade", index=True)
    tipo = fields.Selection([("familia", "Familia"), ("producto", "Producto")], required=True, default="familia")
    sequence = fields.Integer("Orden", default=10)
    contiene = fields.Char(
        "Familia (texto que aparece)",
        help="Texto de la descripción o del código, sin importar mayúsculas ni acentos. Varias opciones "
             "separadas por coma: «BULON, TUERCA». Si una fila entra en dos reglas, vale la primera.")
    codigo = fields.Char("Código del proveedor", help="El código del producto en la lista del proveedor.")
    # Elegir en lugar de escribir (06/11): la familia de las que trae la lista, o el producto buscándolo
    # por código o descripción en la última lista. Se guarda el texto o el código, que es lo que usa el
    # motor: la regla sigue valiendo con las listas que lleguen después.
    familia_id = fields.Many2one("comercio.lista.familia", "Familia", ondelete="set null",
                                 domain="[('lista_id', '=', lista_id)]",
                                 help="Elegí una de las familias de la lista (escribí parte del nombre).")
    linea_id = fields.Many2one("comercio.lista.importacion.linea", "Producto de la lista", ondelete="set null",
                               domain="[('importacion_id', '=', importacion_vigente_id)]",
                               context={"linea_con_codigo": True},
                               help="Buscalo por código o por descripción en la última lista del proveedor.")
    importacion_vigente_id = fields.Many2one(related="lista_id.importacion_vigente_id")
    filas = fields.Integer("Filas que entran", compute="_compute_filas",
                           help="Cuántas filas de la última lista toman este descuento.")
    descripcion = fields.Char("Producto", compute="_compute_descripcion")
    descuentos = fields.Char("Descuentos extra (%)", required=True, help="En cadena: «10» o «10+5».")
    nota = fields.Char("Nota", help="Por qué (p. ej. «acuerdo con el viajante, octubre»).")

    @api.constrains("descuentos")
    def _check_descuentos(self):
        for regla in self:
            try:
                if not cadena(regla.descuentos):
                    raise ValueError
            except ValueError as error:
                raise UserError(_("Descuentos: escribilos como «10» o «10+5» (porcentajes separados por +).")) \
                    from error

    @api.constrains("tipo", "contiene", "codigo")
    def _check_a_que_aplica(self):
        for regla in self:
            if regla.tipo == "familia" and not (regla.contiene or "").strip():
                raise UserError(_("Falta el texto de la familia (p. ej. «BULON»)."))
            if regla.tipo == "producto" and not (regla.codigo or "").strip():
                raise UserError(_("Falta el código del proveedor del producto."))

    @api.onchange("familia_id")
    def _onchange_familia_id(self):
        if self.familia_id:
            self.contiene = self.familia_id.name

    @api.onchange("linea_id")
    def _onchange_linea_id(self):
        if self.linea_id:
            self.codigo = self.linea_id.codigo_proveedor

    @api.depends("tipo", "contiene", "codigo", "sequence", "lista_id")
    def _compute_filas(self):
        """Filas de la última lista a las que les toca cada regla (una fila entra en la primera
        regla de familia que coincide, como en el motor)."""
        for lista in self.lista_id:
            reglas = self.filtered(lambda r, li=lista: r.lista_id == li)
            vigente = lista.importacion_vigente_id
            lineas = vigente.linea_ids if vigente else self.env["comercio.lista.importacion.linea"]
            por_regla = lineas._por_regla(lista.regla_ids)
            for regla in reglas:
                regla.filas = len(por_regla.get(regla.id, ()))
        (self - self.filtered("lista_id")).filas = 0

    def action_ver_filas(self):
        """Las filas de la última lista que toman este descuento."""
        self.ensure_one()
        vigente = self.lista_id.importacion_vigente_id
        ids = vigente.linea_ids._por_regla(self.lista_id.regla_ids).get(self.id, []) if vigente else []
        accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_catalogo.action_importacion_lineas")
        accion.update({"domain": [("id", "in", list(ids))], "context": {},
                       "name": _("Filas con «%s»", self.contiene or self.codigo)})
        return accion

    @api.depends("codigo", "lista_id")
    def _compute_descripcion(self):
        """La descripción del producto en la última lista del proveedor (para ver que el código es
        el correcto)."""
        Linea = self.env["comercio.lista.importacion.linea"].sudo()
        for regla in self:
            regla.descripcion = False
            if regla.tipo != "producto" or not regla.codigo or not regla.lista_id:
                continue
            vigente = self.env["comercio.lista.importacion"]._vigente_de(regla.lista_id)
            if vigente:
                linea = Linea.search([("importacion_id", "=", vigente.id),
                                      ("codigo_proveedor", "=", regla.codigo.strip())], limit=1)
                regla.descripcion = linea.descripcion or _("(no está en la última lista)")

    def para_el_motor(self):
        """(reglas por familia, excepciones por código) en el formato de catalogo.costo."""
        familias = [{"nombre": r.contiene, "contiene": r.contiene, "descuentos": r.descuentos}
                    for r in self.filtered(lambda r: r.tipo == "familia").sorted(lambda r: (r.sequence, r.id))]
        productos = {}
        for r in self.filtered(lambda r: r.tipo == "producto"):
            codigo = r.codigo.strip()
            productos[codigo] = "+".join(filter(None, [productos.get(codigo), r.descuentos]))
        return familias, productos


class ComercioListaFamilia(models.Model):
    """Una familia de la lista de un proveedor («ABRAZADERA CIERRE RAPIDO», «BULONERIA VARIOS»): el
    título de arriba de las filas o la columna de familia (FC: «Detalle»). Se rehace en cada
    simulación de la última lista, para elegirla en «Descuentos por familia» (06/11)."""

    _name = "comercio.lista.familia"
    _description = "Familia de la lista de un proveedor"
    _order = "name"

    lista_id = fields.Many2one("comercio.lista.proveedor", "Lista", required=True, ondelete="cascade", index=True)
    name = fields.Char("Familia", required=True)
    filas = fields.Integer("Filas")

    _familia_unica = models.Constraint("unique (lista_id, name)", "La familia ya está en esta lista.")

    @api.depends("name", "filas")
    def _compute_display_name(self):
        for familia in self:
            familia.display_name = _("%(n)s (%(f)s filas)", n=familia.name, f=familia.filas)
