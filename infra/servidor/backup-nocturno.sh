#!/bin/bash
# Backup de cada noche (ADR 0027): base + filestore + CA interna de Caddy, cifrado con restic
# en el pendrive del servidor y en Cloudflare R2. Avisa por Discord si salió bien y por
# Discord y mail si algo falló. Lo corre el timer odoo-backup (03:00); a mano:
#   sudo systemctl start odoo-backup     (o: sudo bash infra/servidor/backup-nocturno.sh)
#
# El volcado es el zip estándar de Odoo (ADR 0005, infra/scripts/backup.sh), descomprimido
# en una carpeta fija: así restic sube solo lo que cambió. restaurar-backup.sh lo vuelve a zipear.
set -uo pipefail
export STACK="${STACK:-onprem}"
source "$(dirname "$0")/respaldo-comun.sh"

install -d -m 700 "$TRABAJO_DIR" "$ESTADO_DIR"
chmod 700 "$TRABAJO_DIR" "$ESTADO_DIR"  # por si ya existían con otros permisos
REGISTRO="$(mktemp)"; trap 'rm -f "$REGISTRO"' EXIT
exec > >(tee -a "$REGISTRO") 2>&1

ping_hc "${HC_BACKUP_URL:-}" /start
INICIO="$(date +%s)"
fallar() {
    avisar error "Backup: $1" "$(tail -25 "$REGISTRO")"
    ping_hc "${HC_BACKUP_URL:-}" /fail
    exit 1
}
[[ -n "$(copias)" ]] || fallar "no hay copias configuradas en $BACKUP_ENV"

# ---------------------------------------------------------------- volcado
echo "== Volcando la base"
ZIP="$("$REPO_DIR/infra/scripts/backup.sh" "$TRABAJO_DIR/zip" | tail -1)"
[[ -f "$ZIP" ]] || fallar "no se pudo volcar la base"
rm -rf "$TRABAJO_DIR/actual.nueva"
python3 -m zipfile -e "$ZIP" "$TRABAJO_DIR/actual.nueva" || fallar "no se pudo descomprimir el volcado"
cp "$ZIP.manifest" "$TRABAJO_DIR/actual.nueva/backup.manifest"
rm -rf "$TRABAJO_DIR/actual"
mv "$TRABAJO_DIR/actual.nueva" "$TRABAJO_DIR/actual"
rm -f "$ZIP" "$ZIP.manifest"

RUTAS=("$TRABAJO_DIR/actual")
# CA interna de Caddy (ADR 0013): si se pierde, hay que reinstalar la raíz en todas las PCs
if [[ "$STACK" == onprem ]]; then
    CADDY="$(sed -n 's/^CADDY_DATA_DIR=//p' "${ONPREM_ENV_FILE:-/etc/odoo-comercio/onprem.env}" | tail -1)"
    [[ -n "$CADDY" && -d "$CADDY" ]] && RUTAS+=("$CADDY")
fi
TAMANO="$(du -sh "$TRABAJO_DIR/actual" | cut -f1)"
ARCHIVOS="$(find "$TRABAJO_DIR/actual/filestore" -type f 2>/dev/null | wc -l)"

# ---------------------------------------------------------------- copias
BIEN=(); MAL=()
for copia in $(copias); do
    echo "== Copia: $copia"
    if ! copia_disponible "$copia"; then
        echo "No está disponible (¿pendrive desenchufado?)"; MAL+=("$copia: no disponible"); continue
    fi
    REPO="$(repo_de "$copia")"
    # shellcheck disable=SC2046  # guardar_de devuelve varias opciones
    if restic -r "$REPO" backup --host "$HOST_RESTIC" --tag nocturno "${RUTAS[@]}" \
       && restic -r "$REPO" forget --host "$HOST_RESTIC" --tag nocturno $(guardar_de "$copia") --prune; then
        marcar_ok "$copia"; BIEN+=("$copia")
    else
        MAL+=("$copia: falló restic")
    fi
done

# ---------------------------------------------------------------- métricas (Grafana, ADR 0028)
{
    echo "# HELP odoo_backup_bytes Volcado de la base más adjuntos (sin comprimir) del último backup."
    echo "# TYPE odoo_backup_bytes gauge"
    echo "odoo_backup_bytes $(du -sb "$TRABAJO_DIR/actual" | cut -f1)"
    echo "# HELP odoo_filestore_bytes Adjuntos de Odoo (filestore) del último backup."
    echo "# TYPE odoo_filestore_bytes gauge"
    echo "odoo_filestore_bytes $(du -sb "$TRABAJO_DIR/actual/filestore" 2>/dev/null | cut -f1 || echo 0)"
    echo "# HELP odoo_backup_adjuntos Cantidad de archivos adjuntos del último backup."
    echo "# TYPE odoo_backup_adjuntos gauge"
    echo "odoo_backup_adjuntos $ARCHIVOS"
    echo "# HELP odoo_backup_duracion_segundos Duración del último backup (volcado y copias)."
    echo "# TYPE odoo_backup_duracion_segundos gauge"
    echo "odoo_backup_duracion_segundos $(( $(date +%s) - INICIO ))"
} | escribir_metricas backup
metricas_copias

# ---------------------------------------------------------------- aviso
RESUMEN="Base y archivos: $TAMANO ($ARCHIVOS adjuntos)
Copias bien: ${BIEN[*]:-ninguna}"
if [[ ${#MAL[@]} -eq 0 ]]; then
    avisar ok "Backup OK" "$RESUMEN"
    ping_hc "${HC_BACKUP_URL:-}"
elif [[ ${#BIEN[@]} -gt 0 ]]; then
    avisar aviso "Backup incompleto: ${MAL[*]}" "$RESUMEN
$(tail -15 "$REGISTRO")"
    ping_hc "${HC_BACKUP_URL:-}" /fail
    exit 1
else
    fallar "no quedó ninguna copia (${MAL[*]})"
fi
