# ruff: noqa: E501  (consultas PromQL y SQL largas: se leen mejor en una línea)
"""Genera los tableros de Grafana (ADR 0028): grafana/tableros/*.json.

Los tableros se escriben acá, en Python (más corto y revisable que cientos de líneas de JSON),
y se versionan los dos: este archivo y los JSON que lee Grafana. Para cambiar un tablero:
    python3 infra/docker/monitoreo/grafana/generar_tableros.py
y Grafana lo toma solo en un minuto (aprovisionamiento/dashboards/tableros.yaml).

Las consultas SQL del tablero «Negocio (Odoo)» dependen de nombres de tablas y columnas de Odoo
y de los módulos propios (docs/codigo-propio.md): `make verify-monitoreo` las corre todas
contra la base con el usuario de solo lectura. El usuario solo puede leer las columnas
listadas en monitoreo/usuarios.sql: una consulta nueva puede necesitar sumar columnas ahí.
"""

import json
from pathlib import Path

DESTINO = Path(__file__).parent / "tableros"
PROM = {"type": "prometheus", "uid": "prometheus"}
SQL = {"type": "grafana-postgresql-datasource", "uid": "odoo"}
TZ = "America/Argentina/Cordoba"
BASE = 'datname="$base"'


# ---------------------------------------------------------------- piezas de los tableros

class Tablero:
    """Arma un tablero con filas plegables; acomoda los paneles de izquierda a derecha."""

    def __init__(self, uid, titulo, descripcion, variables=(), desde="now-7d"):
        self.uid, self.titulo, self.descripcion = uid, titulo, descripcion
        self.variables, self.desde = list(variables), desde
        self.paneles, self.fila, self.x, self.y, self.alto = [], None, 0, 0, 0
        self.id = 0

    def seccion(self, titulo, abierta=False):
        self._cerrar_renglon()
        self.id += 1
        self.fila = {"type": "row", "id": self.id, "title": titulo, "collapsed": not abierta,
                     "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}, "panels": []}
        self.paneles.append(self.fila)
        self.y += 1
        self.abierta = abierta

    def _cerrar_renglon(self):
        if self.x:
            self.y += self.alto
            self.x, self.alto = 0, 0

    def agregar(self, panel, ancho=12, alto=8):
        if self.x + ancho > 24:
            self._cerrar_renglon()
        self.id += 1
        panel["id"] = self.id
        panel["gridPos"] = {"h": alto, "w": ancho, "x": self.x, "y": self.y}
        self.x += ancho
        self.alto = max(self.alto, alto)
        if self.fila is not None and not self.abierta:
            self.fila["panels"].append(panel)
        else:
            self.paneles.append(panel)

    def json(self):
        self._cerrar_renglon()
        return {
            "uid": self.uid, "title": self.titulo, "description": self.descripcion,
            "tags": ["casa-ejemplo"], "timezone": TZ, "editable": False,
            "graphTooltip": 1, "refresh": "1m", "schemaVersion": 41, "version": 1,
            "time": {"from": self.desde, "to": "now"},
            "templating": {"list": self.variables}, "panels": self.paneles,
            "annotations": {"list": []}, "links": [],
        }


def prom(expr, leyenda="", instant=False, ref="A"):
    t = {"datasource": PROM, "expr": expr, "refId": ref, "legendFormat": leyenda or "__auto"}
    if instant:
        t.update(instant=True, range=False, format="table")
    return t


def sql(consulta, formato="time_series", ref="A"):
    return {"datasource": SQL, "rawSql": " ".join(consulta.split()), "format": formato, "refId": ref,
            "rawQuery": True, "editorMode": "code"}


def _panel(tipo, titulo, objetivos, descripcion="", unidad=None, **extra):
    fuente = objetivos[0]["datasource"]
    panel = {"type": tipo, "title": titulo, "description": descripcion, "datasource": fuente,
             "targets": objetivos,
             "fieldConfig": {"defaults": {}, "overrides": extra.pop("overrides", [])},
             "options": extra.pop("options", {})}
    if unidad:
        panel["fieldConfig"]["defaults"]["unit"] = unidad
    for clave in ("min", "max", "decimals", "thresholds", "mappings", "custom", "color"):
        if clave in extra:
            panel["fieldConfig"]["defaults"][clave] = extra.pop(clave)
    panel.update(extra)
    return panel


def umbrales(*pasos):
    """umbrales(("green", None), ("orange", 80), ("red", 90))"""
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in pasos]}


def serie(titulo, objetivos, descripcion="", unidad=None, apilado=False, barras=False, **extra):
    custom = {"drawStyle": "bars" if barras else "line", "fillOpacity": 60 if barras else 10,
              "lineWidth": 1 if barras else 2, "showPoints": "never", "spanNulls": True,
              "stacking": {"mode": "normal" if apilado else "none"}}
    custom.update(extra.pop("custom", {}))
    opciones = {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                "tooltip": {"mode": "multi", "sort": "desc"}}
    return _panel("timeseries", titulo, objetivos, descripcion, unidad, custom=custom, options=opciones,
                  **extra)


def dato(titulo, objetivos, descripcion="", unidad=None, color="value", **extra):
    opciones = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "colorMode": color, "graphMode": "none", "textMode": "auto", "justifyMode": "center"}
    extra.setdefault("thresholds", umbrales(("green", None)))
    # El número es el valor de ahora: consulta instantánea, así no depende del rango elegido
    # (con «Últimos 30 días» y poca historia, el paso del gráfico dejaba «No data»)
    for objetivo in objetivos:
        if objetivo.get("datasource") == PROM:
            objetivo.update(instant=True, range=False)
    return _panel("stat", titulo, objetivos, descripcion, unidad, options=opciones, **extra)


def tabla(titulo, objetivos, descripcion="", unidad=None, transformaciones=(), orden=None, **extra):
    opciones = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
    if orden:
        opciones["sortBy"] = [{"displayName": orden[0], "desc": orden[1]}]
    extra.setdefault("custom", {"align": "auto", "filterable": False})
    return _panel("table", titulo, objetivos, descripcion, unidad, options=opciones,
                  transformations=list(transformaciones), **extra)


def barras_categoria(titulo, objetivos, descripcion="", unidad=None, apilado=True, **extra):
    """Gráfico de barras con categorías en X (p. ej. la hora del día)."""
    opciones = {"orientation": "vertical", "stacking": "normal" if apilado else "none",
                "showValue": "never", "groupWidth": 0.8, "barWidth": 0.9, "xTickLabelRotation": 0,
                "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                "tooltip": {"mode": "multi", "sort": "desc"}}
    return _panel("barchart", titulo, objetivos, descripcion, unidad, options=opciones, **extra)


def medidor(titulo, objetivos, descripcion="", unidad=None, **extra):
    opciones = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                "valueMode": "color", "namePlacement": "left", "sizing": "auto"}
    return _panel("bargauge", titulo, objetivos, descripcion, unidad, options=opciones, **extra)


def ocultar(*columnas, renombrar=None):
    return {"id": "organize", "options": {"excludeByName": {c: True for c in columnas},
                                          "renameByName": renombrar or {}}}


UNIR = {"id": "merge", "options": {}}
SIN_TIEMPO = ("Time", "__name__", "instance", "job", "datname", "schemaname")


def nombre(campo):
    """Texto traducible de Odoo (jsonb): español, si no inglés."""
    return f"COALESCE({campo}->>'es_AR', {campo}->>'en_US')"


def local(columna):
    """Columna de Odoo (UTC sin zona) a la hora de Argentina (sin zona)."""
    return f"({columna} AT TIME ZONE 'UTC' AT TIME ZONE '{TZ}')"


def dia(columna):
    """Comienzo del día de Argentina de esa columna, como instante (para series por día)."""
    return f"date_trunc('day', {local(columna)}) AT TIME ZONE '{TZ}'"


HOY = f"date_trunc('day', now() AT TIME ZONE '{TZ}')"


# ---------------------------------------------------------------- tablero «Servidor»

