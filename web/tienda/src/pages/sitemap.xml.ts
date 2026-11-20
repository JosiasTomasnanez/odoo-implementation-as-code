// Mapa del sitio para buscadores: portada, categorías, ofertas y cada producto publicado.
import { env } from "cloudflare:workers";
import { sitioDe } from "../servidor/sitio";
export const prerender = false;

export async function GET({ url }: { url: URL }) {
  if (sitioDe(url) === "mayorista") return new Response("No encontrado", { status: 404 });
  const [cats, prods] = await Promise.all([
    env.DB.prepare("SELECT DISTINCT c.slug FROM categorias c JOIN productos p ON p.categoria_id = c.id_odoo AND p.publicado = 1").all<{ slug: string }>(),
    env.DB.prepare("SELECT slug FROM productos WHERE publicado = 1 ORDER BY id_odoo LIMIT 45000").all<{ slug: string }>(),
  ]);
  const rutas = ["/", "/categorias/", "/ofertas/", "/ayuda/",
    ...cats.results.map((c) => `/categoria/${c.slug}/`), ...prods.results.map((p) => `/producto/${p.slug}/`)];
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${
    rutas.map((r) => `<url><loc>${url.origin}${r}</loc></url>`).join("\n")}\n</urlset>\n`;
  return new Response(xml, { headers: { "Content-Type": "application/xml; charset=utf-8", "Cache-Control": "public, max-age=3600" } });
}
