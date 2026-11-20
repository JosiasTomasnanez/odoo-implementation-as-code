# 0028. Monitoreo con Prometheus y Grafana: tableros y alertas con umbrales

- Estado: aceptado en el lab (implementador, 27/10); falta instalarlo en el servidor
- Fecha: 2026-10-27

## Contexto

Los avisos del servidor (ADR 0027) cubren lo que puede dejar al local sin sistema o sin
copias: contenedores caídos, disco lleno, RAID, backups, pendrive, certificado, hora y SMART.
Son scripts que corren cada 15 minutos y avisan cuando algo **se rompe**. No guardan historia
ni miran tendencias.

`observabilidad.md` pedía no sumar un stack de monitoreo sin una necesidad concreta. Ahora
hay dos:

1. **Umbrales con historia.** Saber si algo **se está por romper** (un disco que se llena en
   una semana, una base que crece de golpe, Odoo cada vez más lento, una transacción colgada
   que traba el vacuum) y poder mirar hacia atrás qué pasó a una hora dada. PostgreSQL es lo
   que más interesa al implementador.
2. **Trazabilidad del negocio.** El implementador pidió ver pedidos por puesto y por hora,
   compras, facturas en excepción, listas sin importar, cambios de costo y precios pendientes
   sin abrir Odoo pantalla por pantalla.

Restricciones:
- un solo servidor: Ryzen 5, 16 GB de RAM, Odoo con 3 workers;
- el stack entero tiene que quedar muy por debajo de 1 GB;
- nada publicado a la red del local ni a Internet;
- los datos no salen del servidor;
- lo crítico tiene que seguir avisando aunque Grafana se caiga.

## Decisión

Un overlay de compose, `infra/docker/compose.monitoreo.yml`, que se suma a cualquiera de los dos
stacks con `MONITOREO=1`. Toda la configuración está en `infra/docker/monitoreo/`.

| Pieza | Para qué | Por qué esa |
|---|---|---|
| Prometheus v3.13.4 | guarda las métricas 30 días, lectura cada 30 s | estándar, un binario, ~100 MB con ~13 000 series |
| node_exporter v1.12.1 | CPU, RAM, discos, red, temperaturas, RAID, y las métricas que escriben los scripts (backups, errores del log de Odoo) | el único que ve el servidor real; corre en la red del host y escucha solo en la puerta de enlace de la red interna |
| postgres_exporter v0.20.1 | conexiones, transacciones, caché, locks, tablas, vacuum, WAL, wraparound, consultas lentas | usuario `monitoreo` con `pg_monitor` (estadísticas, sin datos) |
| `pg_stat_statements` | consultas lentas | guarda el texto normalizado (los valores pasan a `$1`) y no registra comandos de administración (`track_utility=off`), que sí guardarían claves |
| blackbox_exporter v0.29.0 | cuánto tarda Odoo (`/web/login`) y si responde (`/web/health`) | más liviano que prender las métricas de Caddy y anda igual en el lab, que no tiene proxy. El HTTPS lo sigue revisando `revisar-servidor.sh` |
| cAdvisor v0.60.6 | CPU y RAM por contenedor | ~20 MB con solo CPU y memoria y lectura cada 30 s; sin él no se ve quién usa la RAM |
| Grafana 13.2.4 | tableros, alertas, contacto por mail | provisionado desde el repo; solo en 127.0.0.1; en el servidor se entra por `tailscale serve` (HTTPS, solo la tailnet) |
| relay a Discord (Python, biblioteca estándar) | las alertas llegan con la misma tarjeta que `avisar.sh` | ver abajo |

**Tableros (en el repo).** Se generan con `grafana/generar_tableros.py`:
- «Servidor»;
- «PostgreSQL»;
- «Negocio (Odoo)».

El de negocio lee la base con `grafana_lector`, un usuario de solo lectura. Solo tiene permiso
sobre **las columnas** que usan las consultas (`monitoreo/usuarios.sql`): nada de mails,
teléfonos ni direcciones de clientes.

