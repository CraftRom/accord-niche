"""Android app settings read from the environment (ACCORD_ANDROID_*).

Docker ``env_file`` passes quotes literally, so ``ACCORD_ANDROID_CERT_SHA256="AB:CD:…"``
reaches the process with the quotes. Values are cleaned here: surrounding quotes
and spaces are removed, lists may be separated by commas, semicolons or spaces,
and a certificate fingerprint is accepted in any case, with colons or as 64 hex
characters. When a variable is set but nothing in it is usable, one warning
names the variable and the reason (never the value), so an empty
``assetlinks.json`` or a refused Android sign-in has a visible cause.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re

log = logging.getLogger(__name__)

DEFAULT_PACKAGE = "ua.accordniche.shop"
_PACKAGE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+$")
_PRINT_COLONS = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){31}$")
_PRINT_PLAIN = re.compile(r"^[0-9A-F]{64}$")
_CLIENT_ID = re.compile(r"^[0-9]{6,32}-[a-z0-9]{8,64}\.apps\.googleusercontent\.com$")
_SEPARATORS = re.compile(r"[,;\s]+")
_QUOTES = "\"'"
_warned: set[tuple[str, str]] = set()


def _unquote(value: str) -> str:
    value = value.strip()
    while len(value) >= 2 and value[0] in _QUOTES and value[-1] == value[0]:
        value = value[1:-1].strip()
    return value.strip(_QUOTES + " \t")


def _items(raw: str) -> list[str]:
    return [item for item in (_unquote(part) for part in _SEPARATORS.split(_unquote(raw))) if item]


def _warn_once(name: str, raw: str, reason: str) -> None:
    # Keyed by a digest of the raw value: one warning per process per value,
    # and a new one after the administrator changes it.
    key = (name, hashlib.sha256(raw.encode()).hexdigest())
    if key not in _warned:
        _warned.add(key)
        log.warning("%s is set but %s; the value is ignored", name, reason)


def normalize_fingerprint(value: str) -> str | None:
    value = _unquote(value).upper()
    if _PRINT_PLAIN.fullmatch(value):
        return ":".join(value[i:i + 2] for i in range(0, 64, 2))
    return value if _PRINT_COLONS.fullmatch(value) else None


def cert_fingerprints() -> list[str]:
    raw = os.getenv("ACCORD_ANDROID_CERT_SHA256", "")
    items = _items(raw)
    prints: list[str] = []
    for item in items:
        value = normalize_fingerprint(item)
        if value and value not in prints:
            prints.append(value)
    if items and not prints:
        _warn_once("ACCORD_ANDROID_CERT_SHA256", raw,
                   "no SHA-256 fingerprint in it is valid (expected 32 hex pairs AA:BB:… or 64 hex characters)")
    return prints


def package_name() -> str | None:
    raw = os.getenv("ACCORD_ANDROID_PACKAGE", "")
    value = _unquote(raw) or DEFAULT_PACKAGE
    if _PACKAGE.fullmatch(value):
        return value
    _warn_once("ACCORD_ANDROID_PACKAGE", raw, "it is not a valid Android package name (e.g. ua.accordniche.shop)")
    return None


def google_android_client_ids() -> frozenset[str]:
    raw = os.getenv("ACCORD_GOOGLE_ANDROID_CLIENT_IDS", "")
    items = _items(raw)
    ids = frozenset(item for item in items if _CLIENT_ID.fullmatch(item))
    if items and not ids:
        _warn_once("ACCORD_GOOGLE_ANDROID_CLIENT_IDS", raw,
                   "no OAuth client ID in it is valid (expected <digits>-<id>.apps.googleusercontent.com)")
    return ids
