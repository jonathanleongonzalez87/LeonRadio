import { connectEvents, getEditors, getInfo } from "./api.js";
import { AreaManager, area, hasEditor, split, toggleBeside } from "./areas.js";
import { initMenus } from "./menus.js";

const KEY = "leonradio.workspaces.v11";
// Tolerante: si un HTML viejo (en caché) no trae algún elemento, se usa uno suelto en vez de fallar.
const $ = (s) => document.querySelector(s) ?? document.createElement("div");
const store = {
  get() { try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; } },
  set(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
};

const defaults = () => ({
  active: 0,
  list: [
    // Las cuatro estaciones de trabajo, en el orden de la arquitectura: Al Aire, Programación, Dirección, Producción.
    { name: "Al Aire", tree: split("v",
        // franja superior delgada: Reloj | VU | Aire | Próxima | Controles
        split("h", area("reloj", true),
          split("h", area("vu", true),
            split("h", area("aire", true), split("h", area("proxima", true), area("controles"), 0.4), 0.46), 0.25), 0.12),
        // cuerpo: Varios (Botonera/Eventos/Explorador por pestañas) + Historial | Emisión con Metadatos debajo
        split("h",
          split("v", area("varios"), area("historial"), 0.6),
          split("v", area("emision"), area("metadatos"), 0.78), 0.34),
        0.22) },
    { name: "Programación", tree: split("h",
        split("v", area("programacion"), area("varios"), 0.3),
        split("v", area("emision"), area("historial"), 0.62), 0.4) },
    { name: "Dirección", tree: split("h", area("direccion"), area("historial"), 0.5) },
    { name: "Producción", tree: split("h", area("produccion"), area("historial"), 0.5) },
  ],
});

let ws = store.get();
if (!ws?.list?.length) ws = defaults();
let mgr;

// Barra de herramientas: lámparas-pulsador de las 4 listas auxiliares (se muestran junto a Emisión)
function syncAux() {
  if (!mgr?.tree) return;
  document.querySelectorAll("#aux-toggles button").forEach((b) =>
    b.setAttribute("aria-pressed", String(hasEditor(mgr.tree, `aux${b.dataset.n}`))));
}
function buildAuxToggles(editors) {
  const box = $("#aux-toggles");
  for (let n = 1; n <= 4; n++) {
    if (!editors.some((e) => e.id === `aux${n}`)) continue;
    const b = document.createElement("button");
    b.type = "button"; b.className = "aux-btn"; b.dataset.n = String(n); b.textContent = String(n);
    b.title = `Lista auxiliar ${n} (mostrar/ocultar junto a Emisión)`;
    b.setAttribute("aria-label", `Lista auxiliar ${n}`);
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", () => mgr.commit(toggleBeside(mgr.tree, `aux${n}`, "emision")));
    box.append(b);
  }
}

function renderTabs() {
  const tabs = $("#tabs");
  tabs.replaceChildren();
  ws.list.forEach((w, i) => {
    const b = document.createElement("button");
    b.className = "tab"; b.role = "tab"; b.textContent = w.name;
    b.setAttribute("aria-selected", String(i === ws.active));
    b.addEventListener("click", () => { ws.active = i; store.set(ws); renderTabs(); mgr.setTree(w.tree); });
    b.addEventListener("dblclick", () => {
      const n = prompt("Nombre del workspace (vacío = eliminar)", w.name);
      if (n === null) return;
      if (n.trim() === "" && ws.list.length > 1) { ws.list.splice(i, 1); ws.active = Math.max(0, i - 1); }
      else if (n.trim()) w.name = n.trim().slice(0, 24);
      store.set(ws); renderTabs(); mgr.setTree(ws.list[ws.active].tree);
    });
    tabs.append(b);
  });
  const add = document.createElement("button");
  add.className = "tab add"; add.textContent = "+"; add.title = "Nuevo workspace (copia del actual)";
  add.addEventListener("click", () => {
    const copy = JSON.parse(JSON.stringify(ws.list[ws.active].tree));
    ws.list.push({ name: `Workspace ${ws.list.length + 1}`, tree: copy });
    ws.active = ws.list.length - 1; store.set(ws); renderTabs(); mgr.setTree(copy);
  });
  tabs.append(add);
}

function tickClock() {
  $("#clock").textContent = new Date().toLocaleTimeString("es-CO", { timeZone: "America/Bogota", hour12: false });
}

function initTheme() {
  let t = "dark";
  try { t = localStorage.getItem("leonradio.theme") || "dark"; } catch { /* nada */ }
  document.documentElement.dataset.theme = t;
  $("#theme").addEventListener("click", () => {
    t = t === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("leonradio.theme", t); } catch { /* nada */ }
  });
}

// Pantalla de carga: se queda hasta que el usuario hace clic (o pulsa Enter/Espacio/Esc).
function splash(msg, pct) {
  const m = document.getElementById("splash-msg");
  if (m) m.textContent = msg;
  const bar = document.querySelector("#splash .splash-bar i");
  if (bar && pct != null) bar.style.width = `${pct}%`;
}
function hideSplash() {
  const s = document.getElementById("splash");
  if (!s) return;
  s.classList.add("ready");
  const bye = () => {
    document.removeEventListener("keydown", key, true);
    s.classList.add("out");
    setTimeout(() => s.remove(), 600);
  };
  const key = (e) => { if (["Enter", " ", "Escape"].includes(e.key)) { e.preventDefault(); bye(); } };
  s.addEventListener("click", bye, { once: true });
  document.addEventListener("keydown", key, true);
}

async function boot() {
  splash("Conectando con el motor…", 25);
  initTheme();
  tickClock(); setInterval(tickClock, 1000);
  const [info, editors] = await Promise.all([getInfo(), getEditors()]);
  $("#station").textContent = info.station;
  splash("Armando los paneles…", 65);
  mgr = new AreaManager($("#screen"), {
    editors,
    onChange: (tree) => { ws.list[ws.active].tree = tree; store.set(ws); },
    onPaint: syncAux,
  });
  buildAuxToggles(editors);
  const resetLayout = () => {
    if (confirm("¿Restablecer todos los workspaces?")) { ws = defaults(); store.set(ws); renderTabs(); mgr.setTree(ws.list[0].tree); }
  };
  $("#reset").addEventListener("click", resetLayout);
  initMenus({ toggleTheme: () => $("#theme").click(), resetLayout });
  renderTabs();
  mgr.setTree(ws.list[ws.active].tree);
  splash("Listo · haz clic para entrar", 100);
  hideSplash();

  let pending = false;
  connectEvents(
    (ev) => { if (ev.event === "audio.levels") return; if (!pending) { pending = true; setTimeout(() => { pending = false; mgr.refreshAll(); }, 700); } },
    (on) => $("#lamp").classList.toggle("on", on),
  );
}
boot().catch((e) => {
  console.error(e);
  $("#screen").textContent = "No se pudo conectar con leonradio-core: " + e.message;
  splash("No se pudo conectar con el motor · haz clic para cerrar", 100);
  hideSplash();
});
