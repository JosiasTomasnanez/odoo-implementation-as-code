// Pruebas de las contraseñas (PBKDF2) y de la pantalla de pago compartida por los dos sitios.
import { test } from "node:test";
import assert from "node:assert/strict";
import { claveAceptable, claveCorrecta, hashClave } from "../src/servidor/claves.ts";
import { rutaMayorista } from "../src/servidor/sitio.ts";

test("contraseña: se guarda con sal y se comprueba", async () => {
  const h1 = await hashClave("Ferreteria2026"), h2 = await hashClave("Ferreteria2026");
  assert.match(h1, /^pbkdf2\$100000\$[0-9a-f]{32}\$[0-9a-f]{64}$/);
  assert.notEqual(h1, h2); // sal distinta
  assert.equal(await claveCorrecta("Ferreteria2026", h1), true);
  assert.equal(await claveCorrecta("ferreteria2026", h1), false);
  assert.equal(await claveCorrecta("x", null), false);
  assert.equal(await claveCorrecta("x", "basura"), false);
});

test("contraseña: reglas mínimas", () => {
  assert.ok(claveAceptable("corta"));
  assert.ok(claveAceptable("12345678"));
  assert.ok(claveAceptable("aaaaaaaaaa"));
  assert.ok(claveAceptable("ana@x.com", "ana@x.com"));
  assert.equal(claveAceptable("Tornillo de 8 mm"), null);
});

test("/compra es la misma página en el sitio mayorista", () => {
  assert.equal(rutaMayorista("/compra"), null);
  assert.equal(rutaMayorista("/carrito"), "/mayoristas/carrito");
  // Legales y arrepentimiento: las mismas páginas en los dos sitios
  assert.equal(rutaMayorista("/legales/terminos/"), null);
  assert.equal(rutaMayorista("/arrepentimiento/"), null);
  assert.equal(rutaMayorista("/robots.txt"), null); // cada sitio arma el suyo (el mayorista: Disallow /)
  assert.equal(rutaMayorista("/admin"), "/mayoristas/admin"); // la administración no existe en el sitio mayorista
});
