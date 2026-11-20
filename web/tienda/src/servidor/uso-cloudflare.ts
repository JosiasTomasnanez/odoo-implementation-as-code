// Uso de Cloudflare contra el plan gratis (P-066): una tarjeta por día en Discord para saber a tiempo
// cuándo pasar al plan pago (Workers Paid). Los cupos son de TODA la cuenta (tienda, demo, página
// «Próximamente», backups en R2), así que se suma todo lo de la cuenta.
//
// Datos: API de analíticas de Cloudflare (GraphQL). Hace falta un token con «Account Analytics:
// Read» (secreto CF_ANALYTICS_TOKEN) y el ID de la cuenta (CF_ACCOUNT_ID). Lo manda un solo Worker:
// el que tenga REPORTE_USO = "1" (hoy la demo; con la tienda de producción, esa).
//
// Cupos del plan gratis según la documentación de Cloudflare (revisados el 18/11/2026). Los diarios se
// reinician a las 00:00 UTC (21:00 de Argentina); los de R2 son por mes.

export const CUPOS = {
  pedidos: 100_000,          // Workers: pedidos por día (si se pasa: error 1027)
  cpuMs: 10,                 // Workers: CPU por pedido o por cron (si se pasa: error 1102)
  d1Leidas: 5_000_000,       // D1: filas leídas por día (si se pasa: D1 rechaza el resto del día)
  d1Escritas: 100_000,       // D1: filas escritas por día
  doPedidos: 100_000,        // Durable Objects: pedidos por día
  kvLecturas: 100_000,       // KV: lecturas por día
  kvEscrituras: 1_000,       // KV: escrituras, borrados y listados por día (cada uno)
  r2Bytes: 10 * 1024 ** 3,   // R2: 10 GB guardados
  r2ClaseA: 1_000_000,       // R2: escrituras y listados por mes
  r2ClaseB: 10_000_000,      // R2: lecturas por mes
};

// Acciones de R2 por clase (las de borrar son gratis)
const R2_CLASE_A = new Set(["ListBuckets", "PutBucket", "ListObjects", "PutObject", "CopyObject",
  "CompleteMultipartUpload", "CreateMultipartUpload", "LifecycleStorageTierTransition", "ListMultipartUploads",
  "UploadPart", "UploadPartCopy", "ListParts", "PutBucketEncryption", "PutBucketCors", "PutBucketLifecycleConfiguration"]);
const R2_CLASE_B = new Set(["HeadBucket", "HeadObject", "GetObject", "UsageSummary", "GetBucketEncryption",
  "GetBucketLocation", "GetBucketCors", "GetBucketLifecycleConfiguration"]);

/** Nivel de un uso: «ok» hasta el 50 %, «atención» hasta el 80 %, «pasar» desde ahí. */
export type Nivel = "ok" | "atencion" | "pasar";
const NIVEL_ORDEN: Nivel[] = ["ok", "atencion", "pasar"];
export const nivelDe = (proporcion: number): Nivel => (proporcion >= 0.8 ? "pasar" : proporcion >= 0.5 ? "atencion" : "ok");
const peor = (niveles: Nivel[]) => niveles.reduce((a, b) => (NIVEL_ORDEN.indexOf(b) > NIVEL_ORDEN.indexOf(a) ? b : a), "ok" as Nivel);

const CONSULTA = `query($cuenta: String!, $dia: Date!, $desde: Time!, $hasta: Time!, $mes: Time!) {
  viewer { accounts(filter: {accountTag: $cuenta}) {
    workersInvocationsAdaptive(limit: 200, filter: {date: $dia}) {
      sum { requests } quantiles { cpuTimeP99 } dimensions { scriptName status } }
    d1AnalyticsAdaptiveGroups(limit: 50, filter: {date: $dia}) { sum { rowsRead rowsWritten } }
    durableObjectsInvocationsAdaptiveGroups(limit: 50, filter: {date: $dia}) { sum { requests } }
    kvOperationsAdaptiveGroups(limit: 50, filter: {date: $dia}) { sum { requests } dimensions { actionType } }
    r2OperationsAdaptiveGroups(limit: 200, filter: {datetime_geq: $mes, datetime_lt: $hasta}) { sum { requests } dimensions { actionType } }
    r2StorageAdaptiveGroups(limit: 50, filter: {datetime_geq: $desde, datetime_lt: $hasta}) { max { payloadSize } dimensions { bucketName } }
  } } }`;

type Fila<S, D = Record<string, string>> = { sum?: S; max?: S; quantiles?: { cpuTimeP99?: number }; dimensions?: D };
export type Datos = {
  workersInvocationsAdaptive?: Fila<{ requests: number }, { scriptName: string; status: string }>[];
  d1AnalyticsAdaptiveGroups?: Fila<{ rowsRead: number; rowsWritten: number }>[];
  durableObjectsInvocationsAdaptiveGroups?: Fila<{ requests: number }>[];
  kvOperationsAdaptiveGroups?: Fila<{ requests: number }, { actionType: string }>[];
  r2OperationsAdaptiveGroups?: Fila<{ requests: number }, { actionType: string }>[];
  r2StorageAdaptiveGroups?: Fila<{ payloadSize: number }, { bucketName: string }>[];
};

