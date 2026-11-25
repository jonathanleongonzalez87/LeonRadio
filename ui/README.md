# LeonRadio · ui

Interfaz de **LeonRadio**: consola de radio vintage para 2026 (HTML/CSS/JS, sin CDN en producción).
Se conecta al motor [`core/`](../core) por REST + WebSocket.

## Contenido
- `prototypes/` — las maquetas originales (v0 es la base visual: dial FM, tubos, VU estéreo, cartuchera).
- `src/css/tokens.css` — tokens de marca (paleta + Space Grotesk / Inter).
- `data/` — datos de ejemplo en JSON (contrato de la futura API).

## Siguiente (F0)
1. Separar `v0-old-radio-console.html` en `index.html` + `css/` + `js/` por componentes.
2. Quitar Tailwind CDN y Google Fonts remotos (empaquetar local).
3. Sustituir `DATABASE` embebida por JSON y luego por la API.
4. Corregir tipografías al manual (la maqueta usa Montserrat/JetBrains Mono).

## Licencia
Código: GPL-3.0-or-later (`LICENSE`). Diseño y documentación: CC BY-SA 4.0 (`../LICENSE`).
**Excepción:** isotipo, logotipo y manual de marca «Jonathan León», © Jonathan León, derechos reservados (ver `../NOTICE.md`).
