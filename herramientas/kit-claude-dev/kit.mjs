#!/usr/bin/env node
// kit.mjs — instala, prende/apaga y desinstala el kit de desarrollo para Claude Code.
//
//   node kit.mjs instalar [minimo|normal|completo]   (por defecto: completo)
//   node kit.mjs estado
//   node kit.mjs on  <módulo…>      node kit.mjs off <módulo…>     (o "todo")
//   node kit.mjs perfil minimo|normal|completo
//   node kit.mjs proyecto [ruta]    (deja ROADMAP, planes, aprendizajes, avance y CLAUDE.md de plantilla)
//   node kit.mjs desinstalar
//
// Nada se borra: lo apagado se guarda en ~/.claude/kit/apagado y desinstalar deja un
// respaldo en ~/.claude/kit-respaldo-<fecha>.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CLAUDE = path.join(os.homedir(), ".claude");
const KIT = path.join(CLAUDE, "kit");
const AQUI = path.dirname(fileURLToPath(import.meta.url));
const APAGADO = path.join(KIT, "apagado");
const F = {
  estado: path.join(KIT, "estado.json"),
  propios: path.join(KIT, "propios.json"),
  settings: path.join(CLAUDE, "settings.json"),
  claudeMd: path.join(CLAUDE, "CLAUDE.md"),
  skillKit: path.join(CLAUDE, "skills", "kit"),
};
const INI = "<!-- kit:inicio · lo escribe kit.mjs: no edites entre estas marcas -->";
const FIN = "<!-- kit:fin -->";
const AGENTES = ["arquitecto", "desarrollador", "revisor-seguridad", "revisor-rendimiento", "disenador-ux", "qa", "mejora-continua", "estado"];
const MATCHER =
  "Bash|PowerShell|Read|Grep|Write|Edit|MultiEdit|NotebookEdit|mcp__computer-use__.*|mcp__remote-devices__computer.*|enable__mcp__remote-devices__computer";
const COMANDO_HOOK = `node "${path.join(KIT, "hooks", "guardas.mjs").replace(/\\/g, "/")}"`;
const MARCA_HOOK = "/.claude/kit/hooks/";

const MODULOS = {
  reglas: { tipo: "regla", archivo: "reglas.md", desc: "Reglas de trabajo (CLAUDE.md global): modo rápido, secretos, seguridad, git, tokens" },
  estilo: { tipo: "regla", archivo: "estilo.md", desc: "Respuestas cortas y directas (menos tokens de salida)" },
  secretos: { tipo: "guarda", desc: "Guarda: no deja imprimir .env, llaves, cookies ni configs con claves" },
  destructivos: { tipo: "guarda", desc: "Guarda: pide confirmación ante force-push, reset --hard, rm -r, DROP, curl|sh…" },
  "simular-entrada": { tipo: "guarda", desc: "Guarda: bloquea simular teclado/mouse y computer use" },
  agentes: { tipo: "agentes", desc: "8 agentes: arquitecto, desarrollador, 3 revisores, qa, mejora-continua, estado" },
  ciclo: { tipo: "skill", skill: "ciclo-de-desarrollo", desc: "Skill /ciclo-de-desarrollo: plan → código → revisión → QA → aprendizaje (con /loop)" },
  verificar: { tipo: "skill", skill: "verificar-antes-de-suponer", desc: "Skill: leer el dato en vez de deducirlo; medir antes de iterar" },
  bugs: { tipo: "skill", skill: "arreglar-un-bug", desc: "Skill: test que falla → arreglo → regresión" },
  borrado: { tipo: "skill", skill: "borrado-seguro", desc: "Skill: papelera, re-chequeo, freno y dry-run en todo borrado" },
};
const PERFILES = {
  minimo: ["reglas", "secretos", "destructivos"],
  normal: ["reglas", "estilo", "secretos", "destructivos", "verificar", "bugs", "borrado"],
  completo: Object.keys(MODULOS),
};

// ---------- utilidades ----------
const existe = (p) => fs.existsSync(p);
const leerJson = (p, def) => (existe(p) ? JSON.parse(fs.readFileSync(p, "utf8")) : def);
const escribirJson = (p, v) => {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(v, null, 2) + "\n");
};
const sello = () => new Date().toISOString().replace(/[-:]/g, "").replace("T", "-").slice(0, 15);
function mover(de, a) {
  fs.mkdirSync(path.dirname(a), { recursive: true });
  try {
    fs.renameSync(de, a);
  } catch {
    fs.cpSync(de, a, { recursive: true });
    fs.rmSync(de, { recursive: true, force: true });
  }
}
function fallar(msg) {
  console.error(`✗ ${msg}`);
  process.exit(1);
}

