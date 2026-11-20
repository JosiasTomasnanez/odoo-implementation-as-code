# 0005. Backups en el formato zip estándar de Odoo

- Estado: aceptado
- Fecha: 2026-09-30

## Contexto

Un backup útil de Odoo necesita la base **y** el filestore (adjuntos, imágenes).
Además, Odoo Online permite descargar backups en su propio formato.

## Decisión

Usar `odoo db dump` / `odoo db load` (zip con `dump.sql`, `filestore/` y
`manifest.json`). Cada backup lleva un `.manifest` con sha256, versión de Odoo y
commit del repo. `restore-test.sh` restaura en una base temporal neutralizada y
valida módulos, usuarios y adjuntos antes de darla por buena.

## Alternativas consideradas

- `pg_dump` + `tar` del filestore por separado: más piezas que sincronizar.
- Snapshots de volúmenes: dependen del almacenamiento y no son portables.

## Consecuencias

- Mismo formato que los backups de Odoo Online: un backup de Online puede
  restaurarse On-Premise (camino de migración), siempre que coincidan versión y edición.
- Para bases grandes el zip puede ser lento; se reevaluará con datos reales.
- Copia externa, cifrado y retención siguen pendientes (P-013).
