# leonradio-ui

Interfaz de **LeonRadio**: consola de radio vintage para 2026 (HTML/CSS/JS, sin CDN en producción).
Se conecta al motor [`leonradio-core`](https://github.com/jonathanleongonzalez87/leonradio-core) por REST + WebSocket.

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
Código y diseño: CC BY-SA 4.0 (ver `LICENSE`).
**Excepción:** el isotipo, el logotipo y el manual de marca «Jonathan León» son © Jonathan León, todos los derechos reservados; no están cubiertos por la licencia CC (ver `NOTICE.md`).
