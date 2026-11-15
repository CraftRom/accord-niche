"""Origin CA: key matching, hostname/expiry verification, and the Docker edge workflow."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import ssl
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('origin_edge', ROOT / 'scripts/connect_elfar_edge.py')
edge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edge)


@pytest.fixture
def certificates(tmp_path):
    now = datetime.now(timezone.utc)
    root_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Ephemeral test root')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(root_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=2))
          .not_valid_after(now + timedelta(days=30)).add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(root_key, hashes.SHA256()))
    ca_file = tmp_path / 'ca.pem'
    ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    def make(names=edge.HOSTS, expired=False):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
                .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=2))
                .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=20))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(host) for host in names]), critical=False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .sign(root_key, hashes.SHA256()))
        cert_file, key_file = tmp_path / 'origin.pem', tmp_path / 'origin.key'
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        key_file.chmod(0o600)
        return cert_file, key_file, ca_file
    return make


@pytest.mark.parametrize('hosts', [edge.HOSTS, ('accordniche.pp.ua', '*.accordniche.pp.ua')])
def test_valid_origin_certificates_cover_both_hostnames(certificates, hosts):
    edge.validate_origin_files(*certificates(names=hosts))


def test_missing_shop_hostname_is_rejected(certificates):
    with pytest.raises(RuntimeError): edge.validate_origin_files(*certificates(names=('accordniche.pp.ua',)))


def test_expired_origin_certificate_is_rejected(certificates):
    with pytest.raises(RuntimeError): edge.validate_origin_files(*certificates(expired=True))


def test_mismatched_private_key_is_rejected(certificates):
    cert, key, ca = certificates()
    other = ec.generate_private_key(ec.SECP256R1())
    key.write_bytes(other.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with pytest.raises(ssl.SSLError): edge.validate_origin_files(cert, key, ca)


def test_group_readable_private_key_is_rejected(certificates):
    cert, key, ca = certificates()
    key.chmod(0o640)
    with pytest.raises(ValueError, match='chmod 600'): edge.validate_origin_files(cert, key, ca)


def test_origin_paths_are_paired_before_any_server_changes(tmp_path):
    with pytest.raises(SystemExit) as error:
        edge.main(['--origin-cert', str(tmp_path / 'origin.pem')])
    assert error.value.code == 2


def test_origin_import_keeps_private_key_out_of_arguments_and_elfar_paths(certificates, monkeypatch):
    cert, key, _ = certificates()
    calls = []
    monkeypatch.setattr(edge, 'run', lambda args, **kw: calls.append(args))
    cert_path, key_path = edge.import_origin_files(cert, key)
    assert cert_path.startswith('/etc/letsencrypt/accord-origin/')
    assert cert_path.endswith('/origin.pem') and key_path.endswith('/origin.key')
    assert '/live/elfar.pp.ua' not in repr(calls)
    assert key.read_text() not in repr(calls)
    assert calls[-1][-3:] == ['600', cert_path, key_path]


def test_origin_workflow_skips_acme_and_verifies_with_explicit_ca(tmp_path, certificates, monkeypatch):
    cert, key, ca = certificates()
    project, elfar = tmp_path / 'accord', tmp_path / 'elfar/deploy'
    (project / 'deploy/nginx').mkdir(parents=True)
    (elfar / 'nginx').mkdir(parents=True)
    (project / 'deploy/nginx/accord-elfar-docker-edge.conf.template').write_text((ROOT / 'deploy/nginx/accord-elfar-docker-edge.conf.template').read_text())
    (elfar / 'docker-compose.prod.yml').write_text((ROOT / 'deploy/docker-compose.prod.yml').read_text())
    (project / '.env.domains').write_text('COMPOSE_PROJECT_NAME=accord-niche\n')
    monkeypatch.setattr(edge, 'ROOT', project)
    monkeypatch.setattr(edge.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(edge, 'inspect_container', lambda name: {})
    monkeypatch.setattr(edge, 'validate_layout', lambda *args: None)
    monkeypatch.setattr(edge, 'urlopen', lambda *args, **kw: pytest.fail('Origin CA must not download trust roots'))
    monkeypatch.setattr(edge, 'probe_http', lambda: pytest.fail('Origin CA must not use HTTP-01'))
    monkeypatch.setattr(edge, 'issue_certificate', lambda *args: pytest.fail('Origin CA must not issue a Let’s Encrypt certificate'))
    checked = []
    def peer(host, *, verified, cafile=None):
        if verified:
            assert cafile and Path(cafile).read_bytes() == ca.read_bytes()
            checked.append(host)
        return b'elfar-original' if host == 'elfar.pp.ua' else b'origin'
    monkeypatch.setattr(edge, 'peer_certificate', peer)
    monkeypatch.setattr(edge, 'check_local_http', lambda host, **kwargs: checked.append('HTTP ' + host) if kwargs.get('cafile') else pytest.fail('missing Origin CA trust'))
    monkeypatch.setattr(edge.subprocess, 'run', lambda *args, **kw: subprocess.CompletedProcess(args[0], 0))
    calls = []
    monkeypatch.setattr(edge, 'run', lambda args, **kw: calls.append(args) or '')
    assert edge.main(['--elfar-dir', str(elfar), '--origin-cert', str(cert), '--origin-key', str(key), '--origin-ca', str(ca)]) == 0
    text = (elfar / 'nginx/accord-main.conf').read_text()
    assert edge.ORIGIN_MARKER in text and '/accord-origin/' in text
    assert '/live/accordniche.pp.ua/fullchain.pem' not in text
    assert set(edge.HOSTS) <= set(checked)
    assert all('certonly' not in args for args in calls)


def test_bundled_roots_are_official_cloudflare_cas_and_load_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(edge, 'urlopen', lambda *args, **kw: pytest.fail('unexpected network request'))
    destination = tmp_path / 'ca.pem'
    edge.prepare_origin_roots(destination)
    certs = x509.load_pem_x509_certificates(destination.read_bytes())
    assert {cert.fingerprint(hashes.SHA256()).hex() for cert in certs} == {
        'd3c7e85c91707fc0a12abc5d88266747aa4fa8e7b162f633ffb3c9d989947620',
        'aa63697a22764b67b2134ce14cb5690ea336940b93986113f49545917832d80d',
    }
    for cert in certs:
        assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        assert cert.not_valid_before_utc < datetime.now(timezone.utc) < cert.not_valid_after_utc
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    previous = context.cert_store_stats()['x509_ca']
    context.load_verify_locations(cafile=str(destination))
    assert context.cert_store_stats()['x509_ca'] == previous + 2


def test_missing_bundled_ca_has_local_recovery_message(tmp_path, monkeypatch):
    monkeypatch.setattr(edge, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='--origin-ca'):
        edge.prepare_origin_roots(tmp_path / 'result.pem')
    assert not (tmp_path / 'result.pem').exists()


@pytest.mark.parametrize('contents', [b'<html>403 Forbidden</html>', b'', b'X' * 131073, b'-----BEGIN PRIVATE KEY-----'])
def test_invalid_local_ca_rejected_without_creating_snapshot(tmp_path, contents):
    source, destination = tmp_path / 'bad.pem', tmp_path / 'snapshot.pem'
    source.write_bytes(contents)
    with pytest.raises((ValueError, ssl.SSLError)):
        edge.prepare_origin_roots(destination, source)
    assert not destination.exists()


def test_leaf_certificate_cannot_replace_ca_trust_file(certificates, tmp_path):
    cert, _, _ = certificates()
    with pytest.raises(ValueError, match='CA-сертифікатів'):
        edge.prepare_origin_roots(tmp_path / 'snapshot.pem', cert)


def test_custom_ca_requires_origin_mode(tmp_path):
    with pytest.raises(SystemExit) as error:
        edge.main(['--origin-ca', str(tmp_path / 'ca.pem')])
    assert error.value.code == 2
