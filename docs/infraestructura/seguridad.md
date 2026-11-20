# Seguridad On-Premise

Estado: **implementado en scripts** (ADR 0026): lo marcado «script» lo hace
`infra/servidor/preparar-servidor.sh` (idempotente, `--simular`). **Probado en máquina
virtual; falta el equipo real** (desde el 27/10). Defensa en profundidad: ninguna medida
sola alcanza.

| Capa | Medida | Estado |
|------|--------|--------|
| Física | servidor en lugar con llave; UPS; inventario de equipos | pendiente (ubicación y UPS, P-011) |
| Firmware | contraseña de BIOS/UEFI, arranque solo desde disco interno, **Secure Boot** | a mano (`instalar-servidor.md`, paso 1); el script comprueba Secure Boot |
| Disco | LUKS2 sobre RAID 1, **desbloqueado por el TPM** (Clevis, PCR 7 = Secure Boot); clave de recuperación en Bitwarden; llave de red del local (Tang) más adelante | script |
| Sistema operativo | **Debian 13** mínimo, sin escritorio; `unattended-upgrades` (seguridad automática); `smartmontools` | script |
| Acceso | SSH solo con llave, sin root, sin contraseña; acceso remoto del técnico por **Tailscale** (opcional en el script); acceso del personal desde fuera del local por **Cloudflare Access + túnel** en `remoto.comercio-ejemplo.example` (ADR 0020, 27/10): código por mail solo a mails autorizados, solo desde Argentina, sesión de 24 h; ese nombre no abre el gestor de bases ni las API | script (`configurar-acceso-remoto.sh`); falta el equipo real |
| Firewall | `ufw` deny por defecto; 22, 80 y 443 solo desde la red del local; SSH también por `tailscale0`. Ojo: el 443 lo publica Docker y no pasa por `ufw` (también llega por Tailscale, que es lo que usa el técnico); el túnel de Cloudflare no abre nada (solo sale) | script (VLAN: ver [red](red.md)) |
| Contenedores | PostgreSQL sin puertos publicados; Odoo solo en 127.0.0.1; imágenes con versión fija | aplicado en compose |
| TLS | proxy Caddy con HTTPS válido (CA interna; Let's Encrypt DNS-01 con dominio), HSTS, cookie de sesión `Secure`; la clave de la CA interna se respalda como secreto (ADR 0013) | listo en compose, probado en el lab |
| Odoo | `list_db = False`, `dbfilter`, contraseña maestra fuerte, `proxy_mode`, mínimo privilegio | plantilla en `odoo.onprem.conf.example` |
| Secretos | fuera del repo, permisos 600, rotación documentada | pendiente |
| Backups | `restic` cifrado a un pendrive en el servidor y a Cloudflare R2, con prueba de restauración (ADR 0027) | ver [backups](backups.md) |
| Monitoreo y logs | avisos por Discord y mail, revisión cada 15 min (ADR 0027); tableros (Grafana) más adelante (P-019) | ver [observabilidad](observabilidad.md) |
