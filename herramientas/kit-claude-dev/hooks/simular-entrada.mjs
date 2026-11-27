// Guarda contra simular teclado o mouse.
//
// Ningún agente maneja el escritorio del usuario tocando teclas o haciendo clics. En el
// proyecto de donde sale este kit, un agente lo hizo "para probar" un diálogo de «Elegir
// carpeta» y dos veces eligió otra carpeta. Lo que solo puede hacer una persona (una
// ventana del sistema, el navegador real) va como "Pendiente del usuario".
//
// Bloquea:
//  1) comandos y código que simulan entrada (SendKeys, SendInput, keybd_event, mouse_event,
//     SetCursorPos, UI Automation, AutoHotkey, nircmd, pyautogui, pynput, robotjs, nut-js…);
//  2) las herramientas de "computer use" (capturas, clics y teclas en el escritorio).
// Sigue permitido: buscar esos nombres con un solo comando de búsqueda y nombrarlos en .md.

const SIMULA =
  /\b(SendKeys|SendInput|keybd_event|mouse_event|SetCursorPos|SetForegroundWindow|AppActivate)\b|System\.Windows\.Automation|UIAutomationClient|\bAutoHotkey\b|\.ahk\b|\bnircmd\b|\bpyautogui\b|\bpynput\b|\bpywinauto\b|\brobotjs\b|@nut-tree|\bnut-js\b|\bxdotool\b|\bcliclick\b/i;
const COMPUTER_USE = /^(mcp__computer-use__|mcp__remote-devices__computer|enable__mcp__remote-devices__computer)/;
const BUSQUEDA = /^\s*(?:git(?:\s+-C\s+(?:"[^"]*"|'[^']*'|\S+))?\s+grep|grep|egrep|rg|Select-String|sls|findstr)\b/i;
const ENCADENA = /[;&|`]|\$\(/;
const EXCEPCIONES = [/[\\/]\.claude[\\/]kit[\\/]hooks[\\/]/i];

const deny = (motivo) => ({ decision: "deny", motivo });
const MOTIVO_ENTRADA =
  "Bloqueado: simular teclado o mouse no está permitido, ni siquiera para probar: maneja el escritorio del usuario. Probá con pruebas automáticas, y dejá lo que necesita una ventana real como «Pendiente del usuario», con 1 a 3 pasos. (Se apaga con: /kit off simular-entrada)";
const MOTIVO_COMPUTER_USE =
  "Bloqueado: computer use (capturas, clics y teclas en el escritorio) está apagado por el kit. Lo que necesite la pantalla real va como «Pendiente del usuario». (Se apaga con: /kit off simular-entrada)";

export function revisar(tool, inp) {
  if (COMPUTER_USE.test(tool)) return deny(MOTIVO_COMPUTER_USE);

  if (tool === "Bash" || tool === "PowerShell") {
    const cmd = String(inp.command || "");
    if (!SIMULA.test(cmd)) return null;
    const sinComillas = cmd.replace(/"(?:[^"\\]|\\.)*"|'[^']*'/g, '""');
    if (BUSQUEDA.test(cmd) && !ENCADENA.test(sinComillas)) return null;
    return deny(MOTIVO_ENTRADA);
  }

  if (tool === "Write" || tool === "Edit" || tool === "MultiEdit" || tool === "NotebookEdit") {
    const ruta = String(inp.file_path || inp.notebook_path || "");
    if (/\.md$/i.test(ruta) || EXCEPCIONES.some((re) => re.test(ruta))) return null;
    const texto = [inp.content, inp.new_string, inp.new_source, ...(Array.isArray(inp.edits) ? inp.edits.map((e) => e && e.new_string) : [])]
      .filter((t) => typeof t === "string")
      .join("\n");
    return SIMULA.test(texto) ? deny(MOTIVO_ENTRADA) : null;
  }
  return null;
}
