# LeonRadio · core

Motor de **LeonRadio**, automatizador de radio (Python). Parte de [LeonRadio](../README.md).

Estación de prueba: **RRC – Rockland Radio Colombia**.

## Estado (v0.0.1)
- [x] Esquema SQLite: `assets`, `commitments`, `playlog`
- [x] Escáner de biblioteca (clasifica por carpeta, lee etiquetas, detecta duplicados por hash)
- [x] Importador `.m3u` con rutas de otra máquina
- [x] Historial inmutable (`playlog`), exportación CSV y cumplimiento de compromisos
- [x] Plataforma F0.5: `sdk` (editores, comandos, permisos), `addons` (manifiesto + carga), `uischema` (UI declarativa), `events`, servidor FastAPI + WebSocket
- [x] Editores incluidos: Aire, Próxima, Emisión, Historial, VU, Reloj, Dial/RDS, Botonera (Eventos y Explorador) y 4 listas Auxiliares (reproductor **simulado**, sin audio)
- [ ] Motor de reproducción (segue, crossfade, ducking, VU) — hito 1

## Uso
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\leonradio scan "C:\ruta\a\Rockland Radio"
```

> La música y el audio de la emisora **no** van en este repositorio (`.gitignore`).

## Licencia
GPL-3.0-or-later (`LICENSE`).
