// Catálogo FICTICIO para la demo visual. Marcas inventadas y precios de ejemplo.
// Más adelante esto lo reemplaza la copia que manda Odoo (productos marcados para la tienda,
// categorías del PdV, precios, stock e imágenes de la ficha).

export type Categoria = { slug: string; nombre: string; icono: string; bajada: string };

export type Producto = {
  slug: string;
  nombre: string;
  marca: string;
  codigo: string; // código de barras (los propios empiezan con 20)
  categoria: string;
  precio: number;
  precioAnterior?: number; // si está, el producto está en oferta
  unidad: string;
  stock: boolean; // «Hay en el local»
  nuevo?: boolean;
  descripcion: string;
  precioMayorista: number; // de la lista mayorista de Odoo (ficticio: 15 % menos)
  imagen?: string; // en la tienda real, la foto de la ficha de Odoo; acá, una ilustración
};

export const categorias: Categoria[] = [
  { slug: "ferreteria", nombre: "Ferretería", icono: "tornillo", bajada: "Tornillos, herramientas, cerraduras" },
  { slug: "sanitarios", nombre: "Sanitarios", icono: "canilla", bajada: "Caños, llaves de paso, griferías" },
  { slug: "electricidad", nombre: "Electricidad", icono: "rayo", bajada: "Cables, lámparas, tomas" },
  { slug: "pileta", nombre: "Pileta", icono: "ola", bajada: "Cloro, limpiafondos, accesorios" },
  { slug: "pintureria", nombre: "Pinturería", icono: "pincel", bajada: "Látex, rodillos, pinceles" },
  { slug: "jardin", nombre: "Jardín", icono: "hoja", bajada: "Mangueras, riego, herramientas" },
  { slug: "mascotas", nombre: "Mascotas", icono: "huella", bajada: "Alimentos, accesorios, higiene" },
];

// Dígito verificador EAN-13, para que los códigos de ejemplo sean válidos.
function ean13(base12: string): string {
  const s = base12.split("").reduce((t, d, i) => t + Number(d) * (i % 2 ? 3 : 1), 0);
  return base12 + ((10 - (s % 10)) % 10);
}
let correlativo = 1000;
const propio = () => ean13("20" + String(correlativo++).padStart(10, "0"));

type Fila = Omit<Producto, "slug" | "codigo" | "precioMayorista" | "imagen"> & { codigo?: string };

