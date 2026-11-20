// Listas de precios armadas en la administración (ADR 0037): una lista base de Odoo con un
// descuento general y descuentos propios por rubro o por producto. La tienda guarda las
// condiciones; los precios los calcula Odoo y vuelven con la sincronización.
export type Regla = { tipo: "rubro" | "producto"; id: number; descuento: number };
export type ListaCliente = { id: string; nombre: string; base_id: number; descuento: number; reglas: Regla[]; version: number; pendiente: number; odoo_id: number | null; resultado: string | null };
export const TOPE_REGLAS = 200;
export const descuentoValido = (d: number) => Number.isFinite(d) && d >= 0 && d <= 60;
/** «12,5» o «12.5» → 12.5 (de a medio punto). */
export const leerDescuento = (v: unknown) => Math.round(Number(String(v ?? "").replace(",", ".")) * 2) / 2;

export function leerReglas(t: string | null): Regla[] {
  try {
    const d: unknown = JSON.parse(t || "[]");
    if (!Array.isArray(d)) return [];
    return d.filter((r): r is Regla => !!r && (r.tipo === "rubro" || r.tipo === "producto") && Number.isInteger(r.id) && r.id > 0 && descuentoValido(r.descuento)).slice(0, TOPE_REGLAS);
  } catch { return []; }
}

type Fila = Omit<ListaCliente, "reglas"> & { reglas: string | null };
const armar = (f: Fila | null): ListaCliente | null => f ? { ...f, reglas: leerReglas(f.reglas) } : null;
const CAMPOS = "id, nombre, base_id, descuento, reglas, version, pendiente, odoo_id, resultado";

export const listaPorId = async (db: D1Database, id: string) =>
  armar(await db.prepare(`SELECT ${CAMPOS} FROM listas_nuevas WHERE id = ?`).bind(id).first<Fila>());
export const listaDeOdoo = async (db: D1Database, odooId: number) =>
  armar(await db.prepare(`SELECT ${CAMPOS} FROM listas_nuevas WHERE odoo_id = ?`).bind(odooId).first<Fila>());

export type Condiciones = { base: string; general: number; rubros: { id: number; nombre: string; descuento: number }[]; productos: { id: number; nombre: string; codigo: string | null; descuento: number }[] };
/** Las condiciones de una lista, con los nombres de sus rubros y productos (para mostrarlas). */
export async function condiciones(db: D1Database, l: ListaCliente): Promise<Condiciones> {
  const base = (await db.prepare("SELECT nombre FROM listas_precios WHERE id_odoo = ?").bind(l.base_id).first<{ nombre: string }>())?.nombre ?? `Lista ${l.base_id}`;
  const nombres = async (tabla: "categorias" | "productos", ids: number[]) => {
    const m = new Map<number, { nombre: string; codigo: string | null }>();
    for (let i = 0; i < ids.length; i += 90) {
      const parte = ids.slice(i, i + 90);
      const r = await db.prepare(`SELECT id_odoo, nombre, ${tabla === "productos" ? "codigo" : "NULL AS codigo"} FROM ${tabla} WHERE id_odoo IN (${parte.map(() => "?").join(",")})`)
        .bind(...parte).all<{ id_odoo: number; nombre: string; codigo: string | null }>();
      for (const x of r.results) m.set(x.id_odoo, x);
    }
    return m;
  };
  const rs = l.reglas.filter((r) => r.tipo === "rubro"), ps = l.reglas.filter((r) => r.tipo === "producto");
  const [nr, np] = await Promise.all([nombres("categorias", rs.map((r) => r.id)), nombres("productos", ps.map((r) => r.id))]);
  return {
    base, general: l.descuento,
    rubros: rs.map((r) => ({ id: r.id, nombre: nr.get(r.id)?.nombre ?? `Rubro ${r.id}`, descuento: r.descuento })).sort((a, b) => a.nombre.localeCompare(b.nombre, "es")),
    productos: ps.map((r) => ({ id: r.id, nombre: np.get(r.id)?.nombre ?? `Producto ${r.id}`, codigo: np.get(r.id)?.codigo ?? null, descuento: r.descuento })).sort((a, b) => a.nombre.localeCompare(b.nombre, "es")),
  };
}
export const pct = (d: number) => `${String(d).replace(".", ",")} %`;
/** Una línea para el cliente: «5 % en toda la lista · 12 % en Pinturería · 2 productos con descuento propio». */
export function resumen(c: Condiciones): string {
  const partes = [];
  if (c.general > 0) partes.push(`${pct(c.general)} en toda la lista`);
  for (const r of c.rubros) partes.push(`${pct(r.descuento)} en ${r.nombre}`);
  if (c.productos.length) partes.push(c.productos.length === 1 ? `${pct(c.productos[0].descuento)} en ${c.productos[0].nombre}` : `${c.productos.length} productos con descuento propio`);
  return partes.join(" · ");
}
