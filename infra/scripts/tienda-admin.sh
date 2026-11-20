#!/usr/bin/env bash
# Primer administrador de la tienda (fase 7): lo agrega con permiso «admin» en la base de la tienda.
# Después entra a /admin/ingresar → «Primera vez o me olvidé la contraseña» (le llega un código) y
# desde «Equipo» suma al resto. Solo hace falta para el primero (o si nadie puede entrar).
#
# Uso: make tienda-admin EMAIL=daniel@ejemplo.com NOMBRE="Daniel"   (base: la de wrangler.jsonc)
set -euo pipefail
EMAIL="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
NOMBRE="${2:-}"
[[ "$EMAIL" =~ ^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$ ]] || { echo "EMAIL inválido" >&2; exit 2; }
[[ "$NOMBRE" =~ ^[[:alpha:][:space:].\'-]{2,80}$ ]] || { echo "NOMBRE inválido (solo letras y espacios)" >&2; exit 2; }
NOMBRE="${NOMBRE//\'/\'\'}"
ID="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
cd "$(dirname "$0")/../../web/tienda"
PATH="$HOME/.local/node22/bin:$PATH" npx wrangler d1 execute comercio-ejemplo-tienda-demo --remote --command \
  "INSERT INTO equipo (id, email, nombre, roles, creado, creado_por) VALUES ('$ID', '$EMAIL', '$NOMBRE', 'admin', datetime('now'), 'make tienda-admin')
   ON CONFLICT(email) DO UPDATE SET roles = 'admin', activo = 1" >/dev/null
echo "Listo: $EMAIL es administrador. Que entre a /admin/ingresar → «Primera vez o me olvidé la contraseña»."
