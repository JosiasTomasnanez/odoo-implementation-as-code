// Lecturas del catálogo para las páginas (siempre con consultas preparadas). Los precios son los
// de la lista pública («Tienda online»), en centavos y con IVA.

export type Vista = {
  id: number; slug: string; nombre: string; codigo: string | null; referencia: string | null; categoria_id: number | null;
  categoria: string | null; categoria_slug: string | null; unidad: string; descripcion: string | null;
  imagen: string | null; consultar: boolean; nuevo: boolean; dias_encargo: number | null;
  precio: number; precio_anterior: number | null; oferta_hasta: string | null; disponible: boolean;
  bulto: number | null;
  /** Stock libre para vender (libre de Odoo − margen); null si el producto no controla stock. */
  libre: number | null;
  /** Solo con la lista de un mayorista: desde cuántas unidades se vende (ver cantidadValida). */
  minimo?: number;
};
export type Rubro = { id: number; nombre: string; slug: string; productos: number; max_descuento: number };

const COLUMNAS = `
  SELECT p.id_odoo AS id, p.slug, p.nombre, p.codigo, p.referencia, p.categoria_id, c.nombre AS categoria, c.slug AS categoria_slug,
         p.unidad, p.descripcion, p.imagen, p.consultar, p.dias_encargo, p.bulto,
         (p.nuevo_hasta IS NOT NULL AND p.nuevo_hasta >= date('now')) AS nuevo,
         pr.precio, pr.precio_anterior, pr.oferta_hasta,
         (s.controla = 0 OR s.libre_odoo - s.margen > 0) AS disponible,
         CASE WHEN s.controla = 0 THEN NULL ELSE s.libre_odoo - s.margen END AS libre`;
const DESDE = `
    FROM productos p
    JOIN precios pr ON pr.producto_id = p.id_odoo AND pr.lista_id = (SELECT id_odoo FROM listas_precios WHERE publica = 1 LIMIT 1)
    LEFT JOIN stock s ON s.producto_id = p.id_odoo
    LEFT JOIN categorias c ON c.id_odoo = p.categoria_id`;
const SELECT = `${COLUMNAS} ${DESDE}
   WHERE p.publicado = 1`;

type Fila = Omit<Vista, "consultar" | "nuevo" | "disponible"> & { consultar: number; nuevo: number; disponible: number | null };
// «Unidades» (nombre de la unidad en Odoo) se muestra como «unidad»: «$ 2.450 por unidad».
const unidad = (u: string) => (/^(unidades?|units?)$/i.test(u.trim()) ? "unidad" : u.toLowerCase());
const vista = (f: Fila): Vista => ({ ...f, unidad: unidad(f.unidad), consultar: !!f.consultar, nuevo: !!f.nuevo, disponible: f.disponible !== 0 });

export async function rubros(db: D1Database): Promise<Rubro[]> {
  const r = await db.prepare(`
    SELECT c.id_odoo AS id, c.nombre, c.slug, COUNT(p.id_odoo) AS productos,
           COALESCE(MAX(CASE WHEN pr.precio_anterior > 0 THEN ROUND((1.0 - pr.precio * 1.0 / pr.precio_anterior) * 100) END), 0) AS max_descuento
      FROM categorias c
      JOIN productos p ON p.categoria_id = c.id_odoo AND p.publicado = 1
      JOIN precios pr ON pr.producto_id = p.id_odoo AND pr.lista_id = (SELECT id_odoo FROM listas_precios WHERE publica = 1 LIMIT 1)
     GROUP BY c.id_odoo ORDER BY c.orden, c.nombre`).all<Rubro>();
  return r.results;
}

export async function rubroPorSlug(db: D1Database, slug: string) {
  return db.prepare("SELECT id_odoo AS id, nombre, slug FROM categorias WHERE slug = ?").bind(slug).first<{ id: number; nombre: string; slug: string }>();
}

