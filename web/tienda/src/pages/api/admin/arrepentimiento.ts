// Marcar resuelto un pedido de arrepentimiento (solo «admin»). Queda en el registro.
import { env } from "cloudflare:workers";
import { miembroActual, puede, registrar } from "../../../servidor/equipo";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

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
  await env.DB.batch([
    env.DB.prepare("UPDATE arrepentimientos SET resuelto = ?, resuelto_por = ?, nota = ? WHERE codigo = ? AND resuelto IS NULL")
      .bind(new Date().toISOString(), yo.nombre, nota, codigo),
    registrar(env.DB, yo, `resolvió el arrepentimiento ${codigo}${nota ? ` (${nota})` : ""}`),
  ]);
  return Response.redirect(`${url.origin}/admin/arrepentimientos`, 303);
}
