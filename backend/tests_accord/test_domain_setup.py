"""Domain bootstrap and deploy safeguards: real files, subprocesses, no live services."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from dotenv import dotenv_values
from shop.domain_security import validate_domain_environment

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('accord_setup', ROOT / 'scripts/setup_domains.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    return tmp_path


def make_config(project):
    assert setup.main([]) == 0
    path = project / '.env.domains'
    return path, setup.parse_env(path)


def test_fresh_bootstrap_and_rerun_preserve_all_bytes(project, capsys):
    path, values = make_config(project)
    assert values['COMPOSE_PROJECT_NAME'] == 'accord-niche'
    assert values['DOMAIN_ONLY'] == 'true'
    assert values['PUBLIC_URL'] == 'https://shop.accordniche.pp.ua'
    assert path.stat().st_mode & 0o777 == 0o600
    before = path.read_bytes()
    assert setup.main([]) == 0
    assert setup.main(['--check']) == 0
    assert path.read_bytes() == before
    output = capsys.readouterr().out
    for key in ['POSTGRES_PASSWORD', 'REDIS_PASSWORD', 'JWT_SECRET', 'DASHBOARD_PASSWORD', 'DATA_ENCRYPTION_KEY']:
        assert values[key] not in output
    second = setup.fresh_environment()
    assert values['JWT_SECRET'] != second['JWT_SECRET']


@pytest.mark.parametrize('key,value', [
    ('PUBLIC_URL', 'http://shop.accordniche.pp.ua'),
    ('PUBLIC_URL', 'https://127.0.0.1'),
    ('DASHBOARD_PUBLIC_URL', 'https://dashboard.attacker.test'),
    ('CORS_ORIGINS', 'https://accordniche.pp.ua'),
    ('TRUSTED_HOSTS', '*'), ('ENABLE_API_DOCS', 'true'), ('DOMAIN_ONLY', 'false'),
    ('JWT_SECRET', 'weak'), ('POSTGRES_PASSWORD', 'change_this_long_password_value'),
    ('REDIS_PASSWORD', 'generate_with_setup_script'), ('DATA_ENCRYPTION_KEY', 'bad'),
    ('MAIN_DOMAIN_ALIASES', 'old.example.test'), ('ACCORD_SITE_PORT', '80'),
    ('ACCORD_DASHBOARD_PORT', '18081'), ('COMPOSE_PROJECT_NAME', '../bad'),
    ('REDIS_URL', 'redis://redis:6379/0'),
    ('DATABASE_URL', 'postgresql+asyncpg://other:wrong@remote:5432/other'),
    ('POSTGRES_HOST', 'remote.example.test'), ('POSTGRES_PORT', '5433'),
])
def test_invalid_config_fails_without_modifying_file(project, key, value):
    path, values = make_config(project)
    values[key] = value
    path.write_text(setup.serialize(values))
    before = path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        setup.main(['--check'])
    assert exc.value.code == 2
    assert path.read_bytes() == before


def test_permissive_file_permissions_rejected(project):
    path, _ = make_config(project)
    path.chmod(0o644)
    with pytest.raises(SystemExit):
        setup.main(['--check'])


def test_symlink_target_not_read_or_overwritten(project):
    source = project / 'private'
    source.write_text('untouched')
    (project / '.env.domains').symlink_to(source)
    with pytest.raises(SystemExit):
        setup.main([])
    assert source.read_text() == 'untouched'


def test_source_import_keeps_credentials_namespace_and_literal_special_chars(project):
    original = setup.fresh_environment()
    original.pop('COMPOSE_PROJECT_NAME')
    original['DASHBOARD_PASSWORD'] = "StrongLiteral$HOME'$(touch HACKED)-secret"
    original['ACCORD_SITE_BIND'] = '0.0.0.0'
    source = project / 'current.env'
    source.write_text(setup.serialize(original))
    assert setup.main(['--source', str(source)]) == 0
    path = project / '.env.domains'
    values = setup.parse_env(path)
    for key in ['POSTGRES_PASSWORD', 'REDIS_PASSWORD', 'JWT_SECRET', 'DASHBOARD_PASSWORD', 'DATA_ENCRYPTION_KEY']:
        assert values[key] == original[key]
    assert values['COMPOSE_PROJECT_NAME'] == 'accord-niche-test'
    assert 'ACCORD_SITE_BIND' not in values
    assert dotenv_values(path, interpolate=False) == values
    before = path.read_bytes()
    with pytest.raises(SystemExit):
        setup.main(['--source', str(source)])
    assert path.read_bytes() == before
    assert not (project / 'HACKED').exists()


def test_invalid_import_leaves_no_output_file(project):
    source = project / 'incomplete.env'
    source.write_text('POSTGRES_USER=accord\n')
    with pytest.raises(SystemExit):
        setup.main(['--source', str(source)])
    assert not (project / '.env.domains').exists()


@pytest.mark.parametrize('text', ['A=one\nA=two\n', 'not an env line', "A='unterminated", 'A=$HOME'])
def test_ambiguous_env_rejected(project, text):
    source = project / 'bad.env'
    source.write_text(text)
    with pytest.raises(ValueError):
        setup.parse_env(source)


def test_domain_security_is_enforced_at_api_startup(project, monkeypatch):
    _, values = make_config(project)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    from shop.config import Settings
    settings = Settings(_env_file=None)
    settings.validate_production_security()
    settings.public_url = 'http://shop.accordniche.pp.ua'
    with pytest.raises(ValueError, match='PUBLIC_URL'):
        settings.validate_production_security()


def prepare_wrapper(project):
    for filename in ['scripts/setup_domains.py', 'scripts/retire_legacy_frontends.py', 'backend/shop/domain_security.py', 'deploy/domains.sh']:
        path = project / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / filename, path)
    (project / 'backend/shop/__init__.py').touch()
    bin_dir = project / 'bin'
    bin_dir.mkdir()
    docker = bin_dir / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['CALL_LOG'], 'a') as stream:
    stream.write(json.dumps({'args':sys.argv[1:],'project':os.getenv('COMPOSE_PROJECT_NAME'),'password':os.getenv('POSTGRES_PASSWORD')})+'\\n')
''')
    docker.chmod(0o755)
    return {**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
            'CALL_LOG': str(project / 'calls.jsonl'), 'POSTGRES_PASSWORD': 'shell-override',
            'COMPOSE_PROJECT_NAME': 'wrong-project'}


def test_deploy_uses_checked_env_and_clears_shell_overrides(project):
    make_config(project)
    env = prepare_wrapper(project)
    result = subprocess.run(['bash', str(project / 'deploy/domains.sh'), 'up', '-d', '--build'],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in (project / 'calls.jsonl').read_text().splitlines()]
    assert len(calls) == 5
    assert all(call['project'] is None and call['password'] is None for call in calls)
    assert calls[0]['args'][-2:] == ['config', '--quiet']
    assert calls[-1]['args'][-3:] == ['up', '-d', '--build']
    assert 'shell-override' not in result.stdout + result.stderr


def test_frontend_migration_runs_for_profile_up_too(project):
    make_config(project)
    env = prepare_wrapper(project)
    args = ['--profile', 'workers', 'up', '-d', '--build']
    result = subprocess.run(['bash', str(project / 'deploy/domains.sh'), *args], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in (project / 'calls.jsonl').read_text().splitlines()]
    assert sum(call['args'][:2] == ['ps','-aq'] for call in calls) == 3
    assert calls[-1]['args'][-5:] == args


@pytest.mark.parametrize('args', [['down', '-v'], ['down', '--volumes=true'], ['down', '-vt0'], ['--project-name=wrong', 'up'], ['-pwrong', 'up'], ['--file=other.yml', 'up']])
def test_deploy_rejects_destructive_or_configuration_bypass_arguments(project, args):
    make_config(project)
    env = prepare_wrapper(project)
    result = subprocess.run(['bash', str(project / 'deploy/domains.sh'), *args], env=env, capture_output=True)
    assert result.returncode == 2
    assert not (project / 'calls.jsonl').exists()


def test_telegram_menu_uses_domain_root_in_domain_mode(monkeypatch):
    from shop.config import settings
    from shop.telegram_menu import storefront_url
    monkeypatch.setattr(settings, 'domain_only', True)
    assert storefront_url('https://shop.accordniche.pp.ua') == 'https://shop.accordniche.pp.ua/'


def test_cleanup_only_removes_retired_code_and_preserves_credentials(project):
    spec = importlib.util.spec_from_file_location('cleanup', ROOT / 'scripts/cleanup_legacy.py')
    cleanup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cleanup)
    cleanup.ROOT = project
    for name in cleanup.RETIRED:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('retired')
    env = project / '.env.domains'
    env.write_text('do not modify')
    cleanup.main()
    assert all(not (project / name).exists() for name in cleanup.RETIRED)
    assert env.read_text() == 'do not modify'


def test_default_compose_cannot_publish_the_retired_public_dashboard():
    import yaml
    compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
    assert compose['include'][0]['path'] == 'deploy/docker-compose.domains.yml'
    assert 'services' not in compose
    for name, host in [('website', 'accordniche.pp.ua'), ('miniapp', 'shop.accordniche.pp.ua'),
                       ('dashboard', 'dashboard.accordniche.pp.ua')]:
        text = (ROOT / f'deploy/nginx/accord-domain-{name}.conf').read_text()
        assert f'if ($host != {host}) {{ return 444; }}' in text


@pytest.mark.parametrize('password,accepted', [('Abc123!', False), ('Abc123!?', True), ('Abc123!?longer', True)])
def test_system_password_minimum_matches_setup_and_api(project, monkeypatch, password, accepted):
    path, values = make_config(project)
    values['DASHBOARD_PASSWORD'] = password
    path.write_text(setup.serialize(values))
    from shop.production_security import unsafe_secrets, validate_production_security
    if accepted:
        assert setup.main(['--check']) == 0
        assert 'DASHBOARD_PASSWORD' not in unsafe_secrets(values['JWT_SECRET'], password)
        validate_production_security(values['PUBLIC_URL'], values['JWT_SECRET'], password)
        for key, value in values.items(): monkeypatch.setenv(key, value)
        from shop.config import Settings
        Settings(_env_file=None).validate_production_security()
    else:
        with pytest.raises(SystemExit): setup.main(['--check'])
        with pytest.raises(RuntimeError, match='DASHBOARD_PASSWORD'):
            validate_production_security(values['PUBLIC_URL'], values['JWT_SECRET'], password)
