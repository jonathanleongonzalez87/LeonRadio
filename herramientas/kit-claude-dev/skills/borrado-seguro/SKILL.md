---
name: borrado-seguro
description: Protocolo obligatorio para cualquier feature, script o comando que borre archivos o datos del usuario de forma automática o masiva (limpiezas, rotación de archivos, purgas, migraciones que eliminan filas). Leelo antes de escribir o correr un borrado.
---

# Borrado seguro

Las carpetas de trabajo suelen mezclar lo que genera la app con archivos personales del usuario. Un borrado mal apuntado es irreversible. Por eso nada se borra de una.

## Todo borrado automático
1. **Solo toca lo que la app creó**, identificado por un **registro** (una lista o tabla de lo que generó), nunca por un patrón suelto (`*.mp4`, "todo lo viejo de la carpeta").
2. **Re-chequea antes de tocar** cada candidato: la ruta resuelta está dentro de la carpeta esperada, es un archivo común (no carpeta, no enlace), el tamaño es plausible, sigue figurando en el registro.
3. **Nunca borra de una**: mueve a una **papelera visible** (por ejemplo `<carpeta>/_papelera/<fecha>/`) y elimina de verdad días después. Lo que el usuario rescató de la papelera no se vuelve a tocar.
4. **Se frena solo** si de golpe hay muchos más candidatos que lo normal (por ejemplo, más del doble del promedio o más de N): no borra nada y avisa.
5. **Tiene dry-run** (lista lo que haría sin hacerlo) y **deja log** de cada movimiento.

## Datos en una base
- Antes de un `DELETE` masivo, `DROP` o migración destructiva: respaldo (dump o rama de la base) y la consulta corrida primero como `SELECT` con el conteo.
- Borrado lógico (`borrado_en`) antes que físico cuando el dato puede hacer falta.
- Nunca contra producción "para probar": primero en una base de desarrollo.

## En la consola
- Mover a la papelera del sistema antes que `rm -rf` / `Remove-Item -Recurse` cuando no es una carpeta de build.
- La guarda `destructivos` del kit pide confirmación en esos casos: no la rodees, explicale al usuario qué se borra y por qué.
- Si un servicio (un hosting, un almacenamiento) no deja que un agente borre algo, lo borra el usuario: dale el comando o los pasos.
