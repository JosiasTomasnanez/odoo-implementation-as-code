#!/bin/bash
# Chequeo del servidor cada 15 minutos (ADR 0027, timer odoo-revisar). Avisa solo cuando algo
# CAMBIA (se rompe o se arregla), no en cada vuelta. Los lunes a la mañana manda un resumen
# aunque esté todo bien, para que el silencio no sea dudoso.
#
#   sudo bash revisar-servidor.sh            chequeo normal
#   sudo bash revisar-servidor.sh --resumen  manda el resumen ahora
#
# Discos (SMART) y RAID tienen aviso propio e inmediato (smartd y mdadm llaman a avisar.sh).
set -uo pipefail
export STACK="${STACK:-onprem}"
source "$(dirname "$0")/respaldo-comun.sh"
source "$REPO_DIR/infra/scripts/lib.sh"
set +e  # lib.sh activa -e: acá cada chequeo sigue aunque otro falle

UMBRAL_DISCO="${UMBRAL_DISCO:-85}"       # % de uso
HORAS_BACKUP="${HORAS_BACKUP:-26}"       # el backup es diario
DIAS_CERTIFICADO="${DIAS_CERTIFICADO:-14}"
mkdir -p "$ESTADO_DIR/chequeos"

declare -a LINEAS=()
CAMBIOS_MAL=(); CAMBIOS_BIEN=()

# resultado <clave> <ok|mal> <detalle>: compara con la vuelta anterior
resultado() {
    local estado="$2" detalle="$3" archivo="$ESTADO_DIR/chequeos/$1" anterior=ok
    [[ -f "$archivo" ]] && anterior="$(head -1 "$archivo")"
    printf '%s\n%s\n' "$estado" "$detalle" > "$archivo"
    if [[ "$estado" == ok ]]; then LINEAS+=("✓ $detalle"); else LINEAS+=("✗ $detalle"); fi
    if [[ "$estado" != "$anterior" ]]; then
        if [[ "$estado" == ok ]]; then CAMBIOS_BIEN+=("$detalle"); else CAMBIOS_MAL+=("$detalle"); fi
    fi
}

