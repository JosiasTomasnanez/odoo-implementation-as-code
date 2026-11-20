import base64
import io
import os

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from ..catalogo.convertir import hojas, leer_tabla, redetectar
from ..models.lista_proveedor import DOCUMENTOS, EXTENSIONES

MIN_FILAS_HOJA = 5  # una hoja con menos filas con datos no se marca sola (portada, notas…)
FOTOS = (".jpg", ".jpeg", ".png", ".webp")
LADO_MAXIMO = 2000  # px por foto al juntarlas: se lee la letra chica y el PDF no pesa de más
MAX_FOTOS = 10  # páginas que lee la IA por lista
MAX_PIXELES = 50_000_000  # ~50 MP: más que cualquier celular; evita imágenes armadas para colgar el servidor


def fotos_a_pdf(fotos: list[tuple[str, bytes]]) -> bytes:
    """Varias fotos de una lista (en orden) → un PDF con una página por foto, que se lee
    como un PDF escaneado. Respeta la rotación que guarda el celular."""
    from PIL import Image, ImageOps  # viene con Odoo

    if len(fotos) > MAX_FOTOS:
        raise UserError(_("Son %(n)s fotos: la IA lee hasta %(m)s páginas por lista.", n=len(fotos), m=MAX_FOTOS))
    paginas = []
    for nombre, contenido in fotos:
        try:
            # Solo formatos de foto, y el tamaño se mira antes de descomprimir (una imagen
            # armada a propósito puede ocupar toda la memoria del servidor)
            imagen = Image.open(io.BytesIO(contenido), formats=["JPEG", "PNG", "WEBP"])
            if imagen.width * imagen.height > MAX_PIXELES:
                raise UserError(_("«%s» es demasiado grande: sacá la foto con menos resolución.", nombre))
            imagen.draft("RGB", (LADO_MAXIMO, LADO_MAXIMO))  # JPEG: decodifica ya achicada
            imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
            imagen = ImageOps.exif_transpose(imagen).convert("RGB")
        except UserError:
            raise
        except Exception as error:  # noqa: BLE001 - archivo dañado o que no es una foto
            raise UserError(_("«%s» no es una foto que se pueda leer.", nombre)) from error
        paginas.append(imagen)
    salida = io.BytesIO()
    paginas[0].save(salida, "PDF", save_all=True, append_images=paginas[1:], resolution=150)
    return salida.getvalue()


