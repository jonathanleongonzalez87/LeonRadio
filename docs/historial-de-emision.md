# Historial de emisión (as-run log)

Objetivo: tener **prueba de lo que sonó**, no de lo que se programó. Sirve para tres cosas distintas:

| Uso | Qué necesita | Filtro típico |
|---|---|---|
| **Derechos de autor / conexos** | título, artista, ISRC, compositor, editorial, duración real | `kind = music` |
| **Compromisos comerciales** | qué cuña, cuántas veces, en qué ventana y franja horaria | `kind = spot` + `commitment_id` |
| **Operación y auditoría** | fuente (auto/live/cart), salida (fm/stream), fallas, saltos | todo |

## Principios
1. **Inmutable.** Cada emisión es un hecho; se copian título/artista/ISRC en la fila para que editar o borrar el archivo no altere reportes pasados.
2. **UTC.** Se guarda en UTC; los reportes convierten a la hora local de la emisora.
3. **Estado real.** `completed` solo si sonó completo; `skipped`/`interrupted`/`failed` quedan registrados con los ms reproducidos.
4. **Todo lo que suena se registra:** música, jingles, pisadores, separadores, cuñas, botonera y voz en vivo.

## Tablas (en `core/src/leonradio_core/db.py`)
- `assets` — biblioteca, con `isrc`, `composer`, `publisher`.
- `commitments` — pauta contratada: cliente, campaña, contrato, cuña, `plays_required`, ventana y franja.
- `playlog` — el historial.

## Reportes (F4)
- **Música para sociedades de gestión.** Pendiente confirmar a cuál(es) reporta RRC y su formato exacto; el CSV base ya incluye los campos comunes.
- **Constancia de pauta** por cliente: fecha/hora de cada emisión + contratado vs emitido.
- **Cumplimiento:** `commitment_status()` devuelve contratado, emitido y faltante; F4 añade alertas antes del vencimiento.
- **Operación:** fallas, silencios, interrupciones.

## Pendiente de definir
- Formato oficial de reporte de la(s) sociedad(es) de gestión de RRC.
- Si las cuñas se reparten por franja (daypart) obligatoria o solo por cantidad.
- Retención del historial (recomendado: indefinida, con copia de seguridad).
