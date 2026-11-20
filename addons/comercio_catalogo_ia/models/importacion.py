import json
import logging
import os
import socket
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.addons.comercio_catalogo.catalogo import plan as motor
from odoo.addons.comercio_catalogo.catalogo import similitud
from odoo.addons.comercio_catalogo.catalogo.codigos import FABRICANTE, normalizar, numero_de_codigo_propio
from odoo.exceptions import UserError

from ..ia import problemas
from ..ia import verificar as ia

_logger = logging.getLogger(__name__)

# Con esta confianza o más, «es el mismo» se deja elegido en «Es el mismo que» (igual hay
# que confirmarlo).
CONFIANZA_PARA_PRESELECCIONAR = 0.8
# La IA une sola (ADR 0034, 06/11) solo con esta confianza o más, a un producto que ya está en el
# catálogo y si el costo no salta más que el tope de la lista. Nunca agrega productos.
CONFIANZA_PARA_UNIR = 0.9
# Para «producto nuevo»: parecidos desde este puntaje (el motor usa 0,50) se le muestran a la IA
UMBRAL_AMPLIO = 0.35
# Filas por clic (de a 20 por pedido a Gemini): más tardaría demasiado para una sola pantalla
MAXIMO_POR_VEZ = 200


def _configuracion():
    """La clave y los modelos vienen del entorno del servidor (compose), no de la base: así no
    viajan en los backups ni los ve nadie desde Odoo."""
    clave = os.environ.get("GEMINI_API_KEY", "")
    modelos = [os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
               os.environ.get("GEMINI_MODEL_RESPALDO", "")]
    return clave, modelos


