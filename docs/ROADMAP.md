# ROADMAP (tier list)

`node scripts/avance.mjs` calcula el avance a partir de la tabla de tareas y escribe `docs/ESTADO.md`.
La visión y las fases históricas (F0–F5) están en [../ROADMAP.md](../ROADMAP.md); **este archivo manda** para el seguimiento.

## Pesos y valores

| Tier | Qué es | Peso en el total |
|---|---|---|
| S | Núcleo: sin esto no sirve | 45% |
| A | Muy importante | 30% |
| B | Pulido | 15% |
| C | Extras | 10% |

Dentro de cada tier pesan los **puntos** (1 = chica, 2 = mediana, 3 = grande).

| Estado | Valor |
|---|---|
| `pendiente` | 0 |
| `en curso` | 0,3 |
| `hecho` | 0,8 (implementado, revisado, con pruebas) |
| `verificado` | 1 (probado con datos reales y aprobado por el usuario) |

| Tier del producto | Condición |
|---|---|
| D · Prototipo | S < 50% |
| C · Alfa | S ≥ 50% |
| B · MVP usable | S al 100% |
| A · Producto sólido | S y A al 100% |
| S · Completo | S, A y B al 100% |

## Reglas de edición
- Solo el ciclo cambia la columna `estado` (después de la revisión o de QA). El responsable la propone en su PR.
- El arquitecto puede proponer filas nuevas o partir una fila. Un id no se reutiliza.
- El id empieza con la letra de su tier (S1, A3, B2…). `depende` lleva ids separados por coma, o `—`.
- Las dos últimas columnas (`estación`, `responsable`) no entran en el cálculo: sirven para trazar quién hace qué. Estaciones: `Núcleo`, `Al Aire`, `Programación`, `Dirección`, `Producción`, `Marca`.
- **S7 pasó a A9** (2026-11-26): el dueño pospone usuarios, roles y permisos; hasta entonces todas las estaciones tienen acceso total. Los comentarios y planes que dicen «S7» se refieren a A9.
- Cada tarea de GitHub (issue) lleva su id del ROADMAP en el título, p. ej. `[A1] Detectar marcas intro/outro`, y la etiqueta de su estación.

## Tareas

| id | tier | función | puntos | estado | depende | estación | responsable |
|---|---|---|---|---|---|---|---|
| S1 | S | Esqueleto: proyecto, pruebas (pytest), README, kit de desarrollo y guía básica | 1 | en curso | — | Núcleo | @jonathanleongonzalez87 |
| S2 | S | Al Aire: motor de audio real, listas de ficheros, crossfade, ducking, VU, historial (F1) | 3 | verificado | — | Al Aire | @jonathanleongonzalez87 |
| S3 | S | Al Aire: Controles, Varios (Botonera, Eventos, Explorador, Navegador), Metadatos, Auxiliares, Preferencias de audio | 3 | hecho | S2 | Al Aire | @jonathanleongonzalez87 |
| S4 | S | Al Aire: Streaming Icecast (MP3, metadatos, grabación) y Monitores remotos | 2 | hecho | S2 | Al Aire | @jonathanleongonzalez87 |
| S5 | S | Núcleo: base de datos persistente y compartida (SQLite en archivo, migraciones, copia de seguridad) | 3 | verificado | — | Núcleo | @jonathanleongonzalez87 |
| S6 | S | Núcleo: seguridad de la API (autenticación, validar rutas, origen, límites, modo red seguro) | 3 | verificado | — | Núcleo | @jonathanleongonzalez87 |
| S8 | S | Núcleo: marco de entidades compartidas + Artista, Álbum, Género y Pieza (con su dueño) y panel «Entidades» | 2 | verificado | S5 | Núcleo | @jonathanleongonzalez87 |
| S10 | S | Núcleo: entidades de Dirección y Al Aire (Programa, Persona, Invitado) | 1 | pendiente | S8 | Núcleo | @jonathanleongonzalez87 |
| S9 | S | Núcleo: estaciones como módulos (registro, menú de editores por estación, convención de paneles) | 2 | en curso | — | Núcleo | @jonathanleongonzalez87 |
| A1 | A | Programación: detectar marcas intro/outro y loudness al escanear (#24) | 2 | pendiente | S5 | Programación | @jonathanleongonzalez87 |
| A2 | A | Programación: pisadores automáticos sobre la intro (#23) | 2 | pendiente | A1 | Programación | @jonathanleongonzalez87 |
| A3 | A | Programación: metadatos ISRC, compositor, editorial (#8) | 2 | pendiente | S8 | Programación | @jonathanleongonzalez87 |
| A4 | A | Programación: parrilla, relojes y dayparts | 3 | pendiente | S8 | Programación | @jonathanleongonzalez87 |
| A5 | A | Programación: reglas de rotación (separación de artista/título, por década) | 3 | pendiente | A4 | Programación | @jonathanleongonzalez87 |
| A6 | A | Producción: clientes, contratos, patrocinios y pauta (compromisos comerciales) | 3 | pendiente | S8 | Producción | @contactocergroup-art |
| A7 | A | Programación + Producción: tandas comerciales ligadas a compromisos (#9) | 3 | pendiente | A4, A6 | Programación | @jonathanleongonzalez87 |
| A8 | A | Al Aire: escaleta, guiones e invitados («Mi programa») | 3 | pendiente | S10 | Al Aire | @jonathanleongonzalez87 |
| A9 | A | Núcleo: usuarios, roles y permisos por estación (antes S7; pospuesta por el dueño: por ahora todas las estaciones tienen acceso total para probar) | 3 | pendiente | S5, S6 | Núcleo | @jonathanleongonzalez87 |
| B1 | B | Producción: presupuestos, inventario, mantenimiento y facturación | 3 | pendiente | A6 | Producción | @contactocergroup-art |
| B2 | B | Reportes de música, pauta y operación (#10, #11) | 3 | pendiente | A3, A6 | Producción | @contactocergroup-art |
| B3 | B | Dirección: identidad de programas, formatos, línea artística y talento | 3 | pendiente | S10 | Dirección | @contactocergroup-art |
| B4 | B | Workspaces en el servidor y exportar/importar (#19) | 1 | pendiente | S5 | Núcleo | @jonathanleongonzalez87 |
| B5 | B | Marca: firma LeonRadio, wordmark según el manual, retícula de fondo | 2 | pendiente | — | Marca | @jonathanleongonzalez87 |
| B6 | B | Al Aire: comunicación interna y participación de la audiencia | 2 | pendiente | A9 | Al Aire | @jonathanleongonzalez87 |
| B7 | B | Pruebas automáticas de la UI (#20) | 2 | pendiente | — | Núcleo | @jonathanleongonzalez87 |
| C1 | C | Addons en proceso aparte del motor de audio (#18, #14) | 3 | pendiente | A9 | Núcleo | @jonathanleongonzalez87 |
| C2 | C | Gestor de addons, plantilla y guía para autores (#17) | 2 | pendiente | C1 | Núcleo | @jonathanleongonzalez87 |
| C3 | C | Streaming: Opus/Ogg y Shoutcast | 2 | pendiente | S4 | Al Aire | @jonathanleongonzalez87 |
| C4 | C | Escucha previa con salida propia y entradas de línea (Live Assist) | 3 | pendiente | S3 | Al Aire | @jonathanleongonzalez87 |
