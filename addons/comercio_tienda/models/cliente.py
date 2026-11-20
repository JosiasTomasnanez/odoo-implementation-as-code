"""Mayoristas y listas que se aprueban en la administración de la tienda (fase 7, ADR 0036).

La tienda manda, por el conector, los mayoristas aprobados (con su lista) y las listas nuevas
pedidas para clientes. Acá se crea o se vincula el contacto (por CUIT) con su lista de precios, y
se crean o se actualizan las listas de clientes («tal lista − X %», con descuentos propios por
rubro o por producto, ADR 0037) con «Sincronizar con la tienda», que vuelven con sus precios.
"""

from __future__ import annotations

import re

from odoo import api, models

from .sale_order import EMAIL

IVA = {"ri": "l10n_ar.res_IVARI", "monotributo": "l10n_ar.res_RM", "exento": "l10n_ar.res_IVAE"}
ETIQUETA = "Mayorista (tienda online)"


def _texto(v, largo: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:largo]


class TiendaCambioClientes(models.Model):
    _inherit = "comercio.tienda.cambio"

    @api.model
    def tienda_sincronizar_clientes(self, clientes: list, listas: list) -> dict:
        """Aplica en Odoo lo aprobado en la tienda. Idempotente: repetir un cliente ya vinculado
        solo vuelve a ponerle la lista; una lista ya creada (mismo pedido) no se duplica."""
        self._verificar_conector()
        hechas = []
        for li in (listas or [])[:20]:
            lid = str(li.get("id", ""))
            if not re.fullmatch(r"[0-9a-f]{32}", lid):
                continue
            try:
                with self.env.cr.savepoint():
                    lista = self._tienda_lista(lid, li)
                hecha = {"id": lid, "odoo_id": lista.id, "resultado": f"lista: {lista.name}"}
            except Exception as e:  # noqa: BLE001 — se informa a la tienda y sigue con las demás
                hecha = {"id": lid, "odoo_id": None, "resultado": f"error: {str(e)[:200]}"}
            if isinstance(li.get("version"), int):
                hecha["version"] = li["version"]
            hechas.append(hecha)
        vinculados = []
        for c in (clientes or [])[:50]:
            cid = str(c.get("id", ""))
            if not re.fullmatch(r"[0-9a-f]{32}", cid):
                continue
            try:
                with self.env.cr.savepoint():
                    socio = self._tienda_mayorista(c)
                vinculados.append(
                    {"id": cid, "odoo_partner_id": socio.id, "resultado": f"contacto {socio.id}"}
                )
            except Exception as e:  # noqa: BLE001
                vinculados.append({"id": cid, "odoo_partner_id": None, "resultado": f"error: {str(e)[:200]}"})
        return {"clientes": vinculados, "listas": hechas}

    def _tienda_lista(self, lid: str, li: dict):
        """Crea la lista pedida en la tienda o la pone al día (nombre, descuento general y
        descuentos por rubro o producto). Sus reglas las maneja la tienda: se regeneran enteras."""
        Lista = self.env["product.pricelist"].sudo().with_context(active_test=False)
        ref = f"tienda:{lid}"
        lista = Lista.search([("comercio_tienda_ref", "=", ref)], limit=1)
        if lista and "reglas" not in li:
            return lista  # pedido de una tienda anterior a las condiciones por rubro: ya está creada
        base = Lista.browse(int(li.get("base_id") or 0)).exists()
        if not base or not base.comercio_tienda_sincronizar or base == lista:
            raise ValueError("la lista base no existe o no está sincronizada con la tienda")
        descuento = float(li.get("descuento") or 0)
        if not 0 <= descuento <= 60:
            raise ValueError("descuento fuera de rango (0 a 60 %)")
        reglas, vistas = [], set()
        for r in (li.get("reglas") or [])[:300]:
            tipo, rid, d = r.get("tipo"), int(r.get("id") or 0), float(r.get("descuento") or 0)
            if tipo not in ("rubro", "producto") or rid <= 0 or not 0 <= d <= 60:
                raise ValueError("una condición de la lista no es válida")
            if (tipo, rid) not in vistas:
                vistas.add((tipo, rid))
                reglas.append({"tipo": tipo, "id": rid, "descuento": d})
        vals = {
            "name": _texto(li.get("nombre"), 60) or f"{base.name} − {descuento:g} %",
            "comercio_tienda_reglas": {"base": base.id, "descuento": descuento, "reglas": reglas},
        }
        if lista:
            lista.write(vals)
        else:
            lista = Lista.create(
                {**vals, "currency_id": base.currency_id.id, "comercio_tienda_sincronizar": True,
                 "comercio_tienda_publica": False, "comercio_tienda_ref": ref}
            )
        lista._comercio_tienda_aplicar_reglas()
        return lista

    def _tienda_mayorista(self, c: dict):
        """Contacto del mayorista (en Odoo 20 «es empresa» lo calcula Odoo por el CUIT): el que ya se vinculó, si no el que tenga ese CUIT, si no
        uno nuevo con los datos del alta. Siempre se le pone la lista aprobada."""
        Partner = self.env["res.partner"].sudo()
        lista = self.env["product.pricelist"].sudo().browse(int(c.get("lista_id") or 0)).exists()
        if not lista or not lista.comercio_tienda_sincronizar or lista.comercio_tienda_publica:
            raise ValueError("la lista no existe o no es una lista mayorista sincronizada")
        cuit = re.sub(r"\D", "", str(c.get("cuit") or ""))
        if not re.fullmatch(r"\d{11}", cuit):
            raise ValueError("CUIT inválido")
        socio = Partner.browse(int(c.get("odoo_partner_id") or 0)).exists()
        if not socio:
            socio = Partner.search(
                [("vat", "in", [cuit, f"{cuit[:2]}-{cuit[2:10]}-{cuit[10]}"]), ("parent_id", "=", False),
                 ("user_ids", "=", False), ("id", "!=", self.env.company.partner_id.id)],
                limit=1,
            )
            # El CUIT lo escribe quien pide la cuenta: solo se vincula a un contacto que ya existía
            # si su mail (o el de uno de sus contactos) es el mail verificado de la cuenta. Si no,
            # no se toca ese contacto (ni su lista) y se avisa en la administración.
            email = str(c.get("email") or "").strip().lower()
            mails = {m.strip().lower() for m in (socio | socio.child_ids).mapped("email") if m}
            if socio and email not in mails:
                raise ValueError(
                    f"ya hay un contacto en Odoo con ese CUIT ({socio.name}) y otro mail. Confirmá con el "
                    f"cliente que es él, agregá {email} a ese contacto en Odoo y tocá «Guardar lista»"
                )
        etiqueta = self._tienda_etiqueta()
        vals = {"property_product_pricelist": lista.id, "category_id": [(4, etiqueta.id)]}
        if not socio:
            email = str(c.get("email") or "").strip().lower()[:160]
            vals.update(
                {
                    "name": _texto(c.get("razon_social"), 120) or email,
                    "vat": cuit,
                    "email": email if EMAIL.match(email) else False,
                    "phone": re.sub(r"[^0-9 +()-]", "", str(c.get("telefono") or ""))[:30] or False,
                    "street": _texto(c.get("direccion"), 120) or False,
                    "city": _texto(c.get("localidad"), 80) or False,
                    "country_id": self.env.ref("base.ar").id,
                    "comercio_tienda_cliente": True,
                    "comment": "Mayorista dado de alta desde la tienda online"
                    + (f". Actividad: {_texto(c.get('actividad'), 40)}" if c.get("actividad") else "")
                    + (f". Contacto: {_texto(c.get('contacto'), 80)}" if c.get("contacto") else ""),
                }
            )
            iva = (
                self.env.ref(IVA.get(str(c.get("condicion_iva")), ""), raise_if_not_found=False)
                if c.get("condicion_iva") in IVA
                else None
            )
            if iva and "l10n_ar_afip_responsibility_type_id" in Partner._fields:
                vals["l10n_ar_afip_responsibility_type_id"] = iva.id
            socio = Partner.create(vals)
            if c.get("contacto"):
                Partner.create(
                    {
                        "name": _texto(c.get("contacto"), 80),
                        "parent_id": socio.id,
                        "type": "contact",
                        "email": vals["email"],
                        "phone": vals["phone"],
                    }
                )
        else:
            # Un contacto que ya existía: solo su lista y la etiqueta (sus datos los maneja Odoo)
            socio.write(vals)
        return socio

    def _tienda_etiqueta(self):
        Cat = self.env["res.partner.category"].sudo()
        return Cat.search([("name", "=", ETIQUETA)], limit=1) or Cat.create({"name": ETIQUETA})
