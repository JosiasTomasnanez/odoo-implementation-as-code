#!/bin/bash
# Instala Odoo en el servidor del local, después de preparar-servidor.sh (ADR 0026,
# docs/runbooks/instalar-servidor.md, paso 8): Docker, los repositorios (este y Enterprise),
# la configuración con sus claves, Odoo con HTTPS, la base «produccion» y la configuración
# del repositorio (make apply).
#
# Uso (en el servidor, con el usuario del técnico):
#   sudo bash instalar-odoo.sh
# Se puede correr varias veces: lo que ya está hecho se saltea. Las claves que genera se
# muestran UNA vez: guardarlas en Bitwarden en ese momento.
set -euo pipefail

REPO_IMPLEMENTACION="${REPO_IMPLEMENTACION:-git@github.com:JosiasTomasnanez/odoo-implementation-as-code.git}"
REPO_ENTERPRISE="${REPO_ENTERPRISE:-git@github.com:odoo/enterprise.git}"
DIR_REPO=/opt/odoo-implementation
DIR_ENTERPRISE=/opt/odoo-enterprise
CONF=/etc/odoo-comercio
BASE=produccion

paso() { echo; echo "== $*"; }
ok() { echo "   ✓ $*"; }
aviso() { echo "   ⚠ $*"; }
clave() { openssl rand -base64 33 | tr -d '/+=' | cut -c1-32; }

if [[ $EUID -ne 0 ]]; then echo "Correrlo con sudo: sudo bash $0" >&2; exit 1; fi
USUARIO="${SUDO_USER:-}"
[[ -n "$USUARIO" && "$USUARIO" != root ]] || { echo "Correrlo con sudo desde el usuario del técnico." >&2; exit 1; }
HOGAR="$(getent passwd "$USUARIO" | cut -d: -f6)"
como_tecnico() { sudo -u "$USUARIO" -H bash -c "$1"; }
CLAVES_NUEVAS=()
# Cada clave nueva se muestra apenas se genera (si algo falla después, no se pierde) y se
# repite en el resumen del final.
clave_nueva() {
    CLAVES_NUEVAS+=("$1")
    echo
    echo "   GUARDAR AHORA EN BITWARDEN (no se vuelve a mostrar): $1"
    read -rp "   Enter cuando esté guardada… " _
}

# ---------------------------------------------------------------- Docker y herramientas
paso "Docker (repositorio oficial) y herramientas"
grep -q 'VERSION_ID="13"' /etc/os-release || { aviso "No es Debian 13."; exit 1; }
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
    ok "Docker ya instalado ($(docker --version | cut -d, -f1))"
else
    apt-get -q update
    DEBIAN_FRONTEND=noninteractive apt-get -q -y install ca-certificates curl
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get -q update
    DEBIAN_FRONTEND=noninteractive apt-get -q -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    ok "Docker instalado"
fi
DEBIAN_FRONTEND=noninteractive apt-get -q -y install git make python3-venv openssl >/dev/null
if id -nG "$USUARIO" | grep -qw docker; then
    ok "$USUARIO ya usa Docker"
else
    usermod -aG docker "$USUARIO"
    ok "$USUARIO puede usar Docker (desde el próximo inicio de sesión)"
fi

# ---------------------------------------------------------------- GitHub
paso "Llave del servidor para GitHub (cuenta CasaEjemplo)"
if [[ "$REPO_IMPLEMENTACION" == git@* || "$REPO_ENTERPRISE" == git@* ]]; then
    if [[ ! -f "$HOGAR/.ssh/id_ed25519" ]]; then
        como_tecnico "mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keygen -q -t ed25519 -N '' -C 'servidor-ejemplo' -f ~/.ssh/id_ed25519"
    fi
    # ssh -T a GitHub sale siempre con código 1 (no da shell): se mira solo el texto, no el
    # código, porque con pipefail un «| grep» daría siempre falla.
    until RESPUESTA="$(como_tecnico "ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -T git@github.com 2>&1" || true)"
          [[ "$RESPUESTA" == *"successfully authenticated"* ]]; do
        echo "   GitHub respondió: $RESPUESTA"
        echo
        echo "   Agregar esta llave en GitHub, entrando como CasaEjemplo:"
        echo "   Settings → SSH and GPG keys → New SSH key (título: servidor-ejemplo)"
        echo
        cat "$HOGAR/.ssh/id_ed25519.pub"
        echo
        read -rp "   Cuando esté agregada, Enter para probar de nuevo… " _
    done
    ok "GitHub reconoce la llave del servidor"
