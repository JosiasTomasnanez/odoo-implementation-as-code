import { env } from "cloudflare:workers";
import { COOKIE_SES, cookie, leerCookie, sha256 } from "../../../servidor/panel";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";
export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const t = leerCookie(request, COOKIE_SES);
  if (t) await env.DB.prepare("DELETE FROM sesiones_panel WHERE token_hash = ?").bind(await sha256(t)).run();
  return new Response(null, { status: 303, headers: { Location: `${url.origin}/panel`, "Set-Cookie": cookie(COOKIE_SES, "", 0) } });
}
