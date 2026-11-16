"""Recovery format, filesystem fencing and Docker ownership, without live containers."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import accord_recovery as recovery
import recovery_archive as archive
import recovery_media as media
from setup_domains import fresh_environment, serialize
from shop.domain_security import ORIGINS, HOSTS
from shop.backup_files import BackupError


def environment():
    values = fresh_environment()
    values.update(ORIGINS)
    values.update(DOMAIN_ONLY='true', ENABLE_API_DOCS='false', MAIN_DOMAIN_ALIASES='',
                  TRUSTED_HOSTS=','.join(sorted(HOSTS)))
    return values


def write_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data,bytes) else data.encode()); path.chmod(0o600)


def media_tar(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as target:
        for name,content,kind in entries:
            info = tarfile.TarInfo(name)
            if kind == 'file': info.size = len(content); target.addfile(info,io.BytesIO(content))
            elif kind == 'dir': info.type = tarfile.DIRTYPE; target.addfile(info)
            else:
                info.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                info.linkname = '/etc/passwd'; target.addfile(info)
    return stream.getvalue()


@pytest.fixture
def payload(tmp_path):
    path = tmp_path/'payload'; path.mkdir()
    write_private(path/'database.dump', b'PGDMP fixture')
    write_private(path/'environment.env', serialize(environment()))
    write_private(path/'media.tar', media_tar([('photo.jpg',b'photo','file')]))
    return path


def make(payload, tmp_path):
    return archive.make_bundle(tmp_path/'backups',payload,project='accord-niche',revision='current',build='qa',
                               media=archive.inspect_media(payload/'media.tar'))


def rewrite(source, target, change):
    with tarfile.open(source,'r:gz') as original, tarfile.open(target,'w:gz') as new:
        for info in original:
            raw = original.extractfile(info).read()
            info, raw = change(info,raw)
            info.size = len(raw); new.addfile(info,io.BytesIO(raw))


def test_bundle_verifies_private_files_and_unpacks_without_docker(payload,tmp_path,monkeypatch):
    source=make(payload,tmp_path)
    assert source.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(recovery, 'HostBackup', lambda: pytest.fail('offline operation contacted Docker'))
    assert recovery.main(['verify',str(source)]) == 0
    destination=tmp_path/'unpacked'
    assert recovery.main(['unpack',str(source),'--output',str(destination)]) == 0
    assert destination.stat().st_mode & 0o777 == 0o700
    for name in ('database.dump','environment.env','media.tar'):
        assert (destination/name).read_bytes() == (payload/name).read_bytes()
        assert (destination/name).stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): recovery.main(['unpack',str(source),'--output',str(destination)])
    assert (destination/'environment.env').read_bytes() == (payload/'environment.env').read_bytes()


@pytest.mark.parametrize('name', ['../outside','/absolute','media\\escape','media/../escape'])
def test_unsafe_outer_path_is_rejected_before_unpack(payload,tmp_path,name):
    source=make(payload,tmp_path); bad=tmp_path/'bad.tar.gz'
    def change(info,raw):
        if info.name=='database.dump': info.name=name
        return info,raw
    rewrite(source,bad,change)
    with pytest.raises(BackupError):
        with archive.open_bundle(bad): pytest.fail('unsafe input accepted')
    assert not (tmp_path/'outside').exists()


def test_changed_payload_is_detected_even_when_tar_is_structurally_valid(payload,tmp_path):
    source=make(payload,tmp_path); bad=tmp_path/'bad.tar.gz'
    rewrite(source,bad,lambda info,raw:(info,raw+b'changed' if info.name=='database.dump' else raw))
    with pytest.raises(BackupError,match='сума'):
        with archive.open_bundle(bad): pass


def test_truncated_archive_does_not_create_an_unpack_destination(payload,tmp_path):
    source=make(payload,tmp_path); bad=tmp_path/'short.tar.gz';bad.write_bytes(source.read_bytes()[:60])
    with pytest.raises(BackupError): recovery.main(['unpack',str(bad),'--output',str(tmp_path/'destination')])
    assert not (tmp_path/'destination').exists()


@pytest.mark.parametrize('entries', [
    [('../escape',b'x','file')], [('x',b'','symlink')], [('x',b'','hardlink')],
    [('same',b'a','file'),('same',b'b','file')],
    [('parent',b'a','file'),('parent/child',b'b','file')],
    [('parent/child',b'a','file'),('parent',b'b','file')]])
def test_media_paths_links_and_duplicates_are_rejected(tmp_path,entries):
    path=tmp_path/'media.tar';path.write_bytes(media_tar(entries))
    with pytest.raises(BackupError): archive.inspect_media(path)


def test_stage_commit_preserves_public_permissions_and_removes_stale_files(tmp_path):
    root=tmp_path/'data';(root/'media').mkdir(parents=True)
    (root/'media/old.jpg').write_bytes(b'old')
    token='a'*32
    result=media.stage(root,token,io.BytesIO(media_tar([('folder/new.jpg',b'new','file')])))
    assert result['folder/new.jpg']['size']==3
    assert (root/'media/old.jpg').read_bytes()==b'old'
    media.commit(root,token)
    assert not (root/'media/old.jpg').exists()
    assert (root/'media/folder/new.jpg').read_bytes()==b'new'
    assert (root/'media').stat().st_mode & 0o777 == 0o755
    assert (root/'media/folder/new.jpg').stat().st_mode & 0o777 == 0o644
    assert (root/('.accord-media-old-'+token)/'old.jpg').exists()
    media.cleanup(root,token,'old')
    assert not (root/('.accord-media-old-'+token)).exists()


def test_failed_media_stage_does_not_change_live_directory(tmp_path):
    root=tmp_path/'data';(root/'media').mkdir(parents=True);(root/'media/old').write_bytes(b'old')
    with pytest.raises(ValueError): media.stage(root,'b'*32,io.BytesIO(media_tar([('escape',b'','symlink')])))
    assert (root/'media/old').read_bytes()==b'old'
    assert not list(root.glob('.accord-media-stage-*'))


def test_failed_second_rename_restores_previous_media(tmp_path,monkeypatch):
    root=tmp_path/'data';(root/'media').mkdir(parents=True);(root/'media/old').write_bytes(b'old')
    token='c'*32;media.stage(root,token,io.BytesIO(media_tar([('new',b'new','file')])))
    original=media.os.rename
    def fail(source,target):
        if 'stage-' in str(source): raise OSError('disk failure')
        return original(source,target)
    monkeypatch.setattr(media.os,'rename',fail)
    with pytest.raises(OSError): media.commit(root,token)
    assert (root/'media/old').read_bytes()==b'old'


def test_private_copy_rejects_symlinks_and_public_secrets(tmp_path):
    source=tmp_path/'secret';write_private(source,'private')
    link=tmp_path/'linked';link.symlink_to(source)
    with pytest.raises(OSError): archive.private_copy(link,tmp_path/'copy',1024)
    source.chmod(0o644)
    with pytest.raises(BackupError): archive.private_copy(source,tmp_path/'copy',1024)
    assert not (tmp_path/'copy').exists()


def install_local_media_transport(tool,tmp_path):
    """Use real files and PostgreSQL; replace only Docker transport for isolated QA."""
    tool.project='accord-niche'
    values=environment();values.update(POSTGRES_USER='postgres',POSTGRES_DB=tool.database)
    tool.values=values;write_private(tool.root/'.env.domains',serialize(values))
    root=tmp_path/'appdata';(root/'media').mkdir(parents=True)
    (root/'media/photo.jpg').write_bytes(b'original photo')
    api={'Id':'api-owned','Image':'sha256:'+'f'*64,'State':{'Running':True},
         'Mounts':[{'Type':'volume','Destination':'/data','Name':'accord-niche_appdata'}],
         'Config':{'Env':[k+'='+v for k,v in values.items()]}}
    rows={'db':{'Id':tool.db},'api':api,'bot':{'Id':'bot-owned','State':{'Running':False}}}
    tool.inventory=lambda:rows
    events=[];run=tool.run
    def dispatch(command,**kw):
        if command[0]!='docker': return run(command,**kw)
        events.append(command)
        if command[1] in {'stop','start'}:
            for row in rows.values():
                if row['Id'] in command[2:]: row['State']['Running']=command[1]=='start'
            return b''
        if command[1]=='inspect':return json.dumps([rows[name] for name in rows if rows[name]['Id'] in command[2:]]).encode()
        assert command[1]=='run'
        assert '--network' in command and command[command.index('--network')+1]=='none'
        assert 'source=accord-niche_appdata' in command[command.index('--mount')+1]
        operation,token=command[-2:]
        if operation=='export':media.export(root,kw['stdout']);return b''
        if operation=='stage':return json.dumps(media.stage(root,token,kw['stdin'])).encode()
        if operation=='commit':media.commit(root,token)
        elif operation.startswith('cleanup-'):media.cleanup(root,token,operation.split('-')[1])
        return b''
    tool.run=dispatch
    return recovery.Recovery(tool,tmp_path/'no-tls'),root,rows,events


def boundary_host(volume='accord-niche_appdata',image='sha256:'+'a'*64):
    api={'Id':'owned','Image':image,'Mounts':[{'Type':'volume','Destination':'/data','Name':volume}]}
    return SimpleNamespace(project='accord-niche',db='db-owned',inventory=lambda:{'db':{'Id':'db-owned'},'api':api})


@pytest.mark.parametrize('volume,image',[('deploy_appdata','sha256:'+'a'*64),('accord-niche_appdata','foreign:latest')])
def test_foreign_media_volume_or_unpinned_image_is_rejected(volume,image):
    with pytest.raises(BackupError): recovery.Recovery(boundary_host(volume,image))


def test_ephemeral_helper_uses_pinned_image_scoped_volume_and_no_network():
    host=boundary_host();commands=[]
    host.run=lambda command,**kwargs:commands.append(command) or b''
    operation=recovery.Recovery(host)
    operation.media('export','d'*32)
    command=commands[0]
    assert command[:4]==['docker','run','--rm','--pull']
    assert command[command.index('--network')+1]=='none'
    assert command[command.index('--mount')+1]=='type=volume,source=accord-niche_appdata,target=/data,readonly'
    assert command[-6]=='sha256:'+'a'*64


def test_journal_is_private_and_preserves_fail_closed_phase_after_process_exit(tmp_path):
    import multiprocessing,os
    row={'id':'e'*32,'phase':'changing_database','operation':'restore','project':'accord-niche',
         'writers':['api-owned'],'safety':'accord-recovery-safety.tar.gz','updated_at':1}
    def crash():
        archive.write_state(tmp_path,row);os._exit(72)
    process=multiprocessing.get_context('fork').Process(target=crash)
    process.start();process.join(5)
    assert process.exitcode==72
    state=archive.recovery_states(tmp_path)[0]
    assert state['phase']=='changing_database' and state['writers']==['api-owned']
    assert state['safety']=='accord-recovery-safety.tar.gz'
    path=tmp_path/('.recovery-state-'+row['id']+'.json')
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('wrong_domain', [False,True])
def test_origin_tls_pair_is_validated_for_all_three_accord_hosts(tmp_path,wrong_domain):
    directory=tmp_path/'tls';directory.mkdir()
    names='DNS:elfar.pp.ua' if wrong_domain else 'DNS:accordniche.pp.ua,DNS:*.accordniche.pp.ua'
    subprocess.run(['openssl','req','-x509','-nodes','-newkey','rsa:2048','-days','1',
          '-subj','/CN=accordniche.pp.ua','-addext','subjectAltName='+names,
          '-keyout',str(directory/'origin.key'),'-out',str(directory/'origin.pem')],capture_output=True,check=True,timeout=15)
    host=boundary_host()
    def run(command,**kwargs):
        result=subprocess.run(command,capture_output=True,timeout=10)
        if result.returncode:raise BackupError('TLS verification failed')
        return result.stdout
    host.run=run
    operation=recovery.Recovery(host)
    if wrong_domain:
        with pytest.raises(BackupError):operation.validate_tls(tmp_path)
    else:operation.validate_tls(tmp_path)


def test_complete_tls_pair_survives_bundle_verify_and_private_unpack(payload,tmp_path):
    write_private(payload/'tls/origin.pem','public certificate fixture')
    write_private(payload/'tls/origin.key','private key fixture')
    source=make(payload,tmp_path)
    with archive.open_bundle(source) as (path,manifest):
        assert manifest['tls_included'] is True
        assert (path/'tls/origin.key').stat().st_mode & 0o777 == 0o600
        assert (path/'tls/origin.key').read_bytes()==b'private key fixture'
