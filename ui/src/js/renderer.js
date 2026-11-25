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
    const b = el("button", "u-btn", n.label);
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
  custom: (n, ctx) => {
    const make = COMPONENTS[n.component];
    if (!make) return el("p", "u-label warn", `Componente desconocido: ${n.component}`);
    try { return make(n.props || {}, ctx); }
    catch (e) { console.error(e); return el("p", "u-label warn", `Error en componente ${n.component}`); }
  },
  separator: () => el("hr", "u-sep"),
  table: (n) => {
    const t = el("table", "u-tab");
    const nh = new Set(n.nh || []);
    const head = el("tr");
    n.columns.forEach((c, i) => head.append(el("th", nh.has(i) ? "nh" : "", c)));
    const thead = el("thead");
    thead.append(head);
    t.append(thead);
    const body = el("tbody");
    n.rows.forEach((r) => {
      const tr = el("tr");
      r.forEach((c, i) => tr.append(el("td", nh.has(i) ? "nh" : "", c)));
      body.append(tr);
    });
    t.append(body);
    if (!n.rows.length) return el("div", "empty", "Sin datos todavía");
    const wrap = el("div", "u-tabwrap");
    wrap.append(t);
    return wrap;
  },
};

function container(cls, node, ctx) {
  const d = el("div", cls);
  (node.children || []).forEach((c) => d.append(render(c, ctx)));
  return d;
}

export function render(node, ctx = {}) {
  const fn = NODES[node.t];
  return fn ? fn(node, ctx) : el("p", "u-label warn", `Nodo desconocido: ${node.t}`);
}
