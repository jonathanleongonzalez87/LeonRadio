# Estado de LeonRadio (para retomar en una sesión nueva)

Última actualización: 2026-11-25. Lee esto primero; después `README.md`, `ROADMAP.md` y `docs/`.

## Qué es
Automatizador de radio con estética de cabina vintage: motor **Python** (`core/`) + interfaz **HTML** (`ui/`),
con paneles intercambiables y addons estilo Blender. Estación de prueba: **RRC – Rockland Radio Colombia**.
Repo: https://github.com/jonathanleongonzalez87/LeonRadio · Proyecto «LeonRadio» (tablero de issues).

## Dónde está todo
- Código: `C:\Users\leont\OneDrive\Documents\LeonRadio\LeonRadio` · audio de la emisora: `..\Rockland Radio` (no se versiona).
- Entorno de desarrollo: `C:\Users\leont\.venvs\leonradio` (fuera de OneDrive). Entorno del lanzador: `%LOCALAPPDATA%\LeonRadio\venv`.
- Pruebas: `cd core` y `C:\Users\leont\.venvs\leonradio\Scripts\python -m pytest -q` → **38 pasan**.

## Cómo ejecutarlo
- **Con audio real:** doble clic en `iniciar-leonradio.bat` (arranca en **pausa**; pulsa ▶ Reproducir). → http://127.0.0.1:8765/
- **Solo interfaz, sin servidor:** `probar-ui.bat` (genera `dist\LeonRadio-demo.html` con el motor dentro del navegador).
- Sin sonido: `leonradio serve --audio null`. Dispositivos: `leonradio devices`. Tono de prueba: `leonradio beep`.
- Capturas del README: `tools\screenshots.py` contra un servidor **sin audio** (si no, dispara sonido).

## Hecho
- **F0 / F0.5:** gestor de áreas y workspaces, editores y addons con permisos, UI declarativa en Python, componentes vintage (VU de agujas, reloj, dial/RDS, botonera).
- **F1 (el usuario confirmó que el audio suena bien):** motor NumPy + miniaudio + WASAPI; listas de **ficheros** (audio, evento, otro) en la Emisión y 4 Auxiliares; crossfade, segue por marcas, ducking, VU real, historial con `file_type`.
- Paneles: Aire, Próxima, Emisión, Historial, VU, Reloj, Dial/RDS, Botonera (pestañas Botonera/Eventos/Explorador), Auxiliar 1–4 (se activan con AUX 1–4).

## Sin subir a git (el usuario pidió subir SOLO cuando lo pida)
Isotipo hexagonal restituido en la cabecera y como favicon (`ui/src/index.html`, `app.css`), `NOTICE.md`/READMEs
actualizados, 1 prueba nueva y capturas regeneradas. Está probado y funciona; falta que el usuario pida el commit.

## Pendiente (issues abiertos)
- F1: #3 se cierra cuando el usuario confirme el audio (ya dijo que funciona → cerrar al subir).
- Mejoras del motor/UI: #21 editar la Emisión (quitar/mover), #22 selector de dispositivo en la UI, #23 pisadores automáticos sobre la intro, #24 detectar marcas intro/outro y loudness.
- F2–F5: #8 metadatos ISRC, #9 compromisos y tandas, #10 reportes, #17 gestor de addons.
- F0.5: #14/#18 aislar addons en proceso aparte, #19 workspaces en el servidor, #20 pruebas de la UI.
- **Preguntas sin responder (las necesita F3/F4):** #11 a qué sociedad de gestión reporta RRC y en qué formato · si las cuñas son por cantidad o también por franja · manual de marca de RRC.

## Reglas del usuario (importantes)
- **No hacer commit ni push salvo que lo pida en ese momento.**
- Solo **reencuadrar** composiciones, no cambiar el contenido de los paneles. VU siempre de agujas vintage.
- Isotipo hexagonal visible; el nombre «Jonathan León» no aparece en la interfaz. Licencias: código GPL-3.0, docs/diseño CC BY-SA 4.0.
- No dejar sonando audio sin avisar (probar en silencio o con `--audio null`).
- Gastar pocos tokens: pedidos acotados, pocas capturas, salidas resumidas.

## Cosas que cuestan tiempo (para no repetirlas)
- miniaudio no abre rutas con tilde: se leen los bytes desde Python (ya resuelto en `FileSource.load`).
- Decodificar dentro del candado del hilo de audio causó un bloque de 497 ms; ahora se precarga fuera.
- En Bash de esta sesión, `\\` se colapsa a `\`: escribir archivos con la herramienta Write o usar `chr(92)`.
- Un comando que mezcla el correo del usuario con peticiones de red lo bloquea el sistema: separarlos.
- El navegador guarda páginas viejas: el servidor ya sirve la UI bajo `/v/<versión>/`.

## Primer mensaje sugerido para la sesión nueva
> Lee `ESTADO.md` y el `ROADMAP.md` de mi proyecto LeonRadio. Quiero continuar con: <tu siguiente paso>.
> Recuerda: no subas nada a git hasta que te lo pida.
