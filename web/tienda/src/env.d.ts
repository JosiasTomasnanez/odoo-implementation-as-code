// Tipografías: se importan solo por su CSS
declare module "@fontsource/*";

declare namespace App {
  interface Locals {
    /** Qué sitio se está viendo, según el dominio (ADR 0035). */
    sitio: "tienda" | "mayorista";
  }
}

// Secretos y variables opcionales del Worker que `wrangler types` no conoce (no están en
// wrangler.jsonc ni en .dev.vars): se declaran acá una vez, en lugar de forzar el tipo en cada uso.
interface OpcionalesDelWorker {
  RESEND_API_KEY?: string;
  BREVO_API_KEY?: string;
  MAIL_DESDE?: string;
  /** Orden de los proveedores de mail, p. ej. «brevo,resend» (correo.ts). */
  MAIL_ORDEN?: string;
  /** Servicio de mails de Cloudflare (binding send_email; solo con el plan pago, P-066). */
  CORREO?: SendEmail;
  /** Canal de Discord para el resumen diario de mails (resumen-mails.ts). */
  DISCORD_WEBHOOK_URL?: string;
  /** Token de Cloudflare con «Account Analytics: Read», para el reporte de uso (uso-cloudflare.ts). */
  CF_ANALYTICS_TOKEN?: string;
  MP_ACCESS_TOKEN?: string;
  MP_WEBHOOK_SECRET?: string;
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
}
declare namespace Cloudflare {
  interface Env extends OpcionalesDelWorker {}
}
interface Env extends OpcionalesDelWorker {}
