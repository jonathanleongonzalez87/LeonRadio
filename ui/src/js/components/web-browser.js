// Navegador web propio: barra de direcciones + página incrustada (iframe) que SIGUE SONANDO aunque cambies de pestaña.
//
// Los paneles se redibujan al cambiar el estado y eso destruiría el iframe (y cortaría el audio del sitio).
// Por eso el iframe vive en una capa fija fuera de los paneles; el panel solo deja un hueco (`stage`) y la capa
// coloca el iframe encima. Si el hueco no se ve (otra pestaña, panel cerrado) el iframe se oculta, sin recargarse.
//
// Límites del navegador: no se puede ir atrás/adelante dentro de una página de otro dominio, y los sitios que
// prohíben ser incrustados (X-Frame-Options / CSP frame-ancestors, p. ej. YouTube o Google) quedan en blanco:
// para esos hay un botón que los abre en una ventana aparte.
const frames = new Map();           // clave -> { frame, url, stage }
let layer = null;
let timer = null;

function ensureLayer() {
  if (layer && layer.isConnected) return;
  layer = document.createElement("div");
  layer.id = "web-layer";
  layer.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:20";
  document.body.append(layer);
}

function place() {
  let any = false;
  frames.forEach((f) => {
    const st = f.stage;
    const r = st && st.isConnected ? st.getBoundingClientRect() : null;
    const visible = r && r.width > 20 && r.height > 20 && st.offsetParent !== null;
    if (!visible) { f.frame.style.display = "none"; return; }
    any = true;
    Object.assign(f.frame.style, {
      display: "block", left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px`,
    });
    const b = st.closest(".body")?.getBoundingClientRect();    // no sobresalir del panel si se desplaza
    f.frame.style.clipPath = b
      ? `inset(${Math.max(0, b.top - r.top)}px ${Math.max(0, r.right - b.right)}px ${Math.max(0, r.bottom - b.bottom)}px ${Math.max(0, b.left - r.left)}px)`
      : "none";
  });
  void any;                          // el reloj sigue: al volver a la pestaña el iframe reaparece solo
}

function startPlacing() {
  if (!timer) timer = setInterval(place, 120);
  place();
}

/** Acepta «rocklandradio.co» o «https://…»; solo http(s). Devuelve null si no parece una dirección. */
export function normalizeUrl(text) {
  let t = String(text || "").trim();
  if (!t) return null;
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(t)) t = `https://${t}`;
  try {
    const u = new URL(t);
    if (!/^https?:$/.test(u.protocol) || !u.hostname.includes(".") && u.hostname !== "localhost") return null;
    return u.href;
  } catch { return null; }
}

export function webBrowser(props) {
  ensureLayer();
  const key = /^[\w.-]{1,40}$/.test(props.id || "") ? props.id : "nav";
  const home = normalizeUrl(props.home);
  let f = frames.get(key);
  if (!f) {
    const frame = document.createElement("iframe");
    frame.title = "Navegador";
    frame.setAttribute("allow", "autoplay; fullscreen; encrypted-media; picture-in-picture; clipboard-write");
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms allow-popups allow-presentation allow-modals");
    frame.referrerPolicy = "no-referrer";
    frame.style.cssText = "position:fixed;display:none;border:0;background:#fff;pointer-events:auto;border-radius:0 0 4px 4px";
    layer.append(frame);
    f = { frame, url: "", stage: null };
    frames.set(key, f);
  }

  const root = document.createElement("div");
  root.className = "webb";
  const bar = document.createElement("div");
  bar.className = "webb-bar";
  const input = document.createElement("input");
  input.type = "text"; input.className = "webb-url"; input.spellcheck = false;
  input.placeholder = "Escribe una dirección (p. ej. rocklandradio.co)";
  input.value = f.url;
  const msg = document.createElement("div");
  msg.className = "webb-msg";

  const go = (raw) => {
    const url = normalizeUrl(raw);
    if (!url) { msg.textContent = "Dirección no válida"; return; }
    msg.textContent = "";
    f.url = url; input.value = url;
    f.frame.src = url;
    startPlacing();
  };
  const btn = (txt, title, fn) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "u-btn sm"; b.textContent = txt; b.title = title;
    b.setAttribute("aria-label", title);
    b.addEventListener("click", fn);
    return b;
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(input.value); });
  bar.append(
    btn("🏠", "Inicio (sitio de la emisora)", () => { if (home) go(home); else msg.textContent = "La emisora no tiene sitio web configurado"; }),
    btn("⟳", "Recargar", () => { if (f.url) { f.frame.src = "about:blank"; setTimeout(() => { f.frame.src = f.url; }, 30); } }),
    input,
    btn("→", "Ir", () => go(input.value)),
    btn("↗", "Abrir en una ventana aparte (para sitios que no se dejan incrustar)", () => { if (f.url) window.open(f.url, "_blank", "noopener"); }),
  );

  const stage = document.createElement("div");
  stage.className = "webb-stage";
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = f.url ? "" : "Escribe una dirección o pulsa 🏠";
  stage.append(empty);
  f.stage = stage;
  root.append(bar, msg, stage);
  startPlacing();
  return root;
}
