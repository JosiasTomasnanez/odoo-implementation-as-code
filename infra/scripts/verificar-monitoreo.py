#!/usr/bin/env python3
"""Verifica el monitoreo (ADR 0028) por la API de Grafana y de Prometheus.

    make verify-monitoreo                       lab
    sudo make verify-monitoreo STACK=onprem     servidor
    python3 infra/scripts/verificar-monitoreo.py --probar-avisos   (solo lab: manda avisos de prueba)

Revisa:
- Grafana responde y sus fuentes de datos (Prometheus y la base de Odoo) andan;
- están los tableros, todas las reglas de alerta (sin errores) y el contacto «avisos»;
- Prometheus lee todos sus destinos;
- cada consulta de los tableros y de las alertas corre sin error: las SQL contra la base con el
  usuario de solo lectura (si Odoo cambia una tabla o columna, o falta un permiso en
  monitoreo/usuarios.sql, aparece acá) y las PromQL contra Prometheus.

Con --probar-avisos (lab): manda un aviso de prueba por el contacto, baja el umbral de una
regla para que salte de verdad, la vuelve a su lugar para que «se arregle», y muestra lo que
llegó al receptor de prueba (lo que vería Discord) y al Mailpit del lab.
Solo biblioteca estándar.
"""

import argparse
import base64
import copy
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MONITOREO = REPO / "infra/docker/monitoreo"
TABLEROS = ("servidor", "postgresql", "negocio")
RECEPTORES = "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/default/receivers"
FALLAS = []


def ok(texto):
    print(f"  ✓ {texto}")


def mal(texto):
    print(f"  ✗ {texto}")
    FALLAS.append(texto)


def leer_env(ruta):
    datos = {}
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            clave, valor = linea.split("=", 1)
            datos[clave.strip()] = valor.strip()
    return datos


class Api:
    def __init__(self, base, usuario=None, clave=None):
        self.base = base.rstrip("/")
        self.auth = None
        if usuario:
            self.auth = "Basic " + base64.b64encode(f"{usuario}:{clave}".encode()).decode()

    def pedir(self, metodo, ruta, datos=None, encabezados=None):
        pedido = urllib.request.Request(self.base + ruta, method=metodo,
                                        data=json.dumps(datos).encode() if datos is not None else None)
        pedido.add_header("Content-Type", "application/json")
        if self.auth:
            pedido.add_header("Authorization", self.auth)
        for clave, valor in (encabezados or {}).items():
            pedido.add_header(clave, valor)
        try:
            with urllib.request.urlopen(pedido, timeout=60) as respuesta:
                cuerpo = respuesta.read()
                return respuesta.status, json.loads(cuerpo) if cuerpo else None
        except urllib.error.HTTPError as error:
            cuerpo = error.read()
            try:
                return error.code, json.loads(cuerpo)
            except ValueError:
                return error.code, cuerpo.decode("utf-8", "replace")
        except OSError as error:  # todavía arrancando, conexión cortada
            return 0, str(error)

    def get(self, ruta):
        return self.pedir("GET", ruta)


def paneles(tablero):
    for panel in tablero.get("panels", []):
        yield panel
        yield from panel.get("panels", [])


def promql_para_probar(expr, base):
    """Las variables de Grafana a valores fijos, para mandar la consulta directo a Prometheus."""
    return (expr.replace("$__rate_interval", "2m").replace("$__range", "1h").replace("$__interval", "1m")
            .replace("$base", base))


