#!/bin/bash
# Deja listo el servidor del local después de instalar Debian 13 (ADR 0026,
# docs/runbooks/instalar-servidor.md): actualizaciones automáticas, SSH solo con llave,
# firewall, arranque desde el segundo disco y desbloqueo del disco con el TPM.
#
# Uso (en el servidor, con el usuario que va a administrarlo):
#   sudo bash preparar-servidor.sh --simular    # muestra qué haría, sin cambiar nada
#   sudo bash preparar-servidor.sh              # lo hace
#
# Se puede correr varias veces: lo que ya está hecho se saltea.
set -euo pipefail

SIMULAR=0
[[ "${1:-}" == "--simular" ]] && SIMULAR=1
GUID_EFI="c12a7328-f81f-11d2-ba4b-00a0c93ec93b"

paso() { echo; echo "== $*"; }
ok() { echo "   ✓ $*"; }
aviso() { echo "   ⚠ $*"; }
hacer() {  # muestra el comando; lo ejecuta salvo en --simular
    echo "   → $*"
    if [[ $SIMULAR -eq 0 ]]; then eval "$@"; fi
}

if [[ $EUID -ne 0 ]]; then echo "Correrlo con sudo: sudo bash $0 $*" >&2; exit 1; fi
USUARIO="${SUDO_USER:-}"
if [[ -z "$USUARIO" || "$USUARIO" == root ]]; then
    echo "Correrlo con sudo desde el usuario del técnico (no como root)." >&2; exit 1
fi
[[ $SIMULAR -eq 1 ]] && echo "MODO SIMULACIÓN: no se cambia nada."

# ---------------------------------------------------------------- comprobaciones
paso "Comprobaciones"
grep -q 'VERSION_ID="13"' /etc/os-release && ok "Debian 13" || { aviso "No es Debian 13: revisar antes de seguir."; exit 1; }
DISCO_CIFRADO="$(blkid -t TYPE=crypto_LUKS -o device | head -1)"
[[ -n "$DISCO_CIFRADO" ]] && ok "Disco cifrado: $DISCO_CIFRADO" || { aviso "No hay disco cifrado (LUKS): ¿se siguió el paso 4?"; exit 1; }
if command -v mokutil >/dev/null && mokutil --sb-state 2>/dev/null | grep -q enabled; then
    ok "Secure Boot activado"; SECURE_BOOT=1
else
    aviso "Secure Boot NO está activado (BIOS, paso 1): el TPM no se ata hasta activarlo."; SECURE_BOOT=0
fi
[[ -e /dev/tpmrm0 ]] && { ok "TPM presente"; TPM=1; } || { aviso "No se ve el TPM (BIOS: AMD fTPM, paso 1)."; TPM=0; }
RED="$(ip -4 route | awk '/proto kernel/ && /scope link/ {print $1; exit}')"
[[ -n "$RED" ]] && ok "Red del local: $RED" || { aviso "No se detectó la red local."; exit 1; }

# ---------------------------------------------------------------- paquetes y actualizaciones
paso "Paquetes y actualizaciones de seguridad automáticas"
hacer "apt-get -q update"
hacer "DEBIAN_FRONTEND=noninteractive apt-get -q -y full-upgrade"
hacer "DEBIAN_FRONTEND=noninteractive apt-get -q -y install unattended-upgrades ufw smartmontools rsync curl efibootmgr mokutil"
if [[ -f /etc/apt/apt.conf.d/20auto-upgrades ]] && grep -q 'Unattended-Upgrade "1"' /etc/apt/apt.conf.d/20auto-upgrades; then
    ok "Actualizaciones automáticas ya activadas"
else
    hacer "printf 'APT::Periodic::Update-Package-Lists \"1\";\nAPT::Periodic::Unattended-Upgrade \"1\";\n' > /etc/apt/apt.conf.d/20auto-upgrades"
fi

# ---------------------------------------------------------------- SSH
paso "SSH: solo con llave, sin root"
LLAVES="$(getent passwd "$USUARIO" | cut -d: -f6)/.ssh/authorized_keys"
if [[ -s "$LLAVES" ]]; then
    if [[ -f /etc/ssh/sshd_config.d/10-solo-llave.conf ]]; then
        ok "Ya está"
    else
        hacer "printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' > /etc/ssh/sshd_config.d/10-solo-llave.conf"
        hacer "systemctl reload ssh"
    fi
else
    aviso "$USUARIO no tiene llave SSH cargada: desde la notebook, ssh-copy-id $USUARIO@<IP>. Se deja la contraseña por ahora (correr de nuevo después)."
fi

# ---------------------------------------------------------------- firewall
paso "Firewall: todo cerrado salvo SSH y web desde $RED"
if ufw status | grep -q "Status: active"; then
    ok "Ya activo"
