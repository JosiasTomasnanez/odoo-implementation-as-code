from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..medidas import FORMATOS, LETRAS, REDONDEOS, letra_que_entra, pesos, redondear_arriba, ubicaciones
from ..medidas import ALTO_UTIL, ANCHO_UTIL

MAXIMO_HOJAS = 200  # por impresión


class ComercioCartel(models.Model):
    _name = "comercio.cartel"
    _description = "Cartel de precio"
    _inherit = ["mail.thread"]
    _order = "write_date desc, id desc"

    name = fields.Char("Título", required=True, tracking=True,
                       help="Lo que dice el cartel en grande. Viene con el nombre del producto; se puede "
                            "escribir lo que se quiera (un salto de línea lo parte en dos).")
    aclaracion = fields.Char("Aclaración", help="Al lado del precio: «x kg», «c/u», «la bolsa de 25 kg».")
    product_tmpl_id = fields.Many2one("product.template", "Producto", index=True,
                                      help="De dónde sale el precio. Vacío: un cartel suelto con precio a mano.")
    modo_precio = fields.Selection([("odoo", "El de Odoo (con IVA)"), ("manual", "Escrito a mano")],
                                   "Precio", default="odoo", required=True, tracking=True)
    redondeo = fields.Selection(REDONDEOS, "Redondear hacia arriba", default="10", required=True,
                                help="Solo con el precio de Odoo. Nunca baja el precio.")
    precio_manual = fields.Float("Precio a mano", digits=(16, 2), tracking=True)
    precio_odoo = fields.Float("Precio de Odoo con IVA", compute="_compute_precio", store=True, digits=(16, 2))
    precio = fields.Float("Precio del cartel", compute="_compute_precio", store=True, digits=(16, 2))
    precio_antes = fields.Float("Antes (tachado)", digits=(16, 2),
                                help="Para ofertas: el precio anterior, tachado. Vacío: no se muestra.")
    mostrar_codigo_barras = fields.Boolean("Con código de barras",
                                           help="El código del producto, chico, abajo (si tiene).")
    formato = fields.Selection([("1", "1 por hoja (A4 entera)"), ("2", "2 por hoja (media A4)"),
                                ("4", "4 por hoja"), ("8", "8 por hoja")],
                               "Tamaño", default="2", required=True)
    estilo = fields.Selection([("clasico", "Clásico"), ("oferta", "Oferta")], default="clasico", required=True)
    copias = fields.Integer(default=1, required=True)
    precio_impreso = fields.Float("Precio impreso", digits=(16, 2), readonly=True, copy=False)
    fecha_impreso = fields.Datetime("Impreso el", readonly=True, copy=False)
    desactualizado = fields.Boolean(
        "Para reimprimir", compute="_compute_desactualizado", store=True,
        help="Ya se imprimió y hoy mostraría otro precio (cambió el precio de venta del producto).")
    active = fields.Boolean(default=True)
    vista_previa = fields.Html("Vista previa", compute="_compute_vista_previa", sanitize=False)

    # Topes: un error de tipeo (10.000 copias) no deja al servidor armando miles de hojas
    _check_copias = models.Constraint("CHECK(copias BETWEEN 1 AND 200)",
                                      "Las copias de un cartel van de 1 a 200.")

    @api.depends("modo_precio", "redondeo", "precio_manual", "product_tmpl_id.list_price",
                 "product_tmpl_id.taxes_id")
    def _compute_precio(self):
        for cartel in self:
            cartel.precio_odoo = cartel.product_tmpl_id._comercio_precio_con_iva() if cartel.product_tmpl_id else 0.0
            if cartel.modo_precio == "manual" or not cartel.product_tmpl_id:
                cartel.precio = cartel.precio_manual
            else:
                cartel.precio = redondear_arriba(cartel.precio_odoo, float(cartel.redondeo))

    @api.depends("precio", "precio_impreso", "fecha_impreso")
    def _compute_desactualizado(self):
        for cartel in self:
            cartel.desactualizado = bool(cartel.fecha_impreso) and abs(cartel.precio - cartel.precio_impreso) > 0.005

    @api.depends("name", "aclaracion", "precio", "precio_antes", "formato", "estilo", "mostrar_codigo_barras",
                 "product_tmpl_id")
    def _compute_vista_previa(self):
        """El cartel como va a salir, achicado (el mismo diseño que el PDF: report/cartel_report.xml).
        Se actualiza mientras se edita la ficha."""
        for cartel in self:
            columnas, filas = FORMATOS[cartel.formato or "2"]
            ancho, alto = ANCHO_UTIL / columnas, ALTO_UTIL / filas
            escala = round(min(1.0, 105.0 / ancho, 120.0 / alto), 3)  # ~ 400 × 450 px en pantalla
            # Todo multiplicado por la escala (el campo de la ficha no deja usar «transform: scale»)
            letras = cartel._letras()
            letras.update(titulo_pt=round(letras["titulo_pt"] * escala, 1),
                          precio_pt=round(letras["precio_pt"] * escala, 1))
            lugar = {"x": 0, "y": 0, "ancho": round(ancho * escala, 1), "alto": round(alto * escala, 1), **letras}
            cartel.vista_previa = self.env["ir.qweb"]._render(
                "comercio_carteles.cartel_vista", {"c": cartel, "l": lugar})

    def action_ver_pdf(self):
        """El PDF tal cual, para revisarlo (no cuenta como impreso)."""
        return self.env.ref("comercio_carteles.action_report_carteles").report_action(self)

    @api.onchange("product_tmpl_id")
    def _onchange_producto(self):
        if self.product_tmpl_id and not self.name:
            self.name = self.product_tmpl_id.name
        if self.product_tmpl_id and not self.aclaracion:
            self.aclaracion = self.product_tmpl_id._comercio_aclaracion_cartel()

    # ------------------------------------------------------------------ imprimir
    def action_imprimir(self):
        """PDF A4 con los carteles elegidos (cada uno con sus copias) y guarda el precio impreso."""
        if not self:
            raise UserError(_("Elegí los carteles a imprimir."))
        sin_precio = self.filtered(lambda c: c.precio <= 0)
        if sin_precio:
            raise UserError(_("«%s» no tiene precio: elegí el producto o escribí el precio a mano.",
                              sin_precio[0].name))
        self.write({"fecha_impreso": fields.Datetime.now()})
        for cartel in self:
            cartel.precio_impreso = cartel.precio
        return self.env.ref("comercio_carteles.action_report_carteles").report_action(self)

    # ------------------------------------------------------------------ armado de las hojas
    def _hojas(self):
        """Las hojas A4 del PDF: los carteles con sus copias, agrupados por tamaño (una hoja tiene
        carteles de un solo tamaño). Cada uno con su posición y el tamaño de sus letras."""
        por_formato = {}
        for cartel in self:
            por_formato.setdefault(cartel.formato, []).extend([cartel] * min(max(cartel.copias, 1), 200))
        total = sum(-(-len(lista) // len(ubicaciones(formato))) for formato, lista in por_formato.items())
        if total > MAXIMO_HOJAS:
            raise UserError(_("Son %(n)s hojas: se imprimen hasta %(m)s por vez. Elegí menos carteles o copias.",
                              n=total, m=MAXIMO_HOJAS))
        hojas = []
        for formato in ("1", "2", "4", "8"):
            lista = por_formato.get(formato, [])
            lugares = ubicaciones(formato)
            for desde in range(0, len(lista), len(lugares)):
                hojas.append([dict(lugar, cartel=c, **c._letras()) for c, lugar
                              in zip(lista[desde:desde + len(lugares)], lugares, strict=False)])
        return hojas

    def _letras(self):
        """Letras lo más grandes posible sin que se corten (el lugar de cada parte, en mm)."""
        self.ensure_one()
        tope_titulo, tope_precio = LETRAS[self.formato]
        columnas, filas = FORMATOS[self.formato]
        ancho, alto = ANCHO_UTIL / columnas * 0.92 * 0.88, ALTO_UTIL / filas * 0.92  # adentro del marco
        oferta, barras = self.estilo == "oferta", self.mostrar_codigo_barras and self.product_tmpl_id.barcode
        texto_precio = pesos(self.precio)
        alto_titulo = alto * (0.38 if oferta else 0.42)
        alto_precio = alto * (0.26 if barras else 0.32) * (0.75 if self.precio_antes else 1.0)
        # El precio va en una línea; la aclaración al lado ocupa ~3 letras más
        # El precio en una línea; abajo, la aclaración (~30 % de alto)
        precio_pt = letra_que_entra(texto_precio, ancho, alto_precio / (1.3 if self.aclaracion else 1.0),
                                    tope_precio, interlineado=1.0, una_linea=True)
        return {"titulo_pt": letra_que_entra((self.name or "").upper(), ancho, alto_titulo, tope_titulo),
                "precio_pt": precio_pt,
                "texto_precio": texto_precio,
                "texto_antes": pesos(self.precio_antes) if self.precio_antes else "",
                "lineas_titulo": (self.name or "").split("\n")}
