# LeonRadio

Automatizador de radio con experiencia de estación vintage, hecho para 2026.
Estación de prueba: **RRC – Rockland Radio Colombia** (https://rocklandradio.co/).

```
leonradio/
├─ core/   Motor Python: biblioteca, historial de emisión, (audio y programación en camino)
├─ ui/     Interfaz HTML: consola vintage, tokens de marca y maquetas (prototypes/)
├─ docs/   Arquitectura y especificaciones (historial de emisión)
└─ ROADMAP.md
```

Tablero: [Proyecto LeonRadio](https://github.com/users/jonathanleongonzalez87/projects/1) · Issues: pestaña *Issues* de este repo.

## Empezar
```powershell
cd core
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

## Documentos
- [ROADMAP.md](ROADMAP.md)
- [docs/arquitectura.md](docs/arquitectura.md)
- [docs/historial-de-emision.md](docs/historial-de-emision.md)
- [docs/editores-y-addons.md](docs/editores-y-addons.md) — editores, workspaces y addons
- [core/README.md](core/README.md) · [ui/README.md](ui/README.md)

## Licencia
- Código (`core/`, `ui/`): **GPL-3.0-or-later** (`core/LICENSE`, `ui/LICENSE`).
- Documentación y diseño: **CC BY-SA 4.0** (`LICENSE`).
- Marca «Jonathan León»: derechos reservados — ver [NOTICE.md](NOTICE.md).

El audio de las emisoras no se versiona.
