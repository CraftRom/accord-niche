"""IndexNow: tell Bing, Yandex, Seznam, Naver… right away that a page changed.

Google reads sitemap.xml (lastmod) and does not use IndexNow; its sitemap
"ping" endpoint was retired in 2023, so sitemap.xml in Search Console is the
Google path. IndexNow is enabled only when ACCORD_INDEXNOW_KEY is set; the key
is published at https://<domain>/<key>.txt as the protocol requires.

Changed URLs are collected for a few seconds and sent in one request, so a
bulk import does not fire hundreds of calls. Failures are logged and never
reach the editor who saved the product or the article.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

from shop.domain_security import DOMAIN

log = logging.getLogger(__name__)
ENDPOINT = "https://api.indexnow.org/indexnow"
ORIGIN = f"https://{DOMAIN}"
DEBOUNCE_SECONDS = 5.0
_KEY = re.compile(r"^[A-Za-z0-9-]{8,128}$")
_pending: set[str] = set()
_task: asyncio.Task | None = None


def key() -> str | None:
    value = os.getenv("ACCORD_INDEXNOW_KEY", "").strip()
    return value if _KEY.fullmatch(value) else None


def _own(url: str) -> bool:
    return url == ORIGIN or url.startswith(ORIGIN + "/")


async def _send(urls: list[str]) -> None:
    secret = key()
    if not secret or not urls:
        return
    import httpx
    body = {"host": DOMAIN, "key": secret, "keyLocation": f"{ORIGIN}/{secret}.txt", "urlList": urls[:10000]}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(ENDPOINT, json=body)
        if response.status_code >= 400:
            log.warning("indexnow rejected %s urls: HTTP %s", len(urls), response.status_code)
    except Exception as exc:  # network trouble must never break saving
        log.warning("indexnow unavailable: %s", type(exc).__name__)


async def _flush_later() -> None:
    global _task
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
        urls = sorted(_pending)
        _pending.clear()
        await _send(urls)
    finally:
        _task = None


def notify(*urls: str) -> None:
    """Queue changed public URLs (sitemap.xml is always added)."""
    global _task
    if not key():
        return
    clean = {url for url in urls if url and _own(url)}
    if not clean:
        return
    _pending.update(clean | {ORIGIN + "/sitemap.xml"})
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _task is None or _task.done():
        _task = loop.create_task(_flush_later())