def tablero_servidor():
    t = Tablero("servidor", "Servidor", "CPU, memoria, discos, red, temperaturas, contenedores, "
                "respuesta de Odoo y backups del servidor del local (ADR 0028).", desde="now-24h")
    disco = 'fstype!~"tmpfs|overlay|squashfs|vfat|ramfs|nsfs|fuse.*"'
    dispositivo = 'device!~"loop.*|ram.*|dm-.*|sr.*"'
    red = 'device!~"lo|veth.*|br-.*|docker.*|tailscale.*"'

    t.seccion("Resumen", abierta=True)
    t.agregar(dato("Encendido hace", [prom("time() - node_boot_time_seconds")], unidad="s"), 4, 4)
    t.agregar(dato("CPU", [prom('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))')],
                   unidad="percent", thresholds=umbrales(("green", None), ("orange", 70), ("red", 90))), 4, 4)
    t.agregar(dato("RAM usada", [prom("100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)")],
                   unidad="percent", thresholds=umbrales(("green", None), ("orange", 80), ("red", 90))), 4, 4)
    t.agregar(dato("Disco más lleno", [prom(f"max(100 * (1 - node_filesystem_avail_bytes{{{disco}}} "
                                            f"/ node_filesystem_size_bytes{{{disco}}}))")],
                   unidad="percent", thresholds=umbrales(("green", None), ("orange", 75), ("red", 85))), 4, 4)
    t.agregar(dato("Temperatura máxima", [prom("max(node_hwmon_temp_celsius)")], unidad="celsius",
                   thresholds=umbrales(("green", None), ("orange", 75), ("red", 85))), 4, 4)
    t.agregar(dato("Odoo responde en", [prom('probe_duration_seconds{instance=~".*/web/login"}')],
                   "Lo que tarda la página de entrada de Odoo (con la base).", unidad="s",
                   thresholds=umbrales(("green", None), ("orange", 1.5), ("red", 3))), 4, 4)

    t.seccion("CPU y memoria")
    t.agregar(serie("CPU por uso", [prom('100 * sum by (mode) (rate(node_cpu_seconds_total{mode!="idle"}[$__rate_interval])) '
                                         '/ scalar(count(count by (cpu) (node_cpu_seconds_total)))', "{{mode}}")],
                    "user = programas (Odoo, PostgreSQL); iowait = esperando al disco.", "percent",
                    apilado=True, max=100))
    t.agregar(serie("Carga (procesos esperando CPU)", [
        prom("node_load1", "1 min"), prom("node_load5", "5 min", ref="B"), prom("node_load15", "15 min", ref="C"),
        prom("count(count by (cpu) (node_cpu_seconds_total))", "núcleos", ref="D")],
        "Por encima de la cantidad de núcleos, hay procesos haciendo cola."))
    t.agregar(serie("Memoria", [
        prom("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "usada"),
        prom("node_memory_Cached_bytes + node_memory_Buffers_bytes", "caché de disco (se libera sola)", ref="B"),
        prom("node_memory_MemAvailable_bytes", "disponible", ref="C")], unidad="bytes"))
    t.agregar(serie("Swap", [
        prom("node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes", "usada"),
        prom("rate(node_vmstat_pswpin[$__rate_interval]) * 4096", "leída por segundo", ref="B"),
        prom("rate(node_vmstat_pswpout[$__rate_interval]) * 4096", "escrita por segundo", ref="C")],
        "Si la swap se lee y escribe todo el tiempo, falta RAM.", "bytes"))

    t.seccion("Discos")
    t.agregar(medidor("Uso por partición", [prom(f"100 * (1 - node_filesystem_avail_bytes{{{disco}}} "
                                                 f"/ node_filesystem_size_bytes{{{disco}}})", "{{mountpoint}}")],
                      "Los scripts avisan al pasar el 85 %.", "percent", min=0, max=100,
                      thresholds=umbrales(("green", None), ("orange", 75), ("red", 85))), 8, 8)
    t.agregar(serie("Espacio libre", [prom(f"node_filesystem_avail_bytes{{{disco}}}", "{{mountpoint}}")],
                    unidad="bytes"), 8, 8)
    t.agregar(tabla("Días hasta llenarse (al ritmo de las últimas 12 h)", [prom(
        f"node_filesystem_avail_bytes{{{disco}}} / clamp_min(-deriv(node_filesystem_avail_bytes{{{disco}}}[12h]), 0.001) / 86400",
        instant=True)], "Muy grande = no se está llenando.", "d", decimals=0,
        transformaciones=[ocultar(*SIN_TIEMPO, "device", "fstype", renombrar={"mountpoint": "Partición",
                                                                               "Value": "Días"})]), 8, 8)
    t.agregar(serie("Lectura y escritura", [
        prom(f"rate(node_disk_read_bytes_total{{{dispositivo}}}[$__rate_interval])", "{{device}} lee"),
        prom(f"-rate(node_disk_written_bytes_total{{{dispositivo}}}[$__rate_interval])", "{{device}} escribe",
             ref="B")], "Escritura hacia abajo.", "Bps"))
    t.agregar(serie("Disco ocupado", [prom(f"100 * rate(node_disk_io_time_seconds_total{{{dispositivo}}}[$__rate_interval])",
                                           "{{device}}")],
                    "Porcentaje del tiempo que el disco está trabajando. Cerca de 100 % = saturado.", "percent",
                    max=100))
    t.agregar(tabla("RAID (espejo)", [prom("node_md_disks", instant=True)],
                    "Discos de cada RAID por estado. Los scripts avisan al instante si se degrada.",
                    transformaciones=[ocultar(*SIN_TIEMPO, renombrar={"device": "RAID", "state": "Estado",
                                                                      "Value": "Discos"})]), 12, 6)
    t.agregar(serie("Esperas por disco (presión de E/S)", [prom(
        "rate(node_pressure_io_waiting_seconds_total[$__rate_interval]) * 100", "procesos esperando E/S")],
        "Porcentaje del tiempo en que algún proceso esperó al disco.", "percent"), 12, 6)

    t.seccion("Red")
    t.agregar(serie("Tráfico", [
        prom(f"rate(node_network_receive_bytes_total{{{red}}}[$__rate_interval]) * 8", "{{device}} recibe"),
        prom(f"-rate(node_network_transmit_bytes_total{{{red}}}[$__rate_interval]) * 8", "{{device}} envía",
             ref="B")], "Envío hacia abajo.", "bps"))
    t.agregar(serie("Errores y descartes", [
        prom(f"rate(node_network_receive_errs_total{{{red}}}[$__rate_interval]) + "
             f"rate(node_network_transmit_errs_total{{{red}}}[$__rate_interval])", "{{device}} errores"),
        prom(f"rate(node_network_receive_drop_total{{{red}}}[$__rate_interval]) + "
             f"rate(node_network_transmit_drop_total{{{red}}}[$__rate_interval])", "{{device}} descartes",
             ref="B")], "Tiene que estar en cero; si no, revisar cable o placa.", "pps"))

    t.seccion("Temperaturas")
    t.agregar(serie("Sensores", [prom("node_hwmon_temp_celsius", "{{chip}} {{sensor}}")],
                    "k10temp = procesador (Ryzen); nvme/drivetemp = discos (también los vigila smartd).",
                    "celsius"), 24, 8)

    t.seccion("Contenedores")
    t.agregar(serie("CPU por contenedor", [prom(
        'sum by (container_label_com_docker_compose_service) (rate(container_cpu_usage_seconds_total{name!=""}[$__rate_interval])) * 100',
        "{{container_label_com_docker_compose_service}}")], "100 % = un núcleo entero.", "percent"))
    t.agregar(serie("RAM por contenedor", [prom(
        'sum by (container_label_com_docker_compose_service) (container_memory_working_set_bytes{name!=""})',
        "{{container_label_com_docker_compose_service}}")], unidad="bytes", apilado=True))
    t.agregar(tabla("RAM usada contra el límite", [
        prom('sum by (container_label_com_docker_compose_service) (container_memory_working_set_bytes{name!=""})',
             instant=True),
        prom('sum by (container_label_com_docker_compose_service) (container_spec_memory_limit_bytes{name!=""} > 0)',
             instant=True, ref="B")],
        "Límites de compose.monitoreo.yml (Odoo y PostgreSQL no tienen).", "bytes",
        transformaciones=[UNIR, ocultar("Time", renombrar={
            "container_label_com_docker_compose_service": "Servicio", "Value #A": "Usada", "Value #B": "Límite"})]))
    t.agregar(serie("Contenedores sin memoria (OOM)", [prom(
        'sum by (container_label_com_docker_compose_service) (increase(container_oom_events_total{name!=""}[$__rate_interval]))',
        "{{container_label_com_docker_compose_service}}")], "Debería estar siempre en cero.", barras=True))

    t.seccion("Odoo: respuesta y errores")
    t.agregar(serie("Tiempo de respuesta", [prom("probe_duration_seconds", "{{instance}}")],
                    "/web/health = Odoo vivo; /web/login = página con la base (lo que siente un usuario). "
                    "Alerta: más de 3 s durante 5 min.", "s"))
    t.agregar(serie("Odoo responde", [prom("probe_success", "{{instance}}")], "1 = sí, 0 = no.",
                    min=0, max=1, custom={"drawStyle": "line", "lineInterpolation": "stepAfter"}))
    t.agregar(serie("Errores en el registro de Odoo", [prom('odoo_log_lineas{nivel=~"ERROR|CRITICAL"}',
                                                            "{{nivel}}")],
                    "Líneas ERROR y CRITICAL en los últimos 15 min (las cuenta revisar-servidor.sh). "
                    "Detalle: docker logs del contenedor odoo. Vacío en el lab.", barras=True), 24, 7)

    t.seccion("Backups")
    t.agregar(medidor("Último backup bueno, hace", [prom("(time() - odoo_backup_ultimo_ok_timestamp_seconds) / 3600",
                                                         "{{copia}}")],
                      "Por copia (pendrive y R2). Los scripts avisan a las 26 h. Vacío en el lab.", "h",
                      thresholds=umbrales(("green", None), ("orange", 25), ("red", 26))), 8, 6)
    t.agregar(serie("Tamaño del backup", [prom("odoo_backup_bytes", "base y adjuntos"),
                                          prom("odoo_filestore_bytes", "adjuntos (filestore)", ref="B")],
                    "Lo escribe backup-nocturno.sh cada noche.", "bytes"), 8, 6)
    t.agregar(serie("Duración del backup", [prom("odoo_backup_duracion_segundos", "duración")],
                    "Volcado + copias a pendrive y R2.", "s"), 8, 6)
    return t


# ---------------------------------------------------------------- tablero «PostgreSQL»

def tablero_postgresql():
    variables = [{
        "name": "base", "label": "Base", "type": "query", "datasource": PROM,
        "query": {"query": 'label_values(pg_database_size_bytes{datname!~"template.*|postgres"}, datname)',
                  "refId": "base"},
        "refresh": 1, "includeAll": False, "multi": False, "sort": 1,
    }]
    t = Tablero("postgresql", "PostgreSQL", "Conexiones, actividad, caché, tablas, consultas lentas, WAL y "
                "mantenimiento de la base de Odoo (ADR 0028).", variables, desde="now-24h")
    tablas = f"{{{BASE}}}"

    t.seccion("Resumen", abierta=True)
    t.agregar(dato("PostgreSQL", [prom("pg_up")], "1 = responde.",
                   mappings=[{"type": "value", "options": {"0": {"text": "CAÍDO", "color": "red"},
                                                           "1": {"text": "OK", "color": "green"}}}]), 3, 4)
    t.agregar(dato("Tamaño de la base", [prom(f"pg_database_size_bytes{{{BASE}}}")], unidad="bytes"), 3, 4)
    t.agregar(dato("Conexiones", [prom("100 * sum(pg_stat_activity_count) / max(pg_settings_max_connections)")],
                   "% del máximo (max_connections).", "percent",
                   thresholds=umbrales(("green", None), ("orange", 60), ("red", 80))), 3, 4)
    t.agregar(dato("Lecturas desde memoria", [prom(
        f"100 * sum(rate(pg_stat_database_blks_hit{{{BASE}}}[1h])) / "
        f"(sum(rate(pg_stat_database_blks_hit{{{BASE}}}[1h])) + sum(rate(pg_stat_database_blks_read{{{BASE}}}[1h])))")],
        "Cache hit ratio de la última hora. Bien: > 99 %.", "percent", decimals=2,
        thresholds=umbrales(("red", None), ("orange", 95), ("green", 99))), 3, 4)
    t.agregar(dato("Transacciones/s", [prom(
        f"sum(rate(pg_stat_database_xact_commit{{{BASE}}}[5m]) + rate(pg_stat_database_xact_rollback{{{BASE}}}[5m]))")],
        unidad="ops"), 3, 4)
    t.agregar(dato("Deadlocks (24 h)", [prom(f"sum(increase(pg_stat_database_deadlocks{{{BASE}}}[24h]))")],
                   decimals=0, thresholds=umbrales(("green", None), ("red", 1))), 3, 4)
    t.agregar(dato("Transacción más larga", [prom('max(pg_stat_activity_max_tx_duration{state!="idle"})')],
                   "Abierta ahora (cualquier estado salvo idle).", "s",
                   thresholds=umbrales(("green", None), ("orange", 60), ("red", 600))), 3, 4)
    t.agregar(dato("Edad de XID (wraparound)", [prom(
        "100 * max(pg_database_wraparound_age_datfrozenxid_seconds) / 2147483648")],
        "% del límite de transacciones antes del «wraparound». El autovacuum lo mantiene bajo; alerta al 50 %.",
        "percent", decimals=2, thresholds=umbrales(("green", None), ("orange", 30), ("red", 50))), 3, 4)

    t.seccion("Conexiones y esperas")
    t.agregar(serie("Conexiones por estado", [prom(f"sum by (state) (pg_stat_activity_count{{{BASE}}})", "{{state}}")],
                    "active = trabajando; idle = esperando (normal en Odoo); «idle in transaction» = "
                    "abrió una transacción y no la cerró (bloquea el vacuum).", apilado=True))
    t.agregar(serie("Antigüedad de la transacción más vieja, por estado", [prom(
        f'max by (state) (pg_stat_activity_max_tx_duration{{{BASE}, state!="idle"}})', "{{state}}")],
        "Alertas: idle in transaction > 5 min; cualquier transacción > 10 min.", "s"))
    t.agregar(serie("Bloqueos por tipo (locks)", [prom(f"sum by (mode) (pg_locks_count{{{BASE}}})", "{{mode}}")],
                    "Muchos *exclusivelock* sostenidos = procesos esperándose entre sí."))
    t.agregar(serie("Transacciones largas en curso", [
        prom("pg_long_running_transactions", "cantidad"),
        prom("time() - (pg_long_running_transactions_oldest_timestamp_seconds > 0)", "la más vieja (s)", ref="B")],
        "Transacciones abiertas hace más de 5 min. La espera concreta (wait_event) no se muestra: verla "
        "pide permisos que también dejan leer el texto con datos de las consultas en curso."))

    t.seccion("Actividad")
    t.agregar(serie("Commits y rollbacks por segundo", [
        prom(f"sum(rate(pg_stat_database_xact_commit{{{BASE}}}[$__rate_interval]))", "commits"),
        prom(f"sum(rate(pg_stat_database_xact_rollback{{{BASE}}}[$__rate_interval]))", "rollbacks", ref="B")],
        "Odoo hace rollback en errores y conflictos de concurrencia; muchos sostenidos = revisar el log.",
        "ops"))
    t.agregar(serie("Filas por segundo", [
        prom(f"sum(rate(pg_stat_database_tup_fetched{{{BASE}}}[$__rate_interval]))", "leídas"),
        prom(f"sum(rate(pg_stat_database_tup_inserted{{{BASE}}}[$__rate_interval]))", "insertadas", ref="B"),
        prom(f"sum(rate(pg_stat_database_tup_updated{{{BASE}}}[$__rate_interval]))", "actualizadas", ref="C"),
        prom(f"sum(rate(pg_stat_database_tup_deleted{{{BASE}}}[$__rate_interval]))", "borradas", ref="D")],
        unidad="rps"))
    t.agregar(serie("Deadlocks y conflictos", [
        prom(f"sum(increase(pg_stat_database_deadlocks{{{BASE}}}[$__rate_interval]))", "deadlocks"),
        prom(f"sum(increase(pg_stat_database_conflicts{{{BASE}}}[$__rate_interval]))", "conflictos", ref="B")],
        "Alerta: algún deadlock en 10 min. Conflictos: solo con réplicas (no hay).", barras=True))
    t.agregar(serie("Archivos temporales", [
        prom(f"sum(rate(pg_stat_database_temp_bytes{{{BASE}}}[$__rate_interval]))", "bytes/s"),
        prom(f"sum(increase(pg_stat_database_temp_files{{{BASE}}}[$__rate_interval]))", "archivos", ref="B")],
        "Consultas que no entran en work_mem y ordenan en disco. Alerta: más de 1 GB por hora.",
        overrides=[{"matcher": {"id": "byName", "options": "bytes/s"},
                    "properties": [{"id": "unit", "value": "Bps"}]}]))

    t.seccion("Caché y disco")
    t.agregar(serie("Lecturas desde memoria (cache hit)", [prom(
        f"100 * sum(rate(pg_stat_database_blks_hit{{{BASE}}}[$__rate_interval])) / "
        f"(sum(rate(pg_stat_database_blks_hit{{{BASE}}}[$__rate_interval])) + "
        f"sum(rate(pg_stat_database_blks_read{{{BASE}}}[$__rate_interval])))", "cache hit")],
        "Alerta: menos de 95 % sostenido. Si baja, la base ya no entra en shared_buffers + caché del sistema.",
        "percent"))
    t.agregar(serie("Bloques: memoria contra disco", [
        prom(f"sum(rate(pg_stat_database_blks_hit{{{BASE}}}[$__rate_interval]))", "desde memoria"),
        prom(f"sum(rate(pg_stat_database_blks_read{{{BASE}}}[$__rate_interval]))", "desde disco", ref="B")],
        "Bloques de 8 kB por segundo.", "ops"))
    t.agregar(serie("Tiempo leyendo y escribiendo disco", [
        prom(f"sum(rate(pg_stat_database_blk_read_time{{{BASE}}}[$__rate_interval])) / 1000", "lectura"),
        prom(f"sum(rate(pg_stat_database_blk_write_time{{{BASE}}}[$__rate_interval])) / 1000", "escritura",
             ref="B")], "Segundos de E/S por segundo (track_io_timing).", "s"))
    t.agregar(serie("Tablas que más leen del disco", [prom(
        f"topk(8, rate(pg_statio_user_tables_heap_blocks_read{tablas}[$__rate_interval]))", "{{relname}}")],
        "Bloques por segundo que no estaban en memoria.", "ops"))

    t.seccion("Tablas: tamaño, crecimiento y mantenimiento")
    t.agregar(tabla("Tablas más grandes", [
        prom(f"topk(20, pg_stat_user_tables_table_size_bytes{tablas} + pg_stat_user_tables_index_size_bytes{tablas})",
             instant=True),
        prom(f"pg_stat_user_tables_index_size_bytes{tablas} and on (relname) topk(20, "
             f"pg_stat_user_tables_table_size_bytes{tablas} + pg_stat_user_tables_index_size_bytes{tablas})",
             instant=True, ref="B"),
        prom(f"pg_stat_user_tables_n_live_tup{tablas} and on (relname) topk(20, "
             f"pg_stat_user_tables_table_size_bytes{tablas} + pg_stat_user_tables_index_size_bytes{tablas})",
             instant=True, ref="C")],
        "Datos + índices. ir_attachment guarda solo la referencia: los archivos están en el filestore "
        "(ver «Adjuntos y mensajes»).",
        transformaciones=[UNIR, ocultar(*SIN_TIEMPO, renombrar={
            "relname": "Tabla", "Value #A": "Total", "Value #B": "Índices", "Value #C": "Filas"})],
        orden=("Total", True),
        overrides=[{"matcher": {"id": "byRegexp", "options": "Total|Índices"},
                    "properties": [{"id": "unit", "value": "bytes"}]}]), 12, 10)
    t.agregar(tabla("Tablas que más crecieron (en el período elegido)", [prom(
        f"topk(20, delta(pg_stat_user_tables_table_size_bytes{tablas}[$__range]) + "
        f"delta(pg_stat_user_tables_index_size_bytes{tablas}[$__range]))", instant=True)],
        "Cambiar el período arriba a la derecha (7 días, 30 días).", "bytes",
        transformaciones=[ocultar(*SIN_TIEMPO, renombrar={"relname": "Tabla", "Value": "Creció"})],
        orden=("Creció", True)), 12, 10)
    t.agregar(serie("Adjuntos y mensajes", [
        prom(f'sum by (relname) (pg_stat_user_tables_table_size_bytes{{{BASE}, relname=~"ir_attachment|mail_message|mail_tracking_value"}} '
             f'+ pg_stat_user_tables_index_size_bytes{{{BASE}, relname=~"ir_attachment|mail_message|mail_tracking_value"}})',
             "{{relname}} (base)"),
        prom("odoo_filestore_bytes", "filestore (archivos adjuntos)", ref="B")],
        "Los archivos (PDF de facturas, listas, fotos) viven en el filestore, fuera de PostgreSQL; su "
        "tamaño sale del backup de cada noche (vacío en el lab).", "bytes"), 24, 8)
    t.agregar(tabla("Filas muertas y último vacuum", [
        prom(f"topk(20, pg_stat_user_tables_n_dead_tup{tablas})", instant=True),
        prom(f"100 * pg_stat_user_tables_n_dead_tup{tablas} / clamp_min(pg_stat_user_tables_n_live_tup{tablas} + "
             f"pg_stat_user_tables_n_dead_tup{tablas}, 1) and on (relname) topk(20, pg_stat_user_tables_n_dead_tup{tablas})",
             instant=True, ref="B"),
        prom(f"(time() - (pg_stat_user_tables_last_autovacuum{tablas} > 0)) / 86400 and on (relname) "
             f"topk(20, pg_stat_user_tables_n_dead_tup{tablas})", instant=True, ref="C"),
        prom(f"(time() - (pg_stat_user_tables_last_autoanalyze{tablas} > 0)) / 86400 and on (relname) "
             f"topk(20, pg_stat_user_tables_n_dead_tup{tablas})", instant=True, ref="D")],
        "Filas muertas (borradas o actualizadas que el vacuum todavía no limpió): es la estimación de "
        "«bloat» liviana. Vacío en «días» = nunca corrió el autovacuum en esa tabla. Alerta: tabla > 50 MB "
        "con > 10 000 filas muertas y sin autovacuum hace > 7 días.",
        transformaciones=[UNIR, ocultar(*SIN_TIEMPO, renombrar={
            "relname": "Tabla", "Value #A": "Filas muertas", "Value #B": "% muertas",
            "Value #C": "Días desde autovacuum", "Value #D": "Días desde autoanalyze"})],
        orden=("Filas muertas", True), decimals=1), 12, 10)
    t.agregar(tabla("Lecturas completas en tablas grandes (candidatas a índice)", [
        prom(f"topk(15, rate(pg_stat_user_tables_seq_tup_read{tablas}[1h]) and on (relname) "
             f"(pg_stat_user_tables_table_size_bytes{tablas} > 10e6))", instant=True),
        prom(f"rate(pg_stat_user_tables_seq_scan{tablas}[1h]) * 3600 and on (relname) topk(15, "
             f"rate(pg_stat_user_tables_seq_tup_read{tablas}[1h]) and on (relname) "
             f"(pg_stat_user_tables_table_size_bytes{tablas} > 10e6))", instant=True, ref="B"),
        prom(f"rate(pg_stat_user_tables_idx_scan{tablas}[1h]) * 3600 and on (relname) topk(15, "
             f"rate(pg_stat_user_tables_seq_tup_read{tablas}[1h]) and on (relname) "
             f"(pg_stat_user_tables_table_size_bytes{tablas} > 10e6))", instant=True, ref="C")],
        "Tablas de más de 10 MB que se recorren enteras (seq scan) en la última hora. Muchas filas "
        "leídas así y pocas búsquedas por índice = puede faltar un índice (decidirlo mirando las "
        "consultas lentas de abajo).",
        transformaciones=[UNIR, ocultar(*SIN_TIEMPO, renombrar={
            "relname": "Tabla", "Value #A": "Filas leídas enteras/s", "Value #B": "Lecturas completas/h",
            "Value #C": "Búsquedas por índice/h"})],
        orden=("Filas leídas enteras/s", True), decimals=0), 12, 10)
    t.agregar(tabla("Índices sin uso (los más grandes)", [sql(
        """SELECT s.relname AS "Tabla", s.indexrelname AS "Índice", pg_relation_size(s.indexrelid) AS "Tamaño"
           FROM pg_stat_user_indexes s JOIN pg_index i ON i.indexrelid = s.indexrelid
           WHERE s.idx_scan = 0 AND NOT i.indisunique AND NOT i.indisprimary
           ORDER BY pg_relation_size(s.indexrelid) DESC LIMIT 20""", "table")],
        "Índices que no se usaron desde que se reiniciaron las estadísticas (o desde que se creó la base). "
        "Ocupan disco y hacen más lentas las escrituras. Muchos son de Odoo: no borrar ninguno sin "
        "revisarlo; mirarlo después de meses de uso real.",
        overrides=[{"matcher": {"id": "byName", "options": "Tamaño"},
                    "properties": [{"id": "unit", "value": "bytes"}]}]), 24, 8)

    t.seccion("Consultas lentas (pg_stat_statements)")
    total = (f"sum by (queryid) (increase(pg_stat_statements_seconds_total{{{BASE}}}[$__range]))")
    llamadas = (f"sum by (queryid) (increase(pg_stat_statements_calls_total{{{BASE}}}[$__range]))")
    texto = "max by (queryid, query) (pg_stat_statements_query_id)"
    explicacion = ("Texto normalizado por PostgreSQL (los valores pasan a $1, $2…: no muestra datos de "
                   "clientes) y cortado a 160 letras. Período: el de arriba a la derecha. Solo las 40 "
                   "consultas que más tiempo llevan (las del monitoreo no cuentan).")
    t.agregar(tabla("Por tiempo total", [
        prom(f"topk(15, {total})", instant=True),
        prom(f"{llamadas} and on (queryid) topk(15, {total})", instant=True, ref="B"),
        prom(f"({total} / clamp_min({llamadas}, 1)) and on (queryid) topk(15, {total})", instant=True, ref="C"),
        prom(f"{texto} and on (queryid) topk(15, {total})", instant=True, ref="D")],
        explicacion, transformaciones=[UNIR, ocultar("Time", "Value #D", renombrar={
            "queryid": "Id", "query": "Consulta", "Value #A": "Tiempo total", "Value #B": "Llamadas",
            "Value #C": "Tiempo medio"})], orden=("Tiempo total", True),
        overrides=[{"matcher": {"id": "byRegexp", "options": "Tiempo.*"},
                    "properties": [{"id": "unit", "value": "s"}]},
                   {"matcher": {"id": "byName", "options": "Consulta"},
                    "properties": [{"id": "custom.width", "value": 700}]}]), 24, 10)
    t.agregar(tabla("Por tiempo medio (más lentas de a una)", [
        prom(f"topk(15, {total} / ({llamadas} > 0))", instant=True),
        prom(f"{llamadas} and on (queryid) topk(15, {total} / ({llamadas} > 0))", instant=True, ref="B"),
        prom(f"{texto} and on (queryid) topk(15, {total} / ({llamadas} > 0))", instant=True, ref="C")],
        explicacion, transformaciones=[UNIR, ocultar("Time", "Value #C", renombrar={
            "queryid": "Id", "query": "Consulta", "Value #A": "Tiempo medio", "Value #B": "Llamadas"})],
        orden=("Tiempo medio", True),
        overrides=[{"matcher": {"id": "byName", "options": "Tiempo medio"},
                    "properties": [{"id": "unit", "value": "s"}]},
                   {"matcher": {"id": "byName", "options": "Consulta"},
                    "properties": [{"id": "custom.width", "value": 700}]}]), 24, 10)
    t.agregar(serie("Llamadas por segundo (las 8 más llamadas)", [prom(
        f"topk(8, sum by (queryid) (rate(pg_stat_statements_calls_total{{{BASE}}}[$__rate_interval])))",
        "{{queryid}}")], "El texto de cada Id está en las tablas de arriba.", "ops"), 24, 8)

    t.seccion("WAL, checkpoints y wraparound")
    t.agregar(serie("WAL generado por hora", [prom("increase(odoo_pg_wal_bytes_total[1h])", "por hora")],
                    "Cuánto escribe la base (registro de cambios). Sirve para dimensionar backups y "
                    "disco. Lo anota revisar-servidor.sh cada 15 min (vacío en el lab).", "bytes"))
    t.agregar(serie("Checkpoints", [
        prom("increase(pg_stat_bgwriter_checkpoints_timed_total[$__rate_interval])", "por tiempo"),
        prom("increase(pg_stat_bgwriter_checkpoints_req_total[$__rate_interval])", "pedidos (WAL lleno)", ref="B")],
        "Muchos «pedidos» = max_wal_size chico para la carga.", barras=True))
    t.agregar(serie("Carpeta pg_wal", [prom("pg_wal_size_bytes", "tamaño")], unidad="bytes"))
    t.agregar(serie("Edad de XID por base (wraparound)", [prom(
        "100 * pg_database_wraparound_age_datfrozenxid_seconds / 2147483648", "{{datname}}")],
        "% del límite. El autovacuum lo baja solo; alerta al 50 %.", "percent"))

    t.seccion("Backups")
    t.agregar(medidor("Último backup bueno, hace", [prom("(time() - odoo_backup_ultimo_ok_timestamp_seconds) / 3600",
                                                         "{{copia}}")],
                      "La alerta la dan los scripts (26 h). Vacío en el lab.", "h",
                      thresholds=umbrales(("green", None), ("orange", 25), ("red", 26))), 12, 6)
    t.agregar(serie("Tamaño de la base y del backup", [
        prom(f"pg_database_size_bytes{{{BASE}}}", "base (PostgreSQL)"),
        prom("odoo_backup_bytes", "backup (volcado + adjuntos)", ref="B")], unidad="bytes"), 12, 6)
    return t


# ---------------------------------------------------------------- tablero «Negocio (Odoo)»

# Pedido «armado»: el puesto lo imprimió (va a caja) o ya está cobrado. El punto de venta de
# origen sale de la referencia del ticket (AAA-<pos.config>-NNNNNN): la caja que lo cobra
# cambia config_id, pero la referencia queda con el puesto que lo armó.
ORIGEN = "COALESCE(substring(o.pos_reference from '^[0-9]+-([0-9]+)-')::int, o.config_id)"
ARMADO = "(o.comercio_en_caja OR o.state IN ('paid', 'done', 'invoiced'))"
PEDIDOS = f"pos_order o JOIN pos_config c ON c.id = {ORIGEN} WHERE {ARMADO}"
COBRADOS = "o.state IN ('paid', 'done', 'invoiced')"
NOMBRE_PRODUCTO = (f"COALESCE(pp.default_code || ' · ', '') || {nombre('pt.name')}")
STOCK_INTERNO = """SELECT q.product_id, sum(q.quantity) AS cantidad FROM stock_quant q
    JOIN stock_location l ON l.id = q.location_id WHERE l.usage = 'internal' GROUP BY q.product_id"""


def tablero_negocio():
    variables = [{
        "name": "dias", "label": "Sin movimiento hace (días)", "type": "custom",
        "query": "30,60,90,180", "current": {"text": "60", "value": "60"},
        # Solo estos valores: la variable va dentro del SQL (sin texto libre)
        "allowCustomValue": False,
        "options": [{"text": v, "value": v, "selected": v == "60"} for v in ("30", "60", "90", "180")],
    }]
    t = Tablero("negocio", "Negocio (Odoo)", "Pedidos, productos, stock, compras, listas de proveedores, "
                "precios y actividad, leídos de la base de Odoo con un usuario de solo lectura (ADR 0028). "
                "Sin datos personales de clientes.", variables, desde="now-30d")

    t.seccion("Hoy", abierta=True)
    hoy_pedido = f"{local('o.date_order')} >= {HOY}"
    t.agregar(dato("Pedidos hoy", [sql(f"SELECT count(*) FROM {PEDIDOS} AND {hoy_pedido}", "table")],
                   "Impresos en los puestos (o cobrados) desde las 0 h.", decimals=0), 4, 4)
    t.agregar(dato("Importe de los pedidos hoy", [sql(
        f"SELECT COALESCE(sum(o.amount_total), 0) FROM {PEDIDOS} AND {hoy_pedido}", "table")],
        "Con IVA.", decimals=0), 4, 4)
    t.agregar(dato("Compras confirmadas hoy", [sql(
        f"SELECT count(*) FROM purchase_order po WHERE po.state IN ('purchase', 'done') "
        f"AND {local('po.date_approve')} >= {HOY}", "table")], decimals=0), 4, 4)
    t.agregar(dato("Facturas de proveedor en excepción", [sql(
        "SELECT count(*) FROM account_move m WHERE m.move_type IN ('in_invoice', 'in_refund') "
        "AND m.state != 'cancel' AND m.release_to_pay = 'exception'", "table")],
        "«Se debe pagar: Excepción» (no coincide con la orden, lo recibido o el total del papel).",
        decimals=0, thresholds=umbrales(("green", None), ("orange", 1), ("red", 5))), 4, 4)
    t.agregar(dato("Precios para cambiar", [sql(
        """SELECT count(*) FROM product_template pt, res_company rc
           WHERE rc.id = (SELECT min(id) FROM res_company) AND pt.active AND pt.comercio_precio_desactualizado
             AND NOT (COALESCE(rc.comercio_diferencia_chica, 0) > 0
                      AND abs(COALESCE(pt.comercio_precio_variacion, 0)) <= rc.comercio_diferencia_chica)""",
        "table")], "En «Precios a actualizar», sin contar las diferencias chicas.", decimals=0,
        thresholds=umbrales(("green", None), ("orange", 1))), 4, 4)
    t.agregar(dato("Códigos de fábrica por escanear", [sql(
        """SELECT count(*) FROM product_product pp JOIN product_template pt ON pt.id = pp.product_tmpl_id
           WHERE pp.active AND pt.active AND pt.type = 'consu' AND pp.barcode LIKE '20%'
             AND NOT COALESCE(pt.comercio_sin_codigo_fabrica, false)""", "table")],
        "Productos con el código propio 20… y sin marcar «No tiene código de fábrica» (ADR 0025).",
        decimals=0), 4, 4)

    t.seccion("Pedidos por puesto")
    pv = nombre("c.name")
    t.agregar(serie("Pedidos por día y puesto", [sql(
        f"""SELECT {dia('o.date_order')} AS time, {pv} AS metric, count(*) AS value
            FROM {PEDIDOS} AND $__timeFilter(o.date_order) GROUP BY 1, 2 ORDER BY 1""")],
        "Pedidos impresos en cada puesto (los cobrados en una caja cuentan para el puesto que los armó).",
        apilado=True, barras=True, decimals=0, custom={"barAlignment": 0}))
    t.agregar(serie("Importe por día y puesto", [sql(
        f"""SELECT {dia('o.date_order')} AS time, {pv} AS metric, sum(o.amount_total) AS value
            FROM {PEDIDOS} AND $__timeFilter(o.date_order) GROUP BY 1, 2 ORDER BY 1""")],
        "Total de los pedidos con IVA.", apilado=True, barras=True, decimals=0))
    t.agregar(barras_categoria("Pedidos por hora del día (horas pico)", [sql(
        f"""SELECT lpad(extract(hour FROM {local('o.date_order')})::text, 2, '0') || ' h' AS hora,
                   {pv} AS puesto, count(*) AS pedidos
            FROM {PEDIDOS} AND $__timeFilter(o.date_order) GROUP BY 1, 2 ORDER BY 1""", "table")],
        "Suma de todo el período elegido.", transformations=[{
            "id": "groupingToMatrix", "options": {"columnField": "puesto", "rowField": "hora",
                                                  "valueField": "pedidos", "emptyValue": "zero"}}]))
    t.agregar(barras_categoria("Pedidos por día de la semana", [sql(
        f"""SELECT extract(isodow FROM {local('o.date_order')})::int || ' ' ||
                   (ARRAY['lun','mar','mié','jue','vie','sáb','dom'])[extract(isodow FROM {local('o.date_order')})::int]
                   AS dia, {pv} AS puesto, count(*) AS pedidos
            FROM {PEDIDOS} AND $__timeFilter(o.date_order) GROUP BY 1, 2 ORDER BY 1""", "table")],
        "Suma de todo el período elegido.", transformations=[{
            "id": "groupingToMatrix", "options": {"columnField": "puesto", "rowField": "dia",
                                                  "valueField": "pedidos", "emptyValue": "zero"}}]))
    t.agregar(tabla("Resumen por puesto (período elegido)", [sql(
        f"""SELECT {pv} AS "Puesto", count(*) AS "Pedidos", COALESCE(sum(it.items), 0) AS "Ítems",
                   sum(o.amount_total) AS "Importe", round(avg(o.amount_total), 2) AS "Promedio por pedido",
                   count(*) FILTER (WHERE o.state = 'cancel') AS "Anulados"
            FROM pos_order o JOIN pos_config c ON c.id = {ORIGEN}
            LEFT JOIN LATERAL (SELECT sum(l.qty) AS items FROM pos_order_line l WHERE l.order_id = o.id) it ON true
            WHERE {ARMADO} AND $__timeFilter(o.date_order)
            GROUP BY 1 ORDER BY 2 DESC""", "table")],
        "Anulados: impresos que nadie cobró (regla de la última caja).", decimals=0), 24, 7)

    t.seccion("Productos")
    t.agregar(tabla("Más vendidos (período elegido)", [sql(
        f"""SELECT {NOMBRE_PRODUCTO} AS "Producto", sum(l.qty) AS "Cantidad",
                   sum(l.price_subtotal_incl) AS "Importe", count(DISTINCT o.id) AS "Pedidos"
            FROM pos_order_line l JOIN pos_order o ON o.id = l.order_id
            JOIN product_product pp ON pp.id = l.product_id JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE {COBRADOS} AND $__timeFilter(o.date_order)
            GROUP BY 1 ORDER BY 2 DESC LIMIT 30""", "table")],
        "Cobrados (o dados por cobrados en la registradora).", decimals=0), 12, 10)
    t.agregar(tabla("Sin movimiento hace $dias días (con stock)", [sql(
        f"""SELECT {NOMBRE_PRODUCTO} AS "Producto", s.cantidad AS "Stock",
                   (SELECT max({local('m.date')}) FROM stock_move m WHERE m.product_id = pp.id AND m.state = 'done')
                     AS "Último movimiento"
            FROM ({STOCK_INTERNO}) s JOIN product_product pp ON pp.id = s.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE s.cantidad > 0 AND pp.active AND NOT EXISTS (
                SELECT 1 FROM stock_move m WHERE m.product_id = pp.id AND m.state = 'done'
                  AND m.date >= now() AT TIME ZONE 'UTC' - make_interval(days => ${{dias:sqlstring}}::int))
            ORDER BY 3 NULLS FIRST LIMIT 50""", "table")],
        "Productos con stock que no entraron ni salieron en ese plazo (elegir los días arriba).",
        decimals=0), 12, 10)

    t.seccion("Stock")
    t.agregar(tabla("Stock negativo", [sql(
        f"""SELECT {NOMBRE_PRODUCTO} AS "Producto", s.cantidad AS "Stock"
            FROM ({STOCK_INTERNO}) s JOIN product_product pp ON pp.id = s.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE s.cantidad < 0 ORDER BY 2 LIMIT 50""", "table")],
        "Se vendió más de lo que figuraba: falta cargar una compra o un ajuste de inventario.",
        decimals=2), 12, 9)
    t.agregar(tabla("Por debajo del mínimo (reglas de reabastecimiento)", [sql(
        f"""SELECT {NOMBRE_PRODUCTO} AS "Producto", op.product_min_qty AS "Mínimo",
                   COALESCE((SELECT sum(q.quantity) FROM stock_quant q JOIN stock_location l ON l.id = q.location_id
                             WHERE q.product_id = op.product_id AND l.usage = 'internal'
                               AND l.parent_path LIKE ol.parent_path || '%'), 0) AS "Stock"
            FROM stock_warehouse_orderpoint op JOIN stock_location ol ON ol.id = op.location_id
            JOIN product_product pp ON pp.id = op.product_id JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE op.active AND COALESCE((SELECT sum(q.quantity) FROM stock_quant q
                  JOIN stock_location l ON l.id = q.location_id WHERE q.product_id = op.product_id
                  AND l.usage = 'internal' AND l.parent_path LIKE ol.parent_path || '%'), 0) < op.product_min_qty
            ORDER BY 1 LIMIT 50""", "table")],
        "Solo productos con regla de mínimo cargada (Inventario → Reabastecimiento). Vacío si no hay reglas.",
        decimals=2), 12, 9)
    t.agregar(serie("Movimientos de stock por día", [sql(
        f"""SELECT {dia('m.date')} AS time,
                   CASE WHEN o.usage = 'supplier' THEN 'Entradas de proveedores'
                        WHEN d.usage = 'customer' THEN 'Ventas y salidas a clientes'
                        WHEN o.usage = 'customer' THEN 'Devoluciones de clientes'
                        WHEN d.usage = 'supplier' THEN 'Devoluciones a proveedores'
                        WHEN 'inventory' IN (o.usage, d.usage) THEN 'Ajustes de inventario'
                        ELSE 'Otros' END AS metric, count(*) AS value
            FROM stock_move m JOIN stock_location o ON o.id = m.location_id
            JOIN stock_location d ON d.id = m.location_dest_id
            WHERE m.state = 'done' AND $__timeFilter(m.date) GROUP BY 1, 2 ORDER BY 1""")],
        "Líneas de movimiento hechas (un pedido con 5 productos = 5).", apilado=True, barras=True,
        decimals=0), 24, 8)

    t.seccion("Compras")
    t.agregar(serie("Órdenes de compra confirmadas por día", [sql(
        f"""SELECT {dia('po.date_approve')} AS time, 'órdenes' AS metric, count(*) AS value
            FROM purchase_order po WHERE po.state IN ('purchase', 'done') AND $__timeFilter(po.date_approve)
            GROUP BY 1, 2 ORDER BY 1"""), sql(
        f"""SELECT {dia('po.date_approve')} AS time, 'importe' AS metric, sum(po.amount_total) AS value
            FROM purchase_order po WHERE po.state IN ('purchase', 'done') AND $__timeFilter(po.date_approve)
            GROUP BY 1, 2 ORDER BY 1""", ref="B")],
        barras=True, decimals=0,
        overrides=[{"matcher": {"id": "byName", "options": "importe"},
                    "properties": [{"id": "custom.axisPlacement", "value": "right"},
                                   {"id": "custom.drawStyle", "value": "line"}]}]))
    t.agregar(serie("Facturas de proveedor cargadas por día", [sql(
        f"""SELECT {dia('m.create_date')} AS time,
                   CASE WHEN j.comercio_sin_factura THEN 'Compras sin factura'
                        WHEN m.release_to_pay = 'exception' THEN 'En excepción'
                        ELSE 'Facturas' END AS metric, count(*) AS value
            FROM account_move m JOIN account_journal j ON j.id = m.journal_id
            WHERE m.move_type IN ('in_invoice', 'in_refund') AND m.state != 'cancel'
              AND $__timeFilter(m.create_date) GROUP BY 1, 2 ORDER BY 1""")],
        apilado=True, barras=True, decimals=0))
    t.agregar(tabla("Recepciones pendientes", [sql(
        f"""SELECT p.name AS "Recepción", p.origin AS "Origen", pr.name AS "Proveedor",
                   {local('p.scheduled_date')} AS "Prevista",
                   GREATEST(0, extract(day FROM now() AT TIME ZONE 'UTC' - p.scheduled_date))::int AS "Días de atraso"
            FROM stock_picking p JOIN stock_picking_type pt ON pt.id = p.picking_type_id
            LEFT JOIN res_partner pr ON pr.id = p.partner_id
            WHERE pt.code = 'incoming' AND p.state NOT IN ('done', 'cancel', 'draft')
            ORDER BY p.scheduled_date LIMIT 50""", "table")],
        "Mercadería pedida que todavía no se recibió en Odoo."), 12, 9)
    t.agregar(tabla("Facturas en excepción o con el total que no cierra", [sql(
        """SELECT m.name AS "Factura", m.ref AS "Número del proveedor", pr.name AS "Proveedor",
                   m.invoice_date AS "Fecha", m.amount_total AS "Total en Odoo",
                   m.comercio_total_factura AS "Total del papel",
                   CASE WHEN m.comercio_total_factura IS NOT NULL
                          AND abs(m.comercio_total_factura - m.amount_total) > 0.01 THEN 'No cierra el total'
                        ELSE 'Excepción' END AS "Problema"
            FROM account_move m LEFT JOIN res_partner pr ON pr.id = m.partner_id
            WHERE m.move_type IN ('in_invoice', 'in_refund') AND m.state != 'cancel'
              AND (m.release_to_pay = 'exception' OR (m.comercio_total_factura IS NOT NULL
                   AND abs(m.comercio_total_factura - m.amount_total) > 0.01))
            ORDER BY m.invoice_date DESC NULLS LAST LIMIT 50""", "table")],
        "Excepción: no coincide con la orden o con lo recibido (account_3way_match). «No cierra»: el total "
        "leído del papel distinto del de Odoo (en un borrador, el de Odoo se actualiza al guardar).",
        decimals=2), 12, 9)
    t.agregar(tabla("Compras sin factura abiertas (ADR 0023)", [sql(
        f"""SELECT m.name AS "Comprobante", pr.name AS "Proveedor", m.date AS "Fecha",
                   m.amount_total AS "Total", m.payment_state AS "Pago",
                   ({HOY}::date - m.date) AS "Días"
            FROM account_move m JOIN account_journal j ON j.id = m.journal_id
            LEFT JOIN res_partner pr ON pr.id = m.partner_id
            WHERE j.comercio_sin_factura AND m.state = 'posted'
            ORDER BY m.date LIMIT 50""", "table")],
        "Registradas en el diario sin factura, a la espera de la factura real (la administración las anula "
        "a mano al cargarla).", decimals=2), 24, 8)

    t.seccion("Listas de proveedores")
    t.agregar(tabla("Última importación por lista", [sql(
        """SELECT pr.name AS "Proveedor", concat_ws(' · ', l.name, l.parte) AS "Lista",
                  l.frecuencia_dias AS "Cada (días)",
                  (SELECT max(i.fecha) FROM comercio_lista_importacion i
                   WHERE i.lista_id = l.id AND i.estado = 'aplicada') AS "Última aplicada",
                  (now() AT TIME ZONE 'UTC')::date - (SELECT max(i.fecha) FROM comercio_lista_importacion i
                   WHERE i.lista_id = l.id AND i.estado = 'aplicada')::date AS "Días",
                  v.estado AS "Estado de la última", CASE WHEN v.estado = 'simulada' THEN v.cant_revisar END
                    AS "Filas para revisar"
           FROM comercio_lista_proveedor l JOIN res_partner pr ON pr.id = l.partner_id
           LEFT JOIN LATERAL (SELECT i.estado, i.cant_revisar FROM comercio_lista_importacion i
                              WHERE i.lista_id = l.id AND i.estado NOT IN ('error', 'descartada')
                              ORDER BY i.id DESC LIMIT 1) v ON true
           WHERE l.active ORDER BY 5 DESC NULLS FIRST""", "table")],
        "«Días» vacío = nunca se aplicó. Alerta: más de 14 días sin importar. Filas para revisar: de la "
        "importación más nueva, si todavía está para revisar.", decimals=0), 24, 10)
    t.agregar(serie("Importaciones por día", [sql(
        f"""SELECT {dia('i.create_date')} AS time, i.estado AS metric, count(*) AS value
            FROM comercio_lista_importacion i WHERE $__timeFilter(i.create_date)
            GROUP BY 1, 2 ORDER BY 1""")],
        "Por estado actual (aplicada, simulada = para revisar, reemplazada, descartada, error).",
        apilado=True, barras=True, decimals=0), 24, 7)

    t.seccion("Costos y precios")
    cambios = f"""FROM product_supplierinfo s
        JOIN LATERAL (SELECT a.price FROM product_supplierinfo a
                      WHERE a.partner_id = s.partner_id AND a.product_tmpl_id = s.product_tmpl_id
                        AND a.comercio_escala_de_id IS NULL AND a.id < s.id AND a.date_end IS NOT NULL
                      ORDER BY a.id DESC LIMIT 1) ant ON true
        WHERE s.comercio_escala_de_id IS NULL AND s.date_start >= ({HOY})::date - 7 AND s.price != ant.price"""
    t.agregar(dato("Cambios de costo de proveedores (7 días)", [sql(f"SELECT count(*) {cambios}", "table")],
                   "Precios de proveedor que cambiaron (cada lista aplicada o carga a mano).", decimals=0), 6, 4)
    t.agregar(dato("Precios para cambiar", [sql(
        """SELECT count(*) FILTER (WHERE NOT (COALESCE(rc.comercio_diferencia_chica, 0) > 0
                      AND abs(COALESCE(pt.comercio_precio_variacion, 0)) <= rc.comercio_diferencia_chica))
           FROM product_template pt, res_company rc
           WHERE rc.id = (SELECT min(id) FROM res_company) AND pt.active AND pt.comercio_precio_desactualizado""",
        "table")], "«Precios a actualizar» en rojo o verde.", decimals=0), 6, 4)
    t.agregar(dato("Diferencias chicas (ocultas)", [sql(
        """SELECT count(*) FILTER (WHERE COALESCE(rc.comercio_diferencia_chica, 0) > 0
                      AND abs(COALESCE(pt.comercio_precio_variacion, 0)) <= rc.comercio_diferencia_chica)
           FROM product_template pt, res_company rc
           WHERE rc.id = (SELECT min(id) FROM res_company) AND pt.active AND pt.comercio_precio_desactualizado""",
        "table")], "Por debajo del porcentaje de «Diferencia chica»: no vale la pena cambiarlos.",
        decimals=0), 6, 4)
    t.agregar(dato("Etiquetas para reimprimir", [sql(
        "SELECT count(*) FROM product_template pt WHERE pt.active AND pt.comercio_etiqueta_pendiente", "table")],
        decimals=0), 6, 4)
    t.agregar(tabla("Cambios de costo de la semana", [sql(
        f"""SELECT s.date_start AS "Desde", pr.name AS "Proveedor",
                   COALESCE(s.product_code || ' · ', '') || {nombre('pt.name')} AS "Producto",
                   ant.price AS "Antes", s.price AS "Ahora",
                   round(100 * (s.price - ant.price) / NULLIF(ant.price, 0), 1) AS "Cambio %"
            {cambios.replace("FROM product_supplierinfo s", "FROM product_supplierinfo s "
                             "JOIN res_partner pr ON pr.id = s.partner_id "
                             "JOIN product_template pt ON pt.id = s.product_tmpl_id")}
            ORDER BY abs(s.price - ant.price) / NULLIF(ant.price, 0) DESC NULLS LAST LIMIT 100""", "table")],
        "Precio del proveedor (por su unidad de compra) contra el anterior del mismo proveedor. "
        "Ordenados por el cambio más grande.", decimals=2), 24, 10)

    t.seccion("Actividad por usuario")
    usuario = "COALESCE(up.name, u.login)"
    t.agregar(tabla("Qué hizo cada usuario (período elegido)", [sql(
        f"""SELECT {usuario} AS "Usuario", x.que AS "Qué", count(*) AS "Cantidad"
            FROM (
              SELECT po.create_uid AS uid, 'Órdenes de compra confirmadas' AS que FROM purchase_order po
               WHERE po.state IN ('purchase', 'done') AND $__timeFilter(po.date_approve)
              UNION ALL
              SELECT m.create_uid, CASE WHEN j.comercio_sin_factura THEN 'Compras sin factura cargadas'
                                        ELSE 'Facturas de proveedor cargadas' END
                FROM account_move m JOIN account_journal j ON j.id = m.journal_id
               WHERE m.move_type IN ('in_invoice', 'in_refund') AND $__timeFilter(m.create_date)
              UNION ALL
              SELECT p.write_uid, 'Recepciones validadas' FROM stock_picking p
                JOIN stock_picking_type pt ON pt.id = p.picking_type_id
               WHERE pt.code = 'incoming' AND p.state = 'done' AND $__timeFilter(p.date_done)
              UNION ALL
              SELECT i.create_uid, 'Listas de proveedores importadas' FROM comercio_lista_importacion i
               WHERE $__timeFilter(i.create_date)
              UNION ALL
              SELECT a.create_uid, 'Ajustes de inventario' FROM stock_move a
                JOIN stock_location o ON o.id = a.location_id JOIN stock_location d ON d.id = a.location_dest_id
               WHERE a.state = 'done' AND 'inventory' IN (o.usage, d.usage) AND $__timeFilter(a.date)
            ) x JOIN res_users u ON u.id = x.uid LEFT JOIN res_partner up ON up.id = u.partner_id
            GROUP BY 1, 2 ORDER BY 1, 3 DESC""", "table")],
        "Usuarios de Odoo (administración, compras, depósito). Los cajeros y puestos son empleados: "
        "van en la tabla de al lado.", decimals=0), 12, 10)
    t.agregar(tabla("Pedidos por empleado del puesto (período elegido)", [sql(
        f"""SELECT COALESCE(o.cashier, '(sin empleado)') AS "Empleado", {pv} AS "Puesto",
                   count(*) AS "Pedidos", sum(o.amount_total) AS "Importe"
            FROM {PEDIDOS} AND $__timeFilter(o.date_order) GROUP BY 1, 2 ORDER BY 3 DESC""", "table")],
        "Empleado con PIN que armó el pedido (pos_hr).", decimals=0), 12, 10)
    return t


def main():
    DESTINO.mkdir(exist_ok=True)
    for t in (tablero_servidor(), tablero_postgresql(), tablero_negocio()):
        archivo = DESTINO / f"{t.uid}.json"
        archivo.write_text(json.dumps(t.json(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("Escrito", archivo)


if __name__ == "__main__":
    main()
