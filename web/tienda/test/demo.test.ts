// Lo de prueba (pago simulado, claves de prueba de Turnstile) solo anda en la demo o local.
import { test } from "node:test";
import assert from "node:assert/strict";
import { modo } from "../src/servidor/pagos.ts";
import { claveDePrueba, esDemo } from "../src/servidor/protecciones.ts";

const env = (vars: Record<string, string>) => vars as unknown as Env;

test("demo: se reconoce por ORIGEN", () => {
  assert.equal(esDemo(env({ ORIGEN: "https://demo.comercio-ejemplo.example" })), true);
  assert.equal(esDemo(env({ ORIGEN: "https://mayoristas-demo.comercio-ejemplo.example" })), true);
  assert.equal(esDemo(env({ ORIGEN: "http://localhost:4321" })), true);
  assert.equal(esDemo(env({ ORIGEN: "https://comercio-ejemplo.example" })), false);
  assert.equal(esDemo(env({ ORIGEN: "https://www.comercio-ejemplo.example" })), false);
  assert.equal(esDemo(env({ ORIGEN: "https://comercio-ejemplo.example.demo.evil.com" })), false);
  assert.equal(esDemo(env({})), false);
});

test("pago simulado: solo en la demo; en producción queda sin configurar", () => {
  assert.equal(modo(env({ PAGOS_MODO: "simulado", ORIGEN: "https://demo.comercio-ejemplo.example" })), "simulado");
  assert.equal(modo(env({ PAGOS_MODO: "simulado", ORIGEN: "https://comercio-ejemplo.example" })), null);
  assert.equal(modo(env({ PAGOS_MODO: "simulado" })), null);
  assert.equal(modo(env({ PAGOS_MODO: "mercadopago", ORIGEN: "https://comercio-ejemplo.example" })), "mercadopago");
});

test("Turnstile: se reconocen las claves de prueba de Cloudflare", () => {
  assert.equal(claveDePrueba("1x0000000000000000000000000000000AA"), true);
  assert.equal(claveDePrueba("2x0000000000000000000000000000000AA"), true);
  assert.equal(claveDePrueba("0x4AAAAAAABkMYinukE8nzYS"), false);
  assert.equal(claveDePrueba(undefined), false);
});
