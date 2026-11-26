// Teclas de reproducción estilo pletina vintage: solo iconos (el nombre sale como ayuda al pasar el cursor).
// Las props son JSON y NO son de confianza: los textos van con textContent/atributos, los iconos son fijos.
import { runCommand } from "../api.js";

const NS = "http://www.w3.org/2000/svg";
const ICONS = {
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  pause: '<rect x="6" y="4.5" width="4.2" height="15"/><rect x="13.8" y="4.5" width="4.2" height="15"/>',
  stop: '<rect x="5.5" y="5.5" width="13" height="13"/>',
  next: '<path d="M4 5v14l9-7z"/><rect x="15.5" y="5" width="4.5" height="14"/>',
  stopafter: '<rect x="6" y="11" width="12.6" height="9" rx="3.5"/><rect x="6.2" y="5" width="2.6" height="9" rx="1.3"/>'
    + '<rect x="9.5" y="3" width="2.6" height="10" rx="1.3"/><rect x="12.8" y="3.5" width="2.6" height="10" rx="1.3"/>'
    + '<rect x="16.1" y="6" width="2.5" height="8" rx="1.25"/><path d="M6.5 15 3.2 11.8a1.4 1.4 0 0 1 2-2L8 12z"/>',
};

function icon(name) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name];                 // constante propia, no viene de las props
  return svg;
}

export function transportDeck(props, ctx) {
  const root = document.createElement("div");
  root.className = "deck";
  // Comandos de cada tecla: la Emisión usa playout.*, cada Auxiliar usa aux.* con su número (props.args).
  const c = props.cmds && typeof props.cmds === "object" ? props.cmds : {};
  const args = props.args && typeof props.args === "object" ? props.args : {};
  const keys = [
    { name: "play", label: "Reproducir", cmd: c.play, down: !!props.playing },
    { name: "pause", label: "Pausa", cmd: c.pause, down: !!props.paused },
    { name: "stop", label: "Stop", cmd: c.stop, down: false },
    { name: "next", label: "Siguiente", cmd: c.next, down: false },
    { name: "stopafter", label: "Parar tras la actual", cmd: c.stop_after, down: !!props.stop_after, led: true },
  ];
  keys.forEach((k) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `dkey${k.down ? " down" : ""}`;
    b.title = k.label;
    b.setAttribute("aria-label", k.label);
    if (k.led) { const l = document.createElement("i"); l.className = "dled"; b.append(l); }
    const knob = document.createElement("span");
    knob.className = "dknob";
    knob.append(icon(k.name));
    b.append(knob);
    b.addEventListener("click", async () => {
      try { await runCommand(k.cmd, args); } catch (e) { console.error(e); }
      ctx.refresh?.();
    });
    root.append(b);
  });
  return root;
}