class ComercioImportarListaWizard(models.TransientModel):
    """Subir el Excel de un proveedor: se simula y se abre para revisar.

    Se elige el proveedor (o se crea escribiendo su nombre); su «lista» se crea sola la
    primera vez, con las columnas sugeridas a partir del archivo.
    """

    _name = "comercio.importar.lista.wizard"
    _description = "Importar la lista de un proveedor"

    partner_id = fields.Many2one(
        "res.partner", "Proveedor", required=True,
        # Solo proveedores o empresas: que no aparezcan empleados ni clientes particulares
        # ni la propia empresa (no se compra a sí misma)
        domain="['|', ('supplier_rank', '>', 0), ('is_company', '=', True), ('ref_company_ids', '=', False)]",
        help="Elegir uno existente o escribir el nombre de uno nuevo y tocar «Crear».",
    )
    lista_id = fields.Many2one(
        "comercio.lista.proveedor", "Lista", compute="_compute_lista_id", readonly=False, store=True,
        domain="[('partner_id', '=', partner_id)]",
        help="El proveedor manda la lista en partes: elegir cuál es este archivo.")
    categoria_id = fields.Many2one(
        "product.category", "Rubro por defecto", compute="_compute_categoria_id", store=True, readonly=False,
        help="Categoría que traen marcada los productos de la lista que no tenemos; en cada uno se "
        "puede cambiar. Queda guardada en la lista del proveedor para la próxima vez.")
    # El descuento general antes de simular (19/11): cargado después, cada corrección es otra
    # importación y se llenan las importaciones. El IVA no va acá (se revisa en la ficha).
    descuentos = fields.Char(
        "Descuento de la lista (%)", compute="_compute_ajustes", store=True, readonly=False,
        help="«10» o «10+10». Queda guardado para la próxima lista de este proveedor. Vacío: no cambia "
             "el que ya tenía (para sacarlo, en la ficha del proveedor).")
    nueva_parte = fields.Boolean(
        "Es otra parte (productos distintos)",
        help="Marcarlo si este archivo trae otros productos del mismo proveedor (p. ej. su lista de "
        "bulones aparte): se crea una parte nueva y no se compara con la que ya tiene, así lo que no "
        "viene en este archivo no se da de baja allá.")
    nombre_parte = fields.Char("Nombre de la parte", help="P. ej. «Bulones» o «Herramientas».")
    tiene_listas = fields.Boolean(compute="_compute_cuantas")
    es_nueva = fields.Boolean(compute="_compute_cuantas")
    varias_listas = fields.Boolean(compute="_compute_cuantas")
    archivo = fields.Binary(
        "Archivo (Excel, CSV, PDF o foto)", required=True,
        help="Lo mejor es el Excel. Un PDF con texto se lee igual; una foto o un PDF escaneado los lee la IA "
        "(varias fotos: la primera acá y las demás en «Más fotos»).")
    nombre_archivo = fields.Char()
    es_foto = fields.Boolean(compute="_compute_es_foto")
    mas_fotos_ids = fields.Many2many(
        "ir.attachment", string="Más fotos",
        help="Si la lista vino en varias fotos: las otras páginas, en orden. Se juntan con la "
        "primera en un solo PDF (hasta 10 páginas en total) y lo lee la IA.")
    hoja_ids = fields.One2many(
        "comercio.importar.lista.hoja", "wizard_id", "Hojas del archivo",
        help="El Excel trae varias hojas: cada una que se marque es una parte de la lista del "
        "proveedor (p. ej. «General» y «Bulones»), con sus bajas por separado.")

    @api.model
    def default_get(self, fields_list):
        valores = super().default_get(fields_list)
        lista = self.env["comercio.lista.proveedor"].browse(self.env.context.get("default_lista_id"))
        if lista.exists() and "partner_id" in fields_list:
            valores["partner_id"] = lista.partner_id.id
        return valores

    def _listas_de(self, partner):
        return self.env["comercio.lista.proveedor"].search([("partner_id", "=", partner.id)]) \
            if partner else self.env["comercio.lista.proveedor"]

    @api.depends("partner_id")
    def _compute_lista_id(self):
        pedida = self.env["comercio.lista.proveedor"].browse(self.env.context.get("default_lista_id")).exists()
        for wizard in self:
            listas = self._listas_de(wizard.partner_id)
            if pedida and pedida in listas:
                wizard.lista_id = pedida  # desde el botón «Importar» de una lista
            elif wizard.lista_id not in listas or not wizard.lista_id:
                # Con varias partes no se adivina: la elige la persona
                wizard.lista_id = listas if len(listas) == 1 else listas.browse()

    @api.depends("lista_id")
    def _compute_categoria_id(self):
        for wizard in self:
            wizard.categoria_id = wizard.lista_id.categoria_id or wizard.categoria_id

    @api.depends("lista_id")
    def _compute_ajustes(self):
        for wizard in self:
            wizard.descuentos = wizard.lista_id.descuentos or False

    def _ajustes(self):
        """Descuento del asistente, para guardar en la lista que se importa."""
        return {"descuentos": (self.descuentos or "").strip() or False}

    def _guardar_ajustes(self, lista):
        # Vacío = no se toca lo que la lista ya tenía (20/11, pedido del usuario: con varias partes
        # el campo aparece vacío hasta elegir la parte, y aceptar así borraba el descuento). Para
        # sacar un descuento se borra en la ficha del proveedor.
        vals = {k: v for k, v in self._ajustes().items() if v and (lista[k] or False) != v}
        if vals:
            lista.write(vals)  # valida el formato de los descuentos («10+10»)

    def _mismo_proveedor_con_otro_nombre(self, partner):
        """Otro proveedor que ya existe con el mismo nombre (sin mirar mayúsculas ni espacios):
        20/11, se creó «RHO» teniendo «Rho» con su ficha, y quedaron dos proveedores."""
        if not partner or not partner.name:
            return self.env["res.partner"]
        clave = " ".join(partner.name.split()).casefold()
        parecidos = self.env["res.partner"].search([
            ("id", "!=", partner.id), ("name", "ilike", partner.name.split()[0]),
            "|", ("supplier_rank", ">", 0), ("is_company", "=", True)])
        iguales = parecidos.filtered(lambda p: " ".join((p.name or "").split()).casefold() == clave)
        # Primero el que ya tiene la ficha de la lista
        return iguales.sorted(lambda p: not self._listas_de(p))[:1]

    @api.onchange("partner_id")
    def _onchange_partner_repetido(self):
        if self.partner_id and not self._listas_de(self.partner_id):
            otro = self._mismo_proveedor_con_otro_nombre(self.partner_id)
            if otro:
                repetido = self.partner_id.name
                self.partner_id = otro
                return {"warning": {"title": _("Ese proveedor ya existe"), "message": _(
                    "Ya hay un proveedor «%(o)s»: se usa ese, con su ficha y sus listas. («%(n)s» quedó "
                    "creado de más y sin usar: se puede archivar en Contactos.)", o=otro.name, n=repetido)}}

    @api.depends("partner_id")
    def _compute_cuantas(self):
        for wizard in self:
            listas = self._listas_de(wizard.partner_id)
            wizard.es_nueva = bool(wizard.partner_id) and not listas
            wizard.tiene_listas = bool(listas)
            wizard.varias_listas = len(listas) > 1

    @api.depends("nombre_archivo")
    def _compute_es_foto(self):
        for wizard in self:
            wizard.es_foto = (wizard.nombre_archivo or "").lower().endswith(FOTOS)

    def _contenido(self):
        valor = self.archivo
        if hasattr(valor, "content"):
            return valor.content
        return base64.b64decode(valor) if valor else b""

    @api.onchange("archivo", "nombre_archivo", "partner_id")
    def _onchange_hojas(self):
        """Excel con varias hojas con productos: se ofrecen para elegir cuáles importar. Cada una
        es una parte; si ya existe (misma hoja), se usa esa con sus columnas."""
        encontradas = hojas(self._contenido(), self.nombre_archivo or "") if self.archivo else []
        con_datos = [(n, f) for n, f in encontradas if f]
        if len(con_datos) < 2:
            self.hoja_ids = [Command.clear()]
            return
        listas = self._listas_de(self.partner_id)
        primera = encontradas[0][0]

        def parte_de(nombre):
            clave = nombre.strip().lower()
            for lista in listas:
                if (lista.hoja or "").strip().lower() == clave or (lista.parte or "").strip().lower() == clave:
                    return lista
            # La lista de siempre, sin hoja elegida, lee la primera
            sin_hoja = listas.filtered(lambda li: not li.hoja)
            return sin_hoja[:1] if nombre == primera and len(sin_hoja) == 1 else listas.browse()

        def parece_lista(nombre):
            """Se marca sola si ya es una parte de este proveedor o si se encuentran el costo y el
            código o la descripción (no los carteles, la hoja de cuentas bancarias, el índice…)."""
            try:
                return bool(redetectar(leer_tabla(self._contenido(), self.nombre_archivo or "", nombre)))
            except Exception:  # noqa: BLE001 - una hoja rara no frena el asistente
                return False

        lineas = [Command.clear()]
        for nombre, filas in con_datos:
            lista = parte_de(nombre)
            lineas.append(Command.create({
                "nombre": nombre, "filas": filas, "lista_id": lista.id,
                "importar": filas >= MIN_FILAS_HOJA and (bool(lista) or parece_lista(nombre)),
                "categoria_id": (lista.categoria_id or self.categoria_id).id}))
        self.hoja_ids = lineas

    def _importar_hojas(self, nombre):
        """Una importación por hoja marcada; las partes que faltan se crean."""
        elegidas = self.hoja_ids.filtered("importar")
        if not elegidas:
            raise UserError(_("Marcá al menos una hoja para importar."))
        Lista = self.env["comercio.lista.proveedor"]
        listas = self._listas_de(self.partner_id)
        varias = len(listas | elegidas.lista_id) + len(elegidas.filtered(lambda h: not h.lista_id)) > 1
        importaciones = self.env["comercio.lista.importacion"]
        for hoja in elegidas:
            lista = hoja.lista_id
            if not lista:
                lista = Lista.create({"partner_id": self.partner_id.id, "parte": hoja.nombre, "hoja": hoja.nombre,
                                      "categoria_id": (hoja.categoria_id or self.categoria_id).id})
            else:
                vals = {}
                if not lista.hoja:
                    vals["hoja"] = hoja.nombre
                if varias and not lista.parte:
                    vals["parte"] = hoja.nombre
                if hoja.categoria_id and lista.categoria_id != hoja.categoria_id:
                    vals["categoria_id"] = hoja.categoria_id.id
                if vals:
                    lista.write(vals)
            importaciones |= lista._importar_archivo(self._contenido(), nombre, origen="manual")
        if len(importaciones) == 1:
            return importaciones.action_abrir()
        accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_catalogo.action_importaciones")
        accion["domain"] = [("id", "in", importaciones.ids)]
        return accion

    def _a_importar(self, nombre):
        """(contenido, nombre) del archivo; con «Más fotos», todas juntas en un PDF."""
        contenido = self._contenido()
        if not (self.es_foto and self.mas_fotos_ids):
            return contenido, nombre
        otras = self.mas_fotos_ids.sorted("id")  # en el orden en que se subieron
        # Solo fotos recién subidas por esta persona en esta ventana: por API se podría pasar el id
        # de cualquier adjunto (una factura, otro documento) y se leería y borraría
        ajenas = otras.filtered(lambda a: a.create_uid != self.env.user or a.res_id
                                or a.res_model not in (False, self._name))
        if ajenas:
            raise UserError(_("En «Más fotos» van solo fotos subidas acá."))
        otras.check_access("read")
        if not all((foto.name or "").lower().endswith(FOTOS) for foto in otras):
            raise UserError(_("En «Más fotos» van solo fotos (.jpg, .png): un PDF o un Excel se sube aparte."))
        pdf = fotos_a_pdf([(nombre, contenido)] + [(foto.name, foto.raw) for foto in otras])
        otras.unlink()  # ya están en el PDF, que queda como «Archivo original»; con los permisos de quien las subió
        return pdf, f"{os.path.splitext(nombre)[0]}.pdf"

    def _importar_en_parte_nueva(self, contenido, nombre):
        """Otro archivo del mismo proveedor con otros productos: parte nueva (columnas sugeridas
        solas). La lista que ya tenía, si no tenía nombre de parte, pasa a llamarse «General»."""
        parte = (self.nombre_parte or "").strip()
        if not parte:
            raise UserError(_("Poné un nombre a la parte nueva (p. ej. «Bulones»)."))
        listas = self._listas_de(self.partner_id)
        if any((li.parte or "").strip().lower() == parte.lower() for li in listas):
            raise UserError(_("%(p)s ya tiene una parte «%(n)s»: elegila en «Parte» en vez de crear otra.",
                              p=self.partner_id.name, n=parte))
        listas.filtered(lambda li: not li.parte).write({"parte": _("General")})
        lista = self.env["comercio.lista.proveedor"].create({
            "partner_id": self.partner_id.id, "parte": parte, "categoria_id": self.categoria_id.id,
            **self._ajustes()})
        return lista._importar_archivo(contenido, nombre, origen="manual").action_abrir()

    def action_importar(self):
        self.ensure_one()
        nombre = self.nombre_archivo or "lista.xlsx"
        if not nombre.lower().endswith(EXTENSIONES + DOCUMENTOS):
            raise UserError(_("El archivo tiene que ser Excel (.xlsx o .xls), CSV, PDF o una foto (.jpg, .png)."))
        if self.partner_id.ref_company_ids:
            raise UserError(_("%s es nuestra empresa, no un proveedor.", self.partner_id.name))
        if not self._listas_de(self.partner_id):
            otro = self._mismo_proveedor_con_otro_nombre(self.partner_id)
            if otro:
                raise UserError(_("Ya existe el proveedor «%(o)s»: elegí ese (así quedan juntas sus listas, "
                                  "precios y facturas), no «%(n)s».", o=otro.name, n=self.partner_id.name))
        if not self.partner_id.supplier_rank:
            self.partner_id.sudo().supplier_rank = 1
        if self.hoja_ids:
            return self._importar_hojas(nombre)
        contenido, nombre = self._a_importar(nombre)
        if self.nueva_parte:
            return self._importar_en_parte_nueva(contenido, nombre)
        if self.varias_listas and not self.lista_id:
            raise UserError(_("%s manda la lista en partes: elegí a cuál corresponde este archivo.",
                              self.partner_id.name))
        lista = self.lista_id or self.env["comercio.lista.proveedor"].create({"partner_id": self.partner_id.id})
        if self.categoria_id and lista.categoria_id != self.categoria_id:
            lista.categoria_id = self.categoria_id  # se recuerda para la próxima lista
        self._guardar_ajustes(lista)
        importacion = lista._importar_archivo(contenido, nombre, origen="manual")
        return importacion.action_abrir()


class ComercioImportarListaHoja(models.TransientModel):
    """Una hoja del Excel que se sube: si se importa y en qué parte de la lista del proveedor."""

    _name = "comercio.importar.lista.hoja"
    _description = "Hoja del archivo a importar"

    wizard_id = fields.Many2one("comercio.importar.lista.wizard", required=True, ondelete="cascade")
    importar = fields.Boolean("Importar")
    nombre = fields.Char("Hoja", readonly=True)
    filas = fields.Integer("Filas", readonly=True)
    lista_id = fields.Many2one("comercio.lista.proveedor", "Parte", readonly=True,
                               help="Vacío: se crea una parte nueva con el nombre de la hoja.")
    categoria_id = fields.Many2one("product.category", "Rubro por defecto")
