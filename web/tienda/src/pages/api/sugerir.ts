// Sugerencias del buscador mientras se escribe: hasta 6 productos y las categorías que coinciden.
// Solo datos públicos (los mismos de la búsqueda).
import { env } from "cloudflare:workers";
import { buscar, rubros } from "../../servidor/consultas";
export const prerender = false;

const norm = (t: string) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

export async function GET({ url }: { url: URL }) {
  const q = (url.searchParams.get("q") ?? "").slice(0, 60).trim();
  const cab = { "Cache-Control": "private, max-age=60" };
  if (q.length < 2) return Response.json({ productos: [], categorias: [] }, { headers: cab });
  const [r, cats] = await Promise.all([buscar(env.DB, q, { filtro: "todos", orden: "rel", pagina: 1 }), rubros(env.DB)]);
  const n = norm(q);
  return Response.json({
    productos: r.items.slice(0, 6).map((p) => ({ slug: p.slug, nombre: p.nombre, precio: p.precio, imagen: p.imagen, categoria: p.categoria })),
    categorias: cats.filter((c) => norm(c.nombre).includes(n)).slice(0, 3).map((c) => ({ slug: c.slug, nombre: c.nombre })),
    total: r.total,
  }, { headers: cab });
}
