# Monitoreo (Grafana)

ADR 0028. Qué vigila cada cosa: `docs/infraestructura/observabilidad.md`.

## Entrar

- **Servidor:** `https://servidor-ejemplo.<tailnet>.ts.net:8443`. Tiene que ser desde una
  compu con Tailscale. Usuario `admin`; la clave está en Bitwarden, «Servidor: Grafana admin».
- **Lab:** `make lab-monitoreo` → `http://localhost:3000` (`admin` / `ejemplo-lab`).
  Para apagarlo: `make lab-monitoreo-down`.

Los tableros están en *Dashboards → Comercio Ejemplo*. Cada fila se abre con un clic, y el período
se elige arriba a la derecha.

| Tablero | Para qué |
|---|---|
| Servidor | CPU, RAM, discos, red, temperaturas, contenedores, cuánto tarda Odoo, errores del registro, backups |
| PostgreSQL | conexiones, actividad, caché, tablas que crecen, vacuum, índices, consultas lentas, WAL |
| Negocio (Odoo) | pedidos por puesto, día y hora; productos; stock; compras; listas; costos y precios; actividad por usuario |

## Cambiar un umbral

1. Editar `infra/docker/monitoreo/umbrales.env`: solo el número.
2. Commitear y, en el servidor, hacer `git pull`.
3. Aplicarlo:
   - en el servidor: `sudo bash infra/servidor/configurar-monitoreo.sh`;
   - en el lab: `make lab-monitoreo`.
4. Revisar con `make verify-monitoreo` (en el servidor, `sudo make verify-monitoreo STACK=onprem`).

Las reglas están en `grafana/aprovisionamiento/alerting/reglas-*.yaml`. No se editan en
Grafana: lo que se toca ahí se pierde al reiniciar.

Para **borrar** una regla, se saca del YAML y se agrega un archivo con `deleteRules`, con su
`uid`. Grafana no borra sola una regla que se sacó del YAML.

## Cambiar un tablero

1. Editar `infra/docker/monitoreo/grafana/generar_tableros.py`.
2. Correr `make tableros`.
3. Commitear los dos: el `.py` y los `.json`.

Grafana lo toma en un minuto. Si la consulta nueva lee otra columna de Odoo, hay que sumarla en
`infra/docker/monitoreo/usuarios.sql` (el usuario de Grafana solo ve esas columnas) y correr
`configurar-monitoreo.sh` (o `make lab-monitoreo`).

## Silenciar durante un mantenimiento

1. Ir a *Alertas → Silencios → Nuevo silencio*.
2. Poner la duración (p. ej. 2 h).
3. Agregar el filtro: `alertname` = el nombre de la regla, o `nivel =~ aviso|error` para todas.

Feriados y días de cierre: silenciar «No hubo pedidos hoy» hasta el día siguiente.

Los avisos de los scripts (`revisar-servidor.sh`) no se silencian desde Grafana.

## Probar los avisos

- **En el servidor:** *Alertas → Puntos de contacto → avisos → Probar*. Llega una tarjeta a
  Discord y, si hay SMTP, un mail.
- **En el lab:** `make verify-monitoreo AVISOS=1`. El «Discord» es un receptor de prueba y el
  mail llega a Mailpit.

## Qué hacer con cada alerta

| Alerta | Qué mirar / hacer |
|---|---|
| CPU alta / Poca RAM / Swap | tablero Servidor → Contenedores: quién la usa. Una importación grande pasa sola; si es Odoo siempre, ver «Consultas lentas» |
| Un disco se llena pronto | `sudo du -xh / \| sort -h \| tail`; tablero PostgreSQL → «Tablas que más crecieron» y «Adjuntos y mensajes» |
| Disco saturado | `cat /proc/mdstat` (RAID reconstruyendo); ¿coincide con el backup de las 03:00? |
| Temperatura alta | ventilación del rack, polvo, ventiladores |
| No se leen métricas | `docker ps`; si es «servidor»: `sudo ufw status \| grep 9100` |
| Odoo lento | los 3 workers ocupados (importación, informe) o la base: tableros Servidor y PostgreSQL |
| Odoo no responde | `compose ps`, `compose logs --tail 50 odoo`; `revisar-servidor.sh` también avisa |
| Muchas conexiones | tablero PostgreSQL → Conexiones por estado; reiniciar Odoo las libera |
| Transacción larga / idle in transaction | ver abajo |
| Deadlocks | registro de Odoo a esa hora (`deadlock detected`): qué pantalla o tarea |
| Lee mucho del disco / temporales | «Consultas lentas» y «Lecturas completas en tablas grandes»; quizás subir `shared_buffers` o `work_mem` |
| Wraparound | muy raro: ver abajo |
| Tabla sin autovacuum | casi siempre una transacción colgada: ver abajo |
| La base crece de golpe | «Tablas que más crecieron» (últimas 24 h): ¿`mail_message`? ¿una importación repetida? |
| Facturas en excepción | tablero Negocio → Compras; las revisa la administración |
| Lista sin importar | pedir la lista nueva al proveedor, o archivar la lista si ya no se usa |
| No hubo pedidos hoy | ¿los puestos entran a Odoo? ¿hay red? |

**Transacción larga, idle in transaction o tabla sin autovacuum.** Ver qué es:

```bash
STACK=onprem bash -c 'source infra/scripts/lib.sh && compose exec db psql -U odoo -d produccion -c \
  "SELECT pid, usename, state, now() - xact_start AS hace, left(query, 80) FROM pg_stat_activity
   WHERE xact_start IS NOT NULL ORDER BY xact_start LIMIT 5"'
```

- Si es un `odoo shell` o un script olvidado, cerrarlo.
- Si no, cortarla con `SELECT pg_terminate_backend(<pid>)`. Al usuario que la tenía abierta le
  sale un error y repite lo que estaba haciendo.

**Wraparound.** Revisar que el autovacuum esté prendido (`SHOW autovacuum`) y que no haya
transacciones colgadas. Si sigue subiendo, correr `VACUUM (FREEZE, VERBOSE)` fuera de horario.

## Cambiar la clave de admin de Grafana

```bash
STACK=onprem bash -c 'source infra/scripts/lib.sh && compose exec grafana grafana cli admin reset-admin-password <nueva>'
```

Guardar la nueva en Bitwarden y en `GF_SECURITY_ADMIN_PASSWORD` de
`/etc/odoo-comercio/monitoreo.env`.