/** Productos de un rubro (sin paginar: para «Más de …» en la ficha). */
export async function deRubro(db: D1Database, id: number, limite = 500): Promise<Vista[]> {
  const r = await db.prepare(`${SELECT} AND p.categoria_id = ? ORDER BY disponible DESC, p.nombre LIMIT ?`).bind(id, limite).all<Fila>();
  return r.results.map(vista);
}

export async function ofertas(db: D1Database, limite = 60): Promise<Vista[]> {
  const r = await db.prepare(`${SELECT} AND pr.precio_anterior > pr.precio
    ORDER BY (1.0 - pr.precio * 1.0 / pr.precio_anterior) DESC LIMIT ?`).bind(limite).all<Fila>();
  return r.results.map(vista);
}

// ---------- Listados paginados (rubro, ofertas, búsqueda) ----------
// Filtro y orden van en la dirección (?filtro=stock&orden=menor&pagina=2): se pueden compartir,
// el botón «atrás» funciona y no hace falta JavaScript. Todo validado contra listas cerradas.
export const POR_PAGINA = 48;
export const FILTROS = { todos: "Todos", oferta: "En oferta", stock: "Hay en el local" } as const;
export const ORDENES = { rel: "Más relevantes", menor: "Menor precio", mayor: "Mayor precio" } as const;
export type Filtro = keyof typeof FILTROS;
export type Orden = keyof typeof ORDENES;
export type Opciones = { filtro: Filtro; orden: Orden; pagina: number };
export type Pagina = { items: Vista[]; total: number; pagina: number; paginas: number; cuantos: Record<Filtro, number>; aproximado?: boolean } & Opciones;

export function opcionesDe(u: URL): Opciones {
  const f = u.searchParams.get("filtro") ?? "", o = u.searchParams.get("orden") ?? "";
  const n = Number(u.searchParams.get("pagina") ?? "1");
  return {
    filtro: Object.hasOwn(FILTROS, f) ? (f as Filtro) : "todos",
    orden: Object.hasOwn(ORDENES, o) ? (o as Orden) : "rel",
    pagina: Number.isInteger(n) && n >= 1 && n <= 10_000 ? n : 1,
  };
}

const ES_OFERTA = "(pr.precio_anterior > pr.precio)";
const HAY = "(COALESCE(s.controla = 0 OR s.libre_odoo - s.margen > 0, 1) AND p.consultar = 0)";
const CONDICION: Record<Filtro, string> = { todos: "", oferta: ` AND ${ES_OFERTA}`, stock: ` AND ${HAY}` };

/** Un listado: `donde` y `relevancia` son SQL fijo de este archivo; los valores van siempre en `binds`. */
// `binds`: los valores del JOIN y del WHERE, en ese orden; `bindsRel`: los de `relevancia` (solo si se ordena por ella).
async function listado(db: D1Database, op: Opciones, donde: string, binds: unknown[], relevancia: string, union = "", bindsRel: unknown[] = [], porPagina = POR_PAGINA): Promise<Pagina> {
  const c = await db.prepare(`SELECT COUNT(*) AS todos, COALESCE(SUM(${ES_OFERTA}), 0) AS oferta, COALESCE(SUM(${HAY}), 0) AS stock
    ${DESDE} ${union} WHERE p.publicado = 1 ${donde}`).bind(...binds).first<Record<Filtro, number>>();
  const cuantos = { todos: c?.todos ?? 0, oferta: c?.oferta ?? 0, stock: c?.stock ?? 0 };
  const total = cuantos[op.filtro];
  const paginas = Math.max(1, Math.ceil(total / porPagina));
  const pagina = Math.min(op.pagina, paginas);
  const orden = op.orden === "menor" ? "pr.precio ASC, p.nombre" : op.orden === "mayor" ? "pr.precio DESC, p.nombre" : relevancia;
  const r = total ? await db.prepare(`${COLUMNAS} ${DESDE} ${union} WHERE p.publicado = 1 ${donde}${CONDICION[op.filtro]}
    ORDER BY ${orden} LIMIT ? OFFSET ?`).bind(...binds, ...(op.orden === "rel" ? bindsRel : []), porPagina, (pagina - 1) * porPagina).all<Fila>() : { results: [] };
  return { items: r.results.map(vista), total, pagina, paginas, cuantos, filtro: op.filtro, orden: op.orden };
}

