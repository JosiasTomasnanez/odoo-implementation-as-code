// Envío de mails de la tienda por el primer proveedor que lo acepte (P-067). Orden: el servicio de
// Cloudflare (binding CORREO: solo con el plan pago, hoy sin configurar), Brevo (BREVO_API_KEY) y
// Resend (RESEND_API_KEY). Si uno rechaza (cupo agotado, caída), se prueba el siguiente. MAIL_ORDEN
// («brevo,resend») cambia el orden. Odoo y los avisos del servidor no pasan por acá: siguen en Resend.
export type Mensaje = { para: string; asunto: string; html: string; texto: string; idem?: string };
export type Resultado = { ok: boolean; por: string | null; detalle: string };
type Config = Pick<Env, "RESEND_API_KEY" | "BREVO_API_KEY" | "MAIL_DESDE" | "MAIL_ORDEN" | "CORREO">;

const DESDE = "Comercio Ejemplo <pedidos@comercio-ejemplo.example>";
const ESPERA = 8000;

/** «Nombre <mail>» → sus dos partes (Brevo las pide separadas). */
export function remitente(de: string): { name?: string; email: string } {
  const m = /^\s*(.*?)\s*<([^<>]+)>\s*$/.exec(de);
  return m ? { ...(m[1] ? { name: m[1] } : {}), email: m[2].trim() } : { email: de.trim() };
}

const json = (url: string, cabeceras: Record<string, string>, cuerpo: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json", ...cabeceras }, body: JSON.stringify(cuerpo), signal: AbortSignal.timeout(ESPERA) });

const PROVEEDORES: Record<string, { listo: (e: Config) => boolean; mandar: (e: Config, de: string, m: Mensaje) => Promise<string | null> }> = {
  cloudflare: {
    listo: (e) => !!e.CORREO,
    mandar: async (e, de, m) => {
      const r = remitente(de);
      await e.CORREO!.send({ from: r.name ? { name: r.name, email: r.email } : r.email, to: m.para, subject: m.asunto, html: m.html, text: m.texto });
      return null;
    },
  },
  brevo: {
    listo: (e) => !!e.BREVO_API_KEY,
    mandar: async (e, de, m) => {
      const r = await json("https://api.brevo.com/v3/smtp/email", { "api-key": e.BREVO_API_KEY!, Accept: "application/json" },
        { sender: remitente(de), to: [{ email: m.para }], subject: m.asunto, htmlContent: m.html, textContent: m.texto });
      return r.ok ? null : `HTTP ${r.status}`;
    },
  },
  resend: {
    listo: (e) => !!e.RESEND_API_KEY,
    mandar: async (e, de, m) => {
      const r = await json("https://api.resend.com/emails", { Authorization: `Bearer ${e.RESEND_API_KEY}`, ...(m.idem ? { "Idempotency-Key": m.idem.slice(0, 250) } : {}) },
        { from: de, to: [m.para], subject: m.asunto, html: m.html, text: m.texto });
      return r.ok ? null : `HTTP ${r.status}`;
    },
  },
};

/** Proveedores configurados, en el orden en que se prueban. */
export function proveedores(env: Config): string[] {
  const orden = (env.MAIL_ORDEN ?? "cloudflare,brevo,resend").split(",").map((x) => x.trim().toLowerCase());
  return [...new Set(orden)].filter((n) => PROVEEDORES[n]?.listo(env));
}

export async function enviar(env: Config, m: Mensaje): Promise<Resultado> {
  const de = env.MAIL_DESDE ?? DESDE, fallas: string[] = [];
  for (const n of proveedores(env)) {
    let falla: string | null;
    try { falla = await PROVEEDORES[n].mandar(env, de, m); } catch (e) { falla = e instanceof Error ? e.name : "error"; }
    if (!falla) return { ok: true, por: n, detalle: fallas.length ? `${n} (antes: ${fallas.join(", ")})` : n };
    fallas.push(`${n} ${falla}`);
  }
  return { ok: false, por: null, detalle: fallas.join(", ") || "sin proveedor de mails configurado" };
}
