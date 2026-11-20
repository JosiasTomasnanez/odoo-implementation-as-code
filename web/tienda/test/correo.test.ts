// Envío de mails por el primer proveedor que lo acepte (P-067). Correr: npm test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { enviar, proveedores, remitente } from "../src/servidor/correo.ts";

const M = { para: "cliente@comercio-ejemplo.example", asunto: "Hola", html: "<p>Hola</p>", texto: "Hola", idem: "p1-Hola" };

/** Reemplaza fetch por respuestas fijas según el dominio y anota lo pedido. */
function conFetch(estados: Record<string, number | Error>) {
  const pedidos: { url: string; cuerpo: Record<string, unknown>; cabeceras: Record<string, string> }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url: string, init: RequestInit) => {
    pedidos.push({ url, cuerpo: JSON.parse(String(init.body)), cabeceras: init.headers as Record<string, string> });
    const e = estados[new URL(url).hostname];
    if (e instanceof Error) throw e;
    return new Response("{}", { status: e });
  }) as typeof fetch;
  return { pedidos, volver: () => { globalThis.fetch = original; } };
}

test("correo: el remitente se separa en nombre y mail", () => {
  assert.deepEqual(remitente("Comercio Ejemplo <pedidos@comercio-ejemplo.example>"), { name: "Comercio Ejemplo", email: "pedidos@comercio-ejemplo.example" });
  assert.deepEqual(remitente("pedidos@comercio-ejemplo.example"), { email: "pedidos@comercio-ejemplo.example" });
});

test("correo: solo cuentan los proveedores configurados, en orden", () => {
  assert.deepEqual(proveedores({}), []);
  assert.deepEqual(proveedores({ RESEND_API_KEY: "r" }), ["resend"]);
  assert.deepEqual(proveedores({ RESEND_API_KEY: "r", BREVO_API_KEY: "b" }), ["brevo", "resend"]);
  assert.deepEqual(proveedores({ RESEND_API_KEY: "r", BREVO_API_KEY: "b", MAIL_ORDEN: "resend, brevo, otro" }), ["resend", "brevo"]);
});

test("correo: sale por Brevo y no toca Resend", async () => {
  const f = conFetch({ "api.brevo.com": 201 });
  try {
    const r = await enviar({ RESEND_API_KEY: "r", BREVO_API_KEY: "b" }, M);
    assert.deepEqual([r.ok, r.por], [true, "brevo"]);
    assert.equal(f.pedidos.length, 1);
    assert.equal(f.pedidos[0].cabeceras["api-key"], "b");
    assert.deepEqual(f.pedidos[0].cuerpo.to, [{ email: M.para }]);
    assert.deepEqual(f.pedidos[0].cuerpo.sender, { name: "Comercio Ejemplo", email: "pedidos@comercio-ejemplo.example" });
  } finally { f.volver(); }
});

test("correo: si Brevo rechaza (cupo) o se cae, sale por Resend", async () => {
  for (const falla of [429, new Error("red")]) {
    const f = conFetch({ "api.brevo.com": falla, "api.resend.com": 200 });
    try {
      const r = await enviar({ RESEND_API_KEY: "r", BREVO_API_KEY: "b" }, M);
      assert.deepEqual([r.ok, r.por], [true, "resend"]);
      assert.match(r.detalle, /antes: brevo/);
      assert.equal(f.pedidos[1].cabeceras["Idempotency-Key"], "p1-Hola");
    } finally { f.volver(); }
  }
});

test("correo: si todos fallan, lo dice; sin proveedor, también", async () => {
  const f = conFetch({ "api.brevo.com": 429, "api.resend.com": 429 });
  try {
    const r = await enviar({ RESEND_API_KEY: "r", BREVO_API_KEY: "b" }, M);
    assert.equal(r.ok, false);
    assert.equal(r.detalle, "brevo HTTP 429, resend HTTP 429");
    assert.equal((await enviar({}, M)).ok, false);
  } finally { f.volver(); }
});

