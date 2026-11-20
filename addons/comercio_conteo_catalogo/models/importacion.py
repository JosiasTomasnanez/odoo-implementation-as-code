from odoo import _, api, models
from odoo.addons.comercio_catalogo.catalogo import plan as motor
from odoo.addons.comercio_catalogo.catalogo.codigos import FABRICANTE, normalizar, numero_de_codigo_propio
from odoo.exceptions import AccessError, UserError


class ComercioListaImportacionLinea(models.Model):
    _inherit = "comercio.lista.importacion.linea"

    def _comercio_filas_del_codigo(self, codigo):
        """Filas de la lista vigente de cada proveedor con ese código, que todavía no son nuestras
        (una por proveedor). Primero por código de barras; si no, por código del proveedor."""
        base = [("de_lista_vigente", "=", True), ("estado", "=", "pendiente"),
                ("accion", "in", (motor.NUEVO, motor.POSIBLE_DUPLICADO))]
        filas = self.search(base + [("codigo_barras", "=", codigo)])
        filas = filas or self.search(base + [("codigo_proveedor", "=", codigo)])
        una_por_proveedor = self.browse()
        for fila in filas:
            if fila.partner_id not in una_por_proveedor.partner_id:
                una_por_proveedor |= fila
        return una_por_proveedor

    @api.model
    def comercio_puede_agregar(self):
        return self.env.user.has_group("comercio_catalogo.group_listas_proveedores")

    @api.model
    def comercio_buscar_para_conteo(self, codigo):
        """Para «Contar inventario»: ¿el código escaneado está en alguna lista? False si no."""
        codigo = (codigo or "").strip()
        filas = self._comercio_filas_del_codigo(codigo) if codigo else self.browse()
        if not filas:
            return False
        parecido = filas.candidato_ids.filtered("active")[:1]
        return {
            "ids": filas.ids,
            "descripcion": filas[0].descripcion,
            "proveedores": filas.partner_id.mapped("name"),
            "categoria": filas[0].categoria_id.display_name or "",
            "parecido": parecido.display_name or False,
            "puede_agregar": self.comercio_puede_agregar(),
        }

    @api.model
    def comercio_agregar_desde_conteo(self, codigo, es_el_parecido=False):
        """Agrega al catálogo el producto del código escaneado (o lo une al parecido) y devuelve
        el código de barras con el que la app de conteo lo encuentra."""
        # El cartel solo aparece con el permiso, pero el servidor lo controla igual (la pantalla
        # no alcanza: este método se puede llamar directo)
        if not self.comercio_puede_agregar():
            raise AccessError(_("Hace falta el permiso «Costos y precios» para agregar productos "
                                "desde las listas."))
        filas = self._comercio_filas_del_codigo((codigo or "").strip())
        if not filas:
            raise UserError(_("El código %s ya no está en ninguna lista pendiente.", codigo))
        if es_el_parecido:
            producto = filas.candidato_ids.filtered("active")[:1]
            if not producto:
                raise UserError(_("Esta fila no se parece a ningún producto nuestro."))
            # Primero el código: se escaneó del envase, así que es el de fábrica de nuestro producto
            # (si no, la fila queda «decidir cuál código queda» y no se une)
            try:
                with self.env.cr.savepoint():
                    producto._comercio_poner_codigo_fabrica(codigo)
            except UserError:
                pass  # no es un código de fábrica, o ya es de otro: el producto queda con el suyo
            for _intento in range(2):  # si la fila cambió desde la simulación, se recalcula y se reintenta
                pendientes = filas.filtered(lambda f: f.estado == "pendiente")
                if not pendientes:
                    break
                pendientes.write({"producto_elegido_id": producto.id})
                pendientes.action_es_el_mismo()
        else:
            if len(filas) > 1:
                filas.action_agregar_como_uno()
            elif filas.accion == motor.POSIBLE_DUPLICADO:
                filas.action_es_nuevo()
            else:
                filas.action_aplicar()
            producto = filas.producto_id[:1]
        if not producto:
            raise UserError(_("No se pudo agregar «%(d)s»: %(a)s", d=filas[0].descripcion,
                              a=filas[0].avisos or _("mirá la fila en su lista.")))
        return producto.product_variant_id.barcode or False


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def comercio_buscar_para_codigo(self, texto):
        """Para «Contar inventario»: productos nuestros por nombre o referencia, para ponerle el
        código escaneado (el producto lo tenemos, pero con otro código o con el 20…)."""
        texto = (texto or "").strip()
        if len(texto) < 2:
            return []
        productos = self.search(["|", ("name", "ilike", texto), ("default_code", "=ilike", texto)], limit=8)
        return [{"id": p.id, "nombre": p.display_name, "codigo": p.barcode or ""} for p in productos]

    def comercio_poner_codigo_desde_conteo(self, codigo):
        """El código escaneado pasa a ser el de fábrica de este producto (el 20… queda como
        alternativo, como en «Códigos de fábrica»); si ya tenía uno de fábrica, el escaneado se
        suma como alternativo. Devuelve el código con el que se cuenta."""
        self.ensure_one()
        producto = self.product_variant_id
        if not producto.barcode or numero_de_codigo_propio(producto.barcode):
            self._comercio_poner_codigo_fabrica(codigo)
            return producto.barcode
        # Ya tiene uno de fábrica (otra presentación, otro proveedor): el nuevo se suma como
        # alternativo, que la caja y la app de conteo también leen; no se pisa el que tenía
        codigo, tipo = normalizar(codigo)
        if tipo != FABRICANTE:
            raise UserError(_("«%s» no es un código de barras de fábrica válido.", codigo))
        Producto = self.env["product.product"].with_context(active_test=False)
        otro = Producto.search([("barcode", "=", codigo)], limit=1)
        otro = otro or self.env["product.uom"].search([("barcode", "=", codigo)], limit=1).product_id
        if otro:
            raise UserError(_("El código %(c)s ya es de «%(o)s».", c=codigo, o=otro.display_name))
        self._comercio_exigir_permiso()
        self.env["product.uom"].sudo().create(
            {"product_id": producto.id, "uom_id": producto.uom_id.id, "barcode": codigo})
        self.message_post(body=_("Código de fábrica alternativo %(c)s, al contar - %(u)s.",
                                 c=codigo, u=self.env.user.name))
        return codigo
