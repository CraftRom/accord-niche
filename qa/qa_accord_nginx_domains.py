"""Validate Nginx configs and verify denied paths on real local Nginx.

Requires system nginx; no external networking or API server is needed.
"""
from __future__ import annotations
import http.client
from pathlib import Path
import socket
import subprocess
import tempfile
import time

BASE=Path(__file__).resolve().parents[1]/'deploy/nginx'

def run():
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp)
        d.chmod(0o755)
        (d/'html').mkdir()
        (d/'html/index.html').write_text('<title>ACCORD test</title>')
        (d/'proxy-params').mkdir()
        (d/'proxy-params/accord.conf').write_text((BASE/'proxy-params/accord.conf').read_text())
        with socket.socket() as sk:
            sk.bind(('127.0.0.1',0))
            port=sk.getsockname()[1]
        files=['accord-domains-limits.conf','accord-domain-website.conf',
               'accord-domain-miniapp.conf','accord-domain-dashboard.conf']
        for name in files:
            s=(BASE/name).read_text()
            if name != 'accord-domains-limits.conf':
                s=s.replace('    listen 80;',f'    listen 127.0.0.1:{port};')
                s=s.replace('root /usr/share/nginx/html;', f'root {d}/html;')
                s=s.replace('http://api:8000','http://127.0.0.1:9')
                s=s.replace('/etc/nginx/proxy-params/accord.conf',str(d/'proxy-params/accord.conf'))
            (d/name).write_text(s)
        config=d/'nginx.conf'
        config.write_text('''pid '''+str(d/'nginx.pid')+''';\nevents {}\nhttp {
  include /etc/nginx/mime.types;
  access_log off;
  error_log stderr warn;
'''+''.join(f'include {d}/{name};\n' for name in files)+"}\n")
        test=subprocess.run(['nginx','-t','-c',str(config),'-p',str(d)],capture_output=True,text=True)
        assert test.returncode==0, test.stderr
        proc=subprocess.Popen(['nginx','-c',str(config),'-p',str(d),'-g','daemon off;'],stderr=subprocess.PIPE)
        try:
            time.sleep(0.2)
            assert proc.poll() is None, f'Nginx exited: {proc.stderr.read()}'
            cases=[
                ('accordniche.pp.ua','/api/auth/browser-login',404),
                ('accordniche.pp.ua','/api/orders',404),
                ('accordniche.pp.ua','/api/web/session',502),
                ('shop.accordniche.pp.ua','/api/orders',404),
                ('shop.accordniche.pp.ua','/api/auth/browser-login',404),
                ('shop.accordniche.pp.ua','/api/shop/config',502),
                ('dashboard.accordniche.pp.ua','/api/auth/login',404),
                ('dashboard.accordniche.pp.ua','/api/auth/browser-login',502),
                ('dashboard.accordniche.pp.ua','/',200),
            ]
            for host,path,expected in cases:
                conn=http.client.HTTPConnection('127.0.0.1',port,timeout=4)
                conn.request('GET',path,headers={'Host':host})
                response=conn.getresponse()
                assert response.status==expected,(host,path,response.status,expected)
                response.read()
                conn.close()
            for host in ('203.0.113.10', 'attacker.test'):
                conn=http.client.HTTPConnection('127.0.0.1',port,timeout=4)
                conn.request('GET','/',headers={'Host':host})
                try:
                    conn.getresponse()
                except http.client.RemoteDisconnected:
                    pass  # Nginx 444 rejects the host without an HTTP response.
                else:
                    raise AssertionError(f'Unknown Host accepted: {host}')
                finally:
                    conn.close()
            print('Nginx syntax + 11 real HTTP host-isolation cases: PASS')
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill()

if __name__=='__main__':
    run()