def verificar(grafana, prom, base):
    print("Grafana")
    limite = time.time() + 120  # recién levantado tarda en contestar
    estado, salud = grafana.get("/api/health")
    while estado != 200 and time.time() < limite:
        time.sleep(3)
        estado, salud = grafana.get("/api/health")
    if estado == 200:
        ok(f"responde (versión {salud.get('version')})")
    else:
        mal(f"Grafana no responde: {estado}")
        return

    for uid in ("prometheus", "odoo"):
        estado, respuesta = grafana.get(f"/api/datasources/uid/{uid}/health")
        if estado == 200 and respuesta.get("status") == "OK":
            ok(f"fuente de datos «{uid}»: {respuesta.get('message')}")
        else:
            mal(f"fuente de datos «{uid}»: {respuesta}")

    tableros = {}
    for uid in TABLEROS:
        estado, respuesta = grafana.get(f"/api/dashboards/uid/{uid}")
        if estado == 200:
            tableros[uid] = respuesta["dashboard"]
            cantidad = sum(1 for p in paneles(tableros[uid]) if p["type"] != "row")
            ok(f"tablero «{respuesta['dashboard']['title']}» ({cantidad} paneles)")
        else:
            mal(f"falta el tablero {uid}")

    esperadas = sum(len(re.findall(r"^\s+- uid: ", p.read_text(encoding="utf-8"), re.M))
                    for p in (MONITOREO / "grafana/aprovisionamiento/alerting").glob("reglas-*.yaml"))
    estado, reglas = grafana.get("/api/v1/provisioning/alert-rules")
    reglas = reglas if estado == 200 else []
    if len(reglas) == esperadas:
        pausadas = [r["title"] for r in reglas if r.get("isPaused")]
        ok(f"{len(reglas)} reglas de alerta" + (f" (pausadas: {', '.join(pausadas)})" if pausadas else ""))
    else:
        mal(f"reglas de alerta: hay {len(reglas)}, se esperaban {esperadas}")
    estado, evaluadas = grafana.get("/api/prometheus/grafana/api/v1/rules")
    grupos = (evaluadas or {}).get("data", {}).get("groups", [])
    con_error = [f"{r['name']}: {r.get('lastError')}" for g in grupos for r in g["rules"]
                 if r.get("health") == "error"]
    if con_error:
        for e in con_error:
            mal(f"regla con error: {e}")
    else:
        ok("ninguna regla con error al evaluarse")

    estado, contactos = grafana.get("/api/v1/provisioning/contact-points")
    tipos = sorted(c["type"] for c in (contactos or []) if c.get("name") == "avisos")
    if "webhook" in tipos:
        ok(f"contacto «avisos»: {', '.join(tipos)} (webhook = relay a Discord)")
    else:
        mal(f"contacto «avisos» sin el webhook del relay: {tipos}")

    print("Prometheus")
    estado, destinos = prom.get("/api/v1/targets")
    activos = destinos["data"]["activeTargets"] if estado == 200 else []
    caidos = [f"{d['labels']['job']} ({d['scrapeUrl']}): {d['lastError']}" for d in activos
              if d["health"] != "up"]
    if activos and not caidos:
        ok(f"{len(activos)} destinos leídos: {', '.join(sorted({d['labels']['job'] for d in activos}))}")
    for c in caidos:
        mal(f"destino caído: {c}")

    print("Consultas de los tableros")
    for tablero in tableros.values():
        sql_bien = prom_bien = 0
        for panel in paneles(tablero):
            for objetivo in panel.get("targets", []):
                uid_fuente = objetivo.get("datasource", {}).get("uid")
                if uid_fuente == "odoo":
                    # Como lo arma Grafana: ${dias:sqlstring} va entre comillas; $dias, tal cual
                    consulta = (objetivo["rawSql"].replace("${dias:sqlstring}", "'60'")
                                .replace("$dias", "60"))
                    error = correr_sql(grafana, consulta, objetivo.get("format"))
                    if error:
                        mal(f"{tablero['title']} → «{panel['title']}»: {error}")
                    else:
                        sql_bien += 1
                elif uid_fuente == "prometheus":
                    estado, r = prom.pedir("GET", "/api/v1/query?" + urllib.parse.urlencode(
                        {"query": promql_para_probar(objetivo["expr"], base)}))
                    if estado == 200 and r.get("status") == "success":
                        prom_bien += 1
                    else:
                        detalle = r.get("error") if isinstance(r, dict) else r
                        mal(f"{tablero['title']} → «{panel['title']}»: {detalle}")
        ok(f"{tablero['title']}: {sql_bien} SQL y {prom_bien} PromQL sin error")

    print("Consultas de las alertas")
    bien = 0
    for regla in reglas:
        for dato in regla["data"]:
            if dato.get("datasourceUid") == "odoo":
                error = correr_sql(grafana, dato["model"]["rawSql"], "table")
            elif dato.get("datasourceUid") == "prometheus":
                consulta = urllib.parse.urlencode({"query": dato["model"]["expr"]})
                estado, r = prom.pedir("GET", "/api/v1/query?" + consulta)
                error = None if estado == 200 else (r.get("error") if isinstance(r, dict) else r)
            else:
                continue
            if error:
                mal(f"alerta «{regla['title']}»: {error}")
            else:
                bien += 1
    ok(f"{bien} consultas de alertas sin error")


