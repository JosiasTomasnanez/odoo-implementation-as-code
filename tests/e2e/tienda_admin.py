"""Prueba de punta a punta de la administración de la tienda (fase 7) contra la demo y el lab.

Con mails de prueba (example.com: la tienda nunca les manda mails) y los códigos puestos a mano en D1:

1. Sin sesión, /admin manda a ingresar. Primera vez: código por mail + contraseña → adentro (y el
   navegador queda de confianza). Con la contraseña mala no entra.
2. Un mayorista ficticio pide cuenta con los datos de la empresa → aparece en «Pendientes».
   Aprobar con la lista «Mayorista» → el conector crea su contacto en Odoo (CUIT, la lista
   y la etiqueta «Mayorista (tienda online)») y la tienda guarda el n.º de contacto. Un pedido suyo
   en el sitio mayorista entra a Odoo con ese contacto y esa lista.
3. Lista nueva «Mayorista − 5 %» desde la administración → Odoo la crea (regla general sobre la base,
   con la misma compra mínima) y vuelve a la tienda con sus precios.
4. Equipo: sumar a alguien con «Mayoristas»: entra a Mayoristas pero no a Equipo. Nadie se saca su
   propio permiso de administración. Otro origen no puede tocar nada.

Uso: make e2e-tienda-admin
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tienda_pedidos as tp  # noqa: E402
from tienda_panel import get, navegador, post  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
N = int(time.time())
ADMIN = f"admin{N}@example.com"
VENDE = f"vende{N}@example.com"
CLIENTE = f"corralon{N}@example.com"


def cuit_ficticio(n: int) -> str:
    """CUIT ficticio distinto en cada corrida, con dígito verificador válido."""
    while True:
        base = f"20{n % 10**8:08d}"
        v = 11 - sum(int(d) * p for d, p in zip(base, [5, 4, 3, 2, 7, 6, 5, 4, 3, 2], strict=True)) % 11
        if v < 10:
            return base + str(0 if v == 11 else v)
        n += 1


CUIT = cuit_ficticio(N)
CLAVE = "Prueba-admin-2026"
MAYORISTAS = os.environ.get("MAYORISTAS", "https://mayoristas-demo.comercio-ejemplo.example")


def d1(sql: str) -> list[dict]:
    r = subprocess.run(
        [
            "npx",
            "wrangler",
            "d1",
            "execute",
            "comercio-ejemplo-tienda-demo",
            "--remote",
            "--json",
            "--command",
            sql,
        ],
        cwd=RAIZ / "web/tienda",
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PATH": f"{Path.home()}/.local/node22/bin:{os.environ['PATH']}"},
    )
    assert r.returncode == 0, r.stderr[-500:]
    return json.loads(r.stdout)[-1]["results"]


def codigo(clave: str, cod: str) -> None:
    h = hashlib.sha256(f"{clave}:{cod}".encode()).hexdigest()
    d1(f"UPDATE codigos_ingreso SET codigo_hash = '{h}' WHERE email = '{clave}'")


def entrar(email: str):
    jar, op = navegador()
    e, loc = post(op, "/api/admin/clave", {"email": email, "cf-turnstile-response": tp.TOKEN_PRUEBA})
    assert "modo=nueva" in loc, loc
    codigo(f"equipo:{email}", "424242")
    e, loc = post(op, "/api/admin/clave", {"email": email, "codigo": "424242", "clave": CLAVE})
    assert loc.endswith("/admin") and any(k.name == "cf_equipo" for k in jar), loc
    return jar, op


def pedido_mayorista(cid: str) -> dict:
    """Compra en el sitio mayorista con la sesión de ese cliente (puesta a mano en D1), paga (simulado)
    y devuelve el pedido de venta que creó el conector en Odoo."""
    token = hashlib.sha256(f"sesion{N}".encode()).hexdigest()
    d1(
        "INSERT INTO sesiones_cliente (token_hash, cliente_id, vence) VALUES "
        f"('{hashlib.sha256(token.encode()).hexdigest()}', '{cid}', "
        "strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '+1 hour'))"
    )

    def llamar(ruta: str, cuerpo: bytes, tipo: str) -> dict:
        req = urllib.request.Request(
            MAYORISTAS + ruta,
            data=cuerpo,
            method="POST",
            headers={
                "Content-Type": tipo,
                "Origin": MAYORISTAS,
                "Accept": "application/json",
                "User-Agent": "e2e-tienda",
                "Cookie": f"cf_cliente={token}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")

    tp.poner_stock("Pinza universal 8\"", 10)
    tp.conector()
    datos = {
        "lineas": [{"slug": tp.slug_de("pinza universal"), "cantidad": 2}],
        "nombre": "Juan Prueba",
        "email": CLIENTE,
        "telefono": "351 555-0000",
        "turnstile": tp.TOKEN_PRUEBA,
    }
    d = llamar("/api/pedido", json.dumps(datos).encode(), "application/json")
    pid, tok = tp.id_y_token(d["pago"])
    pago = urllib.parse.urlencode({"id": pid, "t": tok, "decision": "aprobar"}).encode()
    llamar("/api/pago/simulado", pago, "application/x-www-form-urlencoded")
    for _ in range(20):
        tp.conector()
        campos = ["name", "partner_id", "pricelist_id", "amount_total", "state"]
        so = tp.c.search_read("sale.order", [("comercio_tienda_ref", "=", pid)], campos)
        if so:
            # El total de Odoo tiene que dar lo cobrado: la lista mayorista es un descuento y Odoo 20
            # lo aplicaba otra vez sobre el precio ya rebajado (revisión del 16/11)
            cobrado = d1(f"SELECT total FROM pedidos WHERE id = '{pid}'")[0]["total"] / 100
            assert abs(so[0]["amount_total"] - cobrado) < 0.01, (so[0]["amount_total"], cobrado)
            assert so[0]["state"] == "sale", so[0]
            return so[0]
    raise AssertionError("el pedido mayorista no llegó a Odoo")


def esperar(sql: str, campo: str, intentos: int = 30):
    for _ in range(intentos):
        r = d1(sql)
        if r and r[0].get(campo):
            return r[0]
        tp.conector()
    raise AssertionError(f"no llegó: {sql}")


def main() -> int:
    d1(
        "INSERT INTO equipo (id, email, nombre, roles, creado) VALUES "
        f"('{hashlib.md5(ADMIN.encode()).hexdigest()}', '{ADMIN}', 'Admin e2e', 'admin', datetime('now'))"
    )
    _, anon = navegador()
    e, _, loc = get(anon, "/admin")
    assert e in (302, 303) and loc.endswith("/admin/ingresar"), (e, loc)
    jar, op = entrar(ADMIN)
    _, otro = navegador()
    e, loc = post(otro, "/api/admin/entrar", {"email": ADMIN, "clave": "otra-clave-9"})
    assert "e=clave" in loc, loc
    e, loc = post(otro, "/api/admin/entrar", {"email": ADMIN, "clave": CLAVE})
    assert "modo=codigo" in loc, ("navegador nuevo: pide código", loc)
    print("1. Primera vez con código y contraseña; contraseña mala no; navegador nuevo pide código ✓")

    cid = hashlib.md5(CLIENTE.encode()).hexdigest()
    d1(
        "INSERT INTO clientes (id, email, creado, mayorista, cuit, razon_social, telefono, condicion_iva, "
        "actividad, direccion, localidad, contacto, pedido_alta) VALUES "
        f"('{cid}', '{CLIENTE}', datetime('now'), 'pendiente', '{CUIT}', "
        f"'Corralón e2e {N} (ficticio)', '351 555-0000', 'ri', 'Corralón o materiales', 'Calle Falsa 123', "
        "'Córdoba', 'Juan Prueba', datetime('now'))"
    )
    e, html, _ = get(op, "/admin/mayoristas")
    assert f"Corralón e2e {N}" in html and "Responsable inscripto" in html, html[:300]
    lista = d1("SELECT id_odoo FROM listas_precios WHERE nombre = 'Mayorista'")[0]["id_odoo"]
    e, loc = post(op, "/api/admin/mayorista", {"id": cid, "accion": "aprobar", "lista": lista, "nota": "e2e"})
    assert "ok=aprobado" in loc, loc
    r = esperar(
        f"SELECT odoo_partner_id, odoo_pendiente, odoo_error FROM clientes WHERE id = '{cid}'",
        "odoo_partner_id",
    )
    socio = tp.c.search_read(
        "res.partner",
        [("id", "=", r["odoo_partner_id"])],
        ["name", "vat", "property_product_pricelist", "category_id"],
    )[0]
    assert CUIT in (socio["vat"] or "").replace("-", ""), socio
    assert socio["property_product_pricelist"][0] == lista, socio
    print(f"2. Aprobado → contacto {socio['id']} en Odoo con CUIT y la lista «Mayorista» ✓")

    # 2c. Un pedido de ese mayorista entra a Odoo con SU contacto y SU lista
    ficha = pedido_mayorista(cid)
    assert ficha["partner_id"][0] == socio["id"] and ficha["pricelist_id"][0] == lista, ficha
    print(f"2c. Pedido mayorista → {ficha['name']} en Odoo con su contacto ({socio['id']}), "
          "su lista y el total cobrado ✓")

    otro_cid = hashlib.md5(f"otro{N}".encode()).hexdigest()
    d1(
        "INSERT INTO clientes (id, email, creado, mayorista, cuit, razon_social, pedido_alta) VALUES "
        f"('{otro_cid}', 'otro{N}@example.com', datetime('now'), 'pendiente', '{CUIT}', "
        "'Impostor e2e', datetime('now'))"
    )
    post(op, "/api/admin/mayorista", {"id": otro_cid, "accion": "aprobar", "lista": lista})
    r = esperar(f"SELECT odoo_error FROM clientes WHERE id = '{otro_cid}'", "odoo_error")
    assert "ya hay un contacto" in r["odoo_error"], r
    d1(f"UPDATE clientes SET mayorista = 'rechazado' WHERE id = '{otro_cid}'")
    print("2b. Mismo CUIT con otro mail: no se vincula al contacto ajeno, avisa en la administración ✓")

    nombre = f"Mayorista − 5 % e2e {N}"
    e, loc = post(op, "/api/admin/lista", {"nombre": nombre, "base": lista, "descuento": "5"})
    assert "ok=1" in loc, loc
    r = esperar(f"SELECT odoo_id, resultado FROM listas_nuevas WHERE nombre = '{nombre}'", "odoo_id")
    nueva = r["odoo_id"]
    esperar(f"SELECT COUNT(*) AS n FROM precios WHERE lista_id = {nueva}", "n")
    base, suya = (
        d1(f"SELECT precio FROM precios WHERE lista_id = {x} ORDER BY producto_id LIMIT 1")[0]["precio"]
        for x in (lista, nueva)
    )
    assert abs(suya - round(base * 0.95)) <= 1, (base, suya)
    print(f"3. Lista nueva creada en Odoo (#{nueva}) y de vuelta con precios: {base} → {suya} (−5 %) ✓")

    # 3b. Condiciones propias (ADR 0037): 10 % en un rubro, 20 % en un producto de ese rubro (le
    # gana al rubro); lo demás sigue con el 5 % general. Al quitar el rubro, vuelve al general.
    lid = d1(f"SELECT id FROM listas_nuevas WHERE odoo_id = {nueva}")[0]["id"]
    con_precio = (
        "FROM productos p JOIN precios x ON x.producto_id = p.id_odoo "
        f"AND x.lista_id = {lista} WHERE p.publicado = 1 AND p.categoria_id IS NOT NULL"
    )
    varios = f"SELECT p.categoria_id AS id, COUNT(*) AS n {con_precio} GROUP BY 1 HAVING n >= 2 LIMIT 1"
    rubro = d1(varios)[0]["id"]
    en_rubro = [
        x["id_odoo"]
        for x in d1(f"SELECT p.id_odoo {con_precio} AND p.categoria_id = {rubro} ORDER BY p.id_odoo LIMIT 2")
    ]
    fuera = d1(f"SELECT p.id_odoo {con_precio} AND p.categoria_id <> {rubro} LIMIT 1")[0]["id_odoo"]

    def precio(lista_id: int, prod: int) -> int:
        fila = d1(f"SELECT precio FROM precios WHERE lista_id = {lista_id} AND producto_id = {prod}")
        return fila[0]["precio"]

    def esperar_precio(prod: int, factor: float) -> None:
        quiero = precio(lista, prod) * factor
        for _ in range(40):
            if abs(precio(nueva, prod) - quiero) <= 2:
                return
            tp.conector()
            time.sleep(1)
        raise AssertionError((prod, factor, precio(lista, prod), precio(nueva, prod)))

    for datos in (
        {"accion": "regla", "tipo": "rubro", "ref": rubro, "descuento": "10"},
        {"accion": "regla", "tipo": "producto", "ref": en_rubro[0], "descuento": "20"},
    ):
        e, loc = post(op, "/api/admin/lista", {"id": lid, **datos})
        assert "ok=cambio" in loc, loc
    muy_alto = {"id": lid, "accion": "regla", "tipo": "rubro", "ref": rubro, "descuento": "90"}
    e, loc = post(op, "/api/admin/lista", muy_alto)
    assert "e=datos" in loc, loc
    esperar_precio(en_rubro[0], 0.80)
    esperar_precio(en_rubro[1], 0.90)
    esperar_precio(fuera, 0.95)
    assert esperar(f"SELECT 1 AS listo FROM listas_nuevas WHERE id = '{lid}' AND pendiente = 0", "listo")
    e, html, _ = get(op, f"/admin/listas/{nueva}")
    assert e == 200 and "Condiciones" in html and "Pasar clientes a esta lista" in html, e
    post(op, "/api/admin/lista", {"id": lid, "accion": "quitar", "tipo": "rubro", "ref": rubro})
    esperar_precio(en_rubro[1], 0.95)
    esperar_precio(en_rubro[0], 0.80)
    # Pasar el cliente aprobado a esta lista: cambia en la tienda y en su contacto de Odoo
    e, loc = post(op, "/api/admin/lista", {"accion": "clientes", "lista": nueva, "cliente": cid})
    assert "ok=clientes" in loc, loc
    for _ in range(40):
        tp.conector()
        campos = ["property_product_pricelist"]
        socio = tp.c.search_read("res.partner", [("id", "=", socio["id"])], campos)[0]
        if socio["property_product_pricelist"][0] == nueva:
            break
        time.sleep(1)
    assert socio["property_product_pricelist"][0] == nueva, socio
    print("3b. Descuentos por rubro y por producto (gana el del producto), quitar y pasar un cliente ✓")

    e, loc = post(
        op,
        "/api/admin/equipo",
        {"accion": "alta", "nombre": "Vende e2e", "email": VENDE, "roles": "mayoristas"},
    )
    assert "ok=alta" in loc, loc
    _, v = entrar(VENDE)
    assert get(v, "/admin/mayoristas")[0] == 200
    e, _, loc = get(v, "/admin/equipo")
    assert e in (302, 303) and loc.endswith("/admin"), (e, loc)
    assert (
        post(v, "/api/admin/equipo", {"accion": "alta", "nombre": "X", "email": f"x{N}@example.com"})[0]
        == 403
    )
    yo = hashlib.md5(ADMIN.encode()).hexdigest()
    e, loc = post(op, "/api/admin/equipo", {"accion": "roles", "id": yo, "roles": "mayoristas"})
    assert "e=yo" in loc, loc
    assert (
        post(op, "/api/admin/mayorista", {"id": cid, "accion": "baja"}, origen="https://otro.example")[0]
        == 403
    )
    print("4. Equipo con permisos: «Mayoristas» no entra a Equipo; nadie se saca su admin; otro origen no ✓")

    d1(
        f"UPDATE equipo SET activo = 0 WHERE email IN ('{ADMIN}', '{VENDE}'); "
        "DELETE FROM sesiones_equipo WHERE miembro_id IN "
        f"(SELECT id FROM equipo WHERE email IN ('{ADMIN}', '{VENDE}')); "
        f"UPDATE clientes SET mayorista = 'rechazado' WHERE id = '{cid}'"
    )
    print("Administración de la tienda: todo bien ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
