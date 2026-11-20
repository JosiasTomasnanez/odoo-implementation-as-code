// Service worker de la tienda: permite instalarla como aplicación (PWA) y que abra rápido.
// Precios, stock, carrito, pagos y cuentas van SIEMPRE a la red (nunca se muestran guardados).
// Lo único guardado: estilos, scripts y fuentes (sus nombres cambian con cada versión), el logo,
// los íconos, las fotos de productos (su nombre cambia si cambia la foto) y la página «Sin conexión».
// Lo sirve src/pages/tienda-sw.js.ts en /tienda-sw.js (no /sw.js: esa dirección quedó en la caché de Cloudflare). Al cambiar este archivo, subir VERSION.
const VERSION = "tienda-v2";
const FIJOS = ["/offline", "/logo.webp", "/favicon.png", "/icono-192.png", "/manifest.webmanifest"];
const MAX_FOTOS = 300;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(FIJOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== VERSION && k !== `${VERSION}-fotos`).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

const guardable = (url) =>
  url.pathname.startsWith("/_astro/") || FIJOS.includes(url.pathname) || url.pathname === "/icono-512.png" || url.pathname === "/apple-touch-icon.png";

async function primeroGuardado(pedido, cache, limite) {
  const c = await caches.open(cache);
  const hay = await c.match(pedido);
  if (hay) return hay;
  const r = await fetch(pedido);
  if (r.ok && r.type === "basic") {
    await c.put(pedido, r.clone());
    if (limite) c.keys().then((ks) => ks.length > limite && Promise.all(ks.slice(0, ks.length - limite).map((k) => c.delete(k))));
  }
  return r;
}

self.addEventListener("fetch", (e) => {
  const p = e.request;
  const url = new URL(p.url);
  if (p.method !== "GET" || url.origin !== self.location.origin) return;
  if (p.mode === "navigate") {
    // Las páginas: siempre de la red; sin conexión, el aviso
    e.respondWith(fetch(p).catch(() => caches.match("/offline")));
    return;
  }
  if (/^\/img\/p\/[0-9a-f]{40,64}$/.test(url.pathname)) { e.respondWith(primeroGuardado(p, `${VERSION}-fotos`, MAX_FOTOS)); return; }
  if (guardable(url)) e.respondWith(primeroGuardado(p, VERSION));
  // Todo lo demás (API, precios, carrito, pagos, cuentas): el navegador normal, sin guardar
});