# ---------------------------------------------------------------- contenedores
ESPERADOS="$(compose config --services 2>/dev/null | sort)"
# Un contenedor que se está reiniciando (una actualización, «starting») no es una caída: se
# vuelve a mirar durante unos minutos antes de avisar (19/11: un aviso de error por mail salió
# justo mientras se actualizaba Odoo).
ESPERA_CONTENEDORES="${ESPERA_CONTENEDORES:-300}"  # segundos
for ((espera = 0; ; espera += 30)); do
    MALOS=()
    for servicio in $ESPERADOS; do
        linea="$(compose ps --format '{{.State}} {{.Health}}' "$servicio" 2>/dev/null | head -1)"
        [[ "$linea" == running* && "$linea" != *unhealthy* && "$linea" != *starting* ]] || MALOS+=("$servicio (${linea:-no está})")
    done
    (( ${#MALOS[@]} == 0 || espera >= ESPERA_CONTENEDORES )) && break
    sleep 30
done
if [[ -z "$ESPERADOS" ]]; then
    resultado contenedores mal "Contenedores: no se pudo consultar Docker"
elif [[ ${#MALOS[@]} -eq 0 ]]; then
    resultado contenedores ok "Contenedores: $(echo "$ESPERADOS" | paste -sd, ) funcionando"
else
    resultado contenedores mal "Contenedores con problemas: ${MALOS[*]}"
fi

# ---------------------------------------------------------------- disco
LLENOS=()
while read -r uso montaje; do
    uso="${uso%\%}"
    (( uso >= UMBRAL_DISCO )) && LLENOS+=("$montaje al $uso%")
done < <(df --output=pcent,target -x tmpfs -x devtmpfs -x overlay -x squashfs -x efivarfs -x vfat 2>/dev/null | tail -n +2)
if [[ ${#LLENOS[@]} -eq 0 ]]; then
    resultado disco ok "Espacio en disco: todo por debajo del $UMBRAL_DISCO%"
else
    resultado disco mal "Disco casi lleno: ${LLENOS[*]}"
fi

# ---------------------------------------------------------------- RAID
if grep -q '^md' /proc/mdstat 2>/dev/null; then
    if grep -qE '\[[U_]*_[U_]*\]' /proc/mdstat; then
        resultado raid mal "RAID degradado: un disco no está en el espejo ($(grep -oE '^md[0-9]+.*' /proc/mdstat | tr '\n' ';'))"
    else
        resultado raid ok "RAID: los dos discos en espejo"
    fi
fi

# ---------------------------------------------------------------- backups
if [[ -f "$BACKUP_ENV" ]]; then
    for copia in $(copias); do
        archivo="$ESTADO_DIR/backup-$copia-ok"
        if [[ -f "$archivo" ]]; then
            horas=$(( ($(date +%s) - $(cat "$archivo")) / 3600 ))
            if (( horas <= HORAS_BACKUP )); then
                resultado "backup-$copia" ok "Último backup en $copia: hace $horas h"
            else
                resultado "backup-$copia" mal "No hay backup bueno en $copia desde hace $horas h"
            fi
        else
            resultado "backup-$copia" mal "Todavía no hay ningún backup bueno en $copia"
        fi
    done
    if [[ -n "${USB_MONTAJE:-}" ]]; then
        if copia_disponible pendrive; then
            resultado pendrive ok "Pendrive de backups enchufado"
        else
            resultado pendrive mal "El pendrive de backups no está (¿lo sacaron?)"
        fi
    fi
fi

# ---------------------------------------------------------------- certificado HTTPS
if [[ "$STACK" == onprem ]]; then
    NOMBRE="$(sed -n 's/^ODOO_HOSTS=//p' "$ENV_FILE" | tail -1 | cut -d, -f1 | tr -d ' ')"
    if [[ -n "$NOMBRE" ]]; then
        VENCE="$(echo | openssl s_client -connect 127.0.0.1:443 -servername "$NOMBRE" 2>/dev/null \
                 | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
        if [[ -z "$VENCE" ]]; then
            resultado certificado mal "HTTPS no responde en $NOMBRE"
        else
            dias=$(( ($(date -d "$VENCE" +%s) - $(date +%s)) / 86400 ))
            if (( dias >= DIAS_CERTIFICADO )); then
                resultado certificado ok "Certificado HTTPS de $NOMBRE: vence en $dias días"
            else
                resultado certificado mal "El certificado HTTPS de $NOMBRE vence en $dias días (Caddy no lo renovó)"
            fi
        fi
    fi
fi

# ---------------------------------------------------------------- hora
if command -v timedatectl >/dev/null && [[ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" == yes ]]; then
    resultado hora ok "Hora sincronizada"
elif command -v timedatectl >/dev/null; then
    resultado hora mal "La hora del servidor no está sincronizada (afecta facturas y backups)"
fi

# ---------------------------------------------------------------- métricas para Grafana (ADR 0028)
# Edad de los backups y líneas ERROR/CRITICAL del registro de Odoo en estos 15 minutos (sin
# Loki: alcanza con contarlas). Solo si el monitoreo está instalado (existe METRICAS_DIR).
if [[ -d "$METRICAS_DIR" ]]; then
    metricas_copias
    REGISTRO_ODOO="$(compose logs --since 15m --no-color --no-log-prefix odoo 2>/dev/null)"
    {
        echo "# HELP odoo_log_lineas Líneas del registro de Odoo por nivel en los últimos 15 minutos."
        echo "# TYPE odoo_log_lineas gauge"
        for nivel in ERROR CRITICAL WARNING; do
            echo "odoo_log_lineas{nivel=\"$nivel\"} $(grep -c " $nivel " <<< "$REGISTRO_ODOO")"
        done
    } | escribir_metricas odoo-log
    # Posición del WAL (bytes escritos desde que se creó la base): su ritmo = WAL generado
    WAL="$(compose exec -T db psql -U odoo -d postgres -Atc "SELECT pg_current_wal_lsn() - '0/0'" 2>/dev/null)"
    if [[ "$WAL" =~ ^[0-9]+$ ]]; then
        printf '# HELP odoo_pg_wal_bytes_total Posición del WAL de PostgreSQL.\n# TYPE odoo_pg_wal_bytes_total counter\nodoo_pg_wal_bytes_total %s\n' "$WAL" \
            | escribir_metricas postgresql-wal
    fi
fi

# ---------------------------------------------------------------- avisos
if [[ ${#CAMBIOS_MAL[@]} -gt 0 ]]; then
    avisar error "Problema en el servidor: ${CAMBIOS_MAL[0]}" "$(printf '%s\n' "${CAMBIOS_MAL[@]}")"
fi
if [[ ${#CAMBIOS_BIEN[@]} -gt 0 ]]; then
    avisar ok "Se arregló: ${CAMBIOS_BIEN[0]}" "$(printf '%s\n' "${CAMBIOS_BIEN[@]}")"
fi

# Resumen semanal: lunes desde las 9, una vez por semana
SEMANA="$(date +%G-%V)"
if [[ "${1:-}" == "--resumen" ]] || { [[ "$(date +%u)" == 1 && "$(date +%H)" -ge 9 ]] \
       && [[ "$(cat "$ESTADO_DIR/resumen-semana" 2>/dev/null)" != "$SEMANA" ]]; }; then
    MAL_AHORA="$(printf '%s\n' "${LINEAS[@]}" | grep -c '^✗')"
    if [[ "$MAL_AHORA" -eq 0 ]]; then NIVEL=ok; ASUNTO="Resumen semanal: todo bien"
    else NIVEL=aviso; ASUNTO="Resumen semanal: $MAL_AHORA problema(s)"; fi
    ULTIMA="sin hacer"
    [[ -f "$ESTADO_DIR/restauracion-ok" ]] && ULTIMA="$(date -d "@$(cat "$ESTADO_DIR/restauracion-ok")" '+%d/%m/%Y')"
    MAIL_TODO=si avisar "$NIVEL" "$ASUNTO" "$(printf '%s\n' "${LINEAS[@]}")
Última prueba de restauración: $ULTIMA
Encendido desde: $(uptime -s 2>/dev/null)"
    echo "$SEMANA" > "$ESTADO_DIR/resumen-semana"
fi

printf '%s\n' "${LINEAS[@]}"
ping_hc "${HC_REVISION_URL:-}"
