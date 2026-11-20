// Carrito y partes interactivas de la tienda. El carrito se guarda en este navegador
// (localStorage) y solo tiene «producto → cantidad»: los precios se piden siempre a la tienda
// (/api/productos), nunca se toman de lo guardado en el navegador.
type P = {
  slug: string; nombre: string; unidad: string; imagen: string | null; categoria: string | null;
  precio: number; precio_anterior: number | null; vendible: boolean; consultar: boolean;
  desde?: number; paso?: number; // solo mayoristas: mínimo (en bultos enteros) y de a cuánto
  hay?: number | null; // cuánto se puede vender ahora (null = sin tope: no se controla o es a consultar)
};
/** Mayorista: la cantidad válida más cercana hacia arriba (0 = no lo lleva). */
const ajustar = (q: number, desde = 1, paso = 1) => (q <= 0 ? 0 : Math.max(desde, Math.ceil(q / paso) * paso));
/** Uno menos: un bulto menos, al múltiplo de abajo; si queda por debajo del mínimo, 0 (sale). */
const bajar = (q: number, desde = 1, paso = 1) => {
  const v = Math.ceil(q / paso) * paso - paso;
  return v < desde ? 0 : v;
};
type Carrito = Record<string, number>;

const CLAVE = "cf-carrito";
// En el sitio mayorista no hay fichas de producto: el carrito no enlaza a ellas
const MAYORISTA = document.body.dataset.sitio === "mayorista";
const pesos = (c: number) => "$ " + (c / 100).toLocaleString("es-AR", { maximumFractionDigits: c % 100 ? 2 : 0, minimumFractionDigits: c % 100 ? 2 : 0 });
const norm = (t: string) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function leer(): Carrito {
  try {
    const d = JSON.parse(localStorage.getItem(CLAVE) || "{}");
    const c: Carrito = {};
    // Solo lo que tiene forma de carrito: slugs válidos y cantidades enteras razonables
    for (const [k, v] of Object.entries(d ?? {})) if (/^[a-z0-9-]{1,90}$/.test(k) && Number.isInteger(v) && (v as number) > 0) c[k] = Math.min(v as number, 999);
    return c;
  } catch { return {}; }
}
function guardar(c: Carrito) {
  try { localStorage.setItem(CLAVE, JSON.stringify(c)); } catch { /* sin almacenamiento: queda en memoria */ }
  memoria = c;
  contador();
}
let memoria: Carrito = leer();


function contador() {
  const n = Object.values(memoria).reduce((a, b) => a + b, 0);
  document.querySelectorAll<HTMLElement>("[data-contador]").forEach((el) => {
    el.textContent = String(n);
    el.toggleAttribute("data-vacio", n === 0);
  });
}
function sumar(slug: string, cant = 1) {
  const c = { ...memoria };
  if (!/^[a-z0-9-]{1,90}$/.test(slug) || !Number.isInteger(cant) || cant < 1) return;
  c[slug] = Math.min((c[slug] || 0) + cant, 999);
  guardar(c);
  document.querySelectorAll<HTMLElement>(".carr-btn, .p-carr").forEach((b) => {
    b.classList.remove("salto"); void b.offsetWidth; b.classList.add("salto");
  });
}

/** Saca del carrito lo que la tienda ya no devuelve (renombrado o despublicado en Odoo: su slug
 *  cambió). Si quedara guardado, no se ve pero se manda, y cada compra daría error. */
function depurar(lista: P[], slugs: string[]): number {
  const fuera = slugs.filter((s) => !lista.some((p) => p.slug === s));
  if (!fuera.length) return 0;
  const c = { ...memoria };
  for (const s of fuera) delete c[s];
  guardar(c);
  return fuera.length;
}
// Lo que está en el carrito pero hoy no se puede vender: se muestra, pero no se manda al pagar
let sinStock = new Set<string>();

async function productos(slugs: string[]): Promise<P[]> {
  if (!slugs.length) return [];
  const r = await fetch(`/api/productos?slugs=${encodeURIComponent(slugs.join(","))}`);
  return r.ok ? r.json() : [];
}