test("correo: con el servicio de Cloudflare configurado, va primero", async () => {
  const enviados: unknown[] = [];
  const CORREO = { send: async (m: unknown) => { enviados.push(m); return { messageId: "x" }; } } as unknown as SendEmail;
  const f = conFetch({});
  try {
    const r = await enviar({ CORREO, BREVO_API_KEY: "b" }, M);
    assert.equal(r.por, "cloudflare");
    assert.equal(f.pedidos.length, 0);
    assert.equal((enviados[0] as { to: string }).to, M.para);
  } finally { f.volver(); }
});

import { diaAr, tarjetaResumen } from "../src/servidor/resumen-mails.ts";

test("resumen de mails: día de Argentina y tarjeta de Discord", () => {
  assert.equal(diaAr(Date.UTC(2026, 10, 11, 2, 0)), "2026-11-10");
  assert.equal(tarjetaResumen("2026-11-10", []), null);
  const t = tarjetaResumen("2026-11-10", [{ proveedor: "brevo", cantidad: 40 }, { proveedor: "resend", cantidad: 2 }, { proveedor: "fallidos", cantidad: 1 }])!.embeds[0];
  assert.equal(t.title, "⚠️ Mails de la tienda: 42 enviados");
  assert.match(t.description, /brevo {5}40 {3}cupo: 300 por día/);
  assert.match(t.description, /ningún proveedor: 1/);
  assert.equal(t.footer.text, "tienda online · 10/11/2026");
  assert.equal(tarjetaResumen("2026-11-10", [{ proveedor: "brevo", cantidad: 1 }])!.embeds[0].title, "ℹ️ Mails de la tienda: 1 enviado");
});

import { irDespues, rutaSegura } from "../src/servidor/volver.ts";

test("volver después de ingresar: solo rutas propias", () => {
  for (const v of ["/carrito/", "/producto/tornillo-6x1/", "/buscar/?q=pinza&pagina=2", "/cuenta/pedidos", "/compra"]) assert.equal(rutaSegura(v), v);
  for (const v of ["", null, "//otro.com", "/\\otro.com", "https://otro.com", "/cuenta", "/cuenta/?modo=crear", "/api/cuenta/salir", "/admin", "/a b", "/" + "x".repeat(200)]) assert.equal(rutaSegura(v), null, String(v));
});

test("volver después de ingresar: la tienda vuelve a donde estaba; el mayorista, a su lista", () => {
  const url = new URL("https://demo.comercio-ejemplo.example/api/cuenta/entrar");
  const con = (cookie: string) => new Request(url, { headers: { cookie } });
  const r = irDespues(con("cf_volver=%2Fcarrito%2F; otra=1"), url, "tienda", "cf_cliente=x");
  assert.equal(r.headers.get("Location"), "https://demo.comercio-ejemplo.example/carrito/");
  assert.deepEqual(r.headers.getSetCookie().map((c) => c.split(";")[0]), ["cf_cliente=x", "cf_volver="]);
  assert.equal(irDespues(con(""), url, "tienda", "c=x").headers.get("Location"), "https://demo.comercio-ejemplo.example/");
  assert.equal(irDespues(con("cf_volver=%2F%2Fotro.com"), url, "tienda", "c=x").headers.get("Location"), "https://demo.comercio-ejemplo.example/");
  assert.equal(irDespues(con("cf_volver=%2Fcarrito%2F"), url, "mayorista", "c=x").headers.get("Location"), "https://demo.comercio-ejemplo.example/");
});

import { diferencias } from "../src/servidor/cambios.ts";

test("cambios de datos: solo lo que cambia de verdad", () => {
  assert.deepEqual(diferencias({ telefono: "351 1", contacto: "Ana", direccion: null }, { telefono: "351 2", contacto: "Ana", direccion: "" }),
    [{ campo: "telefono", antes: "351 1", despues: "351 2" }]);
  assert.deepEqual(diferencias({ nombre: null }, { nombre: "Ana" }), [{ campo: "nombre", antes: null, despues: "Ana" }]);
});
