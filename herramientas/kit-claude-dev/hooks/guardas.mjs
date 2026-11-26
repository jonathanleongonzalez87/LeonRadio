// Guardas del kit (hook PreToolUse de Claude Code).
//
// Un solo proceso de Node revisa todas las guardas activas, así cada herramienta paga un
// solo arranque (~50 ms) aunque estén las tres prendidas.
//
// Qué guardas corren:
//  - ~/.claude/kit/estado.json  → { "secretos": true, "destructivos": true, ... } (lo maneja kit.mjs)
//  - variable KIT_OFF al abrir Claude → apaga guardas solo en esa sesión:
//      KIT_OFF=secretos,destructivos   o   KIT_OFF=todo
// Siempre corre (no se apaga): la protección del propio kit. Si Claude intenta apagar
// módulos o tocar los archivos del kit, se le pide confirmación al usuario.

import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { revisar as secretos } from "./secretos.mjs";
import { revisar as destructivos } from "./destructivos.mjs";
import { revisar as simularEntrada } from "./simular-entrada.mjs";

const GUARDAS = [
  ["secretos", secretos],
  ["destructivos", destructivos],
  ["simular-entrada", simularEntrada],
];

function activas() {
  let estado = {};
  try {
    estado = JSON.parse(readFileSync(path.join(os.homedir(), ".claude", "kit", "estado.json"), "utf8"));
  } catch {
    // sin estado: todas prendidas
  }
  const off = String(process.env.KIT_OFF || "").toLowerCase().split(/[,\s]+/).filter(Boolean);
  return GUARDAS.filter(([n]) => estado[n] !== false && !off.includes(n) && !off.includes("todo"));
}

function protegerKit(tool, inp) {
  const motivo = "Esto cambia el kit de guardas (apagar módulos o editar sus archivos). Solo lo decide el usuario. ¿Confirmás?";
  if (tool === "Bash" || tool === "PowerShell") {
    const cmd = String(inp.command || "");
    if (/kit\.mjs["']?\s+(off|perfil|desinstalar)\b/i.test(cmd)) return { decision: "ask", motivo };
    if (/[\\/]\.claude[\\/]kit[\\/]/i.test(cmd) && /(estado\.json|hooks[\\/])/i.test(cmd) && /(>|Set-Content|Out-File|Remove-Item|\brm\b|\bmv\b|Move-Item|writeFile|sed\s+-i)/i.test(cmd)) {
      return { decision: "ask", motivo };
    }
  }
  if (tool === "Write" || tool === "Edit" || tool === "MultiEdit") {
    const ruta = String(inp.file_path || "");
    if (/[\\/]\.claude[\\/]kit[\\/](estado\.json|hooks[\\/])/i.test(ruta)) return { decision: "ask", motivo };
    if (/[\\/]\.claude[\\/]settings(\.local)?\.json$/i.test(ruta) && /kit[\\/]hooks|disableAllHooks/i.test(JSON.stringify(inp))) {
      return { decision: "ask", motivo };
    }
  }
  return null;
}

let raw = "";
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  let ev;
  try {
    ev = JSON.parse(raw || "{}");
  } catch {
    return; // entrada rara: no bloqueamos
  }
  const tool = ev.tool_name || "";
  const inp = ev.tool_input || {};
  const hallazgos = [];
  try {
    const meta = protegerKit(tool, inp);
    if (meta) hallazgos.push(meta);
    for (const [, revisar] of activas()) {
      const r = revisar(tool, inp);
      if (r) hallazgos.push(r);
    }
  } catch (e) {
    process.stderr.write(`kit/guardas: error interno, no bloqueo (${e && e.message})\n`);
    return;
  }
  const r = hallazgos.find((h) => h.decision === "deny") || hallazgos[0];
  if (!r) return;
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: r.decision,
        permissionDecisionReason: r.motivo,
      },
    }),
  );
});