// Cada pieza de un módulo: dónde vive prendida, dónde apagada y su original.
function piezas(nombre) {
  const m = MODULOS[nombre];
  if (m.tipo === "agentes") {
    return AGENTES.map((a) => ({
      id: `agents/${a}.md`,
      activo: path.join(CLAUDE, "agents", `${a}.md`),
      apagado: path.join(APAGADO, "agents", `${a}.md`),
      origen: path.join(KIT, "agentes", `${a}.md`),
    }));
  }
  if (m.tipo === "skill") {
    return [{
      id: `skills/${m.skill}`,
      activo: path.join(CLAUDE, "skills", m.skill),
      apagado: path.join(APAGADO, "skills", m.skill),
      origen: path.join(KIT, "skills", m.skill),
    }];
  }
  return [];
}

// ---------- settings.json (solo la entrada del hook del kit) ----------
function editarSettings(fn) {
  let s = {};
  if (existe(F.settings)) {
    try {
      s = JSON.parse(fs.readFileSync(F.settings, "utf8"));
    } catch {
      fallar(`${F.settings} no es JSON válido: no lo toco. Arreglalo y volvé a correr.`);
    }
    // El primero guarda cómo estaba antes del kit; los siguientes pisan uno solo.
    const resp = existe(`${F.settings}.antes-del-kit`) ? `${F.settings}.respaldo-kit` : `${F.settings}.antes-del-kit`;
    fs.copyFileSync(F.settings, resp);
    console.log(`  respaldo de settings.json → ${resp}`);
  }
  fn(s);
  escribirJson(F.settings, s);
}
const sinHookDelKit = (lista = []) => lista.filter((e) => !JSON.stringify(e).replace(/\\\\/g, "/").includes(MARCA_HOOK));

function registrarHook() {
  editarSettings((s) => {
    s.hooks ??= {};
    s.hooks.PreToolUse = sinHookDelKit(s.hooks.PreToolUse);
    s.hooks.PreToolUse.push({ matcher: MATCHER, hooks: [{ type: "command", command: COMANDO_HOOK, timeout: 10 }] });
  });
}
function quitarHook() {
  if (!existe(F.settings)) return;
  editarSettings((s) => {
    if (!s.hooks?.PreToolUse) return;
    s.hooks.PreToolUse = sinHookDelKit(s.hooks.PreToolUse);
    if (!s.hooks.PreToolUse.length) delete s.hooks.PreToolUse;
    if (!Object.keys(s.hooks).length) delete s.hooks;
  });
}

// ---------- CLAUDE.md global (solo el bloque entre marcas) ----------
function escribirBloque(texto) {
  let md = existe(F.claudeMd) ? fs.readFileSync(F.claudeMd, "utf8") : "";
  const i = md.indexOf(INI);
  const j = md.indexOf(FIN);
  if (i !== -1 && j !== -1) md = (md.slice(0, i).trimEnd() + "\n" + md.slice(j + FIN.length).trimStart()).trim();
  if (texto) md = (md ? md.trimEnd() + "\n\n" : "") + `${INI}\n${texto.trim()}\n${FIN}\n`;
  fs.mkdirSync(CLAUDE, { recursive: true });
  fs.writeFileSync(F.claudeMd, md ? md.trimEnd() + "\n" : "");
}

// ---------- aplicar el estado ----------
function aplicar(estado) {
  const propios = new Set(leerJson(F.propios, []));
  for (const nombre of Object.keys(MODULOS)) {
    for (const p of piezas(nombre)) {
      if (!propios.has(p.id)) continue;
      if (estado[nombre]) {
        if (existe(p.activo)) continue;
        if (existe(p.apagado)) mover(p.apagado, p.activo);
        else fs.cpSync(p.origen, p.activo, { recursive: true });
      } else if (existe(p.activo)) {
        if (existe(p.apagado)) fs.rmSync(p.apagado, { recursive: true, force: true }); // copia vieja del propio kit
        mover(p.activo, p.apagado);
      }
    }
  }
  const reglas = Object.entries(MODULOS)
    .filter(([n, m]) => m.tipo === "regla" && estado[n])
    .map(([, m]) => fs.readFileSync(path.join(KIT, "reglas", m.archivo), "utf8").trim());
  escribirBloque(reglas.join("\n\n"));
  escribirJson(F.estado, estado);
}

