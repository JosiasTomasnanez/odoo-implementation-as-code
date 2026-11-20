// Aplica en D1 un lote del conector (ADR 0033). Todo en un solo batch: o entra el lote entero o
// nada. Siempre con consultas preparadas (bind): ningún dato se pega dentro del SQL.
import type { Lote } from "./esquemas.ts";
import { hashPin } from "./panel.ts";

export function slugify(t: string): string {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 70).replace(/-$/, "") || "producto";
}

export type Resultado = { repetido: boolean; imagenes_faltantes: string[] };

export async function aplicarLote(db: D1Database, lote: Lote, ahora = new Date().toISOString(), pepper = ""): Promise<Resultado> {
  const ya = await db.prepare("SELECT 1 FROM lotes_sync WHERE numero = ?").bind(lote.numero).first();
  if (ya) return { repetido: true, imagenes_faltantes: await faltantes(db, lote) };

  const s: D1PreparedStatement[] = [];
  // Odoo manda siempre todas las listas que viajan: las que ya no están dejan de ser públicas.
  if (lote.listas.length) {
    const ids = lote.listas.map((l) => l.id);
    s.push(db.prepare(`UPDATE listas_precios SET publica = 0 WHERE id_odoo NOT IN (${ids.map(() => "?").join(",")})`).bind(...ids));
  }
  for (const l of lote.listas) {
    s.push(db.prepare(`INSERT INTO listas_precios (id_odoo, nombre, publica) VALUES (?, ?, ?)
      ON CONFLICT(id_odoo) DO UPDATE SET nombre = excluded.nombre, publica = excluded.publica`).bind(l.id, l.nombre, l.publica ? 1 : 0));
  }
  for (const c of lote.categorias) {
    s.push(db.prepare(`INSERT INTO categorias (id_odoo, nombre, slug, padre_id, orden, actualizado) VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(id_odoo) DO UPDATE SET nombre = excluded.nombre, slug = excluded.slug, padre_id = excluded.padre_id,
      orden = excluded.orden, actualizado = excluded.actualizado`).bind(c.id, c.nombre, `${slugify(c.nombre)}-${c.id}`, c.padre_id, c.orden, ahora));
  }
  for (const id of lote.categorias_borradas) {
    s.push(db.prepare("UPDATE productos SET categoria_id = NULL WHERE categoria_id = ?").bind(id));
    s.push(db.prepare("DELETE FROM categorias WHERE id_odoo = ?").bind(id));
  }
  for (const p of lote.productos) {
    const slug = `${slugify(p.nombre)}-${p.id}`;
    // La categoría puede no haber llegado todavía: se guarda igual (sin clave foránea estricta en la práctica).
    s.push(db.prepare(`INSERT INTO productos (id_odoo, slug, nombre, codigo, referencia, categoria_id, unidad, descripcion,
        imagen, publicado, consultar, dias_encargo, nuevo_hasta, bulto, actualizado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id_odoo) DO UPDATE SET slug = excluded.slug, nombre = excluded.nombre, codigo = excluded.codigo,
        referencia = excluded.referencia, categoria_id = excluded.categoria_id, unidad = excluded.unidad,
        descripcion = excluded.descripcion, imagen = excluded.imagen, publicado = excluded.publicado,
        consultar = excluded.consultar, dias_encargo = excluded.dias_encargo, nuevo_hasta = excluded.nuevo_hasta,
        bulto = excluded.bulto, actualizado = excluded.actualizado`)
      .bind(p.id, slug, p.nombre, p.codigo, p.referencia, p.categoria_id, p.unidad, p.descripcion, p.imagen,
        p.publicado ? 1 : 0, p.consultar ? 1 : 0, p.dias_encargo, p.nuevo_hasta, p.bulto ?? null, ahora));
    s.push(db.prepare("DELETE FROM precios WHERE producto_id = ?").bind(p.id));
    for (const pr of p.precios) {
      s.push(db.prepare(`INSERT INTO precios (producto_id, lista_id, precio, precio_anterior, oferta_hasta, minimo) VALUES (?, ?, ?, ?, ?, ?)`)
        .bind(p.id, pr.lista_id, pr.precio, pr.precio_anterior, pr.oferta_hasta, pr.minimo ?? 1));
    }
    s.push(db.prepare(`INSERT INTO stock (producto_id, libre_odoo, margen, controla, actualizado) VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(producto_id) DO UPDATE SET libre_odoo = excluded.libre_odoo, margen = excluded.margen,
        controla = excluded.controla, actualizado = excluded.actualizado`)
      .bind(p.id, p.stock_libre ?? 0, p.margen, p.stock_libre === null ? 0 : 1, ahora));
    s.push(db.prepare("DELETE FROM productos_busqueda WHERE rowid = ?").bind(p.id));
    if (p.publicado) {
      s.push(db.prepare(`INSERT INTO productos_busqueda (rowid, nombre, marca, codigo, referencia, categoria)
        VALUES (?, ?, '', ?, ?, COALESCE((SELECT nombre FROM categorias WHERE id_odoo = ?), ''))`)
        .bind(p.id, p.nombre, p.codigo ?? "", p.referencia ?? "", p.categoria_id));
    }
  }
  for (const id of lote.productos_borrados) {
    s.push(db.prepare("UPDATE productos SET publicado = 0, actualizado = ? WHERE id_odoo = ?").bind(ahora, id));
    s.push(db.prepare("DELETE FROM productos_busqueda WHERE rowid = ?").bind(id));
  }
  for (const e of lote.empleados) {
    const h = e.activo && e.pin && pepper ? await hashPin(pepper, e.id, e.pin) : null;
    s.push(db.prepare(`INSERT INTO empleados (id_odoo, nombre, pin_hash, activo) VALUES (?, ?, ?, ?)
      ON CONFLICT(id_odoo) DO UPDATE SET nombre = excluded.nombre, pin_hash = excluded.pin_hash, activo = excluded.activo`)
      .bind(e.id, e.nombre, h, h ? 1 : 0));
    if (!h) s.push(db.prepare("DELETE FROM sesiones_panel WHERE empleado_id = ?").bind(e.id));
  }
  const cambios = lote.productos.length + lote.productos_borrados.length + lote.categorias.length + lote.categorias_borradas.length;
  s.push(db.prepare("INSERT INTO lotes_sync (numero, recibido, cambios) VALUES (?, ?, ?)").bind(lote.numero, ahora, cambios));
  await db.batch(s);
  return { repetido: false, imagenes_faltantes: await faltantes(db, lote) };
}

/** Fotos que el conector tiene que subir: las que no están o están sin sus versiones livianas. */
async function faltantes(db: D1Database, lote: Lote): Promise<string[]> {
  const claves = [...new Set(lote.productos.filter((p) => p.publicado && p.imagen).map((p) => p.imagen!))];
  if (!claves.length) return [];
  const hay = new Set<string>();
  for (let i = 0; i < claves.length; i += 90) {
    const parte = claves.slice(i, i + 90);
    const r = await db.prepare(`SELECT clave FROM imagenes WHERE variantes = 1 AND clave IN (${parte.map(() => "?").join(",")})`).bind(...parte).all<{ clave: string }>();
    r.results.forEach((x) => hay.add(x.clave));
  }
  return claves.filter((c) => !hay.has(c));
}

/** Tipo de imagen por sus primeros bytes (no por lo que diga quien la manda). */
export function tipoImagen(b: Uint8Array): string | null {
  if (b.length > 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b.length > 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  if (b.length > 12 && b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 && b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50) return "image/webp";
  return null;
}
