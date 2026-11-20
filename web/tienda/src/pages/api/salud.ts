// Chequeo de vida de la tienda (lo usan el conector y los avisos): responde si el Worker y el
// Durable Object «Inventario» contestan. No devuelve datos.
import { env } from "cloudflare:workers";
export const prerender = false;

export async function GET() {
  const inv = env.INVENTARIO.get(env.INVENTARIO.idFromName("principal"));
  const estado = await inv.estado();
  return Response.json({ tienda: "ok", inventario: estado.ok ? "ok" : "mal" }, { headers: { "Cache-Control": "no-store" } });
}
