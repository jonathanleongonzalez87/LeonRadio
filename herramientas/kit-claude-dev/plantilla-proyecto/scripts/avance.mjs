#!/usr/bin/env node
/**
 * Avance del proyecto según la tier list de docs/ROADMAP.md.
 * Imprime el resumen y reescribe docs/ESTADO.md. Si existe la variable KIT_COPIA_ESTADO
 * (una carpeta, por ejemplo una del Drive), deja también una copia ahí.
 * Uso: node scripts/avance.mjs
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PESO = { S: 45, A: 30, B: 15, C: 10 };
const NOMBRE = { S: "Núcleo", A: "Muy importante", B: "Pulido", C: "Extras" };
const VALOR = { pendiente: 0, "en curso": 0.3, hecho: 0.8, verificado: 1 };
const COPIA = process.env.KIT_COPIA_ESTADO;
const proyecto = path.basename(raiz);

const tareas = readFileSync(path.join(raiz, "docs", "ROADMAP.md"), "utf8")
  .split(/\r?\n/)
  .filter((l) => /^\|\s*[SABC]\d+\s*\|/.test(l))
  .map((l) => {
    const [id, tier, funcion, puntos, estado, depende = "—"] = l.split("|").slice(1).map((c) => c.trim());
    return { id, tier, funcion, puntos: Number(puntos), estado: (estado || "").toLowerCase(), depende: depende === "—" || depende === "-" || !depende ? [] : depende.split(/,\s*/) };
  });
if (!tareas.length) {
  console.error("docs/ROADMAP.md no tiene filas de tareas (| S1 | S | … |).");
  process.exit(1);
}
const malas = tareas.filter((t) => !(t.tier in PESO) || !(t.puntos > 0) || !(t.estado in VALOR) || t.id[0] !== t.tier);
if (malas.length) {
  console.error(`Filas inválidas en docs/ROADMAP.md: ${malas.map((t) => t.id).join(", ")} (tier, puntos o estado)`);
  process.exit(1);
}

const tiers = Object.keys(PESO).filter((k) => tareas.some((t) => t.tier === k));
const avance = Object.fromEntries(
  tiers.map((k) => {
    const de = tareas.filter((t) => t.tier === k);
    const total = de.reduce((s, t) => s + t.puntos, 0);
    return [k, { pct: (100 * de.reduce((s, t) => s + t.puntos * VALOR[t.estado], 0)) / total, verificadas: de.filter((t) => t.estado === "verificado").length, n: de.length }];
  }),
);
const global = tiers.reduce((s, k) => s + PESO[k] * avance[k].pct, 0) / tiers.reduce((s, k) => s + PESO[k], 0);
const completo = (k) => !avance[k] || avance[k].pct >= 100;
const tierProducto =
  completo("S") && completo("A") && completo("B") ? "Tier S · Completo"
  : completo("S") && completo("A") ? "Tier A · Producto sólido"
  : completo("S") ? "Tier B · MVP usable"
  : (avance.S?.pct ?? 0) >= 50 ? "Tier C · Alfa"
  : "Tier D · Prototipo";

const listas = new Set(tareas.filter((t) => t.estado === "hecho" || t.estado === "verificado").map((t) => t.id));
const siguientes = [
  ...tareas.filter((t) => t.estado === "en curso"),
  ...tareas.filter((t) => t.estado === "pendiente" && t.depende.every((d) => listas.has(d))),
].slice(0, 3);
const barra = (pct) => "█".repeat(Math.round(pct / 5)) + "░".repeat(20 - Math.round(pct / 5));
const fecha = new Date().toLocaleString("es", { dateStyle: "medium", timeStyle: "short" });

const md = [
  `# Estado de ${proyecto}`,
  "",
  `_Actualizado: ${fecha} · lo genera \`node scripts/avance.mjs\` desde [ROADMAP.md](ROADMAP.md)_`,
  "",
  `## Avance global: ${global.toFixed(0)}% · ${tierProducto}`,
  "",
  "| Tier | Qué es | Peso | Avance | | Verificadas |",
  "|---|---|---|---|---|---|",
  ...tiers.map((k) => `| ${k} | ${NOMBRE[k]} | ${PESO[k]}% | ${avance[k].pct.toFixed(0)}% | \`${barra(avance[k].pct)}\` | ${avance[k].verificadas}/${avance[k].n} |`),
  "",
  "## Siguientes tareas",
  "",
  ...(siguientes.length ? siguientes.map((t, i) => `${i + 1}. **${t.id}** (${t.estado}) — ${t.funcion}`) : ["Ninguna desbloqueada."]),
  "",
].join("\n");
writeFileSync(path.join(raiz, "docs", "ESTADO.md"), md);

console.log(`${proyecto}: ${global.toFixed(0)}% · ${tierProducto}`);
console.log(tiers.map((k) => `${k} ${avance[k].pct.toFixed(0)}%`).join(" · "));
console.log(`Sigue: ${siguientes.map((t) => t.id).join(", ") || "nada desbloqueado"}`);
if (COPIA) {
  try {
    if (existsSync(path.parse(path.resolve(COPIA)).root)) {
      mkdirSync(COPIA, { recursive: true });
      writeFileSync(path.join(COPIA, "ESTADO.md"), md);
      console.log(`Copia en ${path.join(COPIA, "ESTADO.md")}`);
    } else console.log(`(La unidad de ${COPIA} no está conectada: quedó solo en docs/ESTADO.md)`);
  } catch (e) {
    console.log(`(No pude copiar el estado: ${e instanceof Error ? e.message : e})`);
  }
}
