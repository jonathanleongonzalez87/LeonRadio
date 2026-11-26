// Ficha de metadatos del fichero elegido: carátula + etiquetas (intérprete, título, álbum, año, género, comentario) + ruta.
// Las props son JSON y NO son de confianza: todo va con textContent; la carátula solo se acepta si es una ruta /api/cover/<n>.
const FIELDS = [
  ["artist", "Intérprete"], ["year", "Año"],
  ["title", "Título"], ["genre", "Género"],
  ["album", "Álbum"], ["comment", "Comentario"],
];
const KINDS = { audio: "Audio", event: "Evento", other: "Otro" };

export function tagCard(props) {
  const root = document.createElement("div");
  root.className = "tagcard";

  const art = document.createElement("div");
  art.className = "tag-art";
  if (typeof props.cover === "string" && /^\/api\/cover\/\d+$/.test(props.cover)) {
    const img = document.createElement("img");
    img.alt = "";
    img.onerror = () => img.remove();                  // sin carátula: queda el hexágono de la marca
    img.src = props.cover;
    art.append(img);
  }
  const body = document.createElement("div");
  body.className = "tag-body";
  const grid = document.createElement("div");
  grid.className = "tag-grid";
  FIELDS.forEach(([key, label]) => {
    const k = document.createElement("span"); k.className = "tag-k"; k.textContent = label;
    const v = document.createElement("span"); v.className = "tag-v"; v.textContent = String(props[key] || "");
    v.title = v.textContent;
    grid.append(k, v);
  });
  body.append(grid);
  const path = document.createElement("div");
  path.className = "tag-path";
  path.textContent = props.path ? String(props.path) : `${KINDS[props.file] || ""} · ${props.kind || ""}`;
  path.title = path.textContent;
  body.append(path);
  root.append(art, body);
  return root;
}
