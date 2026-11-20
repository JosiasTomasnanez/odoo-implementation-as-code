// El cliente elige qué hacer con lo que falta (desde el link del mail, con el token del pedido).
import { env } from "cloudflare:workers";
import { evento, mismoToken } from "../../../servidor/pedidos";
import { aleatorio } from "../../../servidor/panel";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;
const OPCIONES: Record<string, string> = { esperar: "esperar a que llegue", reemplazo: "otro producto (lo llamamos)", devolucion: "devolución de lo que falta" };

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const f = await request.formData();
  const id = String(f.get("id") ?? ""), t = String(f.get("t") ?? ""), opcion = String(f.get("opcion") ?? "");
  if (!/^[0-9a-f]{32}$/.test(id) || !Object.hasOwn(OPCIONES, opcion)) return error(400, "Datos inválidos");
  const p = await env.DB.prepare("SELECT token, estado, eleccion FROM pedidos WHERE id = ?").bind(id).first<{ token: string; estado: string; eleccion: string | null }>();
  if (!p || !mismoToken(t, p.token)) return error(404, "No encontrado");
  if (p.estado === "faltante" && !p.eleccion) {
    const ts = new Date().toISOString();
    await env.DB.batch([
      env.DB.prepare("UPDATE pedidos SET eleccion = ?, eleccion_fecha = ?, actualizado = ? WHERE id = ? AND eleccion IS NULL").bind(opcion, ts, ts, id),
      env.DB.prepare("INSERT INTO acciones (id, pedido_id, tipo, datos, empleado_id, creada) VALUES (?, ?, 'eleccion', ?, 0, ?)")
        .bind(aleatorio(16), id, JSON.stringify({ opcion: OPCIONES[opcion] }), ts),
    ]);
    await evento(env.DB, id, `el cliente eligió: ${OPCIONES[opcion]}`);
  }
  return Response.redirect(`${url.origin}/pedido/${id}?t=${t}`, 303);
}
