# Roadmap LeonRadio

Decisiones: motor **Python** + UI **HTML** (pywebview) · **Windows primero** · salida **FM + streaming** ·
modo **automático + Live Assist** · monorepo público · código GPL-3.0, docs y diseño CC BY-SA 4.0 · estación de prueba **RRC**.
**Arquitectura de editores y addons** estilo Blender (ver [docs/editores-y-addons.md](docs/editores-y-addons.md)): Python declarativo + JS opcional, addons en proceso aparte con permisos, gestor de áreas propio.

## F0 — Consolidar (en curso)
- [x] Repos y tablero creados; esquema de biblioteca e historial en core (con pruebas)
- [ ] UI: separar la maqueta v0 en `index.html`/`css`/`js`, sin CDN, tipografías del manual
- [ ] Datos de ejemplo → JSON; definir contrato de API v0
- [ ] Biblioteca de prueba RRC (36 archivos: música 00s/10s/20s, jingles, pisadores, separadores)

## F0.5 — Plataforma de editores y addons (nueva, antes de añadir funciones)
- [x] Gestor de áreas y workspaces propio (dividir, unir, redimensionar, cambiar editor, guardar en el navegador)
- [x] Registro de editores y comandos; bus de eventos por WebSocket
- [x] API de addons v0: manifiesto `leonradio_addon.toml`, `register()/unregister()`, permisos comprobados en la API
- [x] UI declarativa en Python (label, kv, button, progress, table, row/column) + renderer seguro (sin innerHTML)
- [x] 3 editores incluidos (Aire, Cola, Historial) usando la misma API + addon de ejemplo (`addons/ejemplo_hora_emisora`)
- [ ] **Addons en proceso aparte** del motor de audio (hoy se cargan en el mismo proceso)
- [ ] Guardar workspaces en el servidor (hoy: `localStorage`); exportar/importar workspace
- [ ] Reproductor de Aire es **simulado** hasta F1

## F1 — Audio real (hito 1, en paralelo a F0.5, en su propio proceso)
- [ ] Reproducir una playlist (`.m3u` de RRC) con salida WASAPI
- [ ] Segue por marcadores intro/outro y crossfade
- [ ] Ducking: pisadores y separadores sobre la música
- [ ] Niveles VU reales por WebSocket → agujas de la UI
- [ ] **Registro en historial de cada emisión** (inicio, fin, ms reproducidos, estado)

## F2 — Biblioteca
- [ ] Marcadores automáticos (intro/outro), loudness EBU R128
- [ ] Edición de metadatos: ISRC, compositor, editorial (necesarios para reportes)
- [ ] Gestión de duplicados («Copia de…»), cartuchera con audio real

## F3 — Programación
- [ ] Relojes (hot clocks), dayparts, eventos fijos y flotantes
- [ ] Reglas de rotación (separación de artista/título, por década)
- [ ] Tandas comerciales ligadas a **compromisos** (cuñas contratadas)
- [ ] Voice tracks y Live Assist

## F4 — Salida, historial y control
- [ ] Streaming Icecast + metadatos (y RDS cuando haya hardware)
- [ ] Reportes: música (derechos), pauta (anunciantes), operación (auditoría)
- [ ] Alertas de incumplimiento de compromisos antes de que venzan
- [ ] Detector de silencio, failover

## F5 — Producto y ecosistema
- [ ] Gestor de addons (instalar, activar, actualizar), plantilla y guía para autores
- [ ] Instalador Windows, actualizaciones, multiusuario, control remoto
