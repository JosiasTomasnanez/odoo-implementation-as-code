// Ingresar con Google: manda a Google (el mail no necesita código: Google ya lo verificó).
import { env } from "cloudflare:workers";
import { googleActivo, inicio } from "../../../servidor/google";
import { rutasCuenta, sitioDe } from "../../../servidor/sitio";

export const prerender = false;

export async function GET({ url }: { url: URL }) {
  if (!googleActivo(env)) return Response.redirect(`${url.origin}${rutasCuenta(sitioDe(url)).ingreso}`, 303);
  const { ir, cookie } = await inicio(env, url.origin);
  return new Response(null, { status: 303, headers: { Location: ir, "Set-Cookie": cookie, "Cache-Control": "no-store" } });
}
