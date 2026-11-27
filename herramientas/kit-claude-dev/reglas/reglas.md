# Kit de desarrollo — reglas de trabajo

Cada regla viene de un incidente real. Si una te parece equivocada en un caso, decilo; no la ignores en silencio.

## El tamaño del cambio decide el camino (modo rápido)
- **Cambio chico** (un texto, un campo, un botón, un arreglo puntual): directo, sin agentes. Rama propia si hay git; pasan `typecheck`, `lint` y `test` (los que existan) y listo.
- **Tarea mediana**: implementar → **una** revisión con el agente del área que más pesa (`revisor-seguridad`, `revisor-rendimiento` o `disenador-ux`) → **una** ronda de arreglos → cerrar. Si toca claves, login, permisos, pagos o datos personales, la revisión es siempre `revisor-seguridad`.
- **Tarea grande** (varias pantallas, integración nueva, claves o pagos) o cuando el usuario pida "ciclo": skill `ciclo-de-desarrollo`.
- Los revisores frenan solo con `BLOQUEANTE` e `IMPORTANTE`. Lo `MENOR` va a la deuda y no frena.
- Arrancá liviano y escalá solo si el cambio lo pide. No reabras el ciclo completo por un agregado chico a algo ya hecho.
- **Por qué:** cada agente arranca de cero y relee todo. Correr el ciclo completo para todo multiplicó horas y tokens sin cambiar el resultado.

## Secretos (regla dura)
- Una clave que aparece en el chat queda quemada: hay que rotarla.
- **Nunca imprimir** el contenido de `.env*`, llaves (`.pem`, `.key`), cookies, `credentials*` ni de objetos de configuración completos. Antes de correr algo que imprime, preguntate **qué más sale en esa salida**.
- **Pedir el campo, no el objeto**: `(Get-Content x.json -Raw | ConvertFrom-Json).campo`, nunca el objeto entero con `ConvertTo-Json` o `Format-List`.
- **Para saber si una clave existe**: `Test-Path`, `Select-String -Quiet`, `grep -q`. Nunca imprimiendo la línea.
- De listados de variables (`vercel env ls`, paneles, CLIs) se imprime solo la columna de nombres. **Por qué:** una columna de valor mostró el inicio de un token y hubo que rotarlo.
- Las claves las carga el usuario (`.env.local`, ajustes de la app, variables "Sensitive" del hosting). Si hace falta el NOMBRE de una variable, leé `.env.example`. No le pidas al usuario que pegue una clave en el chat.
- Si una clave igual termina en pantalla: decilo de una, sin adornos, y pedí que se rote.

## Seguridad del código (siempre, no solo en revisión)
- Procesos: `spawn`/`execFile` con argumentos en array. Nunca `exec` ni `shell: true` con texto que venga de afuera.
- Rutas que llegan del navegador o de un archivo: `path.resolve` y validar contra las carpetas permitidas (`..`, unidades, rutas UNC).
- APIs: autenticación en cada ruta, chequeo de `Origin` (CSRF), límite de tamaño de lo que reciben, errores sin stack trace ni claves.
- Apps locales escuchan solo en `127.0.0.1`.
- Secretos nunca en el cliente (ojo con los prefijos públicos tipo `NEXT_PUBLIC_`), ni en logs, ni en errores, ni en el repo. `.env*` en `.gitignore`.
- LLM: el texto de terceros (mensajes de clientes, páginas, correos) va como dato delimitado, nunca como instrucción. La respuesta se valida con un esquema y nunca se ejecuta.
- Datos personales mínimos, nunca en logs ni en el repo. Los tests usan datos inventados.
- Dependencias nuevas, justificadas y mantenidas. `npm audit --omit=dev` sin altas ni críticas; lo que no se puede arreglar se anota con su porqué y la versión que lo resuelve.

## Archivos del usuario y borrados
- Los archivos del usuario (proyectos, fotos, documentos originales) se leen, no se pisan: la app crea archivos nuevos.
- Nada se borra de una: a una papelera visible, con log. Todo borrado automático sigue el skill `borrado-seguro` (solo lo que la app creó, re-chequeo, freno, dry-run).

## Verificar antes de suponer (skill `verificar-antes-de-suponer`)
- Si el usuario nombró la fuente del dato, esa es la fuente. No escribas heurísticas para deducir algo que el usuario ya tiene clasificado.
- Límites, cuotas y formatos de terceros se confirman en la documentación o en datos reales, y quedan en el código con número y fecha.
- Antes de planear infraestructura, preguntá qué plan y qué hosting tiene el usuario de verdad: los gratuitos limitan crons, almacenamiento y uso comercial.
- "Debería funcionar" no es evidencia: pegá el comando y la salida, con números.
- Si el usuario corrige lo mismo dos veces, la que está mal es tu interpretación.

## Git
- Una rama por tarea (`feat/<id>-<slug>`, `fix/<slug>`). Commits chicos, conventional commits.
- Push de la rama apenas se commitea, si hay remoto: nada de trabajo acumulado sin subir.
- Nunca `--no-verify`: si un hook falla, se arregla lo que falla.
- Merge a `main` y deploy a producción: los decide el usuario, salvo que haya autorizado otra cosa en el CLAUDE.md del proyecto.
- Si la sesión puede cortarse por el límite de uso con trabajo sin commitear: `git commit -m "wip(<id>): ..."` y push antes de seguir.

## Tokens y tiempo
- No releas un archivo ya leído en la conversación salvo que haya cambiado. Leé solo lo necesario (`offset`/`limit`). Si sabés la ruta, `Read` directo.
- Agentes solo cuando valen la pena (cada uno re-lee todo). Revisores en paralelo, en **un solo mensaje**. A cada agente pasale rutas, ids y hallazgos concretos, nunca "lo de antes".
- Lo mínimo que resuelve el problema: sin abstracciones, helpers, validaciones ni features que no se pidieron. Tres líneas repetidas son mejor que una abstracción prematura.
- `Edit` parcial antes que `Write` sobre un archivo existente. Cambiá solo lo necesario.
- Nunca recorras `node_modules` ni carpetas de media enormes de forma recursiva.
- APIs pagas: los tests usan respuestas grabadas (`npm test` nunca gasta créditos) y lo generado se cachea por contenido + parámetros. Nunca se paga dos veces lo mismo.

## Guardas del kit
- Si una guarda bloquea o pide confirmación, no la rodees con otro comando: hacé lo que pide el mensaje.
- Nunca apagues un módulo del kit por tu cuenta: eso lo decide el usuario con `/kit`.
- Lo que necesita la pantalla real (una ventana del sistema, el navegador del usuario, el celular) va en **Pendiente del usuario**, con 1 a 3 pasos.

## Mejora continua
- Cuando algo salió mal o costó de más **y se repetiría**: una regla concreta y chequeable, con `**Por qué:** incidente (AAAA-MM-DD)`. Si fue un accidente único, no se escribe nada.
- Dónde va: de un área → skill del área en el proyecto (`.claude/skills/<area>/SKILL.md`); transversal del proyecto → `CLAUDE.md` del proyecto › "Reglas aprendidas"; de un rol → proponela para el agente. Registro en `docs/aprendizajes.md` si existe.
- Cada `CLAUDE.md` ≤ 150 líneas: lo obsoleto se borra. Las reglas de seguridad y secretos no se aflojan sin el OK del usuario.
