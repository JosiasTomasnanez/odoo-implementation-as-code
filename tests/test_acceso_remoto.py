"""Pruebas de infra/servidor/acceso_remoto_cloudflare.py (ADR 0020) con una API de Cloudflare
falsa en memoria: armado de los pedidos, lectura de mails e idempotencia (la segunda corrida no
cambia nada)."""

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "infra" / "servidor"))
import acceso_remoto_cloudflare as ar  # noqa: E402

CUENTA, ZONA = "cuenta1", "zona1"


def test_leer_mails():
    texto = "# comentario\nAna@Ejemplo.com\n\nbeto@ejemplo.com  # caja\nana@ejemplo.com\n"
    assert ar.leer_mails(texto) == ["ana@ejemplo.com", "beto@ejemplo.com"]
    with pytest.raises(ValueError, match="línea 2"):
        ar.leer_mails("ana@ejemplo.com\nbeto sin arroba\n")


def test_zonas_y_team():
    assert ar.zonas_candidatas("remoto.comercio-ejemplo.example") == ["remoto.comercio-ejemplo.example", "comercio-ejemplo.example"]
    assert ar.team_de("ejemplo.cloudflareaccess.com") == "ejemplo"


def test_segundos():
    assert ar.segundos("24h") == ar.segundos("24h0m0s") == 86400
    assert ar.segundos("90ms") == pytest.approx(0.09)
    assert ar.segundos("24 horas") is None


def test_politica_mails_y_pais():
    p = ar.payload_politica("remoto.x.com", ["a@x.com", "b@x.com"], "ar", "24h")
    assert p["decision"] == "allow"
    assert p["include"] == [{"email": {"email": "a@x.com"}}, {"email": {"email": "b@x.com"}}]
    assert p["require"] == [{"geo": {"country_code": "AR"}}]
    # Cloudflare devuelve la duración normalizada: sigue siendo «igual»
    assert ar.politica_igual({**p, "session_duration": "24h0m0s"}, p)
    assert not ar.politica_igual({**p, "include": p["include"][:1]}, p)
    with pytest.raises(ValueError):
        ar.payload_politica("remoto.x.com", [], "AR", "24h")


def test_ingress_https_verifica_certificado_y_access():
    c = ar.payload_ingress("remoto.x.com", "https://proxy:443", "equipo", "aud1")["config"]["ingress"]
    assert c[0]["hostname"] == "remoto.x.com"
    assert c[0]["originRequest"]["originServerName"] == "remoto.x.com"
    assert "noTLSVerify" not in c[0]["originRequest"]
    assert c[0]["originRequest"]["access"] == {"required": True, "teamName": "equipo", "audTag": ["aud1"]}
    assert c[-1] == {"service": "http_status:404"}
    lab = ar.payload_ingress("p.x.com", "http://odoo:8069", "equipo", "aud1")["config"]["ingress"][0]
    assert "originServerName" not in lab["originRequest"]