fi

# ---------------------------------------------------------------- repositorios
paso "Repositorios"
install -d -o "$USUARIO" -g "$USUARIO" "$DIR_REPO" "$DIR_ENTERPRISE"
if [[ -d "$DIR_REPO/.git" ]]; then
    como_tecnico "git -C $DIR_REPO pull --ff-only --quiet" && ok "Implementación al día"
else
    como_tecnico "git clone --quiet $REPO_IMPLEMENTACION $DIR_REPO" && ok "Implementación clonada en $DIR_REPO"
fi
if [[ -d "$DIR_ENTERPRISE/.git" ]]; then
    ok "Enterprise ya clonado en $DIR_ENTERPRISE"
else
    como_tecnico "git clone --quiet --depth 1 --branch 20.0 $REPO_ENTERPRISE $DIR_ENTERPRISE" && ok "Enterprise clonado en $DIR_ENTERPRISE"
fi

# ---------------------------------------------------------------- configuración y claves
paso "Configuración ($CONF, fuera del repositorio)"
install -d -m 750 -o root -g docker "$CONF"
install -d -m 700 /var/lib/odoo-comercio/caddy
if [[ ! -f "$CONF/db_password" ]]; then
    clave > "$CONF/db_password"
    ok "Clave de PostgreSQL generada (no hace falta anotarla: queda en $CONF)"
fi
# Lo lee PostgreSQL adentro de su contenedor (usuario 999 de la imagen oficial)
chown 999:docker "$CONF/db_password"; chmod 640 "$CONF/db_password"
if [[ ! -f "$CONF/odoo.conf" ]]; then
    MAESTRA="$(clave)"
    sed -e "s|^db_password = CAMBIAR|db_password = $(cat "$CONF/db_password")|" \
        -e "s|^admin_passwd = CAMBIAR|admin_passwd = $MAESTRA|" \
        "$DIR_REPO/infra/docker/odoo.onprem.conf.example" > "$CONF/odoo.conf"
    clave_nueva "Odoo: contraseña maestra (gestor de bases) = $MAESTRA"
fi
# Servidores instalados antes del 04/11: los módulos propios pasaron de /mnt/extra-addons (un VOLUME
# de la imagen oficial, que Docker reusaba con archivos viejos) a /opt/comercio-addons.
if grep -q '^addons_path *=.*/mnt/extra-addons' "$CONF/odoo.conf"; then
    sed -i 's|/mnt/extra-addons|/opt/comercio-addons|' "$CONF/odoo.conf"
    ok "odoo.conf: módulos propios en /opt/comercio-addons"
fi
# Lo lee Odoo adentro de su contenedor (usuario 100 de la imagen oficial)
chown 100:docker "$CONF/odoo.conf"; chmod 640 "$CONF/odoo.conf"
if [[ ! -f "$CONF/onprem.env" ]]; then
    sed -e "s|^ODOO_ENTERPRISE_ADDONS=.*|ODOO_ENTERPRISE_ADDONS=$DIR_ENTERPRISE|" \
        "$DIR_REPO/infra/docker/onprem.env.example" > "$CONF/onprem.env"
    read -rp "   Clave de Gemini para la IA (Enter = sin IA por ahora): " GEMINI
    [[ -n "$GEMINI" ]] && sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=$GEMINI|" "$CONF/onprem.env"
    # HTTPS (ADR 0013): con dominio propio, certificado de Let's Encrypt (las PCs no instalan
    # nada); sin dominio, la CA propia de Caddy (hay que instalar su raíz en cada PC, paso 8)
    read -rp "   Dominio para el HTTPS [comercio-ejemplo.example] («-» = sin dominio, CA propia): " DOMINIO
    DOMINIO="${DOMINIO:-comercio-ejemplo.example}"
    if [[ "$DOMINIO" != "-" ]]; then
        sed -i -e "s|^ODOO_HOSTS=.*|ODOO_HOSTS=odoo.$DOMINIO|" -e "s|^CADDY_TLS_MODO=.*|CADDY_TLS_MODO=dominio|" \
            "$CONF/onprem.env"
        ok "HTTPS con certificado de Let's Encrypt para odoo.$DOMINIO"
    else
        sed -i -e "s|^ODOO_HOSTS=.*|ODOO_HOSTS=odoo.ejemplo.internal|" -e "s|^CADDY_TLS_MODO=.*|CADDY_TLS_MODO=interna|" \
            "$CONF/onprem.env"
        aviso "Sin dominio: CA propia (paso 8 en cada PC) y url de environments/onpremise.yaml a odoo.ejemplo.internal"
    fi
    ok "onprem.env creado"
