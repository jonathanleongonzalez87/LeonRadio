// Barra de menú (Archivo / Ver / Herramientas / Ayuda) y diálogo de Preferencias.
// Todo el texto se escribe con textContent; las listas de dispositivos vienen del servidor y no son de confianza.
import { getJSON, runCommand } from "./api.js";

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

// ---------------------------------------------------------------- diálogo
function openDialog(title, tabs, startTab = 0) {
  document.querySelectorAll(".modal").forEach((m) => m.remove());
  const modal = el("div", "modal");
  const dlg = el("div", "dlg");
  dlg.setAttribute("role", "dialog");
  dlg.setAttribute("aria-label", title);
  const head = el("div", "dlg-head");
  const close = el("button", "hbtn", "✕");
  close.type = "button"; close.title = "Cerrar"; close.setAttribute("aria-label", "Cerrar");
  head.append(el("span", "dlg-title", title), el("span", "sp"), close);
  const bar = el("div", "dlg-tabs");
  const body = el("div", "dlg-body");
  const btns = tabs.map((t, i) => {
    const b = el("button", "dlg-tab", t.label);
    b.type = "button";
    b.addEventListener("click", () => show(i));
    bar.append(b);
    return b;
  });
  const show = (i) => {
    btns.forEach((b, k) => b.setAttribute("aria-selected", String(k === i)));
    body.replaceChildren();
    tabs[i].build(body);
  };
  const end = () => { modal.remove(); document.removeEventListener("keydown", esc, true); };
  const esc = (e) => { if (e.key === "Escape") end(); };
  close.addEventListener("click", end);
  modal.addEventListener("pointerdown", (e) => { if (e.target === modal) end(); });
  document.addEventListener("keydown", esc, true);
  const foot = el("div", "dlg-foot");
  const ok = el("button", "u-btn", "Cerrar");
  ok.type = "button"; ok.addEventListener("click", end);
  foot.append(ok);
  dlg.append(head, bar, body, foot);
  modal.append(dlg);
  document.body.append(modal);
  show(startTab);
}

// ---------------------------------------------------------------- pestaña: dispositivos de audio
const OUTPUTS = [
  ["main", "Salida principal (Emisión)", "Predeterminado de Windows"],
  ["cue", "Escucha previa", "Igual que la principal", "próximamente"],
  ["aux1", "Reproductor Auxiliar 1", "Igual que la principal"],
  ["aux2", "Reproductor Auxiliar 2", "Igual que la principal"],
  ["aux3", "Reproductor Auxiliar 3", "Igual que la principal"],
  ["aux4", "Reproductor Auxiliar 4", "Igual que la principal"],
  ["cart", "Botonera", "Igual que la principal"],
];
const INPUTS = [["line1", "Entrada de línea 1"], ["line2", "Entrada de línea 2"]];

function deviceSelect(devices, current, emptyLabel, disabled) {
  const sel = el("select", "dlg-sel");
  sel.disabled = disabled;
  sel.append(new Option(emptyLabel, ""));
  const byApi = new Map();
  devices.forEach((d) => {
    if (!byApi.has(d.hostapi)) byApi.set(d.hostapi, []);
    byApi.get(d.hostapi).push(d);
  });
  [...byApi.keys()].sort((a, b) => (/WASAPI/.test(b) ? 1 : 0) - (/WASAPI/.test(a) ? 1 : 0)).forEach((api) => {
    const g = document.createElement("optgroup");
    g.label = api;                                     // la «interfaz» de Windows: WASAPI, MME, DirectSound, ASIO…
    byApi.get(api).forEach((d) => g.append(new Option(d.name, d.id)));
    sel.append(g);
  });
  const known = [...sel.options].some((o) => o.value === current);
  if (current && !known) sel.append(new Option(`${current.split("|")[0]} (no disponible)`, current));
  sel.value = current || "";
  return sel;
}

