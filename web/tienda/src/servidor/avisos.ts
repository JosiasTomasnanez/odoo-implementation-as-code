// Avisos al equipo por Discord (el mismo canal del resumen de mails). Para lo que alguien tiene que
// mirar enseguida: un pago con monto distinto o repetido. Sin DISCORD_WEBHOOK_URL no hace nada y
// nunca hace fallar a quien lo llama.
export async function avisarEquipo(env: Env, titulo: string, detalle: string) {
  const url = env.DISCORD_WEBHOOK_URL;
  if (!url?.startsWith("https://discord.com/api/webhooks/")) return;
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        embeds: [{ title: `⚠️ ${titulo}`.slice(0, 250), color: 0xF39C12, description: detalle.slice(0, 1500), footer: { text: "tienda online" } }],
        allowed_mentions: { parse: [] },
      }),
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) console.log(`aviso al equipo: Discord respondió HTTP ${r.status}`);
  } catch (e) {
    console.log(`aviso al equipo no enviado: ${e instanceof Error ? e.message : e}`);
  }
}