export const listadoRubro = (db: D1Database, id: number, op: Opciones, porPagina = POR_PAGINA) =>
  listado(db, op, "AND p.categoria_id = ?", [id], "disponible DESC, p.nombre", "", [], porPagina);

export const listadoOfertas = (db: D1Database, op: Opciones) =>
  listado(db, { ...op, filtro: op.filtro === "oferta" ? "todos" : op.filtro }, `AND ${ES_OFERTA}`, [], "(1.0 - pr.precio * 1.0 / pr.precio_anterior) DESC, p.nombre");

export async function nuevos(db: D1Database, limite = 8): Promise<Vista[]> {
  const r = await db.prepare(`${SELECT} AND p.nuevo_hasta >= date('now') ORDER BY p.nuevo_hasta DESC LIMIT ?`).bind(limite).all<Fila>();
  return r.results.map(vista);
}

export async function porSlug(db: D1Database, slug: string): Promise<Vista | null> {
  const f = await db.prepare(`${SELECT} AND p.slug = ?`).bind(slug).first<Fila>();
  return f ? vista(f) : null;
}

/** Slug actual de un producto por el número del final de un slug viejo («…-123»): el slug lleva el
 *  nombre, así que cambia si en Odoo se renombra. Para redirigir los links viejos. */
export async function slugActual(db: D1Database, slugViejo: string): Promise<string | null> {
  const id = Number(/-(\d{1,12})$/.exec(slugViejo)?.[1] ?? 0);
  if (!id) return null;
  const f = await db.prepare(`${SELECT} AND p.id_odoo = ?`).bind(id).first<Fila>();
  return f && f.slug !== slugViejo ? f.slug : null;
}

export async function porSlugs(db: D1Database, slugs: string[]): Promise<Vista[]> {
  const unicos = [...new Set(slugs)].filter((s) => /^[a-z0-9-]{1,90}$/.test(s)).slice(0, 100);
  if (!unicos.length) return [];
  const r = await db.prepare(`${SELECT} AND p.slug IN (${unicos.map(() => "?").join(",")})`).bind(...unicos).all<Fila>();
  return r.results.map(vista);
}

// Palabras que no ayudan a encontrar («alimento para perro», «llave de paso», «8 x 1/2»)
const VACIAS = new Set(["a", "al", "con", "de", "del", "el", "en", "la", "las", "lo", "los", "o", "para", "por", "sin", "un", "una", "x", "y"]);
// Sinónimos de mostrador (la clave en singular y sin acentos). Se buscan como prefijo, igual que lo escrito.
const SINONIMOS: Record<string, string[]> = {
  pintura: ["latex", "esmalte", "pintur"], latex: ["pintura"], esmalte: ["pintura"],
  foco: ["lampara"], lampara: ["foco"], lamparita: ["lampara", "foco"],
  canilla: ["griferia", "grifo"], grifo: ["canilla", "griferia"], griferia: ["canilla", "grifo"],
  piscina: ["pileta"], pileta: ["piscina"], cloro: ["pileta"],
  perro: ["canino"], canino: ["perro"], gato: ["felino"], felino: ["gato"],
  comida: ["alimento", "balanceado"], alimento: ["comida", "balanceado"], balanceado: ["alimento"],
  soga: ["cuerda"], cuerda: ["soga"], taladro: ["percutor"], atornillador: ["destornillador"],
  destornillador: ["atornillador"], disyuntor: ["diferencial"], diferencial: ["disyuntor"],
  enchufe: ["toma", "ficha"], ficha: ["enchufe"], cano: ["tubo"], tubo: ["cano"],
};
/** Singular simple: «tornillos» → «tornillo», «llaves» → «llav» (se busca como prefijo). */
const raiz = (t: string) => /\d/.test(t) ? t : t.length >= 5 && t.endsWith("es") ? t.slice(0, -2) : t.length >= 4 && t.endsWith("s") ? t.slice(0, -1) : t;

