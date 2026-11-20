"""Estado deseado: lectura y validación de las capas de configuración.

Cada capa es un directorio con archivos YAML que se procesan en orden
alfabético (por eso se prefijan con números: ``00-modulos.yaml``,
``10-categorias.yaml``...). Hay dos tipos de archivo:

Módulos a instalar::

    modules:
      - stock
      - point_of_sale

Ajustes generales (``res.config.settings``, lo que Odoo muestra en *Ajustes*)::

    settings:
      group_product_pricelist: true   # activa las listas de precios

Registros de un modelo::

    model: product.category
    match: [name]          # opcional: cómo adoptar registros que ya existen
    records:
      - id: cat_mascotas   # identificador estable (se guarda como xml_id iac.cat_mascotas)
        values:
          name: Mascotas
          parent_id: {ref: cat_raiz}

Una capa posterior puede redefinir un registro con el mismo ``id``: sus
``values`` se combinan con los anteriores. Así una capa ``online`` u
``onpremise`` ajusta la visión funcional común sin duplicarla.

Valores centralizados (ADR 0010): en ``values`` se puede escribir
``{valor: puestos.mostrador_1}`` y se reemplaza por ese dato de los archivos de
valores del entorno (p. ej. ``config/valores.yaml``), como el ``values.yaml``
de Helm. Así lo que cambia seguido (nombres, márgenes...) se edita en un solo
archivo comentado. Un valor inexistente es un error: nunca se aplica vacío.

Archivos (imágenes, p. ej. el logo del ticket): ``{archivo: ../imagenes/logo.png}``
se reemplaza por el contenido del archivo en base64, que es como Odoo recibe los
campos binarios. La ruta es relativa al YAML que la usa.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ID_RE = re.compile(r"^[a-z0-9_]+$")
RECORD_KEYS = {"id", "values", "noupdate"}


class StateError(ValueError):
    """Archivo de configuración inválido."""


@dataclass
class Record:
    id: str
    model: str
    values: dict
    match: list[str] = field(default_factory=list)
    noupdate: bool = False
    source: str = ""


@dataclass
class DesiredState:
    modules: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    records: list[Record] = field(default_factory=list)


def _merge(base: dict, override: dict) -> dict:
    """Combina mapeos recursivamente: ``override`` pisa a ``base`` clave por clave."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_values(files: list[Path]) -> dict:
    """Lee y combina los archivos de valores en orden (el último gana)."""
    values: dict = {}
    for path in files:
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as exc:
            raise StateError(f"{path}: YAML inválido: {exc}") from None
        if not isinstance(data, dict):
            raise StateError(f"{path}: se esperaba un mapeo en la raíz")
        values = _merge(values, data)
    return values


def _lookup(values: dict, dotted: str, where: str):
    current = values
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise StateError(f"{where}: el valor {dotted!r} no está definido en los archivos de valores")
        current = current[part]
    return current


class Archivo(str):
    """Contenido de un archivo en base64; recuerda la ruta para mostrarla en el plan."""

    ruta: str

    def __new__(cls, contenido: str, ruta: str):
        obj = super().__new__(cls, contenido)
        obj.ruta = ruta
        return obj


def _read_file(base: Path, ruta, where: str) -> Archivo:
    if not isinstance(ruta, str):
        raise StateError(f"{where}: {{archivo: ...}} espera una ruta como texto")
    path = base / ruta
    if not path.is_file():
        raise StateError(f"{where}: el archivo {ruta!r} no existe ({path})")
    return Archivo(base64.b64encode(path.read_bytes()).decode("ascii"), ruta)


def _substitute(obj, values: dict, where: str, base: Path):
    """Reemplaza cada ``{valor: ruta.con.puntos}`` por el dato correspondiente y cada
    ``{archivo: ruta}`` por el contenido del archivo (relativo a ``base``)."""
    if isinstance(obj, dict):
        if set(obj) == {"valor"}:
            if not isinstance(obj["valor"], str):
                raise StateError(f"{where}: {{valor: ...}} espera una ruta como texto")
            return _lookup(values, obj["valor"], where)
        if set(obj) == {"archivo"}:
            return _read_file(base, obj["archivo"], where)
        return {key: _substitute(value, values, where, base) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_substitute(item, values, where, base) for item in obj]
    return obj


def _load_file(path: Path, state: DesiredState, index: dict[str, Record], values_data: dict) -> None:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise StateError(f"{path}: YAML inválido: {exc}") from None
    if data is None:
        return
    if not isinstance(data, dict):
        raise StateError(f"{path}: se esperaba un mapeo en la raíz")

    if "modules" in data:
        if set(data) != {"modules"} or not isinstance(data["modules"], list):
            raise StateError(f"{path}: un archivo de módulos solo contiene 'modules: [...]'")
        for name in data["modules"]:
            if name not in state.modules:
                state.modules.append(name)
        return

    if "settings" in data:
        if set(data) != {"settings"} or not isinstance(data["settings"], dict):
            raise StateError(f"{path}: un archivo de ajustes solo contiene 'settings: {{...}}'")
        state.settings.update(_substitute(data["settings"], values_data, str(path), path.parent))
        return

    model = data.get("model")
    if not model:
        raise StateError(f"{path}: falta 'model' (o 'modules' / 'settings')")
    unknown = set(data) - {"model", "match", "records"}
    if unknown:
        raise StateError(f"{path}: claves desconocidas {sorted(unknown)}")
    match = data.get("match") or []
    for position, raw in enumerate(data.get("records") or [], start=1):
        where = f"{path}#{position}"
        if not isinstance(raw, dict) or "id" not in raw:
            raise StateError(f"{where}: cada registro necesita 'id'")
        extra = set(raw) - RECORD_KEYS
        if extra:
            raise StateError(f"{where}: claves desconocidas {sorted(extra)} (¿faltó 'values'?)")
        record_id = str(raw["id"])
        if not ID_RE.match(record_id):
            raise StateError(f"{where}: id {record_id!r} inválido (usar minúsculas, dígitos y _)")
        values = raw.get("values") or {}
        if not isinstance(values, dict):
            raise StateError(f"{where}: 'values' debe ser un mapeo")
        values = _substitute(values, values_data, where, path.parent)

        previous = index.get(record_id)
        if previous:
            if previous.model != model:
                raise StateError(
                    f"{where}: id {record_id!r} ya definido para {previous.model} "
                    f"en {previous.source}"
                )
            previous.values.update(values)
            previous.match = match or previous.match
            previous.noupdate = bool(raw.get("noupdate", previous.noupdate))
            previous.source += f" + {where}"
            continue
        record = Record(
            id=record_id,
            model=model,
            values=dict(values),
            match=list(match),
            noupdate=bool(raw.get("noupdate", False)),
            source=where,
        )
        index[record_id] = record
        state.records.append(record)


def load_state(layers: list[Path], values_files: list[Path] | None = None) -> DesiredState:
    values_data = load_values(values_files or [])
    state = DesiredState()
    index: dict[str, Record] = {}
    for layer in layers:
        for path in sorted(layer.rglob("*.yaml")):
            _load_file(path, state, index, values_data)
    return state
