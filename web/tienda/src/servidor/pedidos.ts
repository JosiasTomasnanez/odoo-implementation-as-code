// Armado del pedido, reserva y pago (ADR 0033). Los precios y el total los calcula la tienda con
// lo que hay en D1; del navegador solo se toma «qué producto y cuántos».
import { z } from "zod";
import { cantidadValida, conLista, porSlugs, preciosDeLista, primeraValida } from "./consultas.ts";
import type { Inventario } from "./inventario.ts";
import type { EstadoPago } from "./pagos.ts";

export const MINUTOS_RESERVA = 15;

export const PedidoNuevo = z.strictObject({
  lineas: z.array(z.strictObject({ slug: z.string().regex(/^[a-z0-9-]{1,90}$/), cantidad: z.number().int().min(1).max(999) })).min(1).max(100),
  nombre: z.string().trim().min(2).max(120),
  email: z.string().trim().toLowerCase().max(160).email(),
  telefono: z.string().trim().regex(/^[0-9 +()-]{6,30}$/).optional().or(z.literal("")),
  turnstile: z.string().max(4096),
});
export type PedidoNuevo = z.infer<typeof PedidoNuevo>;

const aleatorio = (bytes: number) => [...crypto.getRandomValues(new Uint8Array(bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");

export function inventario(env: Env): DurableObjectStub<Inventario> {
  return env.INVENTARIO.get(env.INVENTARIO.idFromName("principal")) as DurableObjectStub<Inventario>;
}

export async function evento(db: D1Database, pedidoId: string, que: string) {
  await db.prepare("INSERT INTO pedido_eventos (pedido_id, cuando, que) VALUES (?, ?, ?)").bind(pedidoId, new Date().toISOString(), que.slice(0, 500)).run();
}

export type Armado =
  | { ok: true; id: string; numero: number; token: string; total: number; vence: string; lineas: { nombre: string; cantidad: number; precio: number }[] }
  | { ok: false; motivo: "sin_stock"; faltantes: { slug: string; nombre: string; disponible: number }[] }
  | { ok: false; motivo: "no_disponible"; slugs: string[] }
  | { ok: false; motivo: "cantidad"; lineas: { slug: string; nombre: string; desde: number; bulto: number | null }[] };

/** Arma el pedido con los precios de la tienda y reserva todo o nada. Con `listaId` (mayorista
 *  aprobado) cada producto va con el precio de su lista; si no está en ella, el de la tienda. */
export async function armarPedido(env: Env, datos: PedidoNuevo, ahora = new Date(), listaId?: number, sitio: "tienda" | "mayorista" = "tienda"): Promise<Armado> {
  let productos = await porSlugs(env.DB, datos.lineas.map((l) => l.slug));
  if (listaId) {
    const precios = await preciosDeLista(env.DB, listaId, productos.map((p) => p.id));
    productos = productos.map((p) => conLista(p, precios));
  }
  const porSlug = new Map(productos.map((p) => [p.slug, p]));
  const cantidades = new Map<string, number>();
  for (const l of datos.lineas) cantidades.set(l.slug, Math.min(999, (cantidades.get(l.slug) ?? 0) + l.cantidad));
  const malos = [...cantidades.keys()].filter((s) => { const p = porSlug.get(s); return !p || !(p.disponible || p.consultar); });
  if (malos.length) return { ok: false, motivo: "no_disponible", slugs: malos };
  // Mayorista: nunca sueltos; al menos el mínimo de su lista y en bultos enteros
  if (listaId) {
    const mal = [...cantidades].filter(([s, q]) => !cantidadValida(q, porSlug.get(s)!)).map(([s]) => porSlug.get(s)!);
    if (mal.length) return { ok: false, motivo: "cantidad", lineas: mal.map((p) => ({ slug: p.slug, nombre: p.nombre, desde: primeraValida(p), bulto: p.bulto })) };
  }

  const lineas = [...cantidades].map(([slug, cantidad]) => { const p = porSlug.get(slug)!; return { p, cantidad }; });
  const total = lineas.reduce((t, l) => t + l.p.precio * l.cantidad, 0);
  const id = aleatorio(16), token = aleatorio(16);
  const venceMs = ahora.getTime() + MINUTOS_RESERVA * 60_000;
  const vence = new Date(venceMs).toISOString();

  const r = await inventario(env).reservar(id, lineas.map((l) => ({ producto_id: l.p.id, cantidad: l.cantidad })), venceMs);
  if (!r.ok) {
    return { ok: false, motivo: "sin_stock", faltantes: r.faltantes.map((f) => {
      const p = lineas.find((l) => l.p.id === f.producto_id)?.p;
      return { slug: p?.slug ?? "", nombre: p?.nombre ?? "", disponible: f.disponible };
    }) };
  }
  const lista = listaId ? { id_odoo: listaId } : await env.DB.prepare("SELECT id_odoo FROM listas_precios WHERE publica = 1 LIMIT 1").first<{ id_odoo: number }>();
  const n = await env.DB.prepare("UPDATE contadores SET valor = valor + 1 WHERE nombre = 'pedido' RETURNING valor").first<{ valor: number }>();
  const ts = ahora.toISOString();
  const s: D1PreparedStatement[] = [
    env.DB.prepare(`INSERT INTO pedidos (id, numero, token, estado, nombre, email, telefono, total, lista_id, creado, vence, actualizado, sitio)
      VALUES (?, ?, ?, 'pendiente_pago', ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(id, n!.valor, token, datos.nombre, datos.email, datos.telefono || null, total, lista?.id_odoo ?? 0, ts, vence, ts, sitio),
    ...lineas.map((l) => env.DB.prepare(`INSERT INTO pedido_lineas (pedido_id, producto_id, nombre, cantidad, precio, consultar) VALUES (?, ?, ?, ?, ?, ?)`)
      .bind(id, l.p.id, l.p.nombre, l.cantidad, l.p.precio, l.p.consultar ? 1 : 0)),
    env.DB.prepare("INSERT INTO pedido_eventos (pedido_id, cuando, que) VALUES (?, ?, ?)").bind(id, ts, `armado y reservado: ${lineas.length} productos, total ${total}`),
  ];
  await env.DB.batch(s);
  return { ok: true, id, numero: n!.valor, token, total, vence, lineas: lineas.map((l) => ({ nombre: l.p.nombre, cantidad: l.cantidad, precio: l.p.precio })) };
}

/**
 * Procesa un pago ya verificado contra el medio de pago. Idempotente: cada pago una sola vez.
 * Devuelve el estado en que queda el pedido.
 */
export async function procesarPago(env: Env, medio: string, pago: EstadoPago, origen = "https://comercio-ejemplo.example"): Promise<string> {
  const ts = new Date().toISOString();
  const nuevo = await env.DB.prepare(`INSERT INTO pagos (pago_id, pedido_id, medio, estado, monto, recibido) VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(pago_id) DO UPDATE SET estado = excluded.estado WHERE pagos.estado = 'pendiente' RETURNING pago_id`)
    .bind(`${medio}:${pago.pago_id}`, pago.pedido_id, medio, pago.estado, pago.monto, ts).first();
  const pedido = await env.DB.prepare("SELECT id, numero, estado, total FROM pedidos WHERE id = ?").bind(pago.pedido_id).first<{ id: string; numero: number; estado: string; total: number }>();
  if (!pedido) return "desconocido";
  const sinPagar = ["pendiente_pago", "vencido", "rechazado"];
  if (!nuevo) {
    // Ya registrado. Si era un aprobado cuyo trabajo quedó a medias (falló un paso después de
    // anotarlo), se rehace: lo que sigue es idempotente (confirmar, reservar con el mismo id, UPDATE).
    const previo = await env.DB.prepare("SELECT estado FROM pagos WHERE pago_id = ?").bind(`${medio}:${pago.pago_id}`).first<{ estado: string }>();
    const aMedias = previo?.estado === "aprobado" && pago.estado === "aprobado" && pago.monto === pedido.total && sinPagar.includes(pedido.estado);
    if (!aMedias) return pedido.estado; // ya procesado
    await evento(env.DB, pedido.id, `pago aprobado retomado (${medio} ${pago.pago_id})`);
  }
  if (pago.estado === "pendiente") return pedido.estado;
  if (pago.estado === "rechazado") {
    if (pedido.estado === "pendiente_pago") {
      await inventario(env).liberar(pedido.id);
      await env.DB.prepare("UPDATE pedidos SET estado = 'rechazado', actualizado = ? WHERE id = ? AND estado = 'pendiente_pago'").bind(ts, pedido.id).run();
      await evento(env.DB, pedido.id, `pago rechazado (${medio} ${pago.pago_id})`);
      return "rechazado";
    }
    return pedido.estado;
  }
  // Aprobado: el monto tiene que ser exactamente el del pedido
  const nro = `W-${String(pedido.numero).padStart(4, "0")}`;
  if (pago.monto !== pedido.total) {
    // Se cobró algo: la reserva se mantiene (no se libera a los 15 minutos) y se avisa al equipo
    await inventario(env).confirmar(pedido.id);
    await env.DB.prepare("UPDATE pedidos SET estado = 'revisar', actualizado = ? WHERE id = ?").bind(ts, pedido.id).run();
    await evento(env.DB, pedido.id, `pago aprobado con monto distinto: ${pago.monto} ≠ ${pedido.total} (${medio} ${pago.pago_id})`);
    const { avisarEquipo } = await import("./avisos.ts");
    await avisarEquipo(env, `Pedido ${nro}: pago con monto distinto`, `Se cobró ${pago.monto / 100} y el pedido es de ${pedido.total / 100} (${medio} ${pago.pago_id}). Revisarlo antes de prepararlo.`);
    return "revisar";
  }
  if (!sinPagar.includes(pedido.estado)) {
    // Otro pago aprobado de un pedido que ya estaba pago: el cliente pagó dos veces
    await evento(env.DB, pedido.id, `pago repetido: ${medio} ${pago.pago_id} aprobado con el pedido ya en «${pedido.estado}» → devolver`);
    const { avisarEquipo } = await import("./avisos.ts");
    await avisarEquipo(env, `Pedido ${nro}: pago repetido`, `Llegó otro pago aprobado (${medio} ${pago.pago_id}) de un pedido que ya estaba pago. Hay que devolverlo.`);
    return pedido.estado;
  }
  let estado = "pagado";
  if (!(await inventario(env).confirmar(pedido.id))) {
    // La reserva había vencido: se intenta de nuevo; si ya no hay, queda pagado con faltante
    const lineas = await env.DB.prepare("SELECT producto_id, cantidad FROM pedido_lineas WHERE pedido_id = ?").bind(pedido.id).all<{ producto_id: number; cantidad: number }>();
    const r = await inventario(env).reservar(pedido.id, lineas.results, Date.now() + 60_000);
    if (r.ok) await inventario(env).confirmar(pedido.id);
    else estado = "pagado_faltante";
  }
  await env.DB.prepare("UPDATE pedidos SET estado = ?, pagado = ?, pago_id = ?, pago_medio = ?, actualizado = ? WHERE id = ?")
    .bind(estado, ts, pago.pago_id, medio, ts, pedido.id).run();
  await evento(env.DB, pedido.id, `pago aprobado (${medio} ${pago.pago_id}) → ${estado}`);
  const datos = await env.DB.prepare("SELECT id, numero, token, nombre, email, total FROM pedidos WHERE id = ?").bind(pedido.id)
    .first<{ id: string; numero: number; token: string; nombre: string; email: string; total: number }>();
  const lineas = (await env.DB.prepare("SELECT nombre, cantidad, precio FROM pedido_lineas WHERE pedido_id = ?").bind(pedido.id)
    .all<{ nombre: string; cantidad: number; precio: number }>()).results;
  const { mailRecibido } = await import("./mails.ts");
  if (datos) await mailRecibido(env, origen, datos, lineas);
  return estado;
}

/** Tarea de cada minuto: los pedidos sin pagar cuya reserva venció. */
export async function vencerReservas(env: Env): Promise<number> {
  const ids = await inventario(env).vencer(Date.now());
  const ts = new Date().toISOString();
  for (const id of ids) {
    await env.DB.prepare("UPDATE pedidos SET estado = 'vencido', actualizado = ? WHERE id = ? AND estado = 'pendiente_pago'").bind(ts, id).run();
  }
  return ids.length;
}

/** Comparación de tiempo constante para el token del pedido. */
export function mismoToken(a: string, b: string): boolean {
  if (a.length !== b.length || !/^[0-9a-f]+$/.test(a)) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
