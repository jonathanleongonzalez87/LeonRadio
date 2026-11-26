# ROADMAP (tier list)

`node scripts/avance.mjs` calcula el avance a partir de la tabla de tareas.

## Pesos y valores

| Tier | Qué es | Peso en el total |
|---|---|---|
| S | Núcleo: sin esto no sirve | 45% |
| A | Muy importante | 30% |
| B | Pulido | 15% |
| C | Extras | 10% |

Dentro de cada tier pesan los **puntos** (1 = chica, 2 = mediana, 3 = grande).

| Estado | Valor |
|---|---|
| `pendiente` | 0 |
| `en curso` | 0,3 |
| `hecho` | 0,8 (implementado, revisado, con pruebas) |
| `verificado` | 1 (probado con datos reales y aprobado por el usuario) |

| Tier del producto | Condición |
|---|---|
| D · Prototipo | S < 50% |
| C · Alfa | S ≥ 50% |
| B · MVP usable | S al 100% |
| A · Producto sólido | S y A al 100% |
| S · Completo | S, A y B al 100% |

## Reglas de edición
- Solo el ciclo cambia la columna `estado` (después de la revisión o de QA).
- El arquitecto puede proponer filas nuevas o partir una fila. Un id no se reutiliza.
- El id empieza con la letra de su tier (S1, A3, B2…). `depende` lleva ids separados por coma, o `—`.

## Tareas

| id | tier | función | puntos | estado | depende |
|---|---|---|---|---|---|
| S1 | S | Esqueleto: proyecto, typecheck, lint, test y build pasando | 1 | pendiente | — |
| S2 | S | <función principal> | 3 | pendiente | S1 |
| A1 | A | <algo muy importante> | 2 | pendiente | S2 |
| B1 | B | <pulido> | 1 | pendiente | A1 |
| C1 | C | <extra> | 1 | pendiente | — |
