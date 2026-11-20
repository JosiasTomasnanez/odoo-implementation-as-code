"""Carga de entornos (``environments/<nombre>.yaml``) y secretos.

Un entorno describe *dónde* se aplica la configuración (URL, base, protocolo)
y *qué capas* de configuración le corresponden. Los secretos nunca se guardan
en el YAML: se leen de variables de entorno o de un archivo ``.env`` local
(ignorado por git).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class SettingsError(ValueError):
    """Configuración de entorno inválida o incompleta."""


@dataclass
class Environment:
    name: str
    url: str
    database: str
    protocol: str = "json2"
    login: str = "admin"
    api_key_env: str = ""
    lang: str = "es_AR"
    layers: list[Path] = field(default_factory=list)
    values: list[Path] = field(default_factory=list)   # archivos de valores (ADR 0010)
    root: Path = ROOT

    @property
    def api_key(self) -> str:
        if not self.api_key_env:
            raise SettingsError(f"El entorno {self.name!r} no define api_key_env")
        value = os.environ.get(self.api_key_env)
        if not value:
            raise SettingsError(
                f"Falta la variable {self.api_key_env} (definirla en el entorno o en .env)"
            )
        return value


def load_dotenv(path: Path) -> None:
    """Carga un ``.env`` simple (CLAVE=valor) sin pisar variables ya definidas."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_environment(name: str, root: Path = ROOT) -> Environment:
    load_dotenv(root / ".env")
    path = root / "environments" / f"{name}.yaml"
    if not path.is_file():
        available = sorted(p.stem for p in (root / "environments").glob("*.yaml"))
        raise SettingsError(f"No existe el entorno {name!r}. Disponibles: {available}")
    data = yaml.safe_load(path.read_text()) or {}
    missing = [k for k in ("url", "database") if not data.get(k)]
    if missing:
        raise SettingsError(f"{path}: faltan claves obligatorias {missing}")
    layers = [root / layer for layer in data.pop("layers", [])]
    for layer in layers:
        if not layer.is_dir():
            raise SettingsError(f"{path}: la capa {layer} no existe")
    values = [root / v for v in data.pop("values", [])]
    for v in values:
        if not v.is_file():
            raise SettingsError(f"{path}: el archivo de valores {v} no existe")
    known = set(Environment.__dataclass_fields__) - {"name", "layers", "values", "root"}
    unknown = set(data) - known
    if unknown:
        raise SettingsError(f"{path}: claves desconocidas {sorted(unknown)}")
    return Environment(name=name, layers=layers, values=values, root=root, **data)
