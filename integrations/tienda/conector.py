"""Conector de la tienda online (ADR 0033): corre en el servidor del local y siempre SALE hacia
la tienda; el local no publica ninguna API.

Tienda → Odoo: trae los pedidos pagos y los crea confirmados en Odoo (la tienda los marca
«en Odoo» y su reserva deja de restarse aparte).

Odoo → tienda: lee la cola de cambios de `comercio_tienda` en lotes, los manda firmados a la
tienda, sube las fotos que le faltan y recién entonces confirma el lote en Odoo. Si algo falla, no
confirma: el lote se vuelve a mandar en la próxima vuelta (la tienda lo aplica sin duplicar).

Configuración por variables de entorno (en el servidor: /etc/odoo-comercio/conector-tienda.env):
  ODOO_URL, ODOO_DB, ODOO_API_KEY     usuario con el grupo «Tienda online: conector»
  TIENDA_URL                          https://demo.comercio-ejemplo.example o https://comercio-ejemplo.example
  CONECTOR_SECRETO                    la misma clave que el secreto CONECTOR_SECRETO de la tienda
  HC_PING_URL                         (opcional) healthchecks.io: ping tras cada vuelta sin error
  INTERVALO                           segundos entre vueltas (por defecto 5)

Uso:  python -m conector [--una-vez] [--todo]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("conector-tienda")
LOTE = 200


class ErrorTienda(RuntimeError):
    pass


class Odoo:
    """Llamadas JSON-2 mínimas (el usuario del conector solo ve la cola)."""

    def __init__(self, url: str, base: str, clave: str, plazo: float = 120):
        self.url, self.base, self.clave, self.plazo = url.rstrip("/"), base, clave, plazo

    def llamar(self, metodo: str, **kwargs):
        req = urllib.request.Request(
            f"{self.url}/json/2/comercio.tienda.cambio/{metodo}",
            data=json.dumps(kwargs).encode(),
            method="POST",
            headers={
                "Authorization": f"bearer {self.clave}",
                "X-Odoo-Database": self.base,
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "conector-tienda",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.plazo) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            detalle = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"Odoo {metodo}: HTTP {e.code}: {detalle}") from None


class Tienda:
    def __init__(self, url: str, secreto: str, plazo: float = 60):
        if len(secreto) < 32:
            raise SystemExit("CONECTOR_SECRETO tiene que tener al menos 32 caracteres")
        p = urllib.parse.urlparse(url)
        if p.scheme != "https" and p.hostname not in ("localhost", "127.0.0.1"):
            raise SystemExit("TIENDA_URL tiene que ser https (salvo localhost para pruebas)")
        self.url, self.secreto, self.plazo = url.rstrip("/"), secreto.encode(), plazo

    def enviar(self, metodo: str, ruta: str, cuerpo: bytes, tipo: str) -> dict:
        fecha = str(int(time.time()))
        msg = f"{fecha}.{metodo}.{ruta}.{hashlib.sha256(cuerpo).hexdigest()}".encode()
        firma = hmac.new(self.secreto, msg, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            self.url + ruta,
            data=cuerpo or None,
            method=metodo,
            headers={
                "Content-Type": tipo,
                "X-Tienda-Fecha": fecha,
                "X-Tienda-Firma": firma,
                "User-Agent": "conector-tienda",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.plazo) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise ErrorTienda(
                f"tienda {ruta}: HTTP {e.code}: {e.read().decode(errors='replace')[:300]}"
            ) from None
        except urllib.error.URLError as e:
            raise ErrorTienda(f"tienda {ruta}: {e.reason}") from None


def vuelta(odoo: Odoo, tienda: Tienda) -> int:
    """Una pasada: manda hasta vaciar la cola (de a lotes). Devuelve cuántos cambios aplicó."""
    total = 0
    while True:
        lote = odoo.llamar("tienda_leer_cambios", limite=LOTE)
        if not lote["cambios"]:
            return total
        envio = {
            k: lote[k]
            for k in (
                "productos",
                "productos_borrados",
                "categorias",
                "categorias_borradas",
                "listas",
                "empleados",
            )
        }
        envio["numero"] = time.time_ns() // 1_000_000
        r = tienda.enviar(
            "POST", "/api/conector/lote", json.dumps(envio, ensure_ascii=False).encode(), "application/json"
        )
        faltan = set(r.get("imagenes_faltantes") or [])
        for p in lote["productos"]:
            if p.get("imagen") in faltan:
                foto = odoo.llamar("tienda_imagen", producto_id=p["id"])
                if foto.get("id") == p["imagen"] and foto.get("datos"):
                    tienda.enviar(
                        "PUT",
                        f"/api/conector/imagen/{foto['id']}",
                        base64.b64decode(foto["datos"]),
                        "application/octet-stream",
                    )
                    # Las versiones livianas (WebP 400 y 800 px) después: la de 800 marca la foto
                    # como completa en la tienda (si Odoo no las manda, la tienda usa la original)
                    for ancho in ("400", "800"):
                        if (foto.get("webp") or {}).get(ancho):
                            tienda.enviar(
                                "PUT",
                                f"/api/conector/imagen/{foto['id']}-{ancho}",
                                base64.b64decode(foto["webp"][ancho]),
                                "application/octet-stream",
                            )
                    faltan.discard(p["imagen"])
        odoo.llamar("tienda_confirmar", cambios=lote["cambios"])
        total += len(lote["cambios"])
        log.info(
            "lote aplicado: %d cambios, %d pendientes",
            len(lote["cambios"]),
            max(0, lote["pendientes"] - len(lote["cambios"])),
        )


def pedidos(odoo: Odoo, tienda: Tienda, r: dict) -> int:
    """Tienda → Odoo: los pedidos pagos se crean confirmados en Odoo y se avisa a la tienda."""
    lista = r.get("pedidos") or []
    if not lista:
        return 0
    resultado = odoo.llamar("tienda_crear_pedidos", pedidos=lista)
    # Los que dieron error quedan pendientes en la tienda y se reintentan en la vuelta siguiente
    for h in resultado:
        if h.get("error"):
            log.error("pedido %s no se pudo crear en Odoo: %s", h["id"], h["error"])
    hechos = [h for h in resultado if not h.get("error")]
    if hechos:
        tienda.enviar(
            "POST",
            "/api/conector/pedidos/confirmar",
            json.dumps({"pedidos": hechos}).encode(),
            "application/json",
        )
        log.info("pedidos creados en Odoo: %s", ", ".join(h["odoo_nombre"] for h in hechos))
    return len(hechos)


def acciones(odoo: Odoo, tienda: Tienda, r: dict) -> int:
    """Panel de la tienda → Odoo: preparar, listo (valida la entrega), falta algo, retirado."""
    lista = r.get("acciones") or []
    if not lista:
        return 0
    hechas = odoo.llamar("tienda_aplicar_acciones", acciones=lista)
    if hechas:
        tienda.enviar(
            "POST",
            "/api/conector/acciones/confirmar",
            json.dumps({"acciones": hechas}).encode(),
            "application/json",
        )
        log.info("acciones aplicadas en Odoo: %d", len(hechas))
    return len(hechas)


def clientes(odoo: Odoo, tienda: Tienda, r: dict) -> int:
    """Administración de la tienda → Odoo: mayoristas aprobados (contacto y lista) y listas nuevas."""
    cs, ls = r.get("clientes") or [], r.get("listas") or []
    if not cs and not ls:
        return 0
    hecho = odoo.llamar("tienda_sincronizar_clientes", clientes=cs, listas=ls)
    tienda.enviar(
        "POST",
        "/api/conector/clientes/confirmar",
        json.dumps({"clientes": hecho.get("clientes") or [], "listas": hecho.get("listas") or []}).encode(),
        "application/json",
    )
    log.info("mayoristas y listas en Odoo: %d y %d", len(cs), len(ls))
    return len(cs) + len(ls)


def ping(url: str | None, falla: bool = False) -> None:
    if not url:
        return
    try:
        urllib.request.urlopen(url + ("/fail" if falla else ""), timeout=10).read()
    except Exception as e:  # noqa: BLE001 - el ping nunca frena el conector
        log.warning("no se pudo avisar a healthchecks: %s", e)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Conector Odoo → tienda online")
    ap.add_argument("--una-vez", action="store_true", help="una sola pasada y salir (pruebas)")
    ap.add_argument("--todo", action="store_true", help="volver a mandar todo lo publicado")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    env = os.environ
    odoo = Odoo(env["ODOO_URL"], env["ODOO_DB"], env["ODOO_API_KEY"])
    tienda = Tienda(env["TIENDA_URL"], env["CONECTOR_SECRETO"])
    intervalo = max(2.0, float(env.get("INTERVALO", "5")))
    hc = env.get("HC_PING_URL") or None
    if a.todo:
        log.info("se marcan para enviar %d productos", odoo.llamar("tienda_marcar_todo"))
    errores = 0
    while True:
        try:
            # Primero lo que viene de la tienda (pedidos pagos, panel, mayoristas) y después el
            # catálogo: así el stock nuevo de un pedido sale en la misma vuelta. Cada etapa por su
            # cuenta: un lote rechazado o un pedido con error no frena a las demás (revisión 16/11).
            n, fallas = 0, []
            try:
                r = tienda.enviar("GET", "/api/conector/pendientes", b"", "application/json")
            except Exception as e:  # noqa: BLE001
                r, fallas = {}, [f"pendientes: {e}"]
            for etapa in (pedidos, acciones, clientes):
                try:
                    n += etapa(odoo, tienda, r)
                except Exception as e:  # noqa: BLE001
                    fallas.append(f"{etapa.__name__}: {e}")
            try:
                n += vuelta(odoo, tienda)
            except Exception as e:  # noqa: BLE001
                fallas.append(f"catálogo: {e}")
            if fallas:
                raise RuntimeError(" | ".join(fallas))
            errores = 0
            ping(hc)
            if a.una_vez:
                log.info("listo: %d cambios", n)
                return 0
        except Exception as e:  # noqa: BLE001 - sigue intentando; avisa a healthchecks
            errores += 1
            log.error("vuelta con error (%d seguidas): %s", errores, e)
            if errores in (3, 30, 300):
                ping(hc, falla=True)
            if a.una_vez and errores >= 3:
                return 1
            if a.una_vez:
                time.sleep(3)
                continue
        time.sleep(min(300.0, intervalo * (2 ** min(errores, 6))) if errores else intervalo)


if __name__ == "__main__":
    sys.exit(main())
