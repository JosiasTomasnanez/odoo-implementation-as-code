// Pruebas de lo que recibe la tienda del conector: firma, validación y detección de imágenes.
// Correr: npm test (node --test, Node 22).
import { test } from "node:test";
import assert from "node:assert/strict";
import { firmaValida, mensajeAFirmar, sha256Hex } from "../src/servidor/firma.ts";
import { Lote } from "../src/servidor/esquemas.ts";
import { slugify, tipoImagen } from "../src/servidor/catalogo.ts";

const SECRETO = "x".repeat(48);
const enc = new TextEncoder();

async function firmar(fecha: string, metodo: string, ruta: string, cuerpo: Uint8Array<ArrayBuffer>) {
  const clave = await crypto.subtle.importKey("raw", enc.encode(SECRETO), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const f = await crypto.subtle.sign("HMAC", clave, enc.encode(mensajeAFirmar(fecha, metodo, ruta, await sha256Hex(cuerpo))));
  return [...new Uint8Array(f)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

test("firma: válida, vieja, alterada, otra ruta, clave corta", async () => {
  const cuerpo = enc.encode('{"numero":1}');
  const ahora = Date.now();
  const fecha = String(Math.floor(ahora / 1000));
  const firma = await firmar(fecha, "POST", "/api/conector/lote", cuerpo);
  assert.equal(await firmaValida(SECRETO, fecha, firma, "POST", "/api/conector/lote", cuerpo.buffer, ahora), true);
  assert.equal(await firmaValida(SECRETO, fecha, firma, "POST", "/api/conector/lote", cuerpo.buffer, ahora + 301_000), false, "vieja");
  assert.equal(await firmaValida(SECRETO, fecha, firma, "POST", "/api/conector/lote", enc.encode('{"numero":2}').buffer, ahora), false, "cuerpo alterado");
  assert.equal(await firmaValida(SECRETO, fecha, firma, "PUT", "/api/conector/lote", cuerpo.buffer, ahora), false, "otro método");
  assert.equal(await firmaValida(SECRETO, fecha, firma, "POST", "/api/otra", cuerpo.buffer, ahora), false, "otra ruta");
  assert.equal(await firmaValida("corta", fecha, firma, "POST", "/api/conector/lote", cuerpo.buffer, ahora), false, "clave corta");
  assert.equal(await firmaValida(SECRETO, fecha, "zz" + firma.slice(2), "POST", "/api/conector/lote", cuerpo.buffer, ahora), false, "firma no hex");
  assert.equal(await firmaValida(SECRETO, null, firma, "POST", "/api/conector/lote", cuerpo.buffer, ahora), false, "sin fecha");
});

const producto = {
  id: 1, publicado: true, nombre: "Cinta", codigo: null, referencia: null, categoria_id: null, unidad: "Unidades",
  descripcion: null, consultar: false, nuevo_hasta: null, dias_encargo: null, imagen: null, margen: 1, stock_libre: 3,
  precios: [{ lista_id: 1, precio: 245000, precio_anterior: null, oferta_hasta: null }],
};
const lote = { numero: 7, productos: [producto], productos_borrados: [], categorias: [], categorias_borradas: [], listas: [] };

test("lote: válido y rechazos estrictos", () => {
  assert.equal(Lote.safeParse(lote).success, true);
  assert.equal(Lote.safeParse({ ...lote, extra: 1 }).success, false, "campo de más");
  assert.equal(Lote.safeParse({ ...lote, productos: [{ ...producto, id: "1; DROP TABLE productos" }] }).success, false, "id texto");
  assert.equal(Lote.safeParse({ ...lote, productos: [{ ...producto, precios: [{ ...producto.precios[0], precio: -5 }] }] }).success, false, "precio negativo");
  assert.equal(Lote.safeParse({ ...lote, productos: [{ ...producto, nombre: "a".repeat(301) }] }).success, false, "nombre largo");
  assert.equal(Lote.safeParse({ ...lote, productos: [{ ...producto, imagen: "../../etc/passwd" }] }).success, false, "clave de imagen");
});

test("imagen por sus bytes, no por lo que dicen", () => {
  assert.equal(tipoImagen(new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0])), "image/jpeg");
  assert.equal(tipoImagen(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0])), "image/png");
  assert.equal(tipoImagen(enc.encode("<svg onload=alert(1)>")), null);
});

