import { env } from "cloudflare:workers";
import { cookieCliente, salir } from "../../../servidor/clientes";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";
import { rutasCuenta, sitioDe } from "../../../servidor/sitio";
export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  await salir(env.DB, request);
  return new Response(null, { status: 303, headers: { Location: `${url.origin}${rutasCuenta(sitioDe(url)).salir}`, "Set-Cookie": cookieCliente("", 0) } });
}
