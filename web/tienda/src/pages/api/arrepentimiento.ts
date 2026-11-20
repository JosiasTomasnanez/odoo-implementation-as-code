// Botón de arrepentimiento: guarda el pedido, da un código de gestión y lo manda por mail. No hace
// falta cuenta. No se revela si el número de pedido existe (el local lo comprueba al gestionarlo).
import { env } from "cloudflare:workers";
import { z } from "zod";
import { escHtml, mailAviso } from "../../servidor/mails";
import { aleatorio } from "../../servidor/panel";
import { limitar, mismoOrigen, turnstileValido } from "../../servidor/protecciones";
import { error } from "../../servidor/respuestas";

export const prerender = false;
const Email = z.string().trim().toLowerCase().max(160).email();

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const ip = request.headers.get("cf-connecting-ip");
  const lim = await limitar(env.LIMITE_INGRESO, `arrep:${ip ?? "?"}`);
  if (lim) return lim;
  const f = await request.formData();
  const texto = (k: string, max: number) => String(f.get(k) ?? "").replace(/\s+/g, " ").trim().slice(0, max);
  const e = Email.safeParse(String(f.get("email") ?? ""));
  const nombre = texto("nombre", 120);
  const pedido = texto("pedido", 12).toUpperCase().replace(/^(\d+)$/, "W-$1");
  if (!e.success || nombre.length < 2 || !/^W-\d{1,8}$/.test(pedido)) return Response.redirect(`${url.origin}/arrepentimiento/?e=datos`, 303);
  if (!(await turnstileValido(env, String(f.get("cf-turnstile-response") ?? ""), ip))) return Response.redirect(`${url.origin}/arrepentimiento/?e=robot`, 303);
  const tel = String(f.get("telefono") ?? "").replace(/[^0-9 +()-]/g, "").slice(0, 30);
  // El mismo pedido y mail ya lo pidió: se le muestra su código (no se crea otro ni se manda otro mail)
  const ya = await env.DB.prepare("SELECT codigo FROM arrepentimientos WHERE pedido = ? AND email = ? ORDER BY creado DESC LIMIT 1")
    .bind(pedido, e.data).first<{ codigo: string }>();
  if (ya) return Response.redirect(`${url.origin}/arrepentimiento/?codigo=${ya.codigo}`, 303);
  const codigo = `AR-${aleatorio(4).toUpperCase()}`;
  await env.DB.prepare("INSERT INTO arrepentimientos (codigo, creado, nombre, email, telefono, pedido, motivo) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .bind(codigo, new Date().toISOString(), nombre, e.data, tel || null, pedido, texto("motivo", 300) || null).run();
  // El mail solo sale si ese pedido existe y se hizo con ese mail (así nadie usa el formulario para
  // mandarle mails de la tienda a un tercero). El código se muestra siempre en pantalla, y la
  // respuesta es la misma exista o no el pedido.
  const suyo = await env.DB.prepare("SELECT nombre FROM pedidos WHERE numero = ? AND email = ? AND pagado IS NOT NULL")
    .bind(Number(pedido.slice(2)), e.data).first<{ nombre: string }>();
  if (suyo) {
    await mailAviso(env, e.data, `Recibimos tu pedido de arrepentimiento (${codigo})`,
      `<p>Hola ${escHtml(suyo.nombre)}: recibimos tu pedido para dejar sin efecto la compra ${escHtml(pedido)}.</p><p>Tu código de gestión es <b>${codigo}</b>. Te vamos a escribir para coordinar la devolución.</p>`,
      `Hola ${suyo.nombre}: recibimos tu pedido de arrepentimiento por la compra ${pedido}. Código de gestión: ${codigo}.`);
  }
  return Response.redirect(`${url.origin}/arrepentimiento/?codigo=${codigo}`, 303);
}