// ---------- comandos ----------
function instalar(perfil = "completo") {
  const [mayor] = process.versions.node.split(".").map(Number);
  if (mayor < 18) fallar(`Hace falta Node 18 o más nuevo (tenés ${process.versions.node}).`);
  if (!PERFILES[perfil]) fallar(`Perfil desconocido: ${perfil}. Opciones: ${Object.keys(PERFILES).join(", ")}`);

  console.log(`Instalando el kit en ${KIT}`);
  fs.mkdirSync(KIT, { recursive: true });
  if (path.resolve(AQUI) !== path.resolve(KIT)) {
    for (const d of ["hooks", "reglas", "agentes", "skills", "plantilla-proyecto", "pruebas"]) {
      fs.rmSync(path.join(KIT, d), { recursive: true, force: true }); // originales del kit: se reemplazan
      fs.cpSync(path.join(AQUI, d), path.join(KIT, d), { recursive: true });
    }
    for (const f of ["kit.mjs", "README.md"]) fs.copyFileSync(path.join(AQUI, f), path.join(KIT, f));
  }

  // Qué piezas son del kit. Si ya tenés un agente o skill propio con el mismo nombre, no se toca.
  const propios = new Set(leerJson(F.propios, []));
  const conflictos = [];
  for (const n of Object.keys(MODULOS)) {
    for (const p of piezas(n)) {
      if (propios.has(p.id)) continue;
      if (existe(p.activo)) conflictos.push(p.id);
      else propios.add(p.id);
    }
  }
  escribirJson(F.propios, [...propios]);

  const estado = existe(F.estado)
    ? leerJson(F.estado, {})
    : Object.fromEntries(Object.keys(MODULOS).map((n) => [n, PERFILES[perfil].includes(n)]));
  for (const n of Object.keys(MODULOS)) estado[n] ??= PERFILES[perfil].includes(n);

  registrarHook();
  escribirSkillKit();
  aplicar(estado);

  console.log("✓ Kit instalado.");
  if (conflictos.length) console.log(`  Ya tenías propios (no los toqué, el kit no los maneja): ${conflictos.join(", ")}`);
  mostrarEstado();
  console.log("\nAbrí una sesión nueva de Claude Code para que tome reglas, agentes y skills.");
}

function escribirSkillKit() {
  const archivo = path.join(F.skillKit, "SKILL.md");
  if (existe(archivo) && !fs.readFileSync(archivo, "utf8").includes("kit.mjs")) {
    console.log("  Ya tenés un skill llamado 'kit': no lo toco. Usá node kit.mjs desde la terminal.");
    return;
  }
  const kitMjs = path.join(KIT, "kit.mjs").replace(/\\/g, "/");
  fs.mkdirSync(F.skillKit, { recursive: true });
  fs.writeFileSync(
    archivo,
    `---
name: kit
description: Muestra, prende o apaga los módulos del kit de desarrollo (guardas, reglas, agentes, skills). Solo lo usa el usuario escribiendo /kit.
disable-model-invocation: true
argument-hint: "[estado | on <módulo…> | off <módulo…> | perfil minimo|normal|completo | proyecto <ruta>]"
---

Corré este comando en la terminal y mostrá la salida tal cual, sin agregar nada:

\`\`\`
node "${kitMjs}" $ARGUMENTS
\`\`\`

Si no vinieron argumentos, usá \`estado\`. Si la guarda del kit pide confirmación, es lo esperado: el usuario la aprueba.
`,
  );
}

function mostrarEstado() {
  if (!existe(F.estado)) fallar("El kit no está instalado. Corré: node kit.mjs instalar");
  const estado = leerJson(F.estado, {});
  const off = String(process.env.KIT_OFF || "").toLowerCase().split(/[,\s]+/).filter(Boolean);
  console.log("\nMódulo            Estado   Qué hace");
  for (const [n, m] of Object.entries(MODULOS)) {
    let marca = estado[n] ? "ON " : "off";
    if (m.tipo === "guarda" && estado[n] && (off.includes(n) || off.includes("todo"))) marca = "off*";
    console.log(`${n.padEnd(17)} ${marca.padEnd(8)} ${m.desc}`);
  }
  const perfil = Object.entries(PERFILES).find(([, l]) => Object.keys(MODULOS).every((n) => !!estado[n] === l.includes(n)));
  console.log(`\nPerfil: ${perfil ? perfil[0] : "a medida"}${off.length ? `   ·   *apagado en esta sesión por KIT_OFF=${off.join(",")}` : ""}`);
  console.log("Las guardas cambian al instante; reglas, agentes y skills, desde la próxima sesión de Claude Code.");
}

