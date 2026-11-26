# Arquitectura

```
ui/ (HTML/CSS/JS)  ──REST + WebSocket──►  core/ (Python)
                                                     ├─ library   (SQLite, escáner, marcadores)
                                                     ├─ playlog   (historial inmutable)
                                                     ├─ scheduler (relojes, reglas, compromisos)
                                                     ├─ engine    (decodificación, mezcla, segue, ducking)
                                                     └─ outputs   (WASAPI/ASIO · Icecast)
```

- **Tres procesos:** motor de audio (aislado), servidor/addons (Python) y UI. Ver [editores-y-addons.md](editores-y-addons.md).
- **Motor y UI desacoplados:** la UI nunca toca el audio; solo envía comandos y recibe estado (cola, tiempo, VU).
- **Un solo motor, dos salidas:** FM (tarjeta de sonido) y streaming salen de la misma mezcla maestra.
- **Fuente de verdad del tiempo:** el motor, en UTC; la UI muestra hora local de la emisora.
- **Audio fuera de git.** Las bibliotecas viven en disco de la emisora, no en los repos.
- **Rutas portables:** las playlists importadas (`.m3u`) se resuelven por nombre de archivo, porque traen rutas de otra máquina.

## Stack previsto
Python ≥ 3.12 · SQLite · mutagen (etiquetas) · FastAPI/uvicorn (API) · pywebview + PyInstaller (escritorio) ·
motor de audio por decidir en F1 (candidatos: `miniaudio`/`sounddevice` + NumPy).

## Motor de audio (`core/src/leonradio_core/engine/`)
```
Playout (hilo de control)  ── comandos, historial, estado ──►  UI
   │  tick ~20 Hz                                   ▲ avisos (cola segura)
   ▼                                                │
Engine.render(frames)  ◄── hilo de audio (WASAPI) ──┘
   ├─ Deck "emision" + Decks "aux1…aux4"   (listas de ficheros, segue/crossfade, pausa sin clic)
   ├─ Voces superpuestas (Botonera) + ducking de la música
   └─ Medidor VU (RMS) → `audio.levels`
```
- El hilo de audio **no toca la base de datos ni el disco**: solo mezcla y deja avisos en una cola; el Playout los lee y los escribe.
- Los archivos se decodifican **fuera** del candado del motor (precarga de los 2 primeros de cada lista).
- Con la salida nula (`--audio null`, pruebas y demo en el navegador) el Playout renderiza por tiempo: mismo código, sin dispositivo.
- Ficheros de audio sin archivo real (`demo://`) suenan como tono sintético; un archivo real que falta se registra como `failed`.

## Base de datos (S5)
- Un solo archivo SQLite, **`%LOCALAPPDATA%\LeonRadio\leonradio.db`** (disco local; no en OneDrive, que corrompe SQLite). Otra ruta solo por `--db` o `LEONRADIO_DB`; nunca por la API.
- Esquema versionado con `PRAGMA user_version` y la lista `MIGRATIONS` de `db.py`: al abrir se aplican las pendientes (cada una en su transacción). Una base de una versión más nueva se rechaza sin tocarla.
- Una conexión compartida protegida por `host.db_lock`, en modo **WAL** (lectores externos no bloquean al escritor; un corte de luz no la corrompe). Al cerrar el servidor se hace checkpoint y queda un único `.db`.
- **Copias**: al arrancar se copia a `copias\leonradio-AAAAMMDD-HHMMSS.db` (máx. 7; no más de una por hora, salvo si hay migración pendiente). Una copia fallida avisa en el log y no impide arrancar.
- **Restaurar**: cerrar LeonRadio, copiar la copia elegida sobre `leonradio.db` y borrar `leonradio.db-wal` y `leonradio.db-shm`.
- El escaneo de la biblioteca es incremental (tamaño + fecha): lo nuevo se agrega, lo modificado se re-lee, lo que desaparece pasa a `retired` (nunca se borra; el historial queda intacto) y vuelve a `active` si el archivo regresa.
- **Arranque con biblioteca grande:** el escaneo es síncrono antes de levantar el servidor. La primera vez el SHA-256 lee todo el audio (~100 MB/s: minutos si hay muchos GB) y el progreso sale en la consola cada 500 archivos; los arranques siguientes solo hacen `stat` (~1,5 s por 20.000 archivos).
- La base no debe vivir en una carpeta sincronizada (OneDrive, red): SQLite con WAL se corrompe ahí. Por eso el valor por defecto está en `%LOCALAPPDATA%`.
