#!/usr/bin/env bash
# Copia de producción en el lab: baja la última copia de R2, la restaura como la base
# «copia_prod» (al lado de «lab», que no se toca), la neutraliza y le aplica el código de ahora.
# Sirve para probar una actualización con los datos reales antes de hacerla en el servidor, y de
# paso comprueba que las copias de R2 se pueden restaurar sin el servidor.
#
# Uso: make lab-copia-prod [COPIA=latest|<id>]      (borrarla: make lab-copia-prod-borrar)
#
# Necesita ~/copia-prod.env (permisos 600, fuera de git) con un token de R2 de SOLO LECTURA y la
# clave de restic: REPO_R2, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, RESTIC_PASSWORD
# (docs/runbooks/backup-restauracion.md, «Copia de producción en el lab»).
#
# Neutralizada = segura para probar: sin mails ni tareas programadas (Odoo --neutralize), ARCA en
# homologación y sin el certificado real (no se puede sacar un CAE de verdad), identificador de
# base nuevo y sin el código de suscripción (no compite con producción), dirección localhost.
set -euo pipefail
cd "$(dirname "$0")/../.."
export STACK=lab
source infra/scripts/lib.sh

ENV_COPIA="${COPIA_PROD_ENV:-$HOME/copia-prod.env}"
BASE="${BASE:-copia_prod}"
[[ -f "$ENV_COPIA" ]] || { echo "Falta $ENV_COPIA (ver docs/runbooks/backup-restauracion.md)" >&2; exit 1; }
[[ "$(stat -c %a "$ENV_COPIA")" == 600 ]] || { echo "$ENV_COPIA tiene que tener permisos 600" >&2; exit 1; }
command -v restic >/dev/null || { echo "Falta restic: sudo apt install restic" >&2; exit 1; }
# Datos reales: solo con el lab cerrado a la red (make lab-local). Abierto (make lab-red), otra PC
# vería la pantalla de bases y, con la clave maestra del lab, podría bajarse la copia.
if docker port odoo-lab-odoo-1 8069 2>/dev/null | grep -qv '^127\.0\.0\.1:'; then
    echo "El lab está abierto a la red (make lab-red): cerralo con «make lab-local» antes." >&2; exit 1
fi

# Lo bajado está sin cifrar (dump.sql, adjuntos): carpeta privada que se borra siempre al final
umask 077
TRABAJO="$(mktemp -d "${TMPDIR:-/tmp}/copia-prod.XXXXXX")"
trap 'rm -rf "$TRABAJO"' EXIT

log "Bajando la copia «${COPIA:-latest}» de R2"
ZIP="$(BACKUP_ENV="$ENV_COPIA" AVISOS_ENV=/dev/null TRABAJO_DIR="$TRABAJO" ESTADO_DIR="$TRABAJO/estado" \
       RESTIC_CACHE_DIR="$HOME/.cache/restic" RESTIC_SOLO_LECTURA=1 \
       bash infra/servidor/restaurar-backup.sh --desde r2 --copia "${COPIA:-latest}" --destino "$TRABAJO/r2" | tail -1)"
[[ -f "$ZIP" ]] || { echo "No se pudo armar la copia" >&2; exit 1; }

# --neutralize de Odoo: mails, tareas programadas, ARCA en homologación (l10n_ar_edi). Al cargar,
# Odoo le da a la base un identificador nuevo (es una copia, no la misma base).
STACK=lab infra/scripts/restore.sh "$ZIP" "$BASE" --neutralize

log "Aplicando el código de ahora (como al actualizar el servidor: -u all)"
compose exec -T odoo odoo -c /etc/odoo/odoo.conf -d "$BASE" -u all --stop-after-init --no-http \
    --log-level=warn 2>&1 | grep -vE "Missing .author|have the same label|markdown" || true
# Otra vez la neutralización de Odoo: actualizar los módulos vuelve a activar las tareas
# programadas que traen sus datos (cierre nocturno de puestos, dólar del día…)
log "Neutralizando de nuevo (después de actualizar)"
compose exec -T odoo odoo neutralize -c /etc/odoo/odoo.conf -d "$BASE" --log-level=warn 2>&1 \
    | grep -vE "Missing .author|have the same label|markdown" || true

log "Neutralizando lo que Odoo no cubre"
compose exec -T odoo odoo shell -c /etc/odoo/odoo.conf -d "$BASE" --no-http --log-level=warn <<'PY'
icp = env["ir.config_parameter"].sudo()
# Suscripción: que esta copia no se presente como la base de producción registrada
for clave in ("database.enterprise_code", "database.expiration_reason", "database.already_linked_subscription_url",
              "database.already_linked_email", "database.already_linked_send_mail_url"):
    icp.search([("key", "=", clave)]).unlink()
icp.set_str("web.base.url", "http://localhost:8069")
icp.set_bool("web.base.url.freeze", True)
icp.set_str("report.url", "http://localhost:8069")
# ARCA: además de homologación, sin el certificado ni la clave de producción
empresas = env["res.company"].sudo().search([])
if "l10n_ar_afip_ws_crt_id" in empresas._fields:
    empresas.write({"l10n_ar_afip_ws_environment": "testing", "l10n_ar_afip_ws_crt_id": False,
                    "l10n_ar_afip_ws_key_id": False})
# Sin la actualización diaria del dólar (con producción sin certificado, fallaría igual)
if "currency_interval_unit" in empresas._fields:
    empresas.write({"currency_interval_unit": "manually"})
env.cr.commit()
activas = env["ir.cron"].sudo().search([("active", "=", True)])
print("NEUTRALIZADA uuid=%s ARCA=%s tareas_activas=%s" % (
    icp.get_str("database.uuid"), ",".join(empresas.mapped("l10n_ar_afip_ws_environment") or ["-"]),
    ", ".join(activas.mapped("cron_name")) or "ninguna"))
PY

compose restart odoo >/dev/null
log "Lista: http://localhost:8069/web?db=$BASE (usuarios y claves de producción). Borrarla: make lab-copia-prod-borrar"
