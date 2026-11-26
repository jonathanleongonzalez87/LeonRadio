// Monitores de estudio: escucha la emisión desde este dispositivo (teléfono, tableta, otra PC de la red).
// Dos cajas acústicas vintage cuyo woofer late con el nivel, perilla de volumen tipo consola Autogram y un interruptor.
// El audio llega por WebSocket (PCM de 16 bits) y se reproduce con Web Audio; el volumen es de ESTE dispositivo.
//
// El motor de escucha vive fuera de los paneles (se redibujan a menudo): `mon` guarda el estado entre dibujos.

import { bus, needsLogin } from "../api.js";

const NS = "http://www.w3.org/2000/svg";
const KEY = "leonradio.monitor.vol";
const LATENCY = 0.25;                 // segundos de colchón antes de sonar (ahorra cortes en Wi-Fi)

const mon = { on: false, status: "off", ws: null, ctx: null, gain: null, next: 0, vol: loadVol(), view: null, rate: 44100 };

function loadVol() {
  try { const v = parseFloat(localStorage.getItem(KEY)); if (v >= 0 && v <= 1) return v; } catch { /* sin almacenamiento */ }
  return 0.6;
}
const saveVol = () => { try { localStorage.setItem(KEY, String(mon.vol)); } catch { /* nada */ } };
const gainOf = (v) => v * v;           // el volumen se siente mejor con curva cuadrática

function setStatus(s) { mon.status = s; mon.view?.paint(); }

