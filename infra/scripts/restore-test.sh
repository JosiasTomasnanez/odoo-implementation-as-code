#!/usr/bin/env bash
# Prueba de restauración: un backup que nunca se restauró no está validado.
# Restaura en una base temporal neutralizada, comprueba que Odoo la puede usar
# y la elimina.
#
# Uso: STACK=lab|onprem infra/scripts/restore-test.sh <backup.zip>
source "$(dirname "$0")/lib.sh"

FILE="${1:?falta el archivo de backup}"
TEST_DB="restore_test_$(date +%s)"

cleanup() { compose exec -T odoo odoo db -c /etc/odoo/odoo.conf drop "$TEST_DB" >/dev/null 2>&1 || true; }
trap cleanup EXIT

"$(dirname "$0")/restore.sh" "$FILE" "$TEST_DB" --neutralize

log "Validando la base restaurada"
compose exec -T odoo odoo shell -c /etc/odoo/odoo.conf -d "$TEST_DB" --no-http --log-level=warn <<'PY'
installed = env["ir.module.module"].search_count([("state", "=", "installed")])
users = env["res.users"].search_count([])
attachments = env["ir.attachment"].search([("store_fname", "!=", False)], limit=20)
import os
# Odoo 20: _file_read() ya no recibe la ruta; se mira el archivo en el filestore directamente
missing = [a.id for a in attachments if not os.path.isfile(a._full_path(a.store_fname))]
assert installed > 0, "no hay módulos instalados"
assert users > 0, "no hay usuarios"
assert not missing, f"adjuntos sin archivo en el filestore: {missing}"
print(f"RESTORE_OK modulos={installed} usuarios={users} adjuntos_verificados={len(attachments)}")
PY
log "Prueba de restauración OK"
