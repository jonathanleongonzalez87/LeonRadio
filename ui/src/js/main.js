import { connectEvents, getEditors, getInfo } from "./api.js";
import { AreaManager, area, split } from "./areas.js";

const KEY = "leonradio.workspaces.v4";
const $ = (s) => document.querySelector(s);
const store = {
  get() { try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; } },
  set(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
};

const defaults = () => ({
  active: 0,
  list: [
    { name: "Aire", tree: split("v",
        split("h", area("aire"), split("h", area("vu"), split("h", area("reloj"), area("dial"), 0.42), 0.42), 0.30),
        split("h", area("cola"), split("h", area("cartuchera"), area("historial"), 0.55), 0.34), 0.5) },
    { name: "Programación", tree: split("h", area("cola"), area("historial"), 0.45) },
    { name: "Producción", tree: split("h",
        split("v", area("aire"), area("cola"), 0.4),
        split("v", area("ejemplo.hora"), area("cartuchera"), 0.4), 0.55) },
  ],
});

let ws = store.get();
if (!ws?.list?.length) ws = defaults();
let mgr;

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

async function boot() {
  initTheme();
  tickClock(); setInterval(tickClock, 1000);
  const [info, editors] = await Promise.all([getInfo(), getEditors()]);
  $("#station").textContent = info.station;
  mgr = new AreaManager($("#screen"), {
    editors,
    onChange: (tree) => { ws.list[ws.active].tree = tree; store.set(ws); },
  });
  $("#reset").addEventListener("click", () => {
    if (confirm("¿Restablecer todos los workspaces?")) { ws = defaults(); store.set(ws); renderTabs(); mgr.setTree(ws.list[0].tree); }
  });
  renderTabs();
  mgr.setTree(ws.list[ws.active].tree);

  let pending = false;
  connectEvents(
    (ev) => { if (ev.event === "audio.levels") return; if (!pending) { pending = true; setTimeout(() => { pending = false; mgr.refreshAll(); }, 700); } },
    (on) => $("#lamp").classList.toggle("on", on),
  );
}
boot().catch((e) => { console.error(e); $("#screen").textContent = "No se pudo conectar con leonradio-core: " + e.message; });
