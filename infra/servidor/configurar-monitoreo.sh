#!/bin/bash
# Monitoreo del servidor (ADR 0028), después de configurar-respaldo-y-avisos.sh
# (docs/runbooks/instalar-servidor.md, paso 11):
#   - claves nuevas en /etc/odoo-comercio/monitoreo.env (600); la de Grafana se muestra UNA vez;
#   - PostgreSQL con pg_stat_statements (reinicia la base unos segundos la primera vez);
#   - usuarios de la base: «monitoreo» (pg_monitor) y «grafana_lector» (solo lectura);
#   - MONITOREO=1 en onprem.env y el stack (Prometheus, exportadores, Grafana, relay a Discord);
#   - ufw: node_exporter solo desde la red interna del monitoreo;
#   - Grafana por Tailscale (`tailscale serve`, HTTPS en el nombre del servidor en la tailnet);
#   - la verificación (verificar-monitoreo.py).
#
# Uso (en el servidor, desde /opt/odoo-implementation):
#   sudo bash infra/servidor/configurar-monitoreo.sh --simular
#   sudo bash infra/servidor/configurar-monitoreo.sh
# Se puede correr varias veces: lo que ya está hecho se saltea. Para cambiar un umbral, editar
# infra/docker/monitoreo/umbrales.env (en git) y volver a correrlo.
set -euo pipefail

SIMULAR=0
[[ "${1:-}" == "--simular" ]] && SIMULAR=1
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
CONF=/etc/odoo-comercio
ONPREM_ENV="$CONF/onprem.env"
MONITOREO_ENV="$CONF/monitoreo.env"
METRICAS=/var/lib/odoo-comercio/metricas
PUERTO_TAILSCALE=8443   # 443 del servidor lo usa Caddy (HTTPS de Odoo en la red del local)
RED_MONITOREO=172.31.250.0/24
PUERTA_MONITOREO=172.31.250.1

paso() { echo; echo "== $*"; }
ok() { echo "   ✓ $*"; }
aviso() { echo "   ⚠ $*"; }
hacer() {  # muestra el comando; lo ejecuta salvo en --simular
    echo "   → $*"
    if [[ $SIMULAR -eq 0 ]]; then eval "$*"; fi
}
clave() { openssl rand -base64 33 | tr -d '/+=' | cut -c1-32; }

if [[ $EUID -ne 0 ]]; then echo "Correrlo con sudo: sudo bash $0 $*" >&2; exit 1; fi
[[ -f "$ONPREM_ENV" ]] || { echo "Falta $ONPREM_ENV: correr antes instalar-odoo.sh" >&2; exit 1; }
[[ $SIMULAR -eq 1 ]] && echo "MODO SIMULACIÓN: no se cambia nada."
if [[ ! -f "$CONF/avisos.env" ]]; then
    aviso "Falta $CONF/avisos.env: las alertas no van a salir. Correr antes configurar-respaldo-y-avisos.sh."
fi

# ---------------------------------------------------------------- claves
paso "Claves del monitoreo ($MONITOREO_ENV)"
if [[ -f "$MONITOREO_ENV" ]]; then
    ok "Ya están"
elif [[ $SIMULAR -eq 1 ]]; then
    echo "   → generaría las claves de PostgreSQL y de Grafana (la de Grafana, mostrarla una vez → Bitwarden)"
else
    ADMIN="$(clave)"
    umask 077
    cat > "$MONITOREO_ENV" <<FIN
# Monitoreo (ADR 0028). Permisos 600, nunca en git. La clave de Grafana está en Bitwarden
# («Servidor: Grafana admin»); las de PostgreSQL no hace falta anotarlas (se regeneran
# borrando este archivo y corriendo configurar-monitoreo.sh de nuevo).
MONITOREO_DB=produccion
PG_MONITOREO_CLAVE=$(clave)
GRAFANA_DB_CLAVE=$(clave)
# Solo vale la primera vez que arranca Grafana; después: docs/runbooks/monitoreo.md
GF_SECURITY_ADMIN_PASSWORD=$ADMIN
GF_SECURITY_COOKIE_SECURE=true
# Nombre al pie de las tarjetas de Discord (el mismo que usa avisar.sh)
AVISOS_SERVIDOR=$(sed -n 's/^AVISOS_SERVIDOR=//p' /etc/odoo-comercio/avisos.env 2>/dev/null | tail -1 | grep . || echo servidor-ejemplo)
FIN
    umask 022
    echo
    echo "   Grafana, usuario admin. GUARDAR AHORA EN BITWARDEN como «Servidor: Grafana admin»"
    echo "   (no se vuelve a mostrar): $ADMIN"
    read -rp "   Enter cuando esté guardada… " _
    unset ADMIN
    ok "Guardadas en $MONITOREO_ENV"
