// Dial FM de baquelita con cristal + texto RDS (nombre de la emisora y lo que suena).
// Todos los tamaños salen de una unidad `u` calculada del espacio disponible.
import { FONT_DISPLAY, FONT_MONO, canvasComponent, tokens } from "./canvas.js";

const F0 = 88, F1 = 108;

export function fmDial(props) {
  const name = props.name || "";
  const freq = typeof props.frequency === "number" ? props.frequency : null;
  const rds = String(props.rds || "");

  return canvasComponent((ctx, w, h, t) => {
    const T = tokens();
    const dialH = Math.min(Math.max(50, h * 0.5), w * 0.34);
    const u = Math.max(8, Math.min(w / 34, dialH / 6));   // unidad tipográfica
    const narrow = w < 230;

    // cristal oscuro cálido
    const g = ctx.createRadialGradient(w / 2, dialH * 0.45, 4, w / 2, dialH * 0.45, w * 0.6);
    g.addColorStop(0, "#382B1E"); g.addColorStop(0.72, "#1C1713"); g.addColorStop(1, "#120F0C");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, dialH);
    ctx.strokeStyle = T.bronzeD; ctx.lineWidth = 2; ctx.strokeRect(1, 1, w - 2, dialH - 2);

    // escala 88–108 MHz
    const padX = 14, x0 = padX, x1 = w - padX, base = dialH * 0.7;
    const X = (f) => x0 + ((f - F0) / (F1 - F0)) * (x1 - x0);
    ctx.strokeStyle = T.bronze; ctx.fillStyle = T.cream; ctx.textAlign = "center"; ctx.textBaseline = "top";
    ctx.font = `500 ${u * 0.8}px ${FONT_MONO}`;
    ctx.beginPath(); ctx.moveTo(x0, base); ctx.lineTo(x1, base); ctx.lineWidth = 1; ctx.stroke();
    for (let f = F0; f <= F1 + 1e-6; f += 0.5) {
      const whole = Math.abs(f - Math.round(f)) < 1e-6, even = whole && Math.round(f) % 2 === 0;
      ctx.beginPath(); ctx.moveTo(X(f), base);
      ctx.lineTo(X(f), base - (even ? u * 1.5 : whole ? u : u * 0.6));
      ctx.lineWidth = even ? 1.6 : 1; ctx.stroke();
      if (even && w > 300 && Math.round(f) % 4 === 0) ctx.fillText(String(Math.round(f)), X(f), base + 3);
    }
    if (!narrow) {
      ctx.textAlign = "left"; ctx.fillStyle = T.bronze;
      ctx.font = `700 ${u * 0.7}px ${FONT_DISPLAY}`;
      ctx.fillText("FM · MHz", x0, 6);
    }

    // aguja y frecuencia
    const freqTxt = freq === null ? "ONLINE" : freq.toFixed(1);
    ctx.textAlign = narrow ? "center" : "right"; ctx.fillStyle = T.orange;
    ctx.font = `700 ${Math.min(u * 1.7, (w - 2 * padX) / (freqTxt.length * 0.7))}px ${FONT_MONO}`;
    ctx.fillText(freqTxt, narrow ? w / 2 : x1, 4);
    if (freq !== null && freq >= F0 && freq <= F1) {
      ctx.shadowColor = T.orange; ctx.shadowBlur = 8;
      ctx.beginPath(); ctx.moveTo(X(freq), dialH * 0.1); ctx.lineTo(X(freq), base + 6);
      ctx.lineWidth = 2; ctx.strokeStyle = T.orange; ctx.stroke(); ctx.shadowColor = "transparent";
    }
    const gl = ctx.createLinearGradient(0, 0, 0, dialH * 0.45);   // reflejo del cristal
    gl.addColorStop(0, "rgba(255,255,255,.12)"); gl.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = gl; ctx.fillRect(2, 2, w - 4, dialH * 0.45);

    // panel RDS
    ctx.fillStyle = T.g700; ctx.fillRect(0, dialH, w, h - dialH);
    ctx.textBaseline = "top";
    const ry = dialH + u * 0.6;
    ctx.textAlign = "left"; ctx.fillStyle = T.cream; ctx.font = `700 ${u * 0.8}px ${FONT_MONO}`;
    ctx.fillText("RDS", 10, ry);
    if (!narrow) { ctx.textAlign = "right"; ctx.fillStyle = T.felt; ctx.fillText("STEREO", w - 10, ry); }

    ctx.textAlign = "center"; ctx.fillStyle = T.orange;
    ctx.font = `700 ${u * 1.9}px ${FONT_DISPLAY}`;
    ctx.fillText(name, w / 2, ry + u * 1.1);

    // texto RDS: se desplaza si no cabe
    ctx.font = `500 ${u * 0.95}px ${FONT_MONO}`; ctx.fillStyle = T.cream;
    const room = w - 20, tw = ctx.measureText(rds).width, ty = ry + u * 3.6;
    ctx.save(); ctx.beginPath(); ctx.rect(10, 0, room, h); ctx.clip();
    if (tw <= room) { ctx.textAlign = "center"; ctx.fillText(rds, w / 2, ty); }
    else {
      ctx.textAlign = "left";
      const span = tw + 40, off = ((t / 1000) * 30) % span;
      ctx.fillText(rds, 10 - off, ty); ctx.fillText(rds, 10 - off + span, ty);
    }
    ctx.restore();
  });
}
