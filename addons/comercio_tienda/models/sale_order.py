"""Pedidos de la tienda online en Odoo (ADR 0033): el conector los trae y los crea confirmados."""
from __future__ import annotations

import re

from odoo import api, fields, models

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[^@\s]{2,20}$")
# Diferencia aceptada entre lo cobrado y la lista, por unidad (redondeos del IVA)
TOLERANCIA_PRECIO = 0.5


class SaleOrder(models.Model):
    _inherit = "sale.order"

    comercio_tienda_ref = fields.Char("Pedido de la tienda", copy=False, readonly=True, index=True,
                                      help="Identificador del pedido en la tienda online.")
    comercio_tienda_numero = fields.Char("N.º en la tienda", copy=False, readonly=True)

    comercio_tienda_estado = fields.Selection(
        [("preparando", "Preparando"), ("faltante", "Falta algo"), ("listo", "Listo para retirar"), ("retirado", "Retirado"),
         ("cancelado", "Cancelado"), ("devolucion", "Devolución por recibir")],
        "Estado en la tienda", copy=False, readonly=True, tracking=True)

    _comercio_tienda_ref_unico = models.Constraint("UNIQUE(comercio_tienda_ref)", "Ese pedido de la tienda ya existe en Odoo.")


class ResPartner(models.Model):
    _inherit = "res.partner"

    comercio_tienda_cliente = fields.Boolean("Creado por la tienda online", readonly=True, copy=False, index=True)


