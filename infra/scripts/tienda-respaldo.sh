#!/usr/bin/env bash
# Respaldo de la base de la tienda (D1), en un archivo .sql comprimido con fecha: lo que SOLO está
# en la tienda (pedidos y sus pagos, clientes, equipo, arrepentimientos, registro). Tiene datos
# personales: queda FUERA del repositorio, solo legible por el dueño.
# No se respalda lo que sale de Odoo y se vuelve a mandar con «conector --todo» (catálogo, precios,
# stock, empleados, fotos de R2) ni lo pasajero (sesiones, códigos, intentos).
# D1 no exporta la base entera porque tiene la tabla de búsqueda (FTS5): se exporta tabla por tabla.
#
# Uso: make tienda-respaldo            (deja ~/respaldos-tienda/tienda-AAAA-MM-DD-HHMM.sql.gz)
#      DESTINO=/otra/carpeta make tienda-respaldo
# Restaurar: crear la base con las migraciones, borrar esas tablas y cargar el archivo:
#   gunzip -c archivo.sql.gz > t.sql && wrangler d1 execute <base> --remote --file t.sql
# Para que sea automático en el servidor del local hace falta un token de Cloudflare ahí (pendiente:
# sumarlo al restic de los backups, ADR 0013).
set -euo pipefail
BASE="${BASE_D1:-comercio-ejemplo-tienda-demo}"
DESTINO="${DESTINO:-$HOME/respaldos-tienda}"
umask 077
mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/tienda-$(date +%Y-%m-%d-%H%M).sql"
cd "$(dirname "$0")/../../web/tienda"
TABLAS=(pedidos pedido_lineas pedido_eventos pagos acciones clientes equipo arrepentimientos registro_admin listas_nuevas contadores dispositivos)
PATH="$HOME/.local/node22/bin:$PATH" npx wrangler d1 export "$BASE" --remote "${TABLAS[@]/#/--table=}" --output "$ARCHIVO" >/dev/null
# Comprobación mínima: que estén las tablas que importan
for t in pedidos clientes equipo; do
  grep -q "CREATE TABLE \(IF NOT EXISTS \)\?\"\?$t\"\?" "$ARCHIVO" || { echo "El respaldo no tiene la tabla $t" >&2; exit 1; }
done
gzip -f "$ARCHIVO"
# Se guardan los últimos 30
ls -1t "$DESTINO"/tienda-*.sql.gz 2>/dev/null | tail -n +31 | xargs -r rm -f --
echo "Respaldo: $ARCHIVO.gz ($(du -h "$ARCHIVO.gz" | cut -f1))"
