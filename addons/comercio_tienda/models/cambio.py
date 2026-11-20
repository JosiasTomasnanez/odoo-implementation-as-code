"""Cola de cambios hacia la tienda online (ADR 0033).

Cada cambio de un producto publicado o de un rubro deja una fila (una sola por objeto: si cambia
de nuevo, sube su «secuencia»). El conector del local lee lotes con ``tienda_leer_cambios`` y,
cuando la tienda los aplicó, los confirma con ``tienda_confirmar``: se borra solo la fila cuya
secuencia coincide, así un cambio que llegó mientras tanto no se pierde.
"""
from __future__ import annotations

import base64
import io
import logging

from PIL import Image
# Odoo inicia Pillow con pocos formatos (tools/image.py: preinit) y deja afuera WebP: se registra acá
from PIL import WebPImagePlugin  # noqa: F401

from odoo import api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

TIPOS = [("producto", "Producto"), ("categoria", "Rubro del PdV"), ("empleado", "Empleado del panel")]
LOTE_MAXIMO = 500


class TiendaCambio(models.Model):
    _name = "comercio.tienda.cambio"
    _description = "Cambio pendiente para la tienda online"
    _order = "id"

    tipo = fields.Selection(TIPOS, required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    secuencia = fields.Integer(default=1, required=True)

    _tipo_res_unico = models.Constraint("UNIQUE(tipo, res_id)", "Una sola fila por objeto.")

    # ---------------------------------------------------------------- anotar cambios

    @api.model
    def _anotar(self, tipo: str, ids) -> None:
        """Anota (o renueva) el cambio de esos objetos. Una sola consulta, con parámetros."""
        ids = sorted({int(i) for i in ids if i})
        if not ids:
            return
        self.env.cr.execute(
            """
            INSERT INTO comercio_tienda_cambio (tipo, res_id, secuencia, create_uid, create_date, write_uid, write_date)
            SELECT %s, unnest(%s::int[]), 1, %s, now() at time zone 'utc', %s, now() at time zone 'utc'
            ON CONFLICT (tipo, res_id) DO UPDATE
               SET secuencia = comercio_tienda_cambio.secuencia + 1,
                   write_date = now() at time zone 'utc'
            """,
            (tipo, ids, self.env.uid, self.env.uid),
        )

    @api.model
    def _anotar_productos(self, productos) -> None:
        """Productos (product.product) que tienen que viajar: los publicados y los que se
        acaban de despublicar (eso lo anota el propio cambio de la casilla)."""
        publicados = productos.sudo().filtered(lambda p: p.product_tmpl_id.comercio_tienda_publicar)
        self._anotar("producto", publicados.ids)

    # ---------------------------------------------------------------- API del conector

    def _verificar_conector(self) -> None:
        if not (self.env.user.has_group("comercio_tienda.group_tienda_conector") or self.env.is_superuser()
                or self.env.user.has_group("base.group_system")):
            raise AccessError("Solo el conector de la tienda puede leer la cola.")

    @api.model
    def tienda_leer_cambios(self, limite: int = 200) -> dict:
        """Lote para el conector: las filas pendientes y los datos ya armados de cada objeto."""
        self._verificar_conector()
        # Los datos van en el idioma del negocio (el usuario del conector puede tener otro)
        self = self.with_context(lang=self.env.company.partner_id.lang or "es_AR")
        limite = max(1, min(int(limite or 200), LOTE_MAXIMO))
        filas = self.sudo().search([], limit=limite)
        prod_ids = [f.res_id for f in filas if f.tipo == "producto"]
        cat_ids = [f.res_id for f in filas if f.tipo == "categoria"]
        emp_ids = [f.res_id for f in filas if f.tipo == "empleado"]
        empleados = self.env["hr.employee"].sudo().with_context(active_test=False).browse(emp_ids).exists()
        armado = self.env["product.product"].sudo().with_context(active_test=False)
        return {
            "cambios": [{"tipo": f.tipo, "res_id": f.res_id, "secuencia": f.secuencia} for f in filas],
            "productos": armado.browse(prod_ids).exists()._comercio_tienda_datos(),
            "productos_borrados": sorted(set(prod_ids) - set(armado.browse(prod_ids).exists().ids)),
            "categorias": self.env["pos.category"].sudo().browse(cat_ids).exists()._comercio_tienda_datos(),
            "categorias_borradas": sorted(set(cat_ids) - set(self.env["pos.category"].sudo().browse(cat_ids).exists().ids)),
            "listas": self.env["product.pricelist"].sudo()._comercio_tienda_listas(),
            "empleados": empleados._comercio_tienda_datos()
            + [{"id": i, "nombre": "-", "pin": None, "activo": False} for i in set(emp_ids) - set(empleados.ids)],
            "pendientes": self.sudo().search_count([]),
        }

    @api.model
    def tienda_confirmar(self, cambios: list) -> int:
        """Borra las filas aplicadas en la tienda (solo si su secuencia no cambió)."""
        self._verificar_conector()
        borradas = 0
        for c in cambios or []:
            fila = self.sudo().search([("tipo", "=", str(c.get("tipo"))), ("res_id", "=", int(c.get("res_id"))),
                                       ("secuencia", "=", int(c.get("secuencia")))], limit=1)
            if fila:
                fila.unlink()
                borradas += 1
        return borradas

    @api.model
    def tienda_marcar_todo(self) -> int:
        """Vuelve a mandar todo lo publicado y todos los rubros (carga inicial o reparación)."""
        self._verificar_conector()
        productos = self.env["product.product"].sudo().search([("product_tmpl_id.comercio_tienda_publicar", "=", True)])
        self._anotar("producto", productos.ids)
        self._anotar("categoria", self.env["pos.category"].sudo().search([]).ids)
        self._anotar("empleado", self.env["hr.employee"].sudo().search([("comercio_tienda_panel", "=", True)]).ids)
        return len(productos)

    @api.model
    def tienda_imagen(self, producto_id: int) -> dict:
        """Foto del producto para subir a la tienda (1024 px, base64) y su identificador."""
        self._verificar_conector()
        p = self.env["product.product"].sudo().browse(int(producto_id)).exists()
        if not p or not p.product_tmpl_id.comercio_tienda_publicar:
            return {"id": None, "datos": None}
        # Odoo 20 devuelve los binarios como BinaryValue (con to_base64); se mandan en base64.
        datos = p.image_1024
        if hasattr(datos, "to_base64"):
            datos = datos.to_base64()
        elif isinstance(datos, (bytes, bytearray)):
            datos = base64.b64encode(datos).decode()
        return {"id": p._comercio_tienda_id_imagen(), "datos": datos or None, "webp": self._tienda_webp(p) if datos else {}}

    @api.model
    def _tienda_webp(self, producto) -> dict[str, str]:
        """La foto en WebP de 400 y 800 px (base64), para que la tienda mande al celular la más chica
        que le sirve (srcset)."""
        crudo = producto.with_context(bin_size=False).image_1024
        if hasattr(crudo, "to_bytes"):
            crudo = crudo.to_bytes()
        elif isinstance(crudo, str):
            crudo = base64.b64decode(crudo)
        elif hasattr(crudo, "to_base64"):
            crudo = base64.b64decode(crudo.to_base64())
        res = {}
        try:
            # Pillow directo: la herramienta de imágenes de Odoo 20 solo escribe PNG, JPEG, GIF o ICO
            original = Image.open(io.BytesIO(crudo))
            original.load()
        except Exception:  # noqa: BLE001 — una foto que no se puede leer: va solo la original
            return {}
        for ancho in (400, 800):
            foto = original.copy()
            foto.thumbnail((ancho, ancho))  # sin agrandar ni deformar
            if foto.mode not in ("RGB", "RGBA"):
                foto = foto.convert("RGBA" if "transparency" in foto.info or foto.mode in ("LA", "PA") else "RGB")
            salida = io.BytesIO()
            foto.save(salida, "WEBP", quality=80, method=4)
            res[str(ancho)] = base64.b64encode(salida.getvalue()).decode()
        return res

    # ---------------------------------------------------------------- ofertas con fecha

    @api.model
    def _cron_ofertas_con_fecha(self) -> None:
        """Una oferta que empieza o termina cambia el precio sin que nadie escriba nada: cada hora
        se anotan los productos de las reglas que empezaron o terminaron en la última hora y pico."""
        ahora = fields.Datetime.now()
        desde = fields.Datetime.subtract(ahora, minutes=75)
        reglas = self.env["product.pricelist.item"].sudo().search([
            ("pricelist_id.comercio_tienda_sincronizar", "=", True),
            "|", "&", ("date_start", ">", desde), ("date_start", "<=", ahora),
                 "&", ("date_end", ">", desde), ("date_end", "<=", ahora),
        ])
        reglas._comercio_tienda_anotar()
        self._revisar_minimos()

    @api.model
    def _revisar_minimos(self) -> None:
        """Repaso de «A reponer» por si el conector estuvo parado: marca o desmarca según el stock
        libre de ahora. Si la marca cambia, el producto vuelve a viajar (cambia «consultar»)."""
        almacen = self.env["stock.warehouse"].sudo().search([("company_id", "=", self.env.company.id)], limit=1)
        productos = self.env["product.product"].sudo().with_context(warehouse_id=almacen.id).search([
            ("product_tmpl_id.comercio_tienda_publicar", "=", True), ("is_storable", "=", True)])
        cambiaron = []
        for p in productos:
            t = p.product_tmpl_id
            margen = t.categ_id._comercio_tienda_margen()
            bajo = bool(t.active and p.active and t.sale_ok and not t.comercio_tienda_consultar and p.free_qty <= margen)
            if bajo != t.comercio_tienda_bajo_minimo:
                cambiaron.append(p.id)
            t._comercio_tienda_marcar_bajo(bajo, p.free_qty, margen)
        self._anotar("producto", cambiaron)
