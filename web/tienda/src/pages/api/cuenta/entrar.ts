// Entrar con mail y contraseña. Mismo mensaje si el mail no existe o la contraseña no es; 8 fallos
// por mail e IP frenan 15 minutos.
import { env } from "cloudflare:workers";
import { z } from "zod";
import { conClave, cookieCliente, entrar, SEGUNDOS_CLIENTE } from "../../../servidor/clientes";
import { limitar, mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";
import { rutasCuenta, sitioDe } from "../../../servidor/sitio";
import { irDespues } from "../../../servidor/volver";

export const prerender = false;
const Email = z.string().trim().toLowerCase().max(160).email();

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const ip = request.headers.get("cf-connecting-ip") ?? "?";
  const lim = await limitar(env.LIMITE_INGRESO, `entrar:${ip}`);
  if (lim) return lim;
  const rutas = rutasCuenta(sitioDe(url));
  const f = await request.formData();
  const e = Email.safeParse(String(f.get("email") ?? ""));
  const clave = String(f.get("clave") ?? "").slice(0, 200);
  if (!e.success || !clave || !(await conClave(env.DB, e.data, clave, ip))) {
    return Response.redirect(`${url.origin}${rutas.ingreso}?e=clave&m=${encodeURIComponent(e.success ? e.data : "")}`, 303);
  }
  const token = await entrar(env.DB, e.data);
  return irDespues(request, url, sitioDe(url), cookieCliente(token, SEGUNDOS_CLIENTE));
}
