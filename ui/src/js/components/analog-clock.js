// Reloj analógico de pared (como el de la cabina), con la hora de la emisora y fecha.
import { FONT_DISPLAY, FONT_MONO, canvasComponent, tokens } from "./canvas.js";

export function analogClock(props) {
  const tz = props.timezone || "America/Bogota";
  const name = props.name || "";
  const fmt = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dfmt = new Intl.DateTimeFormat("es-CO", { timeZone: tz, weekday: "short", day: "2-digit", month: "short" });

  return canvasComponent((ctx, w, h) => {
    const T = tokens();
    const now = Date.now();
    const p = Object.fromEntries(fmt.formatToParts(now).map((x) => [x.type, x.value]));
    const hh = +p.hour % 12, mm = +p.minute, ss = +p.second + (now % 1000) / 1000;

    const strip = Math.min(34, h * 0.16);
    const D = Math.min(w - 8, h - strip - 4);
    const cx = w / 2, cy = D / 2 + 2, R = D / 2;
    if (R < 30) return;

    // aro de bronce y cara
    let g = ctx.createLinearGradient(cx - R, cy - R, cx + R, cy + R);
    g.addColorStop(0, T.bronze); g.addColorStop(1, T.bronzeD);
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.92, 0, Math.PI * 2); ctx.fillStyle = T.cream; ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = T.g700; ctx.stroke();

    // marcas
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2 - Math.PI / 2, major = i % 5 === 0;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * R * 0.86, cy + Math.sin(a) * R * 0.86);
      ctx.lineTo(cx + Math.cos(a) * R * (major ? 0.76 : 0.81), cy + Math.sin(a) * R * (major ? 0.76 : 0.81));
      ctx.lineWidth = major ? 2.2 : 1; ctx.strokeStyle = T.carbon; ctx.stroke();
    }
    // números
    ctx.fillStyle = T.carbon; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = `700 ${R * 0.19}px ${FONT_DISPLAY}`;
    for (let n = 1; n <= 12; n++) {
      const a = (n / 12) * Math.PI * 2 - Math.PI / 2;
      ctx.fillText(String(n), cx + Math.cos(a) * R * 0.62, cy + Math.sin(a) * R * 0.62);
    }
    // marca de la emisora
    ctx.fillStyle = T.orange; ctx.font = `700 ${R * 0.12}px ${FONT_DISPLAY}`;
    ctx.fillText(name, cx, cy - R * 0.3);

    const hand = (angle, len, width, color, tail = 0.12) => {
      ctx.beginPath();
      ctx.moveTo(cx - Math.cos(angle) * R * tail, cy - Math.sin(angle) * R * tail);
      ctx.lineTo(cx + Math.cos(angle) * R * len, cy + Math.sin(angle) * R * len);
      ctx.lineWidth = width; ctx.lineCap = "round"; ctx.strokeStyle = color; ctx.stroke();
    };
    const up = -Math.PI / 2;
    ctx.shadowColor = "rgba(0,0,0,.3)"; ctx.shadowBlur = 4; ctx.shadowOffsetY = 2;
    hand(up + ((hh + mm / 60) / 12) * Math.PI * 2, 0.45, Math.max(4, R * 0.055), T.carbon);
    hand(up + ((mm + ss / 60) / 60) * Math.PI * 2, 0.7, Math.max(3, R * 0.04), T.carbon);
    hand(up + (ss / 60) * Math.PI * 2, 0.78, Math.max(1.5, R * 0.018), T.orange, 0.2);
    ctx.shadowColor = "transparent";
    ctx.beginPath(); ctx.arc(cx, cy, Math.max(4, R * 0.05), 0, Math.PI * 2); ctx.fillStyle = T.orange; ctx.fill();

    // fecha y hora digital debajo
    ctx.textBaseline = "alphabetic";
    ctx.font = `700 ${Math.max(11, strip * 0.5)}px ${FONT_MONO}`;
    ctx.fillStyle = T.orange;
    ctx.fillText(`${p.hour}:${p.minute}:${p.second}`, cx, D + strip * 0.62);
    ctx.font = `500 ${Math.max(9, strip * 0.32)}px ${FONT_DISPLAY}`;
    ctx.fillStyle = T.g300;
    ctx.fillText(dfmt.format(now).toUpperCase().replace(/\./g, ""), cx, D + strip * 0.98);
  });
}
