"""ACCORD Android app support: Google sign-in from the app and App Links.

Run from backend: python -m pytest -q tests_accord/test_android_app.py
"""
import asyncio
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, Response

from api.routers import public_catalog, website_shop

WEB = '123456789012-webclient1234.apps.googleusercontent.com'
ANDROID = '123456789012-androidapp5678.apps.googleusercontent.com'
OTHER = '999999999999-strangerapp9999.apps.googleusercontent.com'
PRINT = ':'.join(['AB'] * 32)


@pytest.fixture
def google_keys(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid='test-kid', alg='RS256', use='sig')
    monkeypatch.setattr(website_shop, '_google_jwks', {'keys': [public]})
    monkeypatch.setattr(website_shop, '_google_jwks_until', time.monotonic() + 600)
    return key


def token(key, **claims):
    now = int(time.time())
    payload = {'iss': 'https://accounts.google.com', 'aud': WEB, 'sub': '42', 'iat': now,
               'exp': now + 600, 'email': 'buyer@example.com', 'email_verified': True, **claims}
    return jwt.encode(payload, key, algorithm='RS256', headers={'kid': 'test-kid'})


def verify(raw):
    return asyncio.run(website_shop._google_identity(raw, WEB))


def test_website_token_still_accepted(google_keys, monkeypatch):
    monkeypatch.delenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', raising=False)
    assert verify(token(google_keys, azp=WEB))['sub'] == '42'
    assert verify(token(google_keys))['sub'] == '42'


def test_android_token_needs_configured_client(google_keys, monkeypatch):
    monkeypatch.delenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', raising=False)
    with pytest.raises(HTTPException) as refused:
        verify(token(google_keys, azp=ANDROID))
    assert refused.value.status_code == 401
    monkeypatch.setenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', f' {ANDROID} , not-a-client-id')
    assert verify(token(google_keys, azp=ANDROID))['email'] == 'buyer@example.com'


def test_unknown_android_client_and_wrong_audience_refused(google_keys, monkeypatch):
    monkeypatch.setenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', ANDROID)
    with pytest.raises(HTTPException):
        verify(token(google_keys, azp=OTHER))
    # The Android client may stand in only as the authorized party, never as audience.
    with pytest.raises(HTTPException):
        verify(token(google_keys, aud=ANDROID, azp=ANDROID))


def test_asset_links_empty_until_fingerprint(monkeypatch):
    monkeypatch.delenv('ACCORD_ANDROID_CERT_SHA256', raising=False)
    assert asyncio.run(public_catalog.android_asset_links(Response())) == []
    monkeypatch.setenv('ACCORD_ANDROID_CERT_SHA256', 'garbage')
    assert asyncio.run(public_catalog.android_asset_links(Response())) == []


def test_asset_links_statement(monkeypatch):
    monkeypatch.setenv('ACCORD_ANDROID_CERT_SHA256', PRINT.lower() + ',bad')
    monkeypatch.setenv('ACCORD_ANDROID_PACKAGE', 'ua.accordniche.shop')
    [statement] = asyncio.run(public_catalog.android_asset_links(Response()))
    assert statement['relation'] == ['delegate_permission/common.handle_all_urls']
    assert statement['target'] == {'namespace': 'android_app', 'package_name': 'ua.accordniche.shop',
                                   'sha256_cert_fingerprints': [PRINT]}
    monkeypatch.setenv('ACCORD_ANDROID_PACKAGE', 'not a package')
    assert asyncio.run(public_catalog.android_asset_links(Response())) == []


def test_nginx_serves_asset_links_before_dotfile_block():
    from pathlib import Path
    conf = (Path(__file__).resolve().parents[2] / 'deploy/nginx/accord-domain-website.conf').read_text()
    assert 'location = /.well-known/assetlinks.json' in conf
    assert '/api/public/android/assetlinks.json' in conf
