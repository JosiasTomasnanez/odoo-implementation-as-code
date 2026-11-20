// Mandar un código al mail: «alta» (crear la cuenta con la contraseña elegida: la cuenta se crea
// recién al confirmar el código) o «clave» (olvidé mi contraseña). Turnstile, límite por IP, un
// código por minuto y como máximo 20 por día por mail. Mismo mensaje exista o no la cuenta.
import { env } from "cloudflare:workers";
import { z } from "zod";
import { codigosAgotados, contarCodigo, nuevoCodigo } from "../../../servidor/clientes";
import { claveAceptable, hashClave } from "../../../servidor/claves";
import { mailCodigo } from "../../../servidor/mails";
import { limitar, mismoOrigen, turnstileValido } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";
import { aleatorio } from "../../../servidor/panel";
import { COOKIE_ALTA } from "../../../servidor/clientes";
import { rutasCuenta, sitioDe } from "../../../servidor/sitio";

export const prerender = false;
const Email = z.string().trim().toLowerCase().max(160).email();

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const ip = request.headers.get("cf-connecting-ip");
  const lim = await limitar(env.LIMITE_INGRESO, `codigo:${ip ?? "?"}`);
  if (lim) return lim;
  const ingreso = rutasCuenta(sitioDe(url)).ingreso;
  const f = await request.formData();
  const para = f.get("para") === "clave" ? "clave" : "alta";
  const volver = (e: string, m = "") => Response.redirect(`${url.origin}${ingreso}?modo=${para === "alta" ? "crear" : "olvide"}&e=${e}&m=${encodeURIComponent(m)}`, 303);
  const e = Email.safeParse(String(f.get("email") ?? ""));
  if (!e.success) return volver("mail");
  let claveHash: string | null = null;
  if (para === "alta") {
    const clave = String(f.get("clave") ?? "");
    if (f.has("clave2") && f.get("clave2") !== clave) return volver("repetir", e.data);
    if (claveAceptable(clave, e.data)) return volver("clave", e.data);
    claveHash = await hashClave(clave);
  }
  if (!(await turnstileValido(env, String(f.get("cf-turnstile-response") ?? ""), ip))) return volver("robot", e.data);
  const existe = para === "alta" || !!(await env.DB.prepare("SELECT 1 FROM clientes WHERE email = ?").bind(e.data).first());
  const reciente = await env.DB.prepare("SELECT vence FROM codigos_ingreso WHERE email = ?").bind(e.data).first<{ vence: string }>();
  // «alta»: el código queda atado a este navegador (cookie al azar), así nadie más puede colar su
  // contraseña pidiendo otro código para el mismo mail.
  const atado = para === "alta" ? aleatorio() : "";
  let mandado = false;
  if (existe && !(await codigosAgotados(env.DB, e.data)) && (!reciente || Date.parse(reciente.vence) - Date.now() < 9 * 60_000)) {
    await contarCodigo(env.DB, e.data);
    await mailCodigo(env, e.data, await nuevoCodigo(env.DB, e.data, para, claveHash, atado), para);
    mandado = true;
  }
  const h = new Headers({ Location: `${url.origin}${ingreso}?modo=codigo&p=${para}&m=${encodeURIComponent(e.data)}` });
  if (mandado && atado) h.append("Set-Cookie", `${COOKIE_ALTA}=${atado}; Path=/api/cuenta; Max-Age=900; HttpOnly; Secure; SameSite=Strict`);
  return new Response(null, { status: 303, headers: h });
}
