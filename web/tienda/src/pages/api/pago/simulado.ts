// SOLO DEMO (PAGOS_MODO=simulado): «Aprobar» o «Rechazar» un pago, por el mismo circuito que un
// aviso real. En producción este endpoint no existe (responde 404).
import { env } from "cloudflare:workers";
import { modo } from "../../../servidor/pagos";
import { mismoToken, procesarPago } from "../../../servidor/pedidos";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error, json } from "../../../servidor/respuestas";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (modo(env) !== "simulado") return error(404, "No encontrado");
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const f = await request.formData();
  const id = String(f.get("id") ?? ""), t = String(f.get("t") ?? ""), decision = String(f.get("decision") ?? "");
  if (!/^[0-9a-f]{32}$/.test(id) || !["aprobar", "rechazar"].includes(decision)) return error(400, "Datos inválidos");
  const p = await env.DB.prepare("SELECT token, total FROM pedidos WHERE id = ?").bind(id).first<{ token: string; total: number }>();
  if (!p || !mismoToken(t, p.token)) return error(404, "No encontrado");
  const estado = await procesarPago(env, "simulado", {
    pago_id: `${id}-${decision}`, pedido_id: id, estado: decision === "aprobar" ? "aprobado" : "rechazado", monto: p.total,
  }, url.origin);
  if (request.headers.get("accept")?.includes("application/json")) return json({ estado });
  return Response.redirect(`${url.origin}/pedido/${id}?t=${t}`, 303);
}
