# Arquitectura

```
ui/ (HTML/CSS/JS)  ──REST + WebSocket──►  core/ (Python)
                                                     ├─ library   (SQLite, escáner, marcadores)
                                                     ├─ playlog   (historial inmutable)
                                                     ├─ scheduler (relojes, reglas, compromisos)
                                                     ├─ engine    (decodificación, mezcla, segue, ducking)
                                                     └─ outputs   (WASAPI/ASIO · Icecast)
```

- **Tres procesos:** motor de audio (aislado), servidor/addons (Python) y UI. Ver [editores-y-addons.md](editores-y-addons.md).
- **Motor y UI desacoplados:** la UI nunca toca el audio; solo envía comandos y recibe estado (cola, tiempo, VU).
- **Un solo motor, dos salidas:** FM (tarjeta de sonido) y streaming salen de la misma mezcla maestra.
- **Fuente de verdad del tiempo:** el motor, en UTC; la UI muestra hora local de la emisora.
- **Audio fuera de git.** Las bibliotecas viven en disco de la emisora, no en los repos.
- **Rutas portables:** las playlists importadas (`.m3u`) se resuelven por nombre de archivo, porque traen rutas de otra máquina.

## Stack previsto
Python ≥ 3.12 · SQLite · mutagen (etiquetas) · FastAPI/uvicorn (API) · pywebview + PyInstaller (escritorio) ·
motor de audio por decidir en F1 (candidatos: `miniaudio`/`sounddevice` + NumPy).

## Motor de audio (`core/src/leonradio_core/engine/`)
```
Playout (hilo de control)  ── comandos, historial, estado ──►  UI
   │  tick ~20 Hz                                   ▲ avisos (cola segura)
   ▼                                                │
Engine.render(frames)  ◄── hilo de audio (WASAPI) ──┘
   ├─ Deck "emision" + Decks "aux1…aux4"   (listas de ficheros, segue/crossfade, pausa sin clic)
   ├─ Voces superpuestas (Botonera) + ducking de la música
   └─ Medidor VU (RMS) → `audio.levels`
```
- El hilo de audio **no toca la base de datos ni el disco**: solo mezcla y deja avisos en una cola; el Playout los lee y los escribe.
- Los archivos se decodifican **fuera** del candado del motor (precarga de los 2 primeros de cada lista).
- Con la salida nula (`--audio null`, pruebas y demo en el navegador) el Playout renderiza por tiempo: mismo código, sin dispositivo.
- Ficheros de audio sin archivo real (`demo://`) suenan como tono sintético; un archivo real que falta se registra como `failed`.

## Base de datos (S5)
- Un solo archivo SQLite, **`%LOCALAPPDATA%\LeonRadio\leonradio.db`** (disco local; no en OneDrive, que corrompe SQLite). Otra ruta solo por `--db` o `LEONRADIO_DB`; nunca por la API.
- Esquema versionado con `PRAGMA user_version` y la lista `MIGRATIONS` de `db.py`: al abrir se aplican las pendientes (cada una en su transacción). Una base de una versión más nueva se rechaza sin tocarla.
- Una conexión compartida protegida por `host.db_lock`, en modo **WAL** (lectores externos no bloquean al escritor; un corte de luz no la corrompe). Al cerrar el servidor se hace checkpoint y queda un único `.db`.
- **Copias**: al arrancar se copia a `copias\leonradio-AAAAMMDD-HHMMSS.db` (máx. 7; no más de una por hora, salvo si hay migración pendiente). Una copia fallida avisa en el log y no impide arrancar.
- **Restaurar**: cerrar LeonRadio, copiar la copia elegida sobre `leonradio.db` y borrar `leonradio.db-wal` y `leonradio.db-shm`.
- El escaneo de la biblioteca es incremental (tamaño + fecha): lo nuevo se agrega, lo modificado se re-lee, lo que desaparece pasa a `retired` (nunca se borra; el historial queda intacto) y vuelve a `active` si el archivo regresa.
- **Arranque con biblioteca grande:** el escaneo es síncrono antes de levantar el servidor. La primera vez el SHA-256 lee todo el audio (~100 MB/s: minutos si hay muchos GB) y el progreso sale en la consola cada 500 archivos; los arranques siguientes solo hacen `stat` (~1,5 s por 20.000 archivos).
- La base no debe vivir en una carpeta sincronizada (OneDrive, red): SQLite con WAL se corrompe ahí. Por eso el valor por defecto está en `%LOCALAPPDATA%`.