function buildAudio(body) {
  body.append(el("p", "dlg-note", "Cargando dispositivos…"));
  getJSON("/api/audio").then((a) => {
    body.replaceChildren();
    const status = el("div", "dlg-status");
    const setStatus = (t, bad) => { status.textContent = t; status.classList.toggle("bad", !!bad); };
    if (a.simulated) {
      body.append(el("p", "dlg-note warn", "LeonRadio está en modo simulado (sin tarjeta de sonido). Inícialo con audio real para elegir dispositivos."));
    } else {
      body.append(el("p", "dlg-note", `Sonando por: ${a.active}`));
      (a.warnings || []).forEach((w) => body.append(el("p", "dlg-note warn", w)));
    }
    const grid = el("div", "dlg-grid");
    const row = (label, note, sel, testable) => {
      const l = el("label", "dlg-lbl", label);
      if (note) l.append(el("small", "", ` (${note})`));
      const wrap = el("div", "dlg-ctl");
      wrap.append(sel);
      if (testable) {
        const t = el("button", "u-btn sm", "🔈");
        t.type = "button"; t.title = "Probar: tono suave de 1 segundo por este dispositivo";
        t.addEventListener("click", async () => {
          try { await runCommand("audio.test", { device: sel.value || null }); setStatus("Sonó un tono de prueba."); }
          catch (e) { setStatus(`No se pudo probar: ${e.message}`, true); }
        });
        wrap.append(t);
      }
      grid.append(l, wrap);
    };
    OUTPUTS.forEach(([key, label, empty, note]) => {
      const sel = deviceSelect(a.devices, (a.routes || {})[key] || "", empty, a.simulated);
      sel.addEventListener("change", async () => {
        sel.disabled = true;
        try { await runCommand("audio.set_route", { dest: key, device: sel.value || null }); setStatus("Guardado y aplicado."); }
        catch (e) { setStatus(`No se pudo aplicar: ${e.message}`, true); sel.value = (a.routes || {})[key] || ""; }
        finally { sel.disabled = a.simulated; }
      });
      row(label, note, sel, !a.simulated);
    });
    grid.append(el("hr", "dlg-sep"));
    INPUTS.forEach(([key, label]) => {
      const sel = deviceSelect(a.inputs, (a.selected_inputs || {})[key] || "", "(ninguna)", false);
      sel.addEventListener("change", async () => {
        try { await runCommand("audio.set_input", { line: key, device: sel.value || null }); setStatus("Entrada guardada."); }
        catch (e) { setStatus(`No se pudo guardar: ${e.message}`, true); }
      });
      row(label, "se guarda; se usará con Live Assist", sel, false);
    });
    if (!a.devices.length) body.append(el("p", "dlg-note warn", "No se encontraron dispositivos de salida."));
    body.append(grid, status);
  }).catch((e) => {
    body.replaceChildren(el("p", "dlg-note warn", `No se pudo leer la lista de dispositivos: ${e.message}`));
  });
}

// ---------------------------------------------------------------- pestaña: vista
function buildView(body, api) {
  body.append(el("p", "dlg-note", "Apariencia y diseño de paneles."));
  const row = el("div", "dlg-ctl");
  const theme = el("button", "u-btn sm", "◐ Cambiar tema claro/oscuro");
  theme.type = "button"; theme.addEventListener("click", api.toggleTheme);
  const reset = el("button", "u-btn sm", "↺ Restablecer diseño de paneles");
  reset.type = "button"; reset.addEventListener("click", () => { document.querySelector(".modal")?.remove(); api.resetLayout(); });
  row.append(theme, reset);
  body.append(row);
}

// ---------------------------------------------------------------- barra de menú
export function initMenus(api) {
  const bar = document.getElementById("menubar");
  if (!bar) return;
  const prefs = (tab = 0) => openDialog("Preferencias", [
    { label: "Dispositivos de audio", build: buildAudio },
    { label: "Vista", build: (b) => buildView(b, api) },
  ], tab);

  const MENUS = [
    ["Archivo", [["Preferencias…", () => prefs(0), "Ctrl+,"], ...(api.logout ? [["Salir", api.logout]] : [])]],
    ["Ver", [["Cambiar tema claro/oscuro", api.toggleTheme], ["Restablecer diseño de paneles", api.resetLayout]]],
    ["Herramientas", [["Dispositivos de audio…", () => prefs(0)]]],
    ["Ayuda", [
      ["Documentación", () => window.open("https://github.com/jonathanleongonzalez87/LeonRadio", "_blank", "noopener")],
      ["Acerca de LeonRadio", () => openDialog("Acerca de LeonRadio", [{
        label: "LeonRadio",
        build: (b) => {
          b.append(el("p", "dlg-note", "Automatizador de radio con estética de cabina vintage."));
          b.append(el("p", "dlg-note", "Código GPL-3.0 · documentación y diseño CC BY-SA 4.0."));
        },
      }])],
    ]],
  ];

  let openMenu = null;
  const closeMenu = () => {
    if (!openMenu) return;
    openMenu.menu.remove();
    openMenu.btn.setAttribute("aria-expanded", "false");
    openMenu = null;
  };
  MENUS.forEach(([title, items]) => {
    const btn = el("button", "mb-btn", title);
    btn.type = "button";
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");
    const open = () => {
      closeMenu();
      const menu = el("div", "mb-menu");
      menu.setAttribute("role", "menu");
      items.forEach(([label, fn, key]) => {
        const it = el("button", "mb-it");
        it.type = "button"; it.setAttribute("role", "menuitem");
        it.append(el("span", "", label), el("kbd", "", key || ""));
        it.addEventListener("click", () => { closeMenu(); fn(); });
        menu.append(it);
      });
      const r = btn.getBoundingClientRect();
      menu.style.left = `${r.left}px`;
      menu.style.top = `${r.bottom}px`;
      document.body.append(menu);
      btn.setAttribute("aria-expanded", "true");
      openMenu = { menu, btn };
    };
    btn.addEventListener("click", () => (openMenu && openMenu.btn === btn ? closeMenu() : open()));
    btn.addEventListener("pointerenter", () => { if (openMenu && openMenu.btn !== btn) open(); });   // como en Windows
    bar.append(btn);
  });
  document.addEventListener("pointerdown", (e) => {
    if (openMenu && !openMenu.menu.contains(e.target) && !openMenu.btn.contains(e.target)) closeMenu();
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenu();
    if ((e.ctrlKey || e.metaKey) && e.key === ",") { e.preventDefault(); prefs(0); }
  });
}