// Botones «Agregar» (tarjetas y ficha)
document.addEventListener("click", (e) => {
  const b = (e.target as HTMLElement).closest<HTMLButtonElement>("[data-agregar]");
  if (!b || b.disabled) return;
  const cantEl = b.dataset.cantidad ? document.querySelector<HTMLOutputElement>(b.dataset.cantidad) : null;
  sumar(b.dataset.agregar!, b.dataset.cantFija ? Number(b.dataset.cantFija) : cantEl ? Number(cantEl.value) : 1);
  const txt = b.textContent;
  b.classList.add("ok");
  b.textContent = "Agregado ✓";
  setTimeout(() => { b.classList.remove("ok"); b.textContent = txt; }, 1200);
});

// Cantidad en la ficha
document.querySelectorAll<HTMLElement>("[data-cant]").forEach((box) => {
  const out = box.querySelector("output")!;
  box.addEventListener("click", (e) => {
    const d = (e.target as HTMLElement).closest<HTMLElement>("[data-d]")?.dataset.d;
    if (!d) return;
    out.value = String(Math.max(1, Number(out.value) + Number(d)));
  });
});

// Filtros del listado: en el celular se abren en una hoja desde abajo (en la PC están al costado)
const hoja = document.querySelector<HTMLElement>("[data-hoja-filtros]");
if (hoja) {
  const velo = document.querySelector<HTMLElement>("[data-velo]")!;
  const abrir = (si: boolean) => {
    hoja.classList.toggle("abierta", si); velo.classList.toggle("abierta", si);
    document.querySelector("[data-abrir-filtros]")?.setAttribute("aria-expanded", String(si));
    if (si) hoja.querySelector<HTMLElement>("a, button")?.focus({ preventScroll: true });
  };
  document.querySelector("[data-abrir-filtros]")?.addEventListener("click", () => abrir(true));
  hoja.querySelector("[data-cerrar-filtros]")?.addEventListener("click", () => abrir(false));
  velo.addEventListener("click", () => abrir(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && hoja.classList.contains("abierta")) abrir(false); });
}

// Íconos mínimos para lo que se arma en el navegador
const ICONOS: Record<string, string> = {};
document.querySelectorAll<HTMLTemplateElement>("template[data-icono]").forEach((t) => (ICONOS[t.dataset.icono!] = t.innerHTML));
const icono = (cat: string | null) => {
  const n = (cat ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const t: [string, string][] = [["sanit", "canilla"], ["electr", "rayo"], ["pilet", "ola"], ["pintur", "pincel"], ["jardin", "hoja"], ["mascot", "huella"]];
  return ICONOS[t.find(([k]) => n.includes(k))?.[1] ?? "tornillo"] ?? "";
};
const esc = (t: string) => t.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!);
const foto = (p: P) => p.imagen && /^[0-9a-f]{40,64}$/.test(p.imagen)
  ? `<div class="foto"><img src="/img/p/${p.imagen}-400" alt="" loading="lazy" width="200" height="200"></div>`
  : `<div class="foto">${icono(p.categoria)}</div>`;