## Entidades compartidas (S8)
- `core/src/leonradio_core/entities.py`: cada entidad se **declara** (`Entity`, `Field`) y tiene una estación **dueña**; solo `host.entities.writer(<estación>)` escribe (otra estación recibe `PermissionDenied`), todas leen por `list`/`get` o `GET /api/entities*` (solo columnas declaradas, nunca `path` ni `sha256`). Sin borrado: se archiva (`archived=1`).
- Toda fila gestionada lleva `id, archived, created_at, updated_at, created_by, updated_by`; quien firma es `ctx.principal` (`"local"` o `"clave"`; S7 lo cambia a usuario). Los comandos de escritura llevan `risk="datos"`.
- Cada estación pone su SQL en `estaciones/<estacion>/migraciones.py` (solo `sqlite3`, funciones `m<N>_...`) y `db.py` las agrega al final de `MIGRATIONS`. La migración 3 crea Artista, Álbum y Género y vincula `assets` (los textos `artist`/`album` no cambian); `catalogo.sync` vincula lo que escanee después.
- **Límites conocidos:**
  - **Única excepción a «solo por el `writer`»:** `catalogo.sync` escribe `assets.artista_id/album_id` directamente con `host.db`; `assets` no es entidad gestionada y su dueña, Programación, es quien lo hace (la creación de artistas y álbumes sí pasa por el `writer`).
  - **Addons no aislados:** `entities.read` no impide que un addon malicioso llegue a `host` y tome un `writer`; se resuelve con la tarea C1 (aislamiento de addons), igual que la nota de S6.
  - **`risk="datos"` es hoy solo una etiqueta:** S7 debe hacerlo cumplir con permisos por usuario y rol.
  - **Migración m3:** su relleno carga todas las piezas en memoria (~10 s y ~170 MB con 200.000 piezas) y debe seguir corriendo al abrir la base, antes de `playout.start()`.
- Panel común **Entidades**: solo lectura. Contrato para una estación nueva: [entidades.md](entidades.md).

## Seguridad (S6)
Servidor local de una sola emisora, sin hosting ni dominio. El tráfico en la red local va por **HTTP sin cifrar**.
- **Dos modos**, decididos por `--host` al arrancar (`serve()`): *local* (`127.0.0.1`, por defecto: sin clave, `Host` solo `localhost`/`127.0.0.1`/`[::1]`, anti DNS-rebinding) y *red* (`0.0.0.0` u otra IP: clave obligatoria; sin clave guardada no arranca).
- **Clave de acceso**: 16 caracteres sin ambiguos (`XXXX-XXXX-XXXX-XXXX`), solo se guarda su hash `scrypt` en `config.json` (`auth.key_hash`). La primera vez en modo red se crea y se muestra **una sola vez** en la consola; `leonradio clave` crea otra y la anterior (y las sesiones abiertas) dejan de valer, sin reiniciar.
- **El propio PC entra sin clave aunque el servidor esté en modo red**: se exime a la petición cuya dirección REAL del socket (`request.client.host`) es loopback **y** cuyo `Host` es loopback. Nunca se mira `X-Forwarded-For` (uvicorn corre con `proxy_headers=False`). Un túnel o proxy local que reenvíe tráfico de fuera llega con el `Host` de fuera y sí pide clave. **Pero** un proxy o túnel local (ngrok, Caddy…) que reescriba el `Host` a localhost hace pasar el tráfico externo como PC local y entraría sin clave: no usarlos con este modo. `Origin` y `Host` se comprueban igual para todos.
- **Sesión**: `POST /api/login {key}` → cookie `leonradio_sesion` (`HttpOnly`, `SameSite=Strict`, 12 h, en memoria; reiniciar el servidor las cierra). `GET /api/session` (`auth_required`, `authenticated`, `station`), `POST /api/logout`. Bloqueo por IP del socket: 5 fallos en 10 min → 15 min de `429` (también con la clave correcta). Un único punto decide el acceso, `auth.current_principal` (HTTP y WebSocket); S7 solo sustituirá su cuerpo.
- **Origen**: en `POST/PUT/PATCH/DELETE` y en el handshake de `/ws` y `/ws/monitor`, si viene `Origin` debe coincidir con `Host` (si no, `403`); sin `Origin` se acepta (curl, pruebas), pero en modo red sigue pidiéndose la cookie.
- **Límites**: cuerpo HTTP ≤ 256 KiB (`413`), mensaje WebSocket ≤ 64 KiB, `/ws` ≤ 32 y `/ws/monitor` ≤ 16 conexiones. Cabeceras `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`. `/docs`, `/redoc` y `/openapi.json` están desactivados.
- **Rutas permitidas**: todo lo que llega del navegador (`explorer.cd`, `list.add_path`, `explorer.add_folder`, `list.load_m3u`, `stream.set` con `record_dir`) se valida con `paths.check`: la biblioteca de la emisora, Música, Descargas y Escritorio del usuario, más las agregadas **solo por consola** con `leonradio carpetas --agregar RUTA` (`--quitar`, `--lista`). Se rechazan `..` que escapa, rutas UNC y de dispositivo (sin resolverlas), enlaces que apuntan fuera y la carpeta de ajustes (claves y base) aunque esté dentro de una permitida. No hay «Inicio» ni unidades completas. El mensaje de rechazo no incluye rutas.
- **Errores**: un fallo inesperado devuelve `500 {"detail":"Error interno"}` sin traza; los `OSError` solo muestran su `strerror`. Los logs nunca llevan argumentos de comandos, la clave ni cookies.
- **Riesgo por comando**: `host.command_risk` (`normal`, `emision`, `config`, `archivos`); S7 lo usará para dar permisos por rol.
- **Lo que NO protege**: la clave y la cookie viajan **sin cifrar** por HTTP; quien «huela» el Wi-Fi puede verlas. Úsalo solo en una red de confianza (HTTPS es deuda). La contraseña de Icecast sigue en claro en `config.json` (necesaria para conectarse; cifrarla con DPAPI es deuda). Cerrar sesión o cambiar la clave no corta los WebSockets ya abiertos.
