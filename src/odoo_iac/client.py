"""Cliente mínimo para la API externa de Odoo.

Soporta dos transportes con la misma interfaz:

* ``json2``: API JSON-2 (``/json/2/<modelo>/<método>``), disponible desde Odoo 19.
  Es la API recomendada; XML-RPC/JSON-RPC están deprecados y Odoo anunció su
  eliminación en versiones futuras.
* ``xmlrpc``: API clásica, para versiones anteriores o como alternativa.

Ambos funcionan en Odoo Online y On-Premise. Todas las llamadas usan argumentos
por nombre (requisito de JSON-2), así el resto del código no depende del
transporte.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import xmlrpc.client
from typing import Any


class OdooError(RuntimeError):
    """Error devuelto por Odoo o por el transporte."""


class Json2Transport:
    def __init__(self, url: str, database: str, api_key: str, timeout: float = 600):
        # Plazo amplio: instalar un módulo (p. ej. stock en Odoo 20) puede tardar minutos.
        self.url = url.rstrip("/")
        self.database = database
        self.api_key = api_key
        self.timeout = timeout

    def call(self, model: str, method: str, ids: list[int] | None, kwargs: dict) -> Any:
        body = dict(kwargs)
        if ids is not None:
            body["ids"] = ids
        request = urllib.request.Request(
            f"{self.url}/json/2/{model}/{method}",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": f"bearer {self.api_key}",
                "X-Odoo-Database": self.database,
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "odoo-iac",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            try:
                payload = json.loads(detail)
                detail = payload.get("message") or detail
            except ValueError:
                pass
            raise OdooError(f"{model}.{method}: HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise OdooError(f"No se pudo conectar a {self.url}: {exc.reason}") from None


class XmlRpcTransport:
    def __init__(self, url: str, database: str, login: str, api_key: str):
        self.url = url.rstrip("/")
        self.database = database
        self.api_key = api_key
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        try:
            self.uid = common.authenticate(database, login, api_key, {})
        except (OSError, xmlrpc.client.Error) as exc:
            raise OdooError(f"No se pudo conectar a {self.url}: {exc}") from None
        if not self.uid:
            raise OdooError("Autenticación XML-RPC rechazada (login o API key inválidos)")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    def call(self, model: str, method: str, ids: list[int] | None, kwargs: dict) -> Any:
        args = [ids] if ids is not None else []
        try:
            return self.models.execute_kw(
                self.database, self.uid, self.api_key, model, method, args, kwargs
            )
        except xmlrpc.client.Fault as exc:
            raise OdooError(f"{model}.{method}: {exc.faultString.strip().splitlines()[-1]}") from None


class OdooClient:
    """Fachada con las operaciones que usa la herramienta."""

    def __init__(self, transport, context: dict | None = None):
        self.transport = transport
        self.context = context or {}

    def call(self, model: str, method: str, ids: list[int] | None = None, **kwargs) -> Any:
        kwargs.setdefault("context", self.context)
        return self.transport.call(model, method, ids, kwargs)

    def search_read(self, model: str, domain: list, fields: list[str], **kwargs) -> list[dict]:
        return self.call(model, "search_read", domain=domain, fields=fields, **kwargs)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self.call(model, "read", ids, fields=fields)

    def create(self, model: str, vals: dict) -> int:
        result = self.call(model, "create", vals_list=[vals])
        return result[0] if isinstance(result, list) else result

    def write(self, model: str, ids: list[int], vals: dict) -> None:
        self.call(model, "write", ids, vals=vals)

    def fields_get(self, model: str) -> dict[str, dict]:
        return self.call(
            model,
            "fields_get",
            attributes=["type", "relation", "string", "required", "readonly", "translate"],
        )

    def version(self) -> str:
        rows = self.search_read("ir.module.module", [("name", "=", "base")], ["latest_version"])
        return rows[0]["latest_version"] if rows else "?"


def connect(env) -> OdooClient:
    """Crea un cliente a partir de un :class:`odoo_iac.settings.Environment`."""
    if env.protocol == "json2":
        transport = Json2Transport(env.url, env.database, env.api_key)
    elif env.protocol == "xmlrpc":
        transport = XmlRpcTransport(env.url, env.database, env.login, env.api_key)
    else:
        raise OdooError(f"Protocolo desconocido: {env.protocol!r} (usar json2 o xmlrpc)")
    context = {"lang": env.lang} if env.lang else {}
    return OdooClient(transport, context)
