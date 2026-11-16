"""Real multipart bytes traverse both edge variants and the inner domain Nginx.
Run with QA_NGINX_BIN=/path/to/nginx python3 qa/qa_accord_upload_limits.py.
No Docker/VPS or customer data are used.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'deploy/nginx'
MiB = 1024 * 1024


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); return sock.getsockname()[1]


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def do_POST(self):
        remaining = int(self.headers['Content-Length'])
        while remaining:
            chunk = self.rfile.read(min(256*1024, remaining))
            if not chunk: return
            remaining -= len(chunk)
        self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers()


def run():
    executable = os.environ.get('QA_NGINX_BIN', 'nginx')
    backend = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=backend.serve_forever, daemon=True); thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='accord-upload-qa-') as tmp:
            d = Path(tmp); (d/'logs').mkdir(); inner = port(); edges = [port(), port()]
            subprocess.run(['openssl', 'req', '-x509', '-nodes', '-newkey', 'rsa:2048', '-days', '1',
                '-subj', '/CN=accordniche.pp.ua', '-keyout', str(d/'key.pem'), '-out', str(d/'cert.pem')],
                capture_output=True, check=True, timeout=15)
            (d/'html').mkdir(); (d/'html/index.html').write_text('test')
            (d/'proxy.conf').write_text((BASE/'proxy-params/accord.conf').read_text())
            sections = [(BASE/'accord-domains-limits.conf').read_text()]
            for name in ['accord-domain-dashboard.conf','accord-domain-miniapp.conf','accord-domain-website.conf']:
                value = (BASE/name).read_text().replace('listen 80;', f'listen 127.0.0.1:{inner};')
                value = value.replace('http://api:8000', f'http://127.0.0.1:{backend.server_port}')
                value = value.replace('/etc/nginx/proxy-params/accord.conf', str(d/'proxy.conf'))
                value = value.replace('root /usr/share/nginx/html;', f'root {d}/html;')
                sections.append(value)
            for name, edge in zip(['accord-elfar-docker-edge.conf.template','accord-public-edge.conf.template'], edges):
                value = (BASE/name).read_text().replace('listen 80;', f'listen 127.0.0.1:{port()};')
                value = value.replace('listen 443 ssl;', f'listen 127.0.0.1:{edge} ssl;')
                value = value.replace('__ACCORD_CERT__', str(d/'cert.pem')).replace('__ACCORD_KEY__', str(d/'key.pem'))
                value = value.replace('include /etc/nginx/deny.d/*.conf;', '')
                for upstream in ['accord-dashboard:80','accord-miniapp:80','accord-website:80', '127.0.0.1:18081','127.0.0.1:18082','127.0.0.1:18083']:
                    value = value.replace('http://' + upstream, f'http://127.0.0.1:{inner}')
                sections.append(value)
            config = d/'nginx.conf'
            config.write_text(f'pid {d}/nginx.pid; error_log {d}/error.log warn; events {{ worker_connections 128; }} http {{\naccess_log off;\nclient_body_temp_path {d}/client;\nproxy_temp_path {d}/proxy;\n'+ '\n'.join(sections) + '\n}')
            command = [executable, '-p', str(d)+'/', '-c', str(config)]
            syntax = subprocess.run(command+['-t'], capture_output=True, text=True)
            assert syntax.returncode == 0, syntax.stderr
            proc = subprocess.Popen(command+['-g','daemon off; master_process off;'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            context = ssl._create_unverified_context()  # ephemeral test certificate only
            def request(edge, host, path, size, *, declared_only=False):
                connection = http.client.HTTPSConnection('127.0.0.1', edge, timeout=20, context=context)
                try:
                    if declared_only:
                        connection.putrequest('POST', path, skip_host=True)
                        connection.putheader('Host', host); connection.putheader('Content-Length', str(size))
                        connection.putheader('Connection', 'close'); connection.endheaders()
                    else:
                        # Actual multipart overhead is included in the transport body budget.
                        payload = b'--qa\r\nContent-Disposition: form-data; name="file"; filename="qa.bin"\r\n\r\n'+b'x'*size+b'\r\n--qa--\r\n'
                        connection.request('POST', path, payload, {'Host':host,'Content-Type':'multipart/form-data; boundary=qa','Connection':'close'})
                    response = connection.getresponse(); response.read(); return response.status
                finally: connection.close()
            try:
                for _ in range(40):
                    if proc.poll() is not None: raise AssertionError((d/'error.log').read_text())
                    try:
                        request(edges[0], 'dashboard.accordniche.pp.ua', '/api/qa', 1); break
                    except OSError: time.sleep(.05)
                cases = [('dashboard.accordniche.pp.ua','/api/media',8,9),
                         ('dashboard.accordniche.pp.ua','/api/catalog/product-transfer/import',10,11),
                         ('dashboard.accordniche.pp.ua','/api/backups/upload',64,65),
                         ('shop.accordniche.pp.ua','/api/shop/orders/42/chat/photo',8,9)]
                checks = 0
                for edge in edges:
                    for host,path,payload,body_limit in cases:
                        assert request(edge,host,path,payload*MiB) == 200, (edge,path,'valid body rejected')
                        assert request(edge,host,path,body_limit*MiB+1,declared_only=True) == 413, (edge,path,'over budget accepted')
                        checks += 2
                    for host,path,limit in [('dashboard.accordniche.pp.ua','/api/orders',2),('shop.accordniche.pp.ua','/api/shop/orders',1)]:
                        assert request(edge,host,path,limit*MiB+1,declared_only=True) == 413
                        checks += 1
                    assert request(edge,'shop.accordniche.pp.ua','/api/media',1) == 404
                    checks += 1
                print(f'Nginx 2 edge variants → domain proxy → backend: {checks} HTTP checks PASS')
            finally:
                proc.terminate()
                try: proc.wait(5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(5)
    finally:
        backend.shutdown(); backend.server_close(); thread.join(3)


if __name__ == '__main__': run()
