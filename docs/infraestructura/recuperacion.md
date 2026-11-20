# Recuperación ante desastres

Estado: **procedimiento escrito**, falta ensayarlo en el equipo real. Pregunta guía:
*¿qué pasa si el servidor muere completamente?*

```text
Servidor perdido
  → Equipo nuevo: instalar-servidor.md, pasos 1 a 7   (Debian 13, RAID, LUKS + TPM,
                                                      preparar-servidor.sh, instalar-odoo.sh)
  → Secretos y clave de recuperación del disco desde Bitwarden
                                                      («Comercio Ejemplo - Odoo»)
  → configurar-respaldo-y-avisos.sh con la clave de restic y los datos de R2 de siempre
  → Restaurar desde R2 (backup-restauracion.md, «Servidor nuevo»)
  → make verify ENV=onpremise                       (configuración == repo)
  → Pruebas funcionales mínimas (venta, factura, stock)
  → Servicio recuperado; registrar tiempos reales vs RTO
```

Detalle paso a paso: [backup-restauracion.md](../runbooks/backup-restauracion.md#servidor-nuevo-el-anterior-se-perdió)
y [instalar-servidor.md](../runbooks/instalar-servidor.md). Backups: ADR 0027.

Pendiente: ensayar el procedimiento completo en una máquina limpia y anotar el
tiempo real; completar con contactos, credenciales necesarias y checklist de validación.