else
    hacer "ufw default deny incoming"
    hacer "ufw default allow outgoing"
    for puerto in 22 80 443; do hacer "ufw allow from $RED to any port $puerto proto tcp"; done
    hacer "ufw --force enable"
fi

# ---------------------------------------------------------------- arranque desde el segundo disco
paso "Arranque también desde el segundo disco"
EFI_MONTADA="$(findmnt -n -o SOURCE /boot/efi || true)"
EFI_OTRA="$(lsblk -rno PATH,PARTTYPE | awk -v g="$GUID_EFI" -v m="$EFI_MONTADA" 'tolower($2)==g && $1!=m {print $1; exit}')"
if [[ -z "$EFI_OTRA" ]]; then
    aviso "No hay segunda partición EFI (¿un solo disco?): se saltea."
else
    ok "EFI principal $EFI_MONTADA, copia en $EFI_OTRA"
    UUID_OTRA="$(blkid -s UUID -o value "$EFI_OTRA")"
    if grep -q "/boot/efi2" /etc/fstab; then
        ok "Ya está en /etc/fstab"
    else
        hacer "mkdir -p /boot/efi2"
        hacer "echo 'UUID=$UUID_OTRA /boot/efi2 vfat umask=0077,nofail 0 1' >> /etc/fstab"
        hacer "systemctl daemon-reload"
    fi
    # Si muere el primer disco, su partición EFI falta: sin «nofail» Debian entra en modo de
    # emergencia en vez de arrancar (lo encontró la prueba en máquina virtual, 26/10)
    if awk '$2=="/boot/efi" && $4 !~ /nofail/ {f=1} END {exit !f}' /etc/fstab; then
        hacer "sed -i -E '/[[:space:]]\\/boot\\/efi[[:space:]]/ s/(vfat[[:space:]]+)([^[:space:]]+)/\\1\\2,nofail/' /etc/fstab"
    else
        ok "/boot/efi ya no es obligatoria (nofail)"
    fi
    hacer "mountpoint -q /boot/efi2 || mount /boot/efi2"
    hacer "rsync -a --delete /boot/efi/ /boot/efi2/"
    if [[ ! -f /etc/apt/apt.conf.d/99-efi-espejo ]]; then
        hacer "echo 'DPkg::Post-Invoke { \"if mountpoint -q /boot/efi2; then rsync -a --delete /boot/efi/ /boot/efi2/; fi\"; };' > /etc/apt/apt.conf.d/99-efi-espejo"
    fi
    DISCO_OTRO="/dev/$(lsblk -no PKNAME "$EFI_OTRA")"
    PART_OTRA="$(lsblk -no PARTN "$EFI_OTRA")"
    if efibootmgr | grep -q "debian (disco 2)"; then
        ok "Entrada de arranque del disco 2 ya creada"
    else
        hacer "efibootmgr -q -c -d $DISCO_OTRO -p $PART_OTRA -L 'debian (disco 2)' -l '\\EFI\\debian\\shimx64.efi'"
    fi
fi

# ---------------------------------------------------------------- GRUB
# El TPM entrega la clave mientras Secure Boot esté igual (PCR 7): sin contraseña en GRUB,
# cualquiera con un teclado edita el arranque (`init=/bin/sh`) y entra con el disco abierto.
# Con contraseña, el arranque normal sigue automático (--unrestricted) y editarlo la pide.
paso "Contraseña de GRUB (editar el arranque)"
if [[ -f /etc/grub.d/01_contrasena ]]; then
    ok "Ya tiene contraseña"
elif [[ $SIMULAR -eq 1 ]]; then
    echo "   → pediría la contraseña de GRUB (la de Bitwarden «Servidor: GRUB») y la guardaría cifrada"
else
    echo "   Contraseña para editar el arranque: generarla en Bitwarden («Servidor: GRUB»)."
    # La pregunta de grub-mkpasswd-pbkdf2 sale por la salida estándar: se pide acá y se le pasa
    read -rsp "   Contraseña de GRUB: " CLAVE_GRUB; echo
    read -rsp "   Repetirla: " CLAVE_GRUB2; echo
    [[ -n "$CLAVE_GRUB" && "$CLAVE_GRUB" == "$CLAVE_GRUB2" ]] || { aviso "Vacía o no coinciden: correr de nuevo."; exit 1; }
    HASH="$(printf '%s\n%s\n' "$CLAVE_GRUB" "$CLAVE_GRUB" | grub-mkpasswd-pbkdf2 | awk '/grub.pbkdf2/ {print $NF}')"
    unset CLAVE_GRUB CLAVE_GRUB2
    [[ "$HASH" == grub.pbkdf2.* ]] || { aviso "No se generó la contraseña: correr de nuevo."; exit 1; }
    printf '#!/bin/sh\ncat <<FIN\nset superusers="admin"\npassword_pbkdf2 admin %s\nFIN\n' "$HASH" > /etc/grub.d/01_contrasena
    chmod 755 /etc/grub.d/01_contrasena
    ok "Contraseña guardada (usuario de GRUB: admin)"