fi
chown root:docker "$CONF/onprem.env"; chmod 640 "$CONF/onprem.env"
MODO="$(sed -n 's/^CADDY_TLS_MODO=//p' "$CONF/onprem.env" | tail -1)"
if [[ "$MODO" == dominio && ! -s "$CONF/proxy.env" ]]; then
    echo "   Token de Cloudflare para el DNS (Bitwarden «Servidor: Cloudflare DNS (certificados)»):"
    read -rsp "   Token: " TOKEN; echo
    [[ -n "$TOKEN" ]] || { aviso "Sin token no hay certificado: correr de nuevo."; exit 1; }
    (umask 027; echo "CLOUDFLARE_API_TOKEN=$TOKEN" > "$CONF/proxy.env")
    unset TOKEN
    ok "Token guardado en $CONF/proxy.env"
fi
[[ -f "$CONF/proxy.env" ]] && { chown root:docker "$CONF/proxy.env"; chmod 640 "$CONF/proxy.env"; }
grep -q '^ODOO_CONF_FILE=' "$CONF/onprem.env" && ok "Configuración lista"

# ---------------------------------------------------------------- versión de Enterprise
paso "Enterprise de la misma fecha que la imagen de Odoo"
IMAGEN="$(sed -n 's/^ODOO_BASE_IMAGE=//p' "$CONF/onprem.env" | tail -1)"
como_tecnico "$DIR_REPO/infra/scripts/fijar-enterprise.sh $DIR_ENTERPRISE $IMAGEN" | sed 's/^/   ✓ /'

# ---------------------------------------------------------------- Odoo
paso "Odoo con HTTPS (construye la imagen la primera vez: unos minutos)"
cd "$DIR_REPO"
# shellcheck source=/dev/null
STACK=onprem source infra/scripts/lib.sh
compose up -d --build --wait
ok "Odoo y el proxy HTTPS andando"
NOMBRE="$(sed -n 's/^ODOO_HOSTS=//p' "$CONF/onprem.env" | tail -1 | cut -d, -f1)"
grep -q " $NOMBRE\$" /etc/hosts || echo "127.0.0.1 $NOMBRE" >> /etc/hosts
if [[ "$MODO" == dominio ]]; then
    # Las PCs encuentran el servidor por el DNS de Cloudflare (IP privada, sin publicar nada)
    PROXY_ENV="$CONF/proxy.env" "$DIR_REPO/infra/servidor/registrar-dns.sh" "$NOMBRE" | sed 's/^/   /'
    echo "   Esperando el certificado de Let's Encrypt (hasta 3 minutos)…"
    CERT=0
    for _ in $(seq 36); do
        if curl -fsS -o /dev/null --resolve "$NOMBRE:443:127.0.0.1" "https://$NOMBRE/web/health"; then CERT=1; break; fi
        sleep 5
    done
    if [[ $CERT -eq 1 ]]; then ok "Certificado válido para $NOMBRE"
    else aviso "Todavía sin certificado: compose logs proxy (¿token o zona?) y correr de nuevo."; fi
else
    RAIZ=/var/lib/odoo-comercio/caddy/caddy/pki/authorities/local/root.crt
    for _ in $(seq 30); do [[ -f "$RAIZ" ]] && break; sleep 2; done
    [[ -f "$RAIZ" ]] && install -m 644 "$RAIZ" "$CONF/caddy-raiz.crt" && ok "Raíz del HTTPS interno en $CONF/caddy-raiz.crt (instalarla en las PCs)"
fi

# ---------------------------------------------------------------- base de producción
paso "Base «$BASE»"
if compose exec -T db psql -U odoo -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$BASE'" | grep -q 1; then
    ok "La base ya existe (no se toca)"
else
    ADMIN="$(clave)"
    compose stop odoo
    odoo_cli db -c /etc/odoo/odoo.conf init "$BASE" --language es_AR --country AR --username admin --password "$ADMIN"
    compose up -d --wait odoo
    clave_nueva "Odoo: usuario admin de la base $BASE = $ADMIN"
    ok "Base creada (es_AR, Argentina, sin datos de ejemplo)"
