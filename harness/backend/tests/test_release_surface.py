"""The release surface: the support report, and the script that publishes a build.

Two things are pinned here, both because they are the kind of thing that is easy to
break silently.

The **diagnostic report** is the only support channel the product has, and `privacy.md`
promises exactly what it contains: version, platform, configuration, and the tail of the
local log. A report that quietly grew an email address or a learner's message would make
that document false, so the absence of those fields is asserted rather than assumed.

The **release kit** refuses to assemble a publishable directory from a build whose own
record says it is not shippable. That refusal is the whole point of the script; a test
that only checked it produced files would let the guard be deleted without notice.
"""
import json
import shutil
import zipfile
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND.parent / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import release_kit  # noqa: E402 - needs the path above


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def account(client, label='release'):
    response = client.post('/api/v1/auth/register',
                           json={'name': label, 'email': f'{label}@example.test',
                                 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_diagnostics_requires_a_token(client):
    assert client.get('/api/v1/diagnostics').status_code in (401, 403)


def test_diagnostics_reports_configuration_not_the_learner(client, settings):
    headers = account(client)
    response = client.get('/api/v1/diagnostics', headers=headers)
    assert response.status_code == 200
    body = response.text

    assert 'environment: ' in body
    assert 'schema: ' in body
    assert 'platform: ' in body
    # The two facts privacy.md promises, and the one it promises never to include.
    assert 'learner role: ' in body
    assert 'release@example.test' not in body


def test_diagnostics_redacts_secret_shaped_log_lines(client, settings, tmp_path):
    log = Path(settings.data_dir) / 'backend.log'
    log.write_text('starting\napi_key=sk-abcdefghijklmnop\n'
                   'Authorization: Bearer abc.def.ghi\nready\n', encoding='utf-8')

    body = client.get('/api/v1/diagnostics', headers=account(client)).text
    assert 'sk-abcdefghijklmnop' not in body
    assert 'abc.def.ghi' not in body
    assert '<redacted>' in body
    # The non-secret lines survive, or the report would be useless for diagnosis.
    assert 'starting' in body and 'ready' in body


def _record(tmp_path, **overrides):
    dmg = tmp_path / 'Luminfest-arm64.dmg'
    dmg.write_bytes(b'not really a disk image')
    archive = tmp_path / 'Luminfest-arm64.zip'
    archive.write_bytes(b'not really an archive')
    record = {
        'version': '1.1.16',
        'app': str(tmp_path / 'Luminfest.app'),
        'dmg': str(dmg),
        'archive': str(archive),
        'legal_gate': {'placeholders': 0, 'ship_ready': True},
        'backend_smoke': {'passed': True},
        'artifacts': {
            dmg.name: {'bytes': dmg.stat().st_size, 'sha256': release_kit.sha256(dmg)},
            archive.name: {'bytes': archive.stat().st_size, 'sha256': release_kit.sha256(archive)},
        },
    }
    record.update(overrides)
    return record


def test_release_kit_refuses_a_template_legal_build(tmp_path):
    record = _record(tmp_path, legal_gate={'placeholders': 59, 'ship_ready': False})
    with pytest.raises(SystemExit) as exc:
        release_kit.assert_shippable(record, '1.1.16')
    assert 'legal_gate' in str(exc.value)


def test_release_kit_refuses_a_relabelled_build(tmp_path):
    with pytest.raises(SystemExit) as exc:
        release_kit.assert_shippable(_record(tmp_path), '1.1.17')
    assert 'Re-package' in str(exc.value)


def test_release_kit_refuses_a_failed_smoke(tmp_path):
    record = _record(tmp_path, backend_smoke={'passed': False})
    with pytest.raises(SystemExit) as exc:
        release_kit.assert_shippable(record, '1.1.16')
    assert 'smoke' in str(exc.value)


def test_release_kit_refuses_an_artifact_changed_after_packaging(tmp_path):
    record = _record(tmp_path)
    Path(record['dmg']).write_bytes(b'tampered')
    with pytest.raises(SystemExit) as exc:
        release_kit.assert_shippable(record, '1.1.16')
    assert 'changed since it was packaged' in str(exc.value)


def test_release_kit_refuses_unsigned_public_release(tmp_path):
    with pytest.raises(SystemExit, match='Developer ID Application'):
        release_kit.assert_shippable(_record(tmp_path), '1.1.16')


@pytest.fixture
def signed_package(tmp_path, monkeypatch):
    """Synthetic metadata and fake Apple command output; not real signing evidence."""
    record = _record(tmp_path)
    app = tmp_path / 'Luminest.app'
    resources = app / 'Contents' / 'Resources'
    resources.mkdir(parents=True)
    identity = 'Developer ID Application: Test Publisher (A1B2C3D4E5)'
    distribution = {'signing': identity, 'notarized': True, 'version': record['version'],
                    'releasable': True, 'legal_gate': record['legal_gate']}
    (resources / 'distribution.json').write_text(json.dumps(distribution), encoding='utf-8')
    archive = Path(record['archive'])
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.write(resources / 'distribution.json', 'Luminest.app/Contents/Resources/distribution.json')
    record.update(app=str(app), sign_identity=identity,
                  app_notarization={'stapled_app': str(app), 'profile': 'synthetic'},
                  notarization={'notarized': [record['dmg'], record['archive']],
                                'stapled': record['dmg'], 'profile': 'synthetic'})
    record['artifacts'][archive.name]['sha256'] = release_kit.sha256(archive)
    state = {'commands': [], 'fail': None, 'identity': identity,
             'source': 'Notarized Developer ID', 'different_zip': False}

    def run(command, **kwargs):
        state['commands'].append(command)
        assert kwargs['timeout'] == 120
        if state['fail'] and state['fail'](command):
            return subprocess.CompletedProcess(command, 1, '', 'rejected: synthetic failure')
        if command[:2] == ['/usr/bin/hdiutil', 'attach']:
            mount = Path(command[command.index('-mountpoint') + 1])
            shutil.copytree(app, mount / app.name)
        if command[:3] == ['/usr/bin/ditto', '-x', '-k']:
            shutil.copytree(app, Path(command[-1]) / app.name)
        output = ''
        if '--display' in command:
            cdhash = 'b' * 40 if state['different_zip'] and '/archive/' in command[-1] else 'a' * 40
            output = f'Authority={state["identity"]}\nTeamIdentifier=A1B2C3D4E5\nCDHash={cdhash}\n'
        if command[0] == '/usr/sbin/spctl':
            output = f'{command[-1]}: accepted\nsource={state["source"]}\n'
        return subprocess.CompletedProcess(command, 0, '', output)

    monkeypatch.setattr(release_kit.subprocess, 'run', run)
    return record, state


def test_release_kit_requires_live_signed_and_notarized_artifacts(signed_package):
    record, state = signed_package
    evidence = release_kit.assert_shippable(record, record['version'])
    assert set(evidence) == {'app', 'dmg', 'dmg_app', 'zip_app'}
    assert all(row['stapled_ticket_valid'] for row in evidence.values())
    commands = state['commands']
    assert any(command[:4] == ['/usr/bin/codesign', '--verify', '--deep', '--strict']
               for command in commands)
    assert any(command[:4] == ['/usr/sbin/spctl', '--assess', '--type', 'open']
               and 'context:primary-signature' in command for command in commands)
    assert sum(command[:3] == ['/usr/bin/xcrun', 'stapler', 'validate']
               for command in commands) == 4
    assert any(command[:2] == ['/usr/bin/hdiutil', 'detach'] for command in commands)
    assert not any('submit' in command or 'staple' in command or '--sign' in command
                   for command in commands)


@pytest.mark.parametrize('check', ['app_signature', 'dmg_signature', 'notarization', 'ticket',
                                  'dmg_ticket', 'zip_ticket'])
def test_forged_metadata_cannot_replace_apple_verification(signed_package, check):
    record, state = signed_package
    state['fail'] = {
        'app_signature': lambda cmd: cmd[:2] == ['/usr/bin/codesign', '--verify']
                                      and cmd[-1] == record['app'],
        'dmg_signature': lambda cmd: cmd[:2] == ['/usr/bin/codesign', '--verify']
                                      and cmd[-1] == record['dmg'],
        'notarization': lambda cmd: cmd[0] == '/usr/sbin/spctl',
        'ticket': lambda cmd: cmd[:3] == ['/usr/bin/xcrun', 'stapler', 'validate'],
        'dmg_ticket': lambda cmd: cmd[:3] == ['/usr/bin/xcrun', 'stapler', 'validate']
                                   and cmd[-1] == record['dmg'],
        'zip_ticket': lambda cmd: cmd[:3] == ['/usr/bin/xcrun', 'stapler', 'validate']
                                   and '/archive/' in cmd[-1],
    }[check]
    with pytest.raises(SystemExit, match='verification failed'):
        release_kit.assert_shippable(record, record['version'])


def test_release_kit_refuses_a_different_developer_identity(signed_package):
    record, state = signed_package
    state['identity'] = 'Developer ID Application: Different Publisher (A1B2C3D4E5)'
    with pytest.raises(SystemExit, match='expected Developer ID'):
        release_kit.assert_shippable(record, record['version'])


def test_release_kit_refuses_gatekeeper_acceptance_without_notarization(signed_package):
    record, state = signed_package
    state['source'] = 'Developer ID'
    with pytest.raises(SystemExit, match='did not confirm Notarized Developer ID'):
        release_kit.assert_shippable(record, record['version'])


def test_release_kit_refuses_missing_notarization_record(signed_package):
    record, _ = signed_package
    record['app_notarization'] = None
    with pytest.raises(SystemExit, match='missing app/DMG notarization'):
        release_kit.assert_shippable(record, record['version'])


@pytest.mark.parametrize('change', ['legal', 'version', 'notarized', 'marker'])
def test_release_kit_honors_the_signed_bundle_contract(signed_package, change):
    record, _ = signed_package
    resources = Path(record['app']) / 'Contents' / 'Resources'
    path = resources / 'distribution.json'
    distribution = json.loads(path.read_text())
    if change == 'marker':
        (resources / 'NOT_RELEASABLE.txt').write_text('not releasable')
    elif change == 'legal':
        distribution['legal_gate'] = {'ship_ready': False}
    elif change == 'version':
        distribution['version'] = 'old'
    else:
        distribution['notarized'] = False
    path.write_text(json.dumps(distribution))
    with pytest.raises(SystemExit, match='contract|NOT_RELEASABLE'):
        release_kit.assert_shippable(record, record['version'])


def test_release_kit_checks_the_app_actually_shipped_in_the_zip(signed_package):
    record, state = signed_package
    state['different_zip'] = True
    with pytest.raises(SystemExit, match='zip does not contain the recorded signed app'):
        release_kit.assert_shippable(record, record['version'])


def test_release_kit_names_missing_apple_tools(signed_package, monkeypatch):
    record, _ = signed_package

    def missing(command, **kwargs):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(release_kit.subprocess, 'run', missing)
    with pytest.raises(SystemExit, match='verification unavailable'):
        release_kit.assert_shippable(record, record['version'])


def test_cask_points_at_the_versioned_dmg_without_bypassing_gatekeeper():
    text = release_kit.cask_text('1.1.16', 'https://example.test/v1.1.16', 'a' * 64)
    assert 'url "https://example.test/v1.1.16/Luminest-1.1.16-arm64.dmg"' in text
    assert 'depends_on arch: :arm64' in text
    assert '--no-quarantine' not in text
    assert 'xattr' not in text


def test_release_directory_explains_itself_without_a_bypass_installer(signed_package, tmp_path):
    record, _ = signed_package
    record_path = tmp_path / 'package-result.json'
    record_path.write_text(json.dumps(record), encoding='utf-8')
    out = tmp_path / 'release'
    release_kit.main(['--version', '1.1.16', '--result', str(record_path), '--out', str(out)])
    for name in ('Luminest-1.1.16-arm64.dmg', 'Luminest-1.1.16-arm64.zip',
                 'INSTALL.txt', 'SHA256SUMS.txt', 'RELEASE.md', 'release.json'):
        assert (out / name).is_file(), name
    assert not (out / 'install.sh').exists()
    assert not (out / 'luminfest.rb').exists()
    sums = (out / 'SHA256SUMS.txt').read_text(encoding='utf-8')
    assert 'Luminest-1.1.16-arm64.dmg' in sums
    assert 'install.sh' not in sums
    report = json.loads((out / 'release.json').read_text(encoding='utf-8'))
    assert report['cask'] is False
    assert report['notarized'] is True
    assert report['public_release'] is True
    assert report['verification']['app']['stapled_ticket_valid'] is True
    assert 'Do not remove quarantine' in (out / 'INSTALL.txt').read_text()


def test_unsigned_release_does_not_create_a_release_directory(tmp_path):
    record_path = tmp_path / 'package-result.json'
    record_path.write_text(json.dumps(_record(tmp_path)), encoding='utf-8')
    out = tmp_path / 'release'
    with pytest.raises(SystemExit, match='Developer ID Application'):
        release_kit.main(['--version', '1.1.16', '--result', str(record_path), '--out', str(out)])
    assert not out.exists()