// Página del carrito
const lineas = document.querySelector<HTMLElement>("[data-lineas]");
if (lineas) {
  const pintar = (lista: P[]) => {
    // Mayorista: lo que no respeta el mínimo o el bulto se sube a la cantidad válida (y se avisa)
    let ajustados = 0;
    if (MAYORISTA) {
      const c = { ...memoria };
      for (const p of lista) if (c[p.slug] && ajustar(c[p.slug], p.desde, p.paso) !== c[p.slug]) { c[p.slug] = Math.min(ajustar(c[p.slug], p.desde, p.paso), 999); ajustados++; }
      if (ajustados) guardar(c);
    }
    const aviso = document.querySelector<HTMLElement>("[data-ajustados]");
    if (aviso) aviso.hidden = !ajustados;
    const items = Object.entries(memoria)
      .map(([slug, n]) => ({ p: lista.find((x) => x.slug === slug), n }))
      .filter((x): x is { p: P; n: number } => !!x.p && x.n > 0);
    document.querySelector<HTMLElement>("[data-carrito-lleno]")!.hidden = items.length === 0;
    document.querySelector<HTMLElement>("[data-carrito-vacio]")!.hidden = items.length > 0;
    lineas.innerHTML = items.map(({ p, n }) => `<div class="linea">
        ${foto(p)}
        <div>${MAYORISTA ? `<span class="nom">${esc(p.nombre)}</span>` : `<a class="nom" href="/producto/${esc(p.slug)}/">${esc(p.nombre)}</a>`}<div class="cod">${pesos(p.precio)} por ${esc(p.unidad.toLowerCase())}${p.paso && p.paso > 1 ? ` · bulto × ${p.paso}` : ""}${p.desde && p.desde > (p.paso || 1) ? ` · desde ${p.desde}` : ""}</div>${p.consultar ? '<div class="stock consultar">Te confirmamos disponibilidad en el día</div>' : ""}${!p.vendible ? '<div class="stock no">Sin stock: no se va a cobrar</div>' : ""}${p.vendible && p.hay != null && n > p.hay ? `<div class="stock falta">Quedan ${p.hay}. <button type="button" class="tope" data-tope="${p.slug}">${p.hay > 0 ? `Llevar ${p.hay}` : "Quitar"}</button></div>` : p.vendible && p.hay != null && n === p.hay ? '<div class="stock consultar">Es lo último que queda</div>' : ""}</div>
        <div class="der"><span class="precio">${pesos(p.precio * n)}</span>
          <span class="cant"><button type="button" data-mod="${p.slug}" data-d="-1" aria-label="Uno menos">−</button><output>${n}</output><button type="button" data-mod="${p.slug}" data-d="1" aria-label="Uno más"${p.hay != null && n + (p.paso || 1) > p.hay ? " disabled" : ""}>+</button></span>
          <button class="quitar" type="button" data-quitar="${p.slug}">Quitar</button></div>
      </div>`).join("");
    const cobrables = items.filter(({ p }) => p.vendible);
    const total = cobrables.reduce((t, { p, n }) => t + p.precio * n, 0);
    const sub = cobrables.reduce((t, { p, n }) => t + Math.max(p.precio_anterior || p.precio, p.precio) * n, 0);
    const ahorro = sub - total;
    const u = items.reduce((t, { n }) => t + n, 0);
    document.querySelector("[data-unidades]")!.textContent = `${u} ${u === 1 ? "artículo" : "artículos"}`;
    document.querySelector("[data-subtotal]")!.textContent = pesos(sub);
    document.querySelector("[data-ahorro]")!.textContent = ahorro ? "− " + pesos(ahorro) : pesos(0);
    document.querySelector("[data-total]")!.textContent = pesos(total);
    // Si de algo se pide más de lo que hay, no se sigue hasta ajustar (el servidor lo rechazaría igual)
    const seguir = document.querySelector<HTMLAnchorElement>("[data-seguir]");
    const falta = items.some(({ p, n }) => p.vendible && p.hay != null && n > p.hay);
    if (seguir) { seguir.toggleAttribute("aria-disabled", falta); seguir.classList.toggle("apagado", falta); }
    const av = document.querySelector<HTMLElement>("[data-falta]");
    if (av) av.hidden = !falta;
  };
  document.querySelector("[data-seguir]")?.addEventListener("click", (e) => { if ((e.currentTarget as HTMLElement).hasAttribute("aria-disabled")) e.preventDefault(); });
  const pedidos = Object.keys(memoria);
  productos(pedidos).then((d) => {
    const quitados = document.querySelector<HTMLElement>("[data-quitados]");
    if (depurar(d, pedidos) && quitados) quitados.hidden = false;
    pintar(d);
    lineas.addEventListener("click", (e) => {
      const t = e.target as HTMLElement;
      const m = t.closest<HTMLElement>("[data-mod]");
      const q = t.closest<HTMLElement>("[data-quitar]");
      const tope = t.closest<HTMLElement>("[data-tope]");
      const c = { ...memoria };
      // «Llevar N»: baja la cantidad a lo que queda (en bultos enteros si es mayorista)
      if (tope) {
        const p = d.find((x) => x.slug === tope.dataset.tope);
        const paso = p?.paso || 1, hay = Math.floor((p?.hay ?? 0) / paso) * paso;
        c[tope.dataset.tope!] = hay >= (p?.desde || 1) ? hay : 0;
      } else
      if (m) {
        const p = d.find((x) => x.slug === m.dataset.mod);
        const paso = p?.paso || 1, desde = p?.desde || 1, ahora = c[m.dataset.mod!] || 0;
        // De a un bulto (mayorista); por debajo del mínimo sale del carrito
        c[m.dataset.mod!] = Number(m.dataset.d) > 0 ? ajustar(ahora + paso, desde, paso) : bajar(ahora, desde, paso);
      }
      else if (q) delete c[q.dataset.quitar!];
      else return;
      Object.keys(c).forEach((k) => c[k] <= 0 && delete c[k]);
      guardar(c);
      pintar(d);
    });
  });
}

