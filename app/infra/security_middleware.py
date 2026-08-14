from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import (
    ALLOWED_ORIGINS,
    GLOBAL_RATE_LIMIT,
    GLOBAL_RATE_WINDOW_SECONDS,
    LOGIN_RATE_LIMIT,
    LOGIN_RATE_WINDOW_SECONDS,
    MAX_JSON_BYTES,
    MODE,
)


class _BodyTooLarge(Exception):
    pass


class RequestSizeMiddleware:
    """İstek gövdesini ASGI receive seviyesinde sınırlar; chunked istekler de kapsam içindedir."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        limit = MAX_JSON_BYTES
        declared = headers.get("content-length")
        if declared:
            try:
                if int(declared) > limit:
                    response = JSONResponse({"detail": "İstek gövdesi izin verilen boyutu aşıyor."}, status_code=413)
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse({"detail": "Geçersiz Content-Length başlığı."}, status_code=400)
                await response(scope, receive, send)
                return

        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            response = JSONResponse({"detail": "İstek gövdesi izin verilen boyutu aşıyor."}, status_code=413)
            await response(scope, receive, send)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def _cleanup(self, now: float) -> None:
        self._calls += 1
        if self._calls % 1000:
            return
        stale = []
        max_window = max(LOGIN_RATE_WINDOW_SECONDS, GLOBAL_RATE_WINDOW_SECONDS)
        for key, q in self._events.items():
            while q and now - q[0] >= max_window:
                q.popleft()
            if not q:
                stale.append(key)
        for key in stale:
            self._events.pop(key, None)

    def _allowed(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            q = self._events[key]
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "bilinmiyor"
        if request.url.path.endswith("/auth/login") or request.url.path.endswith("/auth/setup"):
            if not self._allowed(f"login:{ip}", LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW_SECONDS):
                return JSONResponse({"detail": "Çok fazla giriş denemesi. Daha sonra tekrar deneyin."}, status_code=429)
        if not self._allowed(f"global:{ip}", GLOBAL_RATE_LIMIT, GLOBAL_RATE_WINDOW_SECONDS):
            return JSONResponse({"detail": "İstek sınırı aşıldı. Daha sonra tekrar deneyin."}, status_code=429)
        return await call_next(request)


class OriginGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                parsed = urlparse(origin)
                normalized = f"{parsed.scheme}://{parsed.netloc}"
                expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
                if normalized != expected and normalized not in ALLOWED_ORIGINS:
                    return JSONResponse({"detail": "İstek kaynağına izin verilmiyor."}, status_code=403)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "require-trusted-types-for 'script'"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        if MODE == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
