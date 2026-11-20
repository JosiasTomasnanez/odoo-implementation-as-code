// El conector avisa qué hizo Odoo: el contacto de cada mayorista y el id de cada lista nueva (o el error).
import { env } from "cloudflare:workers";
import { z } from "zod";
import { firmaValida } from "../../../../servidor/firma";
import { cuerpoConTope, error, json } from "../../../../servidor/respuestas";

export const prerender = false;
const Id = z.string().regex(/^[0-9a-f]{32}$/);
const Conf = z.strictObject({
  clientes: z.array(z.strictObject({ id: Id, odoo_partner_id: z.number().int().positive().nullable(), resultado: z.string().max(300) })).max(50),
  listas: z.array(z.strictObject({ id: Id, odoo_id: z.number().int().positive().nullable(), resultado: z.string().max(300), version: z.number().int().optional() })).max(20),
});

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
  const s: D1PreparedStatement[] = [];
  for (const x of c.data.clientes) {
    // Con error queda en 2 (no se reintenta solo, para no repetir en cada vuelta) y con el motivo a la
    // vista en la administración; «Guardar lista» lo vuelve a mandar.
    s.push(x.odoo_partner_id
      ? env.DB.prepare("UPDATE clientes SET odoo_partner_id = ?, odoo_pendiente = 0, odoo_error = NULL WHERE id = ?").bind(x.odoo_partner_id, x.id)
      : env.DB.prepare("UPDATE clientes SET odoo_pendiente = 2, odoo_error = ? WHERE id = ?").bind(x.resultado, x.id));
  }
  // Lista creada o puesta al día. Si mientras tanto la cambiaron de nuevo (otra versión), sigue
  // pendiente para la próxima vuelta. Con error queda en 2, con el motivo a la vista.
  for (const x of c.data.listas) {
    const v = x.version ?? null;
    s.push(env.DB.prepare(`UPDATE listas_nuevas SET odoo_id = COALESCE(?, odoo_id), resultado = ?,
        pendiente = CASE WHEN ? IS NOT NULL AND version <> ? THEN pendiente WHEN ? IS NULL THEN 2 ELSE 0 END WHERE id = ?`)
      .bind(x.odoo_id, x.resultado, v, v, x.odoo_id, x.id));
  }
  if (s.length) await env.DB.batch(s);
  return json({ ok: true });
}
