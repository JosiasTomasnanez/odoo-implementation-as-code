#!/usr/bin/env bash
# Funciones comunes. Uso: STACK=lab|onprem source infra/scripts/lib.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKER_DIR="$REPO_ROOT/infra/docker"
STACK="${STACK:-lab}"

case "$STACK" in
  lab)
    ENV_FILE="$DOCKER_DIR/lab.env"
    COMPOSE_FILES=(-f "$DOCKER_DIR/compose.yml" -f "$DOCKER_DIR/compose.lab.yml")
    DB_NAME="${DB_NAME:-lab}"
    ;;
  onprem)
    ENV_FILE="${ONPREM_ENV_FILE:-/etc/odoo-comercio/onprem.env}"
    COMPOSE_FILES=(-f "$DOCKER_DIR/compose.yml" -f "$DOCKER_DIR/compose.onprem.yml")
    DB_NAME="${DB_NAME:-produccion}"
    ;;
  *) echo "STACK desconocido: $STACK (lab|onprem)" >&2; exit 1 ;;
esac

# Código Enterprise (opcional), en el entorno o en el .env del repo (fuera del repo, es privado):
# - ODOO_ENTERPRISE_ADDONS: clon de github.com/odoo/enterprise (forma preferida, 26/10;
#   compose.enterprise-git.yml). En el servidor va en onprem.env y se copia en la imagen.
# - ODOO_ENTERPRISE_SRC: paquete descomprimido de odoo.com (Community + Enterprise; compose.enterprise.yml).
for variable in ODOO_ENTERPRISE_ADDONS ODOO_ENTERPRISE_SRC; do
  if [ -z "${!variable:-}" ] && [ -f "$REPO_ROOT/.env" ]; then
    valor="$(sed -n "s/^$variable=//p" "$REPO_ROOT/.env" | tail -1)"
    [ -n "$valor" ] && printf -v "$variable" '%s' "$valor"
  fi
done
if [ -z "${ODOO_ENTERPRISE_ADDONS:-}" ] && [ -f "$ENV_FILE" ]; then
  ODOO_ENTERPRISE_ADDONS="$(sed -n 's/^ODOO_ENTERPRISE_ADDONS=//p' "$ENV_FILE" | tail -1)"
fi
# Clave y modelos de la IA (Gemini, ADR 0018): del entorno o del .env del repo (nunca en git)
for variable in GEMINI_API_KEY GEMINI_MODEL GEMINI_MODEL_RESPALDO GEMINI_PEDIDOS_POR_MINUTO; do
  if [ -z "${!variable:-}" ] && [ -f "$REPO_ROOT/.env" ]; then
    valor="$(sed -n "s/^$variable=//p" "$REPO_ROOT/.env" | tail -1)"
    [ -n "$valor" ] && export "$variable=$valor"
  fi
done
if [ -n "${ODOO_ENTERPRISE_ADDONS:-}" ]; then
  [ -d "$ODOO_ENTERPRISE_ADDONS/web_studio" ] || { echo "ODOO_ENTERPRISE_ADDONS no es el clon de Enterprise: $ODOO_ENTERPRISE_ADDONS" >&2; exit 1; }
  export ODOO_ENTERPRISE_ADDONS
  # Lab: se monta. Servidor: compose.onprem.yml lo copia en la imagen (no hace falta este archivo)
  if [ "$STACK" = lab ]; then COMPOSE_FILES+=(-f "$DOCKER_DIR/compose.enterprise-git.yml"); fi
elif [ -n "${ODOO_ENTERPRISE_SRC:-}" ]; then
  [ -d "$ODOO_ENTERPRISE_SRC/odoo/addons" ] || { echo "ODOO_ENTERPRISE_SRC no tiene odoo/addons: $ODOO_ENTERPRISE_SRC" >&2; exit 1; }
  export ODOO_ENTERPRISE_SRC
  COMPOSE_FILES+=(-f "$DOCKER_DIR/compose.enterprise.yml")
fi

# Conector de la tienda online (ADR 0033, compose.tienda.yml): con TIENDA=1 en onprem.env
# (servidor) o en el .env del repo (lab).
if [ -z "${TIENDA:-}" ]; then
  if [ "$STACK" = onprem ] && [ -r "$ENV_FILE" ]; then
    TIENDA="$(sed -n 's/^TIENDA=//p' "$ENV_FILE" | tail -1)"
  elif [ "$STACK" = lab ] && [ -f "$REPO_ROOT/.env" ]; then
    TIENDA="$(sed -n 's/^TIENDA=//p' "$REPO_ROOT/.env" | tail -1)"
  fi
fi
if [ "${TIENDA:-0}" = 1 ]; then
  COMPOSE_FILES+=(-f "$DOCKER_DIR/compose.tienda.yml")
  if [ "$STACK" = onprem ]; then export CONECTOR_TIENDA_ENV="${CONECTOR_TIENDA_ENV:-/etc/odoo-comercio/conector-tienda.env}"
  else export CONECTOR_TIENDA_ENV="${CONECTOR_TIENDA_ENV:-$DOCKER_DIR/conector-tienda.lab.env}"; fi
