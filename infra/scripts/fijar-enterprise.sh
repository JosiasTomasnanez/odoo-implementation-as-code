#!/usr/bin/env bash
# Deja el clon de Enterprise (github.com/odoo/enterprise, rama 20.0) en el último cambio del día
# de la imagen oficial de Odoo que se usa, para que Community y Enterprise sean de la misma fecha.
# La fecha sale de la etiqueta: odoo:20.0-20261015 → 2026-10-15.
#
# Uso: infra/scripts/fijar-enterprise.sh <carpeta del clon> <imagen>
#   infra/scripts/fijar-enterprise.sh /mnt/datos1/odoo-enterprise-git odoo:20.0-20261015
# Para actualizar Odoo: cambiar ODOO_IMAGE (lab.env / onprem.env), correr esto y reconstruir.
set -euo pipefail

CLON="${1:?falta la carpeta del clon de Enterprise}"
IMAGEN="${2:?falta la imagen (p. ej. odoo:20.0-20261015)}"
[[ "$IMAGEN" =~ :([0-9]+\.[0-9]+)-([0-9]{4})([0-9]{2})([0-9]{2})$ ]] \
  || { echo "La imagen tiene que tener fecha (odoo:20.0-AAAAMMDD), no «$IMAGEN»." >&2; exit 1; }
RAMA="${BASH_REMATCH[1]}"
FECHA="${BASH_REMATCH[2]}-${BASH_REMATCH[3]}-${BASH_REMATCH[4]}"

cd "$CLON"
git rev-parse --git-dir >/dev/null
# El clon puede ser superficial (--depth 1): se trae la historia desde un mes antes
DESDE="$(date -d "$FECHA -31 days" +%Y-%m-%d)"
# Sin terminal para pedir usuario: si GitHub no entra, sigue con lo descargado (no se cuelga)
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes" \
  git fetch --quiet --shallow-since="$DESDE" origin "$RAMA" \
  || echo "Sin conexión con GitHub: se usa lo que ya está descargado." >&2
COMMIT="$(git rev-list -1 --before="$FECHA 23:59:59" "origin/$RAMA")"
[[ -n "$COMMIT" ]] || { echo "No hay cambios de Enterprise $RAMA hasta el $FECHA." >&2; exit 1; }
git -c advice.detachedHead=false checkout --quiet "$COMMIT"
echo "Enterprise $RAMA en $(git log -1 --format='%h del %cd' --date=short) (imagen $IMAGEN)"
