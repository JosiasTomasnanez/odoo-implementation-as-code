// Aprobar, rechazar, cambiar la lista o dar de baja a un mayorista (rol «mayoristas»). Lo que tiene
// que llegar a Odoo (contacto y lista) queda marcado para el conector. Todo queda en el registro.
import { env } from "cloudflare:workers";
import { escHtml, mailAviso } from "../../../servidor/mails";
import { miembroActual, puede, registrar } from "../../../servidor/equipo";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;
const ACCIONES = ["aprobar", "rechazar", "lista", "baja", "reabrir", "visto"] as const;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const yo = await miembroActual(env.DB, request);
  if (!yo) return Response.redirect(`${url.origin}/admin/ingresar`, 303);
  if (!puede(yo, "mayoristas")) return error(403, "Sin permiso");
  const f = await request.formData();
  const id = String(f.get("id") ?? ""), accion = String(f.get("accion") ?? "") as (typeof ACCIONES)[number];
  const ver = ["aprobado", "rechazado"].includes(String(f.get("ver"))) ? `ver=${f.get("ver")}&` : "";
  if (!/^[0-9a-f]{32}$/.test(id) || !ACCIONES.includes(accion)) return error(400, "Acción inválida");
  const nota = String(f.get("nota") ?? "").replace(/\s+/g, " ").trim().slice(0, 300) || null;
  const c = await env.DB.prepare("SELECT email, razon_social, mayorista FROM clientes WHERE id = ?").bind(id).first<{ email: string; razon_social: string | null; mayorista: string | null }>();
  if (!c?.mayorista) return error(404, "No encontrado");
  // El equipo ya vio los cambios que el cliente hizo en sus datos
  if (accion === "visto") {
    await env.DB.prepare("UPDATE clientes SET cambios_sin_ver = 0 WHERE id = ?").bind(id).run();
    return Response.redirect(`${url.origin}/admin/mayoristas?${ver}ok=visto`, 303);
  }
  const desde: Record<string, string> = { aprobar: "pendiente", rechazar: "pendiente", lista: "aprobado", baja: "aprobado", reabrir: "rechazado" };
  if (c.mayorista !== desde[accion]) return Response.redirect(`${url.origin}/admin/mayoristas?${ver}`, 303);
  const quien = c.razon_social ?? c.email;
  const ahora = new Date().toISOString();

  if (accion === "aprobar" || accion === "lista") {
    const lista = Number(f.get("lista"));
    const l = await env.DB.prepare("SELECT nombre FROM listas_precios WHERE id_odoo = ? AND publica = 0").bind(lista).first<{ nombre: string }>();
    if (!l) return error(422, "Lista inválida");
    await env.DB.batch([
      accion === "aprobar"
        ? env.DB.prepare("UPDATE clientes SET mayorista = 'aprobado', lista_id = ?, aprobado = ?, aprobado_por = ?, nota = ?, odoo_pendiente = 1 WHERE id = ? AND mayorista = 'pendiente'").bind(lista, ahora, yo.nombre, nota, id)
        : env.DB.prepare("UPDATE clientes SET lista_id = ?, nota = ?, odoo_pendiente = 1 WHERE id = ? AND mayorista = 'aprobado'").bind(lista, nota, id),
      registrar(env.DB, yo, `${accion === "aprobar" ? "aprobó" : "cambió la lista de"} ${quien} → ${l.nombre}`),
    ]);
    if (accion === "aprobar") {
      const sitio = url.origin.replace(/\/\/(demo\.)?/, (_, d) => `//mayoristas${d ? "-demo" : ""}.`);
      await mailAviso(env, c.email, "Tu cuenta mayorista está aprobada",
        `<p>${escHtml(quien)}: ya podés ver tu lista de precios y hacer pedidos en el sitio mayorista de Comercio Ejemplo.</p>`,
        `${quien}: tu cuenta mayorista de Comercio Ejemplo está aprobada. Entrá en ${sitio}`, { texto: "Ver mi lista de precios", url: sitio });
    }
    return Response.redirect(`${url.origin}/admin/mayoristas?${ver}ok=${accion === "aprobar" ? "aprobado" : "lista"}`, 303);
  }
  const nuevo = accion === "reabrir" ? "pendiente" : "rechazado";
  await env.DB.batch([
    env.DB.prepare("UPDATE clientes SET mayorista = ?, nota = ? WHERE id = ?").bind(nuevo, nota, id),
    // Al dar de baja se cierran sus sesiones del sitio mayorista (deja de ver precios ya)
    ...(accion === "baja" ? [env.DB.prepare("DELETE FROM sesiones_cliente WHERE cliente_id = ?").bind(id)] : []),
    registrar(env.DB, yo, `${({ rechazar: "rechazó", baja: "dio de baja", reabrir: "volvió a pendientes" } as Record<string, string>)[accion]} a ${quien}${nota ? ` (${nota})` : ""}`),
  ]);
  return Response.redirect(`${url.origin}/admin/mayoristas?${ver}ok=${accion === "reabrir" ? "reabierto" : accion === "baja" ? "baja" : "rechazado"}`, 303);
}
