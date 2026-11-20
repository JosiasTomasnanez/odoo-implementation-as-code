# 0027. Backups con restic (pendrive y Cloudflare R2) y avisos por Discord y mail

- Estado: aceptado (implementador, 27/10)
- Fecha: 2026-10-27

## Contexto

El servidor del local (ADR 0026) se instala el 27/10 y la puesta en marcha de ferretería es
la semana siguiente. Hasta ahora el backup (`infra/scripts/backup.sh`, ADR 0005) se corría a
mano, quedaba en el mismo disco, no guardaba la CA interna de Caddy (P-013) y nadie se
enteraba si algo fallaba (P-019): un disco del RAID podía morir sin aviso.

No hay disco USB todavía: el implementador compró un pendrive de 64 GB para la copia local.
El negocio ya tiene cuenta de Cloudflare (dominio, ADR 0013 y 0020). Los avisos tienen que
llegar a alguien que los lea: el implementador, por Discord y por mail. El Gmail del negocio
llega al celular de Daniel y pide su confirmación para crear contraseñas de aplicación; hasta
tener dominio propio se usa el Gmail del implementador. **27/10:** con `comercio-ejemplo.example`, el mail sale
por **Resend** desde `avisos@comercio-ejemplo.example` (registros DNS en Cloudflare; clave en Bitwarden).

## Decisión

**Backups:**
- Cada noche (03:00) se hace el zip de Odoo de siempre (ADR 0005), descomprimido en una
  carpeta fija, más la CA de Caddy.
- `restic` lo cifra y lo sube a dos copias:
  - el **pendrive** enchufado al servidor (ext4, etiqueta `EJEMPLO-BK`);
  - **Cloudflare R2** (bucket `comercio-ejemplo-backups`).
- En las dos quedan **7 diarias y 4 semanales** (un mes hacia atrás); las más viejas se borran
  solas cada noche. Sin mensuales, a pedido del implementador (27/10): pocas copias, pero un
  error que se nota tarde (precios pisados, productos borrados) se puede deshacer hasta un mes.
- La clave de restic está solo en el servidor y en Bitwarden.
- Los domingos, `restic check` lee una parte de los datos de cada copia.
- El día 1 de cada mes se baja la última copia de R2 y se restaura en una base de prueba
  (`restore-test.sh`).

**Avisos:**
- `infra/servidor/avisar.sh` manda a Discord (webhook) y por mail (SMTP con `msmtp`). Los
  «todo bien» van solo a Discord; los problemas, a los dos.
- `revisar-servidor.sh` corre cada 15 minutos. Revisa:
  - contenedores;
  - disco;
  - RAID;
  - antigüedad del último backup de cada copia;
  - pendrive;
  - certificado HTTPS;
  - hora.
- Avisa solo cuando algo cambia, en las dos direcciones: cuando se rompe y cuando se arregla.
- Los lunes manda un resumen aunque todo esté bien.
- Discos y RAID tienen aviso inmediato: `smartd` y `mdadm` llaman a `avisar.sh`.
- Opcional: healthchecks.io recibe un ping del backup y del chequeo, y avisa si el servidor
  deja de responder (lo que el servidor no puede avisar solo).

Todo se programa con timers de systemd versionados en `infra/servidor/systemd/` y se instala
con `infra/servidor/configurar-respaldo-y-avisos.sh`, que es idempotente y acepta `--simular`.
Los datos van en `/etc/odoo-comercio/avisos.env` y `backup.env`, con permisos 600.

## Alternativas consideradas

- **Copiar el zip tal cual a R2:** cada noche subiría el filestore entero (el zip cambia
  completo). Con la carpeta descomprimida, restic sube solo lo nuevo: la segunda copia en el
  lab subió 1 MB de 228 MB.
- **Backblaze B2 / S3:** sirven igual con restic. R2 queda en la cuenta del negocio y no cobra
  por descargar, así que restaurar es gratis.
- **Cron + mail del sistema (postfix):** un MTA completo para avisos es más para mantener;
  `msmtp` solo manda. Los timers dejan registro en `journalctl` y recuperan la corrida perdida
  (`Persistent=true`).
- **Grafana con alertas desde el principio:** queda para la etapa de monitoreo (después de la
  puesta en marcha). Lo crítico (backups, discos) no debe depender de ese stack.

## Consecuencias

- Cierra la parte de backups de P-013 y la de avisos de P-019. Tableros y métricas: etapa
  siguiente (ADR propio).
- Un pendrive es menos confiable que un disco: el chequeo avisa si falta o si su copia tiene
  más de 26 h. Más adelante va un disco USB (`configurar-respaldo-y-avisos.sh` lo toma si
  lleva la etiqueta `EJEMPLO-BK`).
- **Pendiente:** que el servidor no pueda borrar las copias de R2, contra virus que cifran
  todo. Hoy el token puede borrar, porque el servidor mismo aplica la retención. Opción a
  probar: el bucket lock de R2 solo sobre `data/` y `snapshots/`, por menos días que la
  retención diaria. Mientras tanto, el pendrive y R2 son dos lugares distintos, pero los dos
  quedan al alcance del servidor.
- Cambiar el mail a Resend (con dominio propio) es editar `avisos.env`, sin tocar código.
- En un servidor nuevo, con `backup.env` (los datos están en Bitwarden), `restaurar-backup.sh`
  baja la copia: `docs/runbooks/backup-restauracion.md`.