function start() {
  if (mon.on) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) { setStatus("noaudio"); return; }
  mon.ctx = mon.ctx || new Ctx({ latencyHint: "interactive" });
  mon.ctx.resume?.();                  // debe ocurrir dentro del clic: los navegadores lo exigen
  mon.gain = mon.gain || mon.ctx.createGain();
  mon.gain.gain.value = gainOf(mon.vol);
  mon.gain.connect(mon.ctx.destination);
  mon.an = mon.an || buildAnalysers(mon.ctx, mon.gain);
  mon.on = true;
  setStatus("connecting");
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/monitor`);
  ws.binaryType = "arraybuffer";
  mon.ws = ws;
  mon.next = 0;
  ws.onmessage = (m) => {
    if (typeof m.data === "string") {
      try { mon.rate = JSON.parse(m.data).rate || 44100; } catch { /* cabecera inválida */ }
      setStatus("live");
      return;
    }
    play(new Int16Array(m.data));
  };
  ws.onerror = () => { if (mon.ws === ws) setStatus("error"); };
  ws.onclose = () => {
    if (mon.ws !== ws) return;
    stop(); setStatus("error");
    needsLogin().then((n) => { if (n) bus.dispatchEvent(new Event("auth.required")); });   // sin sesión: pantalla de acceso, no bucle
  };
}

function stop() {
  mon.on = false;
  const ws = mon.ws;
  mon.ws = null;
  try { ws?.close(); } catch { /* ya cerrado */ }
  try { mon.gain?.disconnect(mon.ctx.destination); } catch { /* ya desconectado */ }
  if (mon.status !== "error") setStatus("off");
}

function play(pcm) {
  const ctx = mon.ctx;
  const frames = pcm.length >> 1;
  if (!ctx || !frames) return;
  const buf = ctx.createBuffer(2, frames, mon.rate);
  const l = buf.getChannelData(0), r = buf.getChannelData(1);
  for (let i = 0; i < frames; i++) { l[i] = pcm[2 * i] / 32768; r[i] = pcm[2 * i + 1] / 32768; }
  const now = ctx.currentTime;
  if (mon.next < now + 0.02) mon.next = now + LATENCY;          // se vació el colchón: se vuelve a llenar
  if (mon.next > now + 1.2) return;                              // demasiado atrasado: se descarta este bloque
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(mon.gain);
  src.start(mon.next);
  mon.next += frames / mon.rate;
}

// ------------------------------------------------------------------ análisis para animar las membranas
// Se mide DESPUÉS de la perilla: al bajar el volumen las membranas se mueven menos, y a volumen 0 se quedan quietas.
// Cada canal se separa en graves (woofer), medios (cono medio) y agudos (tweeters), como en una caja de verdad.
function buildAnalysers(ctx, gain) {
  const split = ctx.createChannelSplitter(2);
  gain.connect(split);
  const mute = ctx.createGain();                                   // salida muda: algunos navegadores solo procesan
  mute.gain.value = 0;                                             // los nodos que llegan al destino
  mute.connect(ctx.destination);
  const band = (ch, type, freq, q) => {
    const f = ctx.createBiquadFilter();
    f.type = type; f.frequency.value = freq;
    if (q) f.Q.value = q;
    const a = ctx.createAnalyser();
    a.fftSize = 256; a.smoothingTimeConstant = 0;
    split.connect(f, ch); f.connect(a); a.connect(mute);
    return a;
  };
  return [0, 1].map((ch) => ({
    low: band(ch, "lowpass", 180), mid: band(ch, "bandpass", 1200, 0.7), high: band(ch, "highpass", 4000),
  }));
}
const BOOST = { low: 5, mid: 7, high: 13 };                      // cuánto se amplifica cada banda para verse

// ------------------------------------------------------------------ dibujo
const svg = (tag, attrs = {}, parent) => {
  const e = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  parent?.append(e);
  return e;
};

function gradient(defs, id, kind, attrs, stops) {
  const g = svg(kind, { id, ...attrs }, defs);
  stops.forEach(([o, c]) => svg("stop", { offset: o, "stop-color": c }, g));
}

function speaker(root, x, defs) {
  const g = svg("g", { transform: `translate(${x} 8)` }, root);
  svg("rect", { width: 190, height: 214, rx: 7, fill: "url(#wood)", stroke: "#3b2412", "stroke-width": 2 }, g);
  svg("rect", { x: 6, y: 6, width: 178, height: 202, rx: 4, fill: "none", stroke: "rgba(0,0,0,.25)" }, g);
  // tweeters, bocina y medio (arriba)
  const tweeters = [[28, 28], [28, 62]].map(([cx, cy]) => {
    svg("circle", { cx, cy, r: 13, fill: "#1c1815", stroke: "#0c0a08", "stroke-width": 2 }, g);
    return svg("circle", { cx, cy, r: 7, fill: "url(#cone)", style: `transform-origin:${cx}px ${cy}px` }, g);
  });
  svg("rect", { x: 70, y: 14, width: 18, height: 56, rx: 3, fill: "#16120f", stroke: "#0c0a08", "stroke-width": 2 }, g);
  svg("rect", { x: 74, y: 19, width: 10, height: 46, rx: 2, fill: "#2a241d" }, g);
  svg("circle", { cx: 138, cy: 42, r: 28, fill: "#241f1a", stroke: "#0c0a08", "stroke-width": 2 }, g);
  const mid = svg("g", { style: "transform-origin:138px 42px" }, g);
  svg("circle", { cx: 138, cy: 42, r: 21, fill: "url(#cone)" }, mid);
  svg("circle", { cx: 138, cy: 42, r: 8, fill: "#9c9890" }, mid);
  // woofer
  const w = svg("g", { class: "woofer" }, g);
  svg("circle", { cx: 95, cy: 140, r: 68, fill: "#201b16", stroke: "#0c0a08", "stroke-width": 2 }, g);
  svg("circle", { cx: 95, cy: 140, r: 60, fill: "none", stroke: "#4a4036", "stroke-width": 5 }, g);
  const cone = svg("g", { style: "transform-origin:95px 140px;transition:transform .06s linear" }, w);
  svg("circle", { cx: 95, cy: 140, r: 54, fill: "url(#cone)" }, cone);
  [40, 28].forEach((r) => svg("circle", { cx: 95, cy: 140, r, fill: "none", stroke: "rgba(120,100,70,.22)" }, cone));
  const cap = svg("circle", { cx: 95, cy: 140, r: 17, fill: "url(#cap)" }, cone);
  // tornillos
  [[10, 10], [180, 10], [10, 204], [180, 204]].forEach(([cx, cy]) =>
    svg("circle", { cx, cy, r: 3, fill: "#2b1a0c", stroke: "rgba(255,255,255,.2)" }, g));
  return { cone, cap, mid, tweeters };
}

function knobSvg() {
  const s = svg("svg", { viewBox: "0 0 150 150", class: "mon-knob", role: "slider", tabindex: 0,
                        "aria-label": "Volumen del monitor", "aria-valuemin": 0, "aria-valuemax": 100 });
  const defs = svg("defs", {}, s);
  gradient(defs, "skirt", "radialGradient", { cx: "40%", cy: "35%", r: "75%" }, [[0, "#3a3835"], [0.6, "#171614"], [1, "#050505"]]);
  gradient(defs, "alu", "linearGradient", { x1: "0", y1: "0", x2: "1", y2: "1" },
    [[0, "#e9e7e2"], [0.35, "#9d9a93"], [0.55, "#d6d3cc"], [1, "#6d6a64"]]);
  // marcas de la escala
  for (let i = 0; i <= 10; i++) {
    const a = (-135 + 27 * i) * Math.PI / 180;
    const r1 = 62, r2 = i % 5 === 0 ? 72 : 68;
    svg("line", { x1: 75 + r1 * Math.sin(a), y1: 75 - r1 * Math.cos(a), x2: 75 + r2 * Math.sin(a), y2: 75 - r2 * Math.cos(a),
                  stroke: "#cfc6b4", "stroke-width": i % 5 === 0 ? 2 : 1 }, s);
  }
  svg("circle", { cx: 75, cy: 75, r: 56, fill: "url(#skirt)" }, s);
  for (let i = 0; i < 48; i++) {                                    // moleteado del faldón
    const a = i * 7.5 * Math.PI / 180;
    svg("line", { x1: 75 + 50 * Math.sin(a), y1: 75 - 50 * Math.cos(a), x2: 75 + 56 * Math.sin(a), y2: 75 - 56 * Math.cos(a),
                  stroke: "rgba(255,255,255,.07)", "stroke-width": 1.5 }, s);
  }
  const rot = svg("g", { style: "transform-origin:75px 75px" }, s);
  svg("circle", { cx: 75, cy: 75, r: 38, fill: "url(#alu)", stroke: "#2b2a27", "stroke-width": 1.5 }, rot);
  for (let i = 0; i < 40; i++) {                                    // cepillado radial del aluminio
    const a = i * 9 * Math.PI / 180;
    svg("line", { x1: 75, y1: 75, x2: 75 + 37 * Math.sin(a), y2: 75 - 37 * Math.cos(a), stroke: "rgba(0,0,0,.08)" }, rot);
  }
  svg("line", { x1: 75, y1: 75, x2: 75, y2: 38, stroke: "#14110f", "stroke-width": 2, "stroke-linecap": "round" }, rot);
  svg("circle", { cx: 75, cy: 75, r: 2.5, fill: "#14110f" }, rot);
  return { el: s, rot };
}

function toggleSvg() {
  const s = svg("svg", { viewBox: "0 0 70 90", class: "mon-toggle", role: "switch", tabindex: 0, "aria-label": "Escuchar" });
  svg("circle", { cx: 35, cy: 45, r: 24, fill: "#6d6a64", stroke: "#2b2a27", "stroke-width": 2 }, s);
  svg("circle", { cx: 35, cy: 45, r: 17, fill: "#14110f" }, s);
  const lever = svg("g", { style: "transform-origin:35px 45px;transition:transform .12s" }, s);
  svg("rect", { x: 31, y: 8, width: 8, height: 38, rx: 4, fill: "#0e0d0c", stroke: "#3a3835" }, lever);
  svg("ellipse", { cx: 35, cy: 10, rx: 7, ry: 5, fill: "#1e1c1a", stroke: "#4a4742" }, lever);
  return { el: s, lever };
}

const STATUS = {
  off: "Apagado · enciende para escuchar desde este dispositivo",
  connecting: "Conectando…", live: "Escuchando la emisión", error: "Sin conexión con el servidor",
  noaudio: "Este navegador no puede reproducir audio",
};

export function monitors() {
  const root = document.createElement("div");
  root.className = "mon";
  const stage = svg("svg", { viewBox: "0 0 420 230", class: "mon-spk", role: "img", "aria-label": "Monitores de estudio" });
  const defs = svg("defs", {}, stage);
  gradient(defs, "wood", "linearGradient", { x1: "0", y1: "0", x2: "1", y2: "1" }, [[0, "#c98a4b"], [0.5, "#b0713a"], [1, "#8a5126"]]);
  gradient(defs, "cone", "radialGradient", { cx: "40%", cy: "35%", r: "70%" }, [[0, "#f3ecda"], [0.7, "#d9ceb3"], [1, "#a89c80"]]);
  gradient(defs, "cap", "radialGradient", { cx: "38%", cy: "32%", r: "75%" }, [[0, "#fbf7ea"], [0.6, "#d8cfb8"], [1, "#948a72"]]);
  const L = speaker(stage, 8, defs), R = speaker(stage, 222, defs);

  const ctl = document.createElement("div");
  ctl.className = "mon-ctl";
  const knob = knobSvg();
  const tog = toggleSvg();
  const plate = document.createElement("div");
  plate.className = "mon-plate";
  plate.textContent = "MONITOR";
  const kbox = document.createElement("div"); kbox.className = "mon-k"; kbox.append(knob.el, plate);
  const tbox = document.createElement("div"); tbox.className = "mon-t";
  const tl = document.createElement("div"); tl.className = "mon-tl"; tl.textContent = "ESCUCHAR";
  const lamp = document.createElement("i"); lamp.className = "mon-lamp";
  tbox.append(tog.el, tl, lamp);
  ctl.append(kbox, tbox);
  const cap = document.createElement("div");
  cap.className = "mon-cap";
  const note = document.createElement("div");
  note.className = "mon-note";
  note.textContent = "Ponlo en un dispositivo distinto al que emite; en el mismo PC se oiría doble y con retraso.";
  root.append(stage, ctl, cap, note);

  const paint = () => {
    const a = -135 + 270 * mon.vol;
    knob.rot.style.transform = `rotate(${a}deg)`;
    knob.el.setAttribute("aria-valuenow", String(Math.round(mon.vol * 100)));
    tog.lever.style.transform = `rotate(${mon.on ? 0 : 180}deg)`;
    tog.el.setAttribute("aria-checked", String(mon.on));
    lamp.classList.toggle("on", mon.status === "live");
    cap.textContent = STATUS[mon.status] || "";
    cap.classList.toggle("bad", mon.status === "error" || mon.status === "noaudio");
  };
  mon.view = { paint };
  paint();

  const setVol = (v) => {
    mon.vol = Math.max(0, Math.min(1, v));
    if (mon.gain) mon.gain.gain.value = gainOf(mon.vol);
    saveVol(); paint();
  };
  // girar con el puntero: el ángulo del puntero respecto al centro manda (de -135° a +135°)
  const fromPointer = (e) => {
    const r = knob.el.getBoundingClientRect();
    let a = Math.atan2(e.clientX - (r.left + r.width / 2), -(e.clientY - (r.top + r.height / 2))) * 180 / Math.PI;
    if (a > 135) a = 135; else if (a < -135) a = -135;
    return (a + 135) / 270;
  };
  knob.el.addEventListener("pointerdown", (e) => {
    knob.el.setPointerCapture(e.pointerId);
    document.body.classList.add("lr-dragging");                    // sin redibujar mientras se gira
    setVol(fromPointer(e));
    const move = (ev) => setVol(fromPointer(ev));
    const up = () => {
      document.body.classList.remove("lr-dragging");
      knob.el.removeEventListener("pointermove", move);
      knob.el.removeEventListener("pointerup", up);
      knob.el.removeEventListener("pointercancel", up);
    };
    knob.el.addEventListener("pointermove", move);
    knob.el.addEventListener("pointerup", up);
    knob.el.addEventListener("pointercancel", up);
  });
  knob.el.addEventListener("wheel", (e) => { e.preventDefault(); setVol(mon.vol - Math.sign(e.deltaY) * 0.04); }, { passive: false });
  knob.el.addEventListener("keydown", (e) => {
    const d = { ArrowUp: 0.04, ArrowRight: 0.04, ArrowDown: -0.04, ArrowLeft: -0.04, PageUp: 0.15, PageDown: -0.15 }[e.key];
    if (d) { e.preventDefault(); setVol(mon.vol + d); }
  });
  const flip = () => { if (mon.on) { stop(); } else { mon.status = "off"; start(); } paint(); };
  tog.el.addEventListener("click", flip);
  tog.el.addEventListener("keydown", (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); flip(); } });

  // las membranas siguen el ritmo del audio que suena, con ataque rápido y caída suave
  const buf = new Float32Array(256);
  const energy = (a, boost) => {
    a.getFloatTimeDomainData(buf);
    let s = 0;
    for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
    return Math.min(1, Math.pow(Math.sqrt(s / buf.length) * boost, 0.7));
  };
  const k = [{ low: 0, mid: 0, high: 0 }, { low: 0, mid: 0, high: 0 }];
  const frame = () => {
    if (!root.isConnected) { if (mon.view?.paint === paint) mon.view = null; return; }
    const comp = 1 / Math.max(mon.vol, 0.15);                      // la perilla manda casi lineal sobre el movimiento
    [L, R].forEach((sp, ch) => {
      const an = mon.on && mon.status === "live" && mon.an ? mon.an[ch] : null;
      for (const b of ["low", "mid", "high"]) {
        k[ch][b] = Math.max(an ? energy(an[b], BOOST[b] * comp) : 0, k[ch][b] * 0.82);
      }
      sp.cone.style.transform = `scale(${1 + k[ch].low * 0.06})`;          // sutil: como mucho un 6 %
      sp.cap.setAttribute("r", String(17 + k[ch].low * 3.5));
      sp.mid.style.transform = `scale(${1 + k[ch].mid * 0.05})`;
      sp.tweeters.forEach((t) => { t.style.transform = `scale(${1 + k[ch].high * 0.14})`; });
    });
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  return root;
}