**Alertas (en el repo).** Son 21 reglas de Grafana: servidor, Odoo, PostgreSQL y 3 de negocio
de ejemplo. Los umbrales están en un solo archivo, `monitoreo/umbrales.env`. No se repite nada
de lo que ya avisan los scripts.

**Discord: relay en vez del contacto nativo.** En Grafana 13.2.4 el contacto de Discord
(`grafana/alerting`, `receivers/discord/v1/discord.go`):
- fija el pie en «Grafana v13.2.4»;
- usa solo rojo o verde según el estado, sin niveles;
- agrega un link a la regla.

Los avisos tienen que verse igual que los de `avisar.sh`. Por eso Grafana usa un contacto
*webhook* hacia `relay-discord`, un contenedor sin puertos publicados que arma la misma tarjeta:
- color según la etiqueta `nivel`;
- ícono en el título;
- el detalle en un bloque;
- el pie «servidor · fecha · Grafana»;
- «✅ Se arregló: …» al resolverse.

El formato está una sola vez, en `infra/servidor/formato_avisos.py`, que usan `avisar.sh` y el
relay. El **mail** también lo manda el relay (27/10: el de Grafana tenía otro diseño), en HTML
con la misma tarjeta, con el SMTP de `avisos.env` (Resend). Solo se manda si hay SMTP y, como en
`avisar.sh`, no manda los «se arregló».

## Alternativas consideradas

- **Netdata:** tableros automáticos y livianos, pero las alertas y tableros propios (sobre
  todo los del negocio, en SQL) se versionan peor. Además, empuja a su nube para lo mejor.
- **Grafana Cloud (capa gratis):** no hay que mantener Grafana, pero las métricas y las
  consultas de negocio salen del servidor. Descartado: los datos no salen del local.
- **Solo scripts (ampliar `revisar-servidor.sh`):** sirve para estados (anda o no anda), no
  para tendencias, historia ni tableros. Siguen siendo la primera línea para lo crítico.
- **Contacto nativo de Discord de Grafana:** más simple, pero no deja controlar pie, color
  ni timestamp (ver arriba).
- **Loki para el registro de Odoo:** otro servicio y más RAM. Por ahora alcanza con contar
  las líneas ERROR/CRITICAL cada 15 minutos (`revisar-servidor.sh`). Loki queda para la etapa
  3c, si hace falta buscar en el registro.
- **Métricas de Caddy:** obligan a abrir su puerto de administración o sumar un sitio. Además,
  no existen en el lab.

## Consecuencias

- **RAM medida en el lab:** ~430 MB en total. Grafana ~250 MB, Prometheus ~100 MB, el resto
  entre 10 y 25 MB cada uno. Los límites de memoria suman 944 MB.
- **Si Grafana se cae, los avisos críticos siguen.** Los da `revisar-servidor.sh`, que además
  avisa si el contenedor de Grafana se cae (con `MONITOREO=1`, el stack entra en su chequeo de
  contenedores).
- **PostgreSQL arranca con `pg_stat_statements`.** El servicio `db` de `compose.yml` cambia, y la
  primera vez la base se reinicia unos segundos.
- **Al actualizar Odoo hay que revisar las consultas del negocio.** Dependen de nombres de tablas
  y columnas de Odoo y de los módulos propios: `docs/codigo-propio.md`. `make verify-monitoreo`
  corre todas contra la base.
- **Grafana baja dos complementos de grafana.com la primera vez que arranca.** Son las fuentes
  Prometheus y PostgreSQL, que ya no vienen adentro desde Grafana 12. Quedan con versión fija.
- **No se guarda en el backup.** Las métricas son descartables (30 días) y la configuración está
  en git.
- **Pendiente:**
  - confirmar con Daniel el horario para la alerta «no hubo pedidos» (está apagada) y las
    cantidades de las alertas de negocio;
  - definir si la etapa 3c (Loki) hace falta.
