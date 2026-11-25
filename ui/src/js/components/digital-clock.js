// Reloj digital grande para franjas compactas: hora de la emisora, día y fecha.
export function digitalClock(props) {
  const tz = props.timezone || "America/Bogota";
  const tfmt = new Intl.DateTimeFormat("es-CO", { timeZone: tz, hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dayf = new Intl.DateTimeFormat("es-CO", { timeZone: tz, weekday: "long" });
  const datef = new Intl.DateTimeFormat("es-CO", { timeZone: tz, day: "numeric", month: "short", year: "numeric" });

  const root = document.createElement("div");
  root.className = "dclock";
  const day = document.createElement("div"); day.className = "dc-day";
  const time = document.createElement("div"); time.className = "dc-time";
  const date = document.createElement("div"); date.className = "dc-date";
  root.append(day, time, date);

  const update = () => {
    const now = Date.now();
    day.textContent = dayf.format(now);
    time.textContent = tfmt.format(now);
    date.textContent = datef.format(now).replace(/\./g, "");
  };
  update();
  const id = setInterval(() => {
    if (!root.isConnected) { clearInterval(id); return; }
    update();
  }, 250);
  return root;
}
