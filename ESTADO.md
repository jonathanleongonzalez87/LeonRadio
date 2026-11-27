# Estado de LeonRadio (para retomar en una sesión nueva)

Última actualización: 2026-11-27 (v0.2.1). Lee esto primero; después `README.md`, `ROADMAP.md` y `docs/`.

## Qué es
Automatizador de radio con estética de cabina vintage: motor **Python** (`core/`) + interfaz **HTML** (`ui/`),
con paneles intercambiables y addons estilo Blender. Estación de prueba: **RRC – Rockland Radio Colombia**.
Repo: https://github.com/jonathanleongonzalez87/LeonRadio · Proyecto «LeonRadio» (tablero de issues).

## Dónde está todo
- Código: `C:\Users\leont\OneDrive\Documents\LeonRadio\LeonRadio` · audio de la emisora: `..\Rockland Radio` (no se versiona).
- Entorno de desarrollo: `C:\Users\leont\.venvs\leonradio` (fuera de OneDrive). Entorno del lanzador: `%LOCALAPPDATA%\LeonRadio\venv`.
- Pruebas: `cd core` y `C:\Users\leont\.venvs\leonradio\Scripts\python -m pytest -q` → **165 pasan** (1 omitida). El seguimiento por tareas y el % de avance están en `docs/ROADMAP.md` y `docs/ESTADO.md`; las guías para colaborar, en `docs/guia-basica.md`.

## Cómo ejecutarlo
- **Con audio real:** doble clic en `iniciar-leonradio.bat` (arranca en **pausa**; pulsa ▶ Reproducir). → http://127.0.0.1:8765/
- **Solo interfaz, sin servidor:** `probar-ui.bat` (genera `dist\LeonRadio-demo.html` con el motor dentro del navegador).
- Sin sonido: `leonradio serve --audio null`. Dispositivos: `leonradio devices`. Tono de prueba: `leonradio beep`.
- Capturas del README: `tools\screenshots.py` contra un servidor **sin audio** (si no, dispara sonido).

## Hecho (versión 0.1.0)
- **F0 / F0.5:** gestor de áreas y workspaces, editores y addons con permisos, UI declarativa en Python, componentes vintage.
- **F1 (el usuario confirmó que el audio suena bien):** motor NumPy + miniaudio + WASAPI; listas de **ficheros** (audio, evento, otro) en la Emisión y 4 Auxiliares; crossfade, segue, ducking, VU real, historial.
- **Listas:** elegir fila, arrastrar para reordenar, Supr para quitar; deslizador de posición; «parar tras la actual»; Próxima se vacía al armarlo.
- **Paneles:** Aire (tiempo restante y hora de fin), Controles (teclas de pletina), Próxima, Emisión, Metadatos (carátula y etiquetas), Historial, VU, Reloj, Dial/RDS, Auxiliar 1–4 (en fila), y **Varios** (pestañas: Botonera, Eventos, Explorador, Navegador, y los que se acoplen con ＋). Menú de editores en columnas.
- **Botonera:** 10 pads (1–9, 0) con el teclado numérico, pisadores → separadores → jingles; encendidos mientras suenan y se detienen al repulsar.
- **Explorador:** biblioteca o disco duro («Mi equipo»); **Navegador** web incrustado (los sitios que prohíben incrustarse se abren aparte).
- **Monitores** (panel de Varios): escucha remota por WebSocket (`/ws/monitor`, PCM 16 bits, ~0,3 s de retraso); volumen y encendido por dispositivo. Red local: `iniciar-leonradio-red.bat` (`--host 0.0.0.0`), sin contraseña.
- **Streaming** (panel de Varios): Icecast 2 en MP3 con `lameenc`, reconexión, metadatos y grabación; probado contra un Icecast falso en las pruebas, **falta probar contra un servidor real**. Contraseña solo en `config.json`.
- **Preferencias** (menú Archivo, Ctrl+,): tarjeta de sonido por salida (principal, Aux 1–4, Botonera; la escucha previa y las entradas solo se guardan). Ajustes en `%LOCALAPPDATA%\LeonRadio\config.json`.
- Barra de menú, pantalla de carga (se cierra con un clic) y diseños guardados v10 (cambiar `KEY` en `main.js` los restablece).

## Novedades de la 0.2.1
- **Teléfono sin pasos:** `iniciar-leonradio.bat` arranca en modo red (con clave) y Ayuda ▸ Conectar el teléfono (QR) abre en el PC un QR de un solo uso para entrar desde el teléfono en la misma red.
- **Audio:** si la salida guardada ya no existe (p. ej. unos auriculares desconectados) usa la predeterminada de Windows en vez del modo simulado.

## Novedades de la 0.2.0
- **Núcleo:** base SQLite persistente con migraciones y copias (S5), seguridad de la API con clave de acceso, sesión, origen y carpetas permitidas (S6), entidades compartidas Pieza/Artista/Álbum/Género con su dueño y panel «Entidades» (S8). Usuarios, roles y permisos se pospusieron a A9: por ahora acceso total a las estaciones.
- **Estaciones:** pestañas Al Aire, Programación, Dirección y Producción; reparto de trabajo en `docs/estaciones.md`; kit de desarrollo en `herramientas/`; audio propio de RRC en `datos-de-prueba/` (la música va en un repositorio privado).
- **Hora local** del Historial. Avance: 36 % (Tier C · Alfa).

## Pendiente (issues abiertos)
- Mejoras del motor/UI: #23 pisadores automáticos sobre la intro, #24 detectar marcas intro/outro y loudness.
- F2–F5: #8 metadatos ISRC, #9 compromisos y tandas, #10 reportes, #17 gestor de addons.
- F0.5: #14/#18 aislar addons en proceso aparte, #19 workspaces en el servidor, #20 pruebas de la UI.
- Ideas anotadas: escucha previa con su propia salida; entradas de línea (Live Assist); las Auxiliares abiertas en fila reparten el ancho a la mitad cada una; el audio del Navegador no pasa por el motor (sin VU ni ducking).
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