// Pantalla de pago (/compra): resumen del pedido y el formulario
const mini = document.querySelector<HTMLElement>("[data-mini]");
if (mini) {
  const slugs = Object.keys(memoria);
  if (!slugs.length) location.replace("/carrito");
  productos(slugs).then((lista) => {
    if (depurar(lista, slugs)) return location.replace("/carrito");
    const items = Object.entries(memoria)
      .map(([slug, n]) => ({ p: lista.find((x) => x.slug === slug), n }))
      .filter((x): x is { p: P; n: number } => !!x.p && x.n > 0);
    if (!items.length) return location.replace("/carrito");
    sinStock = new Set(items.filter(({ p }) => !p.vendible).map(({ p }) => p.slug));
    mini.innerHTML = items.map(({ p, n }) => `<li>${foto(p)}<span class="nom">${esc(p.nombre)}</span><span class="n">× ${n}</span><span class="pr">${p.vendible ? pesos(p.precio * n) : "Sin stock"}</span></li>`).join("");
    const cobrables = items.filter(({ p }) => p.vendible);
    const total = cobrables.reduce((t, { p, n }) => t + p.precio * n, 0);
    const sub = cobrables.reduce((t, { p, n }) => t + Math.max(p.precio_anterior || p.precio, p.precio) * n, 0);
    const u = items.reduce((t, { n }) => t + n, 0);
    document.querySelector("[data-unidades]")!.textContent = `${u} ${u === 1 ? "artículo" : "artículos"}`;
    document.querySelector("[data-subtotal]")!.textContent = pesos(sub);
    document.querySelector("[data-ahorro]")!.textContent = sub - total ? "− " + pesos(sub - total) : pesos(0);
    document.querySelector("[data-total]")!.textContent = pesos(total);
    document.querySelector("[data-total-boton]")!.textContent = pesos(total);
  });
}
{
  // Comprar: la tienda arma el pedido con sus precios, reserva el stock y devuelve a dónde pagar.
  const form = document.querySelector<HTMLFormElement>("[data-compra]");
  const aviso = document.querySelector<HTMLElement>("[data-error-compra]");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const boton = form.querySelector<HTMLButtonElement>("[data-pagar]")!;
    const f = new FormData(form);
    const mostrar = (t: string) => { aviso!.textContent = t; aviso!.hidden = false; };
    aviso!.hidden = true;
    if (!form.checkValidity()) return mostrar("Completá tu nombre y un mail válido.");
    const turnstile = String(f.get("cf-turnstile-response") ?? "");
    if (!turnstile) return mostrar("Esperá un segundo a que se complete la verificación de seguridad.");
    const aPagar = Object.entries(memoria).filter(([slug]) => !sinStock.has(slug));
    if (!aPagar.length) return mostrar("No queda nada con stock en el carrito.");
    boton.disabled = true; boton.setAttribute("aria-busy", "true");
    try {
      const r = await fetch("/api/pedido", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lineas: aPagar.map(([slug, cantidad]) => ({ slug, cantidad })),
          nombre: String(f.get("nombre") ?? ""), email: String(f.get("email") ?? ""), telefono: String(f.get("telefono") ?? ""), turnstile,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok && typeof d.pago === "string" && /^https?:\/\//.test(d.pago)) { location.href = d.pago; return; }
      if (r.status === 409 && Array.isArray(d.slugs) && d.slugs.length) {
        // Algo dejó de estar a la venta mientras tanto: se saca y se recalcula
        const c = { ...memoria };
        for (const s of d.slugs) delete c[s];
        guardar(c);
        mostrar("Sacamos del carrito lo que ya no está a la venta. Revisá el total y volvé a tocar Pagar.");
        setTimeout(() => location.reload(), 2500);
        return;
      }
      if (r.status === 409 && d.faltantes) {
        mostrar("No alcanza el stock de: " + d.faltantes.map((x: { nombre: string; disponible: number }) => `${x.nombre} (hay ${x.disponible})`).join(", ") + ". Ajustá las cantidades.");
      } else mostrar(d.error || "No pudimos armar el pedido. Probá de nuevo.");
      (window as unknown as { turnstile?: { reset: () => void } }).turnstile?.reset();
    } catch { mostrar("Sin conexión. Probá de nuevo."); }
    boton.disabled = false; boton.removeAttribute("aria-busy");
  });
}

