# Roadmap LeonRadio

Decisiones: motor **Python** + UI **HTML** (pywebview) · **Windows primero** · salida **FM + streaming** ·
modo **automático + Live Assist** · monorepo público · código GPL-3.0, docs y diseño CC BY-SA 4.0 · estación de prueba **RRC**.
**Arquitectura de editores y addons** estilo Blender (ver [docs/editores-y-addons.md](docs/editores-y-addons.md)): Python declarativo + JS opcional, addons en proceso aparte con permisos, gestor de áreas propio.

## F0 — Consolidar (en curso)
- [x] Repos y tablero creados; esquema de biblioteca e historial en core (con pruebas)
- [x] UI: maqueta v0 separada en `index.html` + `css/` + `js/`, sin CDN, Space Grotesk/Inter locales
- [x] Componentes vintage portados como componentes JS: VU analógico estéreo, reloj de pared, dial FM + RDS, botonera F1–F12
- [x] Datos de ejemplo y configuración en JSON (`core/src/leonradio_core/data/`); contrato en [docs/api-v0.md](docs/api-v0.md)
- [ ] Biblioteca de prueba RRC (36 archivos: música 00s/10s/20s, jingles, pisadores, separadores)

## F0.5 — Plataforma de editores y addons (nueva, antes de añadir funciones)
- [x] Gestor de áreas y workspaces propio (dividir, unir, redimensionar, cambiar editor, guardar en el navegador)
- [x] Registro de editores y comandos; bus de eventos por WebSocket
- [x] API de addons v0: manifiesto `leonradio_addon.toml`, `register()/unregister()`, permisos comprobados en la API
- [x] UI declarativa en Python (label, kv, button, progress, table, row/column) + renderer seguro (sin innerHTML)
- [x] 3 editores incluidos (Aire, Emisión, Historial) usando la misma API + addon de ejemplo (`addons/ejemplo_hora_emisora`)
- [ ] **Addons en proceso aparte** del motor de audio (hoy se cargan en el mismo proceso)
- [ ] Guardar workspaces en el servidor (hoy: `localStorage`); exportar/importar workspace
- [x] Reproductor de Aire real desde F1

## F1 — Audio real (hito 1)
- [x] Motor de audio en Python: mezclador estéreo (NumPy), decodificación con miniaudio, salida WASAPI (sounddevice)
- [x] Listas de **ficheros** (audios, eventos y otros) en la Emisión y las 4 Auxiliares → [docs/ficheros.md](docs/ficheros.md)
- [x] Reproducir una playlist (`.m3u` de RRC): carga por nombre de archivo desde Botonera ▸ Explorador ▸ Listas
- [x] Segue por marcadores (`outro_ms`) y crossfade de potencia constante; saltar con fundido de 300 ms
- [x] Ducking: las piezas de la Botonera suenan encima de la mezcla y bajan la música
- [x] Niveles VU reales (RMS) por WebSocket → agujas de la UI
- [x] **Registro en historial de cada fichero** (tipo, inicio, fin, ms reales, estado, fuente)
- [x] Salida nula (pruebas y demo en el navegador) y respaldo automático si el dispositivo no abre
- [x] Probado: 37 pruebas sin dispositivo + prueba en silencio del dispositivo real (hilo de audio ≈ 0,3 ms por bloque de 23 ms)
- [x] **Confirmación auditiva** (la hizo el usuario): suena bien
- [x] Selector de dispositivo de audio en la UI (Preferencias, una tarjeta por salida); editar la Emisión (mover, quitar); controles, deslizador, metadatos, Varios, Explorador de disco, Navegador
- [ ] Pisadores automáticos sobre la intro

## F2 — Biblioteca
- [ ] Marcadores automáticos (intro/outro), loudness EBU R128
- [ ] Edición de metadatos: ISRC, compositor, editorial (necesarios para reportes)
- [ ] Gestión de duplicados («Copia de…»), botonera con audio real

## F3 — Programación
- [ ] Relojes (hot clocks), dayparts, eventos fijos y flotantes
- [ ] Reglas de rotación (separación de artista/título, por década)
- [ ] Tandas comerciales ligadas a **compromisos** (cuñas contratadas)
- [ ] Voice tracks y Live Assist

## F4 — Salida, historial y control
- [x] Streaming Icecast 2 en MP3 + metadatos + grabación (panel Streaming de Varios) · [ ] RDS cuando haya hardware · [ ] Opus/Ogg y Shoutcast
- [ ] Reportes: música (derechos), pauta (anunciantes), operación (auditoría)
- [ ] Alertas de incumplimiento de compromisos antes de que venzan
- [ ] Detector de silencio, failover

## F5 — Producto y ecosistema
- [ ] Gestor de addons (instalar, activar, actualizar), plantilla y guía para autores
- [ ] Instalador Windows, actualizaciones, multiusuario, control remoto
