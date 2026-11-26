# <Nombre del proyecto>

<Qué es, para quién y qué problema resuelve, en 2-3 líneas.>

El plan y el avance viven en [docs/ROADMAP.md](docs/ROADMAP.md) (tier list) y [docs/ESTADO.md](docs/ESTADO.md) (lo genera `node scripts/avance.mjs`).

## Stack
- <Lenguaje, framework, base de datos, hosting y su PLAN real (gratuito/pago) con sus límites.>

## Comandos
- `npm run dev`: <dónde corre>
- `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`: los cuatro pasan antes de cada merge.
- `node scripts/avance.mjs`: % de avance según el ROADMAP.

## Dónde vive cada cosa
- <Carpetas clave, una línea cada una.>
- **Claves**: en `.env.local` (las carga el usuario; los nombres están en `.env.example`).

## Cómo se trabaja
- Rigen las reglas del kit (modo rápido; ciclo completo con `/ciclo-de-desarrollo` solo para tareas grandes).
- Merge a `main`: <lo decide el usuario | autorizado a publicar lo terminado>.
- Estado de una tarea en el ROADMAP: `hecho` = implementado, revisado y con pruebas; `verificado` = probado con datos reales y aprobado por el usuario.

## Calidad propia de este proyecto
- <Lo no negociable de este dominio: datos de menores, pagos, tono de marca, público que lo usa en el celular…>

## Reglas aprendidas
<!-- mejora-continua agrega acá las reglas transversales: "- Regla. **Por qué:** incidente (AAAA-MM-DD)." Máximo 150 líneas en todo el archivo; lo obsoleto se borra. -->
