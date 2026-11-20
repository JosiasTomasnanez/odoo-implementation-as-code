// Lo que puede llegar del conector, validado estricto: cualquier campo de más, de otro tipo o
// demasiado largo hace rechazar el lote entero (no se guarda nada a medias).
import { z } from "zod";

const texto = (max: number) => z.string().trim().max(max);
const id = z.number().int().positive().max(2_147_483_647);

export const Precio = z.strictObject({
  lista_id: id,
  precio: z.number().int().min(0).max(100_000_000_00),
  precio_anterior: z.number().int().min(0).max(100_000_000_00).nullable(),
  oferta_hasta: texto(30).nullable(),
  // Opcionales para aceptar lotes de un módulo anterior (se publica primero la tienda)
  minimo: z.number().int().min(1).max(100_000).optional(),
});

export const Producto = z.strictObject({
  id,
  publicado: z.boolean(),
  nombre: texto(300).min(1),
  codigo: texto(64).nullable(),
  referencia: texto(64).nullable(),
  categoria_id: id.nullable(),
  unidad: texto(40),
  descripcion: texto(4000).nullable(),
  consultar: z.boolean(),
  nuevo_hasta: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(),
  dias_encargo: z.number().int().min(0).max(365).nullable(),
  imagen: z.string().regex(/^[0-9a-f]{40,64}$/).nullable(),
  margen: z.number().min(0).max(1_000_000),
  stock_libre: z.number().min(-1_000_000_000).max(1_000_000_000).nullable(),
  bulto: z.number().int().min(2).max(100_000).nullable().optional(),
  precios: z.array(Precio).max(1000), // una por lista: con listas por cliente (ADR 0037) son muchas
});

export const Categoria = z.strictObject({
  id,
  nombre: texto(120).min(1),
  padre_id: id.nullable(),
  orden: z.number().int().min(-1_000_000).max(1_000_000),
});

export const Lista = z.strictObject({ id, nombre: texto(120).min(1), publica: z.boolean() });

export const Empleado = z.strictObject({ id, nombre: texto(80).min(1), pin: z.string().regex(/^\d{4,8}$/).nullable(), activo: z.boolean() });

export const Lote = z.strictObject({
  numero: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
  productos: z.array(Producto).max(500),
  productos_borrados: z.array(id).max(500),
  categorias: z.array(Categoria).max(500),
  categorias_borradas: z.array(id).max(500),
  listas: z.array(Lista).max(1000),
  empleados: z.array(Empleado).max(200).default([]),
});
export type Lote = z.infer<typeof Lote>;