export type Medida = { nombre: string; usado: number; cupo: number; texto: string; nivel: Nivel; nota?: string };
export type Resumen = { dia: string; medidas: Medida[]; nivel: Nivel; avisos: string[] };

const sumar = <T>(filas: T[] | undefined, f: (x: T) => number) => (filas ?? []).reduce((n, x) => n + (f(x) || 0), 0);
const miles = (n: number) => Math.round(n).toLocaleString("es-AR");
const bytes = (n: number) => (n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(2)} GB` : `${(n / 1024 ** 2).toFixed(1)} MB`);

/** Convierte la respuesta de la API en medidas contra el cupo y un nivel general. */
export function resumir(dia: string, d: Datos): Resumen {
  const medida = (nombre: string, usado: number, cupo: number, formato = miles, nota?: string): Medida =>
    ({ nombre, usado, cupo, texto: `${formato(usado)} de ${formato(cupo)}`, nivel: nivelDe(usado / cupo), nota });

  const inv = d.workersInvocationsAdaptive ?? [];
  const pedidos = sumar(inv, (f) => f.sum?.requests ?? 0);
  // CPU: el peor p99 de un Worker de la cuenta (en microsegundos) y los pedidos cortados por CPU
  // (de los que terminaron bien: los que el cliente cortó a mitad dan picos que no cuentan)
  const terminados = inv.filter((f) => f.dimensions?.status === "success");
  const cpuP99 = Math.max(0, ...(terminados.length ? terminados : inv).map((f) => f.quantiles?.cpuTimeP99 ?? 0)) / 1000;
  const cortados = sumar(inv.filter((f) => f.dimensions?.status === "exceededCpu" || f.dimensions?.status === "exceededResources"),
    (f) => f.sum?.requests ?? 0);
  const kv = (tipo: (a: string) => boolean) =>
    sumar((d.kvOperationsAdaptiveGroups ?? []).filter((f) => tipo(f.dimensions?.actionType ?? "")), (f) => f.sum?.requests ?? 0);
  const kvLecturas = kv((a) => a === "read");
  const kvEscrituras = Math.max(kv((a) => a === "write"), kv((a) => a === "delete"), kv((a) => a === "list"));
  const r2 = (clase: Set<string>) =>
    sumar((d.r2OperationsAdaptiveGroups ?? []).filter((f) => clase.has(f.dimensions?.actionType ?? "")), (f) => f.sum?.requests ?? 0);
  // Guardado en R2: el máximo de cada bucket en el día, sumado
  const porBucket = new Map<string, number>();
  for (const f of d.r2StorageAdaptiveGroups ?? []) {
    const b = f.dimensions?.bucketName ?? "?";
    porBucket.set(b, Math.max(porBucket.get(b) ?? 0, f.max?.payloadSize ?? 0));
  }
  const r2Bytes = [...porBucket.values()].reduce((a, b) => a + b, 0);

  const cpu: Medida = {
    nombre: "CPU por pedido (p99)", usado: cpuP99, cupo: CUPOS.cpuMs,
    texto: `${cpuP99.toFixed(1)} ms de ${CUPOS.cpuMs} ms`,
    // El p99 por encima del cupo todavía no corta (Cloudflare tolera picos); lo que corta son los «cortados»
    nivel: cortados > 0 ? "pasar" : cpuP99 > CUPOS.cpuMs ? "atencion" : "ok",
    nota: cortados > 0 ? `${miles(cortados)} pedidos cortados por CPU (error 1102)` : undefined,
  };
  const medidas: Medida[] = [
    medida("Pedidos a los Workers", pedidos, CUPOS.pedidos),
    cpu,
    medida("D1: filas leídas", sumar(d.d1AnalyticsAdaptiveGroups, (f) => f.sum?.rowsRead ?? 0), CUPOS.d1Leidas),
    medida("D1: filas escritas", sumar(d.d1AnalyticsAdaptiveGroups, (f) => f.sum?.rowsWritten ?? 0), CUPOS.d1Escritas),
    medida("Durable Objects: pedidos", sumar(d.durableObjectsInvocationsAdaptiveGroups, (f) => f.sum?.requests ?? 0), CUPOS.doPedidos),
    medida("KV: lecturas", kvLecturas, CUPOS.kvLecturas),
    medida("KV: escrituras", kvEscrituras, CUPOS.kvEscrituras),
    medida("R2: guardado", r2Bytes, CUPOS.r2Bytes, bytes),
    medida("R2: escrituras del mes", r2(R2_CLASE_A), CUPOS.r2ClaseA),
    medida("R2: lecturas del mes", r2(R2_CLASE_B), CUPOS.r2ClaseB),
  ];
  const nivel = peor(medidas.map((m) => m.nivel));
  const avisos = medidas.filter((m) => m.nivel !== "ok").map((m) => `${m.nombre}: ${m.nota ?? m.texto}`);
  return { dia, medidas, nivel, avisos };
}

const TITULO: Record<Nivel, [string, string, number]> = {
  ok: ["ℹ️", "Uso de Cloudflare: dentro del plan gratis", 0x3498DB],
  atencion: ["⚠️", "Uso de Cloudflare: cerca del cupo gratis, mirar", 0xF39C12],
  pasar: ["🚨", "Uso de Cloudflare: pasar al plan pago (Workers Paid)", 0xE74C3C],
};

/** Tarjeta de Discord, con el mismo diseño que los demás avisos (formato_avisos.py). */
export function tarjetaUso(r: Resumen) {
  const [icono, titulo, color] = TITULO[r.nivel];
  const ancho = Math.max(...r.medidas.map((m) => m.nombre.length));
  const marca: Record<Nivel, string> = { ok: "  ", atencion: "! ", pasar: "!!" };
  const lineas = r.medidas.map((m) => `${marca[m.nivel]} ${m.nombre.padEnd(ancho)}  ${m.texto}${m.cupo && m.nombre !== "CPU por pedido (p99)" ? `  (${Math.round((100 * m.usado) / m.cupo)} %)` : ""}`);
  const [a, mes, dd] = r.dia.split("-");
  const explicacion = r.nivel === "pasar"
    ? "Algún cupo está por llenarse o ya cortó pedidos: si se llena, esa parte de la tienda deja de andar hasta las 21:00. Pasar a Workers Paid (USD 5 por mes) desde el panel de Cloudflare → Workers → Plans."
    : r.nivel === "atencion" ? "Todavía alcanza, pero conviene mirar cómo sigue los próximos días." : "";
  return {
    embeds: [{
      title: `${icono} ${titulo}`,
      color,
      description: (explicacion ? explicacion + "\n" : "") + "```\n" + lineas.join("\n") + "\n```",
      footer: { text: `toda la cuenta de Cloudflare · día ${dd}/${mes}/${a} (UTC)` },
    }],
    allowed_mentions: { parse: [] },
  };
}

/** Pide a Cloudflare los datos de un día (UTC, «AAAA-MM-DD»). */
export async function consultarUso(cuenta: string, token: string, dia: string): Promise<Datos> {
  const desde = `${dia}T00:00:00Z`;
  const hasta = new Date(Date.parse(desde) + 24 * 3600_000).toISOString();
  const mes = `${dia.slice(0, 7)}-01T00:00:00Z`;
  const r = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query: CONSULTA, variables: { cuenta, dia, desde, hasta, mes } }),
    signal: AbortSignal.timeout(15000),
  });
  const json = await r.json() as { data?: { viewer?: { accounts?: Datos[] } }; errors?: { message: string }[] | null };
  if (!r.ok || json.errors?.length) throw new Error(`API de Cloudflare: HTTP ${r.status} ${json.errors?.map((e) => e.message).join("; ") ?? ""}`);
  const cuentaDatos = json.data?.viewer?.accounts?.[0];
  if (!cuentaDatos) throw new Error("API de Cloudflare: sin datos de la cuenta (¿ID o permisos del token?)");
  return cuentaDatos;
}

/** El reporte de ayer por Discord. Sin configuración no hace nada; si la API falla, lo avisa. */
export async function reporteDeUso(env: Env) {
  if (env.REPORTE_USO !== "1") return;
  const url = env.DISCORD_WEBHOOK_URL, cuenta = env.CF_ACCOUNT_ID, token = env.CF_ANALYTICS_TOKEN;
  if (!url?.startsWith("https://discord.com/api/webhooks/") || !cuenta || !token) {
    console.log("reporte de uso: falta DISCORD_WEBHOOK_URL, CF_ACCOUNT_ID o CF_ANALYTICS_TOKEN");
    return;
  }
  const ayer = new Date(Date.now() - 24 * 3600_000).toISOString().slice(0, 10);
  let cuerpo: unknown;
  try {
    cuerpo = tarjetaUso(resumir(ayer, await consultarUso(cuenta, token, ayer)));
  } catch (e) {
    cuerpo = {
      embeds: [{ title: "⚠️ Uso de Cloudflare: no se pudo armar el reporte", color: 0xF39C12,
        description: "```\n" + (e instanceof Error ? e.message : String(e)).slice(0, 500) + "\n```",
        footer: { text: `tienda online · ${ayer}` } }],
      allowed_mentions: { parse: [] },
    };
  }
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo), signal: AbortSignal.timeout(8000) });
  if (!r.ok) console.log(`reporte de uso: Discord respondió HTTP ${r.status}`);
}
