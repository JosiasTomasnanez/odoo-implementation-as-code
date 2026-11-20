"""Tailscale para la PC de ferretería (02/11, `docs/runbooks/acceso-remoto.md`).

Deja en la política de Tailscale:

1. la etiqueta `tag:ferreteria` (la asignan los administradores del tailnet);
2. la regla «todos con todos» (`src: ["*"]`) cambiada a `autogroup:member`, para que los equipos
   con etiqueta no queden incluidos (no son miembros);
3. una regla: `tag:ferreteria` → solo el 443 del servidor (Odoo), por su IP de Tailscale.

Y, con --clave, crea una clave de un solo uso con esa etiqueta (vale 7 días) y la guarda en un
archivo 600: se usa una vez en la PC (`tailscale up --auth-key=…`) y se borra.

Con --simular solo lee y muestra qué cambiaría. Se puede correr varias veces: si la política ya
está, no se toca. La política se escribe como JSON: los comentarios del archivo HuJSON se pierden
(se guarda una copia de la anterior al lado de la clave).

API de Tailscale v2 (tailnet «-» = el del token):
- GET  /tailnet/-/devices                         (IP del servidor)
- GET  /tailnet/-/acl  (Accept: application/json) (política y su ETag)
- POST /tailnet/-/acl/validate                    (revisar antes de guardar)
- POST /tailnet/-/acl  (If-Match: ETag)           (guardar)
- POST /tailnet/-/keys                            (clave de un solo uso con etiqueta)

Uso (desde la notebook del técnico; el token se genera en el panel → Settings → Keys →
Generate access token, y no se guarda en ningún lado):

    TAILSCALE_API_TOKEN=tskey-api-… python3 infra/servidor/tailscale_ferreteria.py --simular
    TAILSCALE_API_TOKEN=tskey-api-… python3 infra/servidor/tailscale_ferreteria.py \
        --clave ~/clave-ferreteria.txt

Solo biblioteca estándar.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.tailscale.com/api/v2/tailnet/-"
ETIQUETA = "tag:ferreteria"
SERVIDOR = "servidor-ejemplo"
DUENOS = ["autogroup:admin"]


class ErrorTailscale(Exception):
    pass


# ---------------------------------------------------------------- funciones puras (con pruebas)


# Orígenes que incluirían a la PC con etiqueta en una regla ajena
ABARCAN_ETIQUETA = {"*", "autogroup:tagged", ETIQUETA}


def politica_con_ferreteria(politica: dict, ip_servidor: str) -> dict:
    """La política con la etiqueta de ferretería, limitada al 443 del servidor. Acepta las dos
    formas de Tailscale (`grants` nuevas y `acls` viejas). No modifica la que recibe.

    El «*» de cualquier origen pasa a `autogroup:member` (los equipos con etiqueta no son
    miembros). Si otra regla nombra `autogroup:tagged` o la etiqueta, no se adivina: error, para
    revisarla a mano. Al final se comprueba que la etiqueta solo aparezca en su propia regla."""
    nueva = copy.deepcopy(politica)
    duenos = nueva.setdefault("tagOwners", {})
    duenos.setdefault(ETIQUETA, list(DUENOS))
    usa_grants = "grants" in nueva or "acls" not in nueva
    clave = "grants" if usa_grants else "acls"
    if usa_grants:
        propia = {"src": [ETIQUETA], "dst": [ip_servidor], "ip": ["tcp:443"]}
    else:
        propia = {"action": "accept", "src": [ETIQUETA], "dst": [f"{ip_servidor}:443"]}
    reglas = [r for r in nueva.setdefault(clave, []) if r.get("src") != [ETIQUETA]]
    for regla in reglas:
        origenes = list(regla.get("src", []))
        if "*" in origenes:
            origenes = list(dict.fromkeys("autogroup:member" if o == "*" else o for o in origenes))
            regla["src"] = origenes
        ajenos = ABARCAN_ETIQUETA & set(origenes)
        if ajenos:
            raise ErrorTailscale(f"Una regla ya incluye {sorted(ajenos)}: revisarla a mano antes ({regla}).")
    nueva[clave] = reglas + [propia]
    _comprobar_solo_propia(nueva[clave], propia)
    return nueva


def _comprobar_solo_propia(reglas: list[dict], propia: dict) -> None:
    for regla in reglas:
        if regla is not propia and ABARCAN_ETIQUETA & set(regla.get("src", [])):
            raise ErrorTailscale(f"La etiqueta quedaría incluida en otra regla: {regla}")


def servidor(dispositivos: list[dict], nombre: str = SERVIDOR) -> dict:
    """El servidor en la lista de equipos: por el nombre de MagicDNS (`servidor-ejemplo.….ts.net`,
    único en el tailnet), no por el hostname que elige cada equipo. Si hay más de uno, error."""
    candidatos = [d for d in dispositivos if str(d.get("name", "")).split(".")[0] == nombre]
    if not candidatos:
        raise ErrorTailscale(f"No está «{nombre}» en el tailnet (¿con otro nombre?).")
    if len(candidatos) > 1:
        raise ErrorTailscale(f"Hay {len(candidatos)} equipos llamados «{nombre}»: "
                             + ", ".join(f"{d.get('name')} ({d.get('nodeId')})" for d in candidatos))
    return candidatos[0]


def ip_del_servidor(dispositivos: list[dict], nombre: str = SERVIDOR) -> str:
    """La IPv4 de Tailscale del servidor (100.x.y.z)."""
    for direccion in servidor(dispositivos, nombre).get("addresses", []):
        if "." in direccion:
            return direccion
    raise ErrorTailscale(f"«{nombre}» no tiene IPv4 de Tailscale.")


def pedido_de_clave() -> dict:
    return {"capabilities": {"devices": {"create": {
        "reusable": False, "ephemeral": False, "preauthorized": True, "tags": [ETIQUETA]}}},
        "expirySeconds": 7 * 24 * 3600, "description": "PC de ferreteria"}


# ---------------------------------------------------------------- API


def _pedir(token: str, metodo: str, ruta: str, cuerpo=None, encabezados=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    pedido = urllib.request.Request(API + ruta, data=datos, method=metodo, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json",
        **({"Content-Type": "application/json"} if datos else {}), **(encabezados or {})})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as respuesta:
            texto = respuesta.read().decode()
            return (json.loads(texto) if texto else {}), respuesta.headers.get("ETag")
    except urllib.error.HTTPError as error:
        raise ErrorTailscale(f"{metodo} {ruta}: HTTP {error.code}: {error.read().decode()[:300]}") from None


def main() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    argumentos.add_argument("--simular", action="store_true", help="solo mostrar qué cambiaría")
    argumentos.add_argument("--clave", type=Path,
                            help="crear una clave de un solo uso y guardarla en este archivo")
    opciones = argumentos.parse_args()
    token = os.environ.get("TAILSCALE_API_TOKEN", "").strip()
    if not token:
        print("Falta TAILSCALE_API_TOKEN (panel de Tailscale → Settings → Keys → Generate access token).",
              file=sys.stderr)
        return 2
    try:
        dispositivos, _ = _pedir(token, "GET", "/devices")
        equipos = dispositivos.get("devices", [])
        ip = ip_del_servidor(equipos)
        elegido = servidor(equipos)
        print(f"Servidor: {elegido.get('name')} · id {elegido.get('nodeId')} · de {elegido.get('user')} · "
              f"{ip} (confirmar que es el del local)")
        actual, etag = _pedir(token, "GET", "/acl")
        nueva = politica_con_ferreteria(actual, ip)
        if nueva == actual:
            print("Política: ya está (no se toca).")
        else:
            print("Política nueva:\n" + json.dumps(nueva, indent=2, ensure_ascii=False))
            resultado, _ = _pedir(token, "POST", "/acl/validate", nueva)
            if resultado.get("message"):
                raise ErrorTailscale(f"Tailscale no acepta la política: {resultado}")
            if opciones.simular:
                print("Simulación: la política no se guardó.")
            else:
                carpeta = opciones.clave.parent if opciones.clave else Path.home()
                copia = carpeta / "tailscale-politica-anterior.json"
                copia.write_text(json.dumps(actual, indent=2, ensure_ascii=False))
                _pedir(token, "POST", "/acl", nueva, {"If-Match": etag} if etag else None)
                print(f"Política guardada (la anterior quedó en {copia}).")
        if opciones.clave:
            if opciones.simular:
                print(f"Simulación: no se crea la clave ({opciones.clave}).")
            else:
                clave, _ = _pedir(token, "POST", "/keys", pedido_de_clave())
                opciones.clave.touch(mode=0o600)
                opciones.clave.write_text(clave["key"] + "\n")
                print(f"Clave de un solo uso (7 días) en {opciones.clave}: usarla en la PC y borrar "
                      "el archivo.")
    except ErrorTailscale as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
