"""Relay de alertas de Grafana a Discord y al mail (ADR 0028).

Por qué existe: el contacto nativo de Discord de Grafana 13 fija el pie («Grafana vX»), el
color (rojo o verde, sin niveles) y suma un link a la regla, y su mail tiene otro diseño; los
avisos tienen que verse igual que los de infra/servidor/avisar.sh. Grafana manda sus alertas
acá (contacto «webhook») y esto las reenvía con el mismo formato (formato_avisos.py, compartido
con avisar.sh): una tarjeta por alerta en Discord y un mail HTML por alerta, color según la
etiqueta `nivel`, «✅ Se arregló: …» al resolverse (solo a Discord, como avisar.sh) y
«servidor · fecha hora · Grafana» al pie, en hora de Argentina.

Solo biblioteca estándar. Escucha en la red interna «monitoreo», sin puertos publicados.
Si Discord no responde contesta 502 y Grafana reintenta (el mail se manda una vez).

Grafana reenvía el grupo entero (todas las alertas encendidas) cada vez que una cambia: cada
alerta encendida se avisa una sola vez por día (por su huella), no en cada reenvío. Las de
negocio (`tipo: negocio`: listas, facturas) van solo a Discord, nunca por mail (18/11: llenaron
el cupo de Resend).
"""

import json
import os
import smtplib
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from formato_avisos import mail, tarjeta

ZONA = ZoneInfo("America/Argentina/Cordoba")
NIVELES = {"error", "aviso", "info"}
# Etiquetas que dicen cuál de varias cosas saltó (en el orden en que se buscan)
DETALLE = ("mountpoint", "device", "relname", "lista", "chip", "job")
# Una alerta encendida no se vuelve a avisar antes de esto (Grafana la repite cada 24 h)
REPETIR_CADA = 23 * 3600
# Más de estas alertas iguales (misma regla y estado) en un envío: una sola tarjeta con el total
JUNTAR_DESDE = 4
_avisadas = {}  # huella → cuándo se avisó (en memoria: al reiniciar, a lo sumo se repite una vez)


def nueva(huella, ahora=None):
    """¿Hay que avisar esta alerta encendida? Sí si no se avisó en las últimas REPETIR_CADA."""
    ahora = time.time() if ahora is None else ahora
    for h, cuando in list(_avisadas.items()):
        if ahora - cuando >= REPETIR_CADA:
            del _avisadas[h]
    if not huella:
        return True
    if huella in _avisadas:
        return False
    _avisadas[huella] = ahora
    return True


def avisos_de(alerta_grafana):
    """(nivel, asunto, texto, servidor, fecha, por_mail) por alerta del mensaje de Grafana
    («webhook»), sin las encendidas que ya se avisaron hoy."""
    servidor = os.environ.get("AVISOS_SERVIDOR") or "servidor"
    fecha = datetime.now(ZONA).strftime("%d/%m/%Y %H:%M")
    for alerta in alerta_grafana.get("alerts", []):
        etiquetas = alerta.get("labels", {})
        notas = alerta.get("annotations", {})
        asunto = notas.get("summary") or etiquetas.get("alertname", "Alerta de Grafana")
        texto = notas.get("description", "")
        huella = alerta.get("fingerprint") or json.dumps(etiquetas, sort_keys=True)
        por_mail = etiquetas.get("tipo") != "negocio"
        if alerta.get("status") == "resolved":
            _avisadas.pop(huella, None)
            # El resumen tiene el valor de cuando saltó: al arreglarse va el nombre de la regla
            # y qué la disparó (partición, tabla, lista…)
            cual = next((etiquetas[e] for e in DETALLE if etiquetas.get(e)), "")
            nivel = "ok"
            asunto = "Se arregló: " + etiquetas.get("alertname", asunto) + (f" ({cual})" if cual else "")
        else:
            if not nueva(huella):
                continue
            nivel = etiquetas.get("nivel") if etiquetas.get("nivel") in NIVELES else "aviso"
        yield nivel, asunto, texto, servidor, fecha, por_mail


def _avisos_y_alertas(mensaje):
    """(aviso, alerta de Grafana) de las que hay que avisar."""
    for alerta in mensaje.get("alerts", []):
        for aviso in avisos_de({"alerts": [alerta]}):
            yield aviso, alerta


