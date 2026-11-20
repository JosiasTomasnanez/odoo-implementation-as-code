// Primera vez u olvido de la contraseña del equipo. Sin «codigo»: manda el código al mail (solo si
// es alguien del equipo, pero responde igual). Con «codigo» y «clave»: la guarda, deja el navegador
// de confianza (el código prueba que el mail es suyo) y entra.
import { env } from "cloudflare:workers";
import { z } from "zod";
import { codigoValido, codigosAgotados, contarCodigo, nuevoCodigo } from "../../../servidor/clientes";
import { claveAceptable, hashClave } from "../../../servidor/claves";
import { abrirSesion, confiar, cortarSesiones, cookieEq, COOKIE_CONF, COOKIE_EQ, SEGUNDOS_CONF, SEGUNDOS_EQ } from "../../../servidor/equipo";
import { mailCodigo } from "../../../servidor/mails";
import { limitar, mismoOrigen, turnstileValido } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;
const Email = z.string().trim().toLowerCase().max(160).email();

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const ip = request.headers.get("cf-connecting-ip") ?? "?";
  const lim = await limitar(env.LIMITE_INGRESO, `admin:${ip}`);
  if (lim) return lim;
  const f = await request.formData();
  const e = Email.safeParse(String(f.get("email") ?? ""));
  const m = e.success ? e.data : "";
  const volver = (q: string) => Response.redirect(`${url.origin}/admin/ingresar?${q}&m=${encodeURIComponent(m)}`, 303);
  if (!e.success) return volver("modo=clave&e=mail");
  const clave = `equipo:${e.data}`;
  const codigo = String(f.get("codigo") ?? "").replace(/\D/g, "");

  if (!codigo) {
    if (!(await turnstileValido(env, String(f.get("cf-turnstile-response") ?? ""), ip))) return volver("modo=clave&e=robot");
    const existe = await env.DB.prepare("SELECT 1 FROM equipo WHERE email = ? AND activo = 1").bind(e.data).first();
    if (existe && !(await codigosAgotados(env.DB, clave))) {
      await contarCodigo(env.DB, clave);
      await mailCodigo(env, e.data, await nuevoCodigo(env.DB, clave, "clave"), "clave");
    }
    return volver("modo=nueva");
  }

  const nueva = String(f.get("clave") ?? "");
  if (f.has("clave2") && f.get("clave2") !== nueva) return volver("modo=nueva&e=repetir");
  if (claveAceptable(nueva, e.data)) return volver("modo=nueva&e=clave");
  if (!(await codigoValido(env.DB, clave, codigo, ip, "clave"))) return volver("modo=nueva&e=codigo");
  const r = await env.DB.prepare("UPDATE equipo SET clave_hash = ? WHERE email = ? AND activo = 1 RETURNING id").bind(await hashClave(nueva), e.data).first<{ id: string }>();
  if (!r) return volver("e=clave");
  // Contraseña nueva: se cierran sus sesiones y se olvidan los navegadores de confianza anteriores
  // (y se levanta el bloqueo por intentos: el código prueba que el mail es suyo)
  await env.DB.batch([cortarSesiones(env.DB, r.id), env.DB.prepare("DELETE FROM confianza_equipo WHERE miembro_id = ?").bind(r.id),
    env.DB.prepare("DELETE FROM intentos WHERE clave = ? OR substr(clave, 1, ?) = ?").bind(`equipo:${e.data}`, `equipo:${e.data}:`.length, `equipo:${e.data}:`)]);
  const h = new Headers({ Location: `${url.origin}/admin`, "Cache-Control": "no-store" });
  h.append("Set-Cookie", cookieEq(COOKIE_EQ, await abrirSesion(env.DB, r.id), SEGUNDOS_EQ));
  h.append("Set-Cookie", cookieEq(COOKIE_CONF, await confiar(env.DB, r.id), SEGUNDOS_CONF));
  return new Response(null, { status: 303, headers: h });
}