test("slug sin acentos ni símbolos", () => {
  assert.equal(slugify("Llave de paso ½\" BRONCE"), "llave-de-paso-bronce");
  assert.equal(slugify("¡¡!!"), "producto");
});

import { consultaFts } from "../src/servidor/consultas.ts";
test("búsqueda: solo palabras entre comillas, sin sintaxis de FTS", () => {
  assert.equal(consultaFts("Llave de paso ½\" BRONCE"), '"llave"* AND "paso"* AND "bronce"*');
  assert.equal(consultaFts('" OR * NEAR(a b) -x ^y'), '"or"* AND "near"* AND "b"*');
  assert.equal(consultaFts("ñandú"), '"nandu"*'); // igual que el índice (remove_diacritics)
  assert.equal(consultaFts("  ***  "), null);
});

test("búsqueda tolerante: plurales, palabras vacías, sinónimos, tipeo y cualquiera", () => {
  assert.equal(consultaFts("tornillos"), '"tornillo"*');
  assert.equal(consultaFts("llaves"), '"llav"*');
  assert.equal(consultaFts("alimento para perros"), '("alimento"* OR "comida"* OR "balanceado"*) AND ("perro"* OR "canino"*)');
  assert.equal(consultaFts("pintura"), '("pintura"* OR "latex"* OR "esmalte"* OR "pintur"*)');
  assert.equal(consultaFts("8 x 1/2"), '"8"* AND "1"* AND "2"*');
  assert.equal(consultaFts("de"), '"de"*'); // si todo es «vacío», se busca igual
  assert.equal(consultaFts("tornilo", "corto"), '"torni"*');
  assert.equal(consultaFts("tornilo 3", "corto"), '"torni"* AND "3"*');
  assert.equal(consultaFts("candado bronce", "o"), '"candado"* OR "bronce"*');
});

import { hashPin, iguales } from "../src/servidor/panel.ts";
import { firmaMercadoPagoValida } from "../src/servidor/pagos.ts";
test("PIN: el hash depende de la clave secreta y del empleado", async () => {
  const a = await hashPin("p".repeat(32), 7, "1234");
  assert.equal(a.length, 64);
  assert.notEqual(a, await hashPin("q".repeat(32), 7, "1234"), "otra clave");
  assert.notEqual(a, await hashPin("p".repeat(32), 8, "1234"), "otro empleado con el mismo PIN");
  assert.equal(iguales(a, await hashPin("p".repeat(32), 7, "1234")), true);
});

test("aviso de Mercado Pago: firma válida, vieja o alterada", async () => {
  const secreto = "s".repeat(40), ts = String(Date.now()), reqId = "abc-123", dataId = "123456789";
  const k = await crypto.subtle.importKey("raw", enc.encode(secreto), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const v1 = [...new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(`id:${dataId};request-id:${reqId};ts:${ts};`)))].map((b) => b.toString(16).padStart(2, "0")).join("");
  assert.equal(await firmaMercadoPagoValida(secreto, `ts=${ts},v1=${v1}`, reqId, dataId), true);
  assert.equal(await firmaMercadoPagoValida(secreto, `ts=${ts},v1=${v1}`, reqId, "999"), false, "otro pago");
  assert.equal(await firmaMercadoPagoValida(secreto, `ts=${ts},v1=${v1}`, reqId, dataId, Date.now() + 20 * 60_000), false, "vieja");
  assert.equal(await firmaMercadoPagoValida("", `ts=${ts},v1=${v1}`, reqId, dataId), false, "sin clave");
});

import { esDePrueba } from "../src/servidor/mails.ts";
import { cuitValido } from "../src/servidor/clientes.ts";
test("mails: nunca a direcciones de prueba", () => {
  assert.equal(esDePrueba("prueba@example.com"), true);
  assert.equal(esDePrueba("x@sub.example.org"), true);
  assert.equal(esDePrueba("a@b.test"), true);
  assert.equal(esDePrueba("implementador@gmail.com"), false);
  assert.equal(esDePrueba("alguien@example.com.ar"), false);
});
test("CUIT: dígito verificador", () => {
  assert.equal(cuitValido("20-12345678-6"), true);
  assert.equal(cuitValido("20123456780"), false);
  assert.equal(cuitValido("12345"), false);
  // De persona (20, 23, 24, 27) y de empresa (30, 33, 34), con el mismo dígito verificador
  assert.equal(cuitValido("27-12345678-0"), true);
  assert.equal(cuitValido("30-12345678-1"), true);
  assert.equal(cuitValido("30-12345678-2"), false);
});
