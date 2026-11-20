// Entrar al panel: el empleado elige su nombre y pone su PIN (solo desde un dispositivo habilitado).
import { env } from "cloudflare:workers";
import { COOKIE_SES, SEGUNDOS_SESION, acierto, bloqueado, cookie, crearSesion, dispositivo, fallo, hashPin, iguales } from "../../../servidor/panel";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const d = await dispositivo(env.DB, request);
  if (!d) return Response.redirect(`${url.origin}/panel/alta`, 303);
  const f = await request.formData();
  const empleado = Number(f.get("empleado"));
  const pin = String(f.get("pin") ?? "");
  const clave = `pin:${d.id}:${empleado}`;
  if (!Number.isInteger(empleado) || empleado <= 0) return Response.redirect(`${url.origin}/panel?e=pin`, 303);
  if (await bloqueado(env.DB, clave) || await bloqueado(env.DB, `pin:${d.id}`)) return Response.redirect(`${url.origin}/panel?e=bloqueado`, 303);
  const e = await env.DB.prepare("SELECT pin_hash FROM empleados WHERE id_odoo = ? AND activo = 1").bind(empleado).first<{ pin_hash: string | null }>();
  const pepper = env.PIN_PEPPER ?? "";
  const ok = !!e?.pin_hash && /^\d{4,8}$/.test(pin) && pepper.length >= 32 && iguales(await hashPin(pepper, empleado, pin), e.pin_hash);
  if (!ok) {
    await fallo(env.DB, clave, 5, 10);          // 5 fallos de esa persona: 10 minutos
    await fallo(env.DB, `pin:${d.id}`, 15, 15); // 15 fallos en el dispositivo: 15 minutos
    return Response.redirect(`${url.origin}/panel?e=pin`, 303);
  }
  await acierto(env.DB, clave);
  const token = await crearSesion(env.DB, empleado, d.id);
  return new Response(null, { status: 303, headers: { Location: `${url.origin}/panel`, "Set-Cookie": cookie(COOKIE_SES, token, SEGUNDOS_SESION) } });
}
