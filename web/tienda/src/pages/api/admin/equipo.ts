// Equipo (solo «admin»): sumar, cambiar permisos, dar de baja y reactivar. Nadie se puede sacar a
// sí mismo la administración ni darse de baja. Cambiar permisos o dar de baja cierra sus sesiones.
import { env } from "cloudflare:workers";
import { z } from "zod";
import { aleatorio } from "../../../servidor/panel";
import { cortarSesiones, esRol, miembroActual, puede, registrar } from "../../../servidor/equipo";
import { escHtml, mailAviso } from "../../../servidor/mails";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;
const Email = z.string().trim().toLowerCase().max(160).email();

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const yo = await miembroActual(env.DB, request);
  if (!yo) return Response.redirect(`${url.origin}/admin/ingresar`, 303);
  if (!puede(yo, "admin")) return error(403, "Sin permiso");
  const f = await request.formData();
  const accion = String(f.get("accion") ?? "");
  const roles = [...new Set(f.getAll("roles").map(String).filter((r) => esRol(r) && r !== "marketing"))].join(",");
  const ir = (q: string) => Response.redirect(`${url.origin}/admin/equipo?${q}`, 303);

  if (accion === "alta") {
    const e = Email.safeParse(String(f.get("email") ?? ""));
    const nombre = String(f.get("nombre") ?? "").replace(/\s+/g, " ").trim().slice(0, 80);
    if (!e.success || nombre.length < 2) return ir("e=mail");
    if (await env.DB.prepare("SELECT 1 FROM equipo WHERE email = ?").bind(e.data).first()) return ir("e=existe");
    await env.DB.batch([
      env.DB.prepare("INSERT INTO equipo (id, email, nombre, roles, creado, creado_por) VALUES (?, ?, ?, ?, ?, ?)")
        .bind(aleatorio(16), e.data, nombre, roles, new Date().toISOString(), yo.nombre),
      registrar(env.DB, yo, `sumó a ${nombre} <${e.data}> (${roles || "sin permisos"})`),
    ]);
    const entrar = `${url.origin}/admin/ingresar?modo=clave&m=${encodeURIComponent(e.data)}`;
    await mailAviso(env, e.data, "Te sumaron a la administración de la tienda",
      `<p>Hola ${escHtml(nombre)}: ${escHtml(yo.nombre)} te sumó a la administración de la tienda online de Comercio Ejemplo. Para entrar, elegí tu contraseña (te mandamos un código a este mail).</p>`,
      `Hola ${nombre}: ${yo.nombre} te sumó a la administración de la tienda de Comercio Ejemplo. Elegí tu contraseña en ${entrar}`,
      { texto: "Elegir mi contraseña", url: entrar });
    return ir("ok=alta");
  }

  const id = String(f.get("id") ?? "");
  if (!/^[0-9a-f]{32}$/.test(id)) return error(400, "Acción inválida");
  const m = await env.DB.prepare("SELECT nombre, email, roles FROM equipo WHERE id = ?").bind(id).first<{ nombre: string; email: string; roles: string }>();
  if (!m) return error(404, "No encontrado");
  if (id === yo.id && (accion === "baja" || (accion === "roles" && !roles.split(",").includes("admin")))) return ir("e=yo");
  if (accion === "roles") {
    await env.DB.batch([
      env.DB.prepare("UPDATE equipo SET roles = ? WHERE id = ?").bind(roles, id),
      ...(id === yo.id ? [] : [cortarSesiones(env.DB, id)]),
      registrar(env.DB, yo, `cambió los permisos de ${m.nombre}: ${m.roles || "ninguno"} → ${roles || "ninguno"}`),
    ]);
    return ir("ok=roles");
  }
  if (accion === "baja" || accion === "reactivar") {
    await env.DB.batch([
      env.DB.prepare("UPDATE equipo SET activo = ? WHERE id = ?").bind(accion === "baja" ? 0 : 1, id),
      cortarSesiones(env.DB, id),
      env.DB.prepare("DELETE FROM confianza_equipo WHERE miembro_id = ?").bind(id),
      registrar(env.DB, yo, `${accion === "baja" ? "dio de baja" : "reactivó"} a ${m.nombre}`),
    ]);
    return ir(accion === "baja" ? "ok=baja" : "ok=alta2");
  }
  return error(400, "Acción inválida");
}