const filas: Fila[] = [
  // Ferretería
  { nombre: "Tornillo autoperforante T1 punta mecha 8 × 1/2\" (caja × 100)", marca: "Ferrotec", categoria: "ferreteria", precio: 6890, precioAnterior: 8120, unidad: "caja", stock: true, descripcion: "Cabeza tanque (con arandela) Phillips, cincado. Para unir perfiles de construcción en seco y chapa de hasta 2 mm." },
  { nombre: "Taladro percutor 650 W con maletín", marca: "Ferrotec", categoria: "ferreteria", precio: 74900, unidad: "unidad", stock: true, descripcion: "Mandril de 13 mm, velocidad variable y reversa. Incluye maletín y 5 mechas." },
  { nombre: "Cinta métrica 5 m × 19 mm", marca: "Medix", categoria: "ferreteria", precio: 5390, unidad: "unidad", stock: true, descripcion: "Carcasa de goma antigolpes, traba y gancho imantado." },
  { nombre: "Candado de bronce 40 mm", marca: "Seguril", categoria: "ferreteria", precio: 9850, precioAnterior: 11600, unidad: "unidad", stock: true, descripcion: "Arco de acero templado, 3 llaves." },
  { nombre: "Juego de destornilladores 6 piezas", marca: "Medix", categoria: "ferreteria", precio: 12400, unidad: "juego", stock: false, descripcion: "3 planos y 3 Phillips, mango bimaterial." },
  { nombre: "Silicona acética transparente 280 ml", marca: "Selladur", categoria: "ferreteria", precio: 4790, unidad: "unidad", stock: true, nuevo: true, descripcion: "Para vidrios, aluminio y cerámicos. Antihongos." },
  { nombre: "Tarugo nylon N° 8 con tope (bolsa × 50)", marca: "Ferrotec", categoria: "ferreteria", precio: 2150, unidad: "bolsa", stock: true, descripcion: "Para ladrillo hueco y macizo." },
  { nombre: "Pinza universal 8\"", marca: "Medix", categoria: "ferreteria", precio: 10900, unidad: "unidad", stock: true, descripcion: "Acero al cromo vanadio, mango aislado." },
  // Sanitarios
  { nombre: "Llave de paso esférica ½\" bronce", marca: "Hidrolux", categoria: "sanitarios", precio: 14900, unidad: "unidad", stock: true, descripcion: "Rosca hembra-hembra. Para agua fría y caliente." },
  { nombre: "Caño termofusión 20 mm × 4 m", marca: "Hidrolux", categoria: "sanitarios", precio: 6350, precioAnterior: 7290, unidad: "barra", stock: true, descripcion: "PN 20, para agua fría y caliente." },
  { nombre: "Flexible de acero 40 cm ½\" H-H", marca: "Hidrolux", categoria: "sanitarios", precio: 3980, unidad: "unidad", stock: true, descripcion: "Malla de acero inoxidable." },
  { nombre: "Grifería monocomando para cocina", marca: "Aquaflor", categoria: "sanitarios", precio: 89900, unidad: "unidad", stock: false, nuevo: true, descripcion: "Pico alto giratorio, cartucho cerámico de 35 mm." },
  { nombre: "Cinta de teflón 19 mm × 10 m", marca: "Selladur", categoria: "sanitarios", precio: 890, unidad: "unidad", stock: true, descripcion: "Para roscas de agua y gas." },
  // Electricidad
  { nombre: "Cable unipolar 2,5 mm² (rollo × 100 m)", marca: "Voltar", categoria: "electricidad", precio: 64500, precioAnterior: 72900, unidad: "rollo", stock: true, descripcion: "Norma IRAM NM 247-3. Varios colores." },
  { nombre: "Lámpara LED 12 W luz fría E27", marca: "Lumina", categoria: "electricidad", precio: 1990, unidad: "unidad", stock: true, descripcion: "Equivale a 100 W. 1.100 lúmenes." },
  { nombre: "Cinta aisladora 19 mm × 20 m", marca: "Voltar", categoria: "electricidad", precio: 2450, precioAnterior: 2890, unidad: "unidad", stock: true, descripcion: "PVC negro, ignífuga." },
  { nombre: "Zapatilla 5 tomas con interruptor, cable 3 m", marca: "Voltar", categoria: "electricidad", precio: 15800, unidad: "unidad", stock: true, descripcion: "Tomas 10 A, con protección para niños." },
  { nombre: "Llave térmica bipolar 2 × 20 A", marca: "Voltar", categoria: "electricidad", precio: 18400, unidad: "unidad", stock: true, descripcion: "Curva C, 4,5 kA. Para riel DIN." },
  { nombre: "Reflector LED 50 W exterior", marca: "Lumina", categoria: "electricidad", precio: 22900, unidad: "unidad", stock: false, descripcion: "IP65, luz fría." },
  // Pileta
  { nombre: "Cloro granulado 10 kg", marca: "Clarimar", categoria: "pileta", precio: 58900, precioAnterior: 69900, unidad: "balde", stock: true, descripcion: "Disolución rápida. Para tratamiento de choque y mantenimiento." },
  { nombre: "Pastillas de cloro triple acción (× 5 de 200 g)", marca: "Clarimar", categoria: "pileta", precio: 16900, unidad: "pack", stock: true, descripcion: "Cloro, alguicida y clarificante." },
  { nombre: "Limpiafondo 8 ruedas con cepillo", marca: "Clarimar", categoria: "pileta", precio: 27500, unidad: "unidad", stock: true, nuevo: true, descripcion: "Para manguera de 1½\". No incluye manguera." },
  { nombre: "Barrefondo flexible 45 cm", marca: "Clarimar", categoria: "pileta", precio: 11200, unidad: "unidad", stock: true, descripcion: "Cerdas de nylon, para pileta de material." },
  // Pinturería
  { nombre: "Látex interior mate blanco 20 l", marca: "Colorama", categoria: "pintureria", precio: 92500, precioAnterior: 104900, unidad: "balde", stock: true, descripcion: "Lavable, rendimiento 10 a 12 m² por litro y mano." },
  { nombre: "Rodillo lana 22 cm con mango", marca: "Colorama", categoria: "pintureria", precio: 7400, unidad: "unidad", stock: true, descripcion: "Para látex en paredes lisas y semilisas." },
  { nombre: "Pincel cerda natural N° 20", marca: "Colorama", categoria: "pintureria", precio: 3290, unidad: "unidad", stock: true, descripcion: "Virola de acero, mango de madera." },
  { nombre: "Enduido plástico interior 4 kg", marca: "Colorama", categoria: "pintureria", precio: 9900, unidad: "pote", stock: false, descripcion: "Para alisar y reparar paredes antes de pintar." },
  // Jardín
  { nombre: "Manguera reforzada ½\" × 25 m", marca: "Verdal", categoria: "jardin", precio: 24900, precioAnterior: 28900, unidad: "unidad", stock: true, descripcion: "Tres capas, no se dobla. Con acoples." },
  { nombre: "Pistola de riego 7 funciones", marca: "Verdal", categoria: "jardin", precio: 8900, unidad: "unidad", stock: true, descripcion: "Gatillo con traba, cuerpo plástico reforzado." },
  { nombre: "Tijera de podar 8\"", marca: "Verdal", categoria: "jardin", precio: 13500, unidad: "unidad", stock: true, descripcion: "Hojas de acero al carbono, traba de seguridad." },
  // Mascotas
  { nombre: "Alimento perro adulto 15 kg", marca: "Canela", categoria: "mascotas", precio: 48900, unidad: "bolsa", stock: true, descripcion: "Razas medianas y grandes. Pollo y arroz." },
  { nombre: "Piedras sanitarias para gato 4 kg", marca: "Canela", categoria: "mascotas", precio: 6200, precioAnterior: 7100, unidad: "bolsa", stock: true, descripcion: "Aglutinantes, con aroma a lavanda." },
  { nombre: "Correa extensible 5 m", marca: "Canela", categoria: "mascotas", precio: 15900, unidad: "unidad", stock: true, nuevo: true, descripcion: "Para perros de hasta 25 kg, botón de freno." },
];

