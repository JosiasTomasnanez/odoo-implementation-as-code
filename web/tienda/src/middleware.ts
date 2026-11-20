// Elige el sitio por el dominio. En el sitio mayorista, las direcciones se sirven desde
// src/pages/mayoristas/ (la tienda no se ve desde ahí); en la tienda, /mayoristas no existe.
// También pone las cabeceras de seguridad en TODO lo que arma el Worker (public/_headers solo cubre
// los archivos fijos): CSP, HSTS, sin iframes ajenos, etc. En la demo, además, «no indexar». La CSP
// permite Turnstile y el medidor de visitas de Cloudflare (Web Analytics, sin cookies).
import { defineMiddleware } from "astro:middleware";
import { rutaMayorista, sitioDe } from "./servidor/sitio";

const SEGURIDAD: Record<string, string> = {
  "Content-Security-Policy": "default-src 'none'; script-src 'self' https://challenges.cloudflare.com https://static.cloudflareinsights.com; frame-src https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://cloudflareinsights.com; manifest-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'self' https://accounts.google.com; frame-ancestors 'none'",
  "Strict-Transport-Security": "max-age=31536000",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
};

function conSeguridad(r: Response, url: URL): Response {
  // Las respuestas de redirección tienen las cabeceras inmutables: se copian
  const out = new Response(r.body, r);
  for (const [k, v] of Object.entries(SEGURIDAD)) if (!out.headers.has(k)) out.headers.set(k, v);
  // Lo que el navegador guarda un rato (portada, rubros, fichas) lleva el encabezado de la cuenta:
  // al ingresar o salir cambia la cookie y no debe mostrarse la copia de antes.
  if (/private.*max-age=[1-9]/.test(out.headers.get("Cache-Control") ?? "")) out.headers.append("Vary", "Cookie");
  if (/(^|[.-])demo\./.test(url.hostname)) out.headers.set("X-Robots-Tag", "noindex, nofollow");
  return out;
}

export const onRequest = defineMiddleware(async (ctx, next) => {
  const sitio = sitioDe(ctx.url);
  ctx.locals.sitio = sitio;
  const path = ctx.url.pathname;
  let r: Response;
  if (sitio === "tienda") {
    r = /^\/mayoristas(\/|$)/.test(path) ? await ctx.rewrite("/404") : await next();
  } else {
    const interna = rutaMayorista(path);
    r = interna ? await ctx.rewrite(interna + ctx.url.search) : await next();
  }
  return conSeguridad(r, ctx.url);
});
