# shellcheck shell=bash disable=SC2034  # se usa con source: las variables son para quien lo carga
# Funciones comunes de los backups y los chequeos del servidor (ADR 0027).
# Se usa con: source "$(dirname "$0")/respaldo-comun.sh"
#
# Rutas del servidor; para probar en el lab se cambian por variables de entorno
# (BACKUP_ENV, AVISOS_ENV, TRABAJO_DIR, ESTADO_DIR, RESTIC_CACHE_DIR).

# El volcado sin cifrar (dump.sql, adjuntos) y lo restaurado: solo root los puede leer
umask 077

SERVIDOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SERVIDOR_DIR/../.." && pwd)"
BACKUP_ENV="${BACKUP_ENV:-/etc/odoo-comercio/backup.env}"
TRABAJO_DIR="${TRABAJO_DIR:-/var/lib/odoo-comercio/backup}"
ESTADO_DIR="${ESTADO_DIR:-/var/lib/odoo-comercio/estado}"
export RESTIC_CACHE_DIR="${RESTIC_CACHE_DIR:-/var/cache/restic}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}"  # R2 no usa regiones
# Mismo nombre en un servidor nuevo: las copias siguen siendo «del servidor» al cambiar el equipo
HOST_RESTIC="odoo-comercio"

if [[ -f "$BACKUP_ENV" ]]; then set -a; source "$BACKUP_ENV"; set +a; fi
if [[ -f "${AVISOS_ENV:-/etc/odoo-comercio/avisos.env}" ]]; then
    set -a; source "${AVISOS_ENV:-/etc/odoo-comercio/avisos.env}"; set +a
fi

avisar() { "$SERVIDOR_DIR/avisar.sh" "$@" || true; }

# Ping a healthchecks.io (opcional): si deja de llegar, ellos avisan que el servidor no responde
ping_hc() {  # ping_hc <url> [/start|/fail]
    [[ -n "${1:-}" ]] || return 0
    curl -fsS -m 10 --retry 3 "$1${2:-}" >/dev/null 2>&1 || true
}

# Copias configuradas: «pendrive» y/o «r2»
copias() {
    [[ -n "${REPO_USB:-}" ]] && echo pendrive
    [[ -n "${REPO_R2:-}" ]] && echo r2
    return 0
}
repo_de() { case "$1" in pendrive) echo "$REPO_USB" ;; r2) echo "$REPO_R2" ;; esac; }
guardar_de() {  # cuántas copias se guardan (restic forget)
    case "$1" in
        pendrive) echo "${GUARDAR_USB:---keep-daily 7 --keep-weekly 4}" ;;
        r2) echo "${GUARDAR_R2:---keep-daily 7 --keep-weekly 4}" ;;
    esac
}

# El pendrive se monta solo si está enchufado (fstab con nofail); si no, se intenta montarlo
copia_disponible() {
    [[ "$1" == pendrive && -n "${USB_MONTAJE:-}" ]] || return 0
    mountpoint -q "$USB_MONTAJE" || mount "$USB_MONTAJE" >/dev/null 2>&1
    mountpoint -q "$USB_MONTAJE"
}

marcar_ok() { install -d -m 700 "$ESTADO_DIR"; date +%s > "$ESTADO_DIR/backup-$1-ok"; }

# Métricas para Grafana (ADR 0028), en formato de texto de Prometheus: node_exporter las lee de
# METRICAS_DIR (textfile collector). Sin el monitoreo instalado (no existe la carpeta) no se
# escribe nada. Se escriben enteras y se renombran, para que nunca se lea un archivo a medias.
METRICAS_DIR="${METRICAS_DIR:-/var/lib/odoo-comercio/metricas}"
escribir_metricas() {  # escribir_metricas <nombre> < contenido
    if [[ ! -d "$METRICAS_DIR" ]]; then cat >/dev/null; return 0; fi
    local tmp
    tmp="$(mktemp "$METRICAS_DIR/.$1.XXXXXX")" || return 0
    cat > "$tmp"
    chmod 644 "$tmp"  # node_exporter corre sin privilegios
    mv -f "$tmp" "$METRICAS_DIR/$1.prom"
}
# Cuándo fue el último backup bueno de cada copia (tableros «Servidor» y «PostgreSQL»; la alerta
# la dan los scripts)
metricas_copias() {
    local archivo copia
    {
        echo "# HELP odoo_backup_ultimo_ok_timestamp_seconds Fin del último backup bueno de cada copia."
        echo "# TYPE odoo_backup_ultimo_ok_timestamp_seconds gauge"
        for archivo in "$ESTADO_DIR"/backup-*-ok; do
            [[ -f "$archivo" ]] || continue
            copia="${archivo##*/backup-}"; copia="${copia%-ok}"
            echo "odoo_backup_ultimo_ok_timestamp_seconds{copia=\"$copia\"} $(cat "$archivo")"
        done
    } | escribir_metricas backup-copias
}
