"""Real Nginx SSI + real API on a temporary SQLite: per-URL SEO head tags.

    npm --prefix website run build && python3 qa/qa_accord_seo_nginx.py

Needs nginx (QA_NGINX_BIN) and the backend dependencies; starts its own
listeners on free local ports and never touches a running nginx or database.
"""
import os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; BASE = ROOT / 'deploy/nginx'
NGINX = os.environ.get('QA_NGINX_BIN', 'nginx')
if not shutil.which(NGINX) or not (ROOT / 'website/dist/index.html').exists():
    print('SKIP: потрібні nginx і зібраний website/dist'); sys.exit(0)
work = Path(tempfile.mkdtemp(prefix='accord-seo-'))
def free():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p
api_port, web_port = free(), free()
db = work / 'seo.db'
env = {**os.environ, 'DATABASE_URL': f'sqlite+aiosqlite:///{db}', 'TRUSTED_HOSTS': 'accordniche.pp.ua,127.0.0.1,localhost',
       'BOT_TOKEN': '', 'OPTIONAL_TELEGRAM': 'true', 'JWT_SECRET': 'x' * 48, 'REDIS_URL': '', 'PYTHONPATH': str(ROOT / 'backend')}
seed = '''
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine
from shop import models as m
async def main():
    e = create_async_engine("sqlite+aiosqlite:///%s")
    async with e.begin() as c:
        await c.run_sync(m.Base.metadata.create_all)
        from sqlalchemy import insert
        now = datetime.now(timezone.utc)
        await c.execute(insert(m.Product), [dict(id=7, name='Aventus </script><b>', brand='Creed', sku='CRD-0007', price=Decimal('450'), stock=3,
            is_active=True, volume_ml=5, description='Ананас і берёза. "Лапки" & <тег>', photo_url='https://cdn.example/a.jpg', name_lower='')])
        await c.execute(insert(m.Product), [dict(id=8, name='Hidden', brand='X', sku='HID-0008', price=Decimal('1'), stock=1, is_active=False, name_lower='')])
        await c.execute(insert(m.BlogPost), [dict(id=1, slug='novyi-slug', title='Як обрати аромат', excerpt='Короткий опис', search_text='', body='Текст',
            cover_url='/media/cover.jpg', status='published', published_at=now - timedelta(days=1), created_by='a', updated_by='a')])
        await c.execute(insert(m.BlogSlug), [dict(slug='novyi-slug', post_id=1), dict(slug='staryi-slug', post_id=1)])
    await e.dispose()
asyncio.run(main())
''' % db
subprocess.run([sys.executable, '-c', seed], env=env, check=True, cwd=ROOT / 'backend')
api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', str(api_port)],
                       env=env, cwd=ROOT / 'backend', stdout=open(work / 'api.log', 'wb'), stderr=subprocess.STDOUT)
conf = work / 'conf'; conf.mkdir(exist_ok=True); (conf / 'proxy-params').mkdir(exist_ok=True)
(conf / 'proxy-params/accord.conf').write_text((BASE / 'proxy-params/accord.conf').read_text())
site = (BASE / 'accord-domain-website.conf').read_text()
site = site.replace('    listen 80;', f'    listen 127.0.0.1:{web_port};').replace('root /usr/share/nginx/html;', f'root {ROOT}/website/dist;')
site = site.replace('http://api:8000', f'http://127.0.0.1:{api_port}').replace('/etc/nginx/proxy-params/accord.conf', str(conf / 'proxy-params/accord.conf'))
site = site.replace('resolver 127.0.0.11 valid=10s ipv6=off;', 'resolver 127.0.0.1 valid=10s ipv6=off;')
(conf / 'site.conf').write_text(site)
(conf / 'nginx.conf').write_text(f'''pid {work}/nginx.pid; error_log {work}/error.log; events {{}}
http {{ include /etc/nginx/mime.types; access_log off; client_body_temp_path {work}/tmp; proxy_temp_path {work}/tmp;
  fastcgi_temp_path {work}/tmp; uwsgi_temp_path {work}/tmp; scgi_temp_path {work}/tmp;
  include {BASE}/accord-domains-limits.conf; include {conf}/site.conf; }}''')
