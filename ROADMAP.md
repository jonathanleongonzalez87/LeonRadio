# Roadmap LeonRadio

Decisiones: motor **Python** + UI **HTML** (pywebview) · **Windows primero** · salida **FM + streaming** ·
modo **automático + Live Assist** · repos públicos CC BY-SA 4.0 · estación de prueba **RRC**.

## F0 — Consolidar (en curso)
- [x] Repos y tablero creados; esquema de biblioteca e historial en core (con pruebas)
- [ ] UI: separar la maqueta v0 en `index.html`/`css`/`js`, sin CDN, tipografías del manual
- [ ] Datos de ejemplo → JSON; definir contrato de API v0
- [ ] Biblioteca de prueba RRC (36 archivos: música 00s/10s/20s, jingles, pisadores, separadores)

## F1 — Audio real (hito 1)
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

## F5 — Producto
- [ ] Instalador Windows, actualizaciones, multiusuario, control remoto
