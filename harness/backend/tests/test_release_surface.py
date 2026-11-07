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


def test_release_kit_accepts_a_clean_record(tmp_path):
    release_kit.assert_shippable(_record(tmp_path), '1.1.16')  # must not raise


def test_install_script_is_valid_posix_sh(tmp_path):
    script = tmp_path / 'install.sh'
    script.write_text(release_kit.INSTALL_SH, encoding='utf-8')
    completed = subprocess.run(['/bin/sh', '-n', str(script)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_install_script_refuses_a_path_it_did_not_install(tmp_path):
    """The guard that stops a mistyped INSTALL_DIR from deleting something else."""
    assert 'case "$TARGET" in' in release_kit.INSTALL_SH
    assert '*/"$APP.app")' in release_kit.INSTALL_SH


def test_cask_points_at_the_versioned_dmg(tmp_path):
    text = release_kit.cask_text('1.1.16', 'https://example.test/v1.1.16', 'a' * 64)
    assert 'url "https://example.test/v1.1.16/Luminest-1.1.16-arm64.dmg"' in text
    assert "depends_on arch: :arm64" in text
    # The caveat must name the flag, because without it the app is quarantined and blocked.
    assert '--no-quarantine' in text


def test_release_directory_explains_itself(tmp_path):
    """A release folder has to be actionable by whoever receives it, not just by us."""
    record_path = tmp_path / 'package-result.json'
    record_path.write_text(json.dumps(_record(tmp_path)), encoding='utf-8')
    out = tmp_path / 'release'

    release_kit.main(['--version', '1.1.16', '--result', str(record_path), '--out', str(out)])

    for name in ('Luminest-1.1.16-arm64.dmg', 'Luminest-1.1.16-arm64.zip',
                 'install.sh', 'INSTALL.txt', 'SHA256SUMS.txt', 'RELEASE.md', 'release.json'):
        assert (out / name).is_file(), name

    sums = (out / 'SHA256SUMS.txt').read_text(encoding='utf-8')
    assert 'install.sh' in sums and 'Luminest-1.1.16-arm64.dmg' in sums

    # Without a public URL there is no cask: a formula pointing at a host that does not
    # exist is worse than no formula, because it looks installable.
    assert not (out / 'luminfest.rb').exists()
    report = json.loads((out / 'release.json').read_text(encoding='utf-8'))
    assert report['cask'] is False
    assert report['notarized'] is False