class ComercioListaImportacionLinea(models.Model):
    _inherit = "comercio.lista.importacion.linea"

    ia_veredicto = fields.Selection(
        [(ia.MISMO, "Es el mismo"), (ia.DISTINTO, "Es otro"), (ia.DUDOSO, "Dudoso")],
        "Sugerencia IA", readonly=True,
        help="Segunda opinión de la IA. Es solo una sugerencia: hay que confirmarla.")
    ia_producto_id = fields.Many2one("product.template", "IA: es el mismo que", readonly=True)
    ia_confianza = fields.Float("Confianza IA", readonly=True, digits=(3, 2))
    ia_motivo = fields.Char("Motivo IA", readonly=True)
    unida_por_ia = fields.Boolean("Unida por la IA", readonly=True, copy=False,
                                  help="La IA la unió sola a un producto que ya teníamos (confianza alta y "
                                       "costo parecido). Se puede deshacer como cualquier fila.")

    # «Nuestro producto» (columna para comparar): si la fila no está unida, el que propone la IA va
    # primero; al lado, en corto, lo que dijo. El motivo y la confianza, en la lupa.
    def _comparar_con(self):
        self.ensure_one()
        return self.producto_id or self.producto_elegido_id or self.ia_producto_id or self.candidato_ids[:1]

    def _texto_ia_corto(self):
        return {ia.MISMO: "IA: es el mismo", ia.DISTINTO: "IA: es otro",
                ia.DUDOSO: "IA: duda"}.get(self.ia_veredicto, "")

    def _tono_ia(self):
        return {ia.MISMO: "ia_mismo", ia.DISTINTO: "ia_otro", ia.DUDOSO: "ia_duda"}.get(self.ia_veredicto, "")

    @api.depends("producto_id", "producto_elegido_id", "candidato_ids", "ia_producto_id", "ia_veredicto")
    def _compute_comparar(self):
        return super()._compute_comparar()

    def _tipo_ia(self):
        """Qué se le pregunta a la IA sobre la fila:
        - «duplicado»: posible duplicado pendiente (¿es alguno de los parecidos?);
        - «nuevo»: el programa no encontró nada parecido (¿seguro que no lo tenemos?);
        - «vinculo»: ya está unida a un producto nuestro (¿es de verdad el mismo?)."""
        self.ensure_one()
        if self.accion == motor.POSIBLE_DUPLICADO and self.estado == "pendiente":
            return "duplicado"
        if self.accion == motor.NUEVO and self.estado == "pendiente":
            return "nuevo"
        if self.producto_id and self.estado != "ignorada":
            return "vinculo"
        return False

    def _buscador_amplio(self):
        """Nuestros productos (nombre y cómo los describe cada proveedor), con un umbral más bajo
        que el del motor: para «nuevo», lo que el programa descartó igual se le muestra a la IA."""
        buscador = similitud.Buscador(similitud.Configuracion(umbral_candidato=UMBRAL_AMPLIO))
        for producto in self.env["product.template"].search_read([], ["name"]):
            buscador.agregar(producto["id"], producto["name"])
        for precio in self.env["product.supplierinfo"].search_read(
                [("product_name", "!=", False), ("product_tmpl_id.active", "=", True)],
                ["product_tmpl_id", "product_name"]):
            buscador.agregar(precio["product_tmpl_id"][0], precio["product_name"])
        return buscador

    def _candidatos_ia(self, buscador=None):
        tipo = self._tipo_ia()
        if tipo == "duplicado":
            return self.candidato_ids[:3]
        if tipo == "vinculo":
            return self.producto_id
        texto = self.descripcion or ""
        ids = [c.id for c in buscador.candidatos(texto)] if buscador and texto else []
        return self.env["product.template"].browse(ids[:3])

    def _filas_para_ia(self, buscador=None):
        filas = []
        # Con los archivados: el motor también los propone (un producto archivado puede volver)
        for linea in self.with_context(active_test=False):
            datos = json.loads(linea.datos or "{}")
            candidatos = []
            for producto in linea._candidatos_ia(buscador):
                otras = producto.seller_ids.filtered(
                    lambda s, p=linea.partner_id: s.product_name and s.partner_id != p)
                candidatos.append({"id": producto.id, "nombre": producto.name,
                                   "otras_descripciones": list(dict.fromkeys(otras.mapped("product_name")))})
            filas.append({"fila": linea.id, "descripcion": linea.descripcion or datos.get("descripcion_proveedor", ""),
                          "codigo": linea.codigo_proveedor, "unidad": datos.get("unidad", ""),
                          "candidatos": candidatos})
        return filas

    def _ia_no_aplica(self):
        """Explica por qué la IA no sirve para las filas elegidas."""
        problema = self.filtered(lambda li: li.accion == motor.REVISAR)[:1]
        if problema:
            raise UserError(_(
                "«%(d)s»: %(p)s.\n\nLa IA no arregla filas de la lista: compara un producto del proveedor "
                "con los nuestros para decir si ya lo tenemos. Esta fila se resuelve en la lista del "
                "proveedor (o preguntándole).", d=problema.descripcion, p=problema.detalle))
        raise UserError(_(
            "La IA ayuda a decidir si un producto de la lista ya lo tenemos. Elegí filas «Producto nuevo» o "
            "«Posible duplicado» pendientes, o filas que ya son nuestras (para confirmar que están bien "
            "unidas)."))

    def action_verificar_ia(self):
        """Opinión de la IA sobre las filas elegidas: posibles duplicados, productos nuevos (¿ya
        lo tenemos con otro nombre?) y filas ya unidas a un producto nuestro (¿es el mismo?)."""
        lineas = self.filtered(lambda li: li._tipo_ia())
        if not lineas:
            self._ia_no_aplica()
        if len(lineas) > MAXIMO_POR_VEZ:
            raise UserError(_("Son %(n)s filas: la IA revisa hasta %(m)s por vez. Elegí menos (o usá "
                              "los botones de la importación, que van de a %(m)s).", n=len(lineas),
                              m=MAXIMO_POR_VEZ))
        lineas.importacion_id._exigir_vigente()
        clave, modelos = _configuracion()
        if not clave:
            raise UserError(_("Falta la clave de la IA (GEMINI_API_KEY) en el servidor."))
        nuevos = lineas.filtered(lambda li: li._tipo_ia() == "nuevo")
        buscador = nuevos._buscador_amplio() if nuevos else None
        filas = lineas._filas_para_ia(buscador)
        # Un «nuevo» sin nada parecido entre lo nuestro no hace falta preguntarlo
        sin_parecidos = {f["fila"] for f in filas if not f["candidatos"]}
        resultados, consumo = [], ia.Consumo()
        a_consultar = [f for f in filas if f["fila"] not in sin_parecidos]
        if a_consultar:
            try:
                resultados, consumo = ia.verificar(a_consultar, clave, modelos)
            except ia.ErrorIA as error:
                raise UserError(_("No se pudo consultar a la IA: %s", error)) from error
        resultados += [ia.Resultado(f, ia.DISTINTO, None, 1.0, _("Nada parecido entre nuestros productos."))
                       for f in sin_parecidos]
        por_id = {r.fila: r for r in resultados}
        for linea in lineas:
            r = por_id[linea.id]
            linea.sudo().write({"ia_veredicto": r.veredicto, "ia_producto_id": r.candidato_id or False,
                                "ia_confianza": r.confianza, "ia_motivo": r.motivo})
            if (linea._tipo_ia() in ("duplicado", "nuevo") and r.veredicto == ia.MISMO
                    and r.confianza >= CONFIANZA_PARA_PRESELECCIONAR and not linea.producto_elegido_id):
                linea.producto_elegido_id = r.candidato_id
        # Lo que la IA confirma con seguridad se une solo (ADR 0034): solo a productos que ya tenemos
        unidas = lineas.filtered(lambda li: li._ia_puede_unir())
        if unidas:
            unidas._unir_por_ia()
        conteo = {v: len([r for r in resultados if r.veredicto == v]) for v in (ia.MISMO, ia.DISTINTO, ia.DUDOSO)}
        vinculos = lineas.filtered(lambda li: li._tipo_ia() == "vinculo")
        alertas = len(vinculos.filtered(lambda li: li.ia_veredicto != ia.MISMO))
        for importacion in lineas.importacion_id:
            importacion.message_post(body=_(
                "Verificación con IA (%(modelo)s) de %(n)s filas: %(m)s el mismo, %(d)s otro, %(u)s dudosas; "
                "%(a)s de lo nuestro a revisar; %(s)s unidas solas. Consumo: %(p)s pedidos, %(t)s tokens.",
                modelo=consumo.modelo or "-", n=len(lineas), m=conteo[ia.MISMO], d=conteo[ia.DISTINTO],
                u=conteo[ia.DUDOSO], a=alertas, s=len(unidas.filtered(lambda li: li.importacion_id == importacion)),
                p=consumo.pedidos, t=consumo.tokens))
        _logger.info("IA: %s filas, %s pedidos, %s tokens (%s)", len(lineas), consumo.pedidos, consumo.tokens,
                     consumo.modelo)
        mensaje = _("%(m)s el mismo, %(d)s otro, %(u)s dudosas.", m=conteo[ia.MISMO], d=conteo[ia.DISTINTO],
                    u=conteo[ia.DUDOSO])
        if unidas:
            mensaje += " " + _("%s se unieron solas a productos que ya teníamos (filtro «Unidas por la IA»).",
                               len(unidas))
        if vinculos:
            mensaje += " " + _("De lo que ya teníamos unido, la IA duda de %s (filtro «La IA duda»).", alertas)
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Verificación con IA"), "message": mensaje,
            "type": "warning" if alertas else "info", "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def _sugerir_problemas_ia(self):
        """Filas con problema («a revisar»): la IA explica qué pasó y qué hacer (en «Motivo IA»)."""
        lineas = self.filtered(lambda li: li.accion == motor.REVISAR and li.estado == "pendiente")
        if not lineas:
            raise UserError(_("No hay filas con problemas pendientes."))
        clave, modelos = _configuracion()
        filas = []
        for linea in lineas[:MAXIMO_POR_VEZ]:
            datos = json.loads(linea.datos or "{}")
            filas.append({"fila": linea.id, "descripcion": linea.descripcion or datos.get("descripcion_proveedor", ""),
                          "codigo": linea.codigo_proveedor, "problema": linea.detalle or "",
                          # Solo un texto («SIN STOCK», «Consultar»), nunca un precio (ADR 0018)
                          "texto_precio": datos.get("precio_original") if not any(
                              ch.isdigit() for ch in str(datos.get("precio_original") or "")) else ""})
        try:
            sugerencias, consumo = problemas.sugerir(filas, clave, modelos)
        except ia.ErrorIA as error:
            raise UserError(_("No se pudo consultar a la IA: %s", error)) from error
        por_id = {s.fila: s for s in sugerencias}
        for linea in lineas[:MAXIMO_POR_VEZ]:
            s = por_id[linea.id]
            linea.sudo().write({"ia_veredicto": False, "ia_producto_id": False, "ia_confianza": 0,
                                "ia_motivo": f"{problemas.QUE_HACER[s.accion]}: {s.explicacion}"})
        _logger.info("IA: %s filas con problemas, %s pedidos, %s tokens", len(filas), consumo.pedidos, consumo.tokens)
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Filas con problemas"), "type": "info",
            "message": _("La IA sugirió qué hacer con %s filas: está en la columna «Motivo IA». Para cargar el "
                         "precio o arreglar la descripción, «Corregir» en la fila.", len(filas)),
            "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def action_abrir_verificar_ia(self):
        """El único botón de IA de las listas: abre «¿Qué querés revisar con la IA?»."""
        return self.env["comercio.verificar.ia.wizard"]._abrir(lineas=self)

    def _ia_puede_unir(self):
        """¿La IA puede unir sola esta fila? Pendiente, «es el mismo» con confianza alta, a un producto
        que ya está en el catálogo, y el costo de la lista no salta más que el tope de la ficha (un salto
        grande suele ser otra presentación: unidad contra caja)."""
        self.ensure_one()
        if (self.estado != "pendiente" or self._tipo_ia() not in ("duplicado", "nuevo")
                or self.ia_veredicto != ia.MISMO or not self.ia_producto_id
                or self.ia_confianza < CONFIANZA_PARA_UNIR or not self.importacion_vigente
                or self.importacion_id.leida_con_ia):  # lista leída de una foto: nada se aplica solo
            return False
        # 20/11 (Rho): la IA unió guantes de cuatro marcas a un mismo guante genérico. Si otra fila
        # de esta lista también dice ser ese producto, no es «seguro»: lo decide una persona.
        if self.importacion_id.linea_ids.filtered(
                lambda li: li != self and li.ia_veredicto == ia.MISMO
                and li.ia_producto_id == self.ia_producto_id and li.estado in ("pendiente", "aplicada")):
            return False
        # Ni si la fila trae un código de fábrica y el producto ya tiene otro de fábrica
        codigo, tipo = normalizar(self.codigo_barras or "")
        propio = self.ia_producto_id.barcode
        if (tipo == FABRICANTE and propio and propio != codigo
                and not numero_de_codigo_propio(propio)):
            return False
        actual, nuevo = self.ia_producto_id.standard_price, self.costo
        if not actual or not nuevo:
            return False
        tope = (self.importacion_id.lista_id.tope_automatico or 0) / 100
        return abs(nuevo / actual - 1) <= tope

    def _unir_por_ia(self):
        for linea in self:
            linea.producto_elegido_id = linea.ia_producto_id
        self.sudo().write({"decision": "es_el_mismo", "unida_por_ia": True})
        return self._aplicar_por_importacion()

    def action_aceptar_ia(self):
        """Confirma «es el mismo» de la IA en filas pendientes: las une al producto que dijo. Nunca agrega
        productos al catálogo (06/11): «es otro» queda en «No los tenemos» para que una persona decida
        si lo quiere. Las dudosas, sin sugerencia o ya unidas no se tocan."""
        pendientes = self.filtered(lambda li: li._tipo_ia() in ("duplicado", "nuevo"))
        if not pendientes:
            self._ia_no_aplica()
        mismos = pendientes.filtered(lambda li: li.ia_veredicto == ia.MISMO and li.ia_producto_id)
        if not mismos:
            if not pendientes.filtered("ia_veredicto"):
                raise UserError(_("Las filas elegidas todavía no tienen sugerencia de la IA: primero tocá "
                                  "«Revisar con IA»."))
            raise UserError(_("En las filas elegidas la IA no dijo «es el mismo»: lo que es otro producto no se "
                              "agrega solo (decidí con «Agregar como nuevo» si lo querés en el catálogo) y lo "
                              "dudoso se decide a mano (el motivo está en la lupa)."))
        for linea in mismos:
            linea.producto_elegido_id = linea.ia_producto_id
        mismos.write({"decision": "es_el_mismo"})
        return mismos._aplicar_por_importacion()


