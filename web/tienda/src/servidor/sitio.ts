// Dos sitios en el mismo Worker (ADR 0035): la tienda (comercio-ejemplo.example, demo.…) y el sitio
// mayorista (mayoristas.comercio-ejemplo.example, mayoristas-demo.…). Comparten catálogo, stock, reservas
// y pedidos; cada uno tiene sus páginas y su sesión (la cookie es de cada dominio).
export type Sitio = "tienda" | "mayorista";

export const sitioDe = (url: URL): Sitio => (/^mayoristas[.-]/.test(url.hostname) ? "mayorista" : "tienda");

/** A dónde mandar después de cada paso de la cuenta, según el sitio. */
export const rutasCuenta = (s: Sitio) =>
  s === "mayorista"
    ? { ingreso: "/ingresar", despues: "/", salir: "/ingresar" }
    : { ingreso: "/cuenta", despues: "/", salir: "/" };

// En el sitio mayorista se atiende esto tal cual; todo lo demás se busca en src/pages/mayoristas/.
const COMPARTIDO = /^\/(api|img|pedido|pago|legales|arrepentimiento|_astro|_image|robots\.txt)(\/|$)/; // robots.txt: el mismo archivo arma el de cada sitio

// Páginas de la tienda que el sitio mayorista usa tal cual (deciden por Astro.locals.sitio).
const PROPIAS: Record<string, string> = { "/pedidos": "/cuenta/pedidos", "/pedidos/": "/cuenta/pedidos", "/compra": "/compra", "/compra/": "/compra" };
const INTERNAS = new Set(Object.values(PROPIAS));

/** Ruta interna para una dirección del sitio mayorista, o null si va tal cual. */
export function rutaMayorista(path: string): string | null {
  if (COMPARTIDO.test(path) || INTERNAS.has(path) || path.startsWith("/mayoristas/") || path === "/mayoristas") return null;
  return PROPIAS[path] ?? `/mayoristas${path}`;
}
