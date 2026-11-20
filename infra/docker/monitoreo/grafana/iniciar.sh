#!/bin/sh
# Arranque de Grafana (ADR 0028): arma la carpeta de aprovisionamiento a partir de la del repo
# (umbrales y base) y pone el contacto de las alertas (el relay, que manda a Discord y al mail).
set -eu

DESTINO=/tmp/aprovisionamiento
rm -rf "$DESTINO"
mkdir -p "$DESTINO"
cp -R /etc/grafana/aprovisionamiento-repo/. "$DESTINO/"

# Umbrales (umbrales.env): cada @NOMBRE@ de las reglas pasa a su valor. Grafana no reemplaza
# variables adentro de las consultas ni de los umbrales, por eso se hace acá.
for variable in $(env | sed -n 's/^\(\(UMBRAL\|ALERTA\)_[A-Z0-9_]*\)=.*/\1/p'); do
    valor="$(printenv "$variable")"
    case "$valor" in
        true|false|[0-9]*) ;;
        *) echo "Umbral inválido: $variable=$valor (solo números o true/false)" >&2; exit 1 ;;
    esac
    sed -i "s/@$variable@/$valor/g" "$DESTINO"/alerting/*.yaml
done
# La base de Odoo (lab o produccion): las alertas de PostgreSQL miran solo esa
case "${MONITOREO_DB:-}" in
    ''|*[!a-z0-9_]*) echo "MONITOREO_DB inválida: '${MONITOREO_DB:-}'" >&2; exit 1 ;;
esac
sed -i "s/@MONITOREO_DB@/$MONITOREO_DB/g" "$DESTINO"/alerting/*.yaml
if grep -n '@\(UMBRAL\|ALERTA\|MONITOREO\)_[A-Z0-9_]*@' "$DESTINO"/alerting/*.yaml; then
    echo "Faltan umbrales en umbrales.env (arriba, cuáles)" >&2
    exit 1
fi

# Un solo contacto: el relay manda a Discord y al mail con el formato de avisar.sh
cp /etc/grafana/contactos/avisos.yaml "$DESTINO/alerting/contactos.yaml"

# Que las claves que Grafana no usa no queden a la vista de los paneles ni de los complementos:
# la del exporter de PostgreSQL, el webhook y el mail (los usa solo el relay)
unset SMTP_CLAVE PG_MONITOREO_CLAVE DISCORD_WEBHOOK_URL

exec /run.sh "$@"
