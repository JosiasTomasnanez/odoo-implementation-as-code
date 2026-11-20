// Vuelta de Google: canjea el código, busca o crea la cuenta y abre la sesión. En el sitio
// mayorista, sin aprobación, la página de inicio le pide los datos de la empresa como siempre.
import { env } from "cloudflare:workers";
import { cookieCliente, deGoogle, entrar, SEGUNDOS_CLIENTE } from "../../../servidor/clientes";
import { borrarCookie, canje, googleActivo } from "../../../servidor/google";
import { limitar } from "../../../servidor/protecciones";
import { rutasCuenta, sitioDe } from "../../../servidor/sitio";
import { irDespues } from "../../../servidor/volver";

export const prerender = false;

export async function GET({ request, url }: { request: Request; url: URL }) {
  const rutas = rutasCuenta(sitioDe(url));
  const lim = await limitar(env.LIMITE_INGRESO, `entrar:${request.headers.get("cf-connecting-ip") ?? "?"}`);
  if (lim) return lim;
  const u = googleActivo(env) ? await canje(env, url.origin, request, url) : null;
  const h = new Headers({ "Cache-Control": "no-store" });
  h.append("Set-Cookie", borrarCookie);
  if (!u) {
    h.set("Location", `${url.origin}${rutas.ingreso}?e=google`);
    return new Response(null, { status: 303, headers: h });
  }
  await deGoogle(env.DB, u.sub, u.email, u.nombre);
  return irDespues(request, url, sitioDe(url), cookieCliente(await entrar(env.DB, u.email), SEGUNDOS_CLIENTE), [borrarCookie]);
}
