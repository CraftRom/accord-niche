"""Dependency-light smoke checks for public website security helpers.

Run: python3 backend/qa/qa_accord_website_security.py
These checks avoid importing the entire Telegram runtime in an offline CI image.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

SOURCE = Path(__file__).resolve().parents[1] / 'api' / 'routers' / 'website_shop.py'
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
names = {'_hash', '_secure', '_website_origin', '_require_csrf', '_phone', '_csrf_cookie'}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
ns = {'hashlib': hashlib, 'hmac': hmac, 'HTTPException': HTTPException, 'CSRF_NAME': 'accord_csrf'}
exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), str(SOURCE), 'exec'), ns)


class WebsiteSecurityTests(unittest.TestCase):
    def test_hash_is_sha256(self):
        self.assertEqual(ns['_hash']('hello'), hashlib.sha256(b'hello').hexdigest())

    def test_phone_normalization(self):
        expected = '+380671234567'
        for raw in ('+38 (067) 123-45-67', '380671234567', '0671234567'):
            with self.subTest(raw=raw):
                self.assertEqual(ns['_phone'](raw), expected)
        for raw in ('123', '095', '+440123456789', '0012345678'):
            with self.subTest(invalid=raw):
                with self.assertRaises(HTTPException): ns['_phone'](raw)

    def test_csrf_checks_real_origin_including_nonstandard_port(self):
        token = 'ab' * 24
        request = SimpleNamespace(
            headers={'host':'192.0.2.4:18081','origin':'http://192.0.2.4:18081',
                     'x-csrf-token':token},
            cookies={'accord_csrf': token},
            url=SimpleNamespace(scheme='http'),
            client=SimpleNamespace(host='127.0.0.1'),
        )
        ns['_require_csrf'](request)
        for origin in ('http://192.0.2.4', 'https://192.0.2.4:18081', 'http://evil.test'):
            with self.subTest(origin=origin):
                request.headers['origin'] = origin
                with self.assertRaises(HTTPException): ns['_require_csrf'](request)
        request.headers['origin'] = 'http://192.0.2.4:18081'
        request.headers['x-csrf-token'] = 'ff' * 24
        with self.assertRaises(HTTPException): ns['_require_csrf'](request)

    def test_secure_mode_origin_when_behind_https_proxy(self):
        request = SimpleNamespace(
            headers={'host':'accord.example','x-forwarded-proto':'https'},
            url=SimpleNamespace(scheme='http'),
            client=SimpleNamespace(host='127.0.0.1'),
        )
        self.assertTrue(ns['_secure'](request))
        self.assertEqual(ns['_website_origin'](request), 'https://accord.example')


if __name__ == '__main__':
    unittest.main(verbosity=2)
