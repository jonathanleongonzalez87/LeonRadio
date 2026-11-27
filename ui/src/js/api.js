// Cliente de la API de leonradio-core.
// Dos transportes: el servidor (REST + WebSocket) o, en el HTML autónomo, el motor Python dentro del
// navegador (Pyodide). En ese caso el arranque define globalThis.LR_DEMO_BACKEND (una promesa).
export const bus = new EventTarget();   // los componentes se suscriben con bus.addEventListener("audio.levels", …)

const demo = () => globalThis.LR_DEMO_BACKEND || null;
const SAME = { credentials: "same-origin" };

// Una respuesta 401 en uso (sesión caducada o clave cambiada): se avisa a la pantalla de acceso.
function authLost() {
  bus.dispatchEvent(new Event("auth.required"));
  return new Error("Tu sesión terminó. Entra de nuevo.");
}

export async function getJSON(url) {
  const r = await fetch(url, SAME);
  if (r.status === 401) throw authLost();
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
    ...SAME,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ args }),
  });
  if (r.status === 401) throw authLost();
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).detail || ""; } catch { /* sin cuerpo */ }
    throw new Error(typeof detail === "string" && detail ? detail : `${name}: ${r.status}`);
  }
  return r.json();
}

// ---- sesión (modo red): ver docs/arquitectura.md → Seguridad ----
export async function getSession() {
  if (demo()) return { auth_required: false, authenticated: true, station: "" };
  const r = await fetch("/api/session", SAME);       // lanza TypeError si no hay red
  if (!r.ok) throw Object.assign(new Error("session"), { status: r.status });
  return r.json();
}
// Devuelve { status, body } sin lanzar por 401/429 (son respuestas esperadas); solo lanza si no hay red.
export async function login(key) {
  const r = await fetch("/api/login", {
    ...SAME, method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }),
  });
  let body = {};
  try { body = await r.json(); } catch { /* sin cuerpo */ }
  return { status: r.status, body };
}
export async function logout() {
  if (demo()) return;
  await fetch("/api/logout", { ...SAME, method: "POST" });
}
export async function needsLogin() {
  try { const s = await getSession(); return s.auth_required && !s.authenticated; } catch { return false; }
}

// ---- eventos en vivo (con reconexión automática si hay servidor) ----
const rt = { paused: false, ws: null, reopen: null };
export function pauseRealtime() {          // sin sesión: ni reintentos ni conexión abierta
  rt.paused = true;
  try { rt.ws?.close(); } catch { /* ya cerrado */ }
}
export function resumeRealtime() {
  if (rt.paused) { rt.paused = false; rt.reopen?.(); }
}

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
  let wait = 500;
  const open = () => {
    if (rt.paused) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    rt.ws = ws;
    ws.onopen = () => { wait = 500; onStatus(true); };
    ws.onmessage = (m) => { try { dispatch(JSON.parse(m.data)); } catch { /* ignorar */ } };
    ws.onclose = async () => {
      onStatus(false);
      if (rt.paused) return;
      // un handshake rechazado no da código al navegador: se pregunta a la sesión antes de reintentar
      if (await needsLogin()) { rt.paused = true; bus.dispatchEvent(new Event("auth.required")); return; }
      setTimeout(open, wait); wait = Math.min(wait * 2, 8000);
    };
  };
  rt.reopen = () => { wait = 500; open(); };      // se llama con rt.paused ya en false
  open();
}
