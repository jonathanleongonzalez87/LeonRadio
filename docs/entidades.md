# Entidades compartidas

Una **entidad** es un dato que existe una sola vez y que varias estaciones usan. Regla de oro: **la crea y modifica solo su dueño; las demás la leen.** Si otra estación necesita un cambio, lo pide (issue) o lo hace el dueño.

Estado: `existe` = ya está en el código; `pendiente` = por crear (tarea S8 define el modelo común).

| Entidad | Qué es | Dueño (escribe) | La leen | Estado |
|---|---|---|---|---|
| **Pieza** (asset) | Archivo de audio de la biblioteca (música, jingle, pisador, separador, cuña) | Programación | Al Aire, Producción | existe (`assets`) |
| **Registro de emisión** | Qué sonó, cuándo y por dónde (historial) | Al Aire (se genera solo) | Programación, Producción, Dirección | existe (`playlog`) |
| **Artista / Álbum / Género** | Catálogo musical | Programación | Al Aire, Dirección | pendiente |
| **Reloj / Parrilla / Franja** | Estructura horaria de la emisión | Programación | Al Aire, Dirección, Producción | pendiente |
| **Programa** | Espacio con concepto, identidad, formato y horario | Dirección | todas | pendiente |
| **Persona / Talento** | Locutores, productores, equipo | Dirección | todas | pendiente |
| **Invitado** | Persona que participa en un programa | Al Aire | Producción, Dirección | pendiente |
| **Escaleta / Guion** | Plan de un programa en emisión | Al Aire | Programación, Dirección | pendiente |
| **Cliente / Anunciante** | Quien contrata pauta o patrocinio | Producción | Programación, Al Aire | pendiente |
| **Contrato / Compromiso / Pauta** | Cuñas contratadas (cantidad o franja), patrocinios | Producción | Programación (tandas), Al Aire | pendiente |
| **Presupuesto / Inventario / Factura** | Administración y logística | Producción | Dirección | pendiente |
| **Usuario / Rol / Permiso** | Quién entra y qué puede hacer | Núcleo | todas | pendiente |

## Al crear o cambiar una entidad
1. Mira esta tabla: si ya existe, úsala; no crees otra parecida.
2. Si es nueva, agrégala aquí **en el mismo PR**, con dueño y lectores.
3. Modelo y tablas en el núcleo (S5/S8), con **migración**; nunca tablas privadas de una estación para datos compartidos.
4. Nombres en español, singular, sin tildes en los identificadores (`programa`, `compromiso`).
5. Datos de prueba inventados; nunca datos personales reales en el repositorio.
