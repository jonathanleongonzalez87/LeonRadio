"""Clave de acceso, sesiones y el único punto de autenticación (`current_principal`).

Modo local (127.0.0.1): no se pide nada. Modo red (`--host` no loopback): hace falta la clave, salvo para el propio
PC de la emisora (socket loopback + `Host` loopback). La clave solo se guarda como hash `scrypt` en `config.json`.
S7 sustituye el cuerpo de `current_principal` y de `POST /api/login` por usuarios; las rutas no cambian.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, WebSocketException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.requests import HTTPConnection

from . import paths, settings

COOKIE = "leonradio_sesion"
SESSION_SECONDS = 12 * 3600
MAX_SESSIONS = 64
MAX_FAILS, FAIL_WINDOW, BLOCK_SECONDS, MAX_TRACKED_IPS = 5, 10 * 60, 15 * 60, 1000
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ234567"      # Base32 sin 0/O/1/I/L
_SCRYPT = (14, 8, 1)                             # log2(n), r, p


# --- clave -----------------------------------------------------------------
def new_key() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def _norm(key: str) -> bytes:
    return "".join(str(key).upper().split()).replace("-", "").encode("utf-8")


def hash_key(key: str) -> str:
    n, r, p = _SCRYPT
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(_norm(key), salt=salt, n=2 ** n, r=r, p=p)
    return "$".join(["scrypt", str(n), str(r), str(p), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()])


def verify(key: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        want = base64.b64decode(digest)
        got = hashlib.scrypt(_norm(key), salt=base64.b64decode(salt), n=2 ** int(n), r=int(r), p=int(p), dklen=len(want))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


def rotate() -> str:
    """Clave nueva (es lo que hace `leonradio clave`): la anterior y las sesiones abiertas dejan de valer."""
    global _hash_cache
    key = new_key()
    settings.set_auth_hash(hash_key(key))
    _hash_cache = None
    return key


def ensure_key() -> str | None:
    """Si no hay clave la crea y la devuelve (para mostrarla UNA vez); si ya hay, devuelve None."""
    return None if settings.get_auth().get("key_hash") else rotate()


_hash_cache: tuple[tuple, str] | None = None


def current_hash() -> str:
    """Hash vigente; se relee solo si cambió `config.json` (un `stat` por petición)."""
    global _hash_cache
    p = settings.path()
    try:
        st = p.stat()
        sig = (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        return ""
    if _hash_cache is None or _hash_cache[0] != sig:
        _hash_cache = (sig, str(settings.get_auth().get("key_hash") or ""))
    return _hash_cache[1]


def _fingerprint(key_hash: str) -> str:
    return hashlib.sha256(key_hash.encode("utf-8")).hexdigest()[:16]


# --- sesiones y bloqueo -----------------------------------------------------
class SessionStore:
    """En memoria (proceso único). Una sesión vale solo mientras la huella del hash de la clave no cambie."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._items: dict[str, tuple[float, str]] = {}

    def create(self, fingerprint: str) -> str:
        token = secrets.token_urlsafe(32)
        self._items[token] = (self.clock() + SESSION_SECONDS, fingerprint)
        while len(self._items) > MAX_SESSIONS:
            del self._items[next(iter(self._items))]
        return token

    def valid(self, token: str | None, fingerprint: str) -> bool:
        item = self._items.get(token or "")
        if item is None:
            return False
        if item[0] < self.clock() or not hmac.compare_digest(item[1], fingerprint):
            self._items.pop(token, None)
            return False
        return True

    def delete(self, token: str | None) -> None:
        self._items.pop(token or "", None)


class PairingStore:
    """Enlaces de un solo uso (QR) para que un teléfono entre sin teclear la clave. En memoria, 10 min de vida."""

    TTL, MAX = 600, 16

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._items: dict[str, float] = {}

    def create(self) -> str:
        now = self.clock()
        self._items = {t: e for t, e in self._items.items() if e > now}
        token = secrets.token_urlsafe(24)
        self._items[token] = now + self.TTL
        while len(self._items) > self.MAX:
            del self._items[next(iter(self._items))]
        return token

    def redeem(self, token: str) -> bool:
        """Consume el enlace: solo vale una vez."""
        exp = self._items.pop(token, 0.0)
        return exp > self.clock()


