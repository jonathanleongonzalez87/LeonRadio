# Guía básica para desarrollar LeonRadio

Para quien se suma al proyecto. Léela entera una vez (10 minutos); después sirve de consulta.

## 1. La idea en 30 segundos
LeonRadio es **una sola plataforma** para gestionar una emisora. Tiene cuatro **estaciones de trabajo**, cada una con herramientas a la medida de su función, que comparten la misma información y a veces los mismos paneles:

| Estación | Para qué sirve | Código |
|---|---|---|
| **Al Aire** | Emisión, escaleta, guiones, invitados, audiencia | `builtin/` (hoy) → `estaciones/al_aire/` |
| **Programación** | Parrilla, librería, artistas, fórmulas, rotaciones | `estaciones/programacion/` |
| **Dirección** | Identidad de programas, formatos, talento, estrategia | `estaciones/direccion/` |
| **Producción** | Presupuestos, contratos, patrocinios, pauta, facturación, informes | `estaciones/produccion/` |

Tres conceptos que **no se mezclan**: la *estación* decide qué espacio ve el usuario; el *rol y los permisos* deciden qué puede hacer; la *entidad* es el dato compartido (un Programa, un Artista, un Compromiso). Más detalle en [estaciones.md](estaciones.md) y [entidades.md](entidades.md).

## 2. Preparar tu equipo (Windows)
1. Instala **Python 3.12+** (python.org, marcando *Add python.exe to PATH*) y **Git**. Para usar el kit de desarrollo, también **Node 18+**.
2. Clona el repositorio y crea tu entorno (fuera de OneDrive):
   ```powershell
   git clone https://github.com/jonathanleongonzalez87/LeonRadio.git
   cd LeonRadio\core
   python -m venv $HOME\.venvs\leonradio
   $HOME\.venvs\leonradio\Scripts\python -m pip install -e ".[api,audio,dev]" httpx
   $HOME\.venvs\leonradio\Scripts\python -m pytest -q          # deben pasar todas
   ```
3. Arranca sin sonido para desarrollar: `leonradio serve --audio null --library "<carpeta de la emisora>"` y abre http://127.0.0.1:8765/.
4. El audio de la emisora **no se versiona**: pide la carpeta de pruebas (RRC) al dueño del proyecto.
5. Kit de desarrollo (reglas, guardas, agentes): está en `Referentes/kit-claude-dev` (fuera del repo). `node kit.mjs instalar` y abre una sesión nueva de Claude Code.