fi

# Monitoreo (ADR 0028, compose.monitoreo.yml): con MONITOREO=1 en el entorno, en onprem.env
# (servidor, lo pone configurar-monitoreo.sh) o en el .env del repo (lab). `make lab-monitoreo`
# lo prende solo para ese comando. Sin la variable, el stack es el de siempre.
if [ -z "${MONITOREO:-}" ]; then
  if [ "$STACK" = onprem ] && [ -r "$ENV_FILE" ]; then
    MONITOREO="$(sed -n 's/^MONITOREO=//p' "$ENV_FILE" | tail -1)"
  elif [ "$STACK" = lab ] && [ -f "$REPO_ROOT/.env" ]; then
    MONITOREO="$(sed -n 's/^MONITOREO=//p' "$REPO_ROOT/.env" | tail -1)"
  fi
fi
if [ "${MONITOREO:-0}" = 1 ]; then
  COMPOSE_FILES+=(-f "$DOCKER_DIR/compose.monitoreo.yml")
  export MONITOREO_DB="$DB_NAME"
  if [ "$STACK" = lab ]; then
    COMPOSE_FILES+=(-f "$DOCKER_DIR/compose.monitoreo-lab.yml")
    export MONITOREO_ENV_FILE="${MONITOREO_ENV_FILE:-$DOCKER_DIR/monitoreo/lab/monitoreo.env}"
    # Otro archivo de avisos (p. ej. un Discord de prueba): MONITOREO_AVISOS_ENV en el .env del repo
    if [ -z "${MONITOREO_AVISOS_ENV:-}" ] && [ -f "$REPO_ROOT/.env" ]; then
      MONITOREO_AVISOS_ENV="$(sed -n 's/^MONITOREO_AVISOS_ENV=//p' "$REPO_ROOT/.env" | tail -1)"
    fi
    export AVISOS_ENV_FILE="${MONITOREO_AVISOS_ENV:-$DOCKER_DIR/monitoreo/lab/avisos.env}"
    export MONITOREO_METRICAS_DIR="${MONITOREO_METRICAS_DIR:-$DOCKER_DIR/monitoreo/lab/metricas}"
  else
    export MONITOREO_ENV_FILE="${MONITOREO_ENV_FILE:-/etc/odoo-comercio/monitoreo.env}"
    export AVISOS_ENV_FILE="${AVISOS_ENV_FILE:-/etc/odoo-comercio/avisos.env}"
  fi
fi

# Acceso desde fuera del local (ADR 0020, compose.acceso-remoto.yml): túnel de Cloudflare. Solo
# en el servidor (necesita el proxy), con ACCESO_REMOTO=1 en onprem.env (lo pone
# configurar-acceso-remoto.sh). En el lab se prueba con un cloudflared suelto (acceso-remoto.md).
if [ "$STACK" = onprem ] && [ -z "${ACCESO_REMOTO:-}" ] && [ -r "$ENV_FILE" ]; then
  ACCESO_REMOTO="$(sed -n 's/^ACCESO_REMOTO=//p' "$ENV_FILE" | tail -1)"
fi
if [ "$STACK" = onprem ] && [ "${ACCESO_REMOTO:-0}" = 1 ]; then
  COMPOSE_FILES+=(-f "$DOCKER_DIR/compose.acceso-remoto.yml")
fi

# Usuarios de PostgreSQL del monitoreo (idempotente): «monitoreo» (pg_monitor, para el
# exportador) y «grafana_lector» (solo lectura de las columnas que usan los tableros).
monitoreo_usuarios() {
  local clave_monitoreo clave_lector
  clave_monitoreo="$(sed -n 's/^PG_MONITOREO_CLAVE=//p' "$MONITOREO_ENV_FILE" | tail -1)"
  clave_lector="$(sed -n 's/^GRAFANA_DB_CLAVE=//p' "$MONITOREO_ENV_FILE" | tail -1)"
  [ -n "$clave_monitoreo" ] && [ -n "$clave_lector" ] || { echo "Faltan claves en $MONITOREO_ENV_FILE" >&2; return 1; }
  # Las claves van por la entrada (no en la línea de comandos, que se ve con ps)
  { printf '\\set clave_monitoreo %s\n\\set clave_lector %s\n\\set base %s\n' \
      "$clave_monitoreo" "$clave_lector" "$DB_NAME"
    cat "$DOCKER_DIR/monitoreo/usuarios.sql"
  } | compose exec -T db psql -q -U odoo -d "$DB_NAME" -v ON_ERROR_STOP=1
}

compose() {
  docker compose --project-directory "$DOCKER_DIR" --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" "$@"
}

# Ejecuta el binario odoo con la configuración del entorno, sin levantar el servidor.
odoo_cli() {
  compose run --rm -T --no-deps --entrypoint odoo odoo "$@"
}

log() { echo "==> $*" >&2; }
