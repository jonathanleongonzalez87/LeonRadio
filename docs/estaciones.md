# Estaciones de trabajo

Fuente: «Arquitectura Leon Radio» (Referentes). Hasta que se asignen usuarios y roles, **todas las estaciones están abiertas** a cualquiera que use la plataforma; lo que cambia es quién las **desarrolla**.

## Mapa

| Estación | Alcance | Prioridad | Estado | Desarrolla | Tareas (ROADMAP) |
|---|---|---|---|---|---|
| **Al Aire** | Mi programa, escaleta, guiones, invitados, controles de emisión, comunicación interna, participación de la audiencia | 1 · en desarrollo | Emisión, listas, botonera, streaming, monitores y preferencias de audio hechos | Dueño del proyecto | S2–S4, A8, B6, C3, C4 |
| **Programación** | Parrilla, librería musical, artistas, álbumes, géneros, categorías, fórmulas, rotaciones, automatización y continuidad | 2 · alta | Biblioteca y escaneo básicos | Dueño del proyecto | A1–A5, A7 |
| **Producción** | Presupuestos, inventario, mantenimiento, contratos, patrocinios, pauta, facturación, cronogramas, informes y administración | 3 · media | Por iniciar | @contactocergroup-art | A6, B1, B2 |
| **Dirección** | Identidad de programas, línea artística, formatos, proyectos creativos, guías de estilo, dirección de talento, estrategia transmedia | 4 · media | Por iniciar | Quien tenga tiempo | B3 |

Orden de desarrollo acordado: **primero el núcleo común (S5–S9: datos, seguridad, entidades, usuarios y permisos), luego Programación**; Producción avanza en paralelo apoyándose en el núcleo, y Dirección entra cuando haya manos.

## Cómo está organizado el código
```
core/src/leonradio_core/
├─ estaciones/
│  ├─ al_aire/       (nuevos paneles de Al Aire; los actuales aún están en builtin/)
│  ├─ programacion/
│  ├─ direccion/
│  └─ produccion/
├─ builtin/          editores y comandos de Al Aire y comunes (se irán moviendo, tarea S9)
├─ engine/           audio, streaming y monitoreo (núcleo)
└─ sdk.py            API de editores (núcleo)
```
Cada carpeta de estación define `register(host)`; al arrancar se cargan todas. Quien lleva una estación trabaja **solo en su carpeta**.

## Paneles compartidos
Algunos paneles sirven a varias estaciones. Se mantienen una sola vez y cada estación los acopla donde los necesita (en **Varios** o en su propio workspace):

| Panel | Lo usan |
|---|---|
| Historial de emisión | Al Aire, Programación (qué sonó), Producción (informes y pauta) |
| Metadatos | Al Aire, Programación (ISRC, compositor, editorial) |
| Explorador / Biblioteca | Al Aire, Programación |
| Reloj, VU, Monitores | Al Aire, y cualquier estación que quiera tenerlos a la vista |
| Navegador | Todas |

## El flujo que debe poder circular (ejemplo: crear un programa)
1. **Dirección**: define concepto, identidad, formato y orientación artística → crea el *Programa*.
2. **Producción**: gestiona recursos, presupuesto, personal, invitados y compromisos comerciales de ese Programa.
3. **Programación**: incorpora el Programa a la *parrilla* y fija sus condiciones de emisión.
4. **Al Aire**: recibe la *escaleta*, prepara la emisión y ejecuta.
5. **Regreso**: resultados de audiencia, observaciones del talento, cumplimiento de objetivos y evaluación vuelven a Dirección y Producción **sobre el mismo registro del Programa**, sin copias.

## Usuarios, roles y permisos (más adelante)
Un director podrá consultar Programación y Al Aire sin tener una segunda copia de los datos: el acceso lo definen los **permisos**, no la estación. Hasta la tarea S7 no hay inicio de sesión.