export type ModoBusqueda = "y" | "corto" | "o";

/**
 * Búsqueda: cada palabra (sin acentos, solo letras y números, sin palabras vacías, en singular y
 * con sus sinónimos) como prefijo. Modos: «y» todas obligatorias; «corto» igual pero con el
 * comienzo de las palabras largas (tolera errores de tipeo al final: «tornilo» → «torni»); «o»
 * cualquiera. La consulta de FTS se arma solo con esos tokens entre comillas: no se puede inyectar
 * sintaxis. Un código completo (de barras o interno) va primero.
 */
export function consultaFts(q: string, modo: ModoBusqueda = "y"): string | null {
  const todos = q.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .split(/[^a-z0-9ñ]+/).filter((t) => t.length > 0);
  const utiles = todos.filter((t) => !VACIAS.has(t));
  const tokens = [...new Set((utiles.length ? utiles : todos).map(raiz))].slice(0, 8);
  if (!tokens.length) return null;
  const grupo = (t: string) => {
    const base = modo === "corto" && t.length >= 6 && !/\d/.test(t) ? t.slice(0, Math.max(4, t.length - 2)) : t;
    const alternativas = [...new Set([base, ...(SINONIMOS[t] ?? [])])];
    return alternativas.length > 1 ? `(${alternativas.map((x) => `"${x}"*`).join(" OR ")})` : `"${base}"*`;
  };
  return tokens.map(grupo).join(modo === "o" ? " OR " : " AND ");
}

/** Búsqueda paginada: lo que coincide con el código completo (de barras o interno) va primero. Si
 *  con todas las palabras no hay nada, prueba con el comienzo de cada una y después con cualquiera
 *  (y lo marca como «aproximado»). */
export async function buscar(db: D1Database, q: string, op: Opciones, porPagina = POR_PAGINA): Promise<Pagina> {
  const texto = q.trim().slice(0, 100);
  const vacia: Pagina = { ...op, items: [], total: 0, pagina: 1, paginas: 1, cuantos: { todos: 0, oferta: 0, stock: 0 } };
  let anterior = "";
  for (const modo of ["y", "corto", "o"] as const) {
    const fts = consultaFts(texto, modo);
    if (!fts) return vacia;
    if (fts === anterior) continue;
    anterior = fts;
    const r = await listado(db, op, "", [fts], "(p.codigo = ? OR p.referencia = ?) DESC, b.rank, p.nombre",
      "JOIN (SELECT rowid, rank FROM productos_busqueda WHERE productos_busqueda MATCH ?) b ON b.rowid = p.id_odoo", [texto, texto], porPagina);
    if (r.cuantos.todos > 0) return modo === "y" ? r : { ...r, aproximado: true };
  }
  return vacia;
}

export const descuento = (p: Pick<Vista, "precio" | "precio_anterior">) =>
  p.precio_anterior && p.precio_anterior > p.precio ? Math.round((1 - p.precio / p.precio_anterior) * 100) : 0;
export const pesos = (centavos: number) =>
  "$ " + (centavos / 100).toLocaleString("es-AR", { maximumFractionDigits: centavos % 100 ? 2 : 0, minimumFractionDigits: centavos % 100 ? 2 : 0 });

