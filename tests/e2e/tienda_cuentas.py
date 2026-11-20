"""Prueba de punta a punta de las cuentas de clientes de la tienda (fase 6) contra la demo.

Con un mail de prueba (example.com: la tienda nunca le manda mails) y el código puesto a mano en
D1 (el mail no se manda):

1. Pedir el código: siempre el mismo mensaje; con un código equivocado no entra; con el bueno sí.
2. «Mis pedidos» muestra los pedidos hechos antes con ese mail y «Repetir este pedido».
3. La tienda no muestra nada mayorista (ADR 0035). En el sitio mayorista (otro dominio, otra
   sesión): sin aprobación no hay lista ni Excel; CUIT inválido no; válido → «pendiente»; aprobada
   con la lista «Mayorista» → lista con «Tu precio», Excel válido y «Mis pedidos» sin los de la tienda.
4. Sin sesión, «Mis pedidos» manda a ingresar; otro origen no puede pedir códigos ni salir.

Uso: make e2e-tienda-cuentas
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tienda_pedidos as tp  # noqa: E402
from tienda_panel import get, navegador, post  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
EMAIL = f"cuenta{int(time.time())}@example.com"
MAYORISTAS = os.environ.get("MAYORISTAS", "https://mayoristas-demo.comercio-ejemplo.example")


def d1(sql: str) -> str:
    r = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "comercio-ejemplo-tienda-demo", "--remote", "--command", sql],
        cwd=RAIZ / "web/tienda",
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PATH": f"{Path.home()}/.local/node22/bin:{os.environ['PATH']}"},
    )
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout


def main() -> int:
    estado, d = tp.pedir(tp.slug_de("candado"), 1, email=EMAIL)
    pid, tok = tp.id_y_token(d["pago"])
    tp.http("POST", "/api/pago/simulado", form={"id": pid, "t": tok, "decision": "aprobar"})

    jar, op = navegador()
    clave = "Prueba-e2e-2026"
    alta = {"para": "alta", "email": EMAIL, "clave": clave, "cf-turnstile-response": tp.TOKEN_PRUEBA}
    e, loc = post(op, "/api/cuenta/codigo", {**alta, "clave": "corta"})
    assert "e=clave" in loc, loc
    e, loc = post(op, "/api/cuenta/codigo", {**alta, "clave2": clave + "x"})
    assert "e=repetir" in loc, loc
    e, loc = post(op, "/api/cuenta/codigo", alta)
    assert "modo=codigo&p=alta" in loc, loc
    codigo = "135790"
    # El código de «crear cuenta» está atado al navegador que lo pidió (cookie cf_alta)
    atado = next(k.value for k in jar if k.name == "cf_alta")
    h = hashlib.sha256(f"{EMAIL}:{codigo}:{atado}".encode()).hexdigest()
    d1(f"UPDATE codigos_ingreso SET codigo_hash = '{h}' WHERE email = '{EMAIL}'")
    e, loc = post(op, "/api/cuenta/verificar", {"email": EMAIL, "p": "alta", "codigo": "000000"})
    assert "e=codigo" in loc, loc
    _, ajeno = navegador()
    e, loc = post(ajeno, "/api/cuenta/verificar", {"email": EMAIL, "p": "alta", "codigo": codigo})
    assert "e=navegador" in loc, ("el código no vale en otro navegador", loc)
    e, loc = post(op, "/api/cuenta/verificar", {"email": EMAIL, "p": "alta", "codigo": codigo})
    assert loc == f"{tp.TIENDA}/" and any(k.name == "cf_cliente" for k in jar), loc
    jar, op = navegador()
    e, loc = post(op, "/api/cuenta/entrar", {"email": EMAIL, "clave": "otra-clave-9"})
    assert "e=clave" in loc, loc
    # Ingresar devuelve a donde estaba (lo recuerda la página de ingreso), no a la cuenta
    e, _, _ = get(op, "/cuenta/?v=%2Fcarrito%2F")
    assert e == 200 and any(k.name == "cf_volver" for k in jar), e
    e, _, _ = get(op, "/cuenta/?v=%2F%2Fotro.example")
    e, loc = post(op, "/api/cuenta/entrar", {"email": EMAIL, "clave": clave})
    assert loc == f"{tp.TIENDA}/carrito/" and any(k.name == "cf_cliente" for k in jar), loc
    e, html, _ = get(op, "/cuenta/")
    assert e == 200 and all(t in html for t in ("Mis pedidos", "Cerrar sesión", "data-menu-cuenta")), html[:9]
    e, loc = post(op, "/api/cuenta/datos", {"nombre": "Cliente De Prueba", "telefono": "351 5550000"})
    assert loc.endswith("/cuenta/datos?ok=1"), loc
    e, loc = post(op, "/api/cuenta/datos", {"nombre": "<b>x</b>", "telefono": "abc"})
    assert loc.endswith("/cuenta/datos?e=1"), loc
    e, html, _ = get(op, "/cuenta/datos")
    assert 'value="Cliente De Prueba"' in html and 'value="351 5550000"' in html, html[:300]
    print("1. Crear cuenta: el código confirma el mail; después se entra con la contraseña (la mala no), "
          "vuelve a donde estaba y la cuenta muestra sus opciones y guarda sus datos ✓")

    e, html, _ = get(op, "/cuenta/pedidos")
    assert d["pedido"] in html and "Repetir este pedido" in html, html[:300]
    print(f"2. «Mis pedidos» muestra {d['pedido']} (hecho antes con ese mail) y «Repetir» ✓")

    e, _, _ = get(op, "/cuenta/lista")
    assert e == 404, e
    e, _ = post(op, "/api/cuenta/mayorista", {"razon": "Ferretería Prueba", "cuit": "20-12345678-6"})
    assert e == 404, e
    e, _, _ = get(op, "/mayoristas/")
    assert e == 404, e
    _, may = navegador()
    m = MAYORISTAS
    e, _, loc = get(may, "/", base=m)
    assert e == 303 and loc.endswith("/ingresar"), (e, loc)

    def pm(ruta: str, datos: dict) -> tuple[int, str]:
        return post(may, ruta, datos, origen=m, base=m)

    e, loc = pm("/api/cuenta/entrar", {"email": EMAIL, "clave": "otra-clave-9"})
    assert loc.startswith(m + "/ingresar?e=clave"), loc
    e, loc = pm("/api/cuenta/entrar", {"email": EMAIL, "clave": clave})
    assert loc == m + "/", loc
    e, html, _ = get(may, "/", base=m)
    assert "Pedir cuenta mayorista" in html and "Tu precio" not in html
    assert get(may, "/lista.xlsx", base=m)[0] == 403
    alta = {
        "razon": "Ferretería Prueba",
        "cuit": "20-12345678-6",
        "iva": "monotributo",
        "actividad": "Ferretería",
        "direccion": "Calle Falsa 123",
        "localidad": "Córdoba",
        "telefono": "351 555-0000",
        "contacto": "Ana Prueba",
    }
    e, loc = pm("/api/cuenta/mayorista", {**alta, "cuit": "20-12345678-0"})
    assert "e=cuit" in loc, loc
    e, loc = pm("/api/cuenta/mayorista", {**alta, "iva": ""})
    assert loc.endswith("e=iva"), ("faltan datos de la empresa", loc)
    e, loc = pm("/api/cuenta/mayorista", {**alta, "cuit": "27-12345678-5", "telefono": "12"})
    assert loc.endswith("e=cuit,telefono"), loc
    e, html, _ = get(may, "/?e=cuit,telefono", base=m)
    for t in ("Falta corregir", "CUIT o CUIL no es válido", "Teléfono, con característica"):
        assert t in html, ("no avisa qué corregir", t)
    pm("/api/cuenta/mayorista", alta)
    e, html, _ = get(may, "/", base=m)
    assert "Estamos revisando tu cuenta" in html
    lista = "(SELECT id_odoo FROM listas_precios WHERE nombre = 'Mayorista')"
    d1(f"UPDATE clientes SET mayorista = 'aprobado', lista_id = {lista} WHERE email = '{EMAIL}'")
    e, html, _ = get(may, "/", base=m)
    assert "Tu precio" in html and "Descargar en Excel" in html, html[:300]
    r = may.open(urllib.request.Request(m + "/lista.xlsx", headers={"User-Agent": "e2e-panel"}), timeout=60)
    assert r.status == 200 and r.read(2) == b"PK"
    e, html, _ = get(may, "/pedidos", base=m)
    assert e == 200 and d["pedido"] not in html, "«Mis pedidos» mayorista no muestra los de la tienda"
    # Mi cuenta mayorista: cambia el contacto (queda registrado); el CUIT y la razón social, no
    nuevos = {k: alta[k] for k in ("direccion", "localidad")}
    nuevos.update(contacto="Beto Prueba", telefono="351 555-1111")
    e, loc = pm("/api/cuenta/datos", {**nuevos, "cuit": "30-99999999-9", "razon": "Otra SA", "telefono": "x"})
    assert loc == m + "/cuenta?e=1", loc
    e, loc = pm("/api/cuenta/datos", {**nuevos, "cuit": "30-99999999-9", "razon": "Otra SA"})
    assert loc == m + "/cuenta?ok=1", loc
    e, html, _ = get(may, "/cuenta", base=m)
    for t in ('value="Beto Prueba"', 'value="351 555-1111"', "Ferretería Prueba", "20-12345678-6"):
        assert t in html, ("mi cuenta mayorista", t)
    assert "Otra SA" not in html and "30-99999999-9" not in html, "el CUIT y la razón social no se cambian"
    suyo = f"(SELECT id FROM clientes WHERE email = '{EMAIL}')"
    cambios = d1(f"SELECT campo, antes, despues FROM cambios_cliente WHERE cliente_id = {suyo}")
    assert '"contacto"' in cambios and "Ana Prueba" in cambios and "351 555-1111" in cambios, cambios[-400:]
    # nombre y teléfono (tienda) + contacto y teléfono (mayorista)
    assert cambios.count('"campo"') == 4, cambios[-600:]
    print("3. Tienda sin nada mayorista; sitio mayorista: alta, CUIT, pendiente, aprobada → lista y Excel; "
          "«Mi cuenta» cambia el contacto con registro y deja el CUIT como está ✓")

    _, otro = navegador()
    e, _, loc = get(otro, "/cuenta/pedidos")
    assert e == 303 and loc.endswith("/cuenta?v=/cuenta/pedidos"), (e, loc)
    e, _ = post(op, "/api/cuenta/entrar", {"email": EMAIL, "clave": clave}, origen="https://otro.example")
    assert e == 403, e
    print("4. Sin sesión manda a ingresar; otro origen no ✓")
    print("Cuentas de clientes: todo bien ✓")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        tp.limpiar()