function slugify(t: string): string {
  return t
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60)
    .replace(/-$/, "");
}

// Ilustraciones de la demo (scripts/ilustraciones.py), en el mismo orden que las filas.
const ilustraciones = ["caja-tornillos","taladro","cinta-metrica","candado","destornilladores","cartucho","bolsa-tarugos","pinza","llave-paso","cano","flexible","griferia","teflon","cable","lampara","cinta-aisladora","zapatilla","termica","reflector","balde-cloro","pastillas","limpiafondo","barrefondo","latex","rodillo","pincel","enduido","manguera","pistola-riego","tijera-podar","alimento-perro","piedras-gato","correa"];

export const productos: Producto[] = filas.map((f, i) => ({
  ...f,
  codigo: f.codigo ?? propio(),
  slug: slugify(f.nombre),
  precioMayorista: Math.round((f.precio * 0.85) / 10) * 10,
  imagen: ilustraciones[i] ? `/img/${ilustraciones[i]}.svg` : undefined,
}));

export const categoriaDe = (slug: string) => categorias.find((c) => c.slug === slug)!;
export const descuento = (p: Producto) =>
  p.precioAnterior ? Math.round((1 - p.precio / p.precioAnterior) * 100) : 0;
export const pesos = (n: number) => "$ " + n.toLocaleString("es-AR", { maximumFractionDigits: 0 });

// Datos del local. Lo que todavía no confirmó el negocio queda vacío y la tienda no lo muestra
// (horario, WhatsApp, razón social, CUIT y Data Fiscal: pedirlos a Daniel antes de salir).
export const local = {
  direccion: "Dr. Arturo Capdevila 1235",
  ciudad: "Córdoba",
  telefono: "0351 478-7185",
  mapa: "https://www.google.com/maps/search/?api=1&query=Dr.+Arturo+Capdevila+1235%2C+C%C3%B3rdoba%2C+Argentina",
  horario: "",        // p. ej. "Lunes a viernes de 8 a 18 h · Sábados de 8 a 13 h"
  whatsapp: "",       // solo números con código de país, p. ej. "5493511234567"
  mail: "",           // mail de atención al cliente
  mailCuentas: "odoo@comercio-ejemplo.example", // a dónde piden los mayoristas un cambio de CUIT, razón social o IVA
  razonSocial: "",    // como figura en ARCA
  cuit: "",           // 30-12345678-9
  dataFiscal: "",     // dirección del QR «Data Fiscal» de ARCA
};
// Mientras sea false, las páginas legales muestran «Borrador»: falta que las revise un profesional
// y completar razón social, CUIT y mail de arriba.
export const legalesRevisados = false;
/** Días para retirar un pedido listo antes de que el local llame para decidir (DIAS_AVISO_LOCAL). */
export const diasRetiro = 7;
export const wa = (texto: string) => (local.whatsapp ? `https://wa.me/${local.whatsapp}?text=${encodeURIComponent(texto)}` : "");

// Historial de pedidos de un cliente de ejemplo (en la tienda real sale de Odoo).
// Las líneas citan el código de barras: la página busca el producto real (D1) con ese código.
export type Pedido = { numero: string; fecha: string; estado: "Listo para retirar" | "Retirado"; lineas: { codigo: string; cant: number }[] };
const s = (texto: string) => productos.find((p) => p.nombre.startsWith(texto))!.codigo;
export const clienteDemo = { nombre: "Ferretería Ejemplo SRL", mayorista: true };
export const pedidosDemo: Pedido[] = [
  { numero: "W-0041", fecha: "2026-10-30", estado: "Listo para retirar", lineas: [
    { codigo: s("Tornillo autoperforante"), cant: 10 }, { codigo: s("Tarugo nylon"), cant: 20 }, { codigo: s("Cinta aisladora"), cant: 24 }, { codigo: s("Silicona"), cant: 12 } ] },
  { numero: "W-0032", fecha: "2026-10-16", estado: "Retirado", lineas: [
    { codigo: s("Caño termofusión"), cant: 30 }, { codigo: s("Llave de paso"), cant: 6 }, { codigo: s("Cinta de teflón"), cant: 50 }, { codigo: s("Flexible"), cant: 12 } ] },
  { numero: "W-0027", fecha: "2026-10-02", estado: "Retirado", lineas: [
    { codigo: s("Cable unipolar"), cant: 4 }, { codigo: s("Lámpara LED"), cant: 40 }, { codigo: s("Llave térmica"), cant: 5 } ] },
];
