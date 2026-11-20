#!/bin/bash
# Correo saliente de Odoo por Resend con el dominio propio (P-022, 06/11): las órdenes de compra,
# facturas y avisos salen desde notificaciones@comercio-ejemplo.example (con el nombre de quien lo manda) y
# las respuestas van al mail de esa persona (Reply-To), porque Resend solo envía.
#
#   - odoo.conf (fuera del repo): smtp.resend.com:587 STARTTLS (smtp_ssl del odoo.conf es STARTTLS, no SSL directo), usuario «resend», la clave de Resend,
#     email_from y from_filter = comercio-ejemplo.example (lo que no es del dominio sale como notificaciones@);
#     (en Odoo 20 el remitente por defecto es email_from del odoo.conf, no mail.default.from);
#   - --respuestas: el mail del administrador y de la empresa, si están vacíos (sin mail de quien
#     envía, Odoo no manda nada); ahí llegan las respuestas;
#   - reinicia Odoo y, con --prueba, manda un mail de prueba a esa dirección.
#
# La clave: Resend → API Keys → «odoo», permiso «Sending access», solo el dominio comercio-ejemplo.example.
# Se pide por teclado (no se ve) o se lee de un archivo con RESEND_API_KEY=… (permisos 600), que se
# borra después. Queda solo en odoo.conf (640, root:docker). Bitwarden: «Servidor: Resend (Odoo)».
#
# Uso en el servidor (desde /opt/odoo-implementation):
#   sudo bash infra/servidor/configurar-correo.sh --respuestas odoo@comercio-ejemplo.example \
#        [--clave-archivo /root/resend-odoo.env] [--prueba alguien@ejemplo.com]
#   sudo bash infra/servidor/configurar-correo.sh --apagar      # vuelve a no mandar mails
# Se puede correr varias veces.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
CONF=/etc/odoo-comercio
ODOO_CONF="$CONF/odoo.conf"
DOMINIO="${CORREO_DOMINIO:-comercio-ejemplo.example}"
REMITENTE="${CORREO_REMITENTE:-notificaciones@$DOMINIO}"
BASE="${ODOO_BASE:-produccion}"

RESPUESTAS="" CLAVE_ARCHIVO="" PRUEBA="" APAGAR=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --respuestas) RESPUESTAS="$2"; shift 2 ;;
        --clave-archivo) CLAVE_ARCHIVO="$2"; shift 2 ;;
        --prueba) PRUEBA="$2"; shift 2 ;;
        --apagar) APAGAR=1; shift ;;
        *) echo "Opción desconocida: $1" >&2; exit 2 ;;
    esac
done
[[ $EUID -eq 0 ]] || { echo "Correr con sudo." >&2; exit 1; }
[[ -f "$ODOO_CONF" ]] || { echo "Falta $ODOO_CONF (primero instalar-odoo.sh)." >&2; exit 1; }
ok() { echo "   ✓ $*"; }

# Saca del odoo.conf los ajustes de correo (activos o comentados de la plantilla vieja)
limpiar() { sed -i -E '/^; Correo saliente por la Gmail/,/^; from_filter/d;
                     /^; Correo saliente por Resend/d;
                     /^;? *(smtp_server|smtp_port|smtp_ssl|smtp_user|smtp_password|email_from|from_filter) *=/d' "$ODOO_CONF"; }

if [[ $APAGAR -eq 1 ]]; then
    limpiar
    ok "Correo saliente apagado en odoo.conf"
else
    if [[ -n "$CLAVE_ARCHIVO" ]]; then
        CLAVE="$(sed -n 's/^RESEND_API_KEY=//p' "$CLAVE_ARCHIVO" | tail -1)"
    else
        read -rsp "   Clave de Resend para Odoo (no se ve al escribir): " CLAVE; echo
    fi
    [[ "$CLAVE" == re_* ]] || { echo "La clave de Resend empieza con «re_»." >&2; exit 1; }
    limpiar
    cat >> "$ODOO_CONF" <<EOF
; Correo saliente por Resend con el dominio propio (configurar-correo.sh, P-022)
smtp_server = smtp.resend.com
smtp_port = 587
smtp_ssl = True
smtp_user = resend
smtp_password = $CLAVE
email_from = $REMITENTE
from_filter = $DOMINIO
EOF
    unset CLAVE
    chown 100:docker "$ODOO_CONF"; chmod 640 "$ODOO_CONF"
    ok "odoo.conf: Resend (smtp.resend.com:587, STARTTLS), remitente $REMITENTE"
    if [[ -n "$CLAVE_ARCHIVO" ]]; then shred -u "$CLAVE_ARCHIVO" && ok "Archivo de la clave borrado"; fi
fi

cd "$REPO"
STACK=onprem source infra/scripts/lib.sh
compose up -d --force-recreate --wait odoo >/dev/null 2>&1 && ok "Odoo reiniciado"

if [[ -n "$RESPUESTAS" ]]; then
    compose exec -T odoo odoo shell -c /etc/odoo/odoo.conf -d "$BASE" --no-http --log-level=warn <<PY
admin = env.ref("base.user_admin")
if not admin.email:
    admin.email = "$RESPUESTAS"
if not env.company.email:
    env.company.email = "$RESPUESTAS"
env.cr.commit()
print("   ✓ Respuestas a:", admin.email, "(administrador) y", env.company.email, "(empresa)")
PY
fi

if [[ -n "$PRUEBA" && $APAGAR -eq 0 ]]; then
    compose exec -T odoo odoo shell -c /etc/odoo/odoo.conf -d "$BASE" --no-http --log-level=warn <<PY
admin = env.ref("base.user_admin")
mail = env["mail.mail"].sudo().create({
    "subject": "Prueba de correo de Odoo (Comercio Ejemplo)",
    "body_html": "<p>Si ves este mail, Odoo ya manda correos desde $DOMINIO. Respondé para probar que la respuesta llega.</p>",
    "email_to": "$PRUEBA", "email_from": admin.email_formatted, "reply_to": admin.email_formatted})
mail.send(raise_exception=True)
print("   ✓ Mail de prueba:", mail.state, "→ $PRUEBA")
env.cr.commit()
PY
fi
