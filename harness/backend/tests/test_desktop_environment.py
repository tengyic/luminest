"""The ``desktop`` environment: the shipped macOS bundle's own configuration.

The bundle used to run ``HARNESS_ENV=development``. That value is convenient for a
developer and wrong for a distributed app: ``gate_default`` was ``'0'`` (no 13+
attestation, no Terms acceptance) while ``media_default`` was ``'1'``, which switched on
**both** ``attention_monitor`` and outbound media. ``legal/privacy.md`` states the activity
signal is "off by default" and that the product is for users 13 and older, so the bundle
was shipping a privacy statement its own configuration contradicted.

``production`` cannot be the fix: it demands PostgreSQL and a 32-character secret and
refuses to boot, which is a reasonable demand for a hosted service and an impossible one
for an app someone just double-clicked. ``desktop`` is the fourth value - production-strict
about consent, local about storage.

These tests pin the three properties that made it necessary, and the two couplings that
would have broken the app if the value were introduced naively.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _desktop_settings(tmp_path, monkeypatch) -> Settings:
    # These tests assert *defaults*, so the operator's ``backend/.env`` must not be in play.
    # ``load_dotenv`` injects its keys into ``os.environ`` during ``from_env``, which the
    # autouse scrub in conftest cannot undo - and the developer's file sets
    # ``HARNESS_MEDIA_ENABLED``, so without this the default assertion silently reads the
    # operator's value instead. The frozen bundle ships no ``.env`` at all, which is exactly
    # the situation being tested.
    monkeypatch.setattr('app.config.load_dotenv', lambda *args, **kwargs: {})
    monkeypatch.setenv('HARNESS_ENV', 'desktop')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


def test_desktop_is_strict_about_consent_and_quiet_about_telemetry(tmp_path, monkeypatch):
    """The three defaults that were wrong, plus the invite default that would have
    blocked registration outright."""
    settings = _desktop_settings(tmp_path, monkeypatch)

    assert settings.environment == 'desktop'
    # The age gate and Terms acceptance are on: the app is for users 13 and older.
    assert settings.require_launch_gate is True
    # Activity tracking is off, which is what privacy.md and the settings UI already say.
    assert settings.attention_monitor is False
    # No undisclosed sub-processors: with media off, the policy's table stays true.
    assert settings.media_enabled is False
    # ...but speech stays on, because it is not an outbound fetch. Synthesis is a loopback
    # call to the VoiceStudio the learner is already running, so the "no outbound media"
    # line says nothing about it. These two were the same switch once, and the bundle
    # shipped mute: every tutor reply was refused before synthesis was attempted.
    assert settings.voice_enabled is True
    # A desktop learner installed the app themselves, so no Beta invite code.
    assert settings.require_invite is False
    # Still a local single-user instance.
    assert settings.auto_create is True


def test_desktop_boots_with_sqlite_and_no_secret(tmp_path, monkeypatch):
    """The whole point of a fourth value: ``production`` would refuse this configuration,
    and refusing to boot is not an option for an app the user just launched."""
    settings = _desktop_settings(tmp_path, monkeypatch)
    assert settings.database_url.startswith('sqlite')
    # Reaching this line at all is the assertion: `from_env` validated the whole instance
    # and did not raise. The hosted guard is still enforced - see the test below.


def test_production_still_refuses_sqlite(tmp_path, monkeypatch):
    """Adding a permissive value must not loosen the hosted one."""
    monkeypatch.setenv('HARNESS_ENV', 'production')
    monkeypatch.setenv('HARNESS_DATABASE_URL', f'sqlite:///{tmp_path / "h.sqlite3"}')
    monkeypatch.setenv('HARNESS_SECRET', 'luminfest-production-secret-0123456789-abcdef')
    monkeypatch.setenv('HARNESS_ALLOWED_HOSTS', 'api.example.test')
    with pytest.raises(ValueError, match='PostgreSQL'):
        Settings.from_env()


def test_development_keeps_its_convenient_defaults(tmp_path, monkeypatch):
    """The developer path is deliberately unchanged - this is a new value, not a
    redefinition of the old ones."""
    monkeypatch.setattr('app.config.load_dotenv', lambda *args, **kwargs: {})
    monkeypatch.setenv('HARNESS_ENV', 'development')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    settings = Settings.from_env()
    assert settings.require_launch_gate is False
    assert settings.media_enabled is True
    assert settings.attention_monitor is True


@pytest.fixture
def desktop_client(tmp_path, monkeypatch):
    settings = _desktop_settings(tmp_path, monkeypatch)
    with TestClient(create_app(settings)) as client:
        yield client


def _register(client, **extra):
    return client.post('/api/v1/auth/register', json={
        'name': 'Desktop Learner', 'email': 'desk@class.test',
        'password': 'long-secret-password', **extra,
    })


def test_desktop_registration_is_refused_without_the_attestation(desktop_client):
    """No silent pass: the server refuses an account that has not attested 13+ and
    accepted the Terms. This is the behaviour the shipped bundle lacked entirely."""
    response = _register(desktop_client)
    assert response.status_code == 422
    assert '13' in response.json()['detail']


def test_desktop_first_account_can_teach_and_consent_is_recorded(desktop_client):
    """Two couplings that would break the app if ``desktop`` were added naively.

    ``_ensure_operator`` used to promote only on ``development``, so a new value would have
    left the installed app with no teacher and every whiteboard/simulation tool failing
    closed. And the consent has to land on the user, not merely be required.
    """
    response = _register(desktop_client, age_confirmed=True, accept_terms=True)
    assert response.status_code == 201
    body = response.json()
    assert body['user']['role'] == 'teacher'
    assert body['user']['telemetry_consent'] is False
