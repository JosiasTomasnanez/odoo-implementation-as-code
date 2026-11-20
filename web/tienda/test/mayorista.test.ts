// Pruebas del sitio mayorista (ADR 0035): sitio por dominio, cantidades (mínimo y bulto), Excel y lote.
// Correr: npm test (node --test, Node 22).
import { test } from "node:test";
import assert from "node:assert/strict";
import { cantidadValida, comoSeVende, conLista, primeraValida, consultaFts, opcionesDe, type Vista } from "../src/servidor/consultas.ts";
import { rutaMayorista, sitioDe } from "../src/servidor/sitio.ts";
import { libro, col } from "../src/servidor/xlsx.ts";
import { Producto } from "../src/servidor/esquemas.ts";

test("sitio: por dominio", () => {
  assert.equal(sitioDe(new URL("https://mayoristas.comercio-ejemplo.example/")), "mayorista");
  assert.equal(sitioDe(new URL("https://mayoristas-demo.comercio-ejemplo.example/x")), "mayorista");
  assert.equal(sitioDe(new URL("https://comercio-ejemplo.example/")), "tienda");
  assert.equal(sitioDe(new URL("https://demo.comercio-ejemplo.example/")), "tienda");
  assert.equal(sitioDe(new URL("https://mayoristasfalso.com/")), "tienda");
});

test("sitio mayorista: rutas", () => {
  assert.equal(rutaMayorista("/"), "/mayoristas/");
  assert.equal(rutaMayorista("/carrito"), "/mayoristas/carrito");
  assert.equal(rutaMayorista("/pedidos"), "/cuenta/pedidos");
  assert.equal(rutaMayorista("/producto/x"), "/mayoristas/producto/x"); // no existe: 404
  assert.equal(rutaMayorista("/cuenta/pedidos"), null);
  assert.equal(rutaMayorista("/api/pedido"), null);
  assert.equal(rutaMayorista("/pedido/abc"), null);
  assert.equal(rutaMayorista("/mayoristas/"), null);
});

test("cantidades mayoristas: mínimo y bultos enteros", () => {
  const suelto = { minimo: 1, bulto: null };
  assert.equal(primeraValida(suelto), 1);
  assert.ok(cantidadValida(3, suelto));
  const caja = { minimo: 1, bulto: 12 };
  assert.equal(primeraValida(caja), 12);
  assert.ok(cantidadValida(24, caja));
  assert.ok(!cantidadValida(1, caja));
  assert.ok(!cantidadValida(18, caja));
  const desde = { minimo: 30, bulto: 12 };
  assert.equal(primeraValida(desde), 36); // 30 redondeado a cajas de 12
  assert.ok(!cantidadValida(24, desde));
  assert.ok(cantidadValida(48, desde));
  assert.ok(!cantidadValida(2.5, { minimo: 1, bulto: null }));
  assert.equal(comoSeVende(caja), "bulto × 12");
  assert.equal(comoSeVende(desde), "desde 36 (bultos × 12)");
  assert.equal(comoSeVende({ minimo: 10, bulto: null }), "desde 10 u.");
});

test("listados: filtro, orden y página validados", () => {
  const o = opcionesDe(new URL("https://x/?filtro=stock&orden=menor&pagina=3"));
  assert.deepEqual(o, { filtro: "stock", orden: "menor", pagina: 3 });
  assert.deepEqual(opcionesDe(new URL("https://x/?filtro=x;drop&orden=1&pagina=-2")), { filtro: "todos", orden: "rel", pagina: 1 });
  // Nombres heredados de los objetos (antes daban 500 con «in»)
  for (const raro of ["toString", "constructor", "valueOf", "__proto__", "hasOwnProperty"]) {
    assert.deepEqual(opcionesDe(new URL(`https://x/?filtro=${raro}&orden=${raro}`)), { filtro: "todos", orden: "rel", pagina: 1 });
  }
  assert.equal(opcionesDe(new URL("https://x/?pagina=1.5")).pagina, 1);
  assert.equal(consultaFts('tornillo "OR 1'), '"tornillo"* AND "or"* AND "1"*');
});

test("excel: zip válido, celdas y caracteres raros escapados", () => {
  assert.equal(col(0), "A"); assert.equal(col(25), "Z"); assert.equal(col(26), "AA");
  const x = libro([{ nombre: "Hoja", anchos: [10], filas: [[{ t: "s", v: 'a<b & "c"\u0001' }], [{ t: "n", v: 1.5 }]], filtro: "A1:A2" }], "<styleSheet/>", "t");
  assert.equal(String.fromCharCode(x[0], x[1]), "PK");
  const texto = new TextDecoder().decode(x);
  // escapado y sin el carácter de control (que XML no admite) dentro de la celda
  assert.ok(texto.includes('a&lt;b &amp; &quot;c&quot;</t>'));
  assert.ok(texto.includes("'Hoja'!$A$1:$A$2"));
});

test("lote: producto con bulto y precio con mínimo (y sin ellos, módulo anterior)", () => {
  const base = { id: 1, publicado: true, nombre: "X", codigo: null, referencia: null, categoria_id: null, unidad: "Unidades",
    descripcion: null, consultar: false, nuevo_hasta: null, dias_encargo: null, imagen: null, margen: 0, stock_libre: 3 };
  const precio = { lista_id: 2, precio: 100, precio_anterior: null, oferta_hasta: null };
  assert.ok(Producto.safeParse({ ...base, precios: [precio] }).success);
  assert.ok(Producto.safeParse({ ...base, bulto: 12, precios: [{ ...precio, minimo: 24 }] }).success);
  assert.ok(Producto.safeParse({ ...base, bulto: null, precios: [precio] }).success);
  assert.ok(!Producto.safeParse({ ...base, bulto: 1, precios: [precio] }).success);
  assert.ok(!Producto.safeParse({ ...base, precios: [{ ...precio, minimo: 0 }] }).success);
});

test("mayorista: «disponible» solo si el stock alcanza para el mínimo en bultos enteros", () => {
  const base = { id: 1, precio: 1000, precio_anterior: null, oferta_hasta: null, disponible: true, bulto: 12, libre: 5 } as unknown as Vista;
  const lista = new Map([[1, { precio: 900, minimo: 1 }]]);
  assert.equal(conLista(base, lista).disponible, false);                       // 5 < un bulto de 12
  assert.equal(conLista({ ...base, libre: 12 }, lista).disponible, true);
  assert.equal(conLista({ ...base, libre: 20 }, new Map([[1, { precio: 900, minimo: 24 }]])).disponible, false); // desde 24
  assert.equal(conLista({ ...base, libre: null }, lista).disponible, true);   // no controla stock
  assert.equal(conLista({ ...base, disponible: false, libre: 0 }, lista).disponible, false);
  assert.equal(conLista({ ...base, bulto: null, libre: 1 }, lista).disponible, true); // por unidad
});
