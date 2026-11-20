// Arma el pedido: valida, calcula precios en la tienda, reserva (todo o nada) y devuelve a dónde
// ir a pagar. Protegido con Turnstile, límite por IP y origen propio.
import { env } from "cloudflare:workers";
import { PedidoNuevo, armarPedido, evento } from "../../servidor/pedidos";
import { crearPago } from "../../servidor/pagos";
import { limitar, mismoOrigen, turnstileValido } from "../../servidor/protecciones";
import { clienteActual } from "../../servidor/clientes";
import { cuerpoConTope, error, json } from "../../servidor/respuestas";
import { sitioDe } from "../../servidor/sitio";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (!mismoOrigen(request, url)) return error(403, "Origen no permitido");
  const ip = request.headers.get("cf-connecting-ip");
  const limite = await limitar(env.LIMITE_PEDIDOS, `pedido:${ip ?? "?"}`);
  if (limite) return limite;
  const cuerpo = await cuerpoConTope(request, 32 * 1024);
  if (!cuerpo) return error(413, "Pedido demasiado grande");
  let datos: unknown;
  try { datos = JSON.parse(new TextDecoder().decode(cuerpo)); } catch { return error(400, "Datos inválidos"); }
  const p = PedidoNuevo.safeParse(datos);
  if (!p.success) return error(422, "Revisá los datos: nombre, mail y teléfono.");
  if (!(await turnstileValido(env, p.data.turnstile, ip))) return error(403, "No pudimos comprobar que no sos un robot. Recargá la página.");

  const cliente = await clienteActual(env.DB, request);
  if (cliente) p.data.email = cliente.email; // con sesión, el mail es el verificado de la cuenta
  // Sitio mayorista: solo con cuenta aprobada y con su lista de Odoo (sus precios los pone la tienda)
  const sitio = sitioDe(url);
  const aprobado = cliente?.mayorista === "aprobado" && cliente.lista_id ? cliente.lista_id : undefined;
  if (sitio === "mayorista" && !aprobado) return error(403, "Tu cuenta mayorista todavía no está aprobada.");
  const r = await armarPedido(env, p.data, new Date(), sitio === "mayorista" ? aprobado : undefined, sitio);
  if (r.ok && cliente) {
    await env.DB.batch([
      env.DB.prepare("UPDATE pedidos SET cliente_id = ? WHERE id = ?").bind(cliente.id, r.id),
      env.DB.prepare("UPDATE clientes SET nombre = COALESCE(nombre, ?), telefono = COALESCE(telefono, NULLIF(?, '')) WHERE id = ?")
        .bind(p.data.nombre, p.data.telefono ?? "", cliente.id),
    ]);
  }
  if (!r.ok && r.motivo === "cantidad") return json({ error: "Revisá las cantidades: " + r.lineas.map((l) => `${l.nombre} (desde ${l.desde}${l.bulto ? `, de a ${l.bulto}` : ""})`).join(", ") + ".", cantidades: r.lineas }, 422);
  if (!r.ok && r.motivo === "no_disponible") return json({ error: "Algunos productos ya no están disponibles.", slugs: r.slugs }, 409);
  if (!r.ok) return json({ error: "No alcanza el stock de algunos productos.", faltantes: r.faltantes }, 409);
  try {
    const pago = await crearPago(env, url.origin, { id: r.id, numero: r.numero, token: r.token, total: r.total, email: p.data.email, vence: r.vence, lineas: r.lineas });
    return json({ ok: true, pedido: `W-${String(r.numero).padStart(4, "0")}`, pago });
  } catch (e) {
    console.error("crear pago", r.id, String(e));
    await evento(env.DB, r.id, `no se pudo crear el pago: ${String(e)}`);
    return error(502, "No pudimos conectar con el medio de pago. Probá de nuevo en unos minutos.");
  }
}
