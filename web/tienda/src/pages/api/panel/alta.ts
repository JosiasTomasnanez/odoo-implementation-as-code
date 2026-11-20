// Habilitar esta PC o tablet como dispositivo del local (una vez, con el código de alta).
import { env } from "cloudflare:workers";
import { COOKIE_DISP, aleatorio, bloqueado, cookie, fallo, acierto, iguales, sha256 } from "../../../servidor/panel";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const codigo = env.PANEL_CODIGO_ALTA ?? "";
  if (codigo.length < 12) return error(503, "El panel no tiene código de alta configurado.");
  const clave = `alta:${request.headers.get("cf-connecting-ip") ?? "?"}`;
  if (await bloqueado(env.DB, clave)) return Response.redirect(`${url.origin}/panel/alta?e=bloqueado`, 303);
  const f = await request.formData();
  const dado = String(f.get("codigo") ?? "").trim().slice(0, 200);
  const nombre = String(f.get("nombre") ?? "").trim().replace(/[^\p{L}\p{N} ._-]/gu, "").slice(0, 60) || "Dispositivo del local";
  if (!iguales(await sha256(dado), await sha256(codigo))) {
    await fallo(env.DB, clave, 5, 30);
    return Response.redirect(`${url.origin}/panel/alta?e=codigo`, 303);
  }
  await acierto(env.DB, clave);
  const token = aleatorio();
  await env.DB.prepare("INSERT INTO dispositivos (id, nombre, token_hash, creado) VALUES (?, ?, ?, ?)")
    .bind(aleatorio(8), nombre, await sha256(token), new Date().toISOString()).run();
  return new Response(null, { status: 303, headers: { Location: `${url.origin}/panel`, "Set-Cookie": cookie(COOKIE_DISP, token, 365 * 86400) } });
}
