// Medios de pago (ADR 0032). La tienda nunca ve tarjetas: arma el pedido, manda al cliente a
// pagar y da el pago por hecho solo cuando lo verifica contra el medio de pago.
//
// PAGOS_MODO (variable del Worker):
//   simulado     → solo demo: una pantalla propia con «Aprobar» / «Rechazar» (mismo circuito)
//   mercadopago  → Checkout Pro. Secretos: MP_ACCESS_TOKEN y MP_WEBHOOK_SECRET
//                  (npx wrangler secret put …). Ojo: es Checkout Pro (Preferencias); el plan es
//                  pasar a la API de Orders (docs/areas/ecommerce.md) cuando haya credenciales.
//   «simulado» solo anda si ORIGEN es la demo o local (esDemo): en producción queda sin configurar.
import { esDemo } from "./protecciones.ts";

export type PedidoPago = { id: string; numero: number; token: string; total: number; email: string; vence: string;
  lineas: { nombre: string; cantidad: number; precio: number }[] };
export type EstadoPago = { pago_id: string; pedido_id: string; estado: "aprobado" | "rechazado" | "pendiente"; monto: number };

const MP = "https://api.mercadopago.com";

export function modo(env: Env): "simulado" | "mercadopago" | null {
  const m = (env as unknown as { PAGOS_MODO?: string }).PAGOS_MODO;
  // Traba dura: el pago simulado deja aprobar sin pagar; fuera de la demo no existe, aunque la
  // configuración diga «simulado» (queda «sin configurar» y no se puede comprar).
  if (m === "simulado") return esDemo(env) ? m : null;
  return m === "mercadopago" ? m : null;
}

/** Dirección a la que va el cliente para pagar. */
export async function crearPago(env: Env, origen: string, p: PedidoPago): Promise<string> {
  const m = modo(env);
  if (m === "simulado") return `${origen}/pago/simulado/${p.id}?t=${p.token}`;
  if (m === "mercadopago") {
    const token = env.MP_ACCESS_TOKEN;
    if (!token) throw new Error("Falta MP_ACCESS_TOKEN");
    const r = await fetch(`${MP}/checkout/preferences`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", "X-Idempotency-Key": `pref-${p.id}` },
      body: JSON.stringify({
        items: p.lineas.map((l) => ({ title: l.nombre.slice(0, 250), quantity: l.cantidad, unit_price: l.precio / 100, currency_id: "ARS" })),
        payer: { email: p.email },
        external_reference: p.id,
        notification_url: `${origen}/api/pago/mercadopago`,
        back_urls: { success: `${origen}/pedido/${p.id}?t=${p.token}`, failure: `${origen}/pedido/${p.id}?t=${p.token}`, pending: `${origen}/pedido/${p.id}?t=${p.token}` },
        auto_return: "approved",
        statement_descriptor: "COMERCIO EJEMPLO",
        expires: true,
        expiration_date_to: p.vence,
        binary_mode: true, // aprobado o rechazado, sin «pendiente» (la reserva dura poco)
      }),
    });
    if (!r.ok) throw new Error(`Mercado Pago: HTTP ${r.status}`);
    const d = (await r.json()) as { init_point?: string };
    if (!d.init_point) throw new Error("Mercado Pago no devolvió el link de pago");
    return d.init_point;
  }
  throw new Error("Pagos sin configurar (PAGOS_MODO)");
}

/** Consulta el pago en Mercado Pago (nunca se le cree al aviso: se pregunta). */
export async function consultarMercadoPago(env: Env, pagoId: string): Promise<EstadoPago | null> {
  const token = env.MP_ACCESS_TOKEN;
  if (!token || !/^\d{1,20}$/.test(pagoId)) return null;
  const r = await fetch(`${MP}/v1/payments/${pagoId}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) return null;
  const d = (await r.json()) as { id: number; status: string; external_reference?: string; transaction_amount: number; currency_id: string };
  if (d.currency_id !== "ARS" || !d.external_reference) return null;
  const estado = d.status === "approved" ? "aprobado" : d.status === "rejected" || d.status === "cancelled" ? "rechazado" : "pendiente";
  return { pago_id: String(d.id), pedido_id: d.external_reference, estado, monto: Math.round(d.transaction_amount * 100) };
}

/**
 * Firma del aviso de Mercado Pago (encabezado x-signature: «ts=…,v1=…»): HMAC-SHA256 con la
 * clave secreta del aviso sobre «id:<data.id>;request-id:<x-request-id>;ts:<ts>;».
 */
export async function firmaMercadoPagoValida(secreto: string, xSignature: string | null, xRequestId: string | null,
  dataId: string, ahora = Date.now()): Promise<boolean> {
  if (!secreto || !xSignature) return false;
  const partes = Object.fromEntries(xSignature.split(",").map((p) => p.trim().split("=", 2) as [string, string]));
  const ts = partes.ts, v1 = partes.v1;
  if (!ts || !v1 || !/^[0-9a-f]{64}$/.test(v1) || !/^\d{10,13}$/.test(ts)) return false;
  const tsMs = ts.length > 10 ? Number(ts) : Number(ts) * 1000;
  if (Math.abs(ahora - tsMs) > 10 * 60_000) return false;
  let plantilla = `id:${dataId.toLowerCase()};`;
  if (xRequestId) plantilla += `request-id:${xRequestId};`;
  plantilla += `ts:${ts};`;
  const enc = new TextEncoder();
  const clave = await crypto.subtle.importKey("raw", enc.encode(secreto), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
  const bytes = new Uint8Array(32);
  for (let i = 0; i < 32; i++) bytes[i] = parseInt(v1.slice(i * 2, i * 2 + 2), 16);
  return crypto.subtle.verify("HMAC", clave, bytes, enc.encode(plantilla));
}
