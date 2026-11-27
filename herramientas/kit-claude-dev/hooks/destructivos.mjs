// Guarda de comandos destructivos o irreversibles.
//
// No bloquea el trabajo: para lo que tiene vuelta difícil PIDE CONFIRMACIÓN ("ask") y el
// usuario decide en el momento. Solo niega lo que nunca corresponde (saltar hooks de git,
// formatear discos).
//
// Pide confirmación: force-push, push directo a main/master, reset --hard, clean -f,
// descartar todos los cambios, borrar ramas, rm -r / Remove-Item -Recurse fuera de carpetas
// de build, DROP/TRUNCATE/DELETE sin WHERE, borrar repos o paquetes publicados, y
// ejecutar scripts bajados de internet sin mirarlos (curl | sh, irm | iex).

// Carpetas que se regeneran solas: borrarlas no pide confirmación.
const REGENERABLES = new Set([
  "node_modules", "dist", "build", "out", ".next", ".nuxt", ".turbo", ".vercel", ".cache",
  "coverage", ".parcel-cache", "__pycache__", ".pytest_cache", "target", "tmp", ".tmp",
]);

const ask = (motivo) => ({ decision: "ask", motivo });
const deny = (motivo) => ({ decision: "deny", motivo });

function borraAlgoNoRegenerable(cmd) {
  // rm -rf a b / rm -r -f a / Remove-Item a -Recurse / rd /s a
  const partes = cmd.split(/&&|\|\||;|\n/);
  for (const p of partes) {
    const rm = p.match(/\brm\s+((?:-[a-zA-Z]+\s+|--[a-z-]+\s+)*)(.*)$/);
    const ri = /\b(Remove-Item|rm|del|ri|rmdir|rd)\b/i.test(p) && /-Recurse\b|\s\/s\b/i.test(p);
    let objetivos = null;
    if (rm && /(^|\s)-[a-zA-Z]*[rR]|--recursive/.test(rm[1])) objetivos = rm[2];
    else if (ri) objetivos = p.replace(/\b(Remove-Item|rm|del|ri|rmdir|rd)\b/i, "").replace(/\s-\w+(:\S+)?|\s\/[a-z]\b/gi, " ");
    if (objetivos === null) continue;
    const lista = objetivos.trim().split(/\s+/).map((t) => t.replace(/^["']|["'],?$/g, "")).filter(Boolean);
    if (!lista.length) return true;
    for (const t of lista) {
      const base = t.replace(/[\\/]+$/, "").split(/[\\/]/).pop();
      if (!REGENERABLES.has(base)) return true;
    }
  }
  return false;
}

export function revisar(tool, inp) {
  if (tool !== "Bash" && tool !== "PowerShell") return null;
  const cmd = String(inp.command || "");

  if (/--no-verify\b/.test(cmd)) {
    return deny("Bloqueado: --no-verify salta los controles del repo. Si un hook falla, arreglá lo que falla.");
  }
  if (/\b(format\s+[a-z]:|diskpart|mkfs(\.\w+)?|dd\s+if=.*\bof=\/dev\/)/i.test(cmd)) {
    return deny("Bloqueado: formatear o escribir discos enteros no lo hace un agente.");
  }
  if (/\bgit\s+push\b/.test(cmd) && /(\s--force(?!-with-lease)\b|\s-f\b|\s\+\S+)/.test(cmd)) {
    return ask("Force-push: reescribe la historia del remoto. ¿Confirmás? (Preferí --force-with-lease.)");
  }
  if (/\bgit\s+push\b[^;&|]*\s(main|master)\b/.test(cmd)) {
    return ask("Push directo a main/master: publicar en la rama principal lo decide el usuario. ¿Confirmás?");
  }
  if (/\bgit\s+reset\s+--hard\b/.test(cmd)) return ask("git reset --hard descarta cambios sin commitear. ¿Confirmás?");
  if (/\bgit\s+clean\s+-[a-zA-Z]*f/.test(cmd)) return ask("git clean -f borra archivos sin seguimiento (no van a la papelera). ¿Confirmás?");
  if (/\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)|\bgit\s+stash\s+(drop|clear)\b/.test(cmd)) {
    return ask("Esto descarta cambios locales que no se pueden recuperar. ¿Confirmás?");
  }
  if (/\bgit\s+branch\s+-D\b/.test(cmd)) return ask("git branch -D borra una rama aunque no esté mergeada. ¿Confirmás?");
  if (borraAlgoNoRegenerable(cmd)) {
    return ask("Borrado recursivo de algo que no es una carpeta de build: no pasa por la papelera. ¿Confirmás? (Protocolo: skill borrado-seguro.)");
  }
  if (/\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\b)/i.test(cmd) || /\bDELETE\s+FROM\s+[\w."]+\s*(;|"|'|$)/i.test(cmd)) {
    return ask("SQL destructivo (DROP / TRUNCATE / DELETE sin WHERE). ¿Contra qué base? ¿Confirmás?");
  }
  if (/\b(gh\s+repo\s+delete|npm\s+unpublish|vercel\s+(env\s+rm|remove|rm)|firebase\s+\w+:delete|supabase\s+db\s+reset)\b/i.test(cmd)) {
    return ask("Esto borra algo publicado o de producción. ¿Confirmás?");
  }
  if (/\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b|\b(irm|iwr|Invoke-RestMethod|Invoke-WebRequest)\b[^|]*\|\s*(iex|Invoke-Expression)\b/i.test(cmd)) {
    return ask("Ejecuta un script bajado de internet sin revisarlo. ¿Lo revisaste y confirmás?");
  }
  return null;
}
