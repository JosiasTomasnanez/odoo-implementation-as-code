// Datos públicos de los productos del carrito (nombre, precio, foto, si se puede vender). En el
// sitio mayorista, con cuenta aprobada, con los precios de su lista.
import { env } from "cloudflare:workers";
import { conLista, porSlugs, preciosDeLista, primeraValida } from "../../servidor/consultas";
import { clienteActual } from "../../servidor/clientes";
import { sitioDe } from "../../servidor/sitio";
export const prerender = false;

export async function GET({ url, request }: { url: URL; request: Request }) {
  const slugs = (url.searchParams.get("slugs") ?? "").split(",").slice(0, 100);
  let items = await porSlugs(env.DB, slugs);
  if (sitioDe(url) === "mayorista") {
    const c = await clienteActual(env.DB, request);
    if (!(c?.mayorista === "aprobado" && c.lista_id)) return Response.json([], { status: 403, headers: { "Cache-Control": "no-store" } });
    const precios = await preciosDeLista(env.DB, c.lista_id, items.map((p) => p.id));
    items = items.map((p) => conLista(p, precios));
  }
  // Cuánto hay para vender ahora (sin contar reservas en curso), solo cuando queda POCO (hasta 10):
  // el carrito avisa «quedan N» antes de pagar, sin publicar el stock exacto de todo el catálogo.
  // null = hay más de 10, no se controla el stock o es «a consultar». Al pagar se comprueba siempre.
  const POCO = 10;
  const hay = new Map<number, number | null>();
  if (items.length) {
    const r = await env.DB.prepare(`SELECT producto_id, controla, libre_odoo - margen AS libre FROM stock WHERE producto_id IN (${items.map(() => "?").join(",")})`)
      .bind(...items.map((p) => p.id)).all<{ producto_id: number; controla: number; libre: number }>();
    for (const f of r.results) {
      const libre = Math.max(0, Math.floor(f.libre));
      hay.set(f.producto_id, f.controla && libre <= POCO ? libre : null);
    }
  }
  return Response.json(items.map((p) => ({
    hay: p.consultar ? null : hay.get(p.id) ?? null,
    slug: p.slug, nombre: p.nombre, unidad: p.unidad, imagen: p.imagen, categoria: p.categoria,
    precio: p.precio, precio_anterior: p.precio_anterior, vendible: p.consultar || p.disponible, consultar: p.consultar,
    ...(p.minimo !== undefined ? { desde: primeraValida(p), paso: p.bulto && p.bulto > 1 ? p.bulto : 1 } : {}),
  })), { headers: { "Cache-Control": "no-store" } });
}
