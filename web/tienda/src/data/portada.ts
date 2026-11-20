// Anuncios del carrusel de la portada. En la tienda real los arma el negocio desde el editor
// (/admin); acá, de ejemplo. Tonos sobrios: azul noche o blanco (09/11, «menos colorinche»).
export type Anuncio = {
  tono: "noche" | "claro"; pre: string; titulo: string; texto: string;
  boton: string; href: string; sello?: { arriba: string; num: string; abajo?: string };
};
export const anuncios: Anuncio[] = [
  { tono: "noche", pre: "Hasta agotar stock", titulo: "Ofertas de la semana", texto: "Precios rebajados en ferretería, pileta, electricidad y pinturería. Lo pedís acá y lo retirás en el local.", boton: "Ver las ofertas", href: "/ofertas/", sello: { arriba: "Hasta", num: "16%", abajo: "off" } },
  { tono: "claro", pre: "Temporada", titulo: "Llegó la pileta", texto: "Cloro, pastillas, limpiafondos y barrefondos. Todo listo para el verano.", boton: "Ver pileta", href: "/buscar/?q=pileta", sello: { arriba: "Cloro", num: "−16%", abajo: "10 kg" } },
];
