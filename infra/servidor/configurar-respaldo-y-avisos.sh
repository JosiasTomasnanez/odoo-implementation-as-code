#!/bin/bash
# Backups automáticos y avisos del servidor (ADR 0027), después de instalar-odoo.sh
# (docs/runbooks/instalar-servidor.md, paso 10):
#   - avisos por Discord y mail (/etc/odoo-comercio/avisos.env) y un aviso de prueba;
#   - el pendrive de backups (lo formatea solo si se confirma escribiendo BORRAR);
#   - las copias cifradas con restic en el pendrive y en Cloudflare R2 (/etc/odoo-comercio/backup.env);
#   - avisos de los discos (smartd) y del RAID (mdadm);
#   - los timers: backup 03:00, chequeo cada 15 min, verificación los domingos, prueba de
#     restauración el día 1 de cada mes;
#   - el primer backup.
#
# Uso (en el servidor, desde /opt/odoo-implementation):
#   sudo bash infra/servidor/configurar-respaldo-y-avisos.sh --simular
#   sudo bash infra/servidor/configurar-respaldo-y-avisos.sh
# Se puede correr varias veces: lo que ya está hecho se saltea. Para cambiar un dato (otro
# webhook, pasar el mail a Resend…), editar el .env correspondiente; no hace falta correrlo.
set -euo pipefail

SIMULAR=0
[[ "${1:-}" == "--simular" ]] && SIMULAR=1
DIR="$(cd "$(dirname "$0")" && pwd)"
CONF=/etc/odoo-comercio
AVISOS_ENV="$CONF/avisos.env"
BACKUP_ENV="$CONF/backup.env"
ETIQUETA=EJEMPLO-BK
MONTAJE=/mnt/backup-usb

paso() { echo; echo "== $*"; }
ok() { echo "   ✓ $*"; }
aviso() { echo "   ⚠ $*"; }
hacer() {  # muestra el comando; lo ejecuta salvo en --simular
    echo "   → $*"
    if [[ $SIMULAR -eq 0 ]]; then eval "$@"; fi
}
clave() { openssl rand -base64 33 | tr -d '/+=' | cut -c1-32; }
preguntar() {  # preguntar <variable> <texto> [defecto] [-s: no mostrar lo que se escribe]
    local respuesta
    if [[ "${4:-}" == -s ]]; then read -rsp "   $2: " respuesta; echo
    else read -rp "   $2${3:+ [$3]}: " respuesta; fi
    printf -v "$1" '%s' "${respuesta:-${3:-}}"
}

if [[ $EUID -ne 0 ]]; then echo "Correrlo con sudo: sudo bash $0 $*" >&2; exit 1; fi
[[ -d "$CONF" ]] || { echo "Falta $CONF: correr antes instalar-odoo.sh" >&2; exit 1; }
[[ $SIMULAR -eq 1 ]] && echo "MODO SIMULACIÓN: no se cambia nada."

# ---------------------------------------------------------------- paquetes
paso "Paquetes"
hacer "DEBIAN_FRONTEND=noninteractive apt-get -q -y install restic msmtp smartmontools python3 ca-certificates >/dev/null"

# ---------------------------------------------------------------- avisos
paso "Avisos (Discord y mail)"
if [[ -f "$AVISOS_ENV" ]]; then
    ok "Ya configurados en $AVISOS_ENV"
elif [[ $SIMULAR -eq 1 ]]; then
    echo "   → pediría el webhook de Discord y los datos del mail, y los guardaría en $AVISOS_ENV (600)"
else
    echo "   Datos en Bitwarden: «Servidor: webhook Discord» y «Servidor: Resend (avisos)»."
    preguntar DISCORD "URL del webhook de Discord (Enter: sin Discord)"
    # Mail por Resend con el dominio propio (P-022): sale de avisos@comercio-ejemplo.example
    preguntar SMTP_CLAVE "Clave de Resend (Enter: sin mail por ahora)" "" -s
    if [[ -n "$SMTP_CLAVE" ]]; then
        preguntar MAIL_PARA "A quién le llegan los mails (separar con coma)"
    else
        MAIL_PARA=""
    fi
    echo "   Opcional: healthchecks.io avisa si el servidor deja de responder (Enter: sin esto)."
    preguntar HC_BACKUP "URL del chequeo «backup» de healthchecks.io"
    preguntar HC_REVISION "URL del chequeo «servidor» de healthchecks.io"
    umask 077
    cat > "$AVISOS_ENV" <<FIN
# Avisos del servidor (ADR 0027). Permisos 600, nunca en git. Mail por Resend (dominio
# comercio-ejemplo.example). Con Gmail sería: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USUARIO y
# MAIL_DE = la cuenta, SMTP_CLAVE = contraseña de aplicación. Sin SMTP_CLAVE no se manda mail.
DISCORD_WEBHOOK_URL=$DISCORD
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USUARIO=resend
SMTP_CLAVE=$SMTP_CLAVE
MAIL_DE=avisos@comercio-ejemplo.example
MAIL_PARA=$MAIL_PARA
HC_BACKUP_URL=$HC_BACKUP
HC_REVISION_URL=$HC_REVISION
# Nombre al pie de los avisos (el de Tailscale)
AVISOS_SERVIDOR=servidor-ejemplo
FIN
    umask 022
    unset SMTP_CLAVE
    ok "Guardado en $AVISOS_ENV"
