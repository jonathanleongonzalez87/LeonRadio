# Arquitectura

```
ui/ (HTML/CSS/JS)  ──REST + WebSocket──►  core/ (Python)
                                                     ├─ library   (SQLite, escáner, marcadores)
                                                     ├─ playlog   (historial inmutable)
                                                     ├─ scheduler (relojes, reglas, compromisos)
                                                     ├─ engine    (decodificación, mezcla, segue, ducking)
                                                     └─ outputs   (WASAPI/ASIO · Icecast)
```

- **Motor y UI desacoplados:** la UI nunca toca el audio; solo envía comandos y recibe estado (cola, tiempo, VU).
- **Un solo motor, dos salidas:** FM (tarjeta de sonido) y streaming salen de la misma mezcla maestra.
- **Fuente de verdad del tiempo:** el motor, en UTC; la UI muestra hora local de la emisora.
- **Audio fuera de git.** Las bibliotecas viven en disco de la emisora, no en los repos.
- **Rutas portables:** las playlists importadas (`.m3u`) se resuelven por nombre de archivo, porque traen rutas de otra máquina.

## Stack previsto
Python ≥ 3.12 · SQLite · mutagen (etiquetas) · FastAPI/uvicorn (API) · pywebview + PyInstaller (escritorio) ·
motor de audio por decidir en F1 (candidatos: `miniaudio`/`sounddevice` + NumPy).
