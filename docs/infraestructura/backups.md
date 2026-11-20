# Backups

Estado: **automático e implementado (ADR 0027, 27/10)**; falta probarlo en el servidor real.

## Qué se respalda

- Base de datos + filestore: el zip estándar de Odoo (ADR 0005), descomprimido para que
  restic suba solo lo que cambia. Incluye el manifiesto con checksum, versión de Odoo y commit.
- La CA interna de Caddy (`CADDY_DATA_DIR`): sin ella habría que reinstalar la raíz en todas
  las PCs.
- **No** se respaldan los secretos de `/etc/odoo-comercio/`: están en Bitwarden. La
  infraestructura se reconstruye desde este repositorio (`instalar-servidor.md`).

## Dónde y cuánto

| Copia | Dónde | Se guardan |
|---|---|---|
| Local | pendrive de 64 GB enchufado al servidor (`EJEMPLO-BK`, `/mnt/backup-usb`) | 7 diarias y 4 semanales (un mes) |
| Afuera | Cloudflare R2, bucket `comercio-ejemplo-backups` | 7 diarias y 4 semanales (un mes) |

Las dos están cifradas con restic (clave en Bitwarden «Servidor: backups (restic)»). En el
lab, la segunda copia de una base de 228 MB subió 1 MB.

## Cuándo

Backup a las 03:00; `restic check` los domingos; prueba de restauración desde R2 el día 1 de
cada mes. Todo avisa por Discord y mail (`observabilidad.md`).

## Piezas

- `infra/scripts/backup.sh`, `restore.sh`, `restore-test.sh`: el zip y su prueba (lab y servidor).
- `infra/servidor/backup-nocturno.sh`, `verificar-backups.sh`, `restaurar-backup.sh`,
  `respaldo-comun.sh`: las copias con restic.
- `infra/servidor/configurar-respaldo-y-avisos.sh` y `infra/servidor/systemd/`: instalación.
- Uso: `docs/runbooks/backup-restauracion.md`.

## Pendiente (P-013)

- Que el servidor no pueda borrar las copias de R2 (contra virus que cifran todo).
- Disco USB en lugar del pendrive.
- RPO (hoy: hasta 1 día de datos) y RTO, a acordar con el negocio.
- Costo real de R2 después del primer mes.

## Pruebas de restauración

| Fecha | Dónde | Copia | Resultado |
|---|---|---|---|
| 27/10/2026 | lab (contenedor Debian 13) | restic local | `RESTORE_OK` (164 módulos, adjuntos verificados) |

## Odoo Online

No se usa ([ADR 0011](../decisiones/0011-sin-odoo-online.md)).
