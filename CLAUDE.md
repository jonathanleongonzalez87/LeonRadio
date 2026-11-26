# LeonRadio

Plataforma de gestión y operación de una emisora (modelo: RRC – Rockland Radio Colombia), con estética de cabina vintage. Una sola plataforma con herramientas a la medida de cada función, que comparte la misma información y a veces los mismos paneles. Motor Python (`core/`) + interfaz HTML (`ui/`), paneles intercambiables y addons estilo Blender.

El plan vive en [docs/ROADMAP.md](docs/ROADMAP.md) (tier list S/A/B/C) y el avance en [docs/ESTADO.md](docs/ESTADO.md) (lo genera `node scripts/avance.mjs`). Cómo retomar y notas de trabajo: [ESTADO.md](ESTADO.md). Guía para colaborar: [docs/guia-basica.md](docs/guia-basica.md).

## Stack
- Python 3.12+ (núcleo, FastAPI + uvicorn, NumPy, miniaudio, sounddevice/WASAPI, lameenc, mutagen), SQLite. UI en HTML/CSS/JS sin framework ni CDN. Sin hosting: corre en el PC de la emisora (Windows primero).
- Node 18+ solo para el kit (`scripts/avance.mjs`, guardas).

## Comandos
- Pruebas: `cd core` y `C:\Users\leont\.venvs\leonradio\Scripts\python -m pytest -q` (hoy 71; deben pasar antes de cada PR).
- Base de datos: `%LOCALAPPDATA%\LeonRadio\leonradio.db` (copias en `copias\`). Otra ruta: `--db RUTA` o `LEONRADIO_DB`; sin `--db`, con `LEONRADIO_CONFIG` queda junto a ese archivo. Pruebas y verificaciones: siempre `:memory:` o una carpeta temporal, nunca la base real.
- Servidor sin sonido: `leonradio serve --audio null --library "..\Rockland Radio"`. Con audio real: `iniciar-leonradio.bat` (arranca en pausa). En red local: `iniciar-leonradio-red.bat`.
- `node scripts/avance.mjs`: % de avance según el ROADMAP.

## Dónde vive cada cosa
- `core/src/leonradio_core/`: `engine/` (audio, streaming, monitor), `builtin/` (editores y comandos de Al Aire), `estaciones/` (un módulo por estación de trabajo), `sdk.py` (API de editores/addons), `settings.py` (ajustes locales).
- `ui/src/`: `js/` (áreas, renderer, componentes), `css/`. `addons/`: ejemplos. `docs/`: arquitectura y guías. `Referentes/` (fuera del repo): PDF de arquitectura, manual de marca, kit.
- **Claves**: nunca en el repo. La contraseña de Icecast vive en `%LOCALAPPDATA%\LeonRadio\config.json`.

## Cómo se trabaja
- Rigen las reglas del kit (modo rápido; `/ciclo-de-desarrollo` solo para tareas grandes).
- **Una rama por tarea** (`feat/<id>-<slug>`, `fix/<slug>`, `docs/<slug>`) y **PR a `main`**. **Commits solo cuando el usuario lo pida en ese momento**, y push solo con su OK. Merge a `main`: lo decide el usuario.
- Estado en el ROADMAP: `hecho` = implementado, revisado y con pruebas; `verificado` = probado con datos reales y aprobado por el usuario.
- Estaciones: Al Aire y Programación las lleva el dueño del proyecto; Producción otra persona; Dirección, quien tenga tiempo. Cada tarea del ROADMAP lleva su estación y responsable. No se mezclan archivos de dos estaciones en un mismo PR salvo en el núcleo común, que revisan ambos.

## Calidad propia de este proyecto
- **Una sola plataforma**: una entidad (Programa, Artista, Compromiso…) tiene un solo dueño que la escribe; las demás estaciones la leen. Nada de duplicar registros (ver [docs/entidades.md](docs/entidades.md)).
- **Marca** (ver [docs/marca.md](docs/marca.md)): isotipo hexagonal visible; el nombre «Jonathan León» NO aparece en la interfaz; paleta y tipografías del manual; «Leon» protagonista en Space Grotesk.
- Solo **reencuadrar** composiciones, no cambiar el contenido de los paneles. El VU es siempre de agujas vintage.
- No dejar sonando audio sin avisar: probar con `--audio null` o en silencio. Con dispositivo real la emisión arranca en pausa.
- **Seguridad**: sin contraseña no se expone la app a la red; rutas que llegan del navegador se validan contra carpetas permitidas (deuda abierta: S6; S5 solo resolvió la base de datos).
- Pocos tokens: pedidos acotados, pocas capturas, salidas resumidas.

## Reglas aprendidas
- Un panel que contiene un `<iframe>`, un campo de texto o una perilla no debe destruirse al redibujarse: se saca de los paneles o se pausa el redibujado mientras se usa. **Por qué:** el navegador integrado se recargaba y cortaba el audio del sitio (2026-11-25).
- Antes de decir que algo funciona con el dispositivo real, probar en silencio abriendo y cerrando cada dispositivo. **Por qué:** los dispositivos WDM-KS fallaban en el equipo del usuario (2026-11-25).
- Los errores de comandos se devuelven con su mensaje (400), no como «500». **Por qué:** el diálogo de Preferencias solo mostraba «500» (2026-11-25).
