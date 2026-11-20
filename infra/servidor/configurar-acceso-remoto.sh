#!/bin/bash
# Acceso a Odoo desde fuera del local (ADR 0020): túnel de Cloudflare + Cloudflare Access en
# remoto.comercio-ejemplo.example (docs/runbooks/instalar-servidor.md, paso 12; uso: acceso-remoto.md).
#   - Cloudflare (acceso_remoto_cloudflare.py): túnel «servidor-ejemplo», aplicación de Access
#     con código por mail, política «mails autorizados Y desde Argentina», reglas del túnel y DNS;
#   - el token del túnel en /etc/odoo-comercio/tunel.env (640 root:docker, una sola línea);
#   - ACCESO_REMOTO=1 y REMOTO_HOST en onprem.env, y el stack (cloudflared + el nombre nuevo en
#     el proxy, con su certificado de Let's Encrypt);
#   - la verificación: certificado válido, cloudflared conectado y Cloudflare pidiendo el código.
#
# Mails autorizados: /etc/odoo-comercio/acceso-remoto-mails.txt, uno por línea (# comenta). Son
# datos del personal: nunca en git. Para sumar o sacar a alguien: editar el archivo y volver a
# correr el script. La lista la decide Daniel.
#
# Token de la API de Cloudflare: lo pide (no se guarda en el servidor); está en Bitwarden
# «Servidor: Cloudflare Access (configuración)». Permisos: ver docs/runbooks/acceso-remoto.md.
#
# Uso en el servidor (desde /opt/odoo-implementation):
#   sudo bash infra/servidor/configurar-acceso-remoto.sh --simular
#   sudo bash infra/servidor/configurar-acceso-remoto.sh
#   sudo bash infra/servidor/configurar-acceso-remoto.sh --borrar     # apaga y borra todo
# Prueba desde la notebook contra el lab (no toca Docker; muestra cómo levantar cloudflared):
#   bash infra/servidor/configurar-acceso-remoto.sh --nombre prueba-remoto.comercio-ejemplo.example \
#     --tunel prueba-ejemplo --origen http://odoo:8069 --mails ~/mails-prueba.txt \
#     --tunel-env ~/tunel-prueba.env [--simular | --borrar]
# Se puede correr varias veces: lo que ya está igual no se toca.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
CONF=/etc/odoo-comercio
ONPREM_ENV="$CONF/onprem.env"
IMAGEN_CLOUDFLARED="$(sed -n 's/^ *image: \(cloudflare\/cloudflared:.*\)/\1/p' "$REPO/infra/docker/compose.acceso-remoto.yml")"

SIMULAR=0
BORRAR=0
NOMBRE="${REMOTO_HOST:-remoto.comercio-ejemplo.example}"
TUNEL="${REMOTO_TUNEL:-servidor-ejemplo}"
ORIGEN="${REMOTO_ORIGEN:-https://proxy:443}"
MAILS="${REMOTO_MAILS:-$CONF/acceso-remoto-mails.txt}"
# Cada cuánto vuelve a pedir el código por mail en el mismo navegador (Cloudflare: 15m a 730h).
# 7 días: la PC fija del local no lo pide todos los días; se puede cerrar antes desde Cloudflare.
SESION="${REMOTO_SESION:-168h}"
TUNEL_ENV=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --simular) SIMULAR=1 ;;
        --borrar) BORRAR=1 ;;
        --nombre) NOMBRE="$2"; shift ;;
        --tunel) TUNEL="$2"; shift ;;
        --origen) ORIGEN="$2"; shift ;;
        --mails) MAILS="$2"; shift ;;
        --sesion) SESION="$2"; shift ;;
        --tunel-env) TUNEL_ENV="$2"; shift ;;
        *) echo "Opción desconocida: $1 (ver el encabezado del script)" >&2; exit 1 ;;
    esac
    shift
done
# Sin --tunel-env: el servidor (escribe tunel.env y levanta cloudflared). Con: solo Cloudflare.
SERVIDOR=0
if [[ -z "$TUNEL_ENV" ]]; then
    SERVIDOR=1
    TUNEL_ENV="$CONF/tunel.env"
fi

paso() { echo; echo "== $*"; }
ok() { echo "   ✓ $*"; }
aviso() { echo "   ⚠ $*"; }
hacer() {  # muestra el comando; lo ejecuta salvo en --simular
    echo "   → $*"
    if [[ $SIMULAR -eq 0 ]]; then eval "$*"; fi
}

if [[ $SERVIDOR -eq 1 ]]; then
    if [[ $EUID -ne 0 ]]; then echo "Correrlo con sudo: sudo bash $0 $*" >&2; exit 1; fi
    [[ -f "$ONPREM_ENV" ]] || { echo "Falta $ONPREM_ENV: correr antes instalar-odoo.sh" >&2; exit 1; }
