#!/usr/bin/env bash
# Crea desde cero la base del laboratorio y una API key para odoo-iac.
# Uso: infra/scripts/lab-init.sh   (destruye la base "lab" si existe)
STACK=lab source "$(dirname "$0")/lib.sh"

# Si Odoo quedó corriendo, conservaría conexiones a la base que se va a recrear.
log "Deteniendo Odoo (si estaba corriendo)"
compose stop odoo

log "Levantando PostgreSQL"
compose up -d --wait db

log "Creando base '$DB_NAME' (es_AR, Argentina, sin datos demo)"
odoo_cli db -c /etc/odoo/odoo.conf init "$DB_NAME" \
  --force --language es_AR --country AR --username admin --password admin

log "Generando API key para odoo-iac"
KEY="$(odoo_cli shell -c /etc/odoo/odoo.conf -d "$DB_NAME" --no-http --log-level=warn <<'PY' | grep '^APIKEY=' | cut -d= -f2
admin = env.ref("base.user_admin")
# Odoo 20 exige un scope; "rpc" habilita JSON-2 y XML-RPC.
key = env["res.users.apikeys"].with_user(admin).sudo()._generate("rpc", "odoo-iac lab", None)
env.cr.commit()
print(f"APIKEY={key}")
PY
)"
[ -n "$KEY" ] || { echo "No se pudo generar la API key" >&2; exit 1; }

ENV_LOCAL="$REPO_ROOT/.env"
touch "$ENV_LOCAL"
grep -v '^ODOO_LAB_API_KEY=' "$ENV_LOCAL" > "$ENV_LOCAL.tmp" || true
echo "ODOO_LAB_API_KEY=$KEY" >> "$ENV_LOCAL.tmp"
mv "$ENV_LOCAL.tmp" "$ENV_LOCAL"
chmod 600 "$ENV_LOCAL"

log "Levantando Odoo"
compose up -d --wait odoo
log "Listo: http://localhost:8069 (admin/admin). API key guardada en .env"
log "Siguiente paso: make plan ENV=lab && make apply ENV=lab"