def mandar_mail(nivel, asunto, texto, servidor, fecha):
    """Como avisar.sh: problemas por mail, «se arregló» solo a Discord. Sin SMTP, nada."""
    e = os.environ
    if nivel == "ok" or not (e.get("SMTP_HOST") and e.get("MAIL_PARA")):
        return
    de = e.get("MAIL_DE") or e.get("SMTP_USUARIO", "")
    mensaje = mail(nivel, asunto, texto, servidor, fecha, "Grafana", de=de, para=e["MAIL_PARA"])
    puerto = int(e.get("SMTP_PORT") or 587)
    try:
        if puerto == 465:
            conexion = smtplib.SMTP_SSL(e["SMTP_HOST"], puerto, timeout=30,
                                        context=ssl.create_default_context())
        else:
            conexion = smtplib.SMTP(e["SMTP_HOST"], puerto, timeout=30)
            if e.get("SMTP_TLS", "on") != "off":  # off: solo para el Mailpit del lab
                conexion.starttls(context=ssl.create_default_context())
        with conexion:
            if e.get("SMTP_CLAVE"):
                conexion.login(e.get("SMTP_USUARIO", ""), e["SMTP_CLAVE"])
            conexion.send_message(mensaje, to_addrs=[d.strip() for d in e["MAIL_PARA"].split(",")])
    except (OSError, smtplib.SMTPException) as error:
        print("No se pudo mandar el mail:", error)


def mandar(cuerpo):
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        print("Sin DISCORD_WEBHOOK_URL: no se manda", json.dumps(cuerpo, ensure_ascii=False))
        return True
    datos = json.dumps(cuerpo).encode()
    for _ in range(3):
        pedido = urllib.request.Request(url, data=datos, method="POST", headers={
            "Content-Type": "application/json", "User-Agent": "relay-discord-ejemplo"})
        try:
            with urllib.request.urlopen(pedido, timeout=20):
                return True
        except urllib.error.HTTPError as error:
            if error.code == 429:  # Discord pide esperar
                time.sleep(min(float(error.headers.get("Retry-After") or 2), 10))
                continue
            print("Discord respondió", error.code, error.read()[:300])
            return False
        except OSError as error:
            print("No se pudo llegar a Discord:", error)
            return False
    return False


def juntar(avisos, alertas):
    """Las alertas iguales que llegan de a muchas (p. ej. una por lista) van en un solo aviso:
    «N × regla», con las primeras como ejemplo."""
    grupos = {}
    for aviso, alerta in zip(avisos, alertas, strict=True):
        regla = alerta.get("labels", {}).get("alertname", "Alerta")
        grupos.setdefault((aviso[0], regla), []).append(aviso)
    salida = []
    for (nivel, regla), lista in grupos.items():
        if len(lista) < JUNTAR_DESDE:
            salida.extend(lista)
            continue
        _, _, texto, servidor, fecha, por_mail = lista[0]
        ejemplos = "\n".join("• " + a[1] for a in lista[:5]) + ("\n…" if len(lista) > 5 else "")
        asunto = (f"Se arreglaron {len(lista)}: {regla}" if nivel == "ok"
                  else f"{len(lista)} × {regla}")
        salida.append((nivel, asunto, ejemplos + ("\n\n" + texto if texto and nivel != "ok" else ""),
                       servidor, fecha, por_mail))
    return salida


class Relay(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (nombre de http.server)
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            mensaje = json.loads(self.rfile.read(largo))
        except ValueError:
            self.send_response(400)
            self.end_headers()
            return
        pares = list(_avisos_y_alertas(mensaje))
        avisos = juntar([a for a, _ in pares], [al for _, al in pares])
        bien = all([mandar(tarjeta(*a[:5], "Grafana")) for a in avisos])
        if bien:  # si Discord falla, Grafana reintenta: el mail sale en ese reintento
            for *aviso, por_mail in avisos:
                if por_mail:
                    mandar_mail(*aviso)
        else:  # que el reintento de Grafana las vuelva a mandar
            for alerta in mensaje.get("alerts", []):
                _avisadas.pop(alerta.get("fingerprint"), None)
        self.send_response(204 if bien else 502)
        self.end_headers()

    def do_GET(self):  # noqa: N802 (prueba de vida)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Relay).serve_forever()