window.addEventListener("storage", () => { memoria = leer(); contador(); });
contador();

// Repetir un pedido: suma todas sus líneas con las mismas cantidades
document.querySelectorAll<HTMLButtonElement>("[data-repetir]").forEach((b) =>
  b.addEventListener("click", () => {
    const lineas = JSON.parse(b.dataset.repetir!) as { slug: string; cant: number }[];
    productos(lineas.map((l) => l.slug)).then((lista) => {
      const c = { ...memoria };
      lineas.forEach((l) => {
        if (lista.find((p) => p.slug === l.slug)?.vendible) c[l.slug] = Math.min((c[l.slug] || 0) + l.cant, 999);
      });
      guardar(c);
      location.href = "/carrito/";
    });
  }));

// Lista mayorista: la cantidad de cada fila ES la del carrito (se guarda al salir del campo), así
// no se pierde nada al cambiar de categoría, buscar o pasar de página. La barra muestra el pedido
// entero, también lo que no está en pantalla.
const tabla = document.querySelector<HTMLTableElement>(".tabla");
if (tabla) {
  const filas = [...tabla.querySelectorAll<HTMLTableRowElement>("[data-fila-lista]")];
  const ins = [...tabla.querySelectorAll<HTMLInputElement>(".cant-in")];
  const barra = document.querySelector<HTMLElement>("[data-barra-lista]")!;
  const precios: Record<string, number> = {};
  ins.forEach((i) => { precios[i.dataset.slug!] = Number(i.dataset.precio); if (memoria[i.dataset.slug!]) i.value = String(memoria[i.dataset.slug!]); });
  const recalcular = () => {
    const items = Object.entries(memoria);
    barra.hidden = items.length === 0;
    document.querySelector("[data-lista-n]")!.textContent = String(items.length);
    document.querySelector("[data-lista-total]")!.textContent = pesos(items.reduce((t, [slug, n]) => t + n * (precios[slug] ?? 0), 0));
  };
  // Precios de lo que está en el carrito pero no en esta pantalla
  const fuera = Object.keys(memoria).filter((sl) => !(sl in precios));
  if (fuera.length) productos(fuera).then((l) => { l.forEach((p) => (precios[p.slug] = p.precio)); recalcular(); });
  recalcular();
  // Al salir del campo: se sube a la cantidad válida (mínimo y bultos enteros), se avisa con el
  // color y se guarda en el carrito (vacío o 0 = se quita)
  tabla.addEventListener("change", (e) => {
    const i = e.target as HTMLInputElement;
    if (!i.classList.contains("cant-in")) return;
    const q = Math.floor(Number(i.value) || 0);
    const v = Math.min(ajustar(q, Number(i.dataset.desde) || 1, Number(i.dataset.paso) || 1), 999);
    i.value = v ? String(v) : "";
    i.classList.toggle("ajustada", v !== q && v > 0);
    // Decir por qué cambió (en el celular no se ve la columna «Se vende» al lado)
    const desde = Number(i.dataset.desde) || 1, paso = Number(i.dataset.paso) || 1;
    const aviso = i.closest("tr")?.querySelector<HTMLElement>("[data-aviso-cant]");
    if (aviso) aviso.textContent = v !== q && v > 0 ? (q < desde ? `Subimos a ${v}: es el mínimo` : `Redondeamos a ${v}: bultos de ${paso}`) : "";
    const c = { ...memoria };
    if (v > 0) c[i.dataset.slug!] = v; else delete c[i.dataset.slug!];
    guardar(c);
    recalcular();
  });
  tabla.addEventListener("keydown", (e) => {
    const i = e.target as HTMLInputElement;
    if (!i.classList.contains("cant-in") || e.key !== "Enter") return;
    e.preventDefault();
    const vis = ins.filter((x) => !x.disabled && !x.closest("tr")!.hidden);
    const sig = vis[vis.indexOf(i) + 1];
    if (sig) sig.focus(); else i.blur();
  });
  document.querySelector<HTMLInputElement>("#filtro-lista")?.addEventListener("input", (e) => {
    const ws = norm((e.target as HTMLInputElement).value).split(/\s+/).filter(Boolean);
    filas.forEach((f) => (f.hidden = !ws.every((w) => norm(f.dataset.filaLista!).includes(w))));
    tabla.querySelectorAll<HTMLElement>("[data-grupo]").forEach((g) => (g.hidden = !g.querySelector("[data-fila-lista]:not([hidden])")));
  });
}

