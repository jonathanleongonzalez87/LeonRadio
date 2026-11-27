# Entidades compartidas

Una **entidad** es un dato que existe una sola vez y que varias estaciones usan. Regla de oro: **la crea y modifica solo su dueño; las demás la leen.** Si otra estación necesita un cambio, lo pide (issue) o lo hace el dueño.

Estado: `existe` = ya está en el código; `pendiente` = por crear. El marco común (S8) está en `core/src/leonradio_core/entities.py`; el panel **Entidades** muestra lo declarado, con su dueño y sus cantidades.

| Entidad | Qué es | Dueño (escribe) | La leen | Estado |
|---|---|---|---|---|
| **Pieza** (asset) | Archivo de audio de la biblioteca (música, jingle, pisador, separador, cuña) | Programación | Al Aire, Producción | existe (`assets`) |
| **Registro de emisión** | Qué sonó, cuándo y por dónde (historial) | Al Aire (se genera solo) | Programación, Producción, Dirección | existe (`playlog`, solo lectura en el marco) |
| **Artista / Álbum / Género** | Catálogo musical | Programación | Al Aire, Dirección | existe (`artista`, `album`, `genero`) |
| **Reloj / Parrilla / Franja** | Estructura horaria de la emisión | Programación | Al Aire, Dirección, Producción | pendiente |
| **Programa** | Espacio con concepto, identidad, formato y horario | Dirección | todas | pendiente |
| **Persona / Talento** | Locutores, productores, equipo | Dirección | todas | pendiente |
| **Invitado** | Persona que participa en un programa | Al Aire | Producción, Dirección | pendiente |
| **Escaleta / Guion** | Plan de un programa en emisión | Al Aire | Programación, Dirección | pendiente |
| **Cliente / Anunciante** | Quien contrata pauta o patrocinio | Producción | Programación, Al Aire | pendiente |
| **Compromiso** | Cuñas contratadas (cantidad o franja) | Producción | Programación (tandas), Al Aire | existe (`commitments`, solo lectura; a rediseñar en A6) |
| **Contrato / Pauta** | Contratos y patrocinios | Producción | Programación (tandas), Al Aire | pendiente |
| **Presupuesto / Inventario / Factura** | Administración y logística | Producción | Dirección | pendiente |
| **Usuario / Rol / Permiso** | Quién entra y qué puede hacer | Núcleo | todas | pendiente |

## Al crear o cambiar una entidad
1. Mira esta tabla: si ya existe, úsala; no crees otra parecida.
2. Si es nueva, agrégala aquí **en el mismo PR**, con dueño y lectores.
3. Modelo y tablas en el núcleo (S5/S8), con **migración**; nunca tablas privadas de una estación para datos compartidos. **Cambiar el esquema = agregar una función al final de `MIGRATIONS` (`core/src/leonradio_core/db.py`) + una prueba; nunca se edita una migración ya publicada** (la versión vive en `PRAGMA user_version`). El catálogo musical es la migración 3; Programa, Persona e Invitado llegan en la tarea S10.
4. Nombres en español, singular, sin tildes en los identificadores (`programa`, `compromiso`).
5. Datos de prueba inventados; nunca datos personales reales en el repositorio.

Aviso de privacidad: los campos `notas` son texto libre y pueden acabar con datos sensibles; no escribas teléfonos, correos ni documentos de personas ahí.

## Declarar una entidad nueva
Para agregar una entidad nueva a tu estación (ejemplo ficticio: **Sala** de grabación, dueña Producción):

1. **Mira esta tabla**: si existe, úsala (referénciala por id).
2. **Declárala** en `estaciones/produccion/entidades.py`:
```python
from ...entities import Entity, Field
SALA = Entity("sala", "sala", owner="produccion", label="Sala de grabación", about="Espacio donde se graba",
              fields=(Field("nombre", required=True), Field("nombre_norm", derived_from="nombre", unique=True),
                      Field("capacidad", "int"), Field("estado", choices=("libre", "ocupada"))))
# en estaciones/produccion/__init__.py:
def register(host):
    host.entities.declare(SALA)
    entities.register_crud(host, "produccion", ["sala"])      # sala.crear / .editar / .archivar / .restaurar
```
3. **Migración** en `estaciones/produccion/migraciones.py` (solo `sqlite3`, SQL literal, idempotente) y agregada al **final** de `MIGRATIONS` en `db.py` con el nombre `m<N>_…` (N = su posición):
```python
def m6_sala(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS sala (id INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL, nombre_norm TEXT NOT NULL UNIQUE, capacidad INTEGER, estado TEXT,
        archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, created_by TEXT NOT NULL, updated_by TEXT NOT NULL)""")
```
   Nunca se edita una migración ya publicada; para cambiar una tabla, otra migración (`ALTER TABLE … ADD COLUMN`).
4. **Referencias por id**: un campo `Field("cliente_id", "int", ref="cliente")` y `REFERENCES cliente(id)` en el SQL. Jamás copies el nombre del cliente a tu tabla. Leer la entidad de otra estación: `ctx.entities.list("cliente")`; escribirla: no se puede (pídelo a su dueña).
5. **Borrado**: no existe; `archivar` (y `restaurar`). Los comandos propios que escriban llevan `risk="datos"` y usan `host.entities.writer("produccion")` con `ctx.principal`.
6. **Prueba** (`core/tests/test_<tu_estacion>_entidades.py`, base `:memory:`, datos inventados):
```python
def test_sala(host):                               # fixture: Host(":memory:") con register_all
    assert entities.check_declaration(host.db, SALA) == []          # el SQL de la migración coincide con la declaración
    w = host.entities.writer("produccion")
    sid = w.create("sala", {"nombre": "Sala Uno", "capacidad": 4}, who="local")
    w.archive("sala", sid, who="local")
    assert host.entities.list("sala")["total"] == 0                 # archivada: sigue en la base
    with pytest.raises(sdk.PermissionDenied): host.entities.writer("direccion").create("sala", {"nombre": "X"}, who="local")
```
7. Agrega la fila a esta tabla (`existe`) **en el mismo PR**; una prueba del núcleo falla si falta.

La misma prueba de ejemplo vive en `core/tests/test_entities.py` con una entidad ficticia propia, de modo que el contrato está comprobado por el propio marco.

## Límites conocidos (S8)
- **Única excepción a «solo por el `writer`»:** `catalogo.sync` escribe `assets.artista_id/album_id` directamente con `host.db`; `assets` no es entidad gestionada y su dueña, Programación, es quien lo hace (la creación de artistas y álbumes sí pasa por el `writer`).
- **Addons no aislados:** `entities.read` no impide que un addon malicioso llegue a `host` y tome un `writer`; se resuelve con la tarea C1 (aislamiento de addons), igual que la nota de S6.
- **`risk="datos"` es hoy solo una etiqueta:** S7 debe hacerlo cumplir con permisos por usuario y rol.
- **Migración m3:** su relleno carga todas las piezas en memoria (~10 s y ~170 MB con 200.000 piezas) y debe seguir corriendo al abrir la base, antes de `playout.start()`.
