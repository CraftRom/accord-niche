"""API answers are no-store, except public files that choose a public lifetime.

Run from backend: python -m pytest -q tests_accord/test_public_cache.py
"""
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from api.security_middleware import SecurityMiddleware, keeps_own_cache


def client():
    app = FastAPI()

    @app.get('/api/public/file')
    def public_file():
        return Response('x', headers={'Cache-Control': 'public, max-age=300'})

    @app.post('/api/public/file')
    def public_post():
        return Response('x', headers={'Cache-Control': 'public, max-age=300'})

    @app.get('/api/public/plain')
    def plain():
        return {'ok': True}

    @app.get('/api/public/private')
    def private():
        return Response('x', headers={'Cache-Control': 'private, max-age=60'})

    @app.get('/api/public/cookie')
    def cookie():
        response = Response('x', headers={'Cache-Control': 'public, max-age=300'})
        response.set_cookie('a', 'b')
        return response

    @app.get('/api/web/file')
    def web_file():
        return Response('x', headers={'Cache-Control': 'public, max-age=300'})

    app.add_middleware(SecurityMiddleware)
    return TestClient(app)


def test_public_file_keeps_its_lifetime():
    c = client()
    assert c.get('/api/public/file').headers['cache-control'] == 'public, max-age=300'


def test_everything_else_is_no_store():
    c = client()
    assert c.post('/api/public/file').headers['cache-control'] == 'no-store'
    assert c.get('/api/public/plain').headers['cache-control'] == 'no-store'
    assert c.get('/api/public/private').headers['cache-control'] == 'no-store'
    assert c.get('/api/public/cookie').headers['cache-control'] == 'no-store'
    assert c.get('/api/web/file').headers['cache-control'] == 'no-store'


def test_rule_directly():
    public = [(b'cache-control', b'public, max-age=60')]
    assert keeps_own_cache('/api/public/seo/sitemap.xml', 'HEAD', public)
    assert not keeps_own_cache('/api/public/seo/sitemap.xml', 'GET', public * 2)
    # Test mode marks sandbox answers private, no-store: they are never cached.
    assert not keeps_own_cache('/api/public/catalog', 'GET', [(b'cache-control', b'private, no-store')])

