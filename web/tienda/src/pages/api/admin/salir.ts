import { env } from "cloudflare:workers";
import { cerrarSesion, cookieEq, COOKIE_EQ } from "../../../servidor/equipo";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  await cerrarSesion(env.DB, request);
  return new Response(null, { status: 303, headers: { Location: `${url.origin}/admin/ingresar`, "Set-Cookie": cookieEq(COOKIE_EQ, "", 0) } });
}
