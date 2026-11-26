// Cartuchera: pads 1–9 y 0 (teclado numérico) que disparan piezas (pisadores, separadores, jingles…).
import { runCommand } from "../api.js";

let active = null; // la cartuchera visible más reciente recibe las teclas F1–F12

window.addEventListener("keydown", (e) => {
  if (!active || !active.root.isConnected) return;
  if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName || "")) return;
  const m = /^Numpad(\d)$/.exec(e.code);                  // solo el teclado numérico, no la fila de números
  if (!m) return;
  const pad = active.byKey.get(m[1]);
  if (pad) { e.preventDefault(); pad.fire(); }
});

export function cartwall(props, ctx) {
  const root = document.createElement("div");
  root.className = "cart";
  const byKey = new Map();
  const pads = Array.isArray(props.pads) ? props.pads : [];

  if (!pads.length) {
    const p = document.createElement("div");
    p.className = "empty";
    p.textContent = "Sin piezas en la biblioteca (jingles, pisadores, separadores)";
    root.append(p);
    return root;
  }

  const lit = new Set(Array.isArray(props.active) ? props.active : []);
  pads.forEach((d) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `pad pad-${/^[a-z]+$/.test(d.style) ? d.style : "graphite"}${lit.has(d.asset_id) ? " on" : ""}`;
    b.title = lit.has(d.asset_id) ? "Sonando · pulsa para detener" : "";
    const k = document.createElement("span"); k.className = "pad-key"; k.textContent = d.key;
    const t = document.createElement("span"); t.className = "pad-title"; t.textContent = d.title;
    const s = document.createElement("span"); s.className = "pad-sub"; s.textContent = d.sub || "";
    const lamp = document.createElement("span"); lamp.className = "pad-lamp";
    b.append(k, t, s, lamp);
    const fire = async () => {
      if (!b.classList.contains("on")) { b.classList.add("fire"); setTimeout(() => b.classList.remove("fire"), 350); }
      try { await runCommand(props.command, { asset_id: d.asset_id }); } catch (err) { console.error(err); }
      ctx.refresh?.();
    };
    b.addEventListener("click", fire);
    byKey.set(d.key, { fire });
    root.append(b);
  });
  active = { root, byKey };
  return root;
}
