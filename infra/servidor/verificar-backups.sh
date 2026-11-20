#!/bin/bash
# Verifica las copias (ADR 0027). Un backup que nunca se restauró no está validado.
#   verificar-backups.sh              restic check de cada copia, leyendo una parte de los datos
#                                     (timer odoo-verificar-backups, domingos)
#   verificar-backups.sh --restaurar  además baja la última copia (R2 si hay) y la restaura en
#                                     una base de prueba (timer odoo-prueba-restauracion, mensual)
set -uo pipefail
export STACK="${STACK:-onprem}"
source "$(dirname "$0")/respaldo-comun.sh"

RESTAURAR=0
[[ "${1:-}" == "--restaurar" ]] && RESTAURAR=1
REGISTRO="$(mktemp)"; TEMPORAL=""
trap 'rm -f "$REGISTRO"; [[ -n "$TEMPORAL" ]] && rm -rf "$TEMPORAL"' EXIT
exec > >(tee -a "$REGISTRO") 2>&1

BIEN=(); MAL=()
for copia in $(copias); do
    echo "== Verificando: $copia"
    if ! copia_disponible "$copia"; then MAL+=("$copia: no disponible"); continue; fi
    # Leer todo de R2 cada semana es lento: se lee una parte distinta cada vez
    if restic -r "$(repo_de "$copia")" check --read-data-subset=10%; then
        BIEN+=("$copia")
    else
        MAL+=("$copia: restic check falló")
    fi
done

if [[ $RESTAURAR -eq 1 ]]; then
    echo "== Prueba de restauración"
    TEMPORAL="$(mktemp -d -p "$TRABAJO_DIR" prueba-XXXX)"
    if ZIP="$("$SERVIDOR_DIR/restaurar-backup.sh" --destino "$TEMPORAL" | tail -1)" && [[ -f "$ZIP" ]] \
       && "$REPO_DIR/infra/scripts/restore-test.sh" "$ZIP"; then
        BIEN+=("restauración")
        date +%s > "$ESTADO_DIR/restauracion-ok"
    else
        MAL+=("la prueba de restauración falló")
    fi
fi

if [[ ${#MAL[@]} -eq 0 ]]; then
    avisar ok "Copias verificadas: ${BIEN[*]}" "$(grep -E 'RESTORE_OK|no errors' "$REGISTRO" | tail -3)"
else
    avisar error "Verificación de copias: ${MAL[*]}" "$(tail -25 "$REGISTRO")"
    exit 1
fi