def correr_sql(grafana, consulta, formato):
    estado, r = grafana.pedir("POST", "/api/ds/query", {
        "from": "now-30d", "to": "now",
        "queries": [{"refId": "A", "datasource": {"uid": "odoo"}, "rawSql": consulta,
                     "format": formato or "table", "rawQuery": True}]})
    if estado != 200:
        detalle = r.get("results", {}).get("A", {}).get("error") if isinstance(r, dict) else None
        return detalle or f"HTTP {estado}: {r}"
    return r["results"]["A"].get("error")


# ---------------------------------------------------------------- prueba de avisos (lab)

def receptor(metodo="GET"):
    filtro = "label=com.docker.compose.service=receptor-prueba"
    contenedor = subprocess.run(["docker", "ps", "-q", "-f", filtro],
                                capture_output=True, text=True, check=True).stdout.split()
    if not contenedor:
        sys.exit("No está el receptor de prueba: make lab-monitoreo (solo en el lab).")
    codigo = ("import json,urllib.request as u;"
              f"r=u.urlopen(u.Request('http://localhost:8080/capturas',method='{metodo}'));"
              "print(r.read().decode() or '[]')")
    salida = subprocess.run(["docker", "exec", contenedor[0], "python", "-c", codigo],
                            capture_output=True, text=True, check=True).stdout
    return json.loads(salida)


def esperar_tarjeta(condicion, segundos=180):
    limite = time.time() + segundos
    while time.time() < limite:
        for captura in receptor():
            for embed in captura["cuerpo"].get("embeds", []):
                if condicion(embed):
                    return captura["cuerpo"]
        time.sleep(3)
    return None


