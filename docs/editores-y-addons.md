# Editores, workspaces y addons

LeonRadio sigue el modelo de Blender: la pantalla es un conjunto de **áreas**; cada área aloja un **editor**
que se elige y se cambia según la necesidad. Los usuarios guardan sus disposiciones como **workspaces**
y la comunidad extiende el programa con **addons**.

## Conceptos
| Concepto | Qué es |
|---|---|
| **Área** | Hueco rectangular de la pantalla. Se divide, une y redimensiona. |
| **Editor** | Tipo de contenido de un área (Aire, Emisión, Biblioteca…). Se cambia desde un selector, como en Blender. |
| **Workspace** | Árbol de áreas + editores guardado con nombre (Aire, Programación, Producción, Comercial, Reportes). |
| **Comando** | Acción con nombre (`playout.next`, `library.scan`). Todo lo que hace un botón o atajo es un comando. |
| **Evento** | Algo que ocurrió (`track_started`, `break_due`, `commitment_at_risk`). |
| **Addon** | Paquete que registra editores, comandos, reglas, salidas o reportes. |

## Editores previstos
Aire · Próxima · Emisión · Auxiliares 1–4 · Biblioteca · Botonera (con Eventos y Explorador) · Relojes · Programación · Historial · Pauta y compromisos ·
Mezclador · Voice-track · Reportes · Monitor de streaming · Propiedades · Consola Python · Info.

## Reglas de diseño
1. **Los editores incluidos usan la misma API que un addon.** Si algo no se puede hacer como addon, la API está incompleta.
2. **La emisión nunca depende de un addon.** El audio vive en su propio proceso; los addons en otro, con comunicación por API.
   Un addon que falle no puede sacar la emisora del aire.
3. **Los addons ven copias de solo lectura del estado** y actúan enviando comandos.
4. **Permisos declarados** en el manifiesto y aprobados por el usuario al instalar.
5. **API versionada** (semver). Un addon declara `api_version` y el programa se niega a cargar los incompatibles.
6. **Python primero:** el panel se describe en Python y la UI lo dibuja con los tokens de marca;
   un componente JS propio es opcional (waveforms, canvas).

## Estructura de un addon
```
mi_addon/
├─ leonradio_addon.toml     # manifiesto
├─ __init__.py              # register() / unregister()
└─ web/                     # opcional: componentes JS
```

```toml
# leonradio_addon.toml
id = "com.ejemplo.reloj-clima"
name = "Reloj del clima"
version = "0.1.0"
api_version = "0.1"
license = "GPL-3.0-or-later"
permissions = ["library.read", "playlog.read", "network"]
```

```python
# __init__.py — boceto de la API (puede cambiar en la v0)
import leonradio as lr

class ClimaEditor(lr.Editor):
    id = "clima.panel"
    label = "Clima"

    def draw(self, ui, ctx):
        ui.label(f"Temperatura: {ctx.state.get('clima.temp', '--')} °C")
        ui.button("Leer ahora", command="clima.leer")

@lr.command("clima.leer")
def leer(ctx):
    ...

def register():   lr.register_editor(ClimaEditor); lr.register_command(leer)
def unregister(): lr.unregister_editor(ClimaEditor)
```

## Ciclo «probar y luego incorporar»
1. El autor desarrolla en `%APPDATA%\LeonRadio\addons\` con recarga en caliente (modo desarrollo).
2. Lo prueba en la emisora de pruebas (RRC) con un workspace propio.
3. Si es bueno, se propone por *pull request* a `addons/` (comunitarios) o se promueve a `core/builtin/`.
4. Todo addon incluido trae pruebas automáticas y su manifiesto.

## Licencias
- **Código (`core/`, `ui/`, addons incluidos):** GPL-3.0-or-later, como Blender. Los addons que usan la API quedan abiertos.
- **Documentación y diseño:** CC BY-SA 4.0.
- **Isotipo hexagonal y marca:** derechos reservados (ver `NOTICE.md`).

## Fases
F0.5 construye: gestor de áreas y workspaces, registro de editores y comandos, bus de eventos,
API de addons v0, 3 editores incluidos (Aire, Emisión, Historial) y un addon de ejemplo.
F5 añade gestor de addons (instalar/activar/actualizar), plantilla y guía para terceros.