// Carrusel de anuncios y filas deslizables
document.querySelectorAll<HTMLElement>("[data-carrusel], [data-fila]").forEach((box) => {
  const pista = box.querySelector<HTMLElement>("[data-pista]")!;
  const puntos = [...box.querySelectorAll<HTMLButtonElement>("[data-ir]")];
  const ant = box.querySelector<HTMLButtonElement>("[data-ant]");
  const sig = box.querySelector<HTMLButtonElement>("[data-sig]");
  const paso = () => (box.hasAttribute("data-carrusel") ? pista.clientWidth : pista.clientWidth * 0.75);
  const actual = () => Math.round(pista.scrollLeft / pista.clientWidth);
  const marcar = () => {
    const fin = pista.scrollLeft + pista.clientWidth >= pista.scrollWidth - 4;
    if (ant) ant.disabled = pista.scrollLeft <= 4;
    if (sig) sig.disabled = fin && !box.hasAttribute("data-carrusel");
    puntos.forEach((b, i) => b.setAttribute("aria-current", String(i === actual())));
  };
  const ir = (i: number) => pista.scrollTo({ left: i * pista.clientWidth });
  puntos.forEach((b, i) => b.addEventListener("click", () => ir(i)));
  ant?.addEventListener("click", () => pista.scrollBy({ left: -paso() }));
  sig?.addEventListener("click", () => {
    if (box.hasAttribute("data-carrusel")) ir((actual() + 1) % puntos.length);
    else pista.scrollBy({ left: paso() });
  });
  pista.addEventListener("scroll", () => requestAnimationFrame(marcar), { passive: true });
  marcar();
  // Pasa solo cada 6 s, salvo que la persona esté encima, lo esté tocando o prefiera sin movimiento
  if (box.hasAttribute("data-carrusel") && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    let quieto = false;
    ["pointerenter", "focusin", "touchstart"].forEach((ev) => box.addEventListener(ev, () => (quieto = true), { passive: true }));
    ["pointerleave", "focusout"].forEach((ev) => box.addEventListener(ev, () => (quieto = false)));
    setInterval(() => { if (!quieto && !document.hidden) ir((actual() + 1) % puntos.length); }, 6000);
  }
});

// ---------- App instalable (PWA, solo la tienda) ----------
if (!MAYORISTA && "serviceWorker" in navigator) {
  navigator.serviceWorker.register("/tienda-sw.js").catch(() => { /* sin service worker la tienda anda igual */ });
}
const instalada = matchMedia("(display-mode: standalone)").matches || (navigator as unknown as { standalone?: boolean }).standalone === true;
// Dentro de la app instalada no hay botón «atrás» del navegador (en iPhone): el de la barra
document.querySelector("[data-volver]")?.addEventListener("click", () => {
  if (history.length > 1 && document.referrer.startsWith(location.origin)) history.back(); else location.href = "/";
});
// «Instalar la app» en el pie: solo si el navegador lo ofrece (Android, Chrome, Edge) o, en
// iPhone/iPad con Safari, la indicación de cómo hacerlo. Ya instalada, no se muestra.
const caja = document.querySelector<HTMLElement>("[data-app]");
if (caja && !instalada && !MAYORISTA) {
  type Pedido = Event & { prompt: () => Promise<void> };
  let diferido: Pedido | null = null;
  const boton = caja.querySelector<HTMLButtonElement>("[data-instalar]")!;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    diferido = e as Pedido;
    caja.hidden = false; boton.hidden = false;
  });
  boton.addEventListener("click", async () => { await diferido?.prompt(); diferido = null; caja.hidden = true; });
  window.addEventListener("appinstalled", () => { caja.hidden = true; });
  if (/iphone|ipad|ipod/i.test(navigator.userAgent) && !/crios|fxios/i.test(navigator.userAgent)) {
    caja.hidden = false;
    caja.querySelector<HTMLElement>("[data-instalar-ios]")!.hidden = false;
  }
}

