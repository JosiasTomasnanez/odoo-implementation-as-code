"""Formato de los avisos del servidor: un solo diseño para Discord y para el mail.

Lo usan:
- infra/servidor/avisar.sh (ADR 0027): `python3 formato_avisos.py discord|mail` con las
  variables NIVEL, ASUNTO, TEXTO, SERVIDOR y FECHA (mail: también MAIL_DE y MAIL_PARA);
  imprime el JSON del webhook o el mail entero (para msmtp).
- el relay de Grafana (infra/docker/monitoreo/relay/relay_discord.py, ADR 0028), que lo importa.

Una tarjeta por aviso: color según el nivel, ícono y asunto en el título, el detalle en un
recuadro y servidor, fecha y hora al pie. Discord: sin «timestamp» (el «Hoy a las…» repetía la
hora). Mail: HTML con la misma tarjeta y una versión en texto para los programas que no
muestran HTML. Solo biblioteca estándar (corre en el servidor y en el contenedor del relay).
"""

import html
import json
import os
import sys
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

COLORES = {"ok": 0x2ECC71, "info": 0x3498DB, "aviso": 0xF39C12, "error": 0xE74C3C}
ICONOS = {"ok": "✅", "info": "ℹ️", "aviso": "⚠️", "error": "🔴"}
ETIQUETAS = {"ok": "TODO BIEN", "info": "INFORMACIÓN", "aviso": "AVISO", "error": "PROBLEMA"}


def _pie(servidor, fecha, origen):
    return " · ".join(p for p in (servidor, fecha, origen) if p)


def tarjeta(nivel, asunto, texto="", servidor="", fecha="", origen=""):
    """Cuerpo del webhook de Discord para un aviso. `origen` se suma al pie (p. ej. «Grafana»)."""
    embed = {
        "title": (ICONOS[nivel] + " " + asunto)[:256],
        "color": COLORES[nivel],
        "footer": {"text": _pie(servidor, fecha, origen)},
    }
    if texto:
        embed["description"] = "```\n" + texto[:3900] + "\n```"
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


def mail_html(nivel, asunto, texto="", servidor="", fecha="", origen=""):
    """La misma tarjeta en HTML de correo: tablas y estilos en línea (Gmail ignora <style>)."""
    color = f"#{COLORES[nivel]:06X}"
    detalle = ""
    if texto:
        detalle = (
            '<tr><td style="padding:0 24px 20px 24px">'
            '<div style="background:#F6F8FA;border:1px solid #E5E7EB;border-radius:6px;'
            "padding:12px 14px;font-family:Consolas,Menlo,'Courier New',monospace;font-size:13px;"
            'line-height:1.5;color:#1F2937;white-space:pre-wrap;word-break:break-word">'
            + html.escape(texto) + "</div></td></tr>")
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#F3F4F6">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#F3F4F6;padding:24px 12px"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;background:#FFFFFF;border-radius:8px;'
        f'border-left:8px solid {color};font-family:Arial,Helvetica,sans-serif">'
        '<tr><td style="padding:20px 24px 4px 24px">'
        f'<span style="display:inline-block;background:{color};color:#FFFFFF;font-size:11px;'
        'font-weight:bold;letter-spacing:1px;padding:3px 8px;border-radius:4px">'
        f"{ETIQUETAS[nivel]}</span></td></tr>"
        '<tr><td style="padding:8px 24px 16px 24px;font-size:20px;line-height:1.3;'
        f'font-weight:bold;color:#111827">{ICONOS[nivel]} {html.escape(asunto)}</td></tr>'
        + detalle +
        '<tr><td style="padding:12px 24px 16px 24px;border-top:1px solid #E5E7EB;'
        f'font-size:12px;color:#6B7280">{html.escape(_pie(servidor, fecha, origen))}</td></tr>'
        "</table>"
        '<p style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#9CA3AF;'
        'margin:12px 0 0 0">Aviso automático del servidor de Comercio Ejemplo.</p>'
        "</td></tr></table></body></html>")


def mail(nivel, asunto, texto="", servidor="", fecha="", origen="", de="", para=""):
    """Mail completo (HTML + texto). Asunto: «[servidor] ícono asunto»."""
    mensaje = EmailMessage()
    mensaje["From"] = formataddr(("Servidor Comercio Ejemplo", de))
    mensaje["To"] = para
    mensaje["Subject"] = f"[{servidor}] {ICONOS[nivel]} {asunto}" if servidor else f"{ICONOS[nivel]} {asunto}"
    mensaje["Message-ID"] = make_msgid(domain=de.split("@")[-1] if "@" in de else None)
    partes = [asunto, ""]
    if texto:
        partes += [texto, ""]
    partes.append("-- " + _pie(servidor, fecha, origen))
    mensaje.set_content("\n".join(partes))
    mensaje.add_alternative(mail_html(nivel, asunto, texto, servidor, fecha, origen), subtype="html")
    return mensaje


if __name__ == "__main__":
    e = os.environ
    datos = (e["NIVEL"], e["ASUNTO"], e.get("TEXTO", ""), e.get("SERVIDOR", ""), e.get("FECHA", ""))
    if len(sys.argv) > 1 and sys.argv[1] == "mail":
        sys.stdout.write(mail(*datos, de=e.get("MAIL_DE", ""), para=e.get("MAIL_PARA", "")).as_string())
    else:
        print(json.dumps(tarjeta(*datos)))
