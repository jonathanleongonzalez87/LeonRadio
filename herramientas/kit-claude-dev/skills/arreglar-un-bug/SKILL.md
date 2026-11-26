---
name: arreglar-un-bug
description: El ciclo para arreglar un bug una sola vez y que no vuelva - mirar lo que falló de verdad, reproducirlo con un test que falla, arreglar, verificar, medir lo no determinista y dejar una regresión. Leelo antes de arreglar cualquier bug reportado por el usuario o visto en uso real.
---

# Arreglar un bug

Un error en uso real no se ve como un stack trace: se ve como un dato que no se guardó. Este es el ciclo para que cada problema se arregle una vez y no vuelva.

## El ciclo (en orden)
1. **Mirar lo que falló de verdad.** Logs, registro de errores, la consulta a la base, la respuesta real de la API. Empezá por ahí, no por lo que suponés (skill `verificar-antes-de-suponer`). Si la app no registra errores, el primer arreglo es registrarlos: dónde, con qué y sin datos sensibles.
2. **Reproducirlo con un test que FALLE.** Primero el test, después el arreglo: si no falla antes, no prueba nada. Datos inventados, nunca datos reales de personas (los tests se commitean).
3. **Arreglar la causa, no el síntoma.** El cambio mínimo. Si el arreglo obvio es justo lo que causó el bug, dejá un comentario de por qué no se hace así.
4. **Verificar.** `typecheck`, `lint` y `test` pasan. Nunca `--no-verify`.
5. **Medir lo que no es determinista.** Si el comportamiento depende de un modelo de IA, de OCR, del azar o del tiempo, una corrida no prueba nada: corré una evaluación sobre un conjunto fijo de casos y compará el número con el de antes del cambio.
6. **Probarlo como lo usa el usuario.** En el build de producción (no en modo desarrollo), en el ancho de pantalla real (celular si lo usan ahí).
7. **Cerrar el círculo.** Cada falla real deja algo permanente: el test de regresión del paso 2, o un caso nuevo en el conjunto de evaluación. Si no queda nada, va a volver. Si el bug revela una regla que se repetiría, va al `CLAUDE.md` o al skill del área con su **Por qué**.

## Reglas que no se rompen
- **Datos personales jamás al repo ni a los logs.** El registro limpia query strings y cadenas que parecen documentos o tokens.
- **El registro nunca rompe la app**: si falla escribir el log, se ignora.
- **Nunca adivinar a quién pertenece un dato**: si no hay coincidencia clara, se reporta sin cargar.
- **Windows**: renombrar un archivo encima de otro que alguien tiene abierto falla con `EPERM`. Las escrituras a un mismo archivo van por una sola cola, con respaldo.
- **Modo desarrollo ≠ producción**: algo "lento" en `dev` puede ser la compilación de cada pantalla. Medí en el build de producción.
