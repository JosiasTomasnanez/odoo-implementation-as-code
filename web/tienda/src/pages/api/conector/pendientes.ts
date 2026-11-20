// Todo lo que espera al conector, en una sola consulta por vuelta (menos pedidos a la tienda: el
// conector pregunta cada pocos segundos todo el día). Firmado con HMAC.
import { env } from "cloudflare:workers";
import { firmaValida } from "../../../servidor/firma";
import { error, json } from "../../../servidor/respuestas";
import { accionesPendientes, clientesPendientes, pedidosPendientes } from "../../../servidor/pendientes";

export const prerender = false;

export async function GET({ request, url }: { request: Request; url: URL }) {
  const ok = await firmaValida(env.CONECTOR_SECRETO, request.headers.get("x-tienda-fecha"),
    request.headers.get("x-tienda-firma"), "GET", url.pathname, new ArrayBuffer(0));
  if (!ok) return error(401, "Firma inválida");
  const [pedidos, acciones, c] = await Promise.all([pedidosPendientes(env.DB), accionesPendientes(env.DB), clientesPendientes(env.DB)]);
  return json({ pedidos, acciones, clientes: c.clientes, listas: c.listas });
}
