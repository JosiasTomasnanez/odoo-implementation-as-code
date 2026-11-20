"""Odoo simulado en memoria para probar el motor sin un servidor real."""

from __future__ import annotations

import itertools

from odoo_iac.client import OdooClient, OdooError

SCHEMAS = {
    "ir.model.data": {
        "module": "char", "name": "char", "model": "char", "res_id": "integer", "noupdate": "boolean",
    },
    "ir.module.module": {"name": "char", "state": "selection"},
    "product.category": {"name": "char", "parent_id": ("many2one", "product.category")},
    "product.tag": {"name": "char"},
    "res.config.settings": {"group_product_pricelist": "boolean"},
    "product.template": {
        "name": "char",
        "list_price": "float",
        "categ_id": ("many2one", "product.category"),
        "product_tag_ids": ("many2many", "product.tag"),
        "image_1920": "image",
    },
}


class FakeTransport:
    def __init__(self):
        self.db: dict[str, dict[int, dict]] = {model: {} for model in SCHEMAS}
        self.ids = itertools.count(1)
        self.writes: list[tuple] = []
        # Módulos en disco que Odoo solo lista después de update_list (p. ej. addons propios).
        self.available: list[str] = []
        # Ajustes vigentes (lo que muestra la pantalla de Ajustes).
        self.settings: dict = {"group_product_pricelist": False}

    # --------------------------------------------------------------- helpers
    def insert(self, _model: str, **vals) -> int:
        new_id = next(self.ids)
        self.db[_model][new_id] = {"id": new_id, **vals}
        return new_id

    def _type(self, model, name):
        spec = SCHEMAS[model][name]
        return spec[0] if isinstance(spec, tuple) else spec

    def _match(self, row, domain):
        for name, op, value in domain:
            if op == "=" and row.get(name) != value:
                return False
            if op == "in" and row.get(name) not in value:
                return False
        return True

    def _read(self, model, row, fields):
        out = {"id": row["id"]}
        for name in fields:
            if name == "id":
                continue
            value = row.get(name, False)
            ftype = self._type(model, name)
            if ftype == "many2one" and value:
                value = [value, f"{name}#{value}"]
            if ftype == "many2many":
                value = sorted(value or [])
            if ftype == "image" and value:
                value = {"content": value, "size": len(value)}  # como JSON-2 en Odoo 20
            out[name] = value
        return out

    def _vals(self, model, vals):
        clean = {}
        for name, value in vals.items():
            if self._type(model, name) == "many2many":
                assert value[0][0] == 6
                value = list(value[0][2])
            clean[name] = value
        return clean

    # ------------------------------------------------------------------ API
    def call(self, model, method, ids, kwargs):
        if model not in self.db:
            raise OdooError(f"modelo {model} inexistente")
        table = self.db[model]
        if method == "fields_get":
            return {
                name: {"type": self._type(model, name), "string": name,
                       "relation": spec[1] if isinstance(spec, tuple) else False}
                for name, spec in SCHEMAS[model].items()
            }
        if method in ("search_read", "search_count"):
            rows = [r for r in table.values() if self._match(r, kwargs["domain"])]
            if method == "search_count":
                return len(rows)
            return [self._read(model, r, kwargs["fields"]) for r in rows]
        if method == "read":
            return [self._read(model, table[i], kwargs["fields"]) for i in ids]
        if method == "create" and model == "res.config.settings":
            # Asistente de Ajustes: arranca con los valores actuales (no cuenta como escritura)
            return [self.insert(model, **{**self.settings, **self._vals(model, v)})
                    for v in kwargs["vals_list"]]
        if method == "create":
            self.writes.append((model, "create", kwargs["vals_list"]))
            return [self.insert(model, **self._vals(model, v)) for v in kwargs["vals_list"]]
        if method == "write":
            self.writes.append((model, "write", ids, kwargs["vals"]))
            for i in ids:
                table[i].update(self._vals(model, kwargs["vals"]))
            return True
        if method == "execute":
            self.writes.append((model, "execute", ids))
            for i in ids:
                self.settings.update({k: v for k, v in table[i].items() if k != "id"})
            return True
        if method == "update_list":
            for name in self.available:
                if not any(r["name"] == name for r in table.values()):
                    self.insert(model, name=name, state="uninstalled")
            self.available = []
            return [0, 0]
        if method == "button_immediate_install":
            for i in ids:
                table[i]["state"] = "installed"
            return True
        raise NotImplementedError(method)


def make_client() -> tuple[OdooClient, FakeTransport]:
    transport = FakeTransport()
    return OdooClient(transport), transport
