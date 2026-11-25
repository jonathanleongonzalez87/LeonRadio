// Utilidades para componentes de canvas: colores de marca (tokens CSS) y bucle de dibujo.

const NAMES = {
  carbon: "--c-carbon", orange: "--c-orange", cream: "--c-cream", bronze: "--c-bronze",
  bronzeD: "--c-bronze-d", sand: "--c-sand", g900: "--c-g900", g700: "--c-g700",
  g500: "--c-g500", g300: "--c-g300", ink: "--c-ink", felt: "--c-felt",
};
let cache = null;

/** Colores de la marca leídos de tokens.css (nunca colores sueltos en los componentes). */
export function tokens() {
  if (!cache) {
    const cs = getComputedStyle(document.documentElement);
    cache = Object.fromEntries(Object.entries(NAMES).map(([k, v]) => [k, cs.getPropertyValue(v).trim() || "#888"]));
  }
  return cache;
}
// Los tokens de paleta son fijos (no cambian con el tema), pero se invalidan por seguridad.
new MutationObserver(() => { cache = null; }).observe(document.documentElement, { attributes: true });

export const FONT_DISPLAY = '"Space Grotesk", "Helvetica Neue", Arial, sans-serif';
export const FONT_MONO = 'ui-monospace, "Cascadia Mono", Consolas, monospace';

/**
 * Crea un <div class="cmp"> con un canvas que se ajusta a su tamaño (HiDPI) y llama a
 * draw(ctx, w, h, t, dt) en cada cuadro mientras el elemento siga en el documento.
 */
export function canvasComponent(draw) {
  const root = document.createElement("div");
  root.className = "cmp";
  const canvas = document.createElement("canvas");
  root.append(canvas);
  const ctx = canvas.getContext("2d");
  let w = 0, h = 0, seen = false, waited = 0, last = performance.now();

  const ro = new ResizeObserver(() => {
    const dpr = window.devicePixelRatio || 1;
    w = root.clientWidth; h = root.clientHeight;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  });
  ro.observe(root);

  const frame = (t) => {
    if (root.isConnected) seen = true;
    else if (seen || ++waited > 120) { ro.disconnect(); return; } // ya no está en pantalla: parar
    const dt = Math.min(0.1, (t - last) / 1000);
    last = t;
    if (w > 4 && h > 4) {
      ctx.clearRect(0, 0, w, h);
      try { draw(ctx, w, h, t, dt); } catch (e) { console.error(e); }
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  return root;
}

export function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h);
}
