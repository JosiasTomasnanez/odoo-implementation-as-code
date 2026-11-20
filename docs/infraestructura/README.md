# Infraestructura On-Premise

Estado: **servidor comprado e instalación en scripts** (ADR 0026), probada en máquina
virtual; en el equipo real desde el 27/10. La producción va en servidor propio (ADR 0007).
Backups con `restic` (pendrive + Cloudflare R2) y avisos por Discord y mail (ADR 0027).
Acceso del técnico por Tailscale; desde fuera del local, propuesto Cloudflare Access (ADR 0020).

## Arquitectura prevista

```text
              Internet
                 │
        [router / firewall]
                 │
   ┌─────────────┼──────────────────────┐
   │ VLAN servidores   VLAN puestos/POS   VLAN invitados (Wi-Fi clientes)
   │      │                 │
   │  [servidor]        cajas, lectores,
   │   ├─ proxy TLS  ◄──  impresoras, balanzas
   │   ├─ Odoo (127.0.0.1:8069)
   │   ├─ PostgreSQL (sin puertos expuestos)
   │   └─ backups ──► copia externa cifrada (P-013)
   └────────────────────────────────────┘
```

- Stack: `infra/docker/compose.yml` + `compose.onprem.yml` (ADR 0004).
- Imagen propia versionada: Odoo oficial + `addons/` del commit desplegado.
- Configuración y secretos en `/etc/odoo-comercio/` (fuera del repo, permisos 600),
  a partir de `infra/docker/*.example`.

## Documentos

- [Servidor (hardware)](servidor.md) · [Seguridad](seguridad.md) · [Red](red.md) · [Backups](backups.md) ·
  [Recuperación ante desastres](recuperacion.md) · [Observabilidad](observabilidad.md) ·
  [Enterprise vs Community](enterprise-vs-community.md)

## Despliegue

Paso a paso en [docs/runbooks/instalar-servidor.md](../runbooks/instalar-servidor.md):

1. Debian 13 a mano (BIOS, RAID 1, LUKS).
2. `infra/servidor/preparar-servidor.sh`: endurecimiento, firewall, TPM, Tailscale opcional.
3. `infra/servidor/instalar-odoo.sh`: Docker, clones en `/opt`, claves en
   `/etc/odoo-comercio`, base `produccion` y `make apply ENV=onpremise`.
4. `infra/servidor/configurar-respaldo-y-avisos.sh`: backups automáticos y avisos (ADR 0027).

Los tres son idempotentes (se pueden correr de nuevo); `preparar-servidor.sh` y
`configurar-respaldo-y-avisos.sh` aceptan `--simular`.