class LoginGuard:
    """5 fallos en 10 min desde la misma IP del socket bloquean 15 min (también la clave correcta)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._fails: dict[str, list[float]] = {}
        self._blocked: dict[str, float] = {}

    def wait(self, ip: str) -> int:
        """Segundos que faltan para poder intentar de nuevo (0 = puede)."""
        until = self._blocked.get(ip, 0.0)
        left = until - self.clock()
        if left > 0:
            return int(left) + 1
        if until:
            self._blocked.pop(ip, None)
            self._fails.pop(ip, None)
        return 0

    def fail(self, ip: str) -> None:
        now = self.clock()
        recent = [t for t in self._fails.get(ip, []) if now - t < FAIL_WINDOW] + [now]
        self._fails.pop(ip, None)
        self._fails[ip] = recent
        if len(recent) >= MAX_FAILS:
            self._blocked[ip] = now + BLOCK_SECONDS
        while len(self._fails) > MAX_TRACKED_IPS:
            now = self.clock()
            old = next((ip for ip in self._fails if self._blocked.get(ip, 0.0) <= now), None)   # no se desalojan bloqueos vigentes
            if old is None:
                break
            del self._fails[old]
            self._blocked.pop(old, None)

    def ok(self, ip: str) -> None:
        self._fails.pop(ip, None)
        self._blocked.pop(ip, None)


# --- quién hace la petición ---------------------------------------------------
@dataclass(frozen=True)
class Principal:
    id: str                  # "local" (modo local o PC de la emisora) o "clave"; S7 le añade user_id
    role: str = "admin"      # hoy único rol; S7 lo calcula del usuario


@dataclass
class AuthState:
    require_auth: bool = False
    sessions: SessionStore = field(default_factory=SessionStore)
    guard: LoginGuard = field(default_factory=LoginGuard)
    pairing: PairingStore = field(default_factory=PairingStore)


def is_local_client(conn: HTTPConnection) -> bool:
    """El propio PC: dirección REAL del socket loopback y `Host` loopback. Nunca se mira `X-Forwarded-For`."""
    client = conn.client
    return bool(client and paths.is_loopback(client.host) and paths.host_header_is_loopback(conn.headers.get("host", "")))


def _resolve(conn: HTTPConnection) -> Principal | None:
    state: AuthState = conn.app.state.auth
    if not state.require_auth or is_local_client(conn):
        return Principal("local")
    h = current_hash()
    if h and state.sessions.valid(conn.cookies.get(COOKIE), _fingerprint(h)):
        return Principal("clave")
    return None


def current_principal(conn: HTTPConnection) -> Principal:
    """Dependencia de FastAPI para HTTP y WebSocket: el único lugar donde se decide el acceso."""
    who = _resolve(conn)
    if who is None:
        if conn.scope["type"] == "websocket":
            raise WebSocketException(code=1008)
        raise HTTPException(401, "Se necesita la clave de acceso")
    return who


# --- endpoints de sesión ---------------------------------------------------
class LoginBody(BaseModel):
    key: str = Field(max_length=200)


NO_STORE = {"Cache-Control": "no-store"}


def build_router(station: Callable[[], str], lan: Callable[[], list[str]] = lambda: []) -> APIRouter:
    router = APIRouter()

    @router.get("/api/session")
    def session(request: Request) -> JSONResponse:
        who = _resolve(request)
        state: AuthState = request.app.state.auth
        required = state.require_auth and not is_local_client(request)
        data = {"auth_required": required, "authenticated": who is not None, "station": station()}
        wait = state.guard.wait(request.client.host) if required and who is None and request.client else 0
        if wait:                                    # el bloqueo sobrevive a recargar la página
            data["retry_after"] = wait
        return JSONResponse(data, headers=NO_STORE)

    @router.post("/api/login")
    def login(body: LoginBody, request: Request) -> JSONResponse:
        state: AuthState = request.app.state.auth
        if not state.require_auth:
            return JSONResponse({"ok": True}, headers=NO_STORE)
        ip = request.client.host if request.client else "?"
        wait = state.guard.wait(ip)
        if wait:
            return JSONResponse({"detail": "Demasiados intentos", "retry_after": wait},
                                status_code=429, headers={**NO_STORE, "Retry-After": str(wait)})
        h = current_hash()
        if not (h and verify(body.key, h)):
            state.guard.fail(ip)
            return JSONResponse({"detail": "Clave incorrecta"}, status_code=401, headers=NO_STORE)
        state.guard.ok(ip)
        resp = JSONResponse({"ok": True}, headers=NO_STORE)
        resp.set_cookie(COOKIE, state.sessions.create(_fingerprint(h)), max_age=SESSION_SECONDS, path="/",
                        httponly=True, samesite="strict", secure=request.url.scheme == "https")
        return resp

    @router.get("/conectar")
    def connect_page(request: Request) -> HTMLResponse:
        """Solo desde el PC de la emisora: muestra el QR (enlace de un solo uso) para abrir el control en el teléfono."""
        state: AuthState = request.app.state.auth
        if not is_local_client(request) or request.headers.get("sec-fetch-site", "none") in ("cross-site", "same-site"):
            raise HTTPException(403, "Solo desde el PC de la emisora")
        if not state.require_auth:
            return HTMLResponse(_page("<p>El modo red está desactivado: este programa solo se abre en este PC. "
                                      "Inicia con <b>iniciar-leonradio.bat</b> para conectar el teléfono.</p>"),
                                headers=NO_STORE)
        port = request.url.port or 8765
        ips = lan()
        if not ips:
            return HTMLResponse(_page("<p>No encuentro una red local. Conecta este PC al mismo Wi-Fi que el teléfono "
                                      "y recarga.</p>"), headers=NO_STORE)
        token = state.pairing.create()
        cards = "".join(
            f'<div class="c">{_qr(f"http://{ip}:{port}/p/{token}")}<p>{ip}</p></div>' for ip in ips[:3])
        body = (f"<h1>Abrir en el teléfono</h1><p>Conecta el teléfono al <b>mismo Wi-Fi</b> que este PC y escanea el "
                f"código con la cámara.</p><div class='r'>{cards}</div>"
                "<p class='s'>El código vale una vez y 10 minutos; recarga la página para uno nuevo. "
                "Si no abre, prueba con el otro código (cada uno es una red del PC) y revisa que el Firewall de Windows "
                "permita LeonRadio en redes privadas. Los datos móviles no sirven: tiene que ser la misma red.</p>")
        return HTMLResponse(_page(body), headers=NO_STORE)

    @router.get("/p/{token}")
    def pair(token: str, request: Request) -> RedirectResponse:
        state: AuthState = request.app.state.auth
        ip = request.client.host if request.client else "?"
        if state.guard.wait(ip):
            raise HTTPException(429, "Demasiados intentos")
        h = current_hash()
        if not (state.require_auth and h and len(token) <= 64 and state.pairing.redeem(token)):
            if len(token) != 32:                    # un QR vencido (forma válida) no bloquea al teléfono
                state.guard.fail(ip)
            raise HTTPException(404, "Enlace vencido o ya usado: genera otro código en el PC (/conectar)")
        state.guard.ok(ip)
        resp = RedirectResponse("/", status_code=303, headers=NO_STORE)
        resp.set_cookie(COOKIE, state.sessions.create(_fingerprint(h)), max_age=SESSION_SECONDS, path="/",
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")
        return resp

    @router.post("/api/logout")
    def logout(request: Request) -> JSONResponse:
        state: AuthState = request.app.state.auth
        state.sessions.delete(request.cookies.get(COOKIE))
        resp = JSONResponse({"ok": True}, headers=NO_STORE)
        resp.delete_cookie(COOKIE, path="/")
        return resp

    return router



def _qr(url: str) -> str:
    import segno
    return segno.make(url, error="m").svg_inline(scale=6, border=2, dark="#111", light="#fff")


def _page(body: str) -> str:
    return ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Conectar el teléfono</title><style>body{font:16px system-ui;background:#1b1a17;color:#eee;"
            "max-width:640px;margin:2rem auto;padding:0 1rem}.r{display:flex;gap:1rem;flex-wrap:wrap}"
            ".c{background:#fff;color:#111;padding:.5rem;border-radius:8px;text-align:center}.c svg{display:block}"
            ".s{opacity:.7;font-size:14px}</style>" + body)
