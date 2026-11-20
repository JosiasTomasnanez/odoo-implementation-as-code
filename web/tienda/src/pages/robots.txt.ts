// robots.txt según el sitio: la demo y el sitio mayorista no se indexan; la tienda sí, salvo las
// páginas personales, y con su mapa del sitio.
import { sitioDe } from "../servidor/sitio";
export const prerender = false;

export function GET({ url }: { url: URL }) {
  const cerrado = sitioDe(url) === "mayorista" || /(^|[.-])demo\./.test(url.hostname);
  const texto = cerrado
    ? "User-agent: *\nDisallow: /\n"
    : `User-agent: *\n${["/api/", "/cuenta", "/carrito", "/compra", "/pedido", "/pago", "/panel", "/admin", "/buscar"].map((r) => `Disallow: ${r}`).join("\n")}\n\nSitemap: ${url.origin}/sitemap.xml\n`;
  return new Response(texto, { headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "public, max-age=3600" } });
}
