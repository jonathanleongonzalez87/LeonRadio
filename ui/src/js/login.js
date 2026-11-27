// Pantalla de acceso (modo red): capa a pantalla completa sobre la app. Ver docs/planes/S6.md → «Propuesta de pantalla de acceso».
// Todo el texto se escribe con textContent. La clave solo vive en el campo: nunca en la URL, el almacenamiento ni la consola.
import { getSession, login } from "./api.js";

const KEEP = new Set(["acceso", "acc-live"]);       // el resto de lo que cuelga de <body> queda inerte mientras la capa está visible
let marked = [];
const SLOW_MS = 8000, REVEAL_MS = 30000;
const T = {
  empty: "Escribe la clave.",
  wrong: "Clave incorrecta. Revísala e inténtalo de nuevo.",
  net: "No se pudo contactar con LeonRadio. Revisa que el PC de la emisora esté encendido y que estés en la misma red.",
  server: "LeonRadio tuvo un problema. Inténtalo otra vez en un momento.",
  checking: "Comprobando la clave",
  slow: "Sigue comprobando… Si no avanza, revisa la conexión.",
  expired: "Tu sesión terminó. Entra de nuevo.",
  expired2: "La última acción no se aplicó. Si cambiaron la clave, usa la nueva.",
  ready: "Ya puedes volver a intentarlo.",
  done: "Sesión iniciada.",
};

const $ = (id) => document.getElementById(id);
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
let L = null;                                      // referencias al DOM (se resuelven una vez)
let lastFocus = null, reason = "", retryFn = null;
let lockTimer = 0, slowTimer = 0, revealTimer = 0, lockUntil = 0;
const loggedIn = [];                               // funciones a llamar tras cada acceso correcto

export function onLoggedIn(fn) { loggedIn.push(fn); }

function refs() {
  if (L) return L;
  L = {
    form: $("acceso"), field: $("clave"), show: $("acc-show"), go: $("acc-go"), retry: $("acc-retry"),
    notice: $("acc-notice"), status: $("acc-status"), alert: $("acc-alert"), lock: $("acc-lock"), count: $("acc-count"),
    title: $("acc-title"), plain: $("acc-plain"), lost: $("acc-lost"), lostLink: $("acc-lostlink"), station: $("acc-station"), live: $("acc-live"),
  };
  L.title.tabIndex = -1;
  if (location.protocol !== "http:") L.plain.hidden = true;   // el aviso de «sin cifrar» solo si la conexión es HTTP
  L.form.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  L.retry.addEventListener("click", () => { clearAlert(); L.go.hidden = false; L.retry.hidden = true; retryFn?.(); });
  L.show.addEventListener("click", () => setReveal(L.field.type === "password"));
  L.field.addEventListener("input", () => { if (L.notice.dataset.kind === "ready") setNotice(""); });
  L.lostLink.querySelector("a").addEventListener("click", (e) => {
    e.preventDefault(); L.lost.open = true; L.lost.querySelector("summary").focus();
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) setReveal(false); });
  return L;
}

const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

// Aviso con icono «!», texto normal y barra naranja: el color nunca es el único indicador.
function message(box, text, sub) {
  box.replaceChildren();
  if (!text) return;
  const body = el("span", "", text);
  if (sub) body.append(el("small", "", sub));
  const m = el("div", "acc-msg"); m.append(el("span", "acc-ico", "!"), body);
  box.append(m);
}
function setNotice(text, sub, kind = "") { refs(); message(L.notice, text, sub); L.notice.dataset.kind = kind; }
function clearAlert() { message(L.alert, ""); L.field.removeAttribute("aria-invalid"); L.field.setAttribute("aria-describedby", "acc-help"); }
function showAlert(text, withLost = false) {
  message(L.alert, text);
  L.field.setAttribute("aria-describedby", "acc-help acc-alert");
  L.lostLink.hidden = !withLost;
}
function announce(text) { L.status.textContent = ""; setTimeout(() => { L.status.textContent = text; }, 30); }

function behind(on) {
  if (on) {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));   // cierra menús y diálogos abiertos
    document.querySelectorAll(".modal, .mb-menu, .emenu").forEach((e) => e.remove());
    marked = [];
    for (const e of document.body.children) {
      if (KEEP.has(e.id) || ["svg", "script"].includes(e.tagName.toLowerCase())) continue;
      marked.push({ e, inert: e.hasAttribute("inert"), aria: e.getAttribute("aria-hidden") });
      e.setAttribute("inert", ""); e.setAttribute("aria-hidden", "true");
    }
  } else {                                                 // se restaura exactamente lo que se marcó
    for (const m of marked) {
      if (!m.inert) m.e.removeAttribute("inert");
      if (m.aria === null) m.e.removeAttribute("aria-hidden"); else m.e.setAttribute("aria-hidden", m.aria);
    }
    marked = [];
  }
}

function setReveal(on) {
  clearTimeout(revealTimer);
  const f = L.field;
  f.type = on ? "text" : "password";
  f.classList.toggle("shown", on);
  f.setAttribute("autocomplete", on ? "off" : "current-password");   // visible: que no se sugiera como texto
  L.show.textContent = on ? "Ocultar" : "Mostrar";
  L.show.setAttribute("aria-pressed", String(on));
  L.show.setAttribute("aria-label", on ? "Ocultar clave" : "Mostrar clave");
  if (on) revealTimer = setTimeout(() => setReveal(false), REVEAL_MS);
}

