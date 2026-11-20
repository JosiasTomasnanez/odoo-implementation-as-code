// El conector del local manda acá los cambios del catálogo (ADR 0033). Firmado con HMAC.
import { env } from "cloudflare:workers";
import { firmaValida } from "../../../servidor/firma";
import { Lote } from "../../../servidor/esquemas";
import { aplicarLote } from "../../../servidor/catalogo";
import { cuerpoConTope, error, json } from "../../../servidor/respuestas";

export const prerender = false;
const MAX = 5 * 1024 * 1024;

export async function POST({ request, url }: { request: Request; url: URL }) {
  const cuerpo = await cuerpoConTope(request, MAX);
  if (!cuerpo) return error(413, "Lote demasiado grande");
  const ok = await firmaValida(env.CONECTOR_SECRETO, request.headers.get("x-tienda-fecha"),
    request.headers.get("x-tienda-firma"), "POST", url.pathname, cuerpo);
  if (!ok) return error(401, "Firma inválida");
  let datos: unknown;
  try { datos = JSON.parse(new TextDecoder().decode(cuerpo)); } catch { return error(400, "JSON inválido"); }
  const lote = Lote.safeParse(datos);
  if (!lote.success) {
    console.warn("lote rechazado", JSON.stringify(lote.error.issues.slice(0, 5)));
    return error(422, "Lote con datos inválidos");
  }
  const r = await aplicarLote(env.DB, lote.data, new Date().toISOString(), env.PIN_PEPPER ?? "");
  return json({ ok: true, ...r });
}
