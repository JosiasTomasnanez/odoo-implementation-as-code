#!/usr/bin/env bash
# Restaura un backup zip (propio u obtenido de Odoo Online) en una base.
#
# Uso: STACK=lab|onprem infra/scripts/restore.sh <backup.zip> <base_destino> [--neutralize]
#
# --neutralize desactiva correos salientes, crons, etc. Usarlo SIEMPRE al restaurar
# una copia de producción en el laboratorio. Sin --neutralize se restaura «movida» (--move): conserva
# el identificador de la base y con él la suscripción Enterprise (04/11).
source "$(dirname "$0")/lib.sh"

FILE="${1:?falta el archivo de backup}"
TARGET="${2:?falta la base destino}"
EXTRA=()
if [ "${3:-}" = "--neutralize" ]; then
  # Copia de prueba: neutralizada y con identificador (UUID) NUEVO, para que nunca se confunda con
  # la base de verdad (ni con su suscripción).
  EXTRA+=(--neutralize)
else
  # Restaurar la base de verdad (p. ej. producción): se CONSERVA el identificador. La suscripción
  # Enterprise está atada a él; sin --move, Odoo genera uno nuevo y el código queda desvinculado.
  EXTRA+=(--move)
fi

if [ -f "$FILE.manifest" ]; then
  expected="$(grep '^sha256=' "$FILE.manifest" | cut -d= -f2)"
  actual="$(sha256sum "$FILE" | cut -d' ' -f1)"
  [ "$expected" = "$actual" ] || { echo "Checksum inválido para $FILE" >&2; exit 1; }
  log "Checksum verificado"
fi

log "Restaurando $FILE → base '$TARGET' ${EXTRA[*]:-}"
compose exec -T odoo sh -c 'cat > /tmp/restore.zip' < "$FILE"
compose exec -T odoo odoo db -c /etc/odoo/odoo.conf load --force "${EXTRA[@]}" "$TARGET" /tmp/restore.zip
# Comprobar los adjuntos contra el zip y reponer los que no coincidan. El 17/11, al restaurar
# producción encima de la base existente (--force, con Odoo andando), los 99 archivos quedaron
# con 0 bytes y la actualización siguiente falló («collides with an existing file»).
compose exec -T odoo python3 - "$TARGET" <<'PY'
import os, sys, zipfile
from odoo.tools import config
config.parse_config(["-c", "/etc/odoo/odoo.conf"])
destino = os.path.join(config["data_dir"], "filestore", sys.argv[1])
repuestos = total = 0
with zipfile.ZipFile("/tmp/restore.zip") as z:
    for m in z.infolist():
        if not m.filename.startswith("filestore/") or m.is_dir():
            continue
        total += 1
        ruta = os.path.join(destino, m.filename[len("filestore/"):])
        if not os.path.isfile(ruta) or os.path.getsize(ruta) != m.file_size:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with z.open(m) as origen, open(ruta, "wb") as f:
                f.write(origen.read())
            repuestos += 1
print(f"Adjuntos: {total} en la copia, {repuestos} repuestos")
PY
compose exec -T odoo rm -f /tmp/restore.zip
log "Restauración terminada"
