// Gestor de áreas (estilo Blender): árbol de divisiones; cada hoja aloja un editor.
//   nodo = { type:"area", id, editor }  |  { type:"split", dir:"h"|"v", ratio, a, b }
// Las funciones de árbol son puras (sin DOM) para poder probarlas y serializarlas a JSON.
import { drawEditor } from "./api.js";
import { render } from "./renderer.js";

let seq = 0;
export const newId = () => `a${Date.now().toString(36)}${(seq++).toString(36)}`;
// Categorías del menú de editores (los que no estén aquí, p. ej. los de addons, van en «Addons»).
const EDITOR_CATEGORIES = [
  { title: "Al aire", ids: ["aire", "proxima", "controles", "reloj"] },
  { title: "Listas", ids: ["emision", "aux1", "aux2", "aux3", "aux4", "historial"] },
  { title: "Material", ids: ["varios", "botonera", "eventos", "explorador", "navegador", "streaming", "monitores", "metadatos"] },
  { title: "Monitoreo", ids: ["vu", "dial"] },
];

export const area = (editor, slim = false) => ({ type: "area", id: newId(), editor, ...(slim ? { slim: true } : {}) });
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

/** Encabezado compacto: el área ocupa todo el espacio y el encabezado aparece al pasar el cursor. */
export function setSlim(tree, id, slim) {
  return mapTree(tree, (n) => {
    if (n.id !== id) return n;
    const { slim: _old, ...rest } = n;
    return slim ? { ...rest, slim: true } : rest;
  });
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
    this.stores = new Map(); // id de área -> estado de su UI (p. ej. pestaña activa)
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
    this.host.onPaint?.();
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

  /** Menú de editores en columnas por categoría (como el de Blender). */
  openMenu(anchor, node) {
    document.querySelectorAll(".emenu").forEach((m) => m.remove());
    const menu = document.createElement("div");
    menu.className = "emenu";
    menu.setAttribute("role", "menu");
    const groups = new Map(EDITOR_CATEGORIES.map((c) => [c.title, []]));
    const other = "Addons";
    groups.set(other, []);
    this.host.editors.forEach((e) => {
      const c = EDITOR_CATEGORIES.find((k) => k.ids.includes(e.id));
      groups.get(c ? c.title : other).push(e);
    });
    groups.forEach((list, title) => {
      if (!list.length) return;
      const col = document.createElement("div");
      col.className = "emenu-col";
      const h = document.createElement("div");
      h.className = "emenu-h";
      h.textContent = title;
      col.append(h);
      list.forEach((e) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "emenu-it" + (e.id === node.editor ? " on" : "");
        b.setAttribute("role", "menuitem");
        b.textContent = `${e.icon} ${e.label}`;
        b.addEventListener("click", () => { close(); this.commit(setEditor(this.tree, node.id, e.id)); });
        col.append(b);
      });
      menu.append(col);
    });
    const close = () => {
      menu.remove();
      document.removeEventListener("pointerdown", away, true);
      document.removeEventListener("keydown", esc, true);
    };
    const away = (ev) => { if (!menu.contains(ev.target) && ev.target !== anchor) close(); };
    const esc = (ev) => { if (ev.key === "Escape") close(); };
    document.body.append(menu);
    const r = anchor.getBoundingClientRect();
    const w = menu.offsetWidth;
    menu.style.left = `${Math.max(4, Math.min(r.left, window.innerWidth - w - 4))}px`;
    menu.style.top = `${Math.min(r.bottom + 2, window.innerHeight - menu.offsetHeight - 4)}px`;
    document.addEventListener("pointerdown", away, true);
    document.addEventListener("keydown", esc, true);
    menu.querySelector(".emenu-it.on, .emenu-it")?.focus();
  }

  buildArea(node) {
    const sec = document.createElement("section");
    sec.className = node.slim ? "area slim" : "area";
    const head = document.createElement("header");

    const cur = this.host.editors.find((e) => e.id === node.editor);
    const sel = document.createElement("button");
    sel.type = "button";
    sel.className = "emenu-btn";
    sel.setAttribute("aria-label", "Tipo de editor");
    sel.setAttribute("aria-haspopup", "true");
    sel.textContent = (cur ? `${cur.icon} ${cur.label}` : `${node.editor} (no disponible)`) + "  ▾";
    sel.addEventListener("click", () => this.openMenu(sel, node));

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
      mk("⇕", node.slim ? "Mostrar siempre el encabezado" : "Encabezado compacto (aparece al pasar el cursor)",
         () => this.commit(setSlim(this.tree, node.id, !node.slim))),
      mk("◫", "Dividir lado a lado", () => this.commit(splitArea(this.tree, node.id, "h"))),
      mk("⬓", "Dividir arriba/abajo", () => this.commit(splitArea(this.tree, node.id, "v"))),
      mk("✕", "Cerrar área", () => this.commit(closeArea(this.tree, node.id)), countAreas(this.tree) <= 1),
    );

    const body = document.createElement("div");
    body.className = "body";
    sec.append(head, body);
    this.views.set(node.id, { id: node.id, body, editor: node.editor, last: "" });
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
      if (document.body.classList.contains("lr-dragging")) return; // arrastrando: se redibuja al soltar
      const ae = document.activeElement;                             // escribiendo en un campo: no se redibuja debajo
      if (ae && view.body.contains(ae) && /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName)) return;
      view.last = sig;
      if (!this.stores.has(view.id)) this.stores.set(view.id, {});
      const top = view.body.scrollTop;                       // conservar el desplazamiento al redibujar
      view.body.replaceChildren(render(tree, { refresh: () => this.refreshAll(), store: this.stores.get(view.id) }));
      view.body.scrollTop = top;
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

// ---- listas auxiliares: mostrar/ocultar un editor junto a otro (barra de herramientas) ----
export function findArea(node, pred) {
  if (node.type === "area") return pred(node) ? node : null;
  return findArea(node.a, pred) || findArea(node.b, pred);
}

export const hasEditor = (tree, editor) => !!findArea(tree, (n) => n.editor === editor);

/**
 * Alterna el editor `editor`: si está en pantalla lo cierra; si no, lo coloca junto a `anchor`
 * (a su derecha). Con otro editor del mismo grupo ya visible (`group`), se apila debajo de él.
 */
export function toggleBeside(tree, editor, anchor, group = "aux") {
  const existing = findArea(tree, (n) => n.editor === editor);
  if (existing) return countAreas(tree) > 1 ? closeArea(tree, existing.id) : tree;
  // las listas auxiliares se abren en fila horizontal, por orden de número
  const num = (e) => Number(e.slice(group.length)) || 0;
  const sibs = [];
  const collect = (n) => { if (n.type === "area") { if (n.editor.startsWith(group)) sibs.push(n); } else { collect(n.a); collect(n.b); } };
  collect(tree);
  if (sibs.length) {
    const before = sibs.filter((s) => num(s.editor) < num(editor)).sort((x, y) => num(y.editor) - num(x.editor))[0];
    if (before) return mapTree(tree, (n) => (n.id === before.id ? split("h", n, area(editor), 0.5) : n));
    const after = sibs.sort((x, y) => num(x.editor) - num(y.editor))[0];
    return mapTree(tree, (n) => (n.id === after.id ? split("h", area(editor), n, 0.5) : n));
  }
  const target = findArea(tree, (n) => n.editor === anchor) || findArea(tree, () => true);
  return mapTree(tree, (n) => (n.id === target.id ? split("h", n, area(editor), 0.7) : n));
}
