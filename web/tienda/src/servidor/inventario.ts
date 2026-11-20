// Durable Object «Inventario» (ADR 0033): una sola instancia («principal») hace todas las
// reservas. Cada operación corre dentro de blockConcurrencyWhile: aunque espere la lectura del
// stock en D1, ninguna otra reserva entra en el medio. Así dos compras de la última unidad no
// pueden reservarla las dos.
//
//   disponible = stock libre de Odoo − margen − reservas activas o pagadas (no reflejadas en Odoo)
//
// Estados de una reserva: activa (esperando el pago) → pagada → reflejada (Odoo ya la descuenta:
// deja de restarse aparte) | liberada (venció, se rechazó el pago o se canceló).
import { DurableObject } from "cloudflare:workers";

export type LineaReserva = { producto_id: number; cantidad: number };
export type Faltante = { producto_id: number; pedido: number; disponible: number };
export type ResultadoReserva = { ok: true } | { ok: false; faltantes: Faltante[] };

type Stock = { producto_id: number; libre_odoo: number; margen: number; controla: number; consultar: number; publicado: number };

export class Inventario extends DurableObject<Env> {
  private sql: SqlStorage;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS reservas (
      pedido_id TEXT NOT NULL, producto_id INTEGER NOT NULL, cantidad INTEGER NOT NULL,
      estado TEXT NOT NULL, vence INTEGER NOT NULL, PRIMARY KEY (pedido_id, producto_id))`);
    this.sql.exec("CREATE INDEX IF NOT EXISTS reservas_producto ON reservas(producto_id, estado)");
  }

  async estado(): Promise<{ ok: true }> {
    return { ok: true };
  }

  private reservado(productoId: number): number {
    const r = this.sql.exec<{ n: number }>(
      "SELECT COALESCE(SUM(cantidad), 0) AS n FROM reservas WHERE producto_id = ? AND estado IN ('activa', 'pagada')", productoId).one();
    return r.n;
  }

  /** Reserva todo el pedido o nada. Repetir la misma reserva (mismo pedido) no duplica. */
  async reservar(pedidoId: string, lineas: LineaReserva[], venceMs: number): Promise<ResultadoReserva> {
    return this.ctx.blockConcurrencyWhile(async () => {
      const ya = this.sql.exec<{ n: number }>("SELECT COUNT(*) AS n FROM reservas WHERE pedido_id = ? AND estado IN ('activa', 'pagada')", pedidoId).one();
      if (ya.n > 0) return { ok: true } as const;
      const ids = [...new Set(lineas.map((l) => l.producto_id))];
      if (!ids.length) return { ok: false, faltantes: [] };
      const r = await this.env.DB.prepare(`SELECT s.producto_id, s.libre_odoo, s.margen, s.controla, p.consultar, p.publicado
          FROM stock s JOIN productos p ON p.id_odoo = s.producto_id WHERE s.producto_id IN (${ids.map(() => "?").join(",")})`)
        .bind(...ids).all<Stock>();
      const stock = new Map(r.results.map((s) => [s.producto_id, s]));
      const faltantes: Faltante[] = [];
      for (const l of lineas) {
        const s = stock.get(l.producto_id);
        if (!s || !s.publicado) { faltantes.push({ producto_id: l.producto_id, pedido: l.cantidad, disponible: 0 }); continue; }
        if (s.consultar || !s.controla) continue; // se vende sin tope (se confirma en el día)
        const disponible = Math.max(0, Math.floor(s.libre_odoo - s.margen - this.reservado(l.producto_id)));
        if (l.cantidad > disponible) faltantes.push({ producto_id: l.producto_id, pedido: l.cantidad, disponible });
      }
      if (faltantes.length) return { ok: false, faltantes };
      for (const l of lineas) {
        this.sql.exec(`INSERT INTO reservas (pedido_id, producto_id, cantidad, estado, vence) VALUES (?, ?, ?, 'activa', ?)
          ON CONFLICT(pedido_id, producto_id) DO UPDATE SET cantidad = excluded.cantidad, estado = 'activa', vence = excluded.vence`,
          pedidoId, l.producto_id, l.cantidad, venceMs);
      }
      return { ok: true } as const;
    });
  }

  /** El pago se aprobó: la reserva activa pasa a pagada. false si ya no estaba (venció). */
  async confirmar(pedidoId: string): Promise<boolean> {
    return this.ctx.blockConcurrencyWhile(async () => {
      const r = this.sql.exec("UPDATE reservas SET estado = 'pagada' WHERE pedido_id = ? AND estado IN ('activa', 'pagada')", pedidoId);
      return r.rowsWritten > 0;
    });
  }

  /** Odoo ya creó el pedido (y descuenta el stock): la reserva deja de restarse aparte. */
  async reflejar(pedidoId: string): Promise<void> {
    await this.ctx.blockConcurrencyWhile(async () => {
      this.sql.exec("UPDATE reservas SET estado = 'reflejada' WHERE pedido_id = ? AND estado = 'pagada'", pedidoId);
    });
  }

  async liberar(pedidoId: string): Promise<void> {
    await this.ctx.blockConcurrencyWhile(async () => {
      this.sql.exec("UPDATE reservas SET estado = 'liberada' WHERE pedido_id = ? AND estado = 'activa'", pedidoId);
    });
  }

  /** Pedido cancelado desde la administración: su reserva (activa o ya pagada) deja de restarse.
   *  Si Odoo ya lo tenía (reflejada), el stock vuelve cuando Odoo lo cancela. */
  async cancelar(pedidoId: string): Promise<void> {
    await this.ctx.blockConcurrencyWhile(async () => {
      this.sql.exec("UPDATE reservas SET estado = 'liberada' WHERE pedido_id = ? AND estado IN ('activa', 'pagada')", pedidoId);
    });
  }

  /** Libera las reservas activas vencidas y devuelve sus pedidos. */
  async vencer(ahoraMs: number): Promise<string[]> {
    return this.ctx.blockConcurrencyWhile(async () => {
      const filas = this.sql.exec<{ pedido_id: string }>(
        "SELECT DISTINCT pedido_id FROM reservas WHERE estado = 'activa' AND vence < ?", ahoraMs).toArray();
      this.sql.exec("UPDATE reservas SET estado = 'liberada' WHERE estado = 'activa' AND vence < ?", ahoraMs);
      // Limpieza: lo liberado o reflejado hace más de 30 días ya no hace falta
      this.sql.exec("DELETE FROM reservas WHERE estado IN ('liberada', 'reflejada') AND vence < ?", ahoraMs - 30 * 86_400_000);
      return filas.map((f) => f.pedido_id);
    });
  }

  /** Para la tienda: cuánto se puede vender ahora de esos productos (sin reservar). */
  async reservadoDe(ids: number[]): Promise<Record<number, number>> {
    const out: Record<number, number> = {};
    for (const id of ids.slice(0, 200)) out[id] = this.reservado(id);
    return out;
  }
}
