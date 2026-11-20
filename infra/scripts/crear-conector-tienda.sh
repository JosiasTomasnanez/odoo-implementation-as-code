#!/usr/bin/env bash
# Crea (o renueva) el usuario técnico del conector de la tienda online y su clave de API
# (ADR 0033). Idempotente: si el usuario existe, le deja solo los permisos mínimos y le cambia la
# clave (la anterior deja de servir). Guarda la clave en el archivo de entorno del conector, que
# queda solo legible por su dueño; la clave no se muestra.
#
# Uso:  STACK=lab    infra/scripts/crear-conector-tienda.sh
#       STACK=onprem sudo -E infra/scripts/crear-conector-tienda.sh   (en el servidor)
#
# Lab:    infra/docker/conector-tienda.lab.env   (fuera de git)
# Server: /etc/odoo-comercio/conector-tienda.env
# Si el archivo no tiene CONECTOR_SECRETO, se genera uno nuevo y se avisa que hay que cargarlo
# también en la tienda (npx wrangler secret put CONECTOR_SECRETO).
set -euo pipefail
source "$(dirname "$0")/lib.sh"

if [ "$STACK" = onprem ]; then ARCHIVO=/etc/odoo-comercio/conector-tienda.env; else ARCHIVO="$DOCKER_DIR/conector-tienda.lab.env"; fi
umask 077
touch "$ARCHIVO"; chmod 600 "$ARCHIVO"

CODIGO='
import datetime
Users = env["res.users"].sudo()
grupo = env.ref("comercio_tienda.group_tienda_conector")
u = Users.with_context(active_test=False).search([("login", "=", "conector-tienda")], limit=1)
grupos = [(6, 0, [env.ref("base.group_portal").id, grupo.id])]
if not u:
    u = Users.create({"name": "Conector de la tienda online", "login": "conector-tienda", "group_ids": grupos})
else:
    u.write({"active": True, "group_ids": grupos})
env["res.users.apikeys"].sudo().search([("user_id", "=", u.id)]).unlink()
vence = datetime.datetime.now() + datetime.timedelta(days=365)
clave = env["res.users.apikeys"].with_user(u).sudo()._generate("rpc", "conector-tienda", vence)
env.cr.commit()
print("CLAVE=" + clave)
'
SALIDA="$(printf '%s' "$CODIGO" | compose exec -T odoo odoo shell -c /etc/odoo/odoo.conf -d "$DB_NAME" --no-http 2>/dev/null | sed -n 's/^CLAVE=//p' | tail -1)"
[ -n "$SALIDA" ] || { echo "No se pudo crear la clave (¿está instalado comercio_tienda?)" >&2; exit 1; }

poner() {  # poner VARIABLE valor  (reemplaza o agrega, sin mostrar el valor)
  local tmp; tmp="$(mktemp)"
  grep -v "^$1=" "$ARCHIVO" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > "$ARCHIVO"; rm -f "$tmp"
}
poner ODOO_API_KEY "$SALIDA"
grep -q '^ODOO_DB=' "$ARCHIVO" || poner ODOO_DB "$DB_NAME"
grep -q '^ODOO_URL=' "$ARCHIVO" || poner ODOO_URL "http://odoo:8069"
if ! grep -q '^CONECTOR_SECRETO=' "$ARCHIVO"; then
  poner CONECTOR_SECRETO "$(openssl rand -hex 32)"
  echo "Se generó un CONECTOR_SECRETO nuevo en $ARCHIVO: cargalo también en la tienda"
  echo "  (cd web/tienda && npx wrangler secret put CONECTOR_SECRETO)  y pegá el valor del archivo."
fi
grep -q '^TIENDA_URL=' "$ARCHIVO" || echo "Falta TIENDA_URL en $ARCHIVO (p. ej. https://demo.comercio-ejemplo.example)"
echo "Listo: usuario «conector-tienda» con permisos mínimos; clave nueva (vence en 1 año) en $ARCHIVO"
