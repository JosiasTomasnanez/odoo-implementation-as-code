// Protección contra bots y abusos en lo que puede llamar cualquiera (armar pedido, pagos).
import { error } from "./respuestas.ts";

/** ¿Esta tienda es la demo o una local? Sale de ORIGEN (configuración del Worker, no del pedido):
 *  demo.…, …-demo.…, localhost. Lo de prueba (pago simulado, claves de prueba de Turnstile) solo
 *  anda ahí, aunque alguien copie la configuración de la demo a producción (revisión 16/11). */
export function esDemo(env: Env): boolean {
  const origen = (env as unknown as { ORIGEN?: string }).ORIGEN ?? "";
  let host = "";
  try { host = new URL(origen).hostname; } catch { return false; }
  return /^demo\.|-demo\.|^localhost$|^127\.0\.0\.1$/.test(host);
}

/** Claves de prueba de Turnstile publicadas por Cloudflare (empiezan con 1x, 2x o 3x y siguen con ceros). */
export const claveDePrueba = (k: string | undefined) => !!k && /^[123]x0{10,}/.test(k);

/** Turnstile (anti-bots de Cloudflare). Sin clave configurada se rechaza: nunca se saltea. */
export async function turnstileValido(env: Env, token: string, ip: string | null): Promise<boolean> {
  const secreto = env.TURNSTILE_SECRET;
  if (!secreto || !token) return false;
  if (claveDePrueba(secreto) && !esDemo(env)) {
    console.log("Turnstile: clave de PRUEBA fuera de la demo; se rechaza (configurar la clave real)");
    return false;
  }
  const datos = new FormData();
  datos.append("secret", secreto);
  datos.append("response", token);
  if (ip) datos.append("remoteip", ip);
  const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: datos });
  if (!r.ok) return false;
  const d = (await r.json()) as { success?: boolean };
  return d.success === true;
}

/** Límite por IP (binding de rate limiting del Worker). Devuelve una respuesta 429 si se pasó. */
export async function limitar(limite: RateLimit | undefined, clave: string): Promise<Response | null> {
  if (!limite) return null;
  const { success } = await limite.limit({ key: clave });
  return success ? null : error(429, "Demasiados intentos. Probá de nuevo en un minuto.");
}

/** Solo se aceptan pedidos de la propia tienda (no de otro sitio que use el navegador del cliente). */
export function mismoOrigen(req: Request, url: URL): boolean {
  const origen = req.headers.get("origin");
  return !!origen && origen === url.origin;
}
