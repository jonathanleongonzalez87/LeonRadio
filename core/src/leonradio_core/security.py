"""Middleware ASGI: Origin (CSRF y secuestro de WebSocket), Host (DNS-rebinding), tamaño del cuerpo y cabeceras."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from fastapi import HTTPException

from . import paths

MAX_BODY = 256 * 1024
MAX_WS_MESSAGE = 64 * 1024
MAX_WS_EVENTS, MAX_WS_MONITOR = 32, 16
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
HEADERS = [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"), (b"referrer-policy", b"no-referrer")]


class ConnectionLimit:
    """Cuenta conexiones simultáneas (un oyente del monitor consume ~176 KB/s)."""

    def __init__(self, limit: int) -> None:
        self.limit, self.count = limit, 0

    def acquire(self) -> bool:
        if self.count >= self.limit:
            return False
        self.count += 1
        return True

    def release(self) -> None:
        self.count = max(0, self.count - 1)


class SecurityMiddleware:
    def __init__(self, app, *, strict_host: bool = False) -> None:
        self.app, self.strict_host = app, strict_host

    async def __call__(self, scope, receive, send) -> None:
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope["headers"]}
        host = headers.get(b"host", b"").decode("latin-1").lower()
        if self.strict_host and not paths.host_header_is_loopback(host):
            await self._reject(scope, receive, send, 421, "Host no permitido")
            return
        origin = headers.get(b"origin")
        if origin is not None and (kind == "websocket" or scope["method"] in UNSAFE):
            text = origin.decode("latin-1").lower()
            if text == "null" or urlsplit(text).netloc != host:
                await self._reject(scope, receive, send, 403, "Origen no permitido")
                return
        if kind == "websocket":
            await self.app(scope, receive, send)
            return
        length = headers.get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
            await self._reject(scope, receive, send, 413, "Cuerpo demasiado grande")
            return
        seen = 0

        async def counted():
            nonlocal seen
            msg = await receive()
            seen += len(msg.get("body", b"")) if msg["type"] == "http.request" else 0
            if seen > MAX_BODY:
                raise HTTPException(413, "Cuerpo demasiado grande")   # HTTPException: FastAPI no lo convierte en 400
            return msg

        async def with_headers(msg) -> None:
            if msg["type"] == "http.response.start":
                have = {k.lower() for k, _v in msg.get("headers", [])}
                msg = {**msg, "headers": [*msg.get("headers", []), *[h for h in HEADERS if h[0] not in have]]}
            await send(msg)

        await self.app(scope, counted, with_headers)

    @staticmethod
    async def _reject(scope, receive, send, status: int, detail: str) -> None:
        if scope["type"] == "websocket":
            await receive()                                  # websocket.connect
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"detail": detail}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *HEADERS]})
        await send({"type": "http.response.body", "body": body})