class CloudflareFalso(ar.Cloudflare):
    """API en memoria con lo justo para configurar/borrar."""

    def __init__(self):
        super().__init__("token", simular=False)
        self.escrituras = []
        self.idps, self.tuneles, self.politicas, self.apps, self.dns = [], [], [], [], []
        self.config = {}
        self.n = 0

    def _id(self):
        self.n += 1
        return f"id{self.n}"

    def pedir(self, metodo, ruta, datos=None, consulta=None):
        consulta = consulta or {}
        if metodo != "GET":
            self.escrituras.append((metodo, ruta))
        if ruta == "/zones":
            zona = {"id": ZONA, "name": "x.com", "account": {"id": CUENTA}}
            return [zona] if consulta["name"] == "x.com" else []
        if ruta.endswith("/access/organizations"):
            return {"auth_domain": "equipo.cloudflareaccess.com"}
        if ruta.endswith("/identity_providers"):
            if metodo == "POST":
                self.idps.append({**datos, "id": self._id()})
                return self.idps[-1]
            return self.idps
        m = re.fullmatch(rf"/accounts/{CUENTA}/cfd_tunnel(?:/([^/]+))?(?:/(\w+))?", ruta)
        if m:
            tid, sub = m.groups()
            if sub == "configurations":
                self.config[tid] = datos
                return {}
            if sub == "token":
                return "TOKEN-" + tid
            if sub == "connections":
                return {}
            if metodo == "DELETE":
                self.tuneles = [t for t in self.tuneles if t["id"] != tid]
                return {}
            if metodo == "POST":
                self.tuneles.append({**datos, "id": self._id(), "status": "inactive"})
                return self.tuneles[-1]
            return [t for t in self.tuneles if t["name"] == consulta.get("name")]
        for lista, base in ((self.politicas, f"/accounts/{CUENTA}/access/policies"),
                            (self.apps, f"/accounts/{CUENTA}/access/apps"),
                            (self.dns, f"/zones/{ZONA}/dns_records")):
            if ruta == base and metodo == "GET":
                if "domain" in consulta:
                    return [a for a in lista if a["domain"] == consulta["domain"]]
                if "name" in consulta and base.endswith("dns_records"):
                    return [r for r in lista if r["name"] == consulta["name"]]
                return lista
            if ruta == base and metodo == "POST":
                lista.append({**datos, "id": self._id(), "aud": "aud-" + str(self.n)})
                return lista[-1]
            if ruta.startswith(base + "/"):
                rid = ruta.rsplit("/", 1)[1]
                i = next(i for i, x in enumerate(lista) if x["id"] == rid)
                if metodo == "DELETE":
                    lista.pop(i)
                    return {}
                lista[i] = {**lista[i], **datos}
                return lista[i]
        raise AssertionError(f"ruta no prevista: {metodo} {ruta}")


def _args(tmp_path, **extra):
    mails = tmp_path / "mails.txt"
    mails.write_text("ana@x.com\nbeto@x.com\n")
    return SimpleNamespace(nombre="remoto.x.com", tunel="servidor-prueba", origen="https://proxy:443",
                           mails=str(mails), tunel_env=str(tmp_path / "tunel.env"), pais="AR",
                           sesion="24h", **extra)


def test_configurar_es_idempotente_y_borrar_limpia(tmp_path, capsys):
    cf = CloudflareFalso()
    args = _args(tmp_path)
    ar.configurar(cf, args)
    assert (tmp_path / "tunel.env").read_text() == f"TUNNEL_TOKEN=TOKEN-{cf.tuneles[0]['id']}\n"
    assert (tmp_path / "tunel.env").stat().st_mode & 0o077 == 0
    assert cf.dns[0]["content"] == f"{cf.tuneles[0]['id']}.cfargotunnel.com" and cf.dns[0]["proxied"]
    assert cf.apps[0]["policies"] == [{"id": cf.politicas[0]["id"], "precedence": 1}]
    assert cf.apps[0]["allowed_idps"] == [cf.idps[0]["id"]]
    regla = cf.config[cf.tuneles[0]["id"]]["config"]["ingress"][0]
    assert regla["originRequest"]["access"]["audTag"] == [cf.apps[0]["aud"]]

    # Segunda corrida: solo la configuración del túnel se vuelve a mandar (PUT idéntico)
    cf.escrituras.clear()
    ar.configurar(cf, args)
    assert [m for m, r in cf.escrituras] == ["PUT"] and cf.escrituras[0][1].endswith("/configurations")

    # Un mail menos: se actualiza la política, nada más
    Path(args.mails).write_text("ana@x.com\n")
    cf.escrituras.clear()
    ar.configurar(cf, args)
    assert ("PUT", f"/accounts/{CUENTA}/access/policies/{cf.politicas[0]['id']}") in cf.escrituras
    assert cf.politicas[0]["include"] == [{"email": {"email": "ana@x.com"}}]

    ar.borrar(cf, args)
    assert not cf.apps and not cf.politicas and not cf.dns and not cf.tuneles


def test_no_pisa_un_registro_a(tmp_path):
    cf = CloudflareFalso()
    cf.dns.append({"id": "a1", "type": "A", "name": "remoto.x.com", "content": "192.168.1.10"})
    with pytest.raises(ar.ErrorCloudflare, match="registro A"):
        ar.configurar(cf, _args(tmp_path))
