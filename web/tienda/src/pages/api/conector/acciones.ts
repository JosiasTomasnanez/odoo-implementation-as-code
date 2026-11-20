// El conector trae las acciones del panel (preparar, listo, faltante, retirado) para aplicarlas en Odoo.
import { env } from "cloudflare:workers";
import { firmaValida } from "../../../servidor/firma";
import { error, json } from "../../../servidor/respuestas";
import { accionesPendientes } from "../../../servidor/pendientes";

export const prerender = false;

export async function GET({ request, url }: { request: Request; url: URL }) {
  const ok = await firmaValida(env.CONECTOR_SECRETO, request.headers.get("x-tienda-fecha"),
    request.headers.get("x-tienda-firma"), "GET", url.pathname, new ArrayBuffer(0));
  if (!ok) return error(401, "Firma inválida");
  return json({ acciones: await accionesPendientes(env.DB) });
}
