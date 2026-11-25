# API v0 (contrato UI ↔ core)

Servidor: `leonradio serve` → `http://127.0.0.1:8765`. La UI solo usa esta API; nunca toca el audio ni la base de datos.

## REST
| Método y ruta | Devuelve |
|---|---|
| `GET /api/info` | `{station, config:{name,short,frequency,timezone,website}, api_version, addons:[{id,name,version,permissions}]}` |
| `GET /api/editors` | `[{id, label, icon, owner}]` — editores disponibles (incluidos y de addons) |
| `GET /api/editors/{id}/draw` | Árbol de UI del editor (ver nodos). Si el editor falla, devuelve un árbol con el error. |
| `POST /api/commands/{nombre}` | Cuerpo `{"args": {...}}` → `{"ok": true, "result": ...}`. `404` comando desconocido, `403` sin permiso. |

## WebSocket `/ws`
El servidor emite `{"event": "<nombre>", "data": {...}}`.

| Evento | Cuándo | Datos |
|---|---|---|
| `state_changed` | cambia una clave de estado | `{key}` |
| `playlog.added` | se registra una emisión | `{id}` |
| `audio.levels` | ~10 veces por segundo | `{l, r, simulated}` con niveles 0–1 |
| `<addon>.<evento>` | un addon emite un evento | libre |

La UI refresca los editores ante `state_changed`/`playlog.added` (máx. 1 vez cada 0,7 s) y entrega `audio.levels` directamente a los componentes (VU).

## Nodos de UI declarativa
`column`, `row` (contenedores con `children`), `label{text,tone}`, `kv{key,value}`, `button{label,command,args}`,
`progress{value,text}`, `table{columns,rows}`, `separator` y `custom{component,props}`.

Tonos de `label`: `normal`, `muted`, `accent`, `big`, `mono`, `ok`, `warn`.

### Componentes (`custom`)
| `component` | Props | Datos que usa |
|---|---|---|
| `vu-meter` | — | evento `audio.levels` |
| `analog-clock` | `timezone`, `name` | hora local de la emisora |
| `fm-dial` | `name`, `frequency` (o `null` = ONLINE), `rds` | — |
| `cartwall` | `pads:[{key,asset_id,title,sub,style}]`, `command` | teclas F1–F12; comando `cart.fire{asset_id}` |

Estilos de pad: `orange`, `bronze`, `graphite`, `cream`.
Las props son JSON y **no son de confianza**: los componentes escriben con `textContent`.

## Datos de ejemplo y configuración (empaquetados en `core/src/leonradio_core/data/`)
- `station.json` — nombre, sigla, frecuencia (`null` = solo online), zona horaria.
- `cartwall.json` — número de pads, tipos de pieza y estilo por tipo.
- `demo_sample.json` — cola de muestra cuando no hay biblioteca cargada.

## Estado
v0, puede cambiar. El audio y los niveles son **simulados** hasta F1.
