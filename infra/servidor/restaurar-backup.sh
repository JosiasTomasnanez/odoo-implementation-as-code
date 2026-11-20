#!/bin/bash
# Baja una copia de restic (pendrive o R2) y la deja como zip de Odoo, listo para
# infra/scripts/restore.sh (ADR 0005 y 0027). Sirve también en un servidor nuevo: alcanza con
# /etc/odoo-comercio/backup.env (los datos están en Bitwarden).
#
# Uso:
#   sudo bash restaurar-backup.sh --listar [--desde r2|pendrive]
#   sudo bash restaurar-backup.sh [--desde r2|pendrive] [--copia latest|<id>] [--destino <carpeta>]
# La última línea que imprime es la ruta del zip. La CA de Caddy queda en <destino>/restic/…
set -euo pipefail
source "$(dirname "$0")/respaldo-comun.sh"

DESDE=""; COPIA=latest; DESTINO=""; LISTAR=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --desde) DESDE="$2"; shift 2 ;;
        --copia) COPIA="$2"; shift 2 ;;
        --destino) DESTINO="$2"; shift 2 ;;
        --listar) LISTAR=1; shift ;;
        *) echo "Opción desconocida: $1" >&2; exit 2 ;;
    esac
done
# Por defecto R2 (está fuera del local); si no hay R2, el pendrive
[[ -n "$DESDE" ]] || DESDE="$(copias | sort -r | head -1)"
REPO="$(repo_de "$DESDE")"
[[ -n "$REPO" ]] || { echo "La copia «$DESDE» no está configurada en $BACKUP_ENV" >&2; exit 1; }
copia_disponible "$DESDE" || { echo "La copia «$DESDE» no está disponible (¿pendrive?)" >&2; exit 1; }

# Con un token de solo lectura (lab: make lab-copia-prod) restic no puede dejar su candado en R2
SIN_CANDADO=()
[[ "${RESTIC_SOLO_LECTURA:-}" == 1 ]] && SIN_CANDADO=(--no-lock)

if [[ $LISTAR -eq 1 ]]; then
    restic -r "$REPO" snapshots --host "$HOST_RESTIC" "${SIN_CANDADO[@]}"
    exit 0
fi

DESTINO="${DESTINO:-$TRABAJO_DIR/restaurado-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$DESTINO"
echo "== Bajando la copia «$COPIA» desde $DESDE a $DESTINO" >&2
restic -r "$REPO" restore "$COPIA" --host "$HOST_RESTIC" --target "$DESTINO/restic" "${SIN_CANDADO[@]}" >&2

ACTUAL="$(dirname "$(find "$DESTINO/restic" -path '*/actual/dump.sql' | head -1)")"
[[ -f "$ACTUAL/dump.sql" ]] || { echo "La copia no tiene dump.sql" >&2; exit 1; }
FECHA="$(sed -n 's/^fecha_utc=//p' "$ACTUAL/backup.manifest" 2>/dev/null || true)"
ZIP="$DESTINO/odoo-${FECHA:-copia}.zip"
# Mismo formato que «odoo db dump»: dump.sql, manifest.json y filestore/ en la raíz del zip
python3 - "$ACTUAL" "$ZIP" <<'PY' >&2
import os, sys, zipfile
origen, destino = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
    for raiz, _, archivos in os.walk(origen):
        for a in archivos:
            ruta = os.path.join(raiz, a)
            relativa = os.path.relpath(ruta, origen)
            if relativa != "backup.manifest":
                z.write(ruta, relativa)
print(f"zip armado: {destino}")
PY
echo "$ZIP"