class ComercioListaImportacion(models.Model):
    _inherit = "comercio.lista.importacion"

    ia_disponible = fields.Boolean(compute="_compute_ia_disponible")

    @api.depends_context("uid")
    def _compute_ia_disponible(self):
        disponible = bool(_configuracion()[0])
        for importacion in self:
            importacion.ia_disponible = disponible

    def _verificar_ia_tipo(self, tipo):
        self.ensure_one()
        lineas = self.linea_ids.filtered(lambda li: not li.ia_veredicto and li._tipo_ia() == tipo)
        if not lineas:
            raise UserError(_("No quedan filas sin verificar."))
        return lineas[:MAXIMO_POR_VEZ].action_verificar_ia()

    def action_verificar_ia(self):
        """Todas las filas «posible duplicado» pendientes de esta lista que no se verificaron."""
        return self._verificar_ia_tipo("duplicado")

    def action_abrir_verificar_ia(self):
        """El único botón de IA de la importación: abre «¿Qué querés revisar con la IA?»."""
        self.ensure_one()
        return self.env["comercio.verificar.ia.wizard"]._abrir(importacion=self)

    def action_verificar_ia_nuestros(self):
        """Lo que el programa ya unió a un producto nuestro (por código o confirmado antes): ¿la
        descripción del proveedor sigue siendo ese producto? De a MAXIMO_POR_VEZ por clic."""
        return self._verificar_ia_tipo("vinculo")

    # ------------------------------------------------------------ revisión al agregar (19/11-20/11)
    def _aplicar(self, lineas, solo_automaticos=False):
        """Antes de agregar productos «nuevos» al catálogo, la IA mira si ya los tenemos con otro
        nombre (pedido del 19/11: revisar a mano lo que no tenemos era demasiado; se revisa solo lo
        que se elige agregar). Lo seguro se une solo (ADR 0034); lo que la IA cree que ya tenemos
        queda sin agregar, con la sugerencia, y un segundo «Agregar» lo agrega igual (ya tiene
        sugerencia: no se vuelve a retener). Lo dudoso se agrega (20/11: retenerlo frenaba muchas
        variantes, p. ej. bulones con otro paso de rosca). Invisible si la IA no está: sin internet,
        sin clave o si falla, se agrega como siempre y sin carteles."""
        a_revisar = lineas.filtered(lambda li: li.estado == "pendiente" and li.accion == motor.NUEVO
                                    and li.decision == "aplicar" and not li.ia_veredicto)
        if not a_revisar or self.env.context.get("sin_revision_ia") or not _configuracion()[0]:
            return super()._aplicar(lineas, solo_automaticos)
        retenidas, unidas = self._revisar_antes_de_agregar(a_revisar)
        resto = lineas.filtered(lambda li: li.estado == "pendiente") - retenidas
        resultado = super()._aplicar(resto, solo_automaticos) if resto else None
        if not (retenidas or unidas):
            return resultado
        partes = []
        if unidas:
            partes.append(_("%s ya los teníamos con otro nombre: se unieron a ese producto (filtro «Unidas por "
                            "la IA»).", len(unidas)))
        if retenidas:
            partes.append(_("%s no se agregaron: la IA cree que ya los tenemos (en amarillo; filtro «Retenidas "
                            "por la IA», con el motivo en «Motivo IA»). Si es el mismo, «Es el mismo»; si no, "
                            "marcarlas y «Agregar» de nuevo.", len(retenidas)))
        self.message_post(body=" ".join(partes))
        if isinstance(resultado, dict) and resultado.get("params", {}).get("message"):
            partes.append(resultado["params"]["message"])  # p. ej. filas que cambiaron desde la simulación
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Revisión con IA antes de agregar"), "message": " ".join(partes),
            "type": "warning" if retenidas else "info", "sticky": bool(retenidas),
            "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def _revisar_antes_de_agregar(self, lineas):
        """Revisa con la IA (de a MAXIMO_POR_VEZ) y devuelve (retenidas, unidas por la IA). Cualquier
        falla queda solo en el log: el alta sigue como si no hubiera IA."""
        vacio = lineas.browse()
        if not _ia_alcanzable():  # sin internet: ni se intenta (los reintentos sumarían segundos)
            _logger.info("IA antes de agregar: sin conexión con Gemini; se agrega sin revisar")
            return vacio, vacio
        for desde in range(0, len(lineas), MAXIMO_POR_VEZ):
            tanda = lineas[desde:desde + MAXIMO_POR_VEZ]
            try:
                with self.env.cr.savepoint():
                    tanda.with_context(sin_revision_ia=True).action_verificar_ia()
            except Exception as error:  # noqa: BLE001 - cupo, corte, respuesta rara: no traba el alta
                _logger.warning("IA antes de agregar: %s; se agrega sin revisar", error)
                break
        retenidas = lineas.filtered(lambda li: li.estado == "pendiente" and li.ia_veredicto == ia.MISMO)
        retenidas.sudo().write({"decision": "pendiente"})
        # Unidas de verdad: si la fila cambió desde la simulación, se volvió a calcular y no se unió
        unidas = lineas.filtered(lambda li: li.unida_por_ia and li.estado == "aplicada")
        return retenidas, unidas


def _ia_alcanzable(espera=3):
    """¿Hay conexión con Gemini? Un intento corto, para no demorar el alta cuando no hay internet."""
    try:
        socket.create_connection((urlparse(ia.URL).hostname, 443), timeout=espera).close()
        return True
    except OSError:
        return False