fi
# Las entradas del menú arrancan sin contraseña; solo editarlas la pide
if ! grep -q -- '--unrestricted' /etc/grub.d/10_linux; then
    hacer "sed -i 's/^CLASS=\"--class gnu-linux --class gnu --class os\"/CLASS=\"--class gnu-linux --class gnu --class os --unrestricted\"/' /etc/grub.d/10_linux"
fi
if [[ $SIMULAR -eq 0 ]] && ! grep -q -- '--unrestricted' /etc/grub.d/10_linux; then
    aviso "No se pudo marcar el arranque como libre: se saca la contraseña para no trabar el arranque."
    rm -f /etc/grub.d/01_contrasena
fi
hacer "update-grub 2>/dev/null"

# ---------------------------------------------------------------- TPM
paso "Desbloqueo del disco con el TPM (Clevis)"
hacer "DEBIAN_FRONTEND=noninteractive apt-get -q -y install clevis clevis-luks clevis-tpm2 clevis-initramfs"
if [[ $SIMULAR -eq 0 ]] && clevis luks list -d "$DISCO_CIFRADO" 2>/dev/null | grep -q tpm2; then
    ok "El disco ya está atado al TPM"
elif [[ $SECURE_BOOT -eq 1 && $TPM -eq 1 ]]; then
    echo "   Va a pedir la frase del disco (la de recuperación, en Bitwarden)."
    hacer "clevis luks bind -d $DISCO_CIFRADO tpm2 '{\"pcr_bank\":\"sha256\",\"pcr_ids\":\"7\"}'"
    hacer "update-initramfs -u -k all"
else
    aviso "Sin Secure Boot o sin TPM no se ata: activarlos en el BIOS y correr de nuevo."
fi

# ---------------------------------------------------------------- acceso remoto (Tailscale)
# Solo para el técnico (ADR 0020): red privada entre sus equipos y el servidor, sin abrir
# puertos en el router. SSH queda abierto también por esa red (interfaz tailscale0).
paso "Acceso remoto del técnico (Tailscale)"
if command -v tailscale >/dev/null && tailscale status >/dev/null 2>&1; then
    ok "Tailscale ya conectado ($(tailscale ip -4 2>/dev/null | head -1))"
elif [[ $SIMULAR -eq 1 ]]; then
    echo "   → preguntaría si instalar Tailscale (instalador oficial) y mostraría el link para autorizarlo"
else
    read -rp "   ¿Instalar Tailscale para entrar desde afuera del local? [s/N] " RESPUESTA
    if [[ "$RESPUESTA" =~ ^[sS] ]]; then
        command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh
        echo "   Abrir el link que aparece y entrar con la cuenta de Tailscale del negocio."
        tailscale up --hostname=servidor-ejemplo
        ok "Tailscale conectado ($(tailscale ip -4 | head -1))"
        echo "   En https://login.tailscale.com/admin/machines: «servidor-ejemplo» → ⋯ → Disable key expiry"
        echo "   (si no, cada 180 días hay que volver a autorizarlo)."
    else
        ok "Sin Tailscale por ahora (correr el script de nuevo para sumarlo)"
    fi
fi
# Odoo por Tailscale (https://odoo.comercio-ejemplo.example con el nombre apuntando a la IP de Tailscale
# del servidor en el archivo hosts de la notebook): no hace falta regla. El 443 lo publica Docker
# (PROXY_BIND_IP=0.0.0.0) y Docker lo redirige al proxy antes de que ufw lo vea, desde cualquier
# interfaz, tailscale0 incluida (por eso nada de Docker se publica en 0.0.0.0 salvo el proxy).
if command -v tailscale >/dev/null && ! ufw status | grep -q 'tailscale0'; then
    hacer "ufw allow in on tailscale0 to any port 22 proto tcp"
fi

# ---------------------------------------------------------------- resumen
paso "Listo"
cat <<FIN
   Ahora probar (docs/runbooks/instalar-servidor.md, paso 7):
   1. sudo reboot → tiene que arrancar solo, sin pedir la frase.
   2. BIOS: Secure Boot en Disabled → tiene que PEDIR la frase. Volver a Enabled.
   3. Desenchufar y enchufar → se prende solo y arranca solo.
FIN