function controls(enabled) {
  const had = [L.field, L.show, L.go].includes(document.activeElement);
  for (const e of [L.field, L.show, L.go]) e.disabled = !enabled;
  if (!enabled && had) L.title.focus();                    // que el foco no caiga en <body>
}
function busy(on) {
  controls(!on);
  L.go.classList.toggle("busy", on);
  L.go.textContent = on ? "Entrando…" : "Entrar";
  L.form.setAttribute("aria-busy", String(on));
  clearTimeout(slowTimer);
  if (L.notice.dataset.kind === "slow") setNotice("");
  if (on) {
    announce(T.checking);
    slowTimer = setTimeout(() => setNotice(T.slow, "", "slow"), SLOW_MS);   // visible, no solo para lectores de pantalla
  }
}

function reset() {
  clearTimeout(lockTimer); clearTimeout(slowTimer);
  clearAlert();
  message(L.notice, ""); L.notice.dataset.kind = "";
  L.lock.hidden = true; L.lostLink.hidden = true;
  L.retry.hidden = true; L.go.hidden = false;
  busy(false);
  L.status.textContent = "";
  setReveal(false);
}

// Abre la capa. `expired`: aviso de sesión caducada (la app sigue debajo; no se recarga la página).
export function showLogin({ expired = false, station = "" } = {}) {
  refs();
  if (!L.form.hidden) { if (expired && !L.notice.firstChild) setNotice(T.expired, T.expired2); return; }
  lastFocus = document.activeElement && !L.form.contains(document.activeElement) ? document.activeElement : null;
  reason = expired ? "expired" : "";
  document.getElementById("splash")?.remove();
  if (station) L.station.textContent = station;
  L.form.classList.remove("out");
  L.form.hidden = false;
  behind(true);
  reset();
  L.field.value = "";
  if (expired) { setNotice(T.expired, T.expired2); announce(T.expired); }
  L.field.focus();
  L.field.scrollIntoView?.({ block: "center" });
}

function close() {
  const target = reason === "expired" && lastFocus?.isConnected ? lastFocus : document.getElementById("screen");
  const finish = () => {
    L.form.hidden = true; L.form.classList.remove("out");
    behind(false);
    if (target) { if (target.id === "screen") target.tabIndex = -1; target.focus?.({ preventScroll: true }); }
  };
  L.live.textContent = "";
  setTimeout(() => { L.live.textContent = T.done; }, 30);
  if (reduced()) finish(); else { L.form.classList.add("out"); setTimeout(finish, 200); }
}

function fail(kind, retry, offline = false) {
  clearTimeout(slowTimer);
  busy(false);
  message(L.alert, kind === "net" ? T.net : T.server);
  retryFn = retry;
  L.go.hidden = true; L.retry.hidden = false;
  if (offline) { L.field.disabled = true; L.show.disabled = true; }    // al cargar, Reintentar es la única vía
  L.retry.focus();
}

const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

function lock(seconds) {
  clearTimeout(lockTimer);
  clearAlert();
  L.field.value = ""; setReveal(false);
  controls(false);
  L.lock.hidden = false; L.lostLink.hidden = false;
  lockUntil = Date.now() + seconds * 1000;
  let lastMin = -1;
  const tick = () => {                                   // se recalcula con la hora del navegador, no se acumula
    const left = Math.max(0, Math.ceil((lockUntil - Date.now()) / 1000));
    L.count.textContent = mmss(left);
    const mins = Math.ceil(left / 60);
    if (left > 0 && mins !== lastMin) {
      announce(`${lastMin < 0 ? "Demasiados intentos. " : ""}Espera ${mins} ${mins === 1 ? "minuto" : "minutos"}.`);
      lastMin = mins;
    }
    if (left > 0) { lockTimer = setTimeout(tick, 1000); return; }
    L.lock.hidden = true; L.lostLink.hidden = true;
    controls(true);
    setNotice(T.ready, "", "ready");
    announce(T.ready);
    L.field.focus();
  };
  tick();
}

async function submit() {
  const key = L.field.value.trim();
  if (!key) { showAlert(T.empty); L.field.setAttribute("aria-invalid", "true"); L.field.focus(); return; }
  clearAlert(); setNotice("");
  setReveal(false);
  busy(true);
  let res;
  try { res = await login(key); } catch { fail("net", submit); return; }
  busy(false);
  if (res.status === 200) {
    L.field.value = "";
    close();
    [...loggedIn].forEach((fn) => fn());
  } else if (res.status === 401) {
    showAlert(T.wrong, true);
    L.field.setAttribute("aria-invalid", "true");
    L.field.focus(); L.field.select();                 // al teclear se reemplaza; no hace falta reescribir todo
  } else if (res.status === 429) {
    lock(Math.max(1, Number(res.body.retry_after) || 900));
  } else {
    fail("server", submit);
  }
}

// Al cargar: deja pasar si no hace falta clave (o ya hay sesión); si no, muestra la capa y espera el acceso.
export function ensureAccess() {
  refs();
  return new Promise((resolve) => {
    // si la sesión falla al cargar y luego se entra con la clave, igual se arranca la app
    onceLoggedIn(() => resolve({ auth_required: true, authenticated: true, station: "" }));
    const check = async () => {
      let s;
      try { s = await getSession(); }
      catch (e) {
        showLogin();
        fail(e && e.status ? "server" : "net", check, true);
        return;
      }
      if (!s.auth_required || s.authenticated) {
        if (!L.form.hidden) close();
        resolve(s);
        return;
      }
      showLogin({ station: s.station });
      L.station.textContent = s.station || "";
      reset();
      if (s.retry_after) lock(s.retry_after);               // el bloqueo sigue aunque se recargue la página
    };
    check();
  });
}

function onceLoggedIn(fn) {
  const wrap = () => { loggedIn.splice(loggedIn.indexOf(wrap), 1); fn(); };
  loggedIn.push(wrap);
}
