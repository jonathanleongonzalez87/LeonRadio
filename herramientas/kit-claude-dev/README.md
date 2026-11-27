# Kit de desarrollo para Claude Code

Reglas, guardas de seguridad, agentes revisores y un ciclo de mejora continua para desarrollar apps con Claude Code **sin perder tiempo ni quemar tokens**. Cada módulo se prende y se apaga con un comando.

Sale de varios meses de uso real. Cada regla tiene detrás un incidente que costó horas o una clave filtrada.

---

## Qué trae

| Módulo | Qué hace | Costo |
|---|---|---|
| `reglas` | Bloque en tu `~/.claude/CLAUDE.md`: modo rápido, secretos, seguridad del código, git, borrados, tokens, mejora continua | ~2.000 tokens por sesión |
| `estilo` | Respuestas de 1 a 3 oraciones, sin relleno | ~150 tokens; **ahorra** salida |
| `secretos` | Guarda: Claude no puede imprimir `.env`, llaves, cookies ni archivos de config con claves | ~50 ms por herramienta |
| `destructivos` | Guarda: **te pide confirmación** antes de force-push, push a main, `reset --hard`, `rm -r`, `DROP`, `curl \| sh`… Niega `--no-verify` | (mismo proceso) |
| `simular-entrada` | Guarda: prohíbe simular teclado/mouse y computer use | (mismo proceso) |
| `agentes` | 8 agentes: `arquitecto`, `desarrollador`, `revisor-seguridad`, `revisor-rendimiento`, `disenador-ux`, `qa`, `mejora-continua`, `estado` | ~400 tokens (descripciones); se usan solo cuando hacen falta |
| `ciclo` | Skill `/ciclo-de-desarrollo`: plan → código → revisión en paralelo → arreglos → QA → aprendizaje → % de avance. Funciona con `/loop` | ~100 tokens |
| `verificar` | Skill: leer el dato en vez de deducirlo, medir antes de iterar | ~60 tokens |
| `bugs` | Skill: test que falla → arreglo → regresión | ~60 tokens |
| `borrado` | Skill: papelera, re-chequeo, freno y dry-run en todo borrado | ~60 tokens |

Las tres guardas corren en **un solo** hook de Node. Los skills y agentes cargan solo su descripción; el contenido entero se lee cuando se usan.

## Requisitos
- Claude Code (terminal, VS Code o app de escritorio).
- Node.js 18 o más nuevo (`node -v`).
- Windows, macOS o Linux.

## Instalar (2 minutos)

1. Descomprimí la carpeta donde quieras.
2. En una terminal, dentro de la carpeta:
   ```
   node kit.mjs instalar
   ```
   Por defecto instala todo (`completo`). Para algo más liviano: `node kit.mjs instalar normal` o `node kit.mjs instalar minimo`.
3. Comprobá las guardas: `node pruebas/probar-guardas.mjs` (tienen que pasar las 41).
4. **Abrí una sesión nueva** de Claude Code.

Qué toca el instalador, y nada más:
- copia el kit a `~/.claude/kit/`;
- agrega **una** entrada de hook en `~/.claude/settings.json` (antes deja un respaldo `settings.json.antes-del-kit`);
- agrega un bloque entre marcas al final de `~/.claude/CLAUDE.md` (lo tuyo queda igual);
- copia agentes a `~/.claude/agents/` y skills a `~/.claude/skills/`. **Si ya tenés uno con el mismo nombre, no lo toca** y te avisa.

## Prender y apagar

Desde Claude Code (lo escribís vos; Claude no puede llamarlo solo):
```
/kit                      → muestra qué está prendido
/kit off agentes ciclo    → apaga módulos
/kit on estilo            → prende módulos
/kit perfil minimo        → minimo | normal | completo
```

Desde la terminal, lo mismo:
```
node ~/.claude/kit/kit.mjs estado
node ~/.claude/kit/kit.mjs off destructivos
```
(En PowerShell: `node "$HOME/.claude/kit/kit.mjs" estado`.)

**Solo por una sesión**, sin cambiar nada guardado: abrí Claude con la variable `KIT_OFF`.
```
KIT_OFF=destructivos claude               # bash / macOS
$env:KIT_OFF="destructivos"; claude        # PowerShell
KIT_OFF=todo claude                        # todas las guardas apagadas
```
`KIT_OFF` solo apaga guardas: `secretos`, `destructivos` y `simular-entrada`.

**Cuándo aplica cada cambio**: las guardas cambian al instante. Reglas, agentes y skills, desde la próxima sesión.

**Perfiles**
| Perfil | Módulos |
|---|---|
| `minimo` | reglas, secretos, destructivos |
| `normal` | minimo + estilo, verificar, bugs, borrado |
| `completo` | todo (+ agentes, ciclo, simular-entrada) |

