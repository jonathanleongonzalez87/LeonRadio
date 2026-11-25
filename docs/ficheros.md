# Ficheros

Las listas de LeonRadio —la **Emisión** y las **4 Auxiliares**— no reproducen solo audios. Lo que reproducen se
llama **fichero**, y hay tres tipos:

| Tipo | Qué es | Ejemplos |
|---|---|---|
| **Audio** | Un archivo de sonido de la biblioteca | música, jingle, pisador, separador, cuña |
| **Evento** | Una acción que la lista ejecuta al llegar a ella | pausa de N segundos, esperar hasta el minuto :00, ejecutar un comando, marcador «Inicio de tanda» |
| **Otro** | Cualquier otro elemento que una lista pueda llevar | nota para el locutor (y lo que añadan los addons) |

Todos comparten la misma forma, así la interfaz, el historial y los addons tratan una lista sin saber qué hay dentro:

```json
{ "uid": "f12", "file": "audio|event|other", "kind": "music|jingle|pause|marker|note…",
  "id": 7, "title": "…", "artist": "…", "duration_ms": 213000, "path": "…",
  "intro_ms": null, "outro_ms": null, "event": { "type": "pause", "seconds": 5 } }
```

## Eventos
| `event.type` | Qué hace | Duración |
|---|---|---|
| `pause` | Silencio de `seconds` segundos | la indicada |
| `wait_until` | Silencio hasta que el reloj marque el `minute` de la hora | hasta que ocurra |
| `command` | Ejecuta el comando `command` con `args` (cualquier comando de LeonRadio, también de addons) | instantáneo |
| `marker` | Marca visible que no hace nada | instantáneo |

Los eventos instantáneos se ejecutan y la lista pasa de inmediato al siguiente fichero.

## Cómo se transitan (segue)
- **Audio → audio de música:** crossfade de potencia constante (3 s por defecto). Si el fichero tiene marca de
  salida (`outro_ms`), el siguiente entra ahí.
- **Jingles, pisadores, separadores:** sin superposición.
- **Eventos y otros:** nunca se superponen.
- **Saltar (⏭):** fundido corto de 300 ms, nunca un corte seco. Queda registrado como `skipped`.
- **Ducking:** una pieza lanzada desde la **Botonera** suena *encima* de la mezcla y baja la música
  (pisadores, separadores y voces −10 dB; jingles −6 dB), con ataque rápido y liberación lenta.

## Historial
Todo fichero que se ejecuta queda en `playlog`, con su `file_type` (`audio`, `event` u `other`), sus milisegundos
reales, su estado (`completed`, `skipped`, `interrupted`, `failed`) y su fuente (`auto` la Emisión, `live` las
Auxiliares, `cart` la Botonera). Así un reporte puede pedir solo la música (`file_type = 'audio'` y
`kind = 'music'`) o auditar también los eventos.

## Para addons
Un addon puede agregar ficheros a una lista con los comandos `list.add` (audio de la biblioteca o plantilla) o,
desde el motor, con `files.event_file(...)` / `files.other_file(...)`. Los tipos nuevos de `other` se muestran y se
registran sin cambios; para que *hagan* algo al llegar su turno basta con que sean eventos de tipo `command`.
Las plantillas de ejemplo están en `core/src/leonradio_core/data/event_files.json`.
