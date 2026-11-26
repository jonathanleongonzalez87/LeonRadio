# LeonRadio · ui

Interfaz de **LeonRadio**: consola de radio vintage para 2026 (HTML/CSS/JS, sin CDN en producción).
Se conecta al motor [`core/`](../core) por REST + WebSocket.

## Contenido
- `prototypes/` — las maquetas originales (v0 es la base visual: dial FM, tubos, VU estéreo, botonera).
- `src/css/tokens.css` — tokens de marca (paleta + Space Grotesk / Inter).
- `src/` — la interfaz: `index.html`, `css/`, `js/` (áreas, renderer, `components/` vintage), `fonts/`.
- Contrato con el motor: [`../docs/api-v0.md`](../docs/api-v0.md).

## Hecho en F0
Separada la maqueta, sin CDN (fuentes locales), tipografías del manual, datos en JSON y los componentes
vintage (VU, reloj, dial/RDS, botonera) portados como componentes JS.

## Pendiente
- Pruebas automáticas del gestor de áreas.
- Componentes de más editores (mezclador, voice-track, relojes de programación).
- Componentes JS propios para addons (hoy solo los incluidos).

## Licencia
Código: GPL-3.0-or-later (`LICENSE`). Diseño y documentación: CC BY-SA 4.0 (`../LICENSE`).
**Aviso:** el isotipo hexagonal (cabecera y favicon) tiene derechos reservados y no está cubierto por esta licencia (ver `../NOTICE.md`).