Apagar no borra nada: los agentes y skills apagados se guardan en `~/.claude/kit/apagado/` con tus ediciones, y vuelven tal cual al prenderlos.

## Cómo se usa en el día a día

No hay que hacer nada especial: las reglas eligen el camino según el **tamaño del cambio**.

| Pedís… | Claude hace… |
|---|---|
| Un cambio chico ("cambiá este texto", "arreglá este botón") | Lo hace directo, con typecheck, lint y test. Sin agentes. |
| Una tarea mediana ("agregá filtros a la lista") | Implementa, **una** revisión del área que más pesa (siempre seguridad si toca claves, login, pagos o datos personales), una ronda de arreglos. |
| Una tarea grande, o "corré un ciclo" | `/ciclo-de-desarrollo` con los agentes. |

Los revisores corren en `sonnet` y en paralelo, y solo frenan por `BLOQUEANTE` o `IMPORTANTE`. Lo `MENOR` queda anotado como deuda.

### Proyecto nuevo con ROADMAP y % de avance
```
node ~/.claude/kit/kit.mjs proyecto ruta/de/tu/app
```
Agrega, sin pisar nada que ya exista: un `CLAUDE.md` de plantilla, `docs/ROADMAP.md` (tier list S/A/B/C con puntos y estados), `docs/aprendizajes.md`, `docs/planes/` y `scripts/avance.mjs`. Completá el CLAUDE.md y las filas del ROADMAP, y después:
```
/ciclo-de-desarrollo            → una tarea completa
/loop /ciclo-de-desarrollo      → una tarea tras otra, hasta que algo te necesite
```
El loop se frena solo si: falta algo tuyo (una clave, una decisión), una tarea falla 3 rondas, o no quedan tareas desbloqueadas. `node scripts/avance.mjs` da el % por tier y el tier del producto (Prototipo → Alfa → MVP → Sólido → Completo).

### Mejora continua
Cuando algo sale mal y se repetiría, `mejora-continua` lo convierte en una regla con su **Por qué** en el `CLAUDE.md` o en un skill **del proyecto**, y lo registra en `docs/aprendizajes.md`. Cada 5 ciclos hace una retro con números. Corre al cerrar tareas grandes o después de un incidente, no en cada cambio. Nunca afloja reglas de seguridad sin tu OK, ni edita los agentes globales: si quiere cambiarlos, te lo propone.

## Si una guarda te frena

- **"Bloqueado"** (`secretos`, `simular-entrada`, `--no-verify`): Claude tiene que buscar otra forma, y el mensaje le dice cuál (por ejemplo, pedir un campo del JSON en vez de imprimir el archivo entero).
- **Pregunta de confirmación** (`destructivos`): decidís vos en el momento. Aprobar es normal si sabés lo que se borra.
- **Si te estorba en un proyecto**: `KIT_OFF=<guarda>` para esa sesión, o `/kit off <guarda>`.
- Si Claude intenta apagar el kit o editar sus archivos, **siempre** te pide confirmación. Esa protección no se apaga.
- Si alguna vez una clave igual aparece en pantalla, rotala.

## Personalizar
- **Tus reglas**: escribilas fuera del bloque `kit:inicio … kit:fin` de `~/.claude/CLAUDE.md`. Lo de adentro lo reescribe el kit.
- **Reglas de un proyecto**: en el `CLAUDE.md` del proyecto, sección "Reglas aprendidas".
- **Agentes**: editá `~/.claude/agents/<agente>.md`. Tus cambios sobreviven a apagar/prender y a reinstalar. Los originales quedan en `~/.claude/kit/agentes/`.
- **Carpetas que se pueden borrar sin confirmación**: la lista `REGENERABLES` en `~/.claude/kit/hooks/destructivos.mjs`.

## Actualizar y desinstalar
- **Actualizar**: descomprimí la versión nueva y corré `node kit.mjs instalar`. Respeta lo que tenés prendido y apagado, y tus agentes editados.
- **Desinstalar**:
  ```
  node ~/.claude/kit/kit.mjs desinstalar
  ```
  Saca el hook, el bloque del CLAUDE.md, los agentes y los skills del kit. Todo queda en `~/.claude/kit-respaldo-<fecha>/`, por si querés recuperar algo.

## Estructura del paquete
```
kit.mjs                 instalar / on / off / perfil / proyecto / desinstalar
reglas/                 reglas.md (el CLAUDE.md del kit) y estilo.md
hooks/                  guardas.mjs + secretos, destructivos, simular-entrada
agentes/                los 8 agentes
skills/                 ciclo-de-desarrollo, verificar-antes-de-suponer, arreglar-un-bug, borrado-seguro
plantilla-proyecto/     CLAUDE.md, docs/ROADMAP.md, docs/aprendizajes.md, docs/planes/, scripts/avance.mjs
pruebas/                probar-guardas.mjs
```
