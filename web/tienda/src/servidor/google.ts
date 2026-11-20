// Ingresar con Google (OpenID Connect, código de autorización con PKCE). La tienda canjea el código
// directo con Google (con su secreto), así que el id_token que vuelve es de Google; igual se revisan
// emisor, destinatario, vencimiento y que el mail esté verificado. Sin GOOGLE_CLIENT_ID no se ofrece.
import { aleatorio } from "./panel.ts";

export const COOKIE_G = "cf_google";
export const googleActivo = (env: Env) => !!(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET);

const b64url = (b: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const vuelta = (origen: string) => `${origen}/api/cuenta/google-vuelta`;

/** Dirección de Google a la que mandar al cliente y la cookie con el estado y el verificador. */
export async function inicio(env: Env, origen: string): Promise<{ ir: string; cookie: string }> {
  const estado = aleatorio(16), verificador = aleatorio(32);
  const reto = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verificador)));
  const q = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID!, redirect_uri: vuelta(origen), response_type: "code",
    scope: "openid email profile", state: estado, code_challenge: reto, code_challenge_method: "S256", prompt: "select_account",
  });
  return {
    ir: `https://accounts.google.com/o/oauth2/v2/auth?${q}`,
    cookie: `${COOKIE_G}=${estado}.${verificador}; Path=/api/cuenta; Max-Age=600; HttpOnly; Secure; SameSite=Lax`,
  };
}

export const borrarCookie = `${COOKIE_G}=; Path=/api/cuenta; Max-Age=0; HttpOnly; Secure; SameSite=Lax`;

/** Canjea el código: devuelve el usuario de Google (id, mail verificado, nombre) o null. */
export async function canje(env: Env, origen: string, req: Request, url: URL): Promise<{ sub: string; email: string; nombre: string | null } | null> {
  const c = (req.headers.get("cookie") ?? "").split(";").map((x) => x.trim()).find((x) => x.startsWith(`${COOKIE_G}=`))?.slice(COOKIE_G.length + 1) ?? "";
  const [estado, verificador] = c.split(".");
  const code = url.searchParams.get("code") ?? "";
  if (!estado || !verificador || url.searchParams.get("state") !== estado || !code || code.length > 2000) return null;
  const k = env;
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ code, client_id: k.GOOGLE_CLIENT_ID!, client_secret: k.GOOGLE_CLIENT_SECRET!, redirect_uri: vuelta(origen), grant_type: "authorization_code", code_verifier: verificador }),
  });
  if (!r.ok) return null;
  const tok = (await r.json()) as { id_token?: string };
  const partes = (tok.id_token ?? "").split(".");
  if (partes.length !== 3) return null;
  let d: { iss?: string; aud?: string; exp?: number; sub?: string; email?: string; email_verified?: boolean; name?: string };
  try { d = JSON.parse(atob(partes[1].replace(/-/g, "+").replace(/_/g, "/"))); } catch { return null; }
  const email = (d.email ?? "").trim().toLowerCase();
  if (!["https://accounts.google.com", "accounts.google.com"].includes(d.iss ?? "") || d.aud !== k.GOOGLE_CLIENT_ID
    || !d.exp || d.exp * 1000 < Date.now() || !d.sub || !/^\d{1,40}$/.test(d.sub) || d.email_verified !== true
    || !email || email.length > 160) return null;
  return { sub: d.sub, email, nombre: d.name ? d.name.replace(/\s+/g, " ").trim().slice(0, 120) : null };
}
