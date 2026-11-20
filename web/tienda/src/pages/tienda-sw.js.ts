// El service worker se sirve desde el Worker (no como archivo fijo) con «no guardar»: así cada
// versión nueva llega enseguida (los archivos fijos quedaban en la caché de Cloudflare).
import codigo from "../sw/sw.js?raw";
export const prerender = false;

export function GET() {
  return new Response(codigo, {
    headers: {
      "Content-Type": "text/javascript; charset=utf-8",
      "Cache-Control": "no-store",
      "Service-Worker-Allowed": "/",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
