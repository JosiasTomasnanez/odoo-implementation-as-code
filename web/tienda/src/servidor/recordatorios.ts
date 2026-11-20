// Plazo de retiro (configurable con DIAS_RECORDATORIO, por defecto 3): un solo recordatorio por
// mail. En el panel, los listos hace más de DIAS_AVISO_LOCAL (7) se marcan para que el local decida.
import { mailRecordatorio } from "./mails.ts";

export async function recordarRetiros(env: Env): Promise<void> {
  const dias = Number((env as unknown as { DIAS_RECORDATORIO?: string }).DIAS_RECORDATORIO ?? "3") || 3;
  const origen = (env as unknown as { ORIGEN?: string }).ORIGEN ?? "https://comercio-ejemplo.example";
  const limite = new Date(Date.now() - dias * 86_400_000).toISOString();
  const r = await env.DB.prepare(`SELECT id, numero, token, nombre, email, total FROM pedidos
      WHERE estado = 'listo' AND listo < ? AND recordado IS NULL LIMIT 50`).bind(limite)
    .all<{ id: string; numero: number; token: string; nombre: string; email: string; total: number }>();
  for (const p of r.results) {
    await mailRecordatorio(env, origen, p);
    await env.DB.prepare("UPDATE pedidos SET recordado = ? WHERE id = ?").bind(new Date().toISOString(), p.id).run();
  }
}
