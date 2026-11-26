"""While test mode is on, the website API reads the sandbox database.

Every /api/public and /api/web request is served from the sandbox, except
those from crawlers and link previews, which keep getting the live site.
Writes that would reach the outside world are refused, responses are marked
no-store and noindex, and a readable marker cookie tells the website to use a
separate cart. When test mode is off the middleware only clears that marker.
"""
from __future__ import annotations

import json
import time

from starlette.requests import cookie_parser

from shop.services import test_mode

SCOPES = ("/api/public/", "/api/web/")
SAFE = {"GET", "HEAD", "OPTIONS"}


def _header(scope, name: bytes) -> str:
    # HTTP/2 clients may split cookies over several headers: read them all.
    return "; ".join(value.decode("latin-1") for key, value in scope.get("headers", ()) if key == name)


def _marker(scope) -> bool:
    raw = _header(scope, b"cookie")
    # Starlette's lenient parser: the stdlib one stops at Google's g_state={...}.
    return bool(raw) and cookie_parser(raw).get(test_mode.VIEW_COOKIE) == "1"


def _cookie_header(value: str, max_age: int) -> tuple[bytes, bytes]:
    return (b"set-cookie", f"{test_mode.VIEW_COOKIE}={value}; Max-Age={max_age}; Path=/; Secure; SameSite=Lax".encode())


class SandboxModeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not path.startswith(SCOPES):
            return await self.app(scope, receive, send)
        sandbox = test_mode.current()
        if sandbox is None or test_mode.crawler(_header(scope, b"user-agent")):
            if sandbox is None and _marker(scope):
                # Test mode ended: the website drops its test cart.
                async def clear(message):
                    if message["type"] == "http.response.start":
                        message = {**message, "headers": [*message.get("headers", []), _cookie_header("", 0)]}
                    await send(message)
                return await self.app(scope, receive, clear)
            return await self.app(scope, receive, send)
        if scope.get("method") not in SAFE and path.startswith("/api/web/") and path not in test_mode.ALLOWED_WRITES:
            body = json.dumps({"detail": "Сайт у тест-режимі: оформлення замовлень, вхід і коментарі тимчасово "
                                         "вимкнено. Спробуйте пізніше."}, ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": 403, "headers": [
                (b"content-type", b"application/json; charset=utf-8"), (b"cache-control", b"no-store"),
                (b"x-accord-test-mode", b"1"), (b"x-robots-tag", b"noindex, nofollow")]})
            await send({"type": "http.response.body", "body": body})
            return
        remaining = max(1, int(sandbox["expires"] - time.time()))

        async def marked(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in (b"cache-control", b"x-robots-tag", b"etag")]
                headers += [(b"cache-control", b"private, no-store"), (b"x-robots-tag", b"noindex, nofollow"),
                            (b"x-accord-test-mode", b"1"), (b"vary", b"User-Agent")]
                if not _marker(scope):
                    headers.append(_cookie_header("1", remaining))
                message = {**message, "headers": headers}
            await send(message)

        handle = test_mode.bind(sandbox)
        try:
            await self.app(scope, receive, marked)
        finally:
            test_mode.unbind(handle)
