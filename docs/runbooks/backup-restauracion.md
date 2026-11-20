# Runbook: backup y restauración

ADR 0005 (formato) y 0027 (copias automáticas y avisos). Instalación en el servidor:
`instalar-servidor.md`, paso 10.

## En el servidor (automático)

| Qué | Cuándo | A mano |
|---|---|---|
| Backup al pendrive y a R2 | 03:00 | `sudo systemctl start odoo-backup` |
| Chequeo (contenedores, disco, RAID, backups, pendrive, HTTPS, hora) | cada 15 min | `sudo bash infra/servidor/revisar-servidor.sh` |
| `restic check` de las copias | domingos 05:00 | `sudo systemctl start odoo-verificar-backups` |
| Prueba de restauración desde R2 | día 1, 05:30 | `sudo systemctl start odoo-prueba-restauracion` |
| Resumen semanal (Discord y mail) | lunes desde las 9 | `sudo bash infra/servidor/revisar-servidor.sh --resumen` |

- Ver qué pasó: `journalctl -u odoo-backup -n 50` (o el servicio que sea).
- Avisos enviados: `journalctl -t odoo-aviso`.
- Próximas corridas: `systemctl list-timers 'odoo-*'`.

## Ver las copias

```bash
cd /opt/odoo-implementation
sudo bash infra/servidor/restaurar-backup.sh --listar                 # R2
sudo bash infra/servidor/restaurar-backup.sh --listar --desde pendrive
```

## Restaurar producción (DESTRUCTIVO)

Primero un backup de lo que hay, aunque esté mal: `sudo systemctl start odoo-backup`.

```bash
cd /opt/odoo-implementation
ZIP=$(sudo bash infra/servidor/restaurar-backup.sh --desde pendrive | tail -1)   # o --copia <id>
sudo STACK=onprem infra/scripts/restore-test.sh "$ZIP"                         # RESTORE_OK
sudo STACK=onprem infra/scripts/restore.sh "$ZIP" produccion
make verify ENV=onpremise
```

`restore.sh` sin `--neutralize` restaura **conservando el identificador de la base** (`odoo db load
--move`): la **suscripción Enterprise** está atada a él (04/11; antes se generaba uno nuevo y el
código quedaba desvinculado). Después de restaurar, comprobar en *Ajustes* que la base sigue
registrada y con el mismo vencimiento.

`--desde pendrive` es lo más rápido (no baja nada de Internet); `r2` si el pendrive no está.

## Servidor nuevo (el anterior se perdió)

1. `instalar-servidor.md`, pasos 1 a 7, con el equipo nuevo.
2. `sudo bash infra/servidor/configurar-respaldo-y-avisos.sh`: cuando pregunta por la clave
   de las copias, pegar la de Bitwarden «Servidor: backups (restic)», y los datos de R2 de
   «Servidor: R2 backups». No crea copias nuevas: sigue usando las de siempre. Al
   «¿Hacer el primer backup ahora?» responder **N**.
3. Restaurar como arriba, `--desde r2` (con `--listar`, elegir la copia de antes de la falla
   y pasarla con `--copia <id>`). Hacerlo antes de las 03:00, cuando corre el backup.
4. La CA de Caddy queda en `<carpeta>/restic/var/lib/odoo-comercio/caddy/`: copiarla a
   `/var/lib/odoo-comercio/caddy/` antes de levantar el proxy (`docker compose … up -d proxy`).
   Así las PCs siguen confiando en el certificado.

## En el lab

```bash
make backup                                   # → backups/<stack>-<base>-<fecha>.zip + .manifest
make restore-test FILE=backups/<archivo>.zip  # base temporal, neutralizada, se borra al final
```

`restore.sh` verifica el checksum si existe el `.manifest`. Una copia de producción en el lab
se restaura **siempre** con `--neutralize` (sin mails ni tareas programadas).

## Copia de producción en el lab (desde R2)

Para probar una actualización con los datos reales antes de hacerla en el servidor (y, de
paso, comprobar que las copias de R2 sirven aunque el servidor no exista):

```bash
make lab-copia-prod                 # la última copia de R2 → base «copia_prod» (≈ 10 min)
make lab-copia-prod COPIA=<id>      # otra copia (ver la lista abajo)
make lab-copia-prod-borrar          # borrarla del lab (son datos reales)
```

Se abre en `http://localhost:8069/web?db=copia_prod`, con los usuarios y claves de producción.
La base `lab` no se toca.

**Neutralizada** (`infra/scripts/lab-copia-prod.sh`), para que sea segura:
- sin mails ni tareas programadas (`--neutralize` de Odoo, **después** de actualizar los
  módulos, que las vuelven a activar);
- ARCA en homologación y **sin el certificado ni la clave** de producción: no se puede sacar un
  CAE real;
- identificador de base nuevo y **sin el código de suscripción**: no compite con producción;
- `web.base.url` en localhost; sin la actualización diaria del dólar.

Después aplica el código de ahora (`-u all`, como al actualizar el servidor). Los módulos
nuevos de `config/` no se instalan solos: si hace falta, `make apply ENV=lab` apunta a `lab`, no
a esta base. Lo bajado se descifra en una carpeta privada que se borra al terminar.

**Credenciales (una vez):** `~/copia-prod.env`, permisos 600, **fuera de git**:
- un **token de R2 de solo lectura** solo para el bucket `comercio-ejemplo-backups` (*R2 → Manage API
  tokens → Create Account API token → Object Read only*): no puede borrar ni escribir copias;
- la clave de restic (Bitwarden «Servidor: backups (restic)»).

```
REPO_R2=s3:https://<Account ID>.r2.cloudflarestorage.com/comercio-ejemplo-backups/servidor
AWS_ACCESS_KEY_ID=…
AWS_SECRET_ACCESS_KEY=…
RESTIC_PASSWORD=…
```

Ver las copias: `set -a; source ~/copia-prod.env; set +a; restic -r "$REPO_R2" snapshots --host odoo-comercio --no-lock`.
Ojo: esa clave abre todas las copias; la base `copia_prod` tiene datos de clientes. Borrarla
cuando no se use.
**Nunca con el lab abierto a la red:** `make lab-copia-prod` no corre si está `make lab-red`, y
`make lab-red` no abre el lab mientras exista `copia_prod` (la pantalla de bases y la clave
maestra del lab dejarían bajarse la copia desde otra PC).