fi
if [[ $SIMULAR -eq 0 ]]; then
    if "$DIR/avisar.sh" aviso "Prueba de avisos" "Si llegó por Discord y por mail, los avisos funcionan."; then
        ok "Aviso de prueba enviado: revisar Discord y el mail"
    else
        aviso "No salió ningún aviso: revisar $AVISOS_ENV"
    fi
fi

# ---------------------------------------------------------------- pendrive
paso "Pendrive de backups"
if grep -q "LABEL=$ETIQUETA" /etc/fstab; then
    ok "Ya registrado ($MONTAJE)"
else
    DISPOSITIVO="$(blkid -L "$ETIQUETA" 2>/dev/null || true)"
    if [[ -z "$DISPOSITIVO" ]]; then
        mapfile -t USB < <(lsblk -dpno NAME,TRAN | awk '$2 == "usb" {print $1}')
        if [[ ${#USB[@]} -eq 0 ]]; then
            aviso "No hay ningún pendrive enchufado: las copias van solo a R2. Enchufarlo y correr de nuevo."
        elif [[ ${#USB[@]} -gt 1 ]]; then
            aviso "Hay ${#USB[@]} dispositivos USB: dejar enchufado solo el pendrive y correr de nuevo."
        else
            echo "   Pendrive encontrado:"
            lsblk -o NAME,SIZE,MODEL,LABEL,FSTYPE "${USB[0]}" 2>&1 | sed 's/^/     /' || true
            if [[ $SIMULAR -eq 1 ]]; then
                echo "   → pediría escribir BORRAR y lo formatearía (ext4, etiqueta $ETIQUETA)"
            else
                read -rp "   SE BORRA TODO lo que tiene. Escribir BORRAR para seguir: " RESPUESTA
                if [[ "$RESPUESTA" == BORRAR ]]; then
                    wipefs -a "${USB[0]}" >/dev/null
                    mkfs.ext4 -q -F -L "$ETIQUETA" "${USB[0]}"
                    udevadm settle
                    DISPOSITIVO="$(blkid -L "$ETIQUETA")"
                    ok "Formateado: $DISPOSITIVO"
                else
                    aviso "No se formateó: las copias van solo a R2 por ahora."
                fi
            fi
        fi
    fi
    if [[ -n "$DISPOSITIVO" ]]; then
        hacer "mkdir -p $MONTAJE"
        # nofail: sin el pendrive el servidor arranca igual (y el chequeo avisa)
        hacer "echo 'LABEL=$ETIQUETA $MONTAJE ext4 defaults,nofail,noatime,x-systemd.device-timeout=5s 0 2' >> /etc/fstab"
        hacer "systemctl daemon-reload && mount $MONTAJE"
        ok "Montado en $MONTAJE"
    fi
fi

# ---------------------------------------------------------------- copias (restic)
paso "Copias cifradas (restic)"
if [[ -f "$BACKUP_ENV" ]]; then
    ok "Ya configuradas en $BACKUP_ENV"
elif [[ $SIMULAR -eq 1 ]]; then
    echo "   → generaría la clave de las copias (mostrarla una vez → Bitwarden) y pediría los datos de R2"
else
    # Servidor nuevo con copias de antes: se usa la clave de siempre (si no, no se pueden abrir)
    preguntar CLAVE_RESTIC "Si ya hay copias (servidor nuevo), pegar la clave «Servidor: backups (restic)»; si no, Enter" "" -s
    if [[ -z "$CLAVE_RESTIC" ]]; then
        CLAVE_RESTIC="$(clave)"
        echo
        echo "   Clave de las copias. Sin ella NO se puede restaurar nada:"
        echo "   GUARDAR AHORA EN BITWARDEN como «Servidor: backups (restic)» (no se vuelve a mostrar): $CLAVE_RESTIC"
        read -rp "   Enter cuando esté guardada… " _
    fi
    echo "   Cloudflare R2 (Bitwarden «Servidor: R2 backups»). Enter en el primero: sin R2."
    preguntar R2_CUENTA "Account ID de Cloudflare"
    if [[ -n "$R2_CUENTA" ]]; then
        preguntar R2_BUCKET "Bucket" comercio-ejemplo-backups
        preguntar R2_ID "Access Key ID del token"
        preguntar R2_SECRETO "Secret Access Key del token" "" -s
    fi
    REPO_USB=""; grep -q "LABEL=$ETIQUETA" /etc/fstab && REPO_USB="$MONTAJE/restic"
    umask 077
    cat > "$BACKUP_ENV" <<FIN
# Copias del servidor (ADR 0027). Permisos 600, nunca en git. Todo está también en Bitwarden.
RESTIC_PASSWORD=$CLAVE_RESTIC
USB_MONTAJE=${REPO_USB:+$MONTAJE}
REPO_USB=$REPO_USB
REPO_R2=${R2_CUENTA:+s3:https://$R2_CUENTA.r2.cloudflarestorage.com/$R2_BUCKET/servidor}
AWS_ACCESS_KEY_ID=${R2_ID:-}
AWS_SECRET_ACCESS_KEY=${R2_SECRETO:-}
# Cuántas copias se guardan
GUARDAR_USB="--keep-daily 7 --keep-weekly 4"
GUARDAR_R2="--keep-daily 7 --keep-weekly 4"
FIN
    umask 022
    unset CLAVE_RESTIC R2_SECRETO
    ok "Guardado en $BACKUP_ENV"
fi
if [[ $SIMULAR -eq 0 ]]; then
    # Si el pendrive se sumó después, se agrega a las copias
    if grep -q "LABEL=$ETIQUETA" /etc/fstab && grep -q '^REPO_USB=$' "$BACKUP_ENV"; then
        sed -i "s|^USB_MONTAJE=.*|USB_MONTAJE=$MONTAJE|; s|^REPO_USB=$|REPO_USB=$MONTAJE/restic|" "$BACKUP_ENV"
        ok "Pendrive sumado a las copias"
    fi
    (
        source "$DIR/respaldo-comun.sh"
        for copia in $(copias); do
            if ! copia_disponible "$copia"; then aviso "$copia: no disponible"; continue; fi
            if restic -r "$(repo_de "$copia")" cat config >/dev/null 2>&1; then
                ok "$copia: la copia ya existe (se sigue usando)"
            elif restic -r "$(repo_de "$copia")" init >/dev/null; then
                ok "$copia: copia nueva creada"
            else
                aviso "$copia: no se pudo crear (revisar los datos en $BACKUP_ENV)"
            fi
        done
    )
fi

# ---------------------------------------------------------------- discos y RAID
paso "Avisos de los discos (SMART) y del RAID"
LINEA_SMART="DEVICESCAN -d removable -n standby,q -a -o on -S on -s (S/../.././02|L/../../6/03) -W 4,50,60 -m root -M exec $DIR/avisar.sh"
if grep -qF "$DIR/avisar.sh" /etc/smartd.conf 2>/dev/null; then
    ok "smartd ya avisa"
else
    # Prueba corta cada noche, larga los sábados; avisa fallas y temperatura alta
    hacer "sed -i 's/^DEVICESCAN/#&/' /etc/smartd.conf && echo '$LINEA_SMART' >> /etc/smartd.conf"
    # En Debian «smartd» es un alias: se habilita por su nombre real
    hacer "systemctl enable smartmontools >/dev/null 2>&1; systemctl restart smartmontools"
fi
if [[ -f /etc/mdadm/mdadm.conf ]]; then
    if grep -q "^PROGRAM $DIR/avisar.sh" /etc/mdadm/mdadm.conf; then
        ok "mdadm ya avisa"
    else
        hacer "echo 'PROGRAM $DIR/avisar.sh --mdadm' >> /etc/mdadm/mdadm.conf"
        hacer "systemctl restart mdmonitor 2>/dev/null || true"
    fi
fi

# ---------------------------------------------------------------- timers
paso "Programación (timers de systemd)"
for unidad in "$DIR"/systemd/*; do
    destino="/etc/systemd/system/$(basename "$unidad")"
    if ! cmp -s "$unidad" "$destino"; then hacer "install -m 644 '$unidad' '$destino'"; fi
done
hacer "systemctl daemon-reload"
for timer in odoo-backup odoo-revisar odoo-verificar-backups odoo-prueba-restauracion; do
    hacer "systemctl enable --now $timer.timer >/dev/null 2>&1"
done
[[ $SIMULAR -eq 0 ]] && systemctl list-timers 'odoo-*' --no-pager | sed 's/^/   /'

# ---------------------------------------------------------------- primer backup
paso "Primer backup"
if ls /var/lib/odoo-comercio/estado/backup-*-ok >/dev/null 2>&1; then
    ok "Ya hay backups"
elif [[ $SIMULAR -eq 1 ]]; then
    echo "   → correría el primer backup (systemctl start odoo-backup)"
else
    echo "   En un servidor nuevo que va a restaurar copias de antes: responder N (si no, la"
    echo "   «última copia» pasa a ser la base vacía de este servidor)."
    read -rp "   ¿Hacer el primer backup ahora? [S/n] " RESPUESTA
    if [[ "$RESPUESTA" =~ ^[nN] ]]; then
        ok "Sin backup por ahora (el timer lo hace a las 03:00: restaurar antes)"
    else
        echo "   Puede tardar unos minutos…"
        if systemctl start odoo-backup; then ok "Backup OK (llega el aviso a Discord)"
        else aviso "Falló: journalctl -u odoo-backup -n 50"; fi
    fi
fi

paso "Listo"
cat <<FIN
   Próximos pasos (docs/runbooks/instalar-servidor.md, paso 10):
   1. Probar la restauración ahora: sudo systemctl start odoo-prueba-restauracion
   2. Sacar el pendrive un momento: en ≤ 15 min llega «El pendrive de backups no está».
FIN