// Pedido pago: se vacía el carrito (lo que se compró ya no hace falta tenerlo ahí)
if (document.querySelector("[data-limpiar-carrito]")) guardar({});

// Sugerencias del buscador: productos y categorías mientras se escribe (flechas y Enter con el
// teclado; Escape las cierra). Si no hay red o no hay coincidencias, no aparece nada.
{
  const q = document.querySelector<HTMLInputElement>("#q");
  const caja = document.querySelector<HTMLElement>("[data-sugerencias]");
  if (q && caja) {
    let reloj = 0, pedido = 0, activo = -1;
    const cerrar = () => { caja.hidden = true; q.setAttribute("aria-expanded", "false"); q.removeAttribute("aria-activedescendant"); activo = -1; };
    const items = () => [...caja.querySelectorAll<HTMLAnchorElement>("a")];
    const marcar = (i: number) => {
      const l = items();
      if (!l.length) return;
      activo = (i + l.length) % l.length;
      l.forEach((a, k) => a.setAttribute("aria-selected", String(k === activo)));
      q.setAttribute("aria-activedescendant", l[activo].id);
      l[activo].scrollIntoView({ block: "nearest" });
    };
    q.addEventListener("input", () => {
      clearTimeout(reloj);
      const t = q.value.trim();
      if (t.length < 2) return cerrar();
      reloj = window.setTimeout(async () => {
        const n = ++pedido;
        try {
          const r = await fetch(`/api/sugerir?q=${encodeURIComponent(t)}`);
          if (!r.ok || n !== pedido) return;
          const d = (await r.json()) as { productos: P[]; categorias: { slug: string; nombre: string }[]; total?: number };
          if (!d.productos.length && !d.categorias.length) return cerrar();
          caja.innerHTML =
            d.categorias.map((c, i) => `<a id="sug-c${i}" role="option" class="sug cat" href="/categoria/${esc(c.slug)}/">En <b>${esc(c.nombre)}</b></a>`).join("") +
            d.productos.map((p, i) => `<a id="sug-p${i}" role="option" class="sug" href="/producto/${esc(p.slug)}/">${foto(p)}<span class="nom">${esc(p.nombre)}</span><span class="precio">${pesos(p.precio)}</span></a>`).join("") +
            ((d.total ?? 0) > d.productos.length ? `<a id="sug-t" role="option" class="sug todo" href="/buscar/?q=${encodeURIComponent(t)}">Ver los ${d.total} resultados</a>` : "");
          caja.hidden = false; q.setAttribute("aria-expanded", "true"); activo = -1;
        } catch { cerrar(); }
      }, 180);
    });
    q.addEventListener("keydown", (e) => {
      if (caja.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); marcar(activo + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); marcar(activo - 1); }
      else if (e.key === "Escape") cerrar();
      else if (e.key === "Enter" && activo >= 0) { e.preventDefault(); items()[activo].click(); }
    });
    document.addEventListener("click", (e) => { if (!(e.target as HTMLElement).closest(".busca")) cerrar(); });
    q.addEventListener("focus", () => { if (caja.innerHTML && q.value.trim().length >= 2) { caja.hidden = false; q.setAttribute("aria-expanded", "true"); } });
  }
}

// Al salir de la cuenta (o eliminarla) el carrito se vacía: el que entre después en este navegador,
// con otra cuenta, no tiene que encontrarse con el pedido a medio armar de otro.
document.addEventListener("submit", (ev) => {
  const f = ev.target as HTMLFormElement | null;
  if (f && /^\/api\/cuenta\/(salir|eliminar)$/.test(new URL(f.action, location.href).pathname)) {
    try { localStorage.removeItem(CLAVE); } catch { /* sin almacenamiento */ }
  }
});

// Menú de la cuenta (encabezado): se cierra al tocar afuera o con Escape
const menuCuenta = document.querySelector<HTMLDetailsElement>("[data-menu-cuenta]");
if (menuCuenta) {
  document.addEventListener("click", (e) => { if (menuCuenta.open && !menuCuenta.contains(e.target as Node)) menuCuenta.open = false; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && menuCuenta.open) { menuCuenta.open = false; menuCuenta.querySelector("summary")?.focus(); } });
}