(work / 'tmp').mkdir(exist_ok=True)
subprocess.run([NGINX, '-t', '-c', str(conf / 'nginx.conf'), '-p', str(work)], check=True)
ng = subprocess.Popen([NGINX, '-c', str(conf / 'nginx.conf'), '-p', str(work), '-g', 'daemon off;'])
def get(path):
    req = urllib.request.Request(f'http://127.0.0.1:{web_port}{path}', headers={'Host': 'accordniche.pp.ua', 'User-Agent': 'TelegramBot (like TwitterBot)'})
    with urllib.request.urlopen(req, timeout=5) as r: return r.status, r.read().decode()
ok = 0
def check(name, cond, detail=''):
    global ok
    print(('✓ ' if cond else '✗ ') + name, '' if cond else detail[:400]); ok += bool(cond)
try:
    for _ in range(300):
        try:
            if urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{api_port}/api/public/seo/head?path=/aroma/7', headers={'Host': 'accordniche.pp.ua'}), timeout=1).status == 200: break
        except Exception: time.sleep(0.1)
    else: raise SystemExit('API did not start')
    st, body = get('/aroma/7')
    head = body.split('</head>')[0]
    check('product title in raw HTML', 'Creed Aventus' in head and '450.00 ₴' in head, head)
    check('script-breaking name is escaped', '</script><b>' not in head and '&lt;/script&gt;' in head, head)
    check('JSON-LD cannot close its element', head.count('</script>') == head.count('<script'), head)
    check('og:image https product photo', 'og:image" content="https://cdn.example/a.jpg"' in head, head)
    check('canonical product URL', 'rel="canonical" href="https://accordniche.pp.ua/aroma/7"' in head, head)
    check('fallback block not duplicated', head.count('<title>') == 1, head)
    st, body = get('/blog/staryi-slug?utm_source=x')
    head = body.split('</head>')[0]
    check('old slug canonicalizes to current', 'href="https://accordniche.pp.ua/blog/novyi-slug"' in head and 'BlogPosting' in head, head)
    check('relative cover becomes absolute', 'og:image" content="https://accordniche.pp.ua/media/cover.jpg"' in head, head)
    st, body = get('/aroma/8'); head = body.split('</head>')[0]
    check('hidden product is noindex and generic', 'noindex' in head and 'Hidden' not in head, head)
    st, body = get('/checkout'); check('checkout is noindex', 'noindex' in body.split('</head>')[0])
    st, body = get('/'); check('home canonical', 'href="https://accordniche.pp.ua"' in body)
    st, body = get('/sitemap.xml')
    check('sitemap lists product and post, not hidden', '/aroma/7<' in body and '/blog/novyi-slug<' in body and '/aroma/8<' not in body, body)
    st, body = get('/robots.txt'); check('robots points to sitemap', 'Sitemap: https://accordniche.pp.ua/sitemap.xml' in body)
    try:
        st, body = get('/__seo_head'); check('internal location exposes nothing', st in (204, 404) and not body, body)
    except urllib.error.HTTPError as e: check('internal location exposes nothing', e.code == 404)
    api.terminate(); api.wait(timeout=10)
    st, body = get('/aroma/7'); head = body.split('</head>')[0]
    check('API down: page still served with fallback tags', st == 200 and head.count('<title>') == 1 and 'розпив оригінальної' in head and 'error' not in head.lower(), head)
finally:
    ng.terminate(); ng.wait(timeout=10)
    if api.poll() is None: api.terminate()
    shutil.rmtree(work, ignore_errors=True)
print(f'SEO E2E: {ok}/15')
sys.exit(0 if ok == 15 else 1)
