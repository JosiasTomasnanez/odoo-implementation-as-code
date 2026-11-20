import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command, Domain
from odoo.tools.misc import formatLang

from ..catalogo import plan as motor
from ..catalogo.busqueda import clave_producto, normalizar, terminos
from ..catalogo.costo import costo_desde_lista, de_la_fila, normalizar_ajustes, regla_de_familia
from ..catalogo.convertir import FormatoCambiado, convertir, filas_con_titulos, leer_tabla, redetectar, titulos_de
from ..catalogo.odoo_api import aplicar, categorias_con_stock, sacar_foto
from .lista_proveedor import COLUMNAS_MAPEO

# Una fila VINCULAR de un producto que vuelve a la lista se guarda aparte, para verla y
# contarla; para el motor sigue siendo VINCULAR.
VUELVE = "vuelve"
ACCIONES = [
    (motor.NUEVO, "Producto nuevo"),
    (motor.VINCULAR, "Se agrega el proveedor"),
    (VUELVE, "Vuelve a la lista"),
    (motor.ACTUALIZAR, "Cambio"),
    (motor.SIN_CAMBIOS, "Sin cambios"),
    (motor.POSIBLE_DUPLICADO, "Posible duplicado"),
    (motor.REVISAR, "Revisar"),
    (motor.BAJA, "Ya no está en la lista"),
]
APROBADAS = ("aplicar", "es_el_mismo", "es_nuevo")
# Lo único de una fila que puede escribir un usuario (pantalla o API). El resto (estado,
# datos, lo necesario para deshacer…) lo escribe solo el módulo, con sudo: si no, se podría
# armar por API una fila que, al deshacerla, borre o cambie cualquier producto o precio.
CAMPOS_DE_USUARIO = {"decision", "producto_elegido_id", "categoria_id", "categoria_mostrada_id", "unidad_compra_id"}
# Filas de productos que ya están en nuestro catálogo (el resto de la lista es el catálogo
# del proveedor: se consulta y se agrega a pedido, P-048).
ACCIONES_REGISTRADAS = (motor.ACTUALIZAR, motor.VINCULAR, VUELVE, motor.SIN_CAMBIOS, motor.BAJA)
CAMPOS_RESTAURABLES = {"product_code", "product_name", "price", "min_qty", "delay", "comercio_precio_mayor",
                       "comercio_cantidad_mayor", "comercio_bulto", "comercio_presentaciones", "uom_id"}
# Más filas que esto se aplican en segundo plano, en tandas (la carga inicial puede tener
# miles de productos y una sola petición superaría el tiempo máximo del servidor).
TANDA_EN_PANTALLA = 400
# Hasta cuántos productos nuevos por vez se avisa a las otras listas (_avisar_otras_listas): más es
# una carga masiva, y cada uno vuelve a simular las filas parecidas de otros proveedores
MAX_AVISAR_OTRAS = 30


class OrmCliente:
    """Adaptador del ORM con la interfaz que usa catalogo.odoo_api (la misma que el cliente JSON-2)."""

    def __init__(self, env):
        self.env = env
        self.context = dict(env.context)

    def search_read(self, model, domain, fields_, context=None, **kwargs):
        return self.env[model].with_context(**(context or {})).search_read(domain, fields_, **kwargs)

    def create(self, model, vals):
        return self.env[model].create(vals).id

    def create_many(self, model, vals_list):
        return self.env[model].create(vals_list).ids

    def write(self, model, ids, vals):
        self.env[model].browse(ids).write(vals)


