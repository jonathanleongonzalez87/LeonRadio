# Marca (resumen para quien desarrolla)

Fuente: «Jonathan León — Manual de marca» v1.0 (Referentes). **Jonathan León es la marca madre**; LeonRadio es un proyecto del ecosistema (como LeonStudio, LeonToon, LeonFrame, LeonProducer): comparte el isotipo y cambia el logotipo.

## Reglas no negociables
- **El nombre «Jonathan León» no aparece en la interfaz** (decisión del dueño). El **isotipo hexagonal** (puma en hexágono) sí, en la cabecera y como favicon. Derechos reservados: ver `NOTICE.md`.
- **Isotipo**: hexágono regular apuntado, trazo constante con terminaciones redondeadas, un solo color. Mínimo **24 px**. Área de protección: la mitad de su altura (x) alrededor.
- **Logotipo «LeonRadio»**: la parte **«Leon» es la protagonista** — Space Grotesk **bold**, color principal (naranja); **«Radio»** la acompaña en **Inter regular**, tono secundario. Una sola palabra visual. *Hoy la cabecera lo hace al revés (Radio en naranja): corrección pendiente, tarea B5.*
- No deformar, rotar, cambiar colores o tipografía, ni añadir sombras, brillos o contornos a la firma.

## Paleta
| Uso | Color | Hex |
|---|---|---|
| Fondo y superficies | Carbón | `#262626` |
| Acento, isotipo, llamados a la acción | Naranja ámbar | `#FD6724` |
| Texto sobre oscuro | Crema | `#F2E8DA` |
| Destacados sobre oscuro | Bronce | `#C58F5E` |
| Destacados sobre claro | Bronce profundo | `#865632` |
| Fondo en modo claro | Arena | `#EFE7DC` |
| Grises cálidos | Grafito 900 / 700, Gris 500 / 300, Tinta, Lino | `#1A1918` `#3A3633` `#6B625A` `#B5A898` `#2A2420` `#E6DCCF` |

Los tokens ya están en `ui/src/css/tokens.css` y coinciden con el manual. **Usa los tokens, no códigos sueltos.**

- Proporción sobre carbón: carbón 60 % · crema 25 % · naranja 10 % · bronce 5 %. Sobre arena: arena 60 · tinta 25 · naranja 10 · bronce profundo 5.
- **Contraste**: texto mínimo AA. El naranja sobre arena es **solo gráfico** (isotipo, botones con texto en tinta), nunca texto.

## Tipografía
- Titulares: **Space Grotesk** (400/500/700). Texto e interfaz: **Inter** (400/500/600). Ambas locales en `ui/src/fonts` (sin CDN).

## Retícula
- Cuadrícula naranja con transparencia de fondo: módulo base **28 px**, líneas mayores cada 5 módulos (140 px); opacidad sobre oscuro 7,5 % / 14 %, sobre claro 11 % / 20 %. Ancho máximo de contenido 1344 px, márgenes laterales 6 %. *Pendiente en la UI (tarea B5).*

## Lo propio de LeonRadio (estética de cabina vintage)
Teclas metálicas, perillas moleteadas, VU de agujas, madera y baquelita. Conviven con la paleta de la marca; no reemplazan sus colores. Pantalla de carga: ilustración del puma (`ui/src/img/splash.webp`).

## Pendiente de marca (B5)
Firma horizontal y vertical de LeonRadio con sus variaciones de color, wordmark corregido en cabecera y pantalla de carga, retícula de fondo, y manual de marca de RRC (la emisora de pruebas) cuando exista.
