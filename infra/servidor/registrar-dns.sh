#!/bin/bash
# Crea o actualiza en Cloudflare el registro A del nombre de Odoo con la IP del servidor en el
# local (ADR 0013, modo dominio). Así las PCs encuentran el servidor sin tocar el router ni el
# archivo hosts de cada una. Nube gris («DNS only»): Cloudflare solo responde la IP privada,
# no pasa tráfico ni publica nada.
#
# Uso: registrar-dns.sh <nombre> [ip]          (ip: por defecto, la del servidor en la red local)
#      registrar-dns.sh --borrar <nombre>
# Token: CLOUDFLARE_API_TOKEN del entorno o de /etc/odoo-comercio/proxy.env (permiso
# «Zone → DNS → Edit» solo sobre la zona). Se puede correr varias veces.
set -euo pipefail

PROXY_ENV="${PROXY_ENV:-/etc/odoo-comercio/proxy.env}"
if [[ -z "${CLOUDFLARE_API_TOKEN:-}" && -r "$PROXY_ENV" ]]; then
    CLOUDFLARE_API_TOKEN="$(sed -n 's/^CLOUDFLARE_API_TOKEN=//p' "$PROXY_ENV" | tail -1)"
fi
[[ -n "${CLOUDFLARE_API_TOKEN:-}" ]] || { echo "Falta CLOUDFLARE_API_TOKEN ($PROXY_ENV)" >&2; exit 1; }
export CLOUDFLARE_API_TOKEN

BORRAR=0
[[ "${1:-}" == "--borrar" ]] && { BORRAR=1; shift; }
NOMBRE="${1:?falta el nombre, p. ej. odoo.comercio-ejemplo.example}"
IP="${2:-}"
if [[ $BORRAR -eq 0 && -z "$IP" ]]; then
    # La IP con que el servidor sale a la red local (no la de Docker ni la de Tailscale)
    IP="$(ip -4 route get 1.1.1.1 | sed -n 's/.* src \([0-9.]*\).*/\1/p')"
fi
[[ $BORRAR -eq 1 || "$IP" =~ ^[0-9]+(\.[0-9]+){3}$ ]] || { echo "IP inválida: «$IP»" >&2; exit 1; }

NOMBRE="$NOMBRE" IP="$IP" BORRAR="$BORRAR" python3 - <<'PY'
import json, os, sys, urllib.request

API = "https://api.cloudflare.com/client/v4"
nombre, ip, borrar = os.environ["NOMBRE"], os.environ["IP"], os.environ["BORRAR"] == "1"

def pedir(metodo, ruta, datos=None):
    req = urllib.request.Request(API + ruta, method=metodo,
                                 data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"Authorization": "Bearer " + os.environ["CLOUDFLARE_API_TOKEN"],
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            respuesta = json.load(r)
    except urllib.error.HTTPError as e:
        respuesta = json.load(e)
    if not respuesta.get("success"):
        sys.exit(f"Cloudflare: {respuesta.get('errors')}")
    return respuesta["result"]

# La zona es el dominio que contiene al nombre (odoo.comercio-ejemplo.example → comercio-ejemplo.example)
partes = nombre.split(".")
zona = None
for i in range(len(partes) - 1):
    encontradas = pedir("GET", "/zones?name=" + ".".join(partes[i:]))
    if encontradas:
        zona = encontradas[0]["id"]
        break
if not zona:
    sys.exit(f"El token no ve ninguna zona que contenga {nombre}")

registros = pedir("GET", f"/zones/{zona}/dns_records?type=A&name={nombre}")
if borrar:
    for r in registros:
        pedir("DELETE", f"/zones/{zona}/dns_records/{r['id']}")
    print(f"✓ {nombre}: registro borrado" if registros else f"✓ {nombre}: no había registro")
    sys.exit(0)

datos = {"type": "A", "name": nombre, "content": ip, "ttl": 300, "proxied": False,
         "comment": "Servidor de Odoo en el local (IP privada; infra/servidor/registrar-dns.sh)"}
if not registros:
    pedir("POST", f"/zones/{zona}/dns_records", datos)
    print(f"✓ {nombre} → {ip} (creado)")
elif registros[0]["content"] == ip and not registros[0]["proxied"]:
    print(f"✓ {nombre} → {ip} (ya estaba)")
else:
    pedir("PUT", f"/zones/{zona}/dns_records/{registros[0]['id']}", datos)
    print(f"✓ {nombre} → {ip} (actualizado; antes {registros[0]['content']})")
PY