class ComercioListaImportacion(models.Model):
    """Una lista recibida de un proveedor: la simulación, lo revisado y lo aplicado."""

    _name = "comercio.lista.importacion"
    _description = "Importación de una lista de proveedor"
    _inherit = ["mail.thread"]
    _order = "id desc"

    lista_id = fields.Many2one("comercio.lista.proveedor", "Lista", required=True, ondelete="cascade")
    partner_id = fields.Many2one(related="lista_id.partner_id", store=True, string="Proveedor")
    parte = fields.Char(related="lista_id.parte", store=True, string="Parte",
                        help="La parte de la lista (General, Bulones…), si el proveedor la manda en partes.")
    name = fields.Char(compute="_compute_name", store=True)
    fecha = fields.Datetime(default=fields.Datetime.now, readonly=True)
    origen = fields.Selection(
        [("manual", "Subida a mano"), ("url", "Link"), ("correo", "Correo"),
         ("recalculo", "Recálculo (descuentos, IVA o dólar)")], default="manual", readonly=True
    )
    cotizacion_usada = fields.Float(
        "Dólar usado", readonly=True, digits=(16, 2),
        help="Pesos por dólar con que se calcularon los costos (solo listas en dólares).")
    archivo = fields.Binary("Archivo", attachment=True, readonly=True)
    nombre_archivo = fields.Char(readonly=True)
    archivo_original = fields.Binary(
        "Archivo original", attachment=True, readonly=True,
        help="El PDF o la foto que se subió; «Archivo» es la tabla que se leyó de él.")
    nombre_original = fields.Char(readonly=True)
    leida_con_ia = fields.Boolean(
        "Leída con IA", readonly=True,
        help="La lista vino en foto o PDF escaneado y la transcribió la IA: nada se aplica solo.")
    estado = fields.Selection(
        [("borrador", "Borrador"), ("simulada", "Para revisar"), ("aplicada", "Aplicada"),
         ("reemplazada", "Reemplazada por una más nueva"), ("descartada", "Descartada"), ("error", "Error")],
        default="borrador", tracking=True, readonly=True,
    )
    error = fields.Text(readonly=True)
    aviso_formato = fields.Text(
        "Formato cambiado", readonly=True,
        help="El proveedor cambió el formato y las columnas se detectaron solas: nada se aplica "
             "automáticamente hasta revisar.")
    linea_ids = fields.One2many("comercio.lista.importacion.linea", "importacion_id", "Filas")
    es_vigente = fields.Boolean(
        "Vigente", compute="_compute_es_vigente",
        help="La importación más nueva de este proveedor (sin contar descartadas ni con error). "
             "Solo esa se puede aplicar, deshacer o cambiar; las anteriores quedan como historial.")
    cant_nuevos = fields.Integer(compute="_compute_cantidades", store=True, string="Nuevos")
    cant_cambios = fields.Integer(compute="_compute_cantidades", store=True, string="Cambios de costo")
    cant_revisar = fields.Integer(compute="_compute_cantidades", store=True, string="Para revisar")
    cant_catalogo = fields.Integer(compute="_compute_cantidades", store=True, string="No los tenemos",
                                   help="Productos de la lista que no están en nuestro catálogo: se "
                                   "agregan solo los que se quieren vender.")
    cant_bajas = fields.Integer(compute="_compute_cantidades", store=True, string="Bajas")
    cant_vuelven = fields.Integer(compute="_compute_cantidades", store=True, string="Vuelven",
                                  help="Productos nuestros que habían salido de la lista y volvieron.")
    cant_aplicadas = fields.Integer(compute="_compute_cantidades", store=True, string="Aplicadas")
    cant_total = fields.Integer(compute="_compute_cantidades", store=True, string="Filas de la lista")
    cant_corregir = fields.Integer(
        compute="_compute_cant_corregir", string="Para corregir",
        help="Filas que la lista trajo mal (sin precio, precio 0, repetidas): «Corregir» o «Ignorar».")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            permitidos = {"lista_id", "archivo", "nombre_archivo", "origen"}
            for vals in vals_list:
                if set(vals) - permitidos:
                    raise AccessError(_("Estos datos de la importación los completa el sistema."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            # Lo único editable es lo de cada fila (categoría, decisión, producto elegido), que
            # el formulario guarda a través de la importación: se pasa a la fila y sus controles.
            if set(vals) != {"linea_ids"}:
                raise AccessError(_("Una importación no se modifica a mano: se usan sus botones."))
            lineas = self.env["comercio.lista.importacion.linea"]
            for comando in vals["linea_ids"]:
                if comando[0] == Command.LINK:
                    continue
                if comando[0] != Command.UPDATE:
                    raise AccessError(_("Las filas de una importación no se agregan ni se quitan a mano."))
                linea = lineas.browse(comando[1])
                if linea.importacion_id not in self:
                    raise AccessError(_("Esa fila es de otra importación."))
                if comando[2]:
                    linea.write(comando[2])
            return True
        return super().write(vals)

    def _compute_cant_corregir(self):
        Linea = self.env["comercio.lista.importacion.linea"]
        for imp in self:
            imp.cant_corregir = Linea.search_count([("importacion_id", "=", imp.id), ("accion", "=", motor.REVISAR),
                                                    ("estado", "=", "pendiente")]) if imp.id else 0

    def _vigente_de(self, lista):
        """La más nueva que cuenta: no las que no cambiaron nada (con error, descartadas o
        reemplazadas sin aplicar). Una reemplazada que llegó a aplicar filas sí cuenta: si la
        que la reemplazó falla, lo aplicado de ella se tiene que poder deshacer."""
        return self.search([("lista_id", "=", lista.id),
                            ("estado", "not in", ("error", "descartada")),
                            "|", ("estado", "!=", "reemplazada"), ("cant_aplicadas", ">", 0)],
                           order="id desc", limit=1)

    def _compute_es_vigente(self):
        for imp in self:
            imp.es_vigente = bool(imp.id) and imp._vigente_de(imp.lista_id) == imp

    def _exigir_vigente(self):
        """Las importaciones viejas son historial: no se aplican, deshacen ni cambian."""
        for imp in self:
            if not imp.es_vigente:
                raise UserError(_(
                    "«%s» ya no es la lista vigente de este proveedor (hay una más nueva, o está "
                    "descartada): queda como historial y no se modifica. Para volver a ella, deshacé y "
                    "descartá primero la más nueva.", imp.name))

    def unlink(self):
        # Borrar una importación pierde el historial y lo necesario para deshacer
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Las importaciones no se borran: quedan como historial. "
                                "Lo que no se quiera aplicar se «Descarta»."))
        return super().unlink()

    @api.depends("partner_id.name", "lista_id.parte", "fecha")
    def _compute_name(self):
        for imp in self:
            fecha = fields.Datetime.context_timestamp(imp, imp.fecha).strftime("%d/%m/%Y %H:%M") if imp.fecha else ""
            parte = f" ({imp.lista_id.parte})" if imp.lista_id.parte else ""  # General, Bulones…: se distinguen
            imp.name = f"{imp.partner_id.name or ''}{parte} {fecha}".strip()

    @api.depends("linea_ids.estado", "linea_ids.accion", "linea_ids.variacion", "linea_ids.registrado",
                 "linea_ids.producto_id")
    def _compute_cantidades(self):
        for imp in self:
            lineas = imp.linea_ids
            pendientes = lineas.filtered(lambda linea: linea.estado == "pendiente")
            imp.cant_total = len(lineas.filtered(lambda linea: linea.accion != motor.BAJA))
            imp.cant_nuevos = len(lineas.filtered(lambda linea: linea.accion == motor.NUEVO))
            imp.cant_cambios = len(lineas.filtered(lambda linea: linea.variacion))
            imp.cant_bajas = len(lineas.filtered(lambda linea: linea.accion == motor.BAJA))
            imp.cant_vuelven = len(lineas.filtered(lambda linea: linea.accion == VUELVE))
            # Para revisar: solo lo que toca productos nuestros. Lo que no tenemos es catálogo.
            imp.cant_revisar = len(pendientes.filtered("registrado"))
            imp.cant_catalogo = len(lineas.filtered(
                lambda linea: not linea.registrado and (linea.estado == "pendiente" or linea.producto_id)))
            imp.cant_aplicadas = len(lineas.filtered(lambda linea: linea.estado == "aplicada"))

    # ------------------------------------------------------------------ simulación
    def _filas(self, lineas=None):
        """Filas de la planilla modelo con las decisiones tomadas («es el mismo», «es nuevo»).
        Con `lineas`, solo esas (cada una con su número de fila original)."""
        # Una sola lectura en bloque: recorrer como registros las 10 000 filas de una lista grande
        # (FC) tardaba ~12 s, y cada «Agregar» lo hace dos veces (planificar y verificar)
        dominio = [("id", "in", lineas.ids)] if lineas is not None else [("importacion_id", "=", self.id)]
        registros = self.env["comercio.lista.importacion.linea"].sudo().search_read(
            dominio + [("datos", "!=", False)],
            ["fila", "datos", "categoria_id", "unidad_compra_id", "decision", "producto_elegido_id"], order="fila")
        filas = []
        for registro in registros:
            fila = json.loads(registro["datos"])
            fila["_n"] = registro["fila"]
            if registro["categoria_id"]:  # la elegida en la fila (por defecto, el rubro de la lista)
                fila["categoria"] = registro["categoria_id"][1]  # nombre completo («A / B»)
            if registro["unidad_compra_id"]:  # la caja del proveedor, elegida en la fila (P-053)
                fila["unidad_compra"] = registro["unidad_compra_id"][0]
            if registro["decision"] == "es_el_mismo" and registro["producto_elegido_id"]:
                fila["vincular_a"] = f"id:{registro['producto_elegido_id'][0]}"
            elif registro["decision"] == "es_nuevo":
                fila["nuevo"] = "si"
            filas.append(fila)
        return filas

    def _plan(self, cliente, filas, con_bajas=True, lista_entera=None):
        lista = self.lista_id
        hoy = fields.Date.context_today(self).isoformat()
        return motor.planificar(
            filas, sacar_foto(cliente, hoy), categorias_con_stock(cliente),
            lista_completa_de=lista.partner_id.id if lista.lista_completa and con_bajas else None,
            lista_id=lista.id,
            otras_listas=bool(lista.search_count([("partner_id", "=", lista.partner_id.id),
                                                  ("id", "!=", lista.id)])),
            lista_entera=lista_entera,
        ), hoy

    def _plan_para(self, cliente, lineas):
        """Plan de las filas a aplicar. Solo si hay bajas hace falta la lista entera (para saber
        qué productos ya no están); si no, alcanza con esas filas (mucho más rápido)."""
        if lineas.filtered(lambda li: li.accion == motor.BAJA):
            return self._plan(cliente, self._filas())
        return self._plan(cliente, self._filas(lineas), con_bajas=False, lista_entera=self._filas())

    def _replanificar(self, lineas, nota=None, solo_si_cambia=False):
        """Vuelve a simular solo esas filas (p. ej. corregidas a mano), sin tocar el resto.
        `nota`: lo que se suma a los avisos (por defecto, «corregida a mano»); `solo_si_cambia`:
        no toca las filas a las que el plan les da la misma acción. Devuelve las que cambió."""
        self.ensure_one()
        self._exigir_vigente()
        acciones, _hoy = self._plan(OrmCliente(self.sudo().env), self._filas(lineas), con_bajas=False,
                                    lista_entera=self._filas())
        por_fila = {a.fila: a for a in acciones if a.fila}
        nota = nota or _("Fila corregida a mano por %s.", self.env.user.name)
        cambiadas = lineas.browse()
        for linea in lineas:
            a = por_fila.get(linea.fila)
            if not a or (solo_si_cambia and (VUELVE if a.vuelve else a.tipo) == linea.accion):
                continue
            cambiadas |= linea
            nuevo = a.tipo in (motor.NUEVO, motor.POSIBLE_DUPLICADO)
            linea.sudo().write({
                "accion": VUELVE if a.vuelve else a.tipo,
                "detalle": a.detalle,
                "avisos": "\n".join(a.avisos + [nota]),
                "codigo_proveedor": a.codigo_proveedor,
                "descripcion": a.descripcion,
                "codigo_barras": a.codigo_barras,
                "costo": a.costo or 0.0,
                "costo_anterior": a.costo_anterior or 0.0,
                "costo_mayor": a.costo_mayor or 0.0,
                "mayor_anterior": a.mayor_anterior or 0.0,
                "variacion": (a.variacion or 0.0) * 100,
                "producto_id": a.tmpl if isinstance(a.tmpl, int) else False,
                "candidato_ids": [(6, 0, [c.id for c in a.candidatos if isinstance(c.id, int)])],
                "categoria_id": (linea.categoria_id.id or self.lista_id.categoria_id.id or False) if nuevo else False,
                "automatico": False,  # corregida a mano: la aplica una persona
                "decision": "nada" if a.tipo == motor.SIN_CAMBIOS else "pendiente",
                "estado": "sin_cambios" if a.tipo == motor.SIN_CAMBIOS else "pendiente",
            })
        cambiadas._calcular_mas_barato()
        return cambiadas

    def _avisar_otras_listas(self, productos):
        """Productos que se acaban de agregar a nuestro catálogo (02/11): en las listas vigentes
        de los OTROS proveedores, las filas «nuevo» que se les parecen se vuelven a simular, así
        pasan a «¿Es el mismo?» con ese producto y no se saltea ningún proveedor ni se crea otro
        igual. Primero se filtra en la base por las dos palabras más largas del nombre."""
        self.ensure_one()
        Linea = self.env["comercio.lista.importacion.linea"].sudo()
        excluir = self.env.context.get("comercio_no_avisar") or []
        cambiadas = Linea
        for producto in productos:
            palabras = sorted((t for t in terminos(producto.name) if not t.strip()[:1].isdigit()),
                              key=len, reverse=True)[:2]
            if not palabras:
                continue
            dominio = [("estado", "=", "pendiente"), ("accion", "=", motor.NUEVO),
                       ("producto_id", "=", False), ("partner_id", "!=", self.partner_id.id),
                       ("id", "not in", excluir)]
            dominio += [("texto_busqueda", "ilike", p) for p in palabras]
            for importacion in Linea.search(dominio, limit=200).importacion_id:
                if importacion._vigente_de(importacion.lista_id) != importacion:
                    continue
                cambiadas |= importacion._replanificar(
                    Linea.search(dominio + [("importacion_id", "=", importacion.id)]),
                    nota=_("Se agregó «%(p)s» desde la lista de %(prov)s: ¿es el mismo?",
                           p=producto.name, prov=self.partner_id.name),
                    solo_si_cambia=True)
        return cambiadas

    def action_simular(self):
        for imp in self:
            # La misma regla que «vigente»: una más nueva descartada o con error no cuenta
            if imp._vigente_de(imp.lista_id) != imp:
                raise UserError(_("Hay una importación más nueva de esta lista: esta queda como "
                                  "historial y no se vuelve a simular."))
            if imp.cant_aplicadas:
                raise UserError(_("Esta importación ya tiene filas aplicadas: no se vuelve a simular "
                                  "(quedaría sin el registro de lo hecho). Subí la lista de nuevo."))
            imp._simular()
            imp.lista_id._actualizar_familias()
        return True

    def _simular(self):
        self.ensure_one()
        lista = self.lista_id
        contenido = self.archivo.content if self.archivo else b""
        nombre = self.nombre_archivo or "lista.xlsx"
        titulos, sugerido = [], {}
        try:
            titulos, sugerido = lista.sugerencia_mapeo(contenido, nombre)
            tabla = leer_tabla(contenido, nombre, lista.hoja or None,
                               monedas=(sugerido.get("moneda") or lista.moneda) == "mixta")
            try:
                mapeo = lista.mapeo(sugerido)
                self.sudo().cotizacion_usada = mapeo["ajustes"]["cotizacion"] or 0.0
                if "costo" not in mapeo["columnas"]:
                    raise FormatoCambiado(_("Falta elegir la columna del costo."))
                fila_titulos = sugerido.get("fila_encabezado") or lista.fila_encabezado or 1
                filas = convertir(mapeo, filas_con_titulos(tabla, fila_titulos))
            except FormatoCambiado:
                # El proveedor cambió el formato: se detecta de nuevo, como la primera vez.
                # Si no alcanza (no aparece el costo), lo resuelve una persona.
                detectado = redetectar(tabla)
                if not detectado:
                    raise
                fila_titulos, columnas = detectado
                titulos = [t for t in titulos_de(tabla, fila_titulos) if t]
                # Las columnas elegidas que el archivo sigue teniendo se conservan (también las que
                # nunca se detectan solas, como «descuento», y las unidas con « + »); solo cambia lo
                # que ya no está
                def sigue(titulo):
                    return bool(titulo) and all(t.strip() in titulos for t in titulo.split(" + "))

                sugerido = {"fila_encabezado": fila_titulos,
                            **{campo: lista[campo] if sigue(lista[campo]) else columnas.get(col, False)
                               for col, campo in COLUMNAS_MAPEO.items()}}
                filas = convertir(lista.mapeo(sugerido), filas_con_titulos(tabla, fila_titulos))
                aviso = self._describir_formato(lista, sugerido)
                if self.origen != "manual":
                    # Una lista que llegó sola (correo o link) no cambia la configuración del
                    # proveedor: el «De:» de un correo se puede falsificar. Se usa solo para esta
                    # importación; queda guardado cuando alguien la sube a mano o corrige las columnas.
                    sugerido = {}
                    aviso += _("\nLlegó sola (%s): el formato nuevo NO se guardó. Para guardarlo, subí "
                               "la lista a mano o corregí las columnas del proveedor.",
                               dict(self._fields["origen"].selection).get(self.origen))
                self.sudo().aviso_formato = aviso
        except UserError as error:  # p. ej. lista en dólares sin cotización
            self.sudo().write({"estado": "error", "error": error.args[0]})
            return
        except FormatoCambiado as error:
            self.sudo().write({"estado": "error", "error": _(
                "%(e)s\nTítulos encontrados en el archivo: %(t)s\nCorregir las columnas en la lista del "
                "proveedor y volver a simular.", e=error, t=", ".join(titulos) or "—")})
            return
        except Exception as error:  # noqa: BLE001 — archivo dañado o de otro formato
            self.sudo().write({"estado": "error", "error": _("No se pudo leer el archivo: %s", error)})
            return
        if not filas:
            self.sudo().write({"estado": "error", "error": _("El archivo no tiene productos con esas columnas.")})
            return
        # Las columnas sugeridas se guardan recién cuando el archivo se leyó bien
        if sugerido:
            lista.write(sugerido)
        for fila in filas:
            fila["proveedor_id"] = lista.partner_id.id
        anteriores = {li.fila: li for li in self.linea_ids if li.fila}
        try:
            acciones, _hoy = self._plan(OrmCliente(self.env), filas)
        except Exception as error:  # noqa: BLE001 — que una lista rara no deje un error 500
            self.sudo().write({"estado": "error", "error": _("No se pudo armar la simulación: %s", error)})
            return
        tope = (lista.tope_automatico or 0) / 100
        promos_antes = self._promociones_anteriores()
        iva_de = self._iva_de_productos(acciones, filas)
        valores = []
        for a in acciones:
            fila = filas[a.fila - 2] if a.fila else None
            anterior = anteriores.get(a.fila)
            avisos_promo = self._avisos_promocion(fila, a, promos_antes) + self._aviso_iva(fila, a, iva_de)
            automatico = motor.es_automatico(a, tope) and not self.aviso_formato and not self.leida_con_ia
            if avisos_promo and fila and not fila.get("promocion"):
                automatico = False  # se terminó una promoción: que lo vea una persona aunque sea poco
            if a.tipo == motor.SIN_CAMBIOS:
                decision, estado = "nada", "sin_cambios"
            elif anterior and anterior.decision == "ignorar":
                decision, estado = "ignorar", "ignorada"
            elif anterior and anterior.decision in APROBADAS:
                decision, estado = anterior.decision, "pendiente"
            else:
                decision, estado = ("aplicar" if automatico else "pendiente"), "pendiente"
            valores.append({
                "importacion_id": self.id,
                "fila": a.fila,
                "datos": json.dumps(fila) if fila else False,
                "accion": VUELVE if a.vuelve else a.tipo,
                "detalle": a.detalle,
                "avisos": "\n".join(a.avisos + avisos_promo),
                "codigo_proveedor": a.codigo_proveedor,
                "descripcion": a.descripcion,
                "codigo_barras": a.codigo_barras,
                "costo": a.costo or 0.0,
                "costo_anterior": a.costo_anterior or 0.0,
                "costo_mayor": a.costo_mayor or 0.0,
                "mayor_anterior": a.mayor_anterior or 0.0,
                "variacion": (a.variacion or 0.0) * 100,
                "producto_id": a.tmpl if isinstance(a.tmpl, int) else False,
                "proveedor_info_id": a.proveedor_id if a.tipo == motor.BAJA else False,
                "candidato_ids": [(6, 0, [c.id for c in a.candidatos if isinstance(c.id, int)])],
                "producto_elegido_id": anterior.producto_elegido_id.id if anterior else False,
                "categoria_id": ((anterior.categoria_id.id if anterior and anterior.categoria_id
                                  else lista.categoria_id.id) or False)
                if a.tipo in (motor.NUEVO, motor.POSIBLE_DUPLICADO) else False,
                "automatico": automatico,
                "decision": decision,
                "estado": estado,
            })
        self.sudo().linea_ids.unlink()
        self.env["comercio.lista.importacion.linea"].sudo().create(valores)
        self.linea_ids._calcular_mas_barato()
        self.sudo().write({"estado": "simulada", "error": False})
        if self.aviso_formato:
            self.message_post(body=_("El proveedor cambió el formato; columnas detectadas solas:\n%s",
                                     self.aviso_formato))
        # Las importaciones anteriores de la misma lista quedan reemplazadas: aplicarlas
        # después volvería atrás los precios.
        self.search([("lista_id", "=", lista.id), ("id", "<", self.id),
                     ("estado", "=", "simulada")]).sudo().write({"estado": "reemplazada"})

    def _promociones_anteriores(self):
        """{código del proveedor: texto de la promoción} de la importación anterior de esta lista
        (para avisar cuando una promoción se termina y el costo sube por eso)."""
        anterior = self.search([("lista_id", "=", self.lista_id.id), ("id", "<", self.id),
                                ("estado", "in", ("aplicada", "reemplazada", "simulada"))], order="id desc", limit=1)
        if not anterior:
            return {}
        promos = {}
        for registro in self.env["comercio.lista.importacion.linea"].sudo().search_read(
                [("importacion_id", "=", anterior.id), ("datos", "ilike", '"promocion"')], ["datos"]):
            datos = json.loads(registro["datos"])
            if datos.get("codigo_proveedor") and datos.get("promocion"):
                promos[datos["codigo_proveedor"]] = datos["promocion"]
        return promos

    def _iva_de_productos(self, acciones, filas):
        """{producto: alícuota de su IVA de venta} de los productos nuestros cuya fila trae IVA."""
        ids = {a.tmpl for a in acciones if isinstance(a.tmpl, int) and a.fila
               and (filas[a.fila - 2] or {}).get("iva_fila")}
        salida = {}
        for producto in self.env["product.template"].sudo().browse(list(ids)).exists():
            iva = producto.taxes_id.filtered(lambda t: t.amount_type == "percent")
            salida[producto.id] = sum(iva.mapped("amount")) if iva else None
        return salida

    @staticmethod
    def _aviso_iva(fila, accion, iva_de):
        """Si la lista dice otro IVA que el del producto: se avisa y se respeta el del producto."""
        from ..catalogo.costo import _pct, porcentaje

        if not fila or not isinstance(accion.tmpl, int) or accion.tmpl not in iva_de:
            return []
        en_lista, propio = porcentaje(fila.get("iva_fila")), iva_de[accion.tmpl]
        if en_lista is None or (propio is not None and abs(en_lista - propio) < 0.01):
            return []
        return [_("La lista dice IVA %(l)s y el producto tiene %(p)s: se respeta el del producto (revisar cuál es el "
                  "correcto).", l=_pct(en_lista), p=_pct(propio) if propio is not None else _("ninguno"))]

    @staticmethod
    def _avisos_promocion(fila, accion, promos_antes):
        """La promoción del proveedor que trae la fila, o que traía y ya no (el costo sube por eso)."""
        if not fila:
            return []
        codigo = fila.get("codigo_proveedor") or ""
        if fila.get("promocion"):
            return [_("Promoción del proveedor: %s", fila["promocion"])]
        if codigo in promos_antes:
            sube = accion.variacion is not None and accion.variacion > 0
            if sube:
                return [_("Sube porque se terminó la promoción del proveedor («%s»)", promos_antes[codigo])]
            return [_("Se terminó la promoción del proveedor («%s»)", promos_antes[codigo])]
        return []

    @staticmethod
    def _describir_formato(lista, sugerido):
        """«Costo: «Precio s/IVA» → «Precio neto»», una línea por columna que cambió."""
        nombres = {campo: lista._fields[campo].string for campo in COLUMNAS_MAPEO.values()}
        nombres["fila_encabezado"] = lista._fields["fila_encabezado"].string
        cambios = [f"{nombres[campo]}: «{lista[campo] or '—'}» → «{valor or '—'}»"
                   for campo, valor in sugerido.items() if (lista[campo] or False) != (valor or False)]
        return "\n".join(cambios)

    # ------------------------------------------------------------------ aplicar
    def action_aplicar_automaticos(self):
        """Aplica lo que la lista permite sin revisar (cambios de costo dentro del tope)."""
        for imp in self:
            imp._aplicar(imp.linea_ids.filtered(lambda li: li.estado == "pendiente" and li.automatico),
                         solo_automaticos=True)
        return True

    def _filas_para_aplicar_todo(self):
        """Lo que aplica «Aplicar todo»: todo lo pendiente de productos que ya tenemos (cambios de
        costo, bajas, proveedor que se agrega o vuelve) y lo que se marcó a mano. Nunca agrega
        productos que no tenemos: eso se elige en «No los tenemos» (así una lista entera no llena
        el catálogo). Tampoco lo que hay que mirar: posibles duplicados sin decidir y filas a corregir."""
        de_lo_nuestro = (motor.ACTUALIZAR, motor.BAJA, motor.VINCULAR, VUELVE)
        return self.linea_ids.filtered(lambda li: li.estado == "pendiente" and (
            li.decision in APROBADAS or (li.accion in de_lo_nuestro and li.decision == "pendiente")))

    def action_aplicar_todo(self):
        """Un solo botón (19/11, en lugar de «Aplicar automáticos» con tope de variación y
        «Aplicar todo lo marcado»): ver _filas_para_aplicar_todo."""
        self.ensure_one()
        self._exigir_vigente()
        lineas = self._filas_para_aplicar_todo()
        if not lineas:
            raise UserError(_("No queda nada para aplicar de lo que ya tenemos. Los productos que no tenemos "
                              "se agregan desde «No los tenemos»."))
        return self._aplicar_o_encolar(lineas)

    def action_aplicar_marcados(self):
        """Aplica todo lo marcado: automáticos, «aplicar», «es el mismo» y «es nuevo»."""
        for imp in self:
            imp._aplicar_o_encolar(imp.linea_ids.filtered(
                lambda li: li.estado == "pendiente" and li.decision in APROBADAS))
        return True

    def _aplicar_o_encolar(self, lineas):
        """Pocas filas: se aplican ya. Muchas: en segundo plano, en tandas, y se avisa al terminar."""
        self.ensure_one()
        if len(lineas) <= TANDA_EN_PANTALLA:
            return self._aplicar(lineas)
        lineas.sudo().write({"en_cola": True})
        self.message_post(body=_("Se están aplicando %s filas en segundo plano.", len(lineas)))
        self.env.ref("comercio_catalogo.cron_aplicar_en_cola")._trigger()
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Aplicando en segundo plano"),
            "message": _("Son %s filas: se aplican en tandas. Te aviso cuando termine.", len(lineas)),
            "type": "info", "next": {"type": "ir.actions.act_window_close"}}}

    @api.model
    def _cron_aplicar_en_cola(self):
        """Aplica una tanda de filas encoladas por importación y se vuelve a programar si quedan."""
        Linea = self.env["comercio.lista.importacion.linea"]
        for importacion in Linea.search([("en_cola", "=", True)]).importacion_id:
            tanda = importacion.linea_ids.filtered("en_cola").sorted("fila")[:TANDA_EN_PANTALLA]
            try:
                importacion._aplicar(tanda.filtered(lambda li: li.estado == "pendiente"))
            except UserError as error:
                importacion.message_post(body=_("Una tanda no se aplicó: %s", error))
            tanda.sudo().write({"en_cola": False})
            if not importacion.linea_ids.filtered("en_cola"):
                importacion.lista_id._recordar(_("Terminó de aplicarse la lista de %s.",
                                                 importacion.partner_id.name))
            self.env.cr.commit()  # cada tanda queda guardada aunque falle la siguiente
        if Linea.search_count([("en_cola", "=", True)]):
            self.env.ref("comercio_catalogo.cron_aplicar_en_cola")._trigger()

    @staticmethod
    def _coincide(linea, a):
        """¿La acción de hoy es la misma que se simuló? Si no, algo cambió desde la simulación."""
        if linea.decision == "es_el_mismo" or (linea.unidad_compra_id and linea.producto_id):
            # posible duplicado, o «nuevo» que ya teníamos; o se eligió la unidad de compra
            esperadas = (motor.VINCULAR, VUELVE, motor.ACTUALIZAR)
        elif linea.accion == motor.POSIBLE_DUPLICADO:
            esperadas = (motor.NUEVO,) if linea.decision == "es_nuevo" else (
                motor.VINCULAR, VUELVE, motor.ACTUALIZAR)
        else:
            esperadas = (linea.accion,)
        if (VUELVE if a.vuelve else a.tipo) not in esperadas:
            return False
        # El costo anterior solo se compara si ya se simuló como cambio de costo (en un posible
        # duplicado no había costo anterior: es el del producto que se elige al confirmar)
        if (linea.accion == motor.ACTUALIZAR and a.tipo == motor.ACTUALIZAR
                and abs((a.costo_anterior or 0) - (linea.costo_anterior or 0)) > 0.005):
            return False
        return True

    def _aplicar(self, lineas, solo_automaticos=False):
        self.ensure_one()
        if not lineas:
            return
        # «Aplicada» = lo nuestro ya se revisó; del catálogo se pueden seguir agregando productos
        if self.estado not in ("simulada", "aplicada"):
            raise UserError(_("Esta importación está «%s»: no se puede aplicar.",
                              dict(self._fields["estado"].selection).get(self.estado)))
        self._exigir_vigente()  # una más nueva descartada o con error no cuenta
        falta = lineas.filtered(lambda li: li.decision == "es_el_mismo" and not li.producto_elegido_id)
        if falta:
            raise UserError(_("Elegí el producto en las filas marcadas «Es el mismo» (fila %s).", falta[0].fila))
        cliente = OrmCliente(self.sudo().env)  # el grupo «Costos y precios» controla quién llega acá
        acciones, hoy = self._plan_para(cliente, lineas)
        tope = (self.lista_id.tope_automatico or 0) / 100
        por_fila = {li.fila: li for li in lineas if li.fila}
        bajas = {li.proveedor_info_id.id: li for li in lineas if li.accion == motor.BAJA}
        Linea = self.env["comercio.lista.importacion.linea"]
        elegidas, hechas, cambiaron = [], Linea, Linea
        pares = []  # (acción, fila) para guardar cómo deshacer cada una
        nuevos_aprobados = {a.tmpl for a in acciones if a.tipo == motor.NUEVO and a.fila in por_fila}
        for a in acciones:
            linea = por_fila.get(a.fila) if a.fila else bajas.get(a.proveedor_id)
            if not linea:
                continue
            if not self._coincide(linea, a) or (solo_automaticos and not motor.es_automatico(a, tope)):
                cambiaron |= linea
                continue
            if isinstance(a.tmpl, str) and a.tipo != motor.NUEVO and a.tmpl not in nuevos_aprobados:
                continue  # depende de un producto nuevo que todavía no se aprobó
            elegidas.append(a)
            hechas |= linea
            pares.append((a, linea))
        aviso = None
        if cambiaron:
            # Se vuelven a calcular ahí mismo (p. ej. se agregó el mismo producto desde otra lista:
            # ahora es «¿Es el mismo?»), en vez de quedar trabadas hasta subir la lista de nuevo
            self._replanificar(cambiaron, nota=_("Cambió desde la simulación (se agregó un producto "
                                                  "parecido o hubo un cambio a mano): se volvió a "
                                                  "calcular, revisala."))
            aviso = {"type": "ir.actions.client", "tag": "display_notification", "params": {
                "title": _("Revisá %s fila(s)", len(cambiaron)), "type": "warning", "sticky": False,
                "message": _("Cambiaron desde que se simuló la lista (p. ej. ya agregaste un producto "
                             "parecido desde otro proveedor): se volvieron a calcular y no se aplicaron. "
                             "Mirá «Se parece a» y, si es el mismo, «Es el mismo»."),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}
        if not elegidas and cambiaron:
            self.message_post(body=_("No se aplicó nada: %s filas cambiaron desde la simulación y se "
                                     "volvieron a calcular.", len(cambiaron)))
            return aviso
        if not elegidas:
            raise UserError(_("Nada para aplicar: lo marcado depende de productos nuevos que todavía no "
                              "se aprobaron."))
        creados = aplicar(cliente, elegidas, hoy, lista_id=self.lista_id.id)
        for a, linea in pares:
            vals = {"deshacer_datos": json.dumps(a.deshacer)}
            if a.tipo == motor.NUEVO:
                vals["producto_id"] = creados.get(a.tmpl)
            elif isinstance(a.tmpl, int) and not linea.producto_id:
                vals["producto_id"] = a.tmpl  # «es el mismo»: queda en nuestro catálogo
            linea.sudo().write(vals)
        hechas.sudo().write({"estado": "aplicada", "aplicada_por": self.env.user.id})
        # Bajas que ya no corresponden: el producto sigue en la lista (p. ej. con otro código)
        seguidos = {a.tmpl for a, _linea in pares if a.tipo in (motor.VINCULAR, motor.ACTUALIZAR)}
        if seguidos:
            # Búsqueda en la base, no recorriendo las filas: con listas de 10 000 filas (FC) recorrerlas
            # tardaba ~25 s por cada «Agregar»
            Linea.sudo().search([
                ("importacion_id", "=", self.id), ("estado", "=", "pendiente"), ("accion", "=", motor.BAJA),
                ("producto_id", "in", [t for t in seguidos if isinstance(t, int)]),
            ]).write({"estado": "sin_cambios", "decision": "nada",
                      "avisos": _("Sigue en la lista con otro código: no es una baja.")})
        self._verificar(hechas, cliente)
        tocados = [creados.get(a.tmpl) if isinstance(a.tmpl, str) else a.tmpl for a in elegidas]
        self.env["product.template"].browse([t for t in tocados if t]).exists()._comercio_actualizar_costo()
        hechas._calcular_mas_barato()
        if self._revisada():
            self.sudo().estado = "aplicada"
        self.message_post(body=_("Aplicadas %(n)s filas por %(u)s.", n=len(hechas), u=self.env.user.name))
        nuevos = self.env["product.template"].browse([t for t in creados.values() if t]).exists()
        if nuevos and len(nuevos) <= MAX_AVISAR_OTRAS:
            self._avisar_otras_listas(nuevos)
        return aviso

    def _revisada(self):
        """No queda nada pendiente de nuestros productos (lo que no tenemos es catálogo)."""
        self.ensure_one()
        return not self.env["comercio.lista.importacion.linea"].search_count(
            [("importacion_id", "=", self.id), ("estado", "=", "pendiente"), ("registrado", "=", True)], limit=1)

    def _verificar(self, hechas, cliente):
        """Vuelve a planificar: lo aplicado tiene que quedar «sin cambios» (o ya no aparecer)."""
        acciones, _hoy = self._plan_para(cliente, hechas)
        pendientes = {a.fila for a in acciones if a.tipo in (motor.NUEVO, motor.VINCULAR, motor.ACTUALIZAR)}
        bajas = {a.proveedor_id for a in acciones if a.tipo == motor.BAJA}
        for linea in hechas:
            if (linea.fila and linea.fila in pendientes) or (
                    linea.accion == motor.BAJA and linea.proveedor_info_id.id in bajas):
                linea.sudo().write({"estado": "error",
                                    "avisos": (linea.avisos or "") + "\nLa verificación no coincide."})

    # ------------------------------------------------------------------ deshacer / descartar
    def action_deshacer_todo(self):
        for imp in self:
            imp.linea_ids.filtered(lambda li: li.estado == "aplicada").action_deshacer()
        return True

    def action_descartar(self):
        """No aplicar nada más de esta lista: lo pendiente queda ignorado (lo aplicado no se toca)."""
        self._exigir_vigente()
        for imp in self:
            imp.linea_ids.filtered(lambda li: li.estado == "pendiente").sudo().write(
                {"decision": "ignorar", "estado": "ignorada", "en_cola": False})
            imp.sudo().estado = "aplicada" if imp.cant_aplicadas else "descartada"
            imp.message_post(body=_("Descartada por %s.", self.env.user.name))
        return True

    # ------------------------------------------------------------------ avisos
    def _avisar_si_hay_pendientes(self):
        for imp in self.filtered(lambda i: i.estado in ("simulada", "error")):
            if imp.estado == "error":
                texto = _("No se pudo leer la lista de %(p)s: %(e)s", p=imp.partner_id.name, e=imp.error)
            elif imp.cant_revisar:
                texto = _("La lista de %(p)s tiene %(n)s filas para revisar.", p=imp.partner_id.name,
                          n=imp.cant_revisar)
            else:
                continue
            imp.lista_id._recordar(texto)

    def action_abrir(self):
        """Abre la importación dentro de la app «Costos y precios» (menú y migas de pan)."""
        self.ensure_one()
        accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_catalogo.action_importaciones")
        accion.update({"res_id": self.id, "view_mode": "form", "views": [(False, "form")],
                       "target": "current"})
        return accion

    def action_revisar_filas(self):
        """Abre las filas de esta importación en una lista con casillas.

        La lista de la pestaña «Filas» del formulario no puede tener casillas (Odoo no
        las pone en las listas embebidas), así que para elegir varias filas y aplicarlas
        juntas se usa esta pantalla. Arranca filtrada en lo que hay para hacer: lo nuestro
        para revisar o, si no queda nada de eso, lo que no tenemos (con «Para revisar» fijo,
        una lista que es todo catálogo abría vacía, 21/10).
        """
        self.ensure_one()
        accion = self.env["ir.actions.act_window"]._for_xml_id("comercio_catalogo.action_importacion_lineas")
        if self.estado == "simulada" and self.cant_revisar:
            contexto = {"search_default_revisar": 1}
        elif self.es_vigente and self.cant_catalogo:
            contexto = {"search_default_catalogo": 1}
        else:
            contexto = {}
        accion.update({
            "name": self.name,
            "domain": [("importacion_id", "=", self.id)],
            "context": contexto,
            "target": "current",
        })
        return accion


class ComercioListaImportacionLinea(models.Model):
    """Una fila de la lista del proveedor: qué propone el plan y qué se decidió."""

    _name = "comercio.lista.importacion.linea"
    _description = "Fila de una lista de proveedor"
    _rec_name = "descripcion"
    _order = "importacion_id, registrado desc, estado_orden, fila"  # lo nuestro primero

    importacion_id = fields.Many2one("comercio.lista.importacion", "Importación", required=True,
                                     ondelete="cascade")
    partner_id = fields.Many2one(related="importacion_id.partner_id", string="Proveedor")
    importacion_vigente = fields.Boolean(related="importacion_id.es_vigente", string="De la lista vigente")
    fila = fields.Integer("Fila del archivo")
    datos = fields.Text()  # fila de la planilla modelo (JSON), para volver a planificar
    accion = fields.Selection(ACCIONES, "Novedad", readonly=True)
    detalle = fields.Char(readonly=True)
    avisos = fields.Text(readonly=True)
    codigo_proveedor = fields.Char("Código", readonly=True)
    descripcion = fields.Char("Descripción del proveedor", readonly=True)
    codigo_barras = fields.Char("Código de barras", readonly=True)
    costo = fields.Float("Costo nuevo", readonly=True)
    costo_anterior = fields.Float("Costo anterior", readonly=True)
    costo_mayor = fields.Float("Por mayor", readonly=True, help="Precio por mayor que trae la lista (si da dos precios).")
    precio_lista = fields.Char(
        "Precio de la lista", compute="_compute_calculo",
        help="Lo que dice la lista, antes de descuentos, recargo, dólar e IVA.")
    calculo = fields.Char(
        "Cálculo del costo", compute="_compute_calculo",
        help="Cómo se llegó al costo desde el precio de la lista (ver «Del precio de la lista al costo» "
             "en la lista del proveedor).")
    mayor_anterior = fields.Float("Por mayor anterior", readonly=True)
    familia = fields.Char("Familia", compute="_compute_calculo",
                          help="La familia de la fila en la lista del proveedor (título de arriba o columna).")
    cantidad_mayor = fields.Float("Desde", compute="_compute_calculo", digits=(16, 0),
                                  help="Cantidad desde la que vale el precio por mayor.")
    variacion = fields.Float("Variación (%)", readonly=True)
    cambio = fields.Char("Cambio", compute="_compute_cambio",
                         help="Cómo cambió el costo respecto del anterior de este proveedor. «· costo manual»: "
                         "el producto tiene el costo escrito a mano y la lista no lo cambia (solo el precio "
                         "de este proveedor).")
    producto_id = fields.Many2one("product.template", "Producto", readonly=True)
    costo_manual = fields.Boolean(related="producto_id.comercio_costo_manual")  # pinta «Costo nuevo»
    registrado = fields.Boolean(
        "En nuestro catálogo", compute="_compute_registrado", store=True,
        help="El producto ya está en Odoo. Si no, es parte del catálogo del proveedor: se agrega "
        "solo si se quiere vender.")
    de_lista_vigente = fields.Boolean(
        "De la última lista", compute="_compute_de_lista_vigente", search="_search_de_lista_vigente",
        help="La fila es de la lista vigente de su proveedor (no de una vieja).")
    texto_busqueda = fields.Char(compute="_compute_texto_busqueda", store=True)
    clave_producto = fields.Char(compute="_compute_clave_producto", store=True, index=True)
    producto_general = fields.Char(
        "Producto (todos)", compute="_compute_producto_general", store=True, index=True,
        help="Para agrupar en «Buscar producto» lo que venden los distintos proveedores, lo tengamos o no: "
             "nuestro producto; si no lo tenemos, el mismo código de barras o la misma descripción (sin importar "
             "mayúsculas, acentos ni el orden de las palabras: «4x40» = «4 X 40») junta a los proveedores.")
    sin_costo = fields.Boolean(
        "Sin precio", compute="_compute_sin_costo", store=True,
        help="La lista no trae precio para esta fila (o no se pudo leer): va al final en «Buscar producto».")
    buscar = fields.Char(
        "Producto", compute="_compute_buscar", search="_search_buscar",
        help="Palabras o números en cualquier orden; busca en la descripción del proveedor, su "
        "código, el código de barras y el nombre, código de barras y referencia de nuestro producto.")
    categoria_id = fields.Many2one(
        "product.category", "Categoría",
        help="Dónde queda el producto al agregarlo. Por defecto, el rubro elegido al importar la lista.")
    # La columna «Categoría» de las pantallas (21/10): en lo nuestro, la del producto (cambiarla
    # cambia el producto); en lo que no tenemos, la elegida para agregarlo (categoria_id).
    categoria_mostrada_id = fields.Many2one(
        "product.category", "Categoría", compute="_compute_categoria_mostrada",
        inverse="_inverse_categoria_mostrada",
        help="Productos nuestros: su categoría (cambiarla acá cambia el producto). Los que no tenemos: "
        "dónde queda al agregarlo; por defecto, el rubro elegido al importar la lista.")
    unidad_compra_id = fields.Many2one(
        "uom.uom", "Unidad de compra",
        help="Cómo lo vende este proveedor si no es la unidad del producto: p. ej. el tornillo se vende "
        "por kg y el proveedor lo trae en «Caja 1000 = 2,5 kg». El precio de la lista se guarda por esa "
        "unidad y al recibir entra convertido. Se puede crear desde acá (cuánto contiene).")
    unidades_posibles_ids = fields.Many2many("uom.uom", compute="_compute_unidades_posibles")
    producto_uom_id = fields.Many2one(related="producto_id.uom_id", string="Unidad del producto")
    proveedor_info_id = fields.Many2one("product.supplierinfo", readonly=True)
    candidato_ids = fields.Many2many("product.template", string="Se parece a", readonly=True)
    producto_elegido_id = fields.Many2one(
        "product.template", "Es el mismo que",
        help="Para «Es el mismo»: el producto existente que corresponde a esta fila.",
    )
    mas_barato_id = fields.Many2one("res.partner", "Más barato ahora", readonly=True)
    mas_barato_precio = fields.Float("Precio del más barato", readonly=True)
    automatico = fields.Boolean("Automático", readonly=True,
                                help="Se aplica sin revisar (cambio de costo dentro del tope).")
    decision = fields.Selection(
        [("pendiente", "Pendiente"), ("aplicar", "Aplicar"), ("es_el_mismo", "Es el mismo"),
         ("es_nuevo", "Es nuevo"), ("ignorar", "Ignorar"), ("nada", "—")],
        default="pendiente",
    )
    estado = fields.Selection(
        [("pendiente", "Pendiente"), ("aplicada", "Aplicada"), ("ignorada", "Ignorada"),
         ("sin_cambios", "Sin cambios"), ("error", "Error")],
        default="pendiente", readonly=True,
    )
    estado_orden = fields.Integer(compute="_compute_estado_orden", store=True)
    en_cola = fields.Boolean("Aplicándose en segundo plano", readonly=True)
    deshacer_datos = fields.Text(readonly=True)  # lo que hizo aplicar (JSON), para deshacerlo
    aplicada_por = fields.Many2one("res.users", readonly=True)

    descripcion_ver = fields.Char("Descripción del proveedor", compute="_compute_ver",
                                  help="La descripción del proveedor, escrita igual que nuestros productos para compararla.")
    parecidos_ver = fields.Text("Se parece a", compute="_compute_ver",
                                help="Nuestros productos parecidos, escritos igual que la descripción del proveedor.")

    # Para comparar (06/11): la columna «Nuestro producto» muestra el producto unido o, si la fila
    # todavía no tiene, el más parecido entre signos de pregunta, al lado de la descripción del
    # proveedor. comercio_catalogo_ia le suma lo que dijo la IA.
    comparar_id = fields.Many2one("product.template", "Para comparar", compute="_compute_comparar")
    comparar_codigo_barras = fields.Char("Su código de barras", compute="_compute_comparar")
    comparar_costo = fields.Float("Su costo actual", compute="_compute_comparar")
    nuestro_ver = fields.Char("Nuestro producto", compute="_compute_comparar",
                              help="El producto de nuestro catálogo unido a esta fila o, entre «¿?», el más "
                                   "parecido (todavía sin unir). La lupa muestra el detalle para comparar.")
    nuestro_es_parecido = fields.Boolean(compute="_compute_comparar")
    # Color de «Nuestro producto»: «parecido» (naranja); con la IA, «ia_mismo» (verde),
    # «ia_otro» (gris) o «ia_duda» (naranja).
    nuestro_tono = fields.Char(compute="_compute_comparar")
    costo_ver = fields.Char("Costo", compute="_compute_columnas_cortas",
                            help="Costo nuevo y cuánto cambió respecto del anterior de este proveedor: "
                                 "▲ sube (rojo) · ▼ baja (verde) · = igual.")
    mayor_ver = fields.Char("Por mayor", compute="_compute_columnas_cortas",
                            help="Precio por mayor de la lista y, después de «×», desde cuántas unidades vale.")

    @api.depends("codigo_proveedor", "descripcion")
    @api.depends_context("linea_con_codigo")
    def _compute_display_name(self):
        """Con el código delante al elegir un producto de la lista («[2202] AUTOPOLISH…»)."""
        con_codigo = self.env.context.get("linea_con_codigo")
        for linea in self:
            nombre = linea.descripcion or ""
            linea.display_name = f"[{linea.codigo_proveedor}] {nombre}" if con_codigo and linea.codigo_proveedor \
                else nombre

    @api.model
    def _search_display_name(self, operator, value):
        """Elegir una fila (p. ej. en «Descuentos por producto»): cada palabra por separado, en el
        código, la descripción o el código de barras, sin importar acentos ni comillas
        («autopolish clasico» encuentra «AUTOPOLISH "CLASICO" LUSTRE…»)."""
        if operator in ("ilike", "=ilike") and isinstance(value, str) and value.strip():
            patrones = terminos(value)
            if patrones:
                return Domain.AND([Domain("texto_busqueda", "ilike", patron) for patron in patrones])
        return super()._search_display_name(operator, value)

    def _por_regla(self, reglas):
        """{id de regla: [ids de filas]}: a qué filas de estas les toca cada descuento extra. Familia:
        la primera regla que coincide (como el motor), con la familia y la descripción; producto: el
        código exacto."""
        familias = [{"id": r.id, "contiene": r.contiene} for r in reglas.filtered(
            lambda r: r.tipo == "familia" and r.contiene).sorted(lambda r: (r.sequence, r.id))]
        por_codigo = {}
        for r in reglas.filtered(lambda r: r.tipo == "producto" and r.codigo):
            por_codigo.setdefault(r.codigo.strip(), []).append(r.id)
        resultado = {}
        for linea in self:
            codigo = (linea.codigo_proveedor or "").strip()
            if familias:
                texto = " ".join(filter(None, [linea.familia, linea.descripcion]))
                regla = regla_de_familia(familias, texto, codigo)
                if regla:
                    resultado.setdefault(regla["id"], []).append(linea.id)
            for regla_id in por_codigo.get(codigo, ()):
                resultado.setdefault(regla_id, []).append(linea.id)
        return resultado

    def _comparar_con(self):
        self.ensure_one()
        return self.producto_id or self.producto_elegido_id or self.candidato_ids[:1]

    def _texto_ia_corto(self):
        return ""

    def _tono_ia(self):
        return ""

    @api.depends("producto_id", "producto_elegido_id", "candidato_ids")
    def _compute_comparar(self):
        for linea in self:
            producto = linea._comparar_con()
            linea.comparar_id = producto
            linea.comparar_codigo_barras = producto.barcode or False
            linea.comparar_costo = producto.standard_price
            linea.nuestro_es_parecido = bool(producto) and not linea.producto_id
            texto = producto.display_name if producto else ""
            if linea.nuestro_es_parecido:
                texto = f"¿{texto}?"
            linea.nuestro_ver = " · ".join(t for t in (texto, linea._texto_ia_corto()) if t) or False
            linea.nuestro_tono = linea._tono_ia() or ("parecido" if linea.nuestro_es_parecido else "")

    @api.depends("descripcion", "candidato_ids.name")
    def _compute_ver(self):
        from ..wizard.elegir_mismo import igual_letra

        for linea in self:
            linea.descripcion_ver = igual_letra(linea.descripcion)
            linea.parecidos_ver = "\n".join(igual_letra(p.name) for p in linea.candidato_ids) or False  # uno abajo del otro

    @api.depends("datos")
    def _compute_calculo(self):
        for linea in self:
            datos = json.loads(linea.datos) if linea.datos else {}
            linea.precio_lista = datos.get("precio_lista") or datos.get("costo") or False
            linea.calculo = datos.get("calculo") or False
            linea.familia = datos.get("familia") or False
            try:
                linea.cantidad_mayor = float(str(datos.get("cantidad_mayor") or 0).replace(",", "."))
            except ValueError:
                linea.cantidad_mayor = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Las filas de una importación las crea el sistema al simular."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if set(vals) - CAMPOS_DE_USUARIO:
                raise AccessError(_("De una fila solo se puede cambiar la decisión y el producto elegido."))
            self.importacion_id._exigir_vigente()
        return super().write(vals)

    def unlink(self):
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Las filas de una importación no se borran: son el registro de lo hecho."))
        return super().unlink()

    @api.depends("variacion", "costo_anterior", "costo", "accion", "producto_id.comercio_costo_manual")
    def _compute_cambio(self):
        """«▲ +5 %» (sube, en rojo), «▼ −5 %» (baja, en verde) o «=» (igual); con «· costo manual»
        si la lista no va a cambiar el costo del producto (21/10)."""
        def porcentaje(valor):
            texto = f"{valor:.0f}" if abs(valor - round(valor)) < 0.05 else f"{valor:.1f}"
            return texto.replace(".", ",")

        for linea in self:
            if not linea.costo_anterior or linea.accion == motor.BAJA:
                linea.cambio = False
            elif linea.variacion > 0.005:
                linea.cambio = f"▲ +{porcentaje(linea.variacion)} %"
            elif linea.variacion < -0.005:
                linea.cambio = f"▼ −{porcentaje(-linea.variacion)} %"
            else:
                linea.cambio = "="
            if linea.producto_id.comercio_costo_manual and linea.accion != motor.BAJA:
                linea.cambio = " · ".join(filter(None, [linea.cambio, _("costo manual")]))

    @api.depends("costo", "cambio", "accion", "costo_mayor", "cantidad_mayor")
    def _compute_columnas_cortas(self):
        """Columnas de la lista (06/11): «Costo» = costo nuevo y cambio juntos («72.633,00 ▲ +5,2 %»);
        «Por mayor» = precio y cantidad desde la que vale («7.780,00 ×12»)."""
        for linea in self:
            costo = formatLang(self.env, linea.costo) if linea.costo and linea.accion != motor.BAJA else ""
            linea.costo_ver = " ".join(t for t in (costo, linea.cambio or "") if t) or False
            if linea.costo_mayor:
                desde = f" ×{linea.cantidad_mayor:g}".replace(".", ",") if linea.cantidad_mayor else ""
                linea.mayor_ver = formatLang(self.env, linea.costo_mayor) + desde
            else:
                linea.mayor_ver = False

    @api.depends("producto_id.categ_id", "categoria_id")
    def _compute_categoria_mostrada(self):
        for linea in self:
            linea.categoria_mostrada_id = linea.producto_id.categ_id if linea.producto_id else linea.categoria_id

    def _inverse_categoria_mostrada(self):
        nuestros = self.filtered("producto_id")
        if nuestros:
            nuestros.importacion_id._exigir_vigente()
        for linea in nuestros:
            if linea.categoria_mostrada_id and linea.producto_id.categ_id != linea.categoria_mostrada_id:
                # El grupo «Costos y precios» no administra productos: solo la categoría, desde acá
                linea.producto_id.sudo().categ_id = linea.categoria_mostrada_id
        for linea in self - nuestros:
            linea.categoria_id = linea.categoria_mostrada_id

    def _compute_de_lista_vigente(self):
        vigentes = set(self._importaciones_vigentes().ids)
        for linea in self:
            linea.de_lista_vigente = linea.importacion_id.id in vigentes

    def _importaciones_vigentes(self):
        Importacion = self.env["comercio.lista.importacion"]
        vigentes = Importacion
        for lista in self.env["comercio.lista.proveedor"].search([]):
            vigentes |= Importacion._vigente_de(lista)
        return vigentes

    def _search_de_lista_vigente(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise UserError(_("Búsqueda no soportada."))
        positivo = (operator == "=") == value
        return [("importacion_id", "in" if positivo else "not in", self._importaciones_vigentes().ids)]

    @api.depends("descripcion")
    def _compute_clave_producto(self):
        for linea in self:
            linea.clave_producto = clave_producto(linea.descripcion) or False

    @api.depends("producto_id.name", "descripcion", "codigo_barras", "clave_producto")
    def _compute_producto_general(self):
        """Nuestro producto; si no lo tenemos, el título del grupo es el de la primera fila (de
        cualquier proveedor) con el mismo código de barras o la misma clave, prefiriendo la que ya
        es nuestra. Así todos los proveedores de un mismo artículo quedan juntos."""
        def con_barras(linea):
            codigo = (linea.codigo_barras or "").strip()
            return codigo if codigo.isdigit() and len(codigo) >= 8 else None

        def titulo(linea):
            return linea.producto_id.name or " ".join((linea.descripcion or "").split()).upper()

        Linea = self.sudo()
        sin_producto = self.filtered(lambda li: not li.producto_id)
        codigos = {c for c in map(con_barras, sin_producto) if c}
        claves = {li.clave_producto for li in sin_producto if li.clave_producto}
        por_barras: dict[str, str] = {}
        por_clave: dict[str, str] = {}
        if codigos:
            for otra in Linea.search([("codigo_barras", "in", list(codigos))]).sorted(
                    lambda li: (not li.producto_id, li.id)):
                por_barras.setdefault(otra.codigo_barras.strip(), titulo(otra))
        if claves:
            for otra in Linea.search([("clave_producto", "in", list(claves))]).sorted(
                    lambda li: (not li.producto_id, li.id)):
                por_clave.setdefault(otra.clave_producto, titulo(otra))
        for linea in self:
            codigo = con_barras(linea)
            if linea.producto_id:
                linea.producto_general = linea.producto_id.name
            elif codigo and codigo in por_barras:
                linea.producto_general = por_barras[codigo]
            elif linea.clave_producto:
                linea.producto_general = por_clave.get(linea.clave_producto) or titulo(linea)
            else:
                linea.producto_general = linea.codigo_proveedor or _("Sin descripción")

    @api.depends("descripcion", "codigo_proveedor", "codigo_barras", "producto_id.name",
                 "producto_id.barcode", "producto_id.default_code")
    def _compute_texto_busqueda(self):
        # También el código de barras y la referencia de nuestro producto (p. ej. el propio
        # 20…, que la lista del proveedor no trae)
        for linea in self:
            producto = linea.producto_id
            linea.texto_busqueda = normalizar(linea.descripcion, linea.codigo_proveedor, linea.codigo_barras,
                                              producto.name or "", producto.barcode or "",
                                              producto.default_code or "")

    def _compute_buscar(self):
        self.buscar = False

    def _search_buscar(self, operator, value):
        """«Buscar producto»: cada palabra (por su comienzo) y cada número (entero), en cualquier orden."""
        if operator not in ("ilike", "like", "=", "=like", "=ilike") or not value:
            return Domain.TRUE
        return Domain.AND([Domain("texto_busqueda", "ilike", patron) for patron in terminos(value)]
                          or [Domain.TRUE])

    @api.depends("costo", "accion")
    def _compute_sin_costo(self):
        for linea in self:
            linea.sin_costo = linea.costo <= 0 and linea.accion != motor.BAJA

    @api.depends("producto_id.uom_id")
    def _compute_unidades_posibles(self):
        """Las que se convierten a la unidad del producto (mismo árbol: kg, g, «Caja = 2,5 kg»…)."""
        Unidad = self.env["uom.uom"]
        for linea in self:
            uom = linea.producto_id.uom_id
            raiz = (uom.parent_path or "").split("/")[0]
            linea.unidades_posibles_ids = Unidad.search([("parent_path", "=like", f"{raiz}/%")]) if raiz else uom

    @api.depends("accion", "producto_id", "producto_id.active")
    def _compute_registrado(self):
        # Un producto quitado (archivado) cuenta como «No los tenemos»: «Agregar» lo reactiva
        for linea in self:
            linea.registrado = (bool(linea.producto_id) or linea.accion in ACCIONES_REGISTRADAS) and (
                not linea.producto_id or linea.producto_id.active)

    @api.depends("estado")
    def _compute_estado_orden(self):
        orden = {"pendiente": 0, "error": 1, "aplicada": 2, "ignorada": 3, "sin_cambios": 4}
        for linea in self:
            linea.estado_orden = orden.get(linea.estado, 5)

    def _calcular_mas_barato(self):
        """Si otro proveedor vigente tiene el producto más barato, se muestra (Odoo le compra a ese)."""
        hoy = fields.Date.context_today(self)
        for linea in self.filtered(lambda li: li.producto_id):
            vigentes = linea.producto_id.seller_ids.filtered(
                lambda s: (not s.date_end or s.date_end >= hoy) and not s.comercio_escala_de_id)
            mejor = vigentes.sorted(lambda s: (s.price_discounted, s.sequence))[:1]
            if mejor and mejor.partner_id != linea.partner_id:
                linea.sudo().write({"mas_barato_id": mejor.partner_id.id,
                                    "mas_barato_precio": mejor.price_discounted})
            else:
                linea.sudo().write({"mas_barato_id": False, "mas_barato_precio": 0.0})

    # Botones de la pantalla de revisión: deciden y aplican en el momento. Sirven para una
    # fila o para varias seleccionadas (Acciones), con un solo recálculo por importación.
    def _aplicar_por_importacion(self):
        resultado = True
        for importacion in self.importacion_id:
            resultado = importacion._aplicar_o_encolar(self.filtered(lambda li: li.importacion_id == importacion))
        return resultado if isinstance(resultado, dict) else True

    def action_es_el_mismo(self):
        # Un «nuevo» también, si alguien (o la IA) encontró que ya lo tenemos con otro nombre
        lineas = self.filtered(lambda li: li.estado == "pendiente" and (
            li.accion == motor.POSIBLE_DUPLICADO or (li.accion == motor.NUEVO and li.producto_elegido_id)))
        for linea in lineas:
            if not linea.producto_elegido_id:
                if len(linea.candidato_ids) == 1 or (len(self) > 1 and linea.candidato_ids):
                    linea.producto_elegido_id = linea.candidato_ids[:1]
                elif len(self) == 1 and linea.candidato_ids:
                    # Varios parecidos: elegir cuál en una ventanita, con los nombres escritos igual
                    return {"type": "ir.actions.act_window", "name": _("¿Cuál es?"),
                            "res_model": "comercio.elegir.mismo.wizard", "view_mode": "form", "target": "new",
                            "res_id": self.env["comercio.elegir.mismo.wizard"].create({"linea_id": linea.id}).id}
                else:
                    raise UserError(_("Elegí en «Es el mismo que» cuál de los productos es (fila %s).",
                                      linea.fila))
        lineas.write({"decision": "es_el_mismo"})
        return lineas._aplicar_por_importacion()

    def action_es_nuevo(self):
        lineas = self.filtered(lambda li: li.estado == "pendiente" and li.accion == motor.POSIBLE_DUPLICADO)
        lineas.write({"decision": "es_nuevo"})
        return lineas._aplicar_por_importacion()

    def action_aplicar(self):
        self._reactivar_productos()
        lineas = self.filtered(lambda li: li.estado == "pendiente" and (li.accion in (
            motor.NUEVO, motor.VINCULAR, VUELVE, motor.ACTUALIZAR, motor.BAJA) or (
            li.unidad_compra_id and li.producto_id)))  # «a revisar» por la unidad, ya elegida
        lineas.write({"decision": "aplicar"})
        return lineas._aplicar_por_importacion()

    def action_abrir_agregar(self):
        """«Agregar a nuestro catálogo» (Buscar producto): una fila «nuevo» se agrega directo; si no,
        una ventanita pregunta cómo (un solo producto, uno por fila o el mismo que el parecido)."""
        lineas = self.filtered(lambda li: li.importacion_vigente)
        if not lineas:
            raise UserError(_("Marcá las filas que querés agregar."))
        if len(lineas) == 1 and not lineas.candidato_ids:
            return lineas.action_aplicar()
        asistente = self.env["comercio.agregar.catalogo.wizard"].create({"linea_ids": [(6, 0, lineas.ids)]})
        return {"type": "ir.actions.act_window", "name": _("Agregar a nuestro catálogo"),
                "res_model": asistente._name, "res_id": asistente.id, "view_mode": "form", "target": "new"}

    def action_agregar_como_uno(self):
        """«Agregar como un solo producto» (Buscar producto, 02/11): las filas marcadas, de varios
        proveedores, son el mismo producto. Se crea uno solo (con la primera fila que no tenemos;
        si alguna ya es nuestra, se usa esa) y se le suman los demás proveedores con su código y su
        precio. Odoo después le compra al más barato."""
        lineas = self.filtered(lambda li: li.importacion_vigente)
        if len(lineas) < 2:
            raise UserError(_("Marcá dos o más filas (de distintos proveedores) que sean el mismo producto."))
        nuestros = lineas.producto_id.filtered("active")
        if len(nuestros) > 1:
            raise UserError(_("Las filas marcadas ya son de productos distintos nuestros (%s): acá no se "
                              "pueden unir. Para juntar productos repetidos está «Fusionar».",
                              ", ".join(nuestros.mapped("display_name"))))
        if nuestros:
            producto, principal = nuestros, lineas.browse()
        else:
            principal = lineas.filtered(lambda li: li.estado == "pendiente" and li.accion == motor.NUEVO)[:1]
            if not principal:
                raise UserError(_("Ninguna de las filas marcadas se puede agregar como producto nuevo."))
            principal.with_context(comercio_no_avisar=lineas.ids).action_aplicar()
            producto = principal.producto_id
            if not producto:
                raise UserError(_("No se pudo agregar «%s»: mirá el aviso de esa fila.",
                                  principal.descripcion))
        resto = (lineas - principal).filtered(
            lambda li: li.estado == "pendiente" and li.producto_id != producto
            and li.accion in (motor.NUEVO, motor.POSIBLE_DUPLICADO))
        resto.write({"producto_elegido_id": producto.id})
        resto.action_es_el_mismo()
        unidas = (lineas - principal).filtered(lambda li: li.producto_id == producto) | principal
        faltan = lineas - unidas
        mensaje = _("«%(p)s» con %(n)s proveedor(es): %(prov)s.", p=producto.display_name, n=len(unidas),
                    prov=", ".join(unidas.partner_id.mapped("name")))
        if faltan:
            mensaje += " " + _("No se pudieron sumar: %s (mirá su aviso).",
                               ", ".join(faltan.mapped("descripcion")))
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Agregado como un solo producto"), "message": mensaje,
            "type": "warning" if faltan else "success",
            "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def _reactivar_productos(self):
        """«Agregar» sobre un producto que se había quitado: vuelve el mismo (con su historial),
        no se crea otro."""
        archivados = self.producto_id.filtered(lambda p: not p.active)
        if archivados:
            self.importacion_id._exigir_vigente()
            vals = {"active": True}
            if "available_in_pos" in archivados._fields:
                vals["available_in_pos"] = True
            archivados.sudo().write(vals)

    def action_quitar_del_catalogo(self):
        """Quita de nuestro catálogo los productos de las filas marcadas: se archivan, no se
        borran (queda su historial de costos y ventas). Dejan de verse en la caja y en Compras;
        en las listas pasan a «No los tenemos» y «Agregar» los vuelve a poner."""
        productos = self.producto_id.filtered("active")
        if not productos:
            raise UserError(_("Las filas marcadas no son de productos de nuestro catálogo."))
        self.importacion_id._exigir_vigente()
        # Primero fuera del POS: con una caja o puesto abierto Odoo no deja archivar un
        # producto disponible en el POS (ver action_deshacer).
        if "available_in_pos" in productos._fields:
            productos.sudo().write({"available_in_pos": False})
        productos.sudo().write({"active": False})
        return True

    def action_deshacer(self):
        """Vuelve atrás filas aplicadas: producto nuevo → se borra (o se archiva si ya se usó);
        proveedor agregado → se quita; cambio de costo → vuelve el precio anterior; baja →
        se reabre el precio. No se deshace si después llegó otra lista que cambió lo mismo.
        Filas ignoradas: vuelven a quedar para decidir (ignorar no había cambiado nada)."""
        ignoradas = self.filtered(lambda li: li.estado == "ignorada")
        lineas = self.filtered(lambda li: li.estado == "aplicada" and li.deshacer_datos)
        # Solo la vigente: deshacer una vieja volvería atrás (o dejaría desactualizada) la más nueva
        (lineas | ignoradas).importacion_id._exigir_vigente()
        for importacion in lineas.importacion_id:  # resguardo aparte de la regla de «vigente»
            if importacion.search_count([("lista_id", "=", importacion.lista_id.id), ("id", ">", importacion.id),
                                         ("cant_aplicadas", ">", 0)]):
                raise UserError(_("Después se aplicó una lista más nueva de este proveedor: deshacer esta "
                                  "volvería atrás cambios posteriores. Deshacé primero la más nueva."))
        Info = self.env["product.supplierinfo"].sudo()
        tocados = lineas.producto_id
        for linea in lineas.sorted("fila", reverse=True):
            datos = json.loads(linea.deshacer_datos)
            creado = Info.browse(datos.get("borrar_prov")).exists()
            if creado and creado.date_end:
                raise UserError(_("Fila %s: ese precio ya lo cambió otra lista; no se puede deshacer.", linea.fila))
            if creado:
                creado.unlink()
            if datos.get("reabrir_prov"):
                Info.browse(datos["reabrir_prov"]).exists().write({"date_end": False})
            if datos.get("restaurar_inicio"):
                id_, inicio = datos["restaurar_inicio"]
                Info.browse(id_).exists().write({"date_start": inicio})
            if datos.get("restaurar_prov"):
                id_, valores = datos["restaurar_prov"]
                valores = {k: v for k, v in valores.items() if k in CAMPOS_RESTAURABLES}
                Info.browse(id_).exists().write(valores)
            if datos.get("quitar_barcode"):
                self.env["product.template"].sudo().browse(datos["quitar_barcode"]).exists().write({"barcode": False})
            if datos.get("restaurar_barcode"):  # vuelve el código propio y se borra el alternativo
                tmpl_id, propio, alternativo = datos["restaurar_barcode"]
                self.env["product.uom"].sudo().browse(alternativo).exists().unlink()
                self.env["product.template"].sudo().browse(tmpl_id).exists().write({"barcode": propio})
            if datos.get("producto") and datos["producto"] == linea.producto_id.id:
                producto = self.env["product.template"].sudo().browse(datos["producto"]).exists()
                # Primero fuera del POS: con una caja o puesto abierto Odoo no deja borrar ni
                # archivar un producto disponible en el POS (encontrado el 19/10).
                producto.write({"available_in_pos": False})
                try:
                    with self.env.cr.savepoint():
                        producto.unlink()
                except Exception:  # noqa: BLE001 — ya se usó (ventas, stock): se archiva
                    producto.write({"active": False})
            linea.sudo().write({
                "estado": "pendiente", "decision": "pendiente", "deshacer_datos": False, "aplicada_por": False,
                "producto_id": False if datos.get("producto") or linea.accion not in ACCIONES_REGISTRADAS
                else linea.producto_id.id,
                "avisos": ((linea.avisos or "") + _("\nDeshecha por %s.", self.env.user.name)).strip(),
            })
        tocados.exists()._comercio_actualizar_costo()  # el costo sale de los precios que quedaron
        # Ignorar no cambió nada en los productos: deshacerlo solo vuelve a dejar la fila para decidir
        ignoradas.sudo().write({"estado": "pendiente", "decision": "pendiente"})
        for importacion in (lineas | ignoradas).importacion_id:
            if importacion.estado != "reemplazada":  # una reemplazada sigue sin poder aplicarse
                importacion.sudo().estado = "simulada"
            importacion.message_post(body=_("Deshechas %(n)s filas por %(u)s.",
                                            n=len((lineas | ignoradas).filtered(
                                                lambda li: li.importacion_id == importacion)),
                                            u=self.env.user.name))
        return True

    def _corregir(self, descripcion=None, precio=None, sin_codigo_barras=False):
        """Corrige a mano una fila que la lista trajo mal (sin precio, precio 0, mal copiada) y
        la vuelve a simular. El precio es el de la LISTA: pasa al costo con los descuentos, el
        IVA y el dólar de la lista, como las demás filas."""
        self.ensure_one()
        importacion = self.importacion_id
        importacion._exigir_vigente()
        if self.estado != "pendiente":
            raise UserError(_("Solo se corrigen filas pendientes (esta está «%s»).",
                              dict(self._fields["estado"].selection).get(self.estado)))
        datos = json.loads(self.datos or "{}")
        if descripcion and descripcion.strip():
            datos["descripcion_proveedor"] = descripcion.strip()
        if precio:
            if precio <= 0:
                raise UserError(_("El precio tiene que ser mayor que 0."))
            ajustes = normalizar_ajustes(importacion.lista_id.mapeo()["ajustes"])
            costo, calculo = costo_desde_lista(
                precio, de_la_fila(ajustes, datos.get("moneda_fila")), datos.get("descuento_fila", ""), datos.get("iva_fila", ""),
                datos.get("descripcion_proveedor") or "", datos.get("codigo_proveedor") or "",
                datos.get("promocion", ""))
            datos.update({"precio_lista": f"{precio:.4f}", "costo": f"{costo:.4f}",
                          "calculo": calculo + _(" (precio corregido a mano)")})
        if sin_codigo_barras:  # el de la lista es de otro producto: se carga sin él
            datos["codigo_barras"] = ""
        datos["corregida_a_mano"] = True
        self.sudo().datos = json.dumps(datos)
        importacion._replanificar(self)
        return True

    def action_corregir(self):
        """Abre la ventana para corregir la fila."""
        self.ensure_one()
        datos = json.loads(self.datos or "{}")
        # El precio que trae la fila, si trae uno (p. ej. un código repetido): se muestra para no
        # tener que volver a escribirlo. «SIN STOCK» o «Consultar» quedan en «La lista dice».
        try:
            precio = motor._numero(datos.get("precio_lista") or datos.get("costo") or "")
        except ValueError:
            precio = 0.0
        return {
            "type": "ir.actions.act_window",
            "name": _("Corregir la fila"),
            "res_model": "comercio.corregir.fila.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_linea_id": self.id, "default_descripcion": self.descripcion,
                        "default_original": datos.get("precio_original") or datos.get("precio_lista") or "",
                        "default_precio": precio, "default_precio_antes": precio},
        }

    def action_ver_detalle(self):
        """Detalle de la fila (06/11): el cálculo completo, a qué se parece, lo que dijo la IA y los
        mismos botones de la lista, en una ventana. La lista queda con pocas columnas legibles."""
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "views": [(self.env.ref("comercio_catalogo.importacion_linea_form").id, "form")],
                "target": "new", "name": self.descripcion or "Fila de la lista"}

    def action_ignorar(self):
        """No aplicar la fila: el producto y el precio quedan como estaban. Se puede deshacer."""
        lineas = self.filtered(lambda li: li.estado == "pendiente")
        lineas.importacion_id._exigir_vigente()
        lineas.sudo().write({"decision": "ignorar", "estado": "ignorada"})
        for importacion in lineas.importacion_id:
            if importacion.estado == "simulada" and importacion._revisada():
                importacion.sudo().estado = "aplicada"  # no queda nada nuestro para decidir
        return True