fi
if ! grep -q '^ODOO_ONPREMISE_API_KEY=' "$DIR_REPO/.env" 2>/dev/null; then
    KEY="$(odoo_cli shell -c /etc/odoo/odoo.conf -d "$BASE" --no-http --log-level=warn <<'PY' | grep '^APIKEY=' | cut -d= -f2
admin = env.ref("base.user_admin")
key = env["res.users.apikeys"].with_user(admin).sudo()._generate("rpc", "odoo-iac servidor", None)
env.cr.commit()
print(f"APIKEY={key}")
PY
)"
    [[ -n "$KEY" ]] || { aviso "No se pudo generar la API key de odoo-iac."; exit 1; }
    como_tecnico "touch $DIR_REPO/.env && chmod 600 $DIR_REPO/.env && echo ODOO_ONPREMISE_API_KEY=$KEY >> $DIR_REPO/.env"
    ok "API key de odoo-iac en $DIR_REPO/.env"
fi

# Dirección de Odoo para los links de los mails: fija. Si no, Odoo la cambia al nombre por el
# que entra el administrador (p. ej. remoto.comercio-ejemplo.example, ADR 0020). Los PDF no dependen
# de esto: van por report.url (config/base/07-direccion-reportes.yaml).
odoo_cli shell -c /etc/odoo/odoo.conf -d "$BASE" --no-http --log-level=warn <<PY >/dev/null
icp = env["ir.config_parameter"].sudo()
icp.set_str("web.base.url", "https://$NOMBRE")
icp.set_bool("web.base.url.freeze", True)
env.cr.commit()
PY
ok "Dirección de Odoo fija: https://$NOMBRE"

# ---------------------------------------------------------------- módulos
# Por la API (make apply) Odoo corta a los 240 s (limit_time_real) y la instalación de todos
# los módulos juntos tarda más: el proxy da 502 y queda a medias. Desde la línea de comandos
# no hay límite. Se instalan los declarados en las capas de onpremise que todavía no estén.
paso "Módulos declarados en config/"
CAPAS="$(sed -n '/^layers:/,/^[a-z]/s/^  - \([^ ]*\).*/\1/p' environments/onpremise.yaml)"
DECLARADOS="$(for c in $CAPAS; do
    if [[ -f "$c/00-modulos.yaml" ]]; then sed -n 's/^  - \([a-z0-9_]*\).*/\1/p' "$c/00-modulos.yaml"; fi
done | sort -u)"
INSTALADOS="$(compose exec -T db psql -U odoo -d "$BASE" -tAc "SELECT name FROM ir_module_module WHERE state = 'installed'" | sort -u)"
FALTAN="$(comm -23 <(echo "$DECLARADOS") <(echo "$INSTALADOS") | paste -sd,)"
if [[ -z "$FALTAN" ]]; then
    ok "Todos instalados"
else
    echo "   Instalando: $FALTAN (unos minutos)"
    compose stop odoo
    odoo_cli -c /etc/odoo/odoo.conf -d "$BASE" -i "$FALTAN" --stop-after-init --log-level=warn
    compose up -d --wait odoo
    ok "Módulos instalados"
fi

# ---------------------------------------------------------------- configuración del repositorio
paso "Configuración de Odoo desde el repositorio (make apply ENV=onpremise)"
# Con la CA propia, odoo-iac tiene que confiar en su raíz; con Let's Encrypt, ya confía
CA_PROPIA=""
if [[ "$MODO" != dominio ]]; then CA_PROPIA="SSL_CERT_FILE=$CONF/caddy-raiz.crt"; fi
como_tecnico "cd $DIR_REPO && make setup >/dev/null && $CA_PROPIA make apply ENV=onpremise"

# ---------------------------------------------------------------- resumen
paso "Listo"
if [[ "$MODO" == dominio ]]; then
    echo "   Odoo: https://$NOMBRE  (las PCs no necesitan nada; si no lo encuentran: paso 8)"
else
    echo "   Odoo: https://$NOMBRE  (en las PCs: docs/runbooks/instalar-servidor.md, paso 8)"
fi
if (( ${#CLAVES_NUEVAS[@]} )); then
    echo
    echo "   Claves nuevas de esta corrida (ya tienen que estar en Bitwarden):"
    for c in "${CLAVES_NUEVAS[@]}"; do echo "     • $c"; done
fi
echo
echo "   Sigue: backups y avisos (instalar-servidor.md, paso 10: configurar-respaldo-y-avisos.sh)."
