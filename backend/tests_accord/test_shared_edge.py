"""Safety contracts for the observed two-project Docker edge configuration."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('edge_installer', ROOT / 'scripts/connect_elfar_edge.py')
edge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edge)


def test_compose_patch_changes_only_nginx_and_adds_external_network():
    original = (ROOT / 'deploy/docker-compose.prod.yml').read_text()
    patched = edge.patch_compose(original)
    before, after = yaml.safe_load(original), yaml.safe_load(patched)
    for name, service in before['services'].items():
        if name != 'nginx': assert after['services'][name] == service, name
    assert after['volumes'] == before['volumes']
    for name, network in before['networks'].items(): assert after['networks'][name] == network
    nginx_before = before['services']['nginx']
    nginx_after = after['services']['nginx']
    for key, value in nginx_before.items():
        if key not in ('volumes', 'networks'): assert nginx_after[key] == value
    assert set(nginx_after['volumes']) == set(nginx_before['volumes']) | {edge.MOUNT}
    assert nginx_after['networks'] == ['internal', 'accord_edge']
    assert after['networks']['accord_edge'] == {'external': True, 'name': edge.NETWORK}
    assert edge.patch_compose(patched) == patched


def test_patch_accepts_a_file_without_final_newline():
    text = (ROOT / 'deploy/docker-compose.prod.yml').read_text().rstrip('\n')
    assert yaml.safe_load(edge.patch_compose(text))['networks']['accord_edge']['external'] is True


@pytest.mark.parametrize('old,new', [('    networks: [internal]', '    networks: [custom]'),
                                    ('  nginx:\n', '  different-proxy:\n')])
def test_unexpected_compose_layout_is_rejected(old, new):
    text = (ROOT / 'deploy/docker-compose.prod.yml').read_text().replace(old, new)
    with pytest.raises(ValueError): edge.patch_compose(text)


def test_bootstrap_never_exposes_customer_or_admin_http_routes():
    text = edge.bootstrap_config()
    assert text.startswith(edge.MARKER)
    assert 'location / { return 404; }' in text
    assert 'proxy_pass' not in text
    assert 'listen 443' not in text
    assert 'root /var/www/certbot' in text


def test_tls_config_uses_only_accord_certificate_and_allows_renewal_after_redirect():
    text = edge.tls_config()
    assert '__ACCORD_' not in text
    assert '/live/elfar.pp.ua/' not in text
    assert text.count('/live/accordniche.pp.ua/fullchain.pem') == 3
    assert text.count('location ^~ /.well-known/acme-challenge/') == 3
    assert 'accord-website:80' in text and 'accord-miniapp:80' in text
    assert 'server_name dashboard.accordniche.pp.ua;' in text
    assert 'http://accord-dashboard:80' in text
    assert 'proxy_read_timeout 370s' in text


def test_certbot_never_expands_or_replaces_elfar_certificate(monkeypatch):
    calls = []
    monkeypatch.setattr(edge, 'run', lambda args, **kw: calls.append(args))
    edge.issue_certificate()
    args = calls[0]
    assert args[:4] == ['docker', 'exec', 'deploy-certbot-1', 'certbot']
    assert args[args.index('--cert-name') + 1] == 'accordniche.pp.ua'
    assert [args[i+1] for i, item in enumerate(args) if item == '-d'] == list(edge.HOSTS)
    assert 'elfar.pp.ua' not in args
    assert '--webroot' in args and '--expand' in args


def test_mounts_must_be_shared_between_existing_proxy_and_certbot():
    labels = {'com.docker.compose.project': 'deploy',
              'com.docker.compose.project.working_dir': '/opt/elfar/deploy',
              'com.docker.compose.project.config_files': '/opt/elfar/deploy/docker-compose.prod.yml'}
    mounts = [{'Source': '/vol/certs', 'Destination': '/etc/letsencrypt'},
              {'Source': '/vol/www', 'Destination': '/var/www/certbot'}]
    nginx, certbot = {'labels': labels, 'mounts': mounts}, {'mounts': mounts}
    edge.validate_layout(nginx, certbot, Path('/opt/elfar/deploy'))
    with pytest.raises(ValueError):
        edge.validate_layout(nginx, {'mounts': []}, Path('/opt/elfar/deploy'))


def test_failure_restores_config_before_live_replacement(tmp_path, monkeypatch):
    project = tmp_path / 'accord'
    elfar = tmp_path / 'elfar/deploy'
    (project / 'scripts').mkdir(parents=True)
    (elfar / 'nginx').mkdir(parents=True)
    compose = elfar / 'docker-compose.prod.yml'
    before = (ROOT / 'deploy/docker-compose.prod.yml').read_text()
    compose.write_text(before)
    (project / '.env.domains').write_text("COMPOSE_PROJECT_NAME='accord-niche'\n")
    monkeypatch.setattr(edge, 'ROOT', project)
    monkeypatch.setattr(edge.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(edge, 'inspect_container', lambda name: {})
    monkeypatch.setattr(edge, 'validate_layout', lambda *args: None)
    monkeypatch.setattr(edge, 'peer_certificate', lambda *args, **kwargs: b'elfar-original')
    monkeypatch.setattr(edge.subprocess, 'run', lambda *args, **kw: subprocess.CompletedProcess(args[0], 0))
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[-2:] == ['config', '--quiet']: raise RuntimeError('invalid config')
        return ''
    monkeypatch.setattr(edge, 'run', run)
    with pytest.raises(RuntimeError, match='invalid config'):
        edge.main(['--elfar-dir', str(elfar)])
    assert compose.read_text() == before
    assert not (elfar / 'nginx/accord-main.conf').exists()
    assert not any('--force-recreate' in args for args in calls)


def test_failure_after_recreation_rolls_back_only_proxy_services(tmp_path, monkeypatch):
    project = tmp_path / 'accord'
    elfar = tmp_path / 'elfar/deploy'
    project.mkdir(); (elfar / 'nginx').mkdir(parents=True)
    compose = elfar / 'docker-compose.prod.yml'
    before = (ROOT / 'deploy/docker-compose.prod.yml').read_text()
    compose.write_text(before)
    (project / '.env.domains').write_text('COMPOSE_PROJECT_NAME=accord-niche\n')
    monkeypatch.setattr(edge, 'ROOT', project)
    monkeypatch.setattr(edge.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(edge, 'inspect_container', lambda name: {})
    monkeypatch.setattr(edge, 'validate_layout', lambda *args: None)
    monkeypatch.setattr(edge, 'peer_certificate', lambda *args, **kwargs: b'elfar-original')
    monkeypatch.setattr(edge.subprocess, 'run', lambda *args, **kw: subprocess.CompletedProcess(args[0], 0))
    monkeypatch.setattr(edge, 'probe_http', lambda: (_ for _ in ()).throw(RuntimeError('DNS not ready')))
    calls = []
    monkeypatch.setattr(edge, 'run', lambda args, **kw: calls.append(args) or '')
    with pytest.raises(RuntimeError, match='DNS not ready'):
        edge.main(['--elfar-dir', str(elfar)])
    assert compose.read_text() == before
    restarts = [args for args in calls if '--force-recreate' in args]
    assert len(restarts) == 2
    assert all(args[-2:] == ['nginx', 'promo-controller'] for args in restarts)
    assert all('--no-deps' in args and '--no-build' in args for args in restarts)


def test_root_nginx_frontends_keep_required_worker_and_bind_capabilities():
    compose = yaml.safe_load((ROOT / 'deploy/docker-compose.domains.yml').read_text())
    for name in ('accord-website', 'accord-dashboard', 'accord-miniapp'):
        assert 'ALL' in compose['services'][name]['cap_drop']
        assert {'CHOWN', 'SETUID', 'SETGID', 'NET_BIND_SERVICE'} <= set(compose['services'][name]['cap_add'])


def test_edge_network_contains_only_frontends_and_keeps_host_ports_local():
    base = yaml.safe_load((ROOT / 'deploy/docker-compose.domains.yml').read_text())
    edge_network = yaml.safe_load((ROOT / 'deploy/docker-compose.edge-network.yml').read_text())
    assert set(edge_network['services']) == {'accord-website', 'accord-miniapp', 'accord-dashboard'}
    for name, alias in [('accord-website', 'accord-website'), ('accord-miniapp', 'accord-miniapp'), ('accord-dashboard', 'accord-dashboard')]:
        assert edge_network['services'][name]['networks']['accord_edge']['aliases'] == [alias]
        assert all(port.startswith('127.0.0.1:') for port in base['services'][name]['ports'])
    for name in ('api', 'db', 'redis'):
        assert name not in edge_network['services']
        assert not base['services'][name].get('ports')


def test_implicit_compose_dns_names_cannot_shadow_elfar_services():
    elfar = yaml.safe_load((ROOT / 'deploy/docker-compose.prod.yml').read_text())
    edge_network = yaml.safe_load((ROOT / 'deploy/docker-compose.edge-network.yml').read_text())
    for name, service in edge_network['services'].items():
        effective_aliases = {name, *service['networks']['accord_edge'].get('aliases', [])}
        assert effective_aliases.isdisjoint(elfar['services']), effective_aliases


def test_successful_workflow_keeps_elfar_and_persists_accord_edge(tmp_path, monkeypatch):
    project = tmp_path / 'accord'
    elfar = tmp_path / 'elfar/deploy'
    (project / 'deploy/nginx').mkdir(parents=True)
    (elfar / 'nginx').mkdir(parents=True)
    (project / 'deploy/nginx/accord-elfar-docker-edge.conf.template').write_text(
        (ROOT / 'deploy/nginx/accord-elfar-docker-edge.conf.template').read_text())
    compose = elfar / 'docker-compose.prod.yml'
    compose.write_text((ROOT / 'deploy/docker-compose.prod.yml').read_text())
    (project / '.env.domains').write_text('COMPOSE_PROJECT_NAME=accord-niche\n')
    monkeypatch.setattr(edge, 'ROOT', project)
    monkeypatch.setattr(edge.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(edge, 'inspect_container', lambda name: {})
    monkeypatch.setattr(edge, 'validate_layout', lambda *args: None)
    monkeypatch.setattr(edge, 'peer_certificate', lambda host, **kwargs: b'elfar-original' if host == 'elfar.pp.ua' else b'accord-cert')
    monkeypatch.setattr(edge.subprocess, 'run', lambda *args, **kw: subprocess.CompletedProcess(args[0], 0))
    monkeypatch.setattr(edge, 'probe_http', lambda: None)
    monkeypatch.setattr(edge, 'check_local_http', lambda host: None)
    calls = []
    monkeypatch.setattr(edge, 'run', lambda args, **kw: calls.append(args) or '')
    assert edge.main(['--elfar-dir', str(elfar)]) == 0
    config = (elfar / 'nginx/accord-main.conf').read_text()
    assert '/live/accordniche.pp.ua/fullchain.pem' in config
    assert edge.NETWORK == yaml.safe_load(compose.read_text())['networks']['accord_edge']['name']
    reload_index = next(i for i, args in enumerate(calls) if args[-2:] == ['-s', 'reload'])
    assert calls[reload_index - 1][-2:] == ['nginx', '-t']
    assert any('certonly' in args for args in calls[:reload_index])
    restarts = [args for args in calls if '--force-recreate' in args]
    assert len(restarts) == 1 and restarts[0][-2:] == ['nginx', 'promo-controller']


def test_failed_elfar_http_check_rolls_back_existing_edge_with_reload_only(tmp_path, monkeypatch):
    project, elfar = tmp_path / 'accord', tmp_path / 'elfar/deploy'
    (project / 'deploy/nginx').mkdir(parents=True)
    (elfar / 'nginx').mkdir(parents=True)
    (project / 'deploy/nginx/accord-elfar-docker-edge.conf.template').write_text(
        (ROOT / 'deploy/nginx/accord-elfar-docker-edge.conf.template').read_text())
    original = edge.patch_compose((ROOT / 'deploy/docker-compose.prod.yml').read_text())
    compose = elfar / 'docker-compose.prod.yml'
    compose.write_text(original)
    old_edge = edge.MARKER + 'server { listen 443 ssl; }\n'
    edge_path = elfar / 'nginx/accord-main.conf'
    edge_path.write_text(old_edge)
    (project / '.env.domains').write_text('COMPOSE_PROJECT_NAME=accord-niche\n')
    monkeypatch.setattr(edge, 'ROOT', project)
    monkeypatch.setattr(edge.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(edge, 'inspect_container', lambda *args: {})
    monkeypatch.setattr(edge, 'validate_layout', lambda *args: None)
    monkeypatch.setattr(edge, 'peer_certificate', lambda *args, **kwargs: b'elfar-original')
    monkeypatch.setattr(edge.subprocess, 'run', lambda *args, **kw: subprocess.CompletedProcess(args[0],0))
    monkeypatch.setattr(edge, 'probe_http', lambda: None)
    def http(host, **kwargs):
        if host == 'elfar.pp.ua':
            raise RuntimeError('ELFAR returns 502')
    monkeypatch.setattr(edge, 'check_local_http', http)
    calls=[]
    monkeypatch.setattr(edge, 'run', lambda args, **kwargs: calls.append(args) or '')
    with pytest.raises(RuntimeError, match='ELFAR returns 502'):
        edge.main(['--elfar-dir',str(elfar)])
    assert compose.read_text() == original
    assert edge_path.read_text() == old_edge
    assert not any('--force-recreate' in args for args in calls)
    assert sum(args[-2:] == ['-s','reload'] for args in calls) == 2
