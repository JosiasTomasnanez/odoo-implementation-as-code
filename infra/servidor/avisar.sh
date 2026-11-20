#!/bin/bash
# Manda un aviso del servidor por Discord y por mail (ADR 0027).
#
# Uso:
#   avisar.sh <nivel> "<asunto>" ["<texto>"]     nivel: ok | info | aviso | error
#   echo "texto largo" | avisar.sh error "Asunto" -
#   avisar.sh --mdadm <evento> <dispositivo> [componente]   (PROGRAM de /etc/mdadm/mdadm.conf)
#   avisar.sh                                    (desde smartd -M exec: lee SMARTD_SUBJECT/MESSAGE)
#   avisar.sh --falla-servicio <unidad>           (odoo-aviso-falla@.service: si no avisó el script)
#
# ok e info van solo a Discord (no llenar el correo de «todo bien»); aviso y error, a los dos.
# Datos de envío en /etc/odoo-comercio/avisos.env (permisos 600, nunca en git):
#   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/…
#   SMTP_HOST=smtp.gmail.com  SMTP_PORT=587  SMTP_USUARIO=…  SMTP_CLAVE=…
#   MAIL_DE=…  MAIL_PARA=uno@…,otro@…
# Para pasar a Resend: SMTP_HOST=smtp.resend.com, SMTP_PORT=465, SMTP_USUARIO=resend,
# SMTP_CLAVE=<API key>, MAIL_DE=avisos@<dominio>. SMTP_TLS=off solo para probar con un SMTP local.
set -uo pipefail

AVISOS_ENV="${AVISOS_ENV:-/etc/odoo-comercio/avisos.env}"
if [[ -f "$AVISOS_ENV" ]]; then set -a; source "$AVISOS_ENV"; set +a; fi
# Nombre al pie de los avisos: el de Tailscale (el hostname de Debian es «servidor»)
SERVIDOR="${AVISOS_SERVIDOR:-$(hostname)}"

if [[ "${1:-}" == "--mdadm" ]]; then
    EVENTO="${2:-?}"; DISPOSITIVO="${3:-?}"; COMPONENTE="${4:-}"
    case "$EVENTO" in
        Fail|FailSpare|DegradedArray|DeviceDisappeared|SparesMissing) NIVEL=error ;;
        RebuildFinished|SpareActive) NIVEL=ok ;;
        *) exit 0 ;;  # NewArray, RebuildStarted, RebuildNN…: sin aviso
    esac
    set -- "$NIVEL" "Discos (RAID): $EVENTO en $DISPOSITIVO" \
        "mdadm informó «$EVENTO» en $DISPOSITIVO ${COMPONENTE:+(disco $COMPONENTE)}.
Estado: $(tr '\n' ' ' < /proc/mdstat)
Qué hacer: docs/runbooks/instalar-servidor.md, paso 6 (reconectar o cambiar el disco)."
elif [[ "${1:-}" == "--falla-servicio" ]]; then
    UNIDAD="${2:?falta la unidad}"
    INVOCACION="$(systemctl show -p InvocationID --value "$UNIDAD")"
    # Si el script ya avisó (logger -t odoo-aviso en esa misma corrida), no se repite
    if [[ -n "$INVOCACION" ]] && journalctl -q "_SYSTEMD_INVOCATION_ID=$INVOCACION" SYSLOG_IDENTIFIER=odoo-aviso | grep -q .; then
        exit 0
    fi
    set -- error "Falló $UNIDAD" "$(journalctl -u "$UNIDAD" -n 20 --no-pager -o cat)"
elif [[ $# -eq 0 && -n "${SMARTD_SUBJECT:-}" ]]; then
    set -- error "Disco: $SMARTD_SUBJECT" "${SMARTD_FULLMESSAGE:-${SMARTD_MESSAGE:-}}"
fi

NIVEL="${1:?falta el nivel (ok, info, aviso, error)}"
ASUNTO="${2:?falta el asunto}"
TEXTO="${3:-}"
[[ "$TEXTO" == "-" ]] && TEXTO="$(cat)"
case "$NIVEL" in
    ok|info|aviso|error) ;;
    *) echo "Nivel desconocido: $NIVEL" >&2; exit 2 ;;
esac

ENVIADOS=0

# El diseño (tarjeta de Discord y mail HTML) está en formato_avisos.py, que comparte el relay
# de Grafana (ADR 0028): color según el nivel, el detalle en un recuadro, servidor y fecha al pie
FORMATO="$(dirname "$(readlink -f "$0")")/formato_avisos.py"
export NIVEL ASUNTO TEXTO SERVIDOR
FECHA="$(date '+%d/%m/%Y %H:%M')"; export FECHA

if [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
    CUERPO="$(python3 "$FORMATO" discord)"
    if curl -fsS -m 20 -H "Content-Type: application/json" -d "$CUERPO" "$DISCORD_WEBHOOK_URL" >/dev/null; then
        ENVIADOS=$((ENVIADOS + 1))
    else
        echo "No se pudo avisar por Discord" >&2
    fi
fi

if [[ "$NIVEL" == aviso || "$NIVEL" == error || "${MAIL_TODO:-no}" == si ]] \
   && [[ -n "${SMTP_HOST:-}" && -n "${MAIL_PARA:-}" ]]; then
    # La clave va en un archivo temporal (no en la línea de comandos, que se ve con ps)
    CONF="$(mktemp)"; trap 'rm -f "$CONF"' EXIT; chmod 600 "$CONF"
    if [[ "${SMTP_PORT:-587}" == 465 ]]; then STARTTLS=off; else STARTTLS=on; fi
    cat > "$CONF" <<FIN
defaults
tls ${SMTP_TLS:-on}
tls_starttls $STARTTLS
tls_trust_file /etc/ssl/certs/ca-certificates.crt
account avisos
host $SMTP_HOST
port ${SMTP_PORT:-587}
$(if [[ -n "${SMTP_CLAVE:-}" ]]; then printf 'auth on\nuser %s\npassword %s\n' "${SMTP_USUARIO:-}" "$SMTP_CLAVE"; fi)
from ${MAIL_DE:-${SMTP_USUARIO:-}}
account default : avisos
FIN
    IFS=, read -ra DESTINOS <<< "$MAIL_PARA"
    if MAIL_DE="${MAIL_DE:-${SMTP_USUARIO:-}}" MAIL_PARA="$MAIL_PARA" python3 "$FORMATO" mail \
       | msmtp -C "$CONF" "${DESTINOS[@]}"; then
        ENVIADOS=$((ENVIADOS + 1))
    else
        echo "No se pudo avisar por mail" >&2
    fi
fi

# Queda también en el registro del sistema (journalctl -t odoo-aviso)
logger -t odoo-aviso -- "$NIVEL: $ASUNTO" 2>/dev/null || true
[[ $ENVIADOS -gt 0 ]]
