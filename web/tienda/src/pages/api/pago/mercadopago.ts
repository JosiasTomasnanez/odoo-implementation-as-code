// Aviso de pago de Mercado Pago (webhook). Se verifica la firma y, sobre todo, se consulta el pago
// en la API de Mercado Pago: lo que dice el aviso no se usa para nada más que el id.
import { env } from "cloudflare:workers";
import { consultarMercadoPago, firmaMercadoPagoValida, modo } from "../../../servidor/pagos";
import { procesarPago } from "../../../servidor/pedidos";
import { cuerpoConTope, error, json } from "../../../servidor/respuestas";

export const prerender = false;

export async function POST({ request, url }: { request: Request; url: URL }) {
  if (modo(env) !== "mercadopago") return error(404, "No encontrado");
  const cuerpo = await cuerpoConTope(request, 16 * 1024);
  if (!cuerpo) return error(413, "Demasiado grande");
  let d: { type?: string; data?: { id?: string | number } } = {};
  try { d = JSON.parse(new TextDecoder().decode(cuerpo)); } catch { /* también llega por query */ }
  const tipo = d.type ?? url.searchParams.get("type") ?? url.searchParams.get("topic");
  const dataId = String(d.data?.id ?? url.searchParams.get("data.id") ?? url.searchParams.get("id") ?? "");
  if (tipo !== "payment" || !/^\d{1,20}$/.test(dataId)) return json({ ok: true }); // otros avisos: se ignoran
  const secreto = env.MP_WEBHOOK_SECRET ?? "";
  if (!(await firmaMercadoPagoValida(secreto, request.headers.get("x-signature"), request.headers.get("x-request-id"), dataId))) {
    console.warn("aviso de Mercado Pago con firma inválida", dataId);
    return error(401, "Firma inválida");
  }
  const pago = await consultarMercadoPago(env, dataId);
  if (!pago || !/^[0-9a-f]{32}$/.test(pago.pedido_id)) return error(502, "No se pudo consultar el pago"); // Mercado Pago reintenta
  const estado = await procesarPago(env, "mercadopago", pago, url.origin);
  return json({ ok: true, estado });
}
