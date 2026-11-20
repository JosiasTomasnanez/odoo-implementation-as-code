// Pedir cuenta mayorista: queda «pendiente» hasta que la administración la aprueba y la vincula a su
// contacto y su lista de precios en Odoo.
import { env } from "cloudflare:workers";
import { clienteActual, cuitValido } from "../../../servidor/clientes";
import { mismoOrigen } from "../../../servidor/protecciones";
import { error } from "../../../servidor/respuestas";
import { sitioDe } from "../../../servidor/sitio";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  // Solo desde el sitio mayorista (la tienda no muestra nada mayorista, ADR 0035)
  if (sitioDe(url) !== "mayorista") return error(404, "No encontrado");
  const c = await clienteActual(env.DB, request);
  if (!c) return Response.redirect(`${url.origin}/ingresar`, 303);
  const f = await request.formData();
  const texto = (k: string, max: number) => String(f.get(k) ?? "").replace(/\s+/g, " ").trim().slice(0, max);
  const cuit = String(f.get("cuit") ?? "").replace(/\D/g, "");
  const razon = texto("razon", 120);
  const tel = String(f.get("telefono") ?? "").replace(/[^0-9 +()-]/g, "").slice(0, 30);
  const iva = ["ri", "monotributo", "exento"].includes(String(f.get("iva"))) ? String(f.get("iva")) : "";
  const actividad = texto("actividad", 40), direccion = texto("direccion", 120), localidad = texto("localidad", 80), contacto = texto("contacto", 80);
  // Se avisa qué dato falló (solo el nombre del campo; lo escrito se conserva en el navegador)
  const mal = [!cuitValido(cuit) && "cuit", razon.length < 2 && "razon", !iva && "iva", !actividad && "actividad", !direccion && "direccion",
    !localidad && "localidad", !contacto && "contacto", tel.replace(/\D/g, "").length < 6 && "telefono"].filter(Boolean);
  if (mal.length) return Response.redirect(`${url.origin}/?e=${mal.join(",")}`, 303);
  if (c.mayorista !== "aprobado") {
    await env.DB.prepare(`UPDATE clientes SET mayorista = 'pendiente', cuit = ?, razon_social = ?, telefono = ?, condicion_iva = ?, actividad = ?,
        direccion = ?, localidad = ?, contacto = ?, pedido_alta = ? WHERE id = ? AND mayorista IS NOT 'rechazado'`)
      .bind(cuit, razon, tel, iva, actividad, direccion, localidad, contacto, new Date().toISOString(), c.id).run();
  }
  return Response.redirect(`${url.origin}/`, 303);
}
