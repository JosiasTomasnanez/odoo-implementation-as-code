// Cuenta de mails por día y proveedor, y el resumen diario por Discord (P-067). El día es el de
// Argentina. Sin DISCORD_WEBHOOK_URL solo se cuenta. Nunca hace fallar un envío.
const CUPOS: Record<string, string> = { brevo: "300 por día", resend: "100 por día, compartido con Odoo y los avisos", cloudflare: "3.000 por mes" };

export const diaAr = (cuando = Date.now()) => new Date(cuando - 3 * 3600_000).toISOString().slice(0, 10);

export async function contarMail(db: D1Database, proveedor: string | null) {
  try {
    await db.prepare(`INSERT INTO mails_dia (dia, proveedor, cantidad) VALUES (?, ?, 1)
        ON CONFLICT(dia, proveedor) DO UPDATE SET cantidad = cantidad + 1`).bind(diaAr(), proveedor ?? "fallidos").run();
  } catch (e) { console.log(`no se pudo contar el mail: ${e instanceof Error ? e.message : e}`); }
}

/** Tarjeta de Discord con el resumen de un día, con el mismo diseño que los avisos del servidor
 *  (infra/servidor/formato_avisos.py): color e ícono según el nivel, detalle en un recuadro y pie.
 *  null si no hubo movimiento. */
export function tarjetaResumen(dia: string, filas: { proveedor: string; cantidad: number }[]) {
  const ok = filas.filter((f) => f.proveedor !== "fallidos" && f.cantidad > 0);
  const fallidos = filas.find((f) => f.proveedor === "fallidos")?.cantidad ?? 0;
  const total = ok.reduce((n, f) => n + f.cantidad, 0);
  if (!total && !fallidos) return null;
  const [a, m, d] = dia.split("-");
  const ancho = Math.max(...ok.map((f) => f.proveedor.length), 0);
  const lineas = ok.map((f) => `${f.proveedor.padEnd(ancho)}  ${String(f.cantidad).padStart(4)}${CUPOS[f.proveedor] ? `   cupo: ${CUPOS[f.proveedor]}` : ""}`);
  if (fallidos) lineas.push(`${lineas.length ? "\n" : ""}No salieron por ningún proveedor: ${fallidos}`);
  return {
    embeds: [{
      title: `${fallidos ? "⚠️" : "ℹ️"} Mails de la tienda: ${total} enviado${total === 1 ? "" : "s"}`,
      color: fallidos ? 0xF39C12 : 0x3498DB,
      description: "```\n" + lineas.join("\n") + "\n```",
      footer: { text: `tienda online · ${d}/${m}/${a}` },
    }],
    allowed_mentions: { parse: [] },
  };
}

/** Manda por Discord el resumen de ayer y borra la cuenta de hace más de 90 días. */
export async function resumenDeAyer(env: Env) {
  const ayer = diaAr(Date.now() - 24 * 3600_000);
  const filas = (await env.DB.prepare("SELECT proveedor, cantidad FROM mails_dia WHERE dia = ? ORDER BY cantidad DESC").bind(ayer)
    .all<{ proveedor: string; cantidad: number }>()).results;
  await env.DB.prepare("DELETE FROM mails_dia WHERE dia < ?").bind(diaAr(Date.now() - 90 * 24 * 3600_000)).run();
  const tarjeta = tarjetaResumen(ayer, filas), url = env.DISCORD_WEBHOOK_URL;
  if (!tarjeta || !url?.startsWith("https://discord.com/api/webhooks/")) return;
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(tarjeta), signal: AbortSignal.timeout(8000) });
  if (!r.ok) console.log(`resumen de mails: Discord respondió HTTP ${r.status}`);
}
