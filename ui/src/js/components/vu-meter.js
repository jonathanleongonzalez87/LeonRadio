// VU estéreo analógico (dos medidores de aguja, L y R) alimentado por el evento `audio.levels`.
import { bus } from "../api.js";
import { FONT_DISPLAY, FONT_MONO, canvasComponent, roundRect, tokens } from "./canvas.js";

const A0 = (-58 * Math.PI) / 180;   // ángulo de la aguja en reposo (respecto a la vertical)
const A1 = (58 * Math.PI) / 180;
const MARKS = [[0, "-20"], [0.3, "-10"], [0.55, "-5"], [0.8, "0"], [1, "+3"]];

function meter(ctx, T, x, y, w, h, value, label) {
  ctx.save();
  // cara del medidor, papel cálido iluminado
  const g = ctx.createLinearGradient(0, y, 0, y + h);
  g.addColorStop(0, T.cream); g.addColorStop(1, T.sand);
  roundRect(ctx, x, y, w, h, 8);
  ctx.fillStyle = g; ctx.fill();
  ctx.lineWidth = 2; ctx.strokeStyle = T.bronzeD; ctx.stroke();
  roundRect(ctx, x, y, w, h, 8); ctx.clip();

  const px = x + w / 2, py = y + h * 1.0;               // pivote
  const R = Math.min((w * 0.47) / Math.sin(A1), h * 0.8);

  // zona roja (0 a +3)
  ctx.beginPath();
  ctx.arc(px, py, R * 0.9, -Math.PI / 2 + A0 + (A1 - A0) * 0.8, -Math.PI / 2 + A1);
  ctx.lineWidth = Math.max(3, R * 0.05); ctx.strokeStyle = T.orange; ctx.stroke();
  // arco de escala
  ctx.beginPath();
  ctx.arc(px, py, R * 0.9, -Math.PI / 2 + A0, -Math.PI / 2 + A0 + (A1 - A0) * 0.8);
  ctx.lineWidth = 1.5; ctx.strokeStyle = T.carbon; ctx.stroke();

  // marcas y números
  ctx.fillStyle = T.carbon; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.font = `700 ${Math.max(9, R * 0.11)}px ${FONT_DISPLAY}`;
  for (let i = 0; i <= 20; i++) {
    const f = i / 20, a = -Math.PI / 2 + A0 + (A1 - A0) * f;
    const major = MARKS.some(([m]) => Math.abs(m - f) < 0.01);
    const r1 = R * 0.9, r2 = R * (major ? 0.78 : 0.84);
    ctx.beginPath();
    ctx.moveTo(px + Math.cos(a) * r1, py + Math.sin(a) * r1);
    ctx.lineTo(px + Math.cos(a) * r2, py + Math.sin(a) * r2);
    ctx.lineWidth = major ? 1.6 : 1; ctx.strokeStyle = f > 0.8 ? T.orange : T.carbon; ctx.stroke();
  }
  MARKS.forEach(([f, txt]) => {
    const a = -Math.PI / 2 + A0 + (A1 - A0) * f;
    ctx.fillStyle = f > 0.8 ? T.orange : T.carbon;
    ctx.fillText(txt, px + Math.cos(a) * R * 0.66, py + Math.sin(a) * R * 0.66);
  });

  // rótulos
  ctx.fillStyle = T.g500; ctx.font = `700 ${Math.max(10, R * 0.16)}px ${FONT_DISPLAY}`;
  ctx.textAlign = "left"; ctx.textBaseline = "top";
  ctx.fillText("VU", x + 10, y + 8);
  ctx.textBaseline = "middle"; ctx.textAlign = "center";
  ctx.fillStyle = T.carbon; ctx.font = `700 ${Math.max(10, R * 0.13)}px ${FONT_MONO}`;
  ctx.textAlign = "left"; ctx.fillText(label, x + 10, y + h - 12);

  // aguja
  const a = -Math.PI / 2 + A0 + (A1 - A0) * Math.max(0, Math.min(1.05, value));
  ctx.beginPath();
  ctx.moveTo(px - Math.cos(a) * R * 0.08, py - Math.sin(a) * R * 0.08);
  ctx.lineTo(px + Math.cos(a) * R * 0.88, py + Math.sin(a) * R * 0.88);
  ctx.lineWidth = Math.max(2, R * 0.022); ctx.lineCap = "round"; ctx.strokeStyle = T.carbon;
  ctx.shadowColor = "rgba(0,0,0,.35)"; ctx.shadowBlur = 3; ctx.shadowOffsetX = 2;
  ctx.stroke();
  ctx.shadowColor = "transparent";
  // tapa del pivote
  ctx.beginPath(); ctx.arc(px, py, Math.max(6, R * 0.09), 0, Math.PI * 2);
  ctx.fillStyle = T.bronzeD; ctx.fill();
  // brillo del cristal
  const gl = ctx.createLinearGradient(x, y, x, y + h * 0.5);
  gl.addColorStop(0, "rgba(255,255,255,.28)"); gl.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gl; ctx.fillRect(x, y, w, h * 0.5);
  ctx.restore();
}

// Versión compacta (áreas bajas): dos barras de LED horizontales, como en una franja de consola.
function bars(ctx, T, w, h, v) {
  const rows = [["L", v[0]], ["R", v[1]]];
  const gapY = 6, rowH = Math.max(8, Math.min(26, (h - gapY * 3) / 2));
  const top = (h - (rowH * 2 + gapY)) / 2;
  const x0 = 22, segs = 26, gap = 2;
  const segW = Math.max(3, (w - x0 - 8 - gap * (segs - 1)) / segs);
  rows.forEach(([label, val], i) => {
    const y = top + i * (rowH + gapY);
    ctx.fillStyle = T.cream; ctx.font = `700 ${Math.max(10, rowH * 0.7)}px ${FONT_MONO}`;
    ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(label, 4, y + rowH / 2);
    const on = Math.round(Math.min(1, val) * segs);
    for (let s = 0; s < segs; s++) {
      ctx.fillStyle = s < on ? (s >= segs - 4 ? T.orange : s >= segs - 9 ? T.bronze : T.cream) : T.g700;
      ctx.fillRect(x0 + s * (segW + gap), y, segW, rowH);
    }
  });
}

export function vuMeter() {
  const target = [0, 0];
  const value = [0, 0];
  const onLevels = (e) => { target[0] = e.detail.l ?? 0; target[1] = e.detail.r ?? 0; };
  bus.addEventListener("audio.levels", onLevels);

  const root = canvasComponent((ctx, w, h, _t, dt) => {
    const T = tokens();
    // balística tipo VU: sube rápido, baja más lento
    for (let i = 0; i < 2; i++) {
      const k = target[i] > value[i] ? 0.035 : 0.12;
      value[i] += (target[i] - value[i]) * (1 - Math.exp(-dt / k));
    }
    if (h < 150) { bars(ctx, T, w, h, value); return; }   // áreas bajas: barras de LED
    // caras con proporción de VU real (1.5:1), centradas verticalmente
    const gap = 8;
    const mw = Math.min((w - gap) / 2, h * 1.5);
    const mh = mw / 1.5;
    const x0 = (w - (mw * 2 + gap)) / 2, y0 = (h - mh) / 2;
    meter(ctx, T, x0, y0, mw, mh, value[0], "L");
    meter(ctx, T, x0 + mw + gap, y0, mw, mh, value[1], "R");
  });
  // deja de escuchar cuando el componente desaparece
  const cleanup = setInterval(() => {
    if (!root.isConnected) { bus.removeEventListener("audio.levels", onLevels); clearInterval(cleanup); }
  }, 3000);
  return root;
}
