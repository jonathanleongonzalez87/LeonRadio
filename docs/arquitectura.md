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