## 3. Cómo se trabaja una tarea
1. **Elige una tarea** de [ROADMAP.md](ROADMAP.md) (la tabla tiene estación y responsable). Si no está asignada, avisa en el issue antes de empezar.
2. **Un issue por tarea**, con el id en el título (`[A6] Contratos y pauta`) y la etiqueta de su estación (`estacion:produccion`…). Usa la plantilla *Tarea*.
3. **Una rama por tarea**: `feat/<id>-<slug>` (ej. `feat/a6-contratos`), `fix/<slug>` o `docs/<slug>`. Nunca trabajes directo en `main`.
4. **Trabaja dentro de tu estación.** No edites archivos de otra estación; si necesitas algo de ella, abre un issue o pídelo en el PR. El **núcleo común** (`sdk.py`, `engine/`, base de datos, usuarios) lo revisan los dueños de las estaciones afectadas.
5. **Pruebas**: toda función nueva lleva pruebas (`core/tests/`). Deben pasar todas antes del PR.
6. **Commits** chicos con [conventional commits](https://www.conventionalcommits.org/es/): `feat(produccion): contratos básicos [A6]`. En este proyecto **se hacen cuando el dueño lo pide**; si eres colaborador externo, commitea tú y sube tu rama.
7. **Pull Request** hacia `main` con la plantilla: qué cambia, cómo se probó, capturas si hay pantalla, y si toca el núcleo. Un PR = una tarea.
8. **Revisión y merge**: lo decide el dueño del proyecto. Al aprobar, el estado de la tarea pasa a `hecho`; cuando se prueba con datos reales y se acepta, a `verificado`.

## 4. Anatomía de un panel (editor)
Un panel es una clase con `draw(ui, ctx)` que describe su interfaz; la UI la dibuja con la marca. Ejemplo mínimo para Producción:

```python
# core/src/leonradio_core/estaciones/produccion/__init__.py
from ... import sdk
from ...uischema import UI

class ContratosPanel(sdk.Editor):
    id, label, icon = "produccion.contratos", "Contratos", "📄"
    station = "produccion"                      # aparece en la columna «Producción» del menú de editores

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        ui.label("CONTRATOS", "accent")
        ui.table(["Cliente", "Vigencia"], [["Ejemplo S.A.", "2026"]])
        ui.button("Nuevo contrato", "produccion.contrato_nuevo")

def register(host):
    sdk.register_editor(ContratosPanel)
    host.register_command("produccion.contrato_nuevo", lambda ctx: ...)
```
- Elementos disponibles: `label`, `kv`, `button`, `table`, `form` (campos que se guardan al salir), `tabs`, `slider`, `row/column` y componentes propios (`ui.custom`). Ver [editores-y-addons.md](editores-y-addons.md).
- Los **comandos** son funciones registradas con un nombre (`estacion.accion`). Los errores esperables se lanzan como `ValueError`: la interfaz muestra el mensaje.
- **Paneles compartidos**: un panel sin `station` (Historial, Metadatos, Reloj…) sirve a todas las estaciones. Para reutilizar un panel de otra estación dentro del tuyo, acóplalo en **Varios** (pestañas) o dibújalo con `ctx.draw_editor("id")`.
- Un panel que tiene campos de texto, `<iframe>` o perillas **no se destruye al redibujar**: ver las reglas en `CLAUDE.md`.

## 5. Cómo compartir información sin duplicarla
- Cada **entidad tiene un dueño** (una estación) que es la única que la crea y modifica; las demás la **leen**. La lista está en [entidades.md](entidades.md).
- Antes de crear una tabla, mira si la entidad ya existe. Si es nueva: agrégala a `entidades.md` en el mismo PR, con su dueño y quién la lee.
- Los datos van en la **base compartida** (tarea S5), con migraciones; no en archivos sueltos por estación.
- Lo que una estación necesita de otra se pide por la entidad, no copiando campos. Los resultados regresan por la misma vía (p. ej. el historial de emisión alimenta los informes de Producción).

## 6. Trazabilidad: dónde mirar y qué actualizar
| Qué | Dónde | Quién lo actualiza |
|---|---|---|
| Plan y estado de cada tarea | [ROADMAP.md](ROADMAP.md) | El responsable propone en su PR; el dueño aprueba |
| % de avance | `node scripts/avance.mjs` → [ESTADO.md](ESTADO.md) | Se regenera, nunca a mano |
| Trabajo en curso | Issues y PR con etiqueta de estación | Cada responsable |
| Decisiones de diseño | `docs/planes/<id>.md` | Quien planifica la tarea |
| Lecciones aprendidas | [aprendizajes.md](aprendizajes.md) y `CLAUDE.md` › Reglas aprendidas | Al cerrar una tarea grande |

## 7. Reglas que no se negocian
- **Seguridad**: nada de claves en el repo ni en el chat; rutas del navegador validadas; la app no se expone a la red sin autenticación (tarea S6).
- **Marca**: [marca.md](marca.md). El nombre «Jonathan León» no aparece en la interfaz.
- **Audio**: nunca dejar sonando sin avisar; pruebas con `--audio null`. La emisión arranca en pausa.
- **Reencuadrar, no rediseñar**: no cambies el contenido de un panel ajeno; propón el cambio en un issue.
- **Pocos tokens**: pedidos acotados a Claude, una tarea por sesión, salidas resumidas.

## 8. Si te atascas
Abre un issue con la etiqueta `ayuda` y tu estación, o pregunta en el PR. Con Claude Code: `/ciclo-de-desarrollo` para una tarea grande del ROADMAP; para algo chico, pídelo directo (el kit elige el camino según el tamaño del cambio).
