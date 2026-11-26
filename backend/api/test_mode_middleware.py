"""Routes the system administrator's test-mode browser to the sandbox database.

Only /api/public and /api/web requests carrying a valid signed test-mode cookie
are affected. They read the sandbox, cannot perform writes that reach the
outside world, and are marked no-store and noindex so no cache or crawler keeps
them. Everyone else never notices the middleware.
"""
from __future__ import annotations

import json
from starlette.requests import cookie_parser

from shop.services import test_mode

SCOPES = ("/api/public/", "/api/web/")
SAFE = {"GET", "HEAD", "OPTIONS"}


def _cookie(scope) -> str | None:
    # Starlette's lenient parser, the same one request.cookies uses. The
    # stdlib SimpleCookie stops at the first value it does not like, e.g.
    # Google sign-in's g_state={"i_l":0}, and then lost the test-mode cookie:
    # the banner (request.cookies) said «test mode» while every request read
    # the live database.
    # HTTP/2 clients may split cookies over several headers: read them all.
    raw = "; ".join(value.decode("latin-1") for name, value in scope.get("headers", ()) if name == b"cookie")
    return cookie_parser(raw).get(test_mode.COOKIE) if raw else None


class SandboxModeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not path.startswith(SCOPES) or path.startswith("/api/public/test-mode/"):
            return await self.app(scope, receive, send)
        raw = _cookie(scope)
        sandbox = test_mode.verify(raw) if raw else None
        if sandbox is None:
            return await self.app(scope, receive, send)
        if scope.get("method") not in SAFE and path.startswith("/api/web/") and path not in test_mode.ALLOWED_WRITES:
            body = json.dumps({"detail": "Тест-режим: оформлення, вхід і коментарі вимкнено. "
                                         "Вийдіть із тест-режиму, щоб користуватися магазином."},
                              ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": 403, "headers": [
                (b"content-type", b"application/json; charset=utf-8"), (b"cache-control", b"no-store"),
                (b"x-accord-test-mode", b"1"), (b"x-robots-tag", b"noindex, nofollow")]})
            await send({"type": "http.response.body", "body": body})
            return

        async def marked(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in (b"cache-control", b"x-robots-tag", b"etag")]
                headers += [(b"cache-control", b"private, no-store"), (b"x-robots-tag", b"noindex, nofollow"),
                            (b"x-accord-test-mode", b"1"), (b"vary", b"Cookie")]
                message = {**message, "headers": headers}
            await send(message)

        handle = test_mode.bind(sandbox)
        try:
            await self.app(scope, receive, marked)
        finally:
            test_mode.unbind(handle)