def probar_avisos(grafana):
    print("Prueba de avisos (lab)")
    receptor("DELETE")

    # 1) Aviso de prueba del contacto (lo mismo que el botón «Probar» de Grafana)
    estado, contactos = grafana.get("/api/v1/provisioning/contact-points")
    webhook = next((c for c in contactos or [] if c["name"] == "avisos" and c["type"] == "webhook"), None)
    estado, receptores = grafana.get(RECEPTORES)
    uid = next((r["metadata"]["name"] for r in (receptores or {}).get("items", [])
                if r["spec"]["title"] == "avisos"), None)
    if not (webhook and uid):
        mal("no está el contacto «avisos» con su webhook")
    else:
        estado, r = grafana.pedir("POST", f"{RECEPTORES}/{uid}/test", {
            "integration": {"uid": webhook["uid"], "type": "webhook", "settings": webhook["settings"]},
            "alert": {"labels": {"nivel": "aviso"}, "annotations": {
                "summary": "Prueba del contacto de avisos",
                "description": "Aviso de prueba de verificar-monitoreo.py."}}})
        tarjeta = esperar_tarjeta(lambda e: "Prueba del contacto" in e.get("title", ""), 60)
        if tarjeta:
            ok("aviso de prueba recibido como tarjeta:")
            print(json.dumps(tarjeta, ensure_ascii=False, indent=2))
        else:
            mal(f"no llegó el aviso de prueba (respuesta de Grafana: {estado} {r})")

    # 2) Una regla de verdad con el umbral bajado: copia de «CPU alta» con umbral 0 y sin espera
    estado, original = grafana.get("/api/v1/provisioning/alert-rules/servidor-cpu")
    if estado != 200:
        mal("no está la regla servidor-cpu")
        return
    prueba = copy.deepcopy(original)
    for clave in ("id", "uid", "updated", "provenance"):
        prueba.pop(clave, None)
    prueba.update(title="Prueba: CPU alta (umbral bajado a 0)", ruleGroup="prueba-avisos", **{"for": "0s"})
    prueba["labels"] = {"nivel": "error"}
    prueba["data"][1]["model"]["conditions"][0]["evaluator"]["params"] = [0]
    prueba["notification_settings"] = {"receiver": "avisos", "group_wait": "1s", "group_interval": "10s",
                                       "repeat_interval": "1h"}
    sin_procedencia = {"X-Disable-Provenance": "true"}
    grafana.pedir("PUT", f"/api/v1/provisioning/folder/{original['folderUID']}/rule-groups/prueba-avisos",
                  {"title": "prueba-avisos", "interval": 10, "rules": []}, sin_procedencia)
    estado, creada = grafana.pedir("POST", "/api/v1/provisioning/alert-rules", prueba, sin_procedencia)
    if estado not in (200, 201):
        mal(f"no se pudo crear la regla de prueba: {estado} {creada}")
        return
    try:
        tarjeta = esperar_tarjeta(lambda e: e.get("title", "").startswith("🔴 CPU al"))
        if tarjeta:
            ok("la regla con el umbral bajado saltó y llegó así:")
            print(json.dumps(tarjeta, ensure_ascii=False, indent=2))
        else:
            mal("la regla de prueba no llegó al receptor")
        # Umbral imposible: se arregla
        creada["data"][1]["model"]["conditions"][0]["evaluator"]["params"] = [1000]
        grafana.pedir("PUT", f"/api/v1/provisioning/alert-rules/{creada['uid']}", creada, sin_procedencia)
        tarjeta = esperar_tarjeta(lambda e: e.get("title", "").startswith("✅ Se arregló: Prueba"))
        if tarjeta:
            ok("al volver el umbral, llegó «se arregló»:")
            print(json.dumps(tarjeta, ensure_ascii=False, indent=2))
        else:
            mal("no llegó el «se arregló»")
    finally:
        grafana.pedir("DELETE", f"/api/v1/provisioning/alert-rules/{creada['uid']}", None, sin_procedencia)
        ok("regla de prueba borrada")

    # 3) El mail (Mailpit del lab): «se arregló» no va por mail, como avisar.sh
    try:
        with urllib.request.urlopen("http://127.0.0.1:8025/api/v1/messages?limit=20", timeout=10) as r:
            asuntos = [m["Subject"] for m in json.load(r).get("messages", [])]
        # Los arma el relay como los de avisar.sh: «[servidor] 🔴 asunto» (al pie dice Grafana)
        de_grafana = [a for a in asuntos if "CPU al" in a or "Prueba del contacto" in a]
        if de_grafana:
            ok(f"mails en Mailpit: {de_grafana[:3]}")
        else:
            mal("no llegó ningún mail de Grafana a Mailpit")
    except OSError as error:
        mal(f"no se pudo leer Mailpit: {error}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stack", default="lab", choices=["lab", "onprem"])
    parser.add_argument("--grafana", default="http://127.0.0.1:3000")
    parser.add_argument("--prometheus", default="http://127.0.0.1:9090")
    parser.add_argument("--probar-avisos", action="store_true", help="manda avisos de prueba (solo lab)")
    args = parser.parse_args()
    env = MONITOREO / "lab/monitoreo.env" if args.stack == "lab" else Path("/etc/odoo-comercio/monitoreo.env")
    try:
        datos = leer_env(env)
    except PermissionError:
        sys.exit(f"No se puede leer {env}: correrlo con sudo.")
    grafana = Api(args.grafana, "admin", datos.get("GF_SECURITY_ADMIN_PASSWORD"))
    prom = Api(args.prometheus)
    verificar(grafana, prom, datos.get("MONITOREO_DB", "lab"))
    if args.probar_avisos:
        if args.stack != "lab":
            sys.exit("--probar-avisos es solo para el lab (en el servidor llegaría a Discord de verdad).")
        probar_avisos(grafana)
    print()
    if FALLAS:
        print(f"✗ {len(FALLAS)} problema(s)")
        sys.exit(1)
    print("✓ Monitoreo verificado")


if __name__ == "__main__":
    main()
