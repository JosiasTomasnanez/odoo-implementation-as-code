"""Motor de reconciliación: compara el estado deseado con Odoo y lo aplica.

Principios (ver docs/decisiones/0003-configuracion-como-codigo.md):

* **Idempotencia**: cada registro se identifica con un xml_id estable
  (``iac.<id>`` en ``ir.model.data``). Aplicar dos veces no duplica nada.
* **Dry run**: ``plan`` calcula los cambios sin escribir.
* **Validación**: después de aplicar se vuelve a planificar; el resultado
  esperado es "sin cambios". Que la API responda OK no alcanza.
* **Adopción**: si un registro todavía no tiene xml_id pero ya existe (por
  ejemplo, creado a mano o por Odoo), se lo busca por los campos ``match`` y
  se lo vincula en lugar de duplicarlo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from odoo_iac.client import OdooClient, OdooError
from odoo_iac.state import Archivo, DesiredState, Record

XMLID_MODULE = "iac"
FLOAT_DIGITS = 6

CREATE, ADOPT, UPDATE, INSTALL, OK = "create", "adopt", "update", "install", "ok"


class PlanError(RuntimeError):
    """El estado deseado no puede aplicarse tal como está escrito."""


class _Pending:
    """Referencia a un registro que todavía no existe (solo en modo plan)."""

    def __init__(self, ref: str):
        self.ref = ref

    def __repr__(self) -> str:
        return f"<nuevo:{self.ref}>"


@dataclass
class Change:
    kind: str
    model: str
    target: str
    source: str = ""
    diff: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    note: str = ""


@dataclass
class Result:
    changes: list[Change] = field(default_factory=list)

    def pending(self) -> list[Change]:
        return [c for c in self.changes if c.kind != OK]

    def count(self, kind: str) -> int:
        return sum(1 for c in self.changes if c.kind == kind)


class Engine:
    def __init__(self, client: OdooClient):
        self.client = client
        self._fields: dict[str, dict] = {}
        # xml_id completo -> (id de ir.model.data, modelo, res_id)
        self._xmlids: dict[str, tuple[int, str, int] | None] = {}
        # Solo en modo plan: xml_id -> res_id adoptado, o None si se va a crear.
        self._planned: dict[str, int | None] = {}
        # Solo en modo plan: hay módulos por instalar (sus registros todavía no existen)
        self._modules_pending = False

    # ------------------------------------------------------------------ util

    def fields(self, model: str) -> dict:
        if model not in self._fields:
            self._fields[model] = self.client.fields_get(model)
        return self._fields[model]

    @staticmethod
    def full_xmlid(ref: str) -> str:
        return ref if "." in ref else f"{XMLID_MODULE}.{ref}"

    def lookup_xmlid(self, ref: str) -> tuple[int, str, int] | None:
        xmlid = self.full_xmlid(ref)
        if xmlid not in self._xmlids:
            module, name = xmlid.split(".", 1)
            rows = self.client.search_read(
                "ir.model.data",
                [("module", "=", module), ("name", "=", name)],
                ["model", "res_id"],
            )
            self._xmlids[xmlid] = (rows[0]["id"], rows[0]["model"], rows[0]["res_id"]) if rows else None
        return self._xmlids[xmlid]

    def existing_id(self, record: Record) -> int | None:
        """Id del registro vinculado al xml_id, verificando que siga existiendo."""
        found = self.lookup_xmlid(record.id)
        if not found:
            return None
        _, model, res_id = found
        if model != record.model:
            raise PlanError(f"{record.source}: iac.{record.id} apunta a {model}, no a {record.model}")
        alive = self.client.call(
            record.model, "search_count", domain=[("id", "=", res_id)],
            context=dict(self.client.context, active_test=False),
        )
        return res_id if alive else None

    def resolve_ref(self, ref: str, record: Record) -> int | _Pending:
        found = self.lookup_xmlid(ref)
        if found:
            return found[2]
        xmlid = self.full_xmlid(ref)
        if xmlid in self._planned:
            planned = self._planned[xmlid]
            return _Pending(ref) if planned is None else planned
        if "." in ref and self._modules_pending:
            # Registro de un módulo que se instala en este mismo apply (p. ej. en una base
            # nueva, `product.model_product_template`): existirá al aplicar.
            return _Pending(ref)
        raise PlanError(
            f"{record.source}: referencia {ref!r} desconocida "
            "(¿el registro se define después o falta instalar un módulo?)"
        )

    def resolve_value(self, record: Record, name: str, value: Any) -> Any:
        meta = self.fields(record.model).get(name)
        if meta is None:
            raise PlanError(f"{record.source}: el campo {record.model}.{name} no existe")
        if isinstance(value, dict):
            if set(value) == {"ref"}:
                return self.resolve_ref(str(value["ref"]), record)
            if set(value) == {"refs"}:
                return [self.resolve_ref(str(r), record) for r in value["refs"]]
            raise PlanError(f"{record.source}: valor de {name} no reconocido: {value!r}")
        return value

    def to_write(self, record: Record, resolved: dict) -> dict:
        vals = {}
        for name, value in resolved.items():
            if self.fields(record.model)[name]["type"] in ("many2many", "one2many"):
                vals[name] = [[6, 0, value]]
            else:
                vals[name] = value
        return vals

    @staticmethod
    def normalize(ftype: str, value: Any) -> Any:
        if ftype == "many2one":
            if isinstance(value, (list, tuple)):
                return value[0] if value else False
            return value or False
        if ftype in ("many2many", "one2many"):
            return frozenset(value or [])
        if ftype in ("float", "monetary"):
            return round(float(value or 0.0), FLOAT_DIGITS)
        if ftype in ("char", "text", "html", "selection") and value in (None, False, ""):
            return False
        if ftype in ("binary", "image"):
            # JSON-2 devuelve {'content': base64, 'size': ...}; se escribe el base64 solo
            if isinstance(value, dict):
                value = value.get("content")
            return value or False
        return value

    def diff(self, record: Record, res_id: int, resolved: dict) -> dict:
        current = self.client.read(record.model, [res_id], list(resolved))[0]
        result = {}
        for name, desired in resolved.items():
            ftype = self.fields(record.model)[name]["type"]
            if isinstance(desired, _Pending) or (
                isinstance(desired, list) and any(isinstance(v, _Pending) for v in desired)
            ):
                result[name] = (current[name], desired)
                continue
            if self.normalize(ftype, current[name]) != self.normalize(ftype, desired):
                result[name] = (current[name], desired)
        return result

    @staticmethod
    def display(record: Record, name: str, resolved: Any) -> Any:
        """Valor para mostrar: las referencias y los archivos se muestran como en el YAML."""
        raw = record.values.get(name)
        if isinstance(raw, Archivo):
            return {"archivo": raw.ruta}
        return raw if isinstance(raw, dict) else resolved

    def find_match(self, record: Record, resolved: dict) -> int | None:
        if not record.match:
            return None
        domain = []
        for name in record.match:
            if name not in resolved or isinstance(resolved[name], _Pending):
                return None
            domain.append((name, "=", resolved[name]))
        rows = self.client.search_read(
            record.model, domain, ["id"], context=dict(self.client.context, active_test=False)
        )
        if len(rows) > 1:
            raise PlanError(
                f"{record.source}: {len(rows)} registros de {record.model} coinciden con "
                f"{domain}; no se puede adoptar sin ambigüedad"
            )
        return rows[0]["id"] if rows else None

    def link_xmlid(self, record: Record, res_id: int) -> None:
        xmlid = self.full_xmlid(record.id)
        existing = self._xmlids.get(xmlid)
        if existing:  # xml_id huérfano (el registro fue borrado): se reapunta
            self.client.write("ir.model.data", [existing[0]], {"res_id": res_id})
            imd_id = existing[0]
        else:
            imd_id = self.client.create(
                "ir.model.data",
                {"module": XMLID_MODULE, "name": record.id, "model": record.model,
                 "res_id": res_id, "noupdate": True},
            )
        self._xmlids[xmlid] = (imd_id, record.model, res_id)

    # --------------------------------------------------------------- módulos

    def reconcile_modules(self, modules: list[str], apply: bool) -> list[Change]:
        if not modules:
            return []
        rows = self.client.search_read(
            "ir.module.module", [("name", "in", modules)], ["name", "state"]
        )
        by_name = {row["name"]: row for row in rows}
        unknown = [m for m in modules if m not in by_name]
        if unknown and apply:
            # Un módulo propio recién agregado (addons/) no figura hasta refrescar la lista.
            self.client.call("ir.module.module", "update_list")
            rows = self.client.search_read(
                "ir.module.module", [("name", "in", unknown)], ["name", "state"]
            )
            by_name.update({row["name"]: row for row in rows})
            unknown = [m for m in modules if m not in by_name]
            if unknown:
                raise PlanError(f"Módulos no disponibles en esta instancia: {unknown}")
        changes, to_install = [], []
        for name in modules:
            if name not in by_name:
                # En plan no se escribe: refrescar la lista queda para apply.
                changes.append(Change(INSTALL, "ir.module.module", name,
                                      note="no figura en la lista: se refresca al aplicar"))
                continue
            state = by_name[name]["state"]
            if state == "installed":
                changes.append(Change(OK, "ir.module.module", name))
            else:
                changes.append(Change(INSTALL, "ir.module.module", name, note=f"estado: {state}"))
                to_install.append(by_name[name]["id"])
        if apply and to_install:
            self.client.call("ir.module.module", "button_immediate_install", to_install)
            self._fields.clear()  # los modelos cambian al instalar módulos
        return changes

    # --------------------------------------------------------------- ajustes

    def reconcile_settings(self, settings: dict, apply: bool, modules_pending: bool) -> list[Change]:
        """Ajustes generales: se comparan con lo que muestra la pantalla de Ajustes.

        Al aplicar se hace lo mismo que el botón «Guardar»: un ``res.config.settings``
        con los valores que cambian y ``execute``. Los demás ajustes no se tocan
        porque el asistente arranca con los valores actuales.
        """
        if not settings:
            return []
        model = "res.config.settings"
        missing = [k for k in settings if k not in self.fields(model)]
        if missing:
            if modules_pending and not apply:
                return [Change(UPDATE, model, "ajustes",
                               note=f"disponibles al instalar los módulos: {', '.join(missing)}")]
            raise PlanError(f"ajustes inexistentes en {model}: {missing}")
        # Como al abrir la pantalla de Ajustes: un asistente nuevo (sin guardar) muestra los
        # valores actuales, incluidos los que vienen de la empresa (campos relacionados), que
        # default_get no trae. Es transitorio: Odoo lo borra solo.
        wizard = self.client.create(model, {})
        current = self.client.read(model, [wizard], list(settings))[0]
        change = Change(OK, model, "ajustes")
        for name, desired in settings.items():
            ftype = self.fields(model)[name]["type"]
            if self.normalize(ftype, current.get(name)) != self.normalize(ftype, desired):
                change.diff[name] = (current.get(name), desired)
        if change.diff:
            change.kind = UPDATE
            if apply:
                self.client.write(model, [wizard], {k: settings[k] for k in change.diff})
                self.client.call(model, "execute", [wizard])
                self._fields.clear()  # un ajuste puede instalar módulos
        return [change]

    # ------------------------------------------------------------- registros

    def reconcile_record(self, record: Record, apply: bool, modules_pending: bool) -> Change:
        change = Change(OK, record.model, record.id, source=record.source)
        try:
            self.fields(record.model)
        except OdooError:
            if modules_pending and not apply:
                self._planned[self.full_xmlid(record.id)] = None
                change.kind = CREATE
                change.note = "el modelo estará disponible al instalar los módulos"
                return change
            raise PlanError(f"{record.source}: el modelo {record.model} no existe") from None

        missing = [k for k in record.values if k not in self.fields(record.model)]
        if missing and modules_pending and not apply:
            # Campos que agrega un módulo que todavía no se instaló (p. ej. un addon propio).
            self._planned[self.full_xmlid(record.id)] = self.existing_id(record)
            change.kind = UPDATE if self._planned[self.full_xmlid(record.id)] else CREATE
            change.note = f"campos disponibles al instalar los módulos: {', '.join(missing)}"
            return change

        resolved = {k: self.resolve_value(record, k, v) for k, v in record.values.items()}
        res_id = self.existing_id(record)

        if res_id is None:
            res_id = self.find_match(record, resolved)
            if res_id is None:
                change.kind = CREATE
                change.diff = {k: (None, self.display(record, k, v)) for k, v in resolved.items()}
                if apply:
                    new_id = self.client.create(record.model, self.to_write(record, resolved))
                    self.link_xmlid(record, new_id)
                else:
                    self._planned[self.full_xmlid(record.id)] = None
                return change
            change.kind = ADOPT
            if apply:
                self.link_xmlid(record, res_id)
            else:
                self._planned[self.full_xmlid(record.id)] = res_id

        if record.noupdate and change.kind != ADOPT:
            change.note = "noupdate: no se sobrescriben cambios hechos en Odoo"
            return change
        if record.noupdate:
            return change

        change.diff = self.diff(record, res_id, resolved)
        if change.diff:
            for name, (old, new) in change.diff.items():
                if isinstance(record.values.get(name), Archivo) and old:
                    old = "(otro archivo)"  # no se muestra el base64 entero
                change.diff[name] = (old, self.display(record, name, new))
            if change.kind == OK:
                change.kind = UPDATE
            if apply:
                vals = self.to_write(record, {k: resolved[k] for k in change.diff})
                self.client.write(record.model, [res_id], vals)
        return change

    def run(self, state: DesiredState, apply: bool = False) -> Result:
        """Calcula (y opcionalmente aplica) los cambios, en orden."""
        self._planned.clear()
        result = Result()
        result.changes.extend(self.reconcile_modules(state.modules, apply))
        modules_pending = any(c.kind == INSTALL for c in result.changes)
        self._modules_pending = modules_pending and not apply  # al aplicar ya están instalados
        result.changes.extend(self.reconcile_settings(state.settings, apply, modules_pending))
        for record in state.records:
            result.changes.append(self.reconcile_record(record, apply, modules_pending))
        return result