fi
[[ "$NOMBRE" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ ]] || { echo "Nombre inválido: «$NOMBRE»" >&2; exit 1; }
[[ $SIMULAR -eq 1 ]] && echo "MODO SIMULACIÓN: no se cambia nada."
echo "Nombre: $NOMBRE · túnel: $TUNEL · origen: $ORIGEN"

# ---------------------------------------------------------------- mails autorizados
if [[ $BORRAR -eq 0 ]]; then
    paso "Mails autorizados ($MAILS)"
    if [[ -s "$MAILS" ]]; then
        ok "$(grep -cvE '^[[:space:]]*(#|$)' "$MAILS") mail(s)"
    elif [[ $SIMULAR -eq 1 || $SERVIDOR -eq 0 ]]; then
        aviso "No existe o está vacío: crearlo (un mail por línea) antes de correrlo de verdad."
        [[ $SIMULAR -eq 1 ]] || exit 1
    else
        echo "   Mails que pueden entrar desde afuera (los decide Daniel), uno por renglón; Enter vacío termina:"
        LISTA=""
        while read -rp "   mail: " MAIL && [[ -n "$MAIL" ]]; do LISTA+="$MAIL"$'\n'; done
        [[ -n "$LISTA" ]] || { aviso "Sin mails no se configura nada."; exit 1; }
        (umask 077; printf '# Mails autorizados para entrar a Odoo desde afuera (ADR 0020). Uno por línea.\n# Después de editarlo: sudo bash infra/servidor/configurar-acceso-remoto.sh\n%s' "$LISTA" > "$MAILS")
        ok "Guardados en $MAILS (600)"
    fi
fi

# ---------------------------------------------------------------- token de la API
paso "Token de la API de Cloudflare (Bitwarden «Servidor: Cloudflare Access (configuración)»)"
if [[ -z "${CLOUDFLARE_ACCESS_TOKEN:-}" ]]; then
    read -rsp "   Token (no se guarda): " CLOUDFLARE_ACCESS_TOKEN || true; echo
fi
if [[ -z "$CLOUDFLARE_ACCESS_TOKEN" ]]; then
    [[ $SIMULAR -eq 1 ]] || { aviso "Sin token no se puede seguir."; exit 1; }
    aviso "Sin token: la simulación no consulta Cloudflare."
    if [[ $BORRAR -eq 1 ]]; then
        aviso "Borraría la aplicación de Access de $NOMBRE, su política, el DNS y el túnel «$TUNEL»."
    else
        aviso "Haría: túnel «$TUNEL», aplicación de Access para $NOMBRE (código por mail, 24 h,"
        aviso "mails de $MAILS y solo AR), reglas del túnel y DNS."
    fi
fi
export CLOUDFLARE_ACCESS_TOKEN

ARGS=(--nombre "$NOMBRE" --tunel "$TUNEL" --origen "$ORIGEN" --mails "$MAILS" --tunel-env "$TUNEL_ENV" --sesion "$SESION")
[[ $SIMULAR -eq 1 ]] && ARGS+=(--simular)

[[ $SERVIDOR -eq 1 ]] && cd "$REPO"

# ---------------------------------------------------------------- borrar
if [[ $BORRAR -eq 1 ]]; then
    if [[ $SERVIDOR -eq 1 ]]; then
        paso "Parar cloudflared y sacar el nombre remoto del proxy"
        # Primero el contenedor: un túnel con conexiones no se puede borrar
        hacer "ACCESO_REMOTO=1 STACK=onprem bash -c 'source infra/scripts/lib.sh && compose rm -sf cloudflared'"
        hacer "sed -i '/^ACCESO_REMOTO=/d; /^REMOTO_HOST=/d; /^# Acceso desde fuera del local/d' $ONPREM_ENV"
    fi
    if [[ -n "$CLOUDFLARE_ACCESS_TOKEN" ]]; then
        python3 "$DIR/acceso_remoto_cloudflare.py" "${ARGS[@]}" --borrar
    fi
    if [[ $SERVIDOR -eq 1 ]]; then
        hacer "rm -f $TUNEL_ENV"
        # Sin ACCESO_REMOTO el proxy se recrea sin el nombre remoto ni la red del túnel
        hacer "ACCESO_REMOTO=0 STACK=onprem bash -c 'source infra/scripts/lib.sh && compose up -d --wait --remove-orphans'"
    else
        echo "   Parar el cloudflared de prueba (Ctrl+C) y borrar $TUNEL_ENV."
    fi
    paso "Listo"
    exit 0