fi
[[ -f "$MONITOREO_ENV" ]] && chmod 600 "$MONITOREO_ENV"

# ---------------------------------------------------------------- métricas de los scripts
paso "Carpeta de métricas de los scripts (backups, registro de Odoo)"
if [[ -d "$METRICAS" ]]; then ok "Ya existe ($METRICAS)"
else hacer "install -d -m 755 $METRICAS"; fi

# ---------------------------------------------------------------- firewall
paso "Firewall: node_exporter solo desde la red del monitoreo"
if ufw status | grep -q "$PUERTA_MONITOREO 9100"; then
    ok "Ya permitido"
else
    hacer "ufw allow in on br-monitoreo from $RED_MONITOREO to $PUERTA_MONITOREO port 9100 proto tcp comment 'Prometheus lee node_exporter'"
fi

# ---------------------------------------------------------------- stack
paso "Monitoreo en onprem.env"
if grep -q '^MONITOREO=1' "$ONPREM_ENV"; then
    ok "Ya activado"
else
    hacer "sed -i '/^MONITOREO=/d' $ONPREM_ENV && printf '\n# Monitoreo (ADR 0028, compose.monitoreo.yml)\nMONITOREO=1\n' >> $ONPREM_ENV"
fi

paso "PostgreSQL con pg_stat_statements y usuarios del monitoreo"
cd "$REPO"
if [[ $SIMULAR -eq 1 ]]; then
    echo "   → compose up -d --wait db (si cambió la configuración, la base se reinicia unos segundos)"
    echo "   → usuarios «monitoreo» y «grafana_lector» (infra/docker/monitoreo/usuarios.sql)"
else
    # shellcheck source=/dev/null
    MONITOREO=1 STACK=onprem source infra/scripts/lib.sh
    compose up -d --wait db
    monitoreo_usuarios
    ok "Usuarios listos (solo lectura para Grafana)"
fi

paso "Prometheus, exportadores, Grafana y relay a Discord"
if [[ $SIMULAR -eq 1 ]]; then
    echo "   → compose up -d --wait (y se recrea Grafana para tomar umbrales y tableros)"
else
    compose up -d --wait
    compose up -d --wait --force-recreate grafana relay-discord
    compose ps --format '   {{.Service}}: {{.Status}}' | grep -E 'prometheus|grafana|exporter|cadvisor|blackbox|relay'
fi

# ---------------------------------------------------------------- Tailscale
paso "Grafana por Tailscale (https, solo la red de Tailscale)"
URL=""
if ! command -v tailscale >/dev/null || ! tailscale status >/dev/null 2>&1; then
    aviso "Tailscale no está conectado: Grafana queda solo en el servidor (ssh -L 3000:127.0.0.1:3000)."
else
    NOMBRE="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
    URL="https://$NOMBRE:$PUERTO_TAILSCALE/"
    if ! ufw status | grep -q "$PUERTO_TAILSCALE/tcp on tailscale0"; then
        hacer "ufw allow in on tailscale0 to any port $PUERTO_TAILSCALE proto tcp comment 'Grafana por Tailscale'"
    fi
    # Si la tailnet no tiene HTTPS activado, tailscale muestra el link para activarlo
    hacer "tailscale serve --bg --https=$PUERTO_TAILSCALE http://127.0.0.1:3000"
    if ! grep -q "^GF_SERVER_ROOT_URL=$URL\$" "$MONITOREO_ENV" 2>/dev/null; then
        hacer "sed -i '/^GF_SERVER_ROOT_URL=/d' $MONITOREO_ENV && echo 'GF_SERVER_ROOT_URL=$URL' >> $MONITOREO_ENV"
        [[ $SIMULAR -eq 0 ]] && compose up -d --wait --force-recreate grafana
    fi
    ok "Grafana: $URL"
fi

# ---------------------------------------------------------------- verificación
paso "Verificación"
if [[ $SIMULAR -eq 1 ]]; then
    echo "   → python3 infra/scripts/verificar-monitoreo.py --stack onprem"
elif python3 "$REPO/infra/scripts/verificar-monitoreo.py" --stack onprem | sed 's/^/   /'; then
    ok "Monitoreo verificado"
else
    aviso "Algo no está bien (arriba, qué). Grafana tarda un minuto en evaluar las reglas: probar de nuevo con"
    aviso "sudo make verify-monitoreo STACK=onprem"
fi

paso "Listo"
cat <<FIN
   Grafana: ${URL:-http://127.0.0.1:3000 (por ssh -L)} · usuario admin · clave en Bitwarden «Servidor: Grafana admin».
   Probar los avisos: Grafana → Alertas → Puntos de contacto → «avisos» → Probar (llega a Discord).
   Uso diario: docs/runbooks/monitoreo.md
FIN
