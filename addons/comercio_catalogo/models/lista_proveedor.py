import ipaddress
import json
import logging
import socket
from datetime import timedelta
from email.utils import getaddresses
from urllib.parse import urljoin

import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes
from urllib3.util import parse_url

from ..catalogo.convertir import (
    analizar_cuentas,
    descuento_detectado,
    encontrar_encabezado,
    filas_con_titulos,
    leer_tabla,
    sugerir_mapeo,
    sugerir_moneda,
    tabla_a_csv,
    titulos_de,
)
from ..catalogo.costo import (
    _pesos,
    cadena,
    cantidad_de_pack,
    costo_desde_lista,
    de_la_fila,
    normalizar_ajustes,
    regla_de_familia,
)
from ..catalogo.pdf import tabla_desde_pdf
from ..catalogo.plan import _numero

_logger = logging.getLogger(__name__)

EXTENSIONES = (".xlsx", ".xlsm", ".xls", ".csv")
# Solo subidos a mano: por correo o link, el PDF de una factura o el logo de una firma se
# leerían como lista.
DOCUMENTOS = (".pdf", ".jpg", ".jpeg", ".png", ".webp")
MAX_BYTES = 20 * 1024 * 1024  # una lista de precios no pesa más que esto
MAX_REDIRECCIONES = 3
# Solo laboratorio: permitir links a la red local (parámetro de sistema booleano)
PARAM_RED_LOCAL = "comercio_catalogo.permitir_red_local"
UNIDADES = [("u", "Unidad"), ("kg", "Kilo"), ("m", "Metro"), ("l", "Litro")]
# Columna de la planilla modelo ↔ campo del mapeo en la lista
COLUMNAS_MAPEO = {
    "codigo_proveedor": "col_codigo",
    "descripcion_proveedor": "col_descripcion",
    "codigo_barras": "col_barras",
    "costo": "col_costo",
    "cantidad_minima": "col_minimo",
    "costo_mayor": "col_costo_mayor",
    "cantidad_mayor": "col_cantidad_mayor",
    "unidad": "col_unidad",
    "descuento": "col_descuento",
    "iva": "col_iva",
    "precio_con_iva": "col_precio_con_iva",
    "promocion": "col_promocion",
    "bulto": "col_bulto",
    "stock": "col_stock",
}
MONEDAS = [("ars", "Pesos"), ("usd", "Dólares"),
           # LTX (02/11): cada fila dice la suya en el formato de la celda («$» = pesos; si no, dólares)
           ("mixta", "Pesos y dólares")]


