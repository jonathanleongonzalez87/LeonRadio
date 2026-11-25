// Gestor de áreas (estilo Blender): árbol de divisiones; cada hoja aloja un editor.
//   nodo = { type:"area", id, editor }  |  { type:"split", dir:"h"|"v", ratio, a, b }
// Las funciones de árbol son puras (sin DOM) para poder probarlas y serializarlas a JSON.
import { drawEditor } from "./api.js";
import { render } from "./renderer.js";

let seq = 0;
export const newId = () => `a${Date.now().toString(36)}${(seq++).toString(36)}`;
export const area = (editor) => ({ type: "area", id: newId(), editor });
export const split = (dir, a, b, ratio = 0.5) => ({ type: "split", dir, ratio, a, b });

// ---- operaciones puras sobre el árbol ------------------------------------
export function mapTree(node, fn) {
  if (node.type === "area") return fn(node);
  return { ...node, a: mapTree(node.a, fn), b: mapTree(node.b, fn) };
}

export function countAreas(node) {
  return node.type === "area" ? 1 : countAreas(node.a) + countAreas(node.b);
}

/** Divide el área `id` en dos (dir "h" = lado a lado, "v" = apilado). La nueva copia el editor. */
export function splitArea(tree, id, dir) {
  return mapTree(tree, (n) => (n.id === id ? split(dir, n, area(n.editor)) : n));
}

/** Cierra el área `id`: su hermana ocupa todo el espacio. No cierra la última. */
export function closeArea(tree, id) {
  if (tree.type === "area") return tree;
  if (tree.a.type === "area" && tree.a.id === id) return tree.b;
  if (tree.b.type === "area" && tree.b.id === id) return tree.a;
  return { ...tree, a: closeArea(tree.a, id), b: closeArea(tree.b, id) };
}

export function setEditor(tree, id, editor) {
  return mapTree(tree, (n) => (n.id === id ? { ...n, editor } : n));
}

export function setRatio(tree, splitNode, ratio) {
  if (tree === splitNode) return { ...tree, ratio };
  if (tree.type === "area") return tree;
  return { ...tree, a: setRatio(tree.a, splitNode, ratio), b: setRatio(tree.b, splitNode, ratio) };
}

// ---- DOM -------------------------------------------------------------------
/**
 * Dibuja `layout.tree` dentro de `root`.
 * host = { editors:[{id,label,icon}], onChange(tree), refreshAll() }
 */
export class AreaManager {
  constructor(root, host) {
    this.root = root;
    this.host = host;
    this.tree = null;
    this.views = new Map(); // id de área -> { body, last }
  }

  setTree(tree) {
    this.tree = tree;
    this.paint();
  }

  commit(tree) {
    this.tree = tree;
    this.host.onChange(tree);
    this.paint();
  }

  paint() {
    this.root.replaceChildren();
    this.views.clear();
    this.root.append(this.build(this.tree));
    this.refreshAll();
  }

  build(node) {
    if (node.type === "area") return this.buildArea(node);
    const wrap = document.createElement("div");
    wrap.className = `split ${node.dir}`;
    const a = this.wrapNode(this.build(node.a), node.ratio);
    const b = this.wrapNode(this.build(node.b), 1 - node.ratio);
    const gutter = document.createElement("div");
    gutter.className = "gutter";
    gutter.setAttribute("role", "separator");
    gutter.addEventListener("pointerdown", (ev) => this.drag(ev, node, wrap, gutter, a, b));
    wrap.append(a, gutter, b);
    return wrap;
  }

  wrapNode(child, ratio) {
    const w = document.createElement("div");
    w.className = "node";
    w.style.flex = `${ratio} 1 0`;
    w.append(child);
    return w;
  }

  drag(ev, node, wrap, gutter, a, b) {
    ev.preventDefault();
    gutter.setPointerCapture(ev.pointerId);
    gutter.classList.add("drag");
    const horizontal = node.dir === "h";
    const move = (e) => {
      const r = wrap.getBoundingClientRect();
      const raw = horizontal ? (e.clientX - r.left) / r.width : (e.clientY - r.top) / r.height;
      node.ratio = Math.min(0.9, Math.max(0.1, raw));
      a.style.flex = `${node.ratio} 1 0`;
      b.style.flex = `${1 - node.ratio} 1 0`;
    };
    const up = () => {
      gutter.classList.remove("drag");
      gutter.removeEventListener("pointermove", move);
      gutter.removeEventListener("pointerup", up);
      this.host.onChange(this.tree);
    };
    gutter.addEventListener("pointermove", move);
    gutter.addEventListener("pointerup", up);
  }

  buildArea(node) {
    const sec = document.createElement("section");
    sec.className = "area";
    const head = document.createElement("header");

    const sel = document.createElement("select");
    sel.setAttribute("aria-label", "Tipo de editor");
    const known = this.host.editors.some((e) => e.id === node.editor);
    if (!known) {
      const o = new Option(`${node.editor} (no disponible)`, node.editor);
      o.disabled = true;
      sel.append(o);
    }
    this.host.editors.forEach((e) => sel.append(new Option(`${e.icon} ${e.label}`, e.id)));
    sel.value = node.editor;
    sel.addEventListener("change", () => this.commit(setEditor(this.tree, node.id, sel.value)));

    const mk = (txt, title, fn, disabled = false) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "hbtn"; b.textContent = txt; b.title = title;
      b.setAttribute("aria-label", title); b.disabled = disabled;
      b.addEventListener("click", fn);
      return b;
    };
    const sp = document.createElement("span");
    sp.className = "sp";
    head.append(
      sel, sp,
      mk("◫", "Dividir lado a lado", () => this.commit(splitArea(this.tree, node.id, "h"))),
      mk("⬓", "Dividir arriba/abajo", () => this.commit(splitArea(this.tree, node.id, "v"))),
      mk("✕", "Cerrar área", () => this.commit(closeArea(this.tree, node.id)), countAreas(this.tree) <= 1),
    );

    const body = document.createElement("div");
    body.className = "body";
    sec.append(head, body);
    this.views.set(node.id, { body, editor: node.editor, last: "" });
    return sec;
  }

  async refreshAll() {
    await Promise.all([...this.views.values()].map((v) => this.refresh(v)));
  }

  async refresh(view) {
    try {
      const tree = await drawEditor(view.editor);
      const sig = JSON.stringify(tree);
      if (sig === view.last) return; // sin cambios: no tocar el DOM (evita parpadeo)
      view.last = sig;
      view.body.replaceChildren(render(tree, { refresh: () => this.refreshAll() }));
    } catch (e) {
      console.error(`editor ${view.editor}:`, e);
      view.last = "";
      const p = document.createElement("div");
      p.className = "empty";
      p.textContent = `Editor «${view.editor}» no disponible`;
      view.body.replaceChildren(p);
    }
  }
}
