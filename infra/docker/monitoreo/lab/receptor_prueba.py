"""Receptor de prueba del laboratorio (ADR 0028): hace de webhook de Discord.

POST /discord   guarda el JSON recibido (lo que llegaría a Discord) y responde 204.
GET  /capturas  devuelve todo lo recibido, en orden.
DELETE /capturas  borra lo recibido.
Solo biblioteca estándar. Vive en la red interna «monitoreo», sin puertos publicados.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CAPTURAS = []


class Receptor(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (nombre de http.server)
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo)
        try:
            dato = json.loads(cuerpo)
        except ValueError:
            dato = {"no_json": cuerpo.decode("utf-8", "replace")}
        CAPTURAS.append({"ruta": self.path, "cuerpo": dato})
        print("RECIBIDO", self.path, json.dumps(dato, ensure_ascii=False), flush=True)
        self.send_response(204)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        datos = json.dumps(CAPTURAS, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_DELETE(self):  # noqa: N802
        CAPTURAS.clear()
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Receptor).serve_forever()
