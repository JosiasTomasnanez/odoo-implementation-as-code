# Observabilidad y mantenimiento

Estado: **avisos de los scripts implementados (ADR 0027, 27/10); tableros y alertas de Grafana
probados en el lab (ADR 0028, 27/10), falta instalarlos en el servidor.**

## Avisos (hecho)

Llegan al implementador por **Discord** y por **mail** (`infra/servidor/avisar.sh`; datos en
`/etc/odoo-comercio/avisos.env`). Los «todo bien» van solo a Discord.

| Qué | Cómo | Cuándo avisa |
|---|---|---|
| Contenedores (db, odoo, proxy) | healthcheck de compose | al caerse y al volver |
| Espacio en disco | `df`, umbral 85 % | al pasar el umbral y al bajar |
| RAID | `/proc/mdstat` y `mdadm` (PROGRAM) | al instante |
| Discos | `smartd` (prueba corta diaria, larga los sábados, temperatura) | al instante |
| Backups | antigüedad del último bueno en cada copia (> 26 h) | al vencerse y al volver |
| Pendrive de backups | montado o no | al sacarlo y al volver |
| Certificado HTTPS | vence en < 14 días | al entrar en ese plazo |
| Hora | NTP sincronizado | al desincronizarse |
| Servidor caído / sin Internet | healthchecks.io (opcional, ping cada 15 min y del backup) | lo avisan ellos |
| Resumen | todo lo anterior + última prueba de restauración | lunes a la mañana |

El chequeo (`revisar-servidor.sh`, cada 15 min) guarda el estado en
`/var/lib/odoo-comercio/estado/chequeos/` y avisa solo cuando algo cambia.

## Grafana: tableros y alertas con umbrales (ADR 0028)

Prometheus + exportadores + Grafana en el mismo servidor (`infra/docker/compose.monitoreo.yml`).
Se entra solo por Tailscale: `https://servidor-ejemplo.<tailnet>.ts.net:8443`. Uso diario:
`docs/runbooks/monitoreo.md`.

**Dos capas, sin repetir:**
- **Los scripts** (arriba) vigilan lo que deja al local sin sistema o sin copias. Tienen que
  avisar aunque Grafana esté caído, y también avisan si se cae un contenedor del monitoreo.
- **Grafana** mira tendencias y umbrales con historia: lo que **se está por romper**.

| Qué | Umbral (en `umbrales.env`) | Nivel |
|---|---|---|
| CPU | > 90 % durante 15 min | aviso |
| RAM disponible | < 10 % durante 10 min | error |
| Swap usada | > 50 % durante 30 min | aviso |
| Un disco se llena (al ritmo de 12 h) | en < 7 días | aviso |
| Disco ocupado (E/S) | > 90 % durante 15 min | aviso |
| Temperatura | > 85 °C durante 10 min | aviso |
| Prometheus no lee un exportador | 5 min | aviso |
| Odoo lento (`/web/login`) | > 3 s durante 5 min | aviso |
| Odoo no responde | 3 min | error |
| Conexiones de PostgreSQL | > 80 % del máximo, 5 min | aviso |
| Transacción abierta | > 10 min | aviso |
| «idle in transaction» | > 5 min | aviso |
| Deadlocks | alguno en 10 min | aviso |
| Lecturas desde memoria (cache hit) | < 95 % durante 30 min, con movimiento | aviso |
| Archivos temporales | > 1 GB en una hora | aviso |
| Edad de XID (wraparound) | > 50 % del límite durante 1 h | error |
| Tabla > 50 MB con > 10 000 filas muertas sin autovacuum | > 7 días | aviso |
| La base crece | > 2 GB en 24 h | aviso |
| *Negocio:* no hubo pedidos (lun-sáb) | después de las 11 (**apagada** hasta confirmar el horario) | aviso |
| *Negocio:* facturas de proveedor en «Excepción» | > 5 | aviso |
| *Negocio:* lista de proveedor sin importar | > 14 días | aviso |

**Cambiar un umbral.** Se edita el número en `infra/docker/monitoreo/umbrales.env` (versionado)
y se vuelve a correr `configurar-monitoreo.sh` (en el lab, `make lab-monitoreo`). No se edita
en Grafana. Las reglas están en `grafana/aprovisionamiento/alerting/reglas-*.yaml`.

**A quién llegan.** Al mismo Discord que los scripts, con la misma tarjeta y «· Grafana» al
pie (por `relay-discord`). Si hay SMTP en `avisos.env`, también por mail; los «se arregló»,
solo a Discord. Se repiten una vez por día mientras sigan.

**Tableros** (`grafana/tableros/`, generados por `generar_tableros.py`; se regeneran con
`make tableros`):

| Tablero | Filas |
|---|---|
| Servidor | resumen; CPU y memoria; discos (uso, días hasta llenarse, E/S, RAID); red; temperaturas; contenedores (CPU, RAM contra el límite, OOM); Odoo (respuesta, errores del registro); backups |
| PostgreSQL | resumen; conexiones y esperas; actividad (commits, rollbacks, deadlocks, temporales); caché y disco; tablas (más grandes, más crecen, adjuntos y mensajes, filas muertas y último vacuum, lecturas completas, índices sin uso); consultas lentas (`pg_stat_statements`); WAL, checkpoints y wraparound; backups |
| Negocio (Odoo) | hoy; pedidos por puesto (día, hora, día de la semana, resumen); productos (más vendidos, sin movimiento); stock (negativo, bajo mínimo, movimientos); compras (órdenes, facturas, recepciones pendientes, excepciones, compras sin factura); listas de proveedores; costos y precios; actividad por usuario |

El de negocio lee la base con `grafana_lector`, que solo tiene permiso sobre las columnas que
usan las consultas (`monitoreo/usuarios.sql`). Las consultas lentas muestran el texto que
normaliza PostgreSQL (`$1`, `$2`…), sin valores.

**Métricas que escriben los scripts** (`/var/lib/odoo-comercio/metricas/`, las lee node_exporter):
- `backup-nocturno.sh`: tamaño, duración y adjuntos del backup;
- `backup-nocturno.sh` y `revisar-servidor.sh`: cuándo fue el último backup bueno de cada copia;
- `revisar-servidor.sh`: líneas ERROR/CRITICAL del registro de Odoo y posición del WAL.

**No se mide (todavía):**
- la espera concreta de cada consulta (`wait_event`): verla da acceso al texto, con datos, de
  las consultas en curso;
- el «bloat» exacto (se usan las filas muertas);
- el registro de Odoo completo (Loki, etapa 3c, solo si hace falta buscar en él).
