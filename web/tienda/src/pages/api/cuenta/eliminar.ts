// Eliminar la cuenta propia: borra la cuenta, sus sesiones y códigos; los pedidos quedan (obligación
// fiscal) pero sin unir a ninguna cuenta. Si era mayorista, su contacto en Odoo no se toca desde acá.
import { env } from "cloudflare:workers";
import { clienteActual, cookieCliente } from "../../../servidor/clientes";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const c = await clienteActual(env.DB, request);
  if (!c) return Response.redirect(`${url.origin}/legales/eliminar-cuenta/`, 303);
  const f = await request.formData();
  if (f.get("seguro") !== "si") return Response.redirect(`${url.origin}/legales/eliminar-cuenta/`, 303);
  await env.DB.batch([
    env.DB.prepare("UPDATE pedidos SET cliente_id = NULL WHERE cliente_id = ?").bind(c.id),
    env.DB.prepare("DELETE FROM sesiones_cliente WHERE cliente_id = ?").bind(c.id),
    env.DB.prepare("DELETE FROM codigos_ingreso WHERE email = ?").bind(c.email),
    env.DB.prepare("DELETE FROM cambios_cliente WHERE cliente_id = ?").bind(c.id),
    env.DB.prepare("DELETE FROM clientes WHERE id = ?").bind(c.id),
    env.DB.prepare("INSERT INTO registro_admin (cuando, quien, que) VALUES (?, 'cliente', ?)")
      .bind(new Date().toISOString(), `una persona eliminó su cuenta${c.mayorista === "aprobado" ? " (era mayorista aprobado: revisar su contacto en Odoo)" : ""}`),
  ]);
  return new Response(null, { status: 303, headers: { Location: `${url.origin}/legales/eliminar-cuenta/?ok=1`, "Set-Cookie": cookieCliente("", 0) } });
}
