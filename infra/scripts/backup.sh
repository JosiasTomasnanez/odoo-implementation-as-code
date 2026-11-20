#!/usr/bin/env bash
# Backup completo (base + filestore) en el formato zip estándar de Odoo, el mismo
# que genera el gestor de bases de Odoo Online. Incluye un manifiesto con checksum.
#
# Uso: STACK=lab|onprem infra/scripts/backup.sh [directorio_destino]
#
# Solo genera la copia local. La copia externa (S3 u otro), el cifrado y la
# retención están PENDIENTES de decisión (docs/infraestructura/backups.md).
source "$(dirname "$0")/lib.sh"

DEST="${1:-$REPO_ROOT/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/${STACK}-${DB_NAME}-${STAMP}.zip"
mkdir -p "$DEST"

log "Volcando '$DB_NAME' → $OUT"
compose exec -T odoo odoo db -c /etc/odoo/odoo.conf dump "$DB_NAME" - > "$OUT.partial"
mv "$OUT.partial" "$OUT"

# Verificación mínima: el zip debe ser legible y contener el volcado SQL.
python3 - "$OUT" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    bad = z.testzip()
    assert bad is None, f"archivo corrupto en el zip: {bad}"
    assert "dump.sql" in z.namelist(), "el zip no contiene dump.sql"
PY

{
  echo "archivo=$(basename "$OUT")"
  echo "sha256=$(sha256sum "$OUT" | cut -d' ' -f1)"
  echo "bytes=$(stat -c %s "$OUT")"
  echo "base=$DB_NAME"
  echo "stack=$STACK"
  echo "fecha_utc=$STAMP"
  echo "odoo=$(compose exec -T odoo odoo --version | tr -d '\r')"
  echo "repo_commit=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo desconocido)"
} > "$OUT.manifest"

log "Backup OK: $OUT"
echo "$OUT"
