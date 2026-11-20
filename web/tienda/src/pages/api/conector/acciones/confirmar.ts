// El conector avisa qué acciones aplicó en Odoo (y con qué resultado).
import { env } from "cloudflare:workers";
import { z } from "zod";
import { firmaValida } from "../../../../servidor/firma";
import { evento } from "../../../../servidor/pedidos";
import { cuerpoConTope, error, json } from "../../../../servidor/respuestas";

export const prerender = false;
const Conf = z.strictObject({ acciones: z.array(z.strictObject({ id: z.string().regex(/^[0-9a-f]{32}$/), resultado: z.string().max(300) })).max(100) });

export async function POST({ request, url }: { request: Request; url: URL }) {
  const cuerpo = await cuerpoConTope(request, 64 * 1024);
  if (!cuerpo) return error(413, "Demasiado grande");
  const ok = await firmaValida(env.CONECTOR_SECRETO, request.headers.get("x-tienda-fecha"),
    request.headers.get("x-tienda-firma"), "POST", url.pathname, cuerpo);
  if (!ok) return error(401, "Firma inválida");
  let d: unknown;
  try { d = JSON.parse(new TextDecoder().decode(cuerpo)); } catch { return error(400, "JSON inválido"); }
  const c = Conf.safeParse(d);
  if (!c.success) return error(422, "Datos inválidos");
  const ts = new Date().toISOString();
  for (const a of c.data.acciones) {
    const r = await env.DB.prepare("UPDATE acciones SET aplicada = ?, resultado = ? WHERE id = ? AND aplicada IS NULL RETURNING pedido_id, tipo")
      .bind(ts, a.resultado, a.id).first<{ pedido_id: string; tipo: string }>();
    if (r) await evento(env.DB, r.pedido_id, `Odoo: ${r.tipo} → ${a.resultado}`);
  }
  return json({ ok: true });
}
