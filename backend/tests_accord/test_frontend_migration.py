"""Only verified, stateless ACCORD frontends can be retired during renaming."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('frontend_migration', ROOT / 'scripts/retire_legacy_frontends.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    (tmp_path / '.env.domains').write_text('COMPOSE_PROJECT_NAME=accord-niche\n')
    monkeypatch.setattr(migration, 'ROOT', tmp_path)
    calls = []
    def fake(args, capture=False):
        calls.append(args)
        if args[:3] == ['docker', 'ps', '-aq']:
            return args[-1].rsplit('=', 1)[1] + '-old\n'
        if args[:2] == ['docker', 'inspect']:
            service = args[-1].removesuffix('-old')
            return json.dumps({'labels':{
                'com.docker.compose.project':'accord-niche',
                'com.docker.compose.service':service,
                'com.docker.compose.project.config_files':str(tmp_path / 'deploy/docker-compose.domains.yml')
            },'mounts':[{'Type':'volume','RW':False,'Destination':'/data'}]})
        return ''
    monkeypatch.setattr(migration, 'run', fake)
    return calls, fake


def test_prebuild_finishes_before_retiring_only_the_three_frontends(setup):
    calls, _ = setup
    migration.migrate(edge=True, build=True)
    build = next(i for i, args in enumerate(calls) if args[-1] == 'build')
    stop = next(i for i, args in enumerate(calls) if args[:2] == ['docker','stop'])
    assert build < stop
    assert calls[stop][2:] == ['website-old','miniapp-old','dashboard-old']
    assert calls[-1] == ['docker','rm','website-old','miniapp-old','dashboard-old']
    assert all('-v' not in args and '--volumes' not in args for args in calls)
    assert all('deploy-nginx-1' not in args and 'deploy-db-1' not in args for args in calls)


def test_failed_build_keeps_old_frontends_running(setup, monkeypatch):
    calls, original = setup
    def fail(args, **kwargs):
        if args[-1] == 'build':
            raise RuntimeError('build failed')
        return original(args, **kwargs)
    monkeypatch.setattr(migration, 'run', fail)
    with pytest.raises(RuntimeError, match='build failed'):
        migration.migrate(build=True)
    assert not any(args[1:2] in (['stop'],['rm']) for args in calls)


@pytest.mark.parametrize('unsafe', ['foreign-project', 'writable-volume'])
def test_unknown_or_stateful_containers_are_preserved(setup, monkeypatch, unsafe):
    calls, original = setup
    def altered(args, **kwargs):
        value = original(args, **kwargs)
        if args[:2] == ['docker','inspect']:
            data = json.loads(value)
            if unsafe == 'foreign-project':
                data['labels']['com.docker.compose.project'] = 'deploy'
            else:
                data['mounts'][0]['RW'] = True
            return json.dumps(data)
        return value
    monkeypatch.setattr(migration, 'run', altered)
    with pytest.raises(ValueError):
        migration.migrate(build=True)
    assert not any(args[1:2] in (['stop'],['rm']) for args in calls)


def test_repeat_run_has_no_mutations_when_legacy_frontends_are_gone(setup, monkeypatch):
    calls, original = setup
    def empty(args, **kwargs):
        if args[:3] == ['docker','ps','-aq']:
            calls.append(args)
            return ''
        return original(args, **kwargs)
    monkeypatch.setattr(migration, 'run', empty)
    migration.migrate(build=True)
    assert len(calls) == 3 and all(args[:3] == ['docker','ps','-aq'] for args in calls)


def test_no_build_requires_existing_images_before_any_stop(setup):
    calls, _ = setup
    migration.migrate(build=False)
    probes = [args for args in calls if args[:3] == ['docker','image','inspect']]
    assert {args[-1] for args in probes} == {'accord-niche-website','accord-niche-miniapp','accord-niche-dashboard'}
