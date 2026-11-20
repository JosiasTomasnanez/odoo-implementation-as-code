// Lo que la tienda tiene para Odoo y espera al conector: pedidos pagos, acciones del panel,
// mayoristas aprobados y listas pedidas en la administración. Lo usan /api/conector/pendientes (una
// sola consulta por vuelta) y los endpoints de cada cosa.
import { leerReglas } from "./listas.ts";

export async function pedidosPendientes(db: D1Database) {
  type P = { id: string; numero: number; nombre: string; email: string; telefono: string | null; total: number; lista_id: number; pagado: string; pago_medio: string; pago_id: string; estado: string; sitio: string; partner_id: number | null };
  // Pedido mayorista de un cliente aprobado: va con su contacto de Odoo (y su lista)
  const pedidos = (await db.prepare(`SELECT p.id, p.numero, p.nombre, p.email, p.telefono, p.total, p.lista_id, p.pagado, p.pago_medio, p.pago_id, p.estado, p.sitio,
      CASE WHEN p.sitio = 'mayorista' THEN c.odoo_partner_id END AS partner_id
      FROM pedidos p LEFT JOIN clientes c ON c.id = p.cliente_id
     WHERE p.estado IN ('pagado', 'pagado_faltante') AND p.odoo_id IS NULL ORDER BY p.pagado LIMIT 50`).all<P>()).results;
  const out = [];
  for (const p of pedidos) {
    const lineas = (await db.prepare("SELECT producto_id, nombre, cantidad, precio, consultar FROM pedido_lineas WHERE pedido_id = ?").bind(p.id).all()).results;
    out.push({ ...p, lineas });
  }
  return out;
}

export async function accionesPendientes(db: D1Database) {
  const r = await db.prepare(`SELECT a.id, a.tipo, a.datos, a.creada, p.id AS pedido, p.odoo_id, e.nombre AS empleado
      FROM acciones a JOIN pedidos p ON p.id = a.pedido_id LEFT JOIN empleados e ON e.id_odoo = a.empleado_id
     WHERE a.aplicada IS NULL AND p.odoo_id IS NOT NULL ORDER BY a.creada LIMIT 100`)
    .all<{ id: string; tipo: string; datos: string | null; creada: string; pedido: string; odoo_id: number; empleado: string | null }>();
  return r.results.map((a) => ({ ...a, datos: a.datos ? JSON.parse(a.datos) : null }));
}

export async function clientesPendientes(db: D1Database) {
  const clientes = (await db.prepare(`SELECT id, email, nombre, telefono, cuit, razon_social, condicion_iva, actividad, direccion, localidad,
      contacto, lista_id, odoo_partner_id FROM clientes WHERE odoo_pendiente = 1 AND mayorista = 'aprobado' AND lista_id IS NOT NULL LIMIT 50`).all()).results;
  // Listas por crear y listas con cambios de condiciones por llevar a Odoo
  const filas = (await db.prepare(`SELECT id, nombre, base_id, descuento, reglas, version FROM listas_nuevas
      WHERE (odoo_id IS NULL AND resultado IS NULL) OR pendiente = 1 ORDER BY creada LIMIT 20`)
    .all<{ id: string; nombre: string; base_id: number; descuento: number; reglas: string | null; version: number }>()).results;
  const listas = filas.map((l) => ({ ...l, reglas: leerReglas(l.reglas) }));
  return { clientes, listas };
}
