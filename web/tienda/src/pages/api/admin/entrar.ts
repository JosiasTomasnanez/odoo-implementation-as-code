// Ingreso del equipo. Paso 1: mail y contraseña. Si este navegador ya es de confianza para esa
// persona, entra; si no, se manda un código al mail (paso 2) atado a este navegador por una cookie
// corta, así el código solo no alcanza: hace falta haber puesto la contraseña acá.
// Paso 2 (con «codigo»): confirma el código, deja el navegador de confianza 60 días y entra.
import { env } from "cloudflare:workers";
import { z } from "zod";
import { codigoValido, nuevoCodigo } from "../../../servidor/clientes";
import { abrirSesion, claveEquipo, confiar, cookieEq, COOKIE_CONF, COOKIE_EQ, deConfianza, SEGUNDOS_CONF, SEGUNDOS_EQ } from "../../../servidor/equipo";
import { mailCodigo } from "../../../servidor/mails";
import { aleatorio, iguales, leerCookie, sha256 } from "../../../servidor/panel";
import { limitar, mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;
const Email = z.string().trim().toLowerCase().max(160).email();
const PASO = "cf_equipo_paso";

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const ip = request.headers.get("cf-connecting-ip") ?? "?";
  const lim = await limitar(env.LIMITE_INGRESO, `admin:${ip}`);
  if (lim) return lim;
  const f = await request.formData();
  const e = Email.safeParse(String(f.get("email") ?? ""));
  const m = e.success ? e.data : "";
  const volver = (q: string) => Response.redirect(`${url.origin}/admin/ingresar?${q}&m=${encodeURIComponent(m)}`, 303);
  if (!e.success) return volver("e=clave");
  const entrar = async (id: string, extra: string[] = []) => {
    const h = new Headers({ Location: `${url.origin}/admin`, "Cache-Control": "no-store" });
    h.append("Set-Cookie", cookieEq(COOKIE_EQ, await abrirSesion(env.DB, id), SEGUNDOS_EQ));
    for (const c of extra) h.append("Set-Cookie", c);
    return new Response(null, { status: 303, headers: h });
  };

  const codigo = String(f.get("codigo") ?? "").replace(/\D/g, "");
  if (codigo) {
    const ticket = leerCookie(request, PASO);
    const v = await codigoValido(env.DB, `equipo:${e.data}`, codigo, ip, "equipo");
    if (!v || !ticket || !v.clave_hash || !iguales(await sha256(ticket), v.clave_hash)) return volver("modo=codigo&e=codigo");
    const id = (await env.DB.prepare("SELECT id FROM equipo WHERE email = ? AND activo = 1").bind(e.data).first<{ id: string }>())?.id;
    if (!id) return volver("e=clave");
    return entrar(id, [cookieEq(COOKIE_CONF, await confiar(env.DB, id), SEGUNDOS_CONF), `${PASO}=; Path=/api/admin; Max-Age=0; HttpOnly; Secure; SameSite=Strict`]);
  }

  const id = await claveEquipo(env.DB, request, e.data, String(f.get("clave") ?? "").slice(0, 200), ip);
  if (!id) return volver("e=clave");
  if (await deConfianza(env.DB, request, id)) return entrar(id);
  const ticket = aleatorio();
  await mailCodigo(env, e.data, await nuevoCodigo(env.DB, `equipo:${e.data}`, "equipo", await sha256(ticket)), "equipo");
  return new Response(null, { status: 303, headers: {
    Location: `${url.origin}/admin/ingresar?modo=codigo&m=${encodeURIComponent(m)}`,
    "Set-Cookie": `${PASO}=${ticket}; Path=/api/admin; Max-Age=600; HttpOnly; Secure; SameSite=Strict`,
  } });
}
