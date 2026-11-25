# leonradio-core

Motor de **LeonRadio**, automatizador de radio (Python). Parte de [LeonRadio](https://github.com/jonathanleongonzalez87/leonradio-docs).

Estación de prueba: **RRC – Rockland Radio Colombia**.

## Estado (v0.0.1)
- [x] Esquema SQLite: `assets`, `commitments`, `playlog`
- [x] Escáner de biblioteca (clasifica por carpeta, lee etiquetas, detecta duplicados por hash)
- [x] Importador `.m3u` con rutas de otra máquina
- [x] Historial inmutable (`playlog`), exportación CSV y cumplimiento de compromisos
- [ ] Motor de reproducción (segue, crossfade, ducking, VU) — hito 1
- [ ] API FastAPI + WebSocket para la UI

## Uso
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\leonradio scan "C:\ruta\a\Rockland Radio"
```

> La música y el audio de la emisora **no** van en este repositorio (`.gitignore`).

## Licencia
CC BY-SA 4.0 (ver `LICENSE`). Creative Commons no recomienda sus licencias para software; si más adelante se necesita una licencia de código (MIT/GPL), el cambio se hace en un commit explícito.
