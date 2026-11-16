"""Regression tests: no cross-domain access to dashboard sessions or admin API."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from shop.config import settings
from api.browser_sessions import check_browser_request

ROOT=Path(__file__).resolve().parents[2]

def request(origin=None, method='POST', host='dashboard.accordniche.pp.ua'):
    headers=[(b'host',host.encode()), (b'x-dashboard-request',b'1')]
    if origin is not None:
        headers.append((b'origin', origin.encode()))
    return Request({'type':'http','method':method,'path':'/api/auth/browser-login', 'scheme':'https',
                    'headers': headers, 'server':(host,443),'client':('127.0.0.1',12345)})

@pytest.mark.parametrize('origin', ['https://accordniche.pp.ua','https://shop.accordniche.pp.ua',
                                      'https://attacker.example', None])
def test_dashboard_rejects_other_origins(origin):
    with patch.object(settings,'dashboard_public_url','https://dashboard.accordniche.pp.ua'):
        with pytest.raises(HTTPException) as exc:
            check_browser_request(request(origin))
        assert exc.value.status_code==403

def test_dashboard_accepts_only_dashboard_origin():
    with patch.object(settings,'dashboard_public_url','https://dashboard.accordniche.pp.ua'):
        check_browser_request(request('https://dashboard.accordniche.pp.ua'))

def test_website_and_dashboard_https_cookies_are_host_only():
    # Isolate the two tiny helpers: importing the full commerce router also
    # imports optional Telegram aiogram, unavailable in the minimal CI runtime.
    import ast
    source=(ROOT/'backend/api/routers/website_shop.py').read_text()
    tree=ast.parse(source)
    functions={node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
    names=['_secure','_session_cookie','_csrf_cookie']
    module=ast.Module(body=[functions[n] for n in names],type_ignores=[])
    namespace={'Request':Request,'SESSION_NAME':'accord_session','CSRF_NAME':'accord_csrf'}
    exec(compile(module,'website_shop.py','exec'),namespace)
    req=request('https://dashboard.accordniche.pp.ua',host='accordniche.pp.ua')
    req.scope['scheme']='https'
    req.scope['headers'].append((b'x-forwarded-proto',b'https'))
    assert namespace['_session_cookie'](req)=='__Host-accord_session'
    assert namespace['_csrf_cookie'](req)=='__Host-accord_csrf'

def test_split_compose_never_publishes_backend_or_database():
    import yaml
    compose=yaml.safe_load((ROOT/'deploy/docker-compose.domains.yml').read_text())
    for name in ('api','db','redis','bot'):
        assert 'ports' not in compose['services'][name]
    for name in ('accord-website','accord-miniapp','accord-dashboard'):
        assert all(p.startswith('127.0.0.1:') for p in compose['services'][name]['ports'])
    assert compose['services']['bot']['profiles'] == ['bot']

def test_no_public_admin_api_in_storefront_configs():
    public=(ROOT/'deploy/nginx/accord-domain-website.conf').read_text()
    mini=(ROOT/'deploy/nginx/accord-domain-miniapp.conf').read_text()
    assert 'location ^~ /api/ { return 404; }' in public
    assert 'location /api/ { return 404; }' in mini
    assert 'location ^~ /api/web/' in public
    assert 'location /api/shop/' in mini
    assert 'location ~ ^/api/shop/orders/[0-9]+/chat/photo$' in mini
    assert 'location = /api/auth/login { return 404; }' in (ROOT/'deploy/nginx/accord-domain-dashboard.conf').read_text()

@pytest.mark.asyncio
@pytest.mark.parametrize('host,path,expected', [
    ('accordniche.pp.ua','/api/auth/browser-login',404),
    ('accordniche.pp.ua','/api/public/catalog',200),
    ('accordniche.pp.ua','/api/web/session',200),
    ('accordniche.pp.ua','/api/public/blog/example',200),
    ('accordniche.pp.ua','/api/web/blog/posts/1/mine',200),
    ('accordniche.pp.ua','/api/blog/posts',404),
    ('shop.accordniche.pp.ua','/api/orders',404),
    ('shop.accordniche.pp.ua','/api/blog/posts',404),
    ('shop.accordniche.pp.ua','/api/shop/config',200),
    ('shop.accordniche.pp.ua','/api/telegram/abcdef/12345678',200),
    ('dashboard.accordniche.pp.ua','/api/web/profile',404),
    ('dashboard.accordniche.pp.ua','/api/auth/login',404),
    ('dashboard.accordniche.pp.ua','/api/orders',200),
    ('dashboard.accordniche.pp.ua','/api/blog/posts',200),
    ('dashboard.accordniche.pp.ua','/api/web/blog/posts/1/mine',404),
    ('localhost','/api/health',200),
    ('localhost','/api/auth/browser-login',404),
    ('203.0.113.10','/api/orders',404),
    ('attacker.test','/api/orders',404),
    ('','/api/orders',404),
])
async def test_domain_boundary_asgi(host,path,expected):
    from api.security_middleware import DomainBoundaryMiddleware
    async def ok(scope,receive,send):
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
    scope={'type':'http','method':'GET','path':path,'headers':[(b'host',host.encode())]}
    messages=[]
    async def send(message): messages.append(message)
    async def receive(): return {'type':'http.request','body':b'','more_body':False}
    with patch.object(settings,'dashboard_public_url','https://dashboard.accordniche.pp.ua'):
        await DomainBoundaryMiddleware(ok)(scope,receive,send)
    assert messages[0]['status']==expected


def test_admin_cookie_differs_from_storefront_and_legacy():
    from api.browser_sessions import cookie_name
    with patch.object(settings, 'public_url', 'https://shop.accordniche.pp.ua'), \
         patch.object(settings, 'dashboard_public_url', 'https://dashboard.accordniche.pp.ua'):
        assert cookie_name() == '__Host-accord_admin_session'


def test_admin_cookie_stays_secure_if_telegram_url_is_misconfigured():
    from api.browser_sessions import secure_cookie
    with patch.object(settings, 'public_url', 'http://shop.accordniche.pp.ua'), \
         patch.object(settings, 'dashboard_public_url', 'https://dashboard.accordniche.pp.ua'):
        assert secure_cookie()
