"""Cloudflare para el acceso desde fuera del local (ADR 0020): túnel, DNS y Access.

Lo llama infra/servidor/configurar-acceso-remoto.sh (que explica el uso). Deja, para un nombre
(por defecto remoto.comercio-ejemplo.example):

1. el túnel `servidor-ejemplo`, administrado desde Cloudflare (config_src=cloudflare), y su
   token en un archivo con UNA línea `TUNNEL_TOKEN=…` (lo lee compose.acceso-remoto.yml);
2. la aplicación de Access del nombre: código por mail (One-time PIN), sesión de 24 h y una
   política reutilizable: mails autorizados (de un archivo fuera del repo) Y desde Argentina;
3. las reglas del túnel: ese nombre → el proxy (https, verificando el certificado), solo con el
   permiso de Access ya comprobado por cloudflared; el resto → 404;
4. el DNS: CNAME del nombre → <túnel>.cfargotunnel.com, con proxy (nube naranja).

Con --borrar deshace todo (aplicación, política, DNS y túnel). Con --simular solo lee y muestra
qué cambiaría. Se puede correr varias veces: lo que ya está igual no se toca.

API de Cloudflare v4 (verificada el 27/10 en developers.cloudflare.com/api):
- GET  /zones?name=…                                  (zona y su cuenta)
- GET  /accounts/{a}/access/organizations             (dominio del equipo: auth_domain)
- GET|POST /accounts/{a}/access/identity_providers    (type=onetimepin, config={})
- GET|POST /accounts/{a}/cfd_tunnel?name=…&is_deleted=false   (config_src=cloudflare)
- GET  /accounts/{a}/cfd_tunnel/{t}/token             (result = token)
- PUT  /accounts/{a}/cfd_tunnel/{t}/configurations    (config.ingress)
- GET|POST|PUT|DELETE /accounts/{a}/access/policies   (políticas reutilizables)
- GET|POST|PUT|DELETE /accounts/{a}/access/apps       (self_hosted; policies = [{id, precedence}])
- GET|POST|PUT|DELETE /zones/{z}/dns_records
- DELETE /accounts/{a}/cfd_tunnel/{t}/connections y DELETE /accounts/{a}/cfd_tunnel/{t}

Solo biblioteca estándar. El token de la API llega por la variable CLOUDFLARE_ACCESS_TOKEN y no
se guarda en ningún lado.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.cloudflare.com/client/v4"
NOMBRE_APP = "Odoo desde afuera"
NOMBRE_IDP = "Código por mail"
MAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErrorCloudflare(Exception):
    pass


# ---------------------------------------------------------------- funciones puras (con pruebas)


def leer_mails(texto: str) -> list[str]:
    """Mails autorizados de un texto: uno por línea, `#` comenta. Minúsculas, sin repetir,
    ordenados. Un renglón que no es un mail es un error (mejor frenar que dejar a alguien afuera
    o adentro por un error de tipeo)."""
    mails = set()
    for numero, linea in enumerate(texto.splitlines(), 1):
        linea = linea.split("#", 1)[0].strip().lower()
        if not linea:
            continue
        if not MAIL_RE.match(linea):
            raise ValueError(f"línea {numero}: «{linea}» no es un mail")
        mails.add(linea)
    return sorted(mails)


def zonas_candidatas(nombre: str) -> list[str]:
    """remoto.comercio-ejemplo.example → [remoto.comercio-ejemplo.example, comercio-ejemplo.example]."""
    partes = nombre.lower().strip(".").split(".")
    return [".".join(partes[i:]) for i in range(len(partes) - 1)]


def segundos(duracion: str | None) -> float | None:
    """Duración al estilo de Go («24h», «24h0m0s», «90m») en segundos; None si no se entiende."""
    if not duracion:
        return None
    partes = re.findall(r"(\d+(?:\.\d+)?)(ms|us|µs|ns|h|m|s)", duracion)
    if not partes or "".join(n + u for n, u in partes) != duracion:
        return None
    factor = {"h": 3600, "m": 60, "s": 1, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}
    return sum(float(n) * factor[u] for n, u in partes)


def nombre_politica(nombre: str) -> str:
    return f"Personal autorizado ({nombre})"


def payload_politica(nombre: str, mails: list[str], pais: str, sesion: str) -> dict:
    """Política reutilizable: incluye cualquiera de los mails (OR) y exige el país (AND)."""
    if not mails:
        raise ValueError("no hay mails autorizados")
    return {
        "name": nombre_politica(nombre),
        "decision": "allow",
        "include": [{"email": {"email": m}} for m in mails],
        "require": [{"geo": {"country_code": pais.upper()}}],
        "exclude": [],
        "session_duration": sesion,
    }


def politica_igual(actual: dict, deseada: dict) -> bool:
    """Compara lo que importa de la política (mails, país, decisión, sesión)."""

    def mails(p):
        return sorted(r["email"]["email"].lower() for r in p.get("include") or [] if "email" in r)

    def paises(p):
        return sorted(r["geo"]["country_code"].upper() for r in p.get("require") or [] if "geo" in r)

    return (
        actual.get("decision") == deseada["decision"]
        and mails(actual) == mails(deseada)
        and len(actual.get("include") or []) == len(deseada["include"])
        and paises(actual) == paises(deseada)
        and len(actual.get("require") or []) == len(deseada["require"])
        and not actual.get("exclude")
        and segundos(actual.get("session_duration")) == segundos(deseada["session_duration"])
    )


def payload_app(nombre: str, idp_id: str, politica_id: str, sesion: str) -> dict:
    """Aplicación de Access del nombre: solo código por mail, directo a pedirlo."""
    return {
        "name": NOMBRE_APP,
        "type": "self_hosted",
        "domain": nombre,
        "session_duration": sesion,
        "allowed_idps": [idp_id],
        "auto_redirect_to_identity": True,
        "app_launcher_visible": False,
        "http_only_cookie_attribute": True,
        "same_site_cookie_attribute": "lax",
        "policies": [{"id": politica_id, "precedence": 1}],
    }


def app_igual(actual: dict, deseada: dict) -> bool:
    politicas = [p.get("id") for p in actual.get("policies") or []]
    return (
        all(actual.get(k) == deseada[k] for k in deseada if k not in ("policies", "session_duration"))
        and segundos(actual.get("session_duration")) == segundos(deseada["session_duration"])
        and politicas == [p["id"] for p in deseada["policies"]]
    )


def payload_ingress(nombre: str, origen: str, team: str, aud: str) -> dict:
    """Reglas del túnel. Con origen https se verifica el certificado del proxy con el mismo
    nombre (Let's Encrypt); cloudflared además exige el permiso de Access de esta aplicación."""
    origin: dict = {"access": {"required": True, "teamName": team, "audTag": [aud]}}
    if origen.startswith("https://"):
        origin["originServerName"] = nombre
    return {
        "config": {
            "ingress": [
                {"hostname": nombre, "service": origen, "originRequest": origin},
                {"service": "http_status:404"},
            ]
        }
    }


def payload_dns(nombre: str, tunel_id: str) -> dict:
    return {
        "type": "CNAME",
        "name": nombre,
        "content": f"{tunel_id}.cfargotunnel.com",
        "proxied": True,
        "ttl": 1,
        "comment": "Túnel al servidor del local (ADR 0020; configurar-acceso-remoto.sh)",
    }


def team_de(auth_domain: str) -> str:
    """ejemplo.cloudflareaccess.com → ejemplo."""
    return auth_domain.split(".", 1)[0]


# ---------------------------------------------------------------- API


class Cloudflare:
    def __init__(self, token: str, simular: bool):
        self.token = token
        self.simular = simular

    def pedir(self, metodo: str, ruta: str, datos=None, consulta: dict | None = None):
        if consulta:
            ruta += "?" + urllib.parse.urlencode(consulta)
        if metodo != "GET" and self.simular:
            print(f"   → (simulación) {metodo} {ruta.split('?')[0]}")
            return {"id": "<nuevo>", "aud": "<nuevo>"}
        req = urllib.request.Request(
            API + ruta,
            method=metodo,
            data=json.dumps(datos).encode() if datos is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                respuesta = json.load(r)
        except urllib.error.HTTPError as e:
            try:
                respuesta = json.load(e)
            except ValueError:
                raise ErrorCloudflare(f"{metodo} {ruta}: HTTP {e.code}") from None
        if not respuesta.get("success"):
            errores = "; ".join(f"{x.get('code')}: {x.get('message')}" for x in respuesta.get("errors") or [])
            raise ErrorCloudflare(f"{metodo} {ruta.split('?')[0]}: {errores or respuesta}")
        return respuesta.get("result")

    def todos(self, ruta: str, consulta: dict | None = None) -> list:
        """GET con páginas (las listas de Cloudflare vienen de a una página)."""
        resultado, pagina = [], 1
        while True:
            parte = self.pedir("GET", ruta, consulta={**(consulta or {}), "page": pagina, "per_page": 100})
            resultado += parte or []
            if not parte or len(parte) < 100:
                return resultado
            pagina += 1


def ok(texto: str) -> None:
    print(f"   ✓ {texto}")


def paso(texto: str) -> None:
    print(f"\n== {texto}")


def buscar_zona(cf: Cloudflare, nombre: str) -> dict:
    for candidata in zonas_candidatas(nombre):
        zonas = cf.pedir("GET", "/zones", consulta={"name": candidata})
        if zonas:
            return zonas[0]
    raise ErrorCloudflare(f"El token no ve ninguna zona que contenga {nombre} (permiso Zone → DNS → Edit)")


def buscar_tuneles(cf: Cloudflare, cuenta: str, nombre: str) -> list:
    consulta = {"name": nombre, "is_deleted": "false"}
    return cf.pedir("GET", f"/accounts/{cuenta}/cfd_tunnel", consulta=consulta) or []


def buscar_apps(cf: Cloudflare, cuenta: str, nombre: str) -> list:
    apps = cf.pedir("GET", f"/accounts/{cuenta}/access/apps", consulta={"domain": nombre, "exact": "true"})
    return [a for a in apps or [] if a.get("domain") == nombre]


def configurar(cf: Cloudflare, args) -> None:
    mails = leer_mails(open(args.mails, encoding="utf-8").read())
    paso(f"Cloudflare para {args.nombre}")
    zona = buscar_zona(cf, args.nombre)
    cuenta = zona["account"]["id"]
    ok(f"Zona {zona['name']} (cuenta {zona['account'].get('name') or cuenta})")
    ok(f"{len(mails)} mail(s) autorizado(s) en {args.mails}")

    try:
        org = cf.pedir("GET", f"/accounts/{cuenta}/access/organizations")
    except ErrorCloudflare as e:
        raise ErrorCloudflare(
            f"{e}\n   ¿Está activado Zero Trust? dash.cloudflare.com → Zero Trust → elegir el nombre del "
            "equipo y el plan Free. ¿El token tiene «Access: Organizations, Identity Providers, and Groups»?"
        ) from None
    auth_domain = (org or {}).get("auth_domain")
    if not auth_domain:
        raise ErrorCloudflare("Zero Trust no está activado: dash.cloudflare.com → Zero Trust (plan Free)")
    team = team_de(auth_domain)
    ok(f"Equipo de Zero Trust: {auth_domain}")

    paso("Inicio de sesión con código por mail (One-time PIN)")
    idps = cf.todos(f"/accounts/{cuenta}/access/identity_providers")
    otp = next((i for i in idps if i.get("type") == "onetimepin"), None)
    if otp:
        ok(f"Ya está («{otp['name']}»)")
    else:
        otp = cf.pedir(
            "POST", f"/accounts/{cuenta}/access/identity_providers",
            {"name": NOMBRE_IDP, "type": "onetimepin", "config": {}},
        )
        ok("Creado")

    paso(f"Túnel «{args.tunel}»")
    tuneles = buscar_tuneles(cf, cuenta, args.tunel)
    if tuneles:
        tunel = tuneles[0]
        if tunel.get("config_src") != "cloudflare":
            raise ErrorCloudflare(f"El túnel {args.tunel} existe pero se administra con un archivo local "
                                  "(config_src=local): borrarlo o elegir otro nombre (--tunel)")
        ok(f"Ya existe ({tunel['id']}, estado {tunel.get('status')})")
    else:
        datos = {"name": args.tunel, "config_src": "cloudflare"}
        tunel = cf.pedir("POST", f"/accounts/{cuenta}/cfd_tunnel", datos)
        ok(f"Creado ({tunel['id']})")

    paso("Política: mails autorizados y solo desde " + args.pais.upper())
    deseada = payload_politica(args.nombre, mails, args.pais, args.sesion)
    politicas = cf.todos(f"/accounts/{cuenta}/access/policies")
    politica = next((p for p in politicas if p.get("name") == deseada["name"]), None)
    if politica and politica_igual(politica, deseada):
        ok("Ya estaba igual")
    elif politica:
        cf.pedir("PUT", f"/accounts/{cuenta}/access/policies/{politica['id']}", deseada)
        ok("Actualizada")
    else:
        politica = cf.pedir("POST", f"/accounts/{cuenta}/access/policies", deseada)
        ok("Creada")

    paso(f"Aplicación de Access para {args.nombre}")
    deseada_app = payload_app(args.nombre, otp["id"], politica["id"], args.sesion)
    apps = buscar_apps(cf, cuenta, args.nombre)
    app = apps[0] if apps else None
    if app and app_igual(app, deseada_app):
        ok("Ya estaba igual")
    elif app:
        app = cf.pedir("PUT", f"/accounts/{cuenta}/access/apps/{app['id']}", deseada_app) or app
        ok("Actualizada")
    else:
        app = cf.pedir("POST", f"/accounts/{cuenta}/access/apps", deseada_app)
        ok("Creada")

    paso(f"Reglas del túnel: {args.nombre} → {args.origen}")
    cf.pedir("PUT", f"/accounts/{cuenta}/cfd_tunnel/{tunel['id']}/configurations",
             payload_ingress(args.nombre, args.origen, team, app.get("aud", "<nuevo>")))
    ok("Aplicadas (con permiso de Access exigido también en el túnel)")

    paso(f"DNS: {args.nombre} → túnel (nube naranja)")
    dns = payload_dns(args.nombre, tunel["id"])
    registros = cf.pedir("GET", f"/zones/{zona['id']}/dns_records", consulta={"name": args.nombre})
    otros = [r for r in registros or [] if r["type"] != "CNAME"]
    if otros:
        otro = otros[0]
        raise ErrorCloudflare(f"{args.nombre} ya tiene un registro {otro['type']} → {otro['content']}: "
                              "borrarlo a mano si sobra (no se pisa)")
    cname = (registros or [None])[0]
    if cname and cname["content"] == dns["content"] and cname.get("proxied"):
        ok("Ya estaba")
    elif cname:
        cf.pedir("PUT", f"/zones/{zona['id']}/dns_records/{cname['id']}", dns)
        ok(f"Actualizado (antes → {cname['content']})")
    else:
        cf.pedir("POST", f"/zones/{zona['id']}/dns_records", dns)
        ok("Creado")

    paso(f"Token del túnel → {args.tunel_env}")
    if cf.simular:
        print("   → (simulación) se guardaría TUNNEL_TOKEN=… (una sola línea)")
    else:
        token = cf.pedir("GET", f"/accounts/{cuenta}/cfd_tunnel/{tunel['id']}/token")
        contenido = f"TUNNEL_TOKEN={token}\n"
        anterior = open(args.tunel_env).read() if os.path.exists(args.tunel_env) else None
        if anterior == contenido:
            ok("Ya estaba")
        else:
            viejo = os.umask(0o077)
            try:
                with open(args.tunel_env, "w") as f:
                    f.write(contenido)
            finally:
                os.umask(viejo)
            ok("Guardado (solo ese archivo; el token de la API no se guarda)")
    print(f"\n   Entrada: https://{args.nombre} (pide el código en https://{auth_domain})")


def borrar(cf: Cloudflare, args) -> None:
    paso(f"Borrar el acceso de {args.nombre} en Cloudflare")
    zona = buscar_zona(cf, args.nombre)
    cuenta = zona["account"]["id"]

    apps = buscar_apps(cf, cuenta, args.nombre)
    for app in apps:
        cf.pedir("DELETE", f"/accounts/{cuenta}/access/apps/{app['id']}")
        ok(f"Aplicación de Access «{app.get('name')}» borrada")

    for p in cf.todos(f"/accounts/{cuenta}/access/policies"):
        if p.get("name") == nombre_politica(args.nombre):
            cf.pedir("DELETE", f"/accounts/{cuenta}/access/policies/{p['id']}")
            ok(f"Política «{p['name']}» borrada")

    tuneles = buscar_tuneles(cf, cuenta, args.tunel)
    destinos = {f"{t['id']}.cfargotunnel.com" for t in tuneles}
    for r in cf.pedir("GET", f"/zones/{zona['id']}/dns_records", consulta={"name": args.nombre}) or []:
        if r["type"] == "CNAME" and r["content"] in destinos:
            cf.pedir("DELETE", f"/zones/{zona['id']}/dns_records/{r['id']}")
            ok(f"DNS {args.nombre} borrado")
        else:
            print(f"   ⚠ {args.nombre}: registro {r['type']} → {r['content']}, no es del túnel: se deja")

    for t in tuneles:
        # Un túnel con conexiones no se borra: se cortan (el contenedor ya debería estar parado)
        cf.pedir("DELETE", f"/accounts/{cuenta}/cfd_tunnel/{t['id']}/connections")
        cf.pedir("DELETE", f"/accounts/{cuenta}/cfd_tunnel/{t['id']}")
        ok(f"Túnel «{t['name']}» borrado")
    if not tuneles:
        ok(f"No había túnel «{args.tunel}»")
    print("   (El inicio con código por mail queda: es de la cuenta y no molesta.)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--nombre", required=True)
    p.add_argument("--tunel", required=True)
    p.add_argument("--origen", required=True)
    p.add_argument("--mails", required=True)
    p.add_argument("--tunel-env", required=True)
    p.add_argument("--pais", default="AR")
    p.add_argument("--sesion", default="168h")
    p.add_argument("--simular", action="store_true")
    p.add_argument("--borrar", action="store_true")
    args = p.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)  # que los errores salgan después de los pasos
    token = os.environ.get("CLOUDFLARE_ACCESS_TOKEN", "")
    if not token:
        print("Falta CLOUDFLARE_ACCESS_TOKEN", file=sys.stderr)
        return 1
    cf = Cloudflare(token, args.simular)
    try:
        (borrar if args.borrar else configurar)(cf, args)
    except (ErrorCloudflare, ValueError, OSError) as e:
        print(f"\n   ✗ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