class TiendaCambioPedidos(models.Model):
    _inherit = "comercio.tienda.cambio"

    @api.model
    def tienda_crear_pedidos(self, pedidos: list) -> list[dict]:
        """Crea en Odoo los pedidos pagos de la tienda (confirmados: su entrega reserva el stock).
        Idempotente: si el pedido ya existe (mismo id de la tienda) lo devuelve sin crearlo.
        Cada pedido va aislado (savepoint): uno con error vuelve con «error» y no frena a los demás
        (la tienda lo sigue teniendo pendiente y el conector lo reintenta en la vuelta siguiente)."""
        self._verificar_conector()
        SO = self.env["sale.order"].sudo().with_context(lang=self.env.company.partner_id.lang or "es_AR")
        lista = self.env["product.pricelist"].sudo().search([("comercio_tienda_publica", "=", True)], limit=1)
        hechos = []
        for p in (pedidos or [])[:50]:
            ref = str(p.get("id", ""))
            if not re.fullmatch(r"[0-9a-f]{32}", ref):
                continue
            try:
                with self.env.cr.savepoint():
                    orden = SO.search([("comercio_tienda_ref", "=", ref)], limit=1)
                    if not orden:
                        orden = self._tienda_nuevo_pedido(SO, lista, p)
            except Exception as e:  # noqa: BLE001 - se informa y sigue con los demás
                hechos.append({"id": ref, "error": str(e)[:200]})
                continue
            hechos.append({"id": ref, "odoo_id": orden.id, "odoo_nombre": orden.name})
        return hechos

    def _tienda_cliente(self, p: dict):
        """Contacto del cliente. Solo se reusa un contacto que creó la propia tienda con ese mail
        exacto (normalizado, sin comodines); nunca se engancha a otro contacto de Odoo (un
        mayorista, un proveedor, un usuario) ni se le cambia nada a uno que ya existe: el mail del
        formulario no está verificado. La vinculación con un cliente real se hace a mano o con la
        cuenta verificada (fase 6)."""
        Partner = self.env["res.partner"].sudo()
        email = str(p.get("email", "")).strip().lower()[:160]
        if not EMAIL.match(email):
            email = ""
        nombre = re.sub(r"\s+", " ", str(p.get("nombre", ""))).strip()[:120] or "Cliente de la tienda online"
        telefono = re.sub(r"[^0-9 +()-]", "", str(p.get("telefono") or ""))[:30]
        cliente = Partner.browse()
        if email:
            cliente = Partner.search([("comercio_tienda_cliente", "=", True), ("email_normalized", "=", email),
                                      ("user_ids", "=", False), ("is_company", "=", False)], limit=1)
        if not cliente:
            cliente = Partner.create({"name": nombre, "email": email or False, "phone": telefono or False,
                                      "comercio_tienda_cliente": True, "comment": "Cliente de la tienda online"})
        return cliente

    def _tienda_nuevo_pedido(self, SO, lista, p: dict):
        # Pedido mayorista de un cliente aprobado: su contacto (vinculado al aprobarlo) y su lista.
        # Odoo no le cree a ciegas a la tienda: el contacto tiene que ser uno que la tienda dio de
        # alta como mayorista (con la etiqueta) y la lista, la que ese contacto tiene en Odoo.
        cliente, problemas = None, []
        if p.get("sitio") == "mayorista":
            cliente, aviso = self._tienda_mayorista_del_pedido(p)
            if aviso:
                problemas.append(aviso)
        if cliente:
            lista = cliente.property_product_pricelist
        else:
            cliente = self._tienda_cliente(p)
        Producto = self.env["product.product"].sudo().with_context(active_test=False)
        lineas, descartadas, precios_distintos = [], [], []
        for li in (p.get("lineas") or [])[:100]:
            producto = Producto.browse(int(li.get("producto_id") or 0)).exists()
            cantidad = int(li.get("cantidad") or 0)
            if not producto or not 0 < cantidad <= 999:
                descartadas.append(f"{str(li.get('nombre') or li.get('producto_id'))[:80]} × {li.get('cantidad')}")
                continue
            final = int(li.get("precio") or 0) / 100  # lo que pagó el cliente, con IVA y con su lista
            esperados = self._tienda_precios_esperados(lista, producto, cantidad)
            if esperados and all(abs(final - e) > TOLERANCIA_PRECIO for e in esperados):
                precios_distintos.append(f"{producto.display_name[:60]}: cobrado $ {final:,.2f}, "
                                         f"la lista hoy da $ {max(esperados):,.2f}")
            # discount 0: el precio ya trae el descuento de la lista; si no, Odoo 20 lo calcula
            # de la regla de la lista y lo aplica otra vez (revisión del 16/11)
            lineas.append((0, 0, {"product_id": producto.id, "product_uom_qty": cantidad,
                                  "price_unit": self._tienda_sin_iva_si_corresponde(producto, final),
                                  "discount": 0,
                                  "name": producto.get_product_multiline_description_sale()
                                  + ("\n(Consultar disponibilidad)" if li.get("consultar") else "")}))
        numero = f"W-{int(p.get('numero') or 0):04d}"
        orden = SO.create({
            "partner_id": cliente.id,
            "pricelist_id": lista.id or False,
            "comercio_tienda_ref": str(p["id"]),
            "comercio_tienda_numero": numero,
            "client_order_ref": numero,
            "origin": f"Tienda online {numero}",
            "note": f"Pagado por {p.get('pago_medio', '?')} ({p.get('pago_id', '')}) el {str(p.get('pagado', ''))[:19]}. Retira en el local.",
            "order_line": lineas,
        })
        # Control: el total de Odoo tiene que dar lo que se cobró. Si falta una línea o no da
        # (tolerancia $ 1 por redondeo del precio sin IVA), queda en presupuesto para revisar.
        cobrado = int(p.get("total") or 0) / 100
        if precios_distintos:
            problemas.append("precios distintos de la lista de Odoo (un cambio de precio reciente, una oferta "
                             "vencida o un pedido adulterado): " + "; ".join(precios_distintos))
        if descartadas:
            problemas.append("líneas que no se pudieron cargar: " + "; ".join(descartadas))
        if not lineas:
            problemas.append("el pedido quedó sin líneas")
        if p.get("total") is not None and abs(orden.amount_total - cobrado) > 1:
            problemas.append(f"el total de Odoo ($ {orden.amount_total:,.2f}) no coincide con lo cobrado ($ {cobrado:,.2f})")
        if problemas:
            texto = "Pedido de la tienda para revisar antes de confirmar: " + ". ".join(problemas) + "."
            orden.message_post(body=texto)
            orden.activity_schedule("mail.mail_activity_data_todo", summary="Revisar pedido de la tienda",
                                    note=texto, user_id=self.env.ref("base.user_admin").id)
            return orden
        orden.action_confirm()
        return orden

    def _tienda_mayorista_del_pedido(self, p: dict):
        """(contacto, aviso). El contacto solo si la tienda lo dio de alta como mayorista (etiqueta)
        y tiene en Odoo la lista del pedido; si no, (None, por qué) y el pedido entra como minorista."""
        socio = self.env["res.partner"].sudo().browse(int(p.get("partner_id") or 0)).exists()
        if not socio:
            return None, "pedido del sitio mayorista sin contacto en Odoo (¿falló el alta del mayorista?): entró como minorista"
        if self._tienda_etiqueta() not in socio.category_id:
            return None, f"el contacto #{socio.id} no es un mayorista de la tienda: entró como minorista"
        lista = socio.property_product_pricelist
        if not lista.comercio_tienda_sincronizar or lista.id != int(p.get("lista_id") or 0):
            return None, (f"la lista del pedido no es la que {socio.name} tiene en Odoo ({lista.name or 'ninguna'}): "
                          "entró como minorista")
        return socio, None

    def _tienda_precios_esperados(self, lista, producto, cantidad: int) -> list[float]:
        """Precios finales con IVA que da la lista de Odoo hoy, con el mismo cálculo que viaja a la
        tienda (product.py, _comercio_tienda_datos): el de la cantidad pedida y el de la mínima (con
        escalas por cantidad, la tienda muestra el de la mínima). Vacío si no hay lista."""
        if not lista:
            return []
        minimo = producto._comercio_tienda_minimos(lista)[producto.id] if not lista.comercio_tienda_publica else 1
        return [producto._comercio_tienda_con_iva(lista._compute_price_rule(producto, float(c))[producto.id][0])
                for c in {max(1, cantidad), minimo}]

    def _tienda_sin_iva_si_corresponde(self, producto, final: float) -> float:
        """El precio de la línea en la forma de los impuestos del producto: si el IVA va incluido,
        el mismo; si no, sin IVA (así el total de Odoo da lo que pagó el cliente)."""
        impuestos = producto.taxes_id.filtered(lambda i: i.company_id == self.env.company)
        if not impuestos or all(i.price_include for i in impuestos):
            return final
        tasa = sum(i.amount for i in impuestos if not i.price_include and i.amount_type == "percent")
        return round(final / (1 + tasa / 100), 6)


