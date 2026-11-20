// Cancelar un pedido pago desde la administración (solo «admin»), por un arrepentimiento o a pedido
// del cliente. La tienda libera la reserva y deja la acción «cancelar» para Odoo: si no se retiró,
// Odoo cancela el pedido (y devuelve al depósito lo que ya estaba separado); si se retiró, prepara la
// devolución para cuando el cliente traiga la mercadería. El dinero se devuelve a mano por el medio
// de pago (Odoo deja la tarea) hasta tener la API de Mercado Pago.
import { env } from "cloudflare:workers";
import { miembroActual, puede, registrar } from "../../../servidor/equipo";
import { aleatorio } from "../../../servidor/panel";
import { evento, inventario } from "../../../servidor/pedidos";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";
import { CANCELABLES } from "../../../servidor/estados";

export const prerender = false;


export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const yo = await miembroActual(env.DB, request);
  if (!yo) return Response.redirect(`${url.origin}/admin/ingresar`, 303);
  if (!puede(yo, "admin")) return error(403, "Sin permiso");
  const f = await request.formData();
  const codigo = String(f.get("codigo") ?? "");
  if (!/^AR-[0-9A-F]{8}$/.test(codigo)) return error(400, "Código inválido");
  const nota = String(f.get("nota") ?? "").replace(/\s+/g, " ").trim().slice(0, 300) || null;
  type A = { pedido: string; email: string };
  const a = await env.DB.prepare("SELECT pedido, email FROM arrepentimientos WHERE codigo = ? AND resuelto IS NULL").bind(codigo).first<A>();
  if (!a) return Response.redirect(`${url.origin}/admin/arrepentimientos`, 303);
  // El pedido tiene que ser de ese número y de ese mail, y estar cobrado
  type P = { id: string; numero: number; estado: string; total: number; pago_medio: string | null; pago_id: string | null };
  const p = await env.DB.prepare(`SELECT id, numero, estado, total, pago_medio, pago_id FROM pedidos
      WHERE 'W-' || printf('%04d', numero) = ? AND email = ? AND pagado IS NOT NULL`).bind(a.pedido, a.email).first<P>();
  if (!p || !CANCELABLES.includes(p.estado)) return error(409, "Ese pedido no se puede cancelar (no está cobrado o ya se canceló)");
  const retirado = p.estado === "retirado";
  const ts = new Date().toISOString();
  const datos = { quien: yo.nombre, retirado, monto: p.total, pago: [p.pago_medio, p.pago_id].filter(Boolean).join(" ") };
  // Si todavía no llegó a Odoo, igual queda la acción: el conector la aplica cuando el pedido exista
  // en Odoo. Un pedido cancelado antes de eso ya no se manda (no está en «pagado»).
  // Primero el estado (con el que tenía: si cambió mientras tanto, no se hace nada) y después el resto
  const r = await env.DB.prepare("UPDATE pedidos SET estado = ?, actualizado = ? WHERE id = ? AND estado = ?")
    .bind(retirado ? "devolucion" : "cancelado", ts, p.id, p.estado).run();
  if (!r.meta.changes) return error(409, "El pedido cambió mientras tanto: volvé a intentar");
  await env.DB.batch([
    env.DB.prepare("INSERT INTO acciones (id, pedido_id, tipo, datos, empleado_id, creada) VALUES (?, ?, 'cancelar', ?, 0, ?)")
      .bind(aleatorio(16), p.id, JSON.stringify(datos), ts),
    env.DB.prepare("UPDATE arrepentimientos SET resuelto = ?, resuelto_por = ?, nota = ? WHERE codigo = ? AND resuelto IS NULL")
      .bind(ts, yo.nombre, `Pedido ${retirado ? "con devolución por recibir" : "cancelado"}${nota ? `. ${nota}` : ""}`, codigo),
    registrar(env.DB, yo, `canceló el pedido ${a.pedido} (arrepentimiento ${codigo})`),
  ]);
  if (!retirado) await inventario(env).cancelar(p.id);
  await evento(env.DB, p.id, `cancelado desde la administración (${yo.nombre})${retirado ? ": devolución por recibir" : ""}`);
  return Response.redirect(`${url.origin}/admin/arrepentimientos`, 303);
}
