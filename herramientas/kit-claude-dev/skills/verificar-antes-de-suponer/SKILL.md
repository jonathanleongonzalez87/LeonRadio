---
name: verificar-antes-de-suponer
description: Las cuatro reglas para no trabajar de forma errática, sacadas de un caso real que costó ocho deploys. Leelo antes de deducir un dato del dominio del usuario en vez de leerlo, antes de iterar contra producción, cuando algo falla "a veces", y cuando el usuario te corrige lo mismo por segunda vez.
---

# Verificar antes de suponer

No es una guía de estilo: es la autopsia de un caso concreto. Si lo que vas a hacer se parece a alguno de los cuatro errores, pará.

## El caso
Había que etiquetar los videos de un canal por tipo. **El primer mensaje del usuario decía "según su playlist".** Salió bien recién a la octava vuelta.

## Regla 1 — Si el usuario nombró la fuente, esa ES la fuente
Se probó duración, palabras del título, de la descripción, si había sido en vivo… Todas inferencias sobre un dato que **ya estaba clasificado a mano** en tres playlists.

> Leer lo que el usuario ya curó cuesta una llamada. Deducirlo cuesta ocho deploys y sale mal igual.

Señal de alarma: estás escribiendo una heurística (`duración <= X`, `si el título contiene…`) para algo que es del usuario —su catálogo, sus clientes, su canal—. Preguntá dónde está el dato antes.

## Regla 2 — Las premisas externas se verifican, no se recuerdan
Se dio por hecho que un video corto de la plataforma dura 60 s o menos. **Ya eran 3 minutos.** Ese dato viejo mandó a la categoría equivocada a todo lo de 60 a 180 s, y se propagó varias vueltas porque se veía como un bug de clasificación, no de premisa.

Cualquier límite, cuota o formato de un tercero que vayas a codificar como constante: confirmalo en la documentación o en los datos reales, y dejá el número con su fecha en un comentario.

## Regla 3 — Mirar los datos UNA vez antes de iterar
Las primeras cinco vueltas fueron: suponer → deploy → esperar el build → mirar → suponer otra vez. Cuando se desplegó un diagnóstico que devolvía **lo que el servidor ve**, la respuesta apareció completa en un paso.

**Un diagnóstico temporal cuesta un deploy. Adivinar cuesta cinco.** Si no podés ver los datos desde tu máquina (credenciales de producción que no se pueden leer), poné el diagnóstico protegido, leelo, borralo.

## Regla 4 — Antes de diagnosticar, descartá que el instrumento esté roto
Dos veces se concluyó "la lista vuelve vacía en producción" y se cambió código. **No había bug**: el script de medición se logueaba 10 veces seguidas y el login permitía 5 cada 5 minutos. A partir del sexto devolvía la pantalla de login, en 150 ms.

**Una respuesta demasiado rápida no consultó nada.** Si algo falla "a veces", mirá primero los tiempos y el instrumento:

| Trampa | Cómo se nota |
| --- | --- |
| Rate limit propio | Vuelve el login o un 429, muy rápido |
| Caché por instancia | Dos cargas seguidas dan distinto sin que cambie nada |
| Deploy en vuelo | Medís el build anterior; confirmá con una marca del código nuevo |

## Lo que sí funcionó
- Leer la verdad de la base o de la API y **pegar el número medido** en vez de "debería andar".
- Dejar en el código el error que se cometió, no solo la solución: el comentario que dice por qué NO se hace de la forma obvia es lo que evita que alguien lo "arregle" de vuelta.
- Cuando el usuario corrige algo dos veces, la que está mal es la interpretación, no él.