class TiendaCambioAcciones(models.Model):
    _inherit = "comercio.tienda.cambio"

    @api.model
    def tienda_aplicar_acciones(self, acciones: list) -> list[dict]:
        """Aplica en Odoo lo que hicieron los empleados en el panel de la tienda. Idempotente:
        repetir una acción ya aplicada no cambia nada (p. ej. «listo» sobre una entrega validada)."""
        self._verificar_conector()
        SO = self.env["sale.order"].sudo()
        hechas = []
        for a in (acciones or [])[:100]:
            aid, tipo = str(a.get("id", "")), str(a.get("tipo", ""))
            if not re.fullmatch(r"[0-9a-f]{32}", aid):
                continue
            orden = SO.browse(int(a.get("odoo_id") or 0)).exists()
            if not orden or orden.comercio_tienda_ref != str(a.get("pedido", "")):
                hechas.append({"id": aid, "resultado": "error: el pedido no coincide"})
                continue
            quien = re.sub(r"[^\w .-]", "", str(a.get("empleado") or "?"))[:60]
            try:
                with self.env.cr.savepoint():
                    resultado = self._tienda_accion(orden, tipo, a.get("datos") or {}, quien)
            except Exception as e:  # noqa: BLE001 - se informa a la tienda y sigue con las demás
                resultado = f"error: {str(e)[:200]}"
            hechas.append({"id": aid, "resultado": resultado})
        return hechas

    def _tienda_accion(self, orden, tipo: str, datos: dict, quien: str) -> str:
        if tipo == "preparar":
            orden.comercio_tienda_estado = "preparando"
            orden.message_post(body=f"Tienda: empezó a prepararlo {quien}.")
            return "ok"
        if tipo == "faltante":
            orden.comercio_tienda_estado = "faltante"
            detalle = []
            for linea in orden.order_line.filtered("product_id"):
                hay = datos.get(str(linea.product_id.id))
                if hay is not None and int(hay) < linea.product_uom_qty:
                    detalle.append(f"{linea.product_id.display_name}: pidió {linea.product_uom_qty:g}, hay {int(hay)}")
            orden.message_post(body="Tienda: falta algo (" + quien + "). " + "; ".join(detalle))
            return "ok"
        if tipo == "listo":
            for picking in orden.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
                for move in picking.move_ids:
                    hay = datos.get(str(move.product_id.id)) if datos else None
                    move.quantity = min(move.product_uom_qty, float(hay)) if hay is not None else move.product_uom_qty
                    move.picked = True
                # skip_sms: sin el asistente de SMS de stock_sms (no hay SMS al cliente desde acá)
                picking.with_context(skip_backorder=True, picking_ids_not_to_backorder=picking.ids, skip_sms=True).button_validate()
            orden.comercio_tienda_estado = "listo"
            orden.message_post(body=f"Tienda: listo para retirar ({quien}). Entrega validada.")
            return "ok"
        if tipo == "eleccion":
            opcion = re.sub(r"[^\w ():.,-]", "", str(datos.get("opcion", "")))[:80]
            orden.message_post(body=f"Tienda: ante el faltante, el cliente eligió {opcion}.")
            return "ok"
        if tipo == "retirado":
            orden.comercio_tienda_estado = "retirado"
            orden.message_post(body=f"Tienda: el cliente lo retiró (entregó {quien}).")
            return "ok"
        if tipo == "cancelar":
            return self._tienda_cancelar(orden, datos, quien)
        return "error: acción desconocida"

    def _tienda_cancelar(self, orden, datos: dict, quien: str) -> str:
        """Cancelación o arrepentimiento desde la administración de la tienda. Idempotente.
        - Sin entregar: se cancela el pedido (y su entrega).
        - Entregado pero no retirado («listo»: la mercadería sigue en el local): devolución al
          depósito validada en el acto y pedido cancelado.
        - Retirado: devolución preparada (se valida al recibir la mercadería) y tarea para el local.
        En todos los casos, tarea para devolver el dinero por el medio de pago (a mano hasta tener
        la API de Mercado Pago)."""
        quien = re.sub(r"[^\w .-]", "", str(datos.get("quien") or quien))[:60]
        if orden.state == "cancel" or orden.comercio_tienda_estado in ("cancelado", "devolucion"):
            return "ok"
        admin = self.env.ref("base.user_admin").id
        entregadas = orden.picking_ids.filtered(lambda p: p.state == "done" and p.picking_type_code == "outgoing")
        retirado = bool(datos.get("retirado"))
        for picking in entregadas.filtered(lambda p: not p.return_ids.filtered(lambda r: r.state != "cancel")):
            devolucion = picking._create_return()
            devolucion.action_return_all()
            devolucion.action_confirm()
            if not retirado:  # la mercadería no salió del local: vuelve al depósito ya
                devolucion.action_assign()
                for move in devolucion.move_ids:
                    move.quantity = move.product_uom_qty
                    move.picked = True
                devolucion.with_context(skip_backorder=True, skip_sms=True).button_validate()
        if retirado and entregadas:
            orden.comercio_tienda_estado = "devolucion"
            orden.activity_schedule("mail.mail_activity_data_todo", summary="Recibir la devolución de la tienda", user_id=admin,
                                    note="El cliente se arrepintió de la compra. Cuando traiga la mercadería, validar la "
                                         "devolución (Inventario → Recepciones) y después cancelar este pedido.")
        else:
            orden.with_context(disable_cancel_warning=True).action_cancel()
            orden.comercio_tienda_estado = "cancelado"
        monto = int(datos.get("monto") or 0) / 100
        medio = re.sub(r"[^\w .:-]", "", str(datos.get("pago") or ""))[:80]
        orden.activity_schedule("mail.mail_activity_data_todo", summary="Devolver el dinero del pedido de la tienda", user_id=admin,
                                note=f"Devolver $ {monto:,.2f} al cliente por {medio or 'el medio con que pagó'}.")
        orden.message_post(body=f"Tienda: pedido {'con devolución por recibir' if retirado and entregadas else 'cancelado'} "
                                f"desde la administración ({quien}). Falta devolver el dinero.")
        return "ok"
