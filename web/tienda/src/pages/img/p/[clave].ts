// Fotos de productos desde R2. La clave cambia si cambia la foto: se puede guardar en caché para siempre.
// «<clave>-400» y «<clave>-800» son las versiones livianas (WebP); si todavía no están, va la original
// con caché corta (así, cuando se suben, se empiezan a usar). La variante va en la ruta y no en un
// ?query: el caché del borde de Cloudflare ignora el ?query.
import { env } from "cloudflare:workers";
export const prerender = false;

export async function GET({ params }: { params: { clave?: string } }) {
  const m = /^([0-9a-f]{40,64})(?:-(400|800))?$/.exec(params.clave ?? "");
  if (!m) return new Response("No encontrada", { status: 404 });
  const [clave, base, ancho] = m;
  let obj = await env.IMAGENES.get(`productos/${clave}`);
  let respaldo = false;
  if (!obj && ancho) { obj = await env.IMAGENES.get(`productos/${base}`); respaldo = true; }
  if (!obj) return new Response("No encontrada", { status: 404 });
  return new Response(obj.body, {
    headers: {
      "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream",
      "Cache-Control": respaldo ? "public, max-age=300" : "public, max-age=31536000, immutable",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
