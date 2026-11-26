// Renderer de UI declarativa: convierte el árbol que describe un editor (Python) en DOM.
// Nunca usa innerHTML con datos: todo texto entra por textContent (los addons no son de confianza).
import { runCommand } from "./api.js";
import { COMPONENTS } from "./components/index.js";

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}

const NODES = {
  column: (n, ctx) => container("u-col", n, ctx),
  row: (n, ctx) => container("u-row", n, ctx),
  label: (n) => el("p", `u-label ${n.tone || "normal"}`, n.text),
  kv: (n) => {
    const d = el("div", "u-kv");
    d.append(el("span", "", n.key), el("span", "", n.value));
    return d;
  },
  button: (n, ctx) => {
    const b = el("button", `u-btn${n.size === "sm" ? " sm" : ""}${n.selected ? " on" : ""}`, n.label);
    b.type = "button";
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await runCommand(n.command, n.args); } catch (e) { console.error(e); }
      finally { b.disabled = false; ctx.refresh?.(); }
    });
    return b;
  },
  progress: (n) => {
    const w = el("div", "u-col");
    const bar = el("div", "u-prog");
    const fill = el("i");
    fill.style.width = `${Math.round(n.value * 1000) / 10}%`;
    bar.append(fill);
    w.append(bar);
    if (n.text) w.append(el("div", "u-prog-t", n.text));
    return w;
  },
  slider: (n, ctx) => {
    const w = el("div", "u-col");
    const r = document.createElement("input");
    r.type = "range"; r.className = "u-seek"; r.min = "0"; r.max = "1000"; r.step = "1";
    r.setAttribute("aria-label", "Posición de reproducción");
    const frac = Math.min(1, n.value / n.max);
    r.value = String(Math.round(frac * 1000));
    r.style.setProperty("--v", `${frac * 100}%`);
    const t = el("div", "u-prog-t");
    const mmss = (ms) => { const s = Math.floor(ms / 1000); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
    const label = (ms) => `${mmss(ms)} / ${mmss(n.max)}${n.suffix || ""}`;
    t.textContent = label(n.value);
    r.addEventListener("pointerdown", () => document.body.classList.add("lr-dragging"));   // sin redibujar al arrastrar
    r.addEventListener("input", () => {
      r.style.setProperty("--v", `${r.value / 10}%`);
      t.textContent = label((r.value / 1000) * n.max);
    });
    r.addEventListener("change", async () => {
      document.body.classList.remove("lr-dragging");
      try { await runCommand(n.command, { ...n.args, ms: Math.round((r.value / 1000) * n.max) }); } catch (e) { console.error(e); }
      ctx.refresh?.();
    });
    r.addEventListener("pointerup", () => document.body.classList.remove("lr-dragging"));
    w.append(r, t);
    return w;
  },
  custom: (n, ctx) => {
    const make = COMPONENTS[n.component];
    if (!make) return el("p", "u-label warn", `Componente desconocido: ${n.component}`);
    try { return make(n.props || {}, ctx); }
    catch (e) { console.error(e); return el("p", "u-label warn", `Error en componente ${n.component}`); }
  },
  tabs: (n, ctx) => {
    const wrap = el("div", "u-tabs");
    const bar = el("div", "u-tabbar");
    bar.setAttribute("role", "tablist");
    const panels = el("div", "u-tabpanels");
    const store = (ctx.store ??= {});
    store.tabs ??= {};                       // la pestaña activa se recuerda entre refrescos
    let active = Number.isInteger(store.tabs[n.id]) ? store.tabs[n.id] : 0;
    if (active >= n.tabs.length) active = 0;
    const btns = [], bodies = [];
    const show = (i) => {
      store.tabs[n.id] = i;
      btns.forEach((b, k) => b.setAttribute("aria-selected", String(k === i)));
      bodies.forEach((p, k) => { p.hidden = k !== i; });
    };
    n.tabs.forEach((t, i) => {
      const b = el("button", "u-tabbtn", t.label);
      b.type = "button"; b.setAttribute("role", "tab");
      b.addEventListener("click", () => show(i));
      bar.append(b); btns.push(b);
      const p = el("div", "u-col");
      (t.children || []).forEach((c) => p.append(render(c, ctx)));
      panels.append(p); bodies.push(p);
    });
    wrap.append(bar, panels);
    show(active);
    return wrap;
  },
  separator: () => el("hr", "u-sep"),
  table: (n, ctx) => {
    const t = el("table", "u-tab");
    const nh = new Set(n.nh || []);
    const head = el("tr");
    n.columns.forEach((c, i) => head.append(el("th", nh.has(i) ? "nh" : "", c)));
    const thead = el("thead");
    thead.append(head);
    t.append(thead);
    const body = el("tbody");
    const fl = n.list && Array.isArray(n.list.uids) ? n.list : null;   // lista de ficheros: elegir, arrastrar, Supr
    const run = async (cmd, args) => {
      try { await runCommand(cmd, args); } catch (e) { console.error(e); }
      ctx.refresh?.();
    };
    n.rows.forEach((r, idx) => {
      const tr = el("tr");
      r.forEach((c, i) => tr.append(el("td", nh.has(i) ? "nh" : "", c)));
      const uid = fl ? fl.uids[idx] : null;
      if (uid) {
        if (uid === fl.selected) tr.classList.add("sel");
        tr.draggable = true;
        tr.addEventListener("click", () => run("list.select", { target: fl.target, uid }));
        tr.addEventListener("dragstart", (e) => {
          document.body.classList.add("lr-dragging");        // mientras se arrastra no se redibuja el panel
          e.dataTransfer.effectAllowed = "move";
          e.dataTransfer.setData("text/plain", uid);
          tr.classList.add("drag");
        });
        tr.addEventListener("dragend", () => {
          document.body.classList.remove("lr-dragging");
          tr.classList.remove("drag");
          body.querySelectorAll(".drop-above,.drop-below").forEach((x) => x.classList.remove("drop-above", "drop-below"));
          ctx.refresh?.();
        });
        tr.addEventListener("dragover", (e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
          const below = e.clientY > tr.getBoundingClientRect().top + tr.offsetHeight / 2;
          body.querySelectorAll(".drop-above,.drop-below").forEach((x) => x.classList.remove("drop-above", "drop-below"));
          tr.classList.add(below ? "drop-below" : "drop-above");
        });
        tr.addEventListener("drop", (e) => {
          e.preventDefault();
          const from = fl.uids.indexOf(e.dataTransfer.getData("text/plain"));
          if (from < 0) return;
          const below = e.clientY > tr.getBoundingClientRect().top + tr.offsetHeight / 2;
          let to = idx + (below ? 1 : 0);
          if (from < to) to -= 1;                            // al quitar el origen, los de abajo suben un puesto
          if (to !== from) run("list.move_to", { target: fl.target, uid: fl.uids[from], index: to });
        });
      }
      body.append(tr);
    });
    t.append(body);
    if (!n.rows.length) return el("div", "empty", "Sin datos todavía");
    const wrap = el("div", "u-tabwrap");
    wrap.append(t);
    if (fl) {
      wrap.tabIndex = 0;
      wrap.addEventListener("keydown", (e) => {
        if (e.key === "Delete" && fl.selected) { e.preventDefault(); run("list.remove", { target: fl.target, uid: fl.selected }); }
      });
    }
    return wrap;
  },
};

function container(cls, node, ctx) {
  const d = el("div", cls + (node.cls && /^[a-z-]+$/.test(node.cls) ? ` ${node.cls}` : ""));
  (node.children || []).forEach((c) => d.append(render(c, ctx)));
  return d;
}

export function render(node, ctx = {}) {
  const fn = NODES[node.t];
  return fn ? fn(node, ctx) : el("p", "u-label warn", `Nodo desconocido: ${node.t}`);
}