function cambiar(prender, nombres) {
  if (!existe(F.estado)) fallar("El kit no está instalado. Corré: node kit.mjs instalar");
  if (!nombres.length) fallar(`Decí qué módulo. Opciones: ${Object.keys(MODULOS).join(", ")} (o "todo")`);
  const estado = leerJson(F.estado, {});
  const lista = nombres.some((n) => ["todo", "todos"].includes(n)) ? Object.keys(MODULOS) : nombres;
  for (const n of lista) {
    if (!MODULOS[n]) fallar(`No existe el módulo "${n}". Opciones: ${Object.keys(MODULOS).join(", ")}`);
    estado[n] = prender;
  }
  if (prender && estado.ciclo && !estado.agentes) {
    estado.agentes = true;
    console.log("  (El ciclo usa los agentes: prendí también 'agentes'.)");
  }
  if (!prender && !estado.agentes && estado.ciclo) {
    estado.ciclo = false;
    console.log("  (Sin agentes el ciclo no funciona: apagué también 'ciclo'.)");
  }
  aplicar(estado);
  mostrarEstado();
}

function perfil(nombre) {
  if (!PERFILES[nombre]) fallar(`Perfiles: ${Object.keys(PERFILES).join(", ")}`);
  if (!existe(F.estado)) fallar("El kit no está instalado. Corré: node kit.mjs instalar");
  aplicar(Object.fromEntries(Object.keys(MODULOS).map((n) => [n, PERFILES[nombre].includes(n)])));
  mostrarEstado();
}

function proyecto(ruta = ".") {
  const destino = path.resolve(ruta);
  const plantilla = existe(path.join(KIT, "plantilla-proyecto")) ? path.join(KIT, "plantilla-proyecto") : path.join(AQUI, "plantilla-proyecto");
  if (!existe(destino)) fallar(`No existe la carpeta ${destino}`);
  console.log(`Plantilla de proyecto en ${destino}`);
  const recorrer = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => (d.isDirectory() ? recorrer(path.join(dir, d.name)) : [path.join(dir, d.name)]));
  for (const origen of recorrer(plantilla)) {
    const rel = path.relative(plantilla, origen);
    const a = path.join(destino, rel);
    if (existe(a)) {
      console.log(`  = ${rel} (ya existe, no lo toco)`);
      continue;
    }
    fs.mkdirSync(path.dirname(a), { recursive: true });
    fs.copyFileSync(origen, a);
    console.log(`  + ${rel}`);
  }
  const gi = path.join(destino, ".gitignore");
  if (!existe(gi) || !/^\.env/m.test(fs.readFileSync(gi, "utf8"))) {
    console.log("  ! Ojo: .gitignore no excluye .env*. Agregá la línea:  .env*  (y  !.env.example)");
  }
  console.log("Completá el CLAUDE.md del proyecto y las filas de docs/ROADMAP.md. Después: /ciclo-de-desarrollo");
}

function desinstalar() {
  const resp = path.join(CLAUDE, `kit-respaldo-${sello()}`);
  console.log(`Desinstalando. Lo del kit queda en ${resp}`);
  quitarHook();
  escribirBloque("");
  const propios = leerJson(F.propios, []);
  for (const n of Object.keys(MODULOS)) {
    for (const p of piezas(n)) {
      if (propios.includes(p.id) && existe(p.activo)) mover(p.activo, path.join(resp, "activos", p.id));
    }
  }
  if (existe(F.skillKit)) mover(F.skillKit, path.join(resp, "activos", "skills", "kit"));
  if (existe(KIT)) mover(KIT, path.join(resp, "kit"));
  console.log("✓ Kit desinstalado: sin hook, sin bloque en CLAUDE.md, sin agentes ni skills del kit.");
  console.log("  Si querés recuperar algo (por ejemplo un agente que editaste), está en el respaldo.");
}

// ---------- entrada ----------
const [cmd = "estado", ...args] = process.argv.slice(2);
const acciones = {
  instalar: () => instalar(args[0]),
  estado: mostrarEstado,
  on: () => cambiar(true, args),
  off: () => cambiar(false, args),
  perfil: () => perfil(args[0]),
  proyecto: () => proyecto(args[0]),
  desinstalar,
};
if (!acciones[cmd]) {
  console.log("Uso: node kit.mjs instalar [minimo|normal|completo] | estado | on <módulo…> | off <módulo…> | perfil <nombre> | proyecto [ruta] | desinstalar");
  process.exit(1);
}
acciones[cmd]();
