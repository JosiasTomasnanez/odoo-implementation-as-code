// Un botón del panel: cambia el estado del pedido y deja la acción para que el conector la aplique
// en Odoo. Solo con sesión de empleado en un dispositivo habilitado, y solo las transiciones válidas.
import { env } from "cloudflare:workers";
import { sesion, aleatorio } from "../../../servidor/panel";
import { evento } from "../../../servidor/pedidos";
import { mailFaltante, mailListo } from "../../../servidor/mails";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;

const DESDE: Record<string, string[]> = {
  preparar: ["pagado", "en_odoo", "pagado_faltante"],
  listo: ["preparando", "faltante"],
  faltante: ["preparando", "en_odoo", "pagado_faltante"],
  retirado: ["listo"],
};
const HACIA: Record<string, string> = { preparar: "preparando", listo: "listo", faltante: "faltante", retirado: "retirado" };

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const s = await sesion(env.DB, request);
  if (!s) return Response.redirect(`${url.origin}/panel`, 303);
  const f = await request.formData();
  const pedidoId = String(f.get("pedido") ?? ""), tipo = String(f.get("tipo") ?? "");
  if (!/^[0-9a-f]{32}$/.test(pedidoId) || !Object.hasOwn(DESDE, tipo)) return error(400, "Acción inválida");
  type P = { id: string; numero: number; token: string; nombre: string; email: string; total: number; estado: string; odoo_id: number | null };
  const p = await env.DB.prepare("SELECT id, numero, token, nombre, email, total, estado, odoo_id FROM pedidos WHERE id = ?").bind(pedidoId).first<P>();
  if (!p || !DESDE[tipo].includes(p.estado)) return Response.redirect(`${url.origin}/panel`, 303);
  if (tipo === "listo" && !p.odoo_id) return Response.redirect(`${url.origin}/panel`, 303);
  const ts = new Date().toISOString();
  const lineas = (await env.DB.prepare("SELECT producto_id, nombre, cantidad, precio FROM pedido_lineas WHERE pedido_id = ?").bind(p.id)
    .all<{ producto_id: number; nombre: string; cantidad: number; precio: number }>()).results;
  let datos: Record<string, number> | null = null;
  const s2: D1PreparedStatement[] = [];
  if (tipo === "faltante") {
    datos = {};
    for (const l of lineas) {
      const v = Number(f.get(`hay_${l.producto_id}`));
      const hay = Number.isInteger(v) ? Math.max(0, Math.min(l.cantidad, v)) : l.cantidad;
      datos[String(l.producto_id)] = hay;
      s2.push(env.DB.prepare("UPDATE pedido_lineas SET disponible = ? WHERE pedido_id = ? AND producto_id = ?").bind(hay, p.id, l.producto_id));
    }
    if (lineas.every((l) => datos![String(l.producto_id)] >= l.cantidad)) return Response.redirect(`${url.origin}/panel`, 303);
  }
  await env.DB.batch([
    ...s2,
    env.DB.prepare(`UPDATE pedidos SET estado = ?, actualizado = ?${tipo === "listo" ? ", listo = ?" : tipo === "retirado" ? ", retirado = ?" : ""} WHERE id = ? AND estado = ?`)
      .bind(...[HACIA[tipo], ts, ...(tipo === "listo" || tipo === "retirado" ? [ts] : []), p.id, p.estado]),
    env.DB.prepare("INSERT INTO acciones (id, pedido_id, tipo, datos, empleado_id, creada) VALUES (?, ?, ?, ?, ?, ?)")
      .bind(aleatorio(16), p.id, tipo, datos ? JSON.stringify(datos) : null, s.empleado_id, ts),
  ]);
  await evento(env.DB, p.id, `${tipo} (${s.nombre}, ${s.dispositivo.nombre})`);
  if (tipo === "listo") await mailListo(env, url.origin, p);
  if (tipo === "faltante") await mailFaltante(env, url.origin, p, lineas.map((l) => ({ ...l, disponible: datos![String(l.producto_id)] })));
  return Response.redirect(`${url.origin}/panel`, 303);
}
