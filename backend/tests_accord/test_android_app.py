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


@pytest.fixture
def fresh_warnings(monkeypatch):
    from shop import android_config
    monkeypatch.setattr(android_config, '_warned', set())
    monkeypatch.delenv('ACCORD_ANDROID_PACKAGE', raising=False)
    return android_config


def links(response=None):
    return asyncio.run(public_catalog.android_asset_links(response or Response()))


def prints_of(statement):
    [item] = statement
    return item['target']['sha256_cert_fingerprints']


def test_asset_links_empty_until_fingerprint(monkeypatch, fresh_warnings, caplog):
    monkeypatch.delenv('ACCORD_ANDROID_CERT_SHA256', raising=False)
    response = Response()
    assert links(response) == []
    assert response.headers['Cache-Control'] == 'no-store'
    assert not caplog.records  # not configured is not an error


def test_invalid_fingerprint_gives_empty_list_and_one_warning(monkeypatch, fresh_warnings, caplog):
    monkeypatch.setenv('ACCORD_ANDROID_CERT_SHA256', '"garbage-value"')
    with caplog.at_level('WARNING', logger='shop.android_config'):
        response = Response()
        assert links(response) == []
        assert links() == []
    assert response.headers['Cache-Control'] == 'no-store'
    warnings = [r for r in caplog.records if r.name == 'shop.android_config']
    assert len(warnings) == 1
    assert 'ACCORD_ANDROID_CERT_SHA256' in warnings[0].getMessage()
    assert 'garbage' not in warnings[0].getMessage()


@pytest.mark.parametrize('raw', [
    f'"{PRINT}"', f"'{PRINT}'", f'  {PRINT}  ', PRINT.lower(), PRINT.replace(':', ''),
    f'"{PRINT.replace(":", "").lower()}"', f'{PRINT.lower()},bad',
])
def test_fingerprint_formats(monkeypatch, fresh_warnings, raw):
    monkeypatch.setenv('ACCORD_ANDROID_CERT_SHA256', raw)
    response = Response()
    statement = links(response)
    assert statement[0]['relation'] == ['delegate_permission/common.handle_all_urls']
    assert statement[0]['target'] == {'namespace': 'android_app', 'package_name': 'ua.accordniche.shop',
                                      'sha256_cert_fingerprints': [PRINT]}
    assert response.headers['Cache-Control'] == 'public, max-age=300'


def test_several_fingerprints_by_space_comma_semicolon(monkeypatch, fresh_warnings):
    second = ':'.join(['C0'] * 32)
    third = 'd1' * 32
    monkeypatch.setenv('ACCORD_ANDROID_CERT_SHA256', f'"{PRINT} {second.lower()};{third}, {PRINT}"')
    assert prints_of(links()) == [PRINT, second, ':'.join(['D1'] * 32)]


def test_package_quotes_and_invalid_package(monkeypatch, fresh_warnings, caplog):
    monkeypatch.setenv('ACCORD_ANDROID_CERT_SHA256', PRINT)
    monkeypatch.setenv('ACCORD_ANDROID_PACKAGE', '"ua.accordniche.shop" ')
    assert links()[0]['target']['package_name'] == 'ua.accordniche.shop'
    monkeypatch.setenv('ACCORD_ANDROID_PACKAGE', 'not a package')
    with caplog.at_level('WARNING', logger='shop.android_config'):
        response = Response()
        assert links(response) == []
    assert response.headers['Cache-Control'] == 'no-store'
    assert [r for r in caplog.records if 'ACCORD_ANDROID_PACKAGE' in r.getMessage()]


def test_quoted_android_client_ids(monkeypatch, fresh_warnings, caplog):
    monkeypatch.setenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', f'"{ANDROID}"')
    assert website_shop.android_client_ids() == frozenset({ANDROID})
    monkeypatch.setenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', f"'{ANDROID} {OTHER}'")
    assert website_shop.android_client_ids() == frozenset({ANDROID, OTHER})
    monkeypatch.setenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', '"nonsense"')
    with caplog.at_level('WARNING', logger='shop.android_config'):
        assert website_shop.android_client_ids() == frozenset()
        assert website_shop.android_client_ids() == frozenset()
    assert len([r for r in caplog.records if 'ACCORD_GOOGLE_ANDROID_CLIENT_IDS' in r.getMessage()]) == 1


def test_quoted_android_client_id_signs_in(google_keys, monkeypatch, fresh_warnings):
    monkeypatch.setenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', f'"{ANDROID}"')
    assert verify(token(google_keys, azp=ANDROID))['sub'] == '42'


def test_cache_headers_survive_the_api_middleware(monkeypatch, fresh_warnings):
    """The security middleware makes API answers no-store; assetlinks keeps its own header."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.security_middleware import SecurityMiddleware
    app = FastAPI()
    app.include_router(public_catalog.router, prefix='/api/public')
    app.add_middleware(SecurityMiddleware)
    client = TestClient(app)
    monkeypatch.delenv('ACCORD_ANDROID_CERT_SHA256', raising=False)
    empty = client.get('/api/public/android/assetlinks.json')
    assert empty.json() == [] and empty.headers['cache-control'] == 'no-store'
    assert empty.headers['content-type'].startswith('application/json')
    monkeypatch.setenv('ACCORD_ANDROID_CERT_SHA256', f'"{PRINT}"')
    filled = client.get('/api/public/android/assetlinks.json')
    assert prints_of(filled.json()) == [PRINT]
    assert filled.headers['cache-control'] == 'public, max-age=300'
    assert filled.headers['content-type'].startswith('application/json')


def test_nginx_serves_asset_links_before_dotfile_block():
    from pathlib import Path
    conf = (Path(__file__).resolve().parents[2] / 'deploy/nginx/accord-domain-website.conf').read_text()
    assert 'location = /.well-known/assetlinks.json' in conf
    assert '/api/public/android/assetlinks.json' in conf
    block = next(line for line in conf.splitlines() if 'location = /.well-known/assetlinks.json' in line)
    # Cache-Control and Content-Type must come from the API, not from nginx.
    assert 'add_header' not in block and 'expires' not in block and 'default_type' not in block
