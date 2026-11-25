// Cliente de la API de leonradio-core.
// Dos transportes: el servidor (REST + WebSocket) o, en el HTML autónomo, el motor Python dentro del
// navegador (Pyodide). En ese caso el arranque define globalThis.LR_DEMO_BACKEND (una promesa).
export const bus = new EventTarget();   // los componentes se suscriben con bus.addEventListener("audio.levels", …)

const demo = () => globalThis.LR_DEMO_BACKEND || null;

export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

export async function getInfo() {
  const d = demo();
  return d ? (await d).info() : getJSON("/api/info");
}
export async function getEditors() {
  const d = demo();
  return d ? (await d).editors() : getJSON("/api/editors");
}
export async function drawEditor(id) {
  const d = demo();
  return d ? (await d).draw(id) : getJSON(`/api/editors/${encodeURIComponent(id)}/draw`);
}

export async function runCommand(name, args = {}) {
  const d = demo();
  if (d) return (await d).run(name, args);
  const r = await fetch(`/api/commands/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ args }),
  });
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  return r.json();
}

// Eventos en vivo (con reconexión automática si hay servidor).
export function connectEvents(onEvent, onStatus) {
  const dispatch = (msg) => {
    bus.dispatchEvent(new CustomEvent(msg.event, { detail: msg.data }));
    onEvent(msg);
  };
  const d = demo();
  if (d) {
    d.then((backend) => { backend.subscribe(dispatch); onStatus(true); }).catch(() => onStatus(false));
    return;
  }
  let ws, wait = 500;
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => { wait = 500; onStatus(true); };
    ws.onmessage = (m) => { try { dispatch(JSON.parse(m.data)); } catch { /* ignorar */ } };
    ws.onclose = () => { onStatus(false); setTimeout(open, wait); wait = Math.min(wait * 2, 8000); };
  };
  open();
}