class ComercioListaProveedor(models.Model):
    """Lista de precios de un proveedor: de dónde llega, cada cuánto y cómo se lee."""

    _name = "comercio.lista.proveedor"
    _description = "Lista de precios de un proveedor"
    _inherit = ["mail.thread", "mail.activity.mixin", "mail.alias.mixin.optional"]
    _order = "partner_id"

    name = fields.Char("Nombre", compute="_compute_name", store=True)
    partner_id = fields.Many2one("res.partner", "Proveedor", required=True, tracking=True)
    parte = fields.Char(
        "Parte", tracking=True,
        help="Solo si el proveedor manda la lista en varias partes (p. ej. una hoja «Bulones»): "
        "una lista por parte. Las bajas de una parte no tocan los precios de la otra.")
    active = fields.Boolean(default=True)
    responsable_id = fields.Many2one(
        "res.users", "Responsable", default=lambda self: self.env.user,
        help="Recibe los avisos: lista para revisar, lista que hay que subir o error al leerla.",
    )

    # De dónde llega
    origen = fields.Selection(
        [("manual", "Se sube a mano"), ("url", "Link de descarga fijo"), ("correo", "Llega por correo")],
        default="manual", required=True, tracking=True,
    )
    url = fields.Char("Link de descarga", help="Dirección fija del Excel o CSV (sin usuario y contraseña).")
    remitentes = fields.Char(
        "Correos del proveedor",
        help="Direcciones que pueden mandar la lista (separadas por coma). Si llega de otra "
        "dirección, se simula pero no se aplica nada solo.",
    )
    frecuencia_dias = fields.Integer(
        "Actualizar cada (días)", default=15,
        help="0 = sin actualización automática ni recordatorios.",
    )
    proxima_actualizacion = fields.Date("Próxima actualización", tracking=True)

    # Cómo se lee el archivo
    hoja = fields.Char("Hoja", help="Nombre o número (0 = la primera). Vacío: la primera.")
    fila_encabezado = fields.Integer("Fila de títulos", help="0 = detectarla sola.")
    col_codigo = fields.Char("Columna «código del proveedor»")
    col_descripcion = fields.Char(
        "Columna «descripción»",
        help="Si la lista parte la descripción en dos columnas, se pueden juntar con « + », "
        "p. ej. «Detalle + Descripción del producto».")
    col_barras = fields.Char("Columna «código de barras»")
    col_costo = fields.Char("Columna «costo»")
    col_minimo = fields.Char("Columna «cantidad mínima»")
    col_costo_mayor = fields.Char(
        "Columna «precio por mayor»",
        help="Si el proveedor da dos precios: el de esta columna vale comprando desde la cantidad de "
             "«Columna cantidad por mayor» (o «Por mayor desde» si el archivo no la trae).")
    col_cantidad_mayor = fields.Char("Columna «cantidad por mayor»")
    cantidad_mayor_fija = fields.Float("Por mayor desde (si el archivo no lo trae)")
    col_unidad = fields.Char("Columna «unidad»")
    col_descuento = fields.Char(
        "Columna «descuento»",
        help="Solo si el proveedor trae su descuento por fila. Nunca se elige sola: si la columna es una "
             "cuenta del comercio (precio final, con IVA, etc.), dejarla vacía.")
    col_iva = fields.Char(
        "Columna «IVA»",
        help="La alícuota de cada fila (10,5 / 21 / 27), si la lista la trae (FC: «Precio con I.V.A», que es "
             "el %). Los productos nuevos que se agregan desde la lista toman ese IVA (venta y compra); en los "
             "que ya tenemos manda el del producto y, si no coincide, la fila avisa. Con «La lista trae el IVA "
             "incluido», sirve también para sacarlo del precio.")
    col_precio_con_iva = fields.Char(
        "Columna «precio con IVA»",
        help="Una columna que el comercio agregó con el precio con el IVA de cada producto (Gas del Sur: «NETO»). "
             "Nunca es el costo: sirve para saber el IVA de cada fila (10,5 o 21) si la lista no lo dice. Se "
             "detecta sola cuando la columna es la del costo × un descuento × el IVA.")
    cuentas_detectadas = fields.Text(
        "Cuentas encontradas en la planilla", readonly=True,
        help="Lo que se encontró al leer el primer archivo: columnas que son cuentas de otras (se ignoran) "
             "y el descuento que la planilla le aplica a la lista. Confirmarlo con el negocio.")
    col_bulto = fields.Char(
        "Columna «unidades por bulto»",
        help="Si el proveedor vende de a bultos enteros (UxB, unidades por caja): la orden de compra avisa si "
             "se pide una cantidad que no es un bulto entero (101 de a 100). No es la compra mínima.")
    col_stock = fields.Char(
        "Columna «stock»",
        help="Si la lista dice qué tiene el proveedor: las filas sin stock («NO», «Agotado», 0) no se cargan. "
             "Lo nuestro que deja de tener stock sale como «ya no está en la lista».")
    col_promocion = fields.Char(
        "Columna «promociones»",
        help="Promociones del proveedor escritas en texto (FC: «Descuentos y Promociones Vigentes»): «5% DTO. "
             "X UNIDAD» baja el costo; «10% DTO. X 2 ROLLOS» es el precio por mayor desde esa cantidad. Cuando "
             "la promoción se termina, la fila avisa que el costo sube por eso.")
    unidad_fija = fields.Selection(UNIDADES, "Unidad si el archivo no la trae", default="u")
    envase_en_descripcion = fields.Boolean(
        "El precio es por el envase que dice la descripción",
        help="Para listas como Mu: «ABRAZADERA 12MM 100u» a $ 54.324 es la caja de 100. Se guarda el "
             "precio por unidad ($ 543) con compra mínima 100. Solo si el archivo no trae columna de unidad.")
    familia_en_descripcion = fields.Boolean(
        "Sumar la familia a la descripción",
        help="Para listas que ponen el nombre de la familia en una fila aparte («CANDADO BRONCE») y "
             "debajo solo la medida («40 mm»): la descripción queda «CANDADO BRONCE 40 mm». Las filas de "
             "familia nunca se leen como productos, esté o no marcado.")
    # Del precio de la lista al costo (23/10; 30/10: precio guardado, reglas y dólar del día).
    # Los valores de cada proveedor los confirma el negocio (pendiente P-056). Ver catalogo/costo.py.
    aviso_moneda = fields.Char("Aviso de moneda", readonly=True,
                               help="El último archivo parece de otra moneda que la elegida (no se cambia sola).")
    moneda = fields.Selection(MONEDAS, "Moneda de la lista", default="ars", required=True, tracking=True)
    cotizacion = fields.Float(
        "Cotización fija", tracking=True,
        help="Solo si se quiere usar un dólar fijo (p. ej. el que da el proveedor). Vacío (0) = el dólar "
             "del día del Banco Nación (lo publica ARCA y Odoo lo actualiza solo cada mañana).")
    cotizacion_del_dia = fields.Float("Dólar del día", compute="_compute_cotizacion_del_dia", digits=(16, 2))
    cotizacion_fecha = fields.Date("Del", compute="_compute_cotizacion_del_dia")
    descuentos = fields.Char(
        "Descuentos del proveedor (%)", tracking=True,
        help="Bonificaciones para toda la lista que la lista no descuenta, en cadena: «30+10+10» = 30 %, "
             "después 10 % y después 10 %. Vacío si la columna elegida ya es el precio neto. Los de una "
             "familia o un producto van abajo y se suman a estos.")
    descuentos_neto = fields.Char(
        "Descuentos que valen también sobre los netos de oferta (%)", tracking=True,
        help="Cuando la columna de promociones trae un precio neto («NETO $ 6900»), ese precio ya tiene "
             "los descuentos comerciales: solo se le aplican estos (Omega: «10», el 10 % por pago). "
             "Vacío: el neto es el costo.")
    recargo = fields.Float("Recargo (%)", tracking=True, help="P. ej. el flete que suma la factura (2,5).")
    descuento_pack = fields.Float(
        "Descuento por pack completo (%)", tracking=True,
        help="Si la descripción dice «(pack x 12)», comprando el pack entero (Nortex: 5 %). Queda como "
             "precio por mayor desde esa cantidad: el costo por unidad no cambia y Compras lo usa al pedir "
             "el pack.")
    trae_iva = fields.Boolean(
        "La lista trae el IVA incluido", tracking=True,
        help="Se saca, porque el costo va sin IVA. La alícuota de cada producto: la columna «IVA» si se "
             "eligió; si no, el IVA de compra del producto (si ya lo tenemos); si no, el de abajo.")
    iva_por_defecto = fields.Float("IVA si no se sabe (%)", default=21.0, tracking=True)
    regla_ids = fields.One2many("comercio.lista.regla", "lista_id", "Descuentos extra")
    familia_ids = fields.One2many("comercio.lista.familia", "lista_id", "Familias de la lista")
    importacion_vigente_id = fields.Many2one("comercio.lista.importacion", compute="_compute_importacion_vigente")
    regla_familia_ids = fields.One2many(
        "comercio.lista.regla", "lista_id", "Descuentos por familia", domain=[("tipo", "=", "familia")],
        context={"default_tipo": "familia"})
    regla_producto_ids = fields.One2many(
        "comercio.lista.regla", "lista_id", "Descuentos por producto", domain=[("tipo", "=", "producto")],
        context={"default_tipo": "producto"})
    ejemplo_calculo = fields.Text("Ejemplo", compute="_compute_ejemplo_calculo")
    categoria_id = fields.Many2one(
        "product.category", "Rubro por defecto",
        help="Categoría que traen marcada los productos de la lista que todavía no tenemos.")
    plazo_dias = fields.Integer("Plazo de entrega (días)")

    # Qué se aplica solo. Desde el 19/11 no está en pantalla: a mano se usa «Aplicar todo» (un
    # botón). El tope queda solo para las listas que se bajan solas de un link o llegan por correo,
    # que se aplican sin que nadie las mire.
    tope_automatico = fields.Float(
        "Aplicar solos los cambios de costo de hasta (%)", default=10.0,
        help="Las variaciones mayores, los productos nuevos, las bajas y lo dudoso esperan confirmación.",
    )
    lista_completa = fields.Boolean(
        "El archivo es la lista completa", default=True,
        help="Si un producto ya no aparece, se deja de comprarle a este proveedor (se cierra su precio).",
    )

    importacion_ids = fields.One2many("comercio.lista.importacion", "lista_id", "Importaciones")
    ultima_importacion_id = fields.Many2one(
        "comercio.lista.importacion", compute="_compute_ultima", string="Última importación"
    )
    pendientes_revision = fields.Integer(compute="_compute_ultima", string="Para revisar")
    cant_productos = fields.Integer(compute="_compute_cant_productos", string="Productos")

    def _dominio_vigentes(self):
        hoy = fields.Date.context_today(self)
        return [("partner_id", "=", self.partner_id.id), ("comercio_escala_de_id", "=", False),
                "|", ("date_end", "=", False), ("date_end", ">=", hoy)]

    def _compute_cant_productos(self):
        Info = self.env["product.supplierinfo"]
        for lista in self:
            lista.cant_productos = Info.search_count(lista._dominio_vigentes()) if lista.partner_id else 0

    def action_ver_productos(self):
        """Lo que vende este proveedor (P-048): las filas de su última lista, filtradas en lo que
        está en nuestro catálogo. Sin el filtro se ve su catálogo entero y se agregan productos.
        Sin ninguna lista importada: sus precios vigentes (cargados a mano)."""
        self.ensure_one()
        vigente = self.env["comercio.lista.importacion"]._vigente_de(self)
        if vigente:
            accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_catalogo.action_importacion_lineas")
            accion.update({
                "name": _("Productos de %s", self.name),
                "domain": [("importacion_id", "=", vigente.id)],
                "context": {"search_default_registrado": 1},
            })
            return accion
        return {
            "type": "ir.actions.act_window",
            "name": _("Productos de %s", self.partner_id.name),
            "res_model": "product.supplierinfo",
            "view_mode": "list,form",
            "views": [(self.env.ref("comercio_catalogo.historial_costos_list").id, "list"), (False, "form")],
            "domain": self._dominio_vigentes(),
            "context": {"default_partner_id": self.partner_id.id},
        }


    @api.model_create_multi
    def create(self, vals_list):
        hoy = fields.Date.context_today(self)
        for vals in vals_list:
            if not vals.get("proxima_actualizacion") and vals.get("frecuencia_dias", 15):
                vals["proxima_actualizacion"] = hoy + timedelta(days=vals.get("frecuencia_dias", 15))
        return super().create(vals_list)

    @api.constrains("url")
    def _check_url(self):
        for lista in self.filtered("url"):
            lista._validar_url(lista.url)

    @api.depends("partner_id.name", "parte")
    def _compute_name(self):
        for lista in self:
            lista.name = _("Lista de %s", lista.partner_id.name or "?")
            if lista.parte:
                lista.name += f" ({lista.parte})"

    @api.depends("importacion_ids.estado", "importacion_ids.cant_revisar")
    def _compute_ultima(self):
        for lista in self:
            ultima = lista.importacion_ids.sorted("id", reverse=True)[:1]
            lista.ultima_importacion_id = ultima
            lista.pendientes_revision = ultima.cant_revisar if ultima else 0

    # ------------------------------------------------------------------ alias de correo
    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values["alias_model_id"] = self.env["ir.model"]._get_id(self._name)
        if self.id:
            values["alias_force_thread_id"] = self.id
        return values

    def message_update(self, msg_dict, update_vals=None):
        """Lista que llega por correo: cada adjunto Excel/CSV se importa."""
        res = super().message_update(msg_dict, update_vals=update_vals)
        remitente = (msg_dict.get("email_from") or "").lower()
        for adjunto in msg_dict.get("attachments") or []:
            nombre, contenido = adjunto[0], adjunto[1]
            if not nombre.lower().endswith(EXTENSIONES):
                continue
            if isinstance(contenido, str):
                contenido = contenido.encode()
            confiable = self._remitente_confiable(remitente)
            self._importar_archivo(contenido, nombre, origen="correo", aplicar_seguros=confiable)
        return res

    def _remitente_confiable(self, remitente):
        """Dirección exacta (no «contiene»). El «De:» de un correo se puede falsificar: por eso
        lo que llega así solo aplica solo los cambios chicos (tope) y el resto se revisa."""
        permitidos = {r.strip().lower() for r in (self.remitentes or "").split(",") if r.strip()}
        direcciones = {d.strip().lower() for _n, d in getaddresses([remitente or ""]) if d}
        return bool(permitidos) and len(direcciones) == 1 and direcciones <= permitidos

    # ------------------------------------------------------------------ mapeo
    def mapeo(self, sugerido=None):
        """Mapeo en el formato del motor (catalogo.convertir). `sugerido`: columnas propuestas
        que todavía no se guardaron."""
        self.ensure_one()
        sugerido = sugerido or {}
        elegidas = {col: sugerido[campo] if campo in sugerido else self[campo]
                    for col, campo in COLUMNAS_MAPEO.items()}
        columnas = {col: titulo for col, titulo in elegidas.items() if titulo}
        fijos = {"unidad": self.unidad_fija if "unidad" not in columnas else "",
                 "categoria": self.categoria_id.complete_name or "",
                 "plazo_dias": self.plazo_dias or "",
                 "cantidad_mayor": (self.cantidad_mayor_fija or "") if "cantidad_mayor" not in columnas else ""}
        familias, productos = self.regla_ids.para_el_motor()
        moneda = sugerido.get("moneda") or self.moneda  # la detectada en el primer archivo (06/11)
        ajustes = {"moneda": moneda, "cotizacion": self._cotizacion() if moneda != "ars" else 0,
                   "descuentos": sugerido.get("descuentos", self.descuentos) or "",
                   "descuentos_neto": self.descuentos_neto or "", "recargo": self.recargo,
                   "pack": self.descuento_pack, "trae_iva": self.trae_iva, "iva": self.iva_por_defecto,
                   "iva_por_codigo": self._iva_por_codigo() if self.trae_iva else {},
                   "reglas": familias, "excepciones": productos}
        return {"proveedor": self.partner_id.name, "parte": self.parte or "", "columnas": columnas,
                "valores_fijos": fijos,
                "familia_en_descripcion": self.familia_en_descripcion,
                "envase_en_descripcion": self.envase_en_descripcion, "ajustes": ajustes}

    def _compute_importacion_vigente(self):
        Importacion = self.env["comercio.lista.importacion"]
        for lista in self:
            lista.importacion_vigente_id = Importacion._vigente_de(lista) if lista.id else False

    def _actualizar_familias(self):
        """Rehace las familias con las de la última lista (para elegirlas en «Descuentos por familia»)."""
        Familia = self.env["comercio.lista.familia"].sudo()
        for lista in self:
            vigente = lista.importacion_vigente_id
            cuantas = {}
            for linea in vigente.linea_ids if vigente else []:
                familia = linea.familia
                if familia:
                    cuantas[familia] = cuantas.get(familia, 0) + 1
            existentes = {f.name: f for f in Familia.search([("lista_id", "=", lista.id)])}
            for nombre, filas in cuantas.items():
                if nombre in existentes:
                    if existentes[nombre].filas != filas:
                        existentes[nombre].filas = filas
                else:
                    Familia.create({"lista_id": lista.id, "name": nombre, "filas": filas})
            sobran = [f.id for n, f in existentes.items() if n not in cuantas]
            Familia.browse(sobran).unlink()

    @api.constrains("descuentos", "descuentos_neto")
    def _check_descuentos(self):
        for lista in self.filtered(lambda li: li.descuentos or li.descuentos_neto):
            try:
                cadena(lista.descuentos or "")
                cadena(lista.descuentos_neto or "")
            except ValueError as error:
                raise UserError(_("Descuentos: escribilos como «30+10+10» (porcentajes separados por +).")) \
                    from error

    # ------------------------------------------------------------------ del precio al costo
    def _dolar(self):
        """(pesos por dólar, fecha) de la última cotización cargada en Odoo; (0, None) si no hay."""
        usd = self.env.ref("base.USD")
        empresa = self.env.company
        hoy = fields.Date.context_today(self)
        tasa = self.env["res.currency.rate"].sudo().search(
            [("currency_id", "=", usd.id), ("name", "<=", hoy),
             "|", ("company_id", "=", False), ("company_id", "=", empresa.id)], order="name desc", limit=1)
        if not tasa:
            return 0.0, None
        return usd._convert(1.0, empresa.currency_id, empresa, hoy, round=False), tasa.name

    def _compute_cotizacion_del_dia(self):
        valor, fecha = self._dolar() if self else (0.0, None)
        for lista in self:
            lista.cotizacion_del_dia, lista.cotizacion_fecha = valor, fecha

    def _cotizacion(self):
        """La cotización que se usa: la fija si hay; si no, la del día. Error claro si no hay ninguna."""
        self.ensure_one()
        if self.cotizacion:
            return self.cotizacion
        valor, _fecha = self._dolar()
        if not valor:
            raise UserError(_(
                "La lista de %s está en dólares y Odoo no tiene la cotización del dólar. Activá la "
                "actualización automática (Contabilidad → Ajustes → Monedas, «[AR] ARCA») o cargá una "
                "«Cotización fija» en la lista.", self.partner_id.name))
        return valor

    def _iva_por_codigo(self):
        """{código del proveedor: alícuota del IVA de compra} de los productos que ya tenemos de
        este proveedor (para sacar el IVA incluido con la alícuota de cada uno)."""
        self.ensure_one()
        salida = {}
        for info in self.env["product.supplierinfo"].sudo().search(self._dominio_vigentes()):
            impuestos = info.product_tmpl_id.supplier_taxes_id.filtered(
                lambda t: t.amount_type == "percent" and t.amount > 0)
            if info.product_code and impuestos:
                salida[info.product_code.strip()] = impuestos[0].amount
        return salida

    @api.depends("descuentos", "recargo", "descuento_pack", "moneda", "cotizacion", "trae_iva",
                 "iva_por_defecto",
                 "regla_ids.descuentos", "regla_ids.contiene", "regla_ids.codigo")
    def _compute_ejemplo_calculo(self):
        """Cómo queda el costo de unas filas de la última lista (una por regla, si hay), con los
        valores de la pantalla. No cambia nada: para ver el efecto antes de «Recalcular costos»."""
        Linea = self.env["comercio.lista.importacion.linea"].sudo()
        for lista in self:
            lista.ejemplo_calculo = False
            vigente = lista.id and self.env["comercio.lista.importacion"]._vigente_de(lista)
            if not vigente:
                continue
            try:
                ajustes = normalizar_ajustes(lista.mapeo()["ajustes"])
            except (UserError, ValueError) as error:
                lista.ejemplo_calculo = str(error)
                continue
            filas = Linea.search([("importacion_id", "=", vigente.id), ("datos", "!=", False),
                                  ("sin_costo", "=", False)], limit=300, order="fila")
            elegidas, vistas = [], set()
            for linea in filas:
                datos = json.loads(linea.datos)
                texto = datos.get("descripcion_proveedor") or ""
                codigo = datos.get("codigo_proveedor") or ""
                regla = regla_de_familia(ajustes["reglas"], texto, codigo)
                clave = ("p", codigo) if codigo in ajustes["excepciones"] else ("r", regla and regla["contiene"])
                if clave not in vistas:
                    vistas.add(clave)
                    elegidas.append(datos)
                if len(elegidas) >= 4:
                    break
            renglones = []
            for datos in elegidas:
                precio = datos.get("precio_lista") or datos.get("costo")
                try:
                    costo, cuenta = costo_desde_lista(
                        _numero(precio), de_la_fila(ajustes, datos.get("moneda_fila")), datos.get("descuento_fila", ""), datos.get("iva_fila", ""),
                        datos.get("descripcion_proveedor") or "", datos.get("codigo_proveedor") or "",
                        datos.get("promocion", ""))
                except ValueError:
                    continue
                pack = cantidad_de_pack(datos.get("descripcion_proveedor")) if ajustes["pack"] else 0
                if pack:
                    mayor = costo * (1 - ajustes["pack"] / 100)
                    cuenta += (f" · por mayor desde {pack:g}: −{ajustes['pack']:g} % (pack completo)"
                               f" → $ {_pesos(mayor)}")
                renglones.append(f"{datos.get('codigo_proveedor') or '-'} {datos.get('descripcion_proveedor') or ''}"
                                 f"\n    {cuenta}")
            lista.ejemplo_calculo = "\n".join(renglones) or False

    def action_recalcular(self):
        """«Recalcular costos»: vuelve a leer la última lista con los descuentos, el IVA y el dólar
        de ahora. Si todavía no se aplicó nada, se simula de nuevo; si no, entra como una
        importación nueva del mismo archivo (simular → revisar → aplicar, con historial)."""
        self.ensure_one()
        vigente = self.env["comercio.lista.importacion"]._vigente_de(self)
        if not vigente or not vigente.archivo:
            raise UserError(_("Esta lista todavía no tiene ningún archivo importado."))
        if not vigente.cant_aplicadas and vigente.estado in ("borrador", "simulada"):
            vigente.action_simular()
            nueva = vigente
        else:
            nueva = self._importar_archivo(vigente.archivo.content, vigente.nombre_archivo, origen="recalculo")
        return nueva.action_abrir()

    @api.model
    def _cron_recalcular_dolar(self):
        """Todos los días, después de la cotización nueva: trae la del día (ARCA) si falta y
        recalcula las listas en dólares que se calcularon con otro dólar."""
        self._recalcular_dolar(traer=True, en_tarea=True)

    @api.model
    def _recalcular_dolar(self, traer=False, en_tarea=False):
        """Las listas en dólares (sin cotización fija) cuya última importación se calculó con
        otro dólar (más de 0,5 %) se vuelven a calcular. Los cambios dentro del tope de cada
        lista se aplican solos; el resto espera revisión. Devuelve cuántas se recalcularon.
        `traer`: antes, la cotización del día de ARCA si todavía no hay (sin certificado falla
        sin ruido y queda la última, p. ej. la cargada a mano en «Dólar»)."""
        listas = self.search([("moneda", "in", ["usd", "mixta"]), ("cotizacion", "=", 0)])
        if not listas:
            return 0
        empresa = self.env.company
        _valor, fecha = self._dolar()
        if traer and fecha != fields.Date.context_today(self) and hasattr(empresa, "update_currency_rates"):
            # La cotización del día, aunque la tarea de Odoo no tenga fecha programada
            # (currency_rate_live solo corre si «próxima ejecución» está cargada)
            try:
                empresa.with_context(suppress_errors=True).update_currency_rates()
            except Exception:  # noqa: BLE001 - sin ARCA se sigue con la última cotización
                _logger.exception("No se pudo traer la cotización del dólar")
        valor, _fecha = self._dolar()
        if not valor:
            return 0
        Imp = self.env["comercio.lista.importacion"]
        hechas = 0
        for lista in listas:
            vigente = Imp._vigente_de(lista)
            if (not vigente or not vigente.archivo or vigente.estado != "aplicada" or not vigente.cotizacion_usada
                    or abs(valor / vigente.cotizacion_usada - 1) < 0.005):
                continue
            try:
                lista._importar_archivo(vigente.archivo.content, vigente.nombre_archivo, origen="recalculo",
                                        aplicar_seguros=True)
                hechas += 1
            except Exception as error:  # noqa: BLE001 - una lista rota no frena a las demás
                if not en_tarea:
                    raise
                _logger.exception("Error al recalcular %s", lista.name)
                lista._recordar(_("No se pudo recalcular con el dólar del día la lista de %(p)s: %(e)s",
                                  p=lista.partner_id.name, e=error))
            if en_tarea:
                self.env.cr.commit()  # cada lista queda guardada aunque falle la siguiente
        return hechas

    def sugerencia_mapeo(self, contenido, nombre_archivo):
        """Títulos del archivo y, si la lista todavía no tiene columnas, las que se proponen.
        No guarda nada: se guarda recién si el archivo se lee bien."""
        self.ensure_one()
        tabla = leer_tabla(contenido, nombre_archivo, self.hoja or None, monedas=self.moneda == "mixta")
        fila = self.fila_encabezado or encontrar_encabezado(tabla)
        titulos = [t for t in titulos_de(tabla, fila) if t]
        vals = {}
        if not self.fila_encabezado:
            vals["fila_encabezado"] = fila
        primera_vez = not (self.col_codigo or self.col_descripcion or self.col_costo)
        if primera_vez:
            filas = filas_con_titulos(tabla, fila) if titulos else []
            for col, titulo in sugerir_mapeo(titulos, filas).items():
                vals[COLUMNAS_MAPEO[col]] = titulo
            vals.update(self._cuentas_de_la_planilla(titulos, filas, vals.get("col_costo")))
        elif not self.col_barras and titulos:
            # 20/11: la primera lista no traía códigos de barras (columna vacía o ausente) y esta sí:
            # se reconoce la columna, así el código de fábrica llega a los productos que ya tenemos
            col = sugerir_mapeo(titulos, filas_con_titulos(tabla, fila)).get("codigo_barras")
            if col:
                vals["col_barras"] = col
        vals.update(self._moneda_sugerida(contenido, nombre_archivo, fila, vals.get("col_costo") or self.col_costo,
                                          primera_vez))
        return titulos, vals

    def _moneda_sugerida(self, contenido, nombre_archivo, fila, col_costo, primera_vez):
        """Moneda de la lista (06/11): en una lista nueva se pone sola; en una que ya tiene, nunca
        se cambia sola: si el archivo parece de otra moneda, queda el aviso en la ficha."""
        try:
            con_formato = leer_tabla(contenido, nombre_archivo, self.hoja or None, monedas=True)
        except Exception:  # noqa: BLE001 - la sugerencia nunca frena la importación
            return {}
        sugerida = sugerir_moneda(con_formato, fila, col_costo)
        nombres = dict(MONEDAS)
        if not sugerida or sugerida == self.moneda:
            return {"aviso_moneda": False}
        if primera_vez:
            return {"moneda": sugerida, "aviso_moneda": False}
        return {"aviso_moneda": _("El último archivo parece estar en %(s)s y la lista está en %(m)s: si es así, "
                                  "cambiá «Moneda de la lista».", s=nombres[sugerida], m=nombres[self.moneda])}

    def _cuentas_de_la_planilla(self, titulos, filas, costo):
        """Columnas que son cuentas del comercio y el descuento que la planilla le aplica a la
        lista (Gas del Sur: «C/ Dto.» = LISTA − 25 %). El descuento se propone en «Descuentos» si la
        lista no tiene; queda escrito para que el negocio lo confirme (30/10)."""
        analisis = analizar_cuentas(titulos, filas)
        lineas = []
        for titulo, (base, factor) in analisis["derivadas"].items():
            cuenta = f"− {(1 - factor) * 100:g} %" if factor < 1 else f"× {factor:g}".replace(".", ",")
            lineas.append(_("«%(t)s» = «%(b)s» %(c)s (cuenta de la planilla: no se usa)",
                            t=" ".join(titulo.split()), b=" ".join(base.split()), c=cuenta))
        if analisis["con_iva"]:
            con_iva, base, factor = analisis["con_iva"]
            lineas.append(_("«%(t)s» = «%(b)s»%(d)s + el IVA de cada producto (10,5 o 21): se usa solo para "
                            "saber el IVA", t=" ".join(con_iva.split()), b=" ".join(base.split()),
                            d=f" − {(1 - factor) * 100:g} %" if factor < 0.9999 else ""))
        vals = {}
        descuento = descuento_detectado(analisis, costo)
        if descuento and not self.descuentos:
            vals["descuentos"] = f"{descuento:g}"
            lineas.append(_("Se puso %s %% en «Descuentos del proveedor»: detectado en la planilla, CONFIRMAR "
                            "con el negocio (puede ser un descuento del proveedor o una cuenta del comercio).",
                            f"{descuento:g}"))
        if lineas:
            vals["cuentas_detectadas"] = "\n".join(lineas)
        return vals

    # ------------------------------------------------------------------ importar
    def _tabla_de_documento(self, contenido, nombre_archivo):
        """(tabla, leída con IA, nota) de un PDF o una foto. Sin IA, solo un PDF con texto
        (comercio_catalogo_ia suma las fotos y los PDF escaneados)."""
        if nombre_archivo.lower().endswith(".pdf"):
            tabla = tabla_desde_pdf(contenido)
            if tabla:
                return tabla, False, _("Lista leída del texto del PDF (sin IA).")
        raise UserError(_(
            "«%s» es una foto o un PDF escaneado (sin texto): para leerlo hace falta la ayuda de la IA, "
            "que no está configurada. Pedile al proveedor el Excel o el PDF original.", nombre_archivo))

    def _importar_archivo(self, contenido, nombre_archivo, origen="manual", aplicar_seguros=False):
        self.ensure_one()
        extra, nota = {}, False
        if nombre_archivo.lower().endswith(DOCUMENTOS):
            # PDF o foto → tabla → CSV: se simula (y se vuelve a simular) como un Excel; el
            # original queda guardado para comparar.
            tabla, con_ia, nota = self._tabla_de_documento(contenido, nombre_archivo)
            extra = {"archivo_original": BinaryBytes(contenido, filename=nombre_archivo),
                     "nombre_original": nombre_archivo, "leida_con_ia": con_ia}
            contenido, nombre_archivo = tabla_a_csv(tabla), f"{nombre_archivo}.csv"
        importacion = self.env["comercio.lista.importacion"].sudo().create({
            "lista_id": self.id,
            "archivo": BinaryBytes(contenido, filename=nombre_archivo),
            "nombre_archivo": nombre_archivo,
            "origen": origen,
            **extra,
        })
        if nota:
            importacion.message_post(body=nota)
        if self.frecuencia_dias:
            hoy = fields.Date.context_today(self)
            self.proxima_actualizacion = hoy + timedelta(days=self.frecuencia_dias)
        importacion = importacion.sudo(False)
        importacion.action_simular()
        if aplicar_seguros and importacion.estado == "simulada":
            importacion.action_aplicar_automaticos()
        importacion._avisar_si_hay_pendientes()
        return importacion

    def action_importar(self):
        """Abre el asistente para subir el archivo."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "comercio.importar.lista.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lista_id": self.id},
        }

    def action_abrir_importar(self):
        """Botón «Importar lista» de la pantalla de proveedores (con o sin filas seleccionadas)."""
        return self.env["ir.actions.act_window"]._for_xml_id("comercio_catalogo.action_importar_lista_wizard")

    def action_descargar_ahora(self):
        self.ensure_one()
        if not self.url:
            raise UserError(_("Falta el link de descarga."))
        importacion = self._descargar_e_importar(aplicar_seguros=False)
        return importacion.action_abrir()

    def _red_local_permitida(self):
        return self.env["ir.config_parameter"].sudo().get_bool(PARAM_RED_LOCAL)

    def _ip_publica(self, direccion):
        ip = ipaddress.ip_address(str(direccion).split("%")[0])
        if not ip.is_global and not self._red_local_permitida():
            raise UserError(_("El link apunta a una dirección interna (%s): no se permite.", ip))

    def _validar_url(self, url):
        """Solo http/https a direcciones públicas: el link no puede apuntar a la red del local
        (router, servidor, impresoras) ni a la nube interna (SSRF).

        Se lee con el mismo analizador que usa la descarga (urllib3) y se rechazan los links
        con usuario, barras invertidas o espacios, que distintos analizadores leen distinto.
        """
        if any(c in url for c in "@\\") or any(c.isspace() or ord(c) < 32 for c in url):
            raise UserError(_("El link tiene caracteres no permitidos (@, \\ o espacios)."))
        partes = parse_url(url)
        if partes.scheme not in ("http", "https") or not partes.host:
            raise UserError(_("El link tiene que empezar con https:// (o http://)."))
        try:
            direcciones = {info[4][0] for info in socket.getaddrinfo(partes.host, partes.port or None)}
        except socket.gaierror as error:
            raise UserError(_("No se encuentra el sitio del link: %s", partes.host)) from error
        for direccion in direcciones:
            self._ip_publica(direccion)

    def _verificar_conexion(self, respuesta):
        """La dirección a la que realmente se conectó (por si el DNS cambió después de validar)."""
        conexion = getattr(respuesta.raw, "connection", None)
        sock = getattr(conexion, "sock", None)
        if sock is None:  # el servidor cierra la conexión al responder: el socket queda en el flujo
            try:
                sock = respuesta.raw._fp.fp.raw._sock
            except AttributeError:
                sock = None
        if sock is None:
            if self._red_local_permitida():
                return
            raise UserError(_("No se pudo verificar a qué dirección se conectó el link."))
        self._ip_publica(sock.getpeername()[0])

    def _descargar(self, url):
        for _salto in range(MAX_REDIRECCIONES + 1):
            self._validar_url(url)
            respuesta = requests.get(url, timeout=60, allow_redirects=False, stream=True)
            try:
                self._verificar_conexion(respuesta)
            except UserError:
                respuesta.close()
                raise
            if respuesta.is_redirect:
                url = urljoin(url, respuesta.headers.get("location", ""))
                continue
            respuesta.raise_for_status()
            contenido = b""
            for parte in respuesta.iter_content(64 * 1024):
                contenido += parte
                if len(contenido) > MAX_BYTES:
                    raise UserError(_("El archivo del link es demasiado grande."))
            return respuesta, contenido
        raise UserError(_("El link redirige demasiadas veces."))

    def _descargar_e_importar(self, aplicar_seguros):
        respuesta, contenido = self._descargar(self.url)
        nombre = self.url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or "lista.xlsx"
        if not nombre.lower().endswith(EXTENSIONES):
            tipo = respuesta.headers.get("content-type", "")
            if "csv" in tipo or "text" in tipo:
                nombre += ".csv"
            elif "ms-excel" in tipo:  # application/vnd.ms-excel: Excel 97-2003
                nombre += ".xls"
            else:
                nombre += ".xlsx"
        return self._importar_archivo(contenido, nombre, origen="url", aplicar_seguros=aplicar_seguros)

    def action_ver_importaciones(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Importaciones"),
            "res_model": "comercio.lista.importacion",
            "view_mode": "list,form",
            "domain": [("lista_id", "=", self.id)],
            "context": {"default_lista_id": self.id},
        }

    # ------------------------------------------------------------------ automático
    @api.model
    def _cron_actualizar_listas(self):
        """Todos los días: listas con link se bajan e importan. Que una lista está atrasada no
        se avisa en Odoo (19/11: eran decenas de actividades por día): lo avisa Grafana por
        Discord, un aviso diario con el total. En Odoo solo queda el error de una descarga."""
        hoy = fields.Date.context_today(self)
        vencidas = self.search([
            ("frecuencia_dias", ">", 0),
            "|", ("proxima_actualizacion", "=", False), ("proxima_actualizacion", "<=", hoy),
        ])
        for lista in vencidas:
            try:
                if lista.origen == "url" and lista.url:
                    lista._descargar_e_importar(aplicar_seguros=True)
            except Exception as error:  # noqa: BLE001 - una lista rota no frena a las demás
                _logger.exception("Error al actualizar %s", lista.name)
                lista._recordar(_("No se pudo actualizar la lista de %(p)s: %(e)s",
                                  p=lista.partner_id.name, e=error))
            lista.proxima_actualizacion = hoy + timedelta(days=lista.frecuencia_dias)
            self.env.cr.commit()  # cada lista queda guardada aunque falle la siguiente

    def _recordar(self, texto):
        """Actividad para el responsable; no se repite si ya tiene una igual sin hacer.
        Sin mail «Te asignaron…» (mail_activity_quick_update): con decenas de listas atrasadas
        eran decenas de mails por día y agotaban el cupo de Resend (19/11). Se ve en el reloj de
        actividades de Odoo y en el aviso diario de Grafana por Discord."""
        self.ensure_one()
        if self.activity_ids.filtered(lambda act: act.summary == texto[:80]):
            return
        self.with_context(mail_activity_quick_update=True).activity_schedule(
            "mail.mail_activity_data_todo", summary=texto[:80], note=texto,
            user_id=(self.responsable_id or self.env.user).id,
        )