fi

# ---------------------------------------------------------------- Cloudflare
if [[ -n "$CLOUDFLARE_ACCESS_TOKEN" ]]; then
    python3 "$DIR/acceso_remoto_cloudflare.py" "${ARGS[@]}"
fi
unset CLOUDFLARE_ACCESS_TOKEN

if [[ $SERVIDOR -eq 0 ]]; then
    paso "Prueba contra el lab"
    cat <<FIN
   Levantar cloudflared en la red del lab (Ctrl+C para cortarlo):
     docker run --rm --network odoo-lab_default --env-file $TUNEL_ENV $IMAGEN_CLOUDFLARED tunnel run
   Desde el celular con datos móviles: https://$NOMBRE → código por mail → login de Odoo.
   Al terminar: el mismo comando de configuración con --borrar.
FIN
    exit 0
fi

# ---------------------------------------------------------------- servidor
paso "Token del túnel ($TUNEL_ENV)"
if [[ -f "$TUNEL_ENV" ]]; then
    chown root:docker "$TUNEL_ENV"; chmod 640 "$TUNEL_ENV"
    ok "640 root:docker"
else
    echo "   → (simulación) quedaría con 640 root:docker"
fi

paso "Acceso remoto en onprem.env"
if grep -q '^ACCESO_REMOTO=1' "$ONPREM_ENV" && grep -qx "REMOTO_HOST=$NOMBRE" "$ONPREM_ENV"; then
    ok "Ya activado"
else
    hacer "sed -i '/^ACCESO_REMOTO=/d; /^REMOTO_HOST=/d; /^# Acceso desde fuera del local/d' $ONPREM_ENV && printf '\n# Acceso desde fuera del local (ADR 0020, compose.acceso-remoto.yml)\nACCESO_REMOTO=1\nREMOTO_HOST=$NOMBRE\n' >> $ONPREM_ENV"
fi

paso "cloudflared y el nombre remoto en el proxy"
if [[ $SIMULAR -eq 1 ]]; then
    echo "   → compose up -d --wait (se recrea el proxy: unos segundos sin Odoo en el local)"
else
    if ACCESO_REMOTO=1 STACK=onprem bash -c 'source infra/scripts/lib.sh && compose up -d --wait'; then
        ok "Levantado"
    else
        aviso "Algo no arrancó (sigue la verificación para ver qué)"
    fi
fi

# ---------------------------------------------------------------- verificación
paso "Verificación"
if [[ $SIMULAR -eq 1 ]]; then
    echo "   → certificado de $NOMBRE en el proxy, cloudflared conectado y Cloudflare pidiendo el código"
    exit 0
fi
# Desde el servidor el nombre remoto no pasa por el túnel: el proxy contesta 403 (solo atiende a
# cloudflared), pero con su certificado: así se comprueba que Let's Encrypt lo dio.
CODIGO=000
for _ in $(seq 24); do
    CODIGO="$(curl -s -o /dev/null -w '%{http_code}' --resolve "$NOMBRE:443:127.0.0.1" "https://$NOMBRE/" || true)"
    [[ "$CODIGO" == 403 ]] && break
    sleep 5
done
if [[ "$CODIGO" == 403 ]]; then ok "Certificado válido para $NOMBRE"
else aviso "Sin certificado válido todavía (código $CODIGO): compose logs proxy"; fi

ESTADO="$(ACCESO_REMOTO=1 STACK=onprem bash -c "source infra/scripts/lib.sh && compose ps --format '{{.Health}}' cloudflared")"
if [[ "$ESTADO" == healthy ]]; then ok "cloudflared conectado a Cloudflare"
else aviso "cloudflared: ${ESTADO:-no está} (compose logs cloudflared)"; fi

# Desde Internet: Cloudflare tiene que pedir el código (redirección a <equipo>.cloudflareaccess.com)
DESTINO=""
for _ in $(seq 12); do
    DESTINO="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "https://$NOMBRE/" || true)"
    [[ "$DESTINO" == 302*cloudflareaccess.com* ]] && break
    sleep 5
done
if [[ "$DESTINO" == 302*cloudflareaccess.com* ]]; then
    ok "Cloudflare Access pide el código antes de Odoo"
else
    aviso "Respuesta inesperada de https://$NOMBRE/: «$DESTINO» (¿DNS todavía propagando? probar en unos minutos)"
fi

paso "Listo"
cat <<FIN
   Desde un celular con datos móviles: https://$NOMBRE → mail autorizado → código → login de Odoo.
   Sumar o sacar a alguien: editar $MAILS y correr de nuevo este script.
   Uso y problemas: docs/runbooks/acceso-remoto.md
FIN