/** Ícono del rubro por su nombre (los rubros vienen de Odoo y no traen ícono). */
export function iconoDe(nombre: string | null): string {
  const n = (nombre ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const tabla: [string, string][] = [["sanit", "canilla"], ["electr", "rayo"], ["pilet", "ola"], ["pintur", "pincel"],
    ["jardin", "hoja"], ["mascot", "huella"], ["veterin", "huella"]];
  return tabla.find(([k]) => n.includes(k))?.[1] ?? "tornillo";
}

type DeLista = { precio: number; minimo: number };

/** Precios y mínimos de una lista (la mayorista del cliente) para esos productos. */
export async function preciosDeLista(db: D1Database, listaId: number, ids: number[]): Promise<Map<number, DeLista>> {
  const unicos = [...new Set(ids)].filter(Number.isInteger);
  const m = new Map<number, DeLista>();
  // D1 acepta hasta 100 parámetros por consulta: de a 90
  for (let i = 0; i < unicos.length; i += 90) {
    const parte = unicos.slice(i, i + 90);
    const r = await db.prepare(`SELECT producto_id, precio, minimo FROM precios WHERE lista_id = ? AND producto_id IN (${parte.map(() => "?").join(",")})`)
      .bind(listaId, ...parte).all<{ producto_id: number; precio: number; minimo: number }>();
    for (const x of r.results) m.set(x.producto_id, { precio: x.precio, minimo: x.minimo });
  }
  return m;
}

/** Con la lista del cliente (mayorista aprobado): su precio y su mínimo. Si la tienda lo tiene más
 *  barato por una oferta, ese precio (el mayorista nunca paga más que el público; a confirmar con
 *  Daniel, P-015). Sin el producto en su lista: el precio público, desde 1 (o un bulto). */
export function conLista(p: Vista, precios: Map<number, DeLista>): Vista {
  const suyo = precios.get(p.id);
  const minimo = suyo?.minimo ?? 1;
  // Disponible para el mayorista solo si alcanza para la primera cantidad válida (mínimo y bulto
  // entero): con 5 unidades y bultos de 12 no hay nada que pueda comprar.
  const disponible = p.disponible && (p.libre == null || p.libre >= primeraValida({ minimo, bulto: p.bulto }));
  if (!suyo || suyo.precio >= p.precio) return { ...p, precio_anterior: null, oferta_hasta: null, minimo, disponible };
  return { ...p, precio: suyo.precio, precio_anterior: null, oferta_hasta: null, minimo, disponible };
}

// ---------- Cantidades mayoristas: al menos el mínimo y en bultos enteros ----------
export type Condicion = { minimo?: number; bulto: number | null };
/** La menor cantidad que se puede pedir: el mínimo redondeado hacia arriba a bultos enteros. */
export const primeraValida = (c: Condicion) => {
  const b = c.bulto && c.bulto > 1 ? c.bulto : 1;
  return Math.ceil(Math.max(1, c.minimo ?? 1) / b) * b;
};
export const cantidadValida = (q: number, c: Condicion) => {
  const b = c.bulto && c.bulto > 1 ? c.bulto : 1;
  return Number.isInteger(q) && q >= primeraValida(c) && q % b === 0;
};
/** Cómo se vende, en palabras: «de a 1», «caja × 12», «desde 24 (cajas × 12)». */
export function comoSeVende(c: Condicion, unidad = "u."): string {
  const b = c.bulto && c.bulto > 1 ? c.bulto : 0;
  const desde = primeraValida(c);
  if (b) return desde > b ? `desde ${desde} (bultos × ${b})` : `bulto × ${b}`;
  return desde > 1 ? `desde ${desde} ${unidad}` : `por ${unidad}`;
}

export async function porCodigos(db: D1Database, codigos: string[]): Promise<Vista[]> {
  const unicos = [...new Set(codigos)].filter((c) => /^[0-9A-Za-z-]{1,32}$/.test(c)).slice(0, 100);
  if (!unicos.length) return [];
  const r = await db.prepare(`${SELECT} AND p.codigo IN (${unicos.map(() => "?").join(",")})`).bind(...unicos).all<Fila>();
  return r.results.map(vista);
}

export const contarPublicados = async (db: D1Database) =>
  (await db.prepare("SELECT COUNT(*) AS n FROM productos WHERE publicado = 1").first<{ n: number }>())?.n ?? 0;

export async function todos(db: D1Database, limite = 2000): Promise<Vista[]> {
  const r = await db.prepare(`${SELECT} ORDER BY c.orden, c.nombre, p.nombre LIMIT ?`).bind(limite).all<Fila>();
  return r.results.map(vista);
}
