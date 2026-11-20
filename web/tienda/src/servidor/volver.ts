// Después de ingresar, la tienda devuelve al cliente a donde estaba (el carrito, un producto) en
// lugar de llevarlo a su cuenta. El lugar viaja en una cookie corta que deja la página de ingreso;
// solo se aceptan rutas propias. El sitio mayorista va siempre a su lista.
import type { Sitio } from "./sitio.ts";
import { rutasCuenta } from "./sitio.ts";

const COOKIE = "cf_volver";
const cookie = (valor: string, segundos: number) => `${COOKIE}=${valor}; Path=/; Max-Age=${segundos}; HttpOnly; Secure; SameSite=Lax`;

/** Una ruta de este sitio a la que tiene sentido volver, o null. */
export function rutaSegura(v: string | null | undefined): string | null {
  if (!v || v.length > 200 || !/^\/(?![/\\])[\w\-./~%?=&+]*$/.test(v)) return null;
  if (/^\/(api|admin|panel)(\/|$)/.test(v) || /^\/cuenta\/?(\?|$)/.test(v)) return null;
  return v;
}

export const recordarVuelta = (ruta: string) => cookie(encodeURIComponent(ruta), 900);

/** Respuesta que abre la sesión y manda a donde estaba (tienda) o al inicio del sitio. */
export function irDespues(req: Request, url: URL, sitio: Sitio, cookieSesion: string, otras: string[] = []): Response {
  const guardada = (req.headers.get("cookie") ?? "").split(";").map((x) => x.trim()).find((x) => x.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1);
  let ruta: string | null = null;
  try { ruta = sitio === "tienda" ? rutaSegura(decodeURIComponent(guardada ?? "")) : null; } catch { ruta = null; }
  const h = new Headers({ Location: `${url.origin}${ruta ?? rutasCuenta(sitio).despues}`, "Cache-Control": "no-store" });
  for (const c of [cookieSesion, cookie("", 0), ...otras]) h.append("Set-Cookie", c);
  return new Response(null, { status: 303, headers: h });
}
