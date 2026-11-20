// Confirmar el código del mail: crea la cuenta con la contraseña elegida («alta») o pone la
// contraseña nueva («clave»), y abre la sesión.
import { env } from "cloudflare:workers";
import { z } from "zod";
import { codigoValido, COOKIE_ALTA, cookieCliente, entrar, SEGUNDOS_CLIENTE } from "../../../servidor/clientes";
import { leerCookie } from "../../../servidor/panel";
import { claveAceptable, hashClave } from "../../../servidor/claves";
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
  const para = f.get("p") === "clave" ? "clave" : "alta";
  const codigo = String(f.get("codigo") ?? "").replace(/\D/g, "");
  const volver = (err: string) => Response.redirect(`${url.origin}${rutas.ingreso}?modo=codigo&p=${para}&e=${err}&m=${encodeURIComponent(e.success ? e.data : "")}`, 303);
  if (!e.success) return volver("codigo");
  // La contraseña nueva se revisa antes de gastar el código
  const nueva = String(f.get("clave") ?? "");
  if (para === "clave" && f.has("clave2") && f.get("clave2") !== nueva) return volver("repetir");
  if (para === "clave" && claveAceptable(nueva, e.data)) return volver("clave");
  const atado = para === "alta" ? leerCookie(request, COOKIE_ALTA) ?? "" : "";
  if (para === "alta" && !atado) return volver("navegador");
  const v = await codigoValido(env.DB, e.data, codigo, ip, para, atado);
  if (!v) return volver("codigo");
  const token = await entrar(env.DB, e.data, para === "clave" ? await hashClave(nueva) : v.clave_hash);
  return irDespues(request, url, sitioDe(url), cookieCliente(token, SEGUNDOS_CLIENTE));
}
