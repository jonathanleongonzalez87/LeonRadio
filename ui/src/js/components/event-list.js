// Lista de eventos programados con cuenta regresiva local (el árbol no cambia cada segundo,
// así el panel no parpadea ni pierde su posición de desplazamiento).
//   props.events = [{ name, kind, minute }]  → ocurren cada hora en ese minuto (de ejemplo, hasta F3).
export function eventList(props) {
  const events = (Array.isArray(props.events) ? props.events : [])
    .filter((e) => Number.isFinite(e.minute)).map((e) => ({ ...e, minute: ((e.minute % 60) + 60) % 60 }));

  const root = document.createElement("div");
  root.className = "u-tabwrap";
  const table = document.createElement("table");
  table.className = "u-tab";
  const head = document.createElement("tr");
  ["Evento", "Tipo", "Faltan"].forEach((h) => { const th = document.createElement("th"); th.textContent = h; head.append(th); });
  const thead = document.createElement("thead"); thead.append(head);
  const body = document.createElement("tbody");
  table.append(thead, body);
  root.append(table);

  const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const update = () => {
    const now = new Date();
    const sec = now.getUTCMinutes() * 60 + now.getUTCSeconds();
    const rows = events
      .map((e) => ({ e, left: (((e.minute * 60 - sec) % 3600) + 3600) % 3600 || 3600 }))
      .sort((a, b) => a.left - b.left);
    body.replaceChildren(...rows.map(({ e, left }, i) => {
      const tr = document.createElement("tr");
      if (i === 0) tr.className = "next";
      [String(e.name ?? ""), String(e.kind ?? ""), mmss(left)].forEach((t) => {
        const td = document.createElement("td"); td.textContent = t; tr.append(td);
      });
      return tr;
    }));
  };
  update();
  const id = setInterval(() => { if (!root.isConnected) clearInterval(id); else update(); }, 1000);
  return root;
}
