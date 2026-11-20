// Cómo se le nombra al cliente cada estado de su pedido.
export const ESTADOS: Record<string, string> = { pagado: "Pagado", en_odoo: "Pagado", preparando: "Preparando", faltante: "Falta algo", listo: "Listo para retirar", retirado: "Retirado", rechazado: "Pago rechazado", revisar: "En revisión", pagado_faltante: "Falta algo", cancelado: "Cancelado", devolucion: "Devolución" };
/** Pedidos cobrados que la administración puede cancelar (api/admin/cancelar.ts). */
export const CANCELABLES = ["pagado", "en_odoo", "pagado_faltante", "revisar", "preparando", "faltante", "listo", "retirado"];
/** El pedido todavía no terminó: conviene tenerlo a la vista. */
export const enCurso = (estado: string) => !["retirado", "rechazado", "cancelado", "devolucion", "vencido"].includes(estado);
