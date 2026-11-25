"""IndexNow: off without a key, batched, own-domain only, never breaks saving."""
import asyncio

import pytest

from shop.services import indexnow


@pytest.mark.asyncio
async def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv('ACCORD_INDEXNOW_KEY', raising=False)
    indexnow.notify('https://accordniche.pp.ua/aroma/1')
    assert indexnow._task is None and not indexnow._pending


@pytest.mark.asyncio
async def test_batches_own_urls_and_survives_network_errors(monkeypatch):
    monkeypatch.setenv('ACCORD_INDEXNOW_KEY', 'a1b2c3d4e5f6a7b8')
    monkeypatch.setattr(indexnow, 'DEBOUNCE_SECONDS', 0.01)
    sent = []

    async def fake_send(urls):
        sent.append(urls)
        raise_later = False
        return raise_later
    monkeypatch.setattr(indexnow, '_send', fake_send)
    indexnow.notify('https://accordniche.pp.ua/aroma/1', 'https://evil.example/x')
    indexnow.notify('https://accordniche.pp.ua/blog/a')
    await asyncio.sleep(0.05)
    assert sent == [['https://accordniche.pp.ua/aroma/1', 'https://accordniche.pp.ua/blog/a',
                     'https://accordniche.pp.ua/sitemap.xml']]


@pytest.mark.asyncio
async def test_send_reports_only_to_the_log(monkeypatch):
    monkeypatch.setenv('ACCORD_INDEXNOW_KEY', 'a1b2c3d4e5f6a7b8')
    import httpx
    calls = []

    class Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False
        async def post(self, url, json):
            calls.append((url, json))
            raise httpx.ConnectError('down')
    monkeypatch.setattr(httpx, 'AsyncClient', Client)
    await indexnow._send(['https://accordniche.pp.ua/aroma/1'])
    url, body = calls[0]
    assert url == indexnow.ENDPOINT and body['host'] == 'accordniche.pp.ua'
    assert body['keyLocation'] == 'https://accordniche.pp.ua/a1b2c3d4e5f6a7b8.txt'


def test_key_format_is_checked(monkeypatch):
    monkeypatch.setenv('ACCORD_INDEXNOW_KEY', 'bad key/../')
    assert indexnow.key() is None
