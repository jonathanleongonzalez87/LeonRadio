"""Genera `dist/LeonRadio-demo.html`: la interfaz + el motor Python en UN solo archivo, sin servidor.

Se abre con doble clic (file://). El motor corre dentro del navegador con Pyodide (Python en WebAssembly),
así que se prueba el MISMO código que usa el servidor; no hay una copia del motor en JavaScript.
Requisitos: solo Python 3 (biblioteca estándar) para generarlo, e internet la primera vez que se abre
(el navegador descarga Pyodide, ~10 MB, y luego lo guarda).

    python tools/build_demo.py
"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui" / "src"
CORE = ROOT / "core" / "src"
OUT = ROOT / "dist" / "LeonRadio-demo.html"
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/"

# Módulos del motor que NO hacen falta (o no pueden correr) en el navegador
PY_EXCLUDE = {"server.py", "cli.py", "library.py"}

IMPORT = re.compile(r'^import\s*\{([^}]*)\}\s*from\s*"([^"]+)";?[ \t]*\n', re.M)
EXPORT = re.compile(r"^export\s+((?:async\s+)?(?:function\*?|const|let|class))\s+([A-Za-z_$][\w$]*)", re.M)


# ---------------------------------------------------------------- JavaScript (módulos ES -> un solo script)
def module_id(path: Path) -> str:
    return "m_" + re.sub(r"\W", "_", str(path.relative_to(UI / "js")))


def collect(path: Path, seen: set[Path], order: list[Path]) -> None:
    path = path.resolve()
    if path in seen:
        return
    seen.add(path)
    for m in IMPORT.finditer(path.read_text(encoding="utf-8")):
        collect(path.parent / m.group(2), seen, order)
    order.append(path)


def convert(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    exports = [m.group(2) for m in EXPORT.finditer(src)]
    src = EXPORT.sub(lambda m: f"{m.group(1)} {m.group(2)}", src)

    def imp(m: re.Match) -> str:
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
        parts = [n.replace(" as ", ": ") for n in names]
        target = module_id((path.parent / m.group(2)).resolve())
        return f"const {{ {', '.join(parts)} }} = {target};\n"

    src = IMPORT.sub(imp, src)
    return f"const {module_id(path)} = (() => {{\n{src}\nreturn {{ {', '.join(exports)} }};\n}})();"


def bundle_js() -> str:
    order: list[Path] = []
    collect(UI / "js" / "main.js", set(), order)
    return "\n\n".join(convert(p) for p in order)


# ---------------------------------------------------------------- CSS con fuentes incrustadas
def bundle_css() -> str:
    css = (UI / "css" / "tokens.css").read_text(encoding="utf-8") + "\n" + (UI / "css" / "app.css").read_text(encoding="utf-8")

    def font(m: re.Match) -> str:
        data = (UI / "css" / m.group(1)).resolve().read_bytes()
        return f"url(data:font/woff2;base64,{base64.b64encode(data).decode()})"

    return re.sub(r"url\(([^)]*\.woff2)\)", font, css)


# ---------------------------------------------------------------- Python del motor
def python_files() -> dict[str, str]:
    files: dict[str, str] = {}
    for p in sorted((CORE / "leonradio_core").rglob("*")):
        if p.is_file() and p.suffix in (".py", ".json") and p.name not in PY_EXCLUDE and "__pycache__" not in p.parts:
            files[str(p.relative_to(CORE)).replace("\\", "/")] = p.read_text(encoding="utf-8")
    files["leonradio/__init__.py"] = (CORE / "leonradio" / "__init__.py").read_text(encoding="utf-8")
    for p in sorted((ROOT / "addons").rglob("*")):
        if p.is_file() and p.suffix in (".py", ".toml") and "__pycache__" not in p.parts:
            files[str(p.relative_to(ROOT)).replace("\\", "/")] = p.read_text(encoding="utf-8")
    return files


BOOT = """
(function () {
  const PYODIDE = "%PYODIDE%";
  const files = JSON.parse(document.getElementById("lr-py-files").textContent);
  const status = (t) => { const s = document.getElementById("screen"); if (s) s.textContent = t; };
  const badge = document.getElementById("demo-badge");
  if (badge) badge.hidden = false;
  status("Cargando el motor de LeonRadio en el navegador… (la primera vez descarga unos 10 MB)");
  const loadScript = (src) => new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src; s.onload = ok; s.onerror = () => fail(new Error("no se pudo descargar " + src));
    document.head.append(s);
  });
  // La UI espera este objeto en lugar del servidor (ver ui/src/js/api.js)
  globalThis.LR_DEMO_BACKEND = (async () => {
    await loadScript(PYODIDE + "pyodide.js");
    const py = await loadPyodide({ indexURL: PYODIDE });
    await py.loadPackage(["sqlite3", "numpy"]);
    for (const [path, text] of Object.entries(files)) {
      const full = "/lr/" + path;
      py.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
      py.FS.writeFile(full, text);
    }
    py.runPython("import sys\\nsys.path.insert(0, '/lr')");
    const be = py.runPython("from leonradio_core.demo_web import create\\ncreate('/lr')");
    const listeners = new Set();
    let last = performance.now();
    setInterval(() => {
      const now = performance.now();
      const dt = Math.min(0.5, (now - last) / 1000);
      last = now;
      for (const ev of JSON.parse(be.tick(dt))) listeners.forEach((fn) => fn(ev));
    }, 100);
    return {
      info: () => JSON.parse(be.info()),
      editors: () => JSON.parse(be.editors()),
      draw: (id) => { const r = JSON.parse(be.draw(id)); if (r.error) throw new Error(r.error); return r; },
      run: (name, args) => { const r = JSON.parse(be.run(name, JSON.stringify(args || {}))); if (!r.ok) throw new Error(r.error); return r; },
      subscribe: (fn) => listeners.add(fn),
    };
  })();
  globalThis.LR_DEMO_BACKEND.catch((e) => status("No se pudo iniciar el motor en el navegador: " + e.message + " (¿hay internet para descargar Pyodide?)"));
})();
""".replace("%PYODIDE%", PYODIDE)


def main() -> None:
    html = (UI / "index.html").read_text(encoding="utf-8")
    html, n = re.subn(r'<link rel="stylesheet" href="css/[^"]+">\s*', "", html)
    assert n == 2, "index.html cambió: revisa los <link> de CSS"
    html = html.replace("</head>", f"<style>\n{bundle_css()}\n</style>\n</head>", 1)

    files_json = json.dumps(python_files(), ensure_ascii=False).replace("</", "<\\/")
    scripts = (
        f'<script id="lr-py-files" type="application/json">{files_json}</script>\n'
        f"<script>{BOOT}</script>\n<script>\n{bundle_js()}\n</script>"
    )
    tag = '<script type="module" src="js/main.js"></script>'
    assert tag in html, "index.html cambió: no encuentro el <script> de main.js"
    html = html.replace(tag, scripts, 1)
    html = html.replace("</head>", f'<meta name="generator" content="tools/build_demo.py {time.strftime("%Y-%m-%d %H:%M:%S")}">\n</head>', 1)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8", newline="\n")
    print(f"Listo: {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    print("Ábrelo con doble clic. La primera vez necesita internet para descargar Pyodide.")


if __name__ == "__main__":
    main()
