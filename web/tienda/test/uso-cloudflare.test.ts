// Reporte de uso de Cloudflare contra el plan gratis (P-066). Correr: npm test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { nivelDe, resumir, tarjetaUso, type Datos } from "../src/servidor/uso-cloudflare.ts";

// Forma real de la respuesta de la API (17/11, demo)
const DEMO: Datos = {
  workersInvocationsAdaptive: [
    { sum: { requests: 9527 }, quantiles: { cpuTimeP99: 13243 }, dimensions: { scriptName: "comercio-ejemplo-tienda-demo", status: "success" } },
    { sum: { requests: 263 }, quantiles: { cpuTimeP99: 22678 }, dimensions: { scriptName: "comercio-ejemplo-tienda-demo", status: "clientDisconnected" } },
  ],
  d1AnalyticsAdaptiveGroups: [{ sum: { rowsRead: 454515, rowsWritten: 1530 } }],
  durableObjectsInvocationsAdaptiveGroups: [{ sum: { requests: 1438 } }],
  kvOperationsAdaptiveGroups: [],
  r2OperationsAdaptiveGroups: [
    { sum: { requests: 57 }, dimensions: { actionType: "PutObject" } },
    { sum: { requests: 72 }, dimensions: { actionType: "ListObjects" } },
    { sum: { requests: 56 }, dimensions: { actionType: "DeleteObject" } },
    { sum: { requests: 36 }, dimensions: { actionType: "GetObject" } },
  ],
  r2StorageAdaptiveGroups: [
    { max: { payloadSize: 644054 }, dimensions: { bucketName: "comercio-ejemplo-tienda-demo" } },
    { max: { payloadSize: 81226498 }, dimensions: { bucketName: "comercio-ejemplo-backups" } },
  ],
};
const de = (r: ReturnType<typeof resumir>, nombre: string) => r.medidas.find((m) => m.nombre.startsWith(nombre))!;

test("uso: niveles por proporción del cupo", () => {
  assert.equal(nivelDe(0.1), "ok");
  assert.equal(nivelDe(0.5), "atencion");
  assert.equal(nivelDe(0.79), "atencion");
  assert.equal(nivelDe(0.8), "pasar");
});

test("uso: suma la cuenta, R2 por clase (borrar no cuenta) y CPU de los que terminaron bien", () => {
  const r = resumir("2026-11-17", DEMO);
  assert.equal(de(r, "Pedidos").usado, 9790);
  assert.equal(de(r, "CPU").usado, 13.243);          // no el 22,7 de los cortados por el cliente
  assert.equal(de(r, "CPU").nivel, "atencion");      // p99 sobre 10 ms, pero nada cortado
  assert.equal(de(r, "D1: filas leídas").usado, 454515);
  assert.equal(de(r, "R2: escrituras").usado, 129);  // Put + List
  assert.equal(de(r, "R2: lecturas").usado, 36);
  assert.equal(de(r, "R2: guardado").usado, 644054 + 81226498);
  assert.equal(r.nivel, "atencion");
  assert.deepEqual(r.avisos, ["CPU por pedido (p99): 13.2 ms de 10 ms"]);
});

test("uso: pedidos cortados por CPU o un cupo al 80 % piden pasar al plan pago", () => {
  const cortados = resumir("2026-11-17", { ...DEMO, workersInvocationsAdaptive: [
    ...DEMO.workersInvocationsAdaptive!,
    { sum: { requests: 3 }, quantiles: { cpuTimeP99: 11000 }, dimensions: { scriptName: "x", status: "exceededCpu" } },
  ] });
  assert.equal(cortados.nivel, "pasar");
  assert.match(de(cortados, "CPU").nota!, /3 pedidos cortados/);
  const lleno = resumir("2026-11-17", { d1AnalyticsAdaptiveGroups: [{ sum: { rowsRead: 4_100_000, rowsWritten: 0 } }] });
  assert.equal(lleno.nivel, "pasar");
  const vacio = resumir("2026-11-17", {});
  assert.equal(vacio.nivel, "ok");
});

test("uso: la tarjeta dice qué hacer según el nivel", () => {
  const ok = tarjetaUso(resumir("2026-11-17", {})).embeds[0];
  assert.match(ok.title, /dentro del plan gratis/);
  assert.match(ok.footer.text, /17\/11\/2026/);
  const pasar = tarjetaUso(resumir("2026-11-17", { d1AnalyticsAdaptiveGroups: [{ sum: { rowsRead: 0, rowsWritten: 95_000 } }] })).embeds[0];
  assert.match(pasar.title, /pasar al plan pago/);
  assert.match(pasar.description, /Workers Paid/);
  assert.match(pasar.description, /!! D1: filas escritas/);
});
