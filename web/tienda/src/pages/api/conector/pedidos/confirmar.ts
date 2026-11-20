// El conector avisa qué pedidos ya creó en Odoo: pasan a «en_odoo» y su reserva deja de restarse.
import { env } from "cloudflare:workers";
import { z } from "zod";
import { firmaValida } from "../../../../servidor/firma";
import { evento, inventario } from "../../../../servidor/pedidos";
import { cuerpoConTope, error, json } from "../../../../servidor/respuestas";

export const prerender = false;
const Confirmacion = z.strictObject({
  pedidos: z.array(z.strictObject({ id: z.string().regex(/^[0-9a-f]{32}$/), odoo_id: z.number().int().positive(), odoo_nombre: z.string().max(64) })).max(50),
});

export async function POST({ request, url }: { request: Request; url: URL }) {
  const cuerpo = await cuerpoConTope(request, 64 * 1024);
  if (!cuerpo) return error(413, "Demasiado grande");
  const ok = await firmaValida(env.CONECTOR_SECRETO, request.headers.get("x-tienda-fecha"),
    request.headers.get("x-tienda-firma"), "POST", url.pathname, cuerpo);
  if (!ok) return error(401, "Firma inválida");
  let datos: unknown;
  try { datos = JSON.parse(new TextDecoder().decode(cuerpo)); } catch { return error(400, "JSON inválido"); }
  const c = Confirmacion.safeParse(datos);
  if (!c.success) return error(422, "Datos inválidos");
  const ts = new Date().toISOString();
  for (const p of c.data.pedidos) {
    const r = await env.DB.prepare(`UPDATE pedidos SET estado = CASE WHEN estado = 'pagado' THEN 'en_odoo' ELSE estado END,
        odoo_id = ?, odoo_nombre = ?, actualizado = ? WHERE id = ? AND odoo_id IS NULL`).bind(p.odoo_id, p.odoo_nombre, ts, p.id).run();
    if (r.meta.changes) {
      await inventario(env).reflejar(p.id);
      await evento(env.DB, p.id, `creado en Odoo: ${p.odoo_nombre}`);
    }
  }
  return json({ ok: true });
}
