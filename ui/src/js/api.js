// Cliente de la API de leonradio-core (REST + WebSocket de eventos).
export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

export const getInfo = () => getJSON("/api/info");
export const getEditors = () => getJSON("/api/editors");
export const drawEditor = (id) => getJSON(`/api/editors/${encodeURIComponent(id)}/draw`);

export async function runCommand(name, args = {}) {
  const r = await fetch(`/api/commands/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ args }),
  });
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  return r.json();
}

// Bus de eventos del servidor: los componentes se suscriben con bus.addEventListener("audio.levels", …)
export const bus = new EventTarget();

// Eventos en vivo con reconexión automática.
export function connectEvents(onEvent, onStatus) {
  let ws, wait = 500;
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => { wait = 500; onStatus(true); };
    ws.onmessage = (m) => {
      try {
        const msg = JSON.parse(m.data);
        bus.dispatchEvent(new CustomEvent(msg.event, { detail: msg.data }));
        onEvent(msg);
      } catch { /* ignorar */ }
    };
    ws.onclose = () => { onStatus(false); setTimeout(open, wait); wait = Math.min(wait * 2, 8000); };
  };
  open();
}
