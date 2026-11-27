---
name: ciclo-de-desarrollo
description: Corre un ciclo completo sobre UNA tarea del docs/ROADMAP.md (plan, implementación, revisiones en paralelo, correcciones, QA, aprendizaje y medición del avance) con los agentes del kit. Usalo cuando el usuario pida "ciclo", "otro ciclo", "seguí con el roadmap", o con /loop /ciclo-de-desarrollo para iterar. Para cambios chicos o tareas medianas NO: ahí rige el modo rápido de las reglas del kit.
---

# Ciclo de desarrollo

Vos orquestás; los agentes (`arquitecto`, `desarrollador`, `revisor-seguridad`, `revisor-rendimiento`, `disenador-ux`, `qa`, `mejora-continua`) hacen el trabajo. Un ciclo = **una** tarea del ROADMAP, terminada y medida.

Si el proyecto no tiene `docs/ROADMAP.md`, ofrecé crearlo con `node ~/.claude/kit/kit.mjs proyecto .` (lo corre el usuario) o seguí con la tarea que nombró el usuario usando `docs/planes/<slug>.md`.

## 0. Elegir la tarea
1. Leé `docs/ROADMAP.md`.
2. Si hay una tarea `en curso`, se retoma esa. Si no, la primera `pendiente` en orden S → A → B → C cuyas dependencias estén en `hecho` o `verificado`. Si el usuario nombró una, va esa.
3. **¿De verdad es grande?** Si es un cambio chico o mediano, decilo y seguí en modo rápido; no gastes el ciclo.

Antes de arrancar:
- Si la tarea necesita algo del usuario que no está (material de muestra, una clave, una decisión), **frená y preguntá**. Si estás en /loop, terminá el loop. No inventes datos de prueba para esquivar el bloqueo.
- `git switch main && git pull && git switch -c feat/<ID>-<slug>`, o retomá la rama si existe.
- En el ROADMAP, pasá la tarea a `en curso` y hacé commit.

## 1. Plan → `arquitecto`
Pasale el id de la tarea. Devuelve `docs/planes/<ID>.md`.
- Si el plan dice **BLOQUEO**, frená y preguntá.
- Si propone partir la tarea, aplicá la partición en el ROADMAP, commit, y seguí con la primera parte.
- Si hay pantallas nuevas, pasale el plan a `disenador-ux` para que agregue la propuesta de pantalla **antes** de implementar.

## 2. Implementación → `desarrollador`
Pasale la ruta del plan. Cuando termine, commit (conventional, con el id) y push.

## 3. Revisión en paralelo (liviana)
Solo los revisores que la tarea necesita, todos en **un solo mensaje**:
- `revisor-seguridad`: si toca rutas, procesos, claves, auth, APIs, pagos o datos personales.
- `disenador-ux`: si hay texto o pantallas que ve el usuario.
- `revisor-rendimiento`: si procesa archivos grandes, llama APIs pagas, o carga listas o consultas grandes.

Si ninguno aplica, directo a QA. A cada revisor pasale la rama y la ruta del plan.

**Modelos**: `arquitecto` y `desarrollador` en `inherit`; revisores, `qa` y `mejora-continua` en `sonnet`. Si `Agent` no ofrece el tipo, lanzá un agente general con: "Sos el agente `<nombre>`; tu rol está en `~/.claude/agents/<nombre>.md`: leelo y seguilo", y pasale `model`.

## 4. Correcciones
- Juntá los `BLOQUEANTE` e `IMPORTANTE` de todos los revisores y pasáselos al `desarrollador` en **una sola ronda**. Los `MENOR` triviales van en la misma ronda; el resto, a "Deuda para los próximos ciclos" del plan.
- No hay segunda revisión salvo que haya habido un `BLOQUEANTE`: se relanza solo ese revisor, máximo 3 rondas.
- Si tras 3 rondas siguen los bloqueantes, frená y llevale al usuario el resumen y las opciones.

## 5. QA → `qa`
- `RECHAZADO`: volvé al paso 4 con las fallas (cuenta como ronda).
- `APROBADO — hecho` / `APROBADO — verificado`: pasá la tarea a ese estado en el ROADMAP y commit.
- Nunca marques `verificado` sin la evidencia de QA.

## 6. Aprendizaje → `mejora-continua`
Solo si hubo algo que aprender (bloqueantes, rechazo de QA, más de una ronda, correcciones del usuario). Pasale: tarea, hallazgos por revisor y severidad, rondas, veredicto y fallas de QA, correcciones del usuario. Commit: `docs: aprendizajes del ciclo <ID>`.

## 7. Medición
Corré `node scripts/avance.mjs` (actualiza `docs/ESTADO.md`). Commit: `docs: estado tras <ID>`. Nunca subas el avance a mano.

## 8. Cierre
- La rama ya está subida (push tras cada commit). Abrí el PR con `gh pr create` si hay GitHub.
- **Merge a `main`**: lo decide el usuario, salvo autorización escrita en el CLAUDE.md del proyecto.
- **Mensaje final** (corto): la línea de avance del script, una línea de qué se hizo, y lo que le toca al usuario.

## Con /loop
- Cada vuelta es un ciclo completo; entre ciclos no hace falta esperar.
- Terminá el loop (no programes otra vuelta) si: hay un bloqueo del usuario, 3 rondas fallidas, no quedan tareas desbloqueadas, o el usuario pidió parar.

## Reglas del orquestador
- No implementás vos: delegás. Sí podés leer, correr comandos de verificación y hacer commits.
- Los agentes no se ven entre sí: a cada uno pasale lo que necesita (rutas absolutas, ids, hallazgos), no "lo de antes".
- Si la tarea toca dos repos, a cada agente pasale las dos rutas absolutas y qué vive en cada una (plan y ROADMAP en uno, código y PR en el otro). Misma rama en los dos.
- Si la sesión se corta por el límite de uso con trabajo sin commitear: `git commit -m "wip(<ID>): ..."` y push en cada repo tocado antes de retomar; después se retoma al agente cortado con `SendMessage`.
