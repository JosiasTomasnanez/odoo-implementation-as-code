// Punto de entrada del Worker: Astro atiende las páginas; acá se exportan los Durable Objects y la
// tarea de cada minuto (vencer las reservas sin pagar).
import { handle } from "@astrojs/cloudflare/handler";
import { vencerReservas } from "./servidor/pedidos";
import { recordarRetiros } from "./servidor/recordatorios";
import { limpiar } from "./servidor/limpieza";
import { resumenDeAyer } from "./servidor/resumen-mails";
import { reporteDeUso } from "./servidor/uso-cloudflare";
export { Inventario } from "./servidor/inventario";

export default {
  async fetch(request, env, ctx) {
    return handle(request, env, ctx);
  },
  async scheduled(_evento, env, ctx) {
    ctx.waitUntil(vencerReservas(env).then((n) => { if (n) console.log(`reservas vencidas: ${n}`); }));
    // Una vez por hora: recordatorio a quien no retiró su pedido
    if (new Date().getUTCMinutes() === 0) ctx.waitUntil(recordarRetiros(env));
    // Una vez por hora (a los 30): borrar lo vencido
    if (new Date().getUTCMinutes() === 30) ctx.waitUntil(limpiar(env));
    // Una vez por día (9:00 de Argentina): resumen de los mails de ayer por Discord
    if (new Date().getUTCHours() === 12 && new Date().getUTCMinutes() === 0) ctx.waitUntil(resumenDeAyer(env));
    // Una vez por día (9:05): uso de Cloudflare contra el plan gratis, solo donde REPORTE_USO = "1" (P-066)
    if (new Date().getUTCHours() === 12 && new Date().getUTCMinutes() === 5) ctx.waitUntil(reporteDeUso(env));
  },
} satisfies ExportedHandler<Env>;
