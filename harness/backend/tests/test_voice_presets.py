"""The Settings voice picker and the paths that carry its selection.

The picker is a list of (profile, tone) pairs, not server-side state: the client resolves
one and sends it on every speech request. These tests pin the three things that would
otherwise fail quietly — the list's shape, the route that serves it, and the supervision
notice passing its selection through instead of dropping back to the instance default.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.harness import voice as voice_backend
from app import routes_supervision
from app.main import create_app

from test_api import account  # noqa: F401 - shared registration helper


def configure(tmp_path, monkeypatch):
    """A valid configured instance: the deterministic 'offline' provider is gone."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key-not-real')


@pytest.fixture
def voice_settings(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    return Settings.from_env()


@pytest.fixture
def client(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    with TestClient(create_app(Settings.from_env())) as test_client:
        yield test_client


# --------------------------------------------------------------- the preset list

def test_presets_are_well_formed_and_stable():
    presets = voice_backend.VOICE_PRESETS
    ids = [p['id'] for p in presets]
    assert len(ids) == len(set(ids)), 'a duplicate id makes the picker ambiguous'
    assert 'default' in ids and 'custom' in ids
    for preset in presets:
        assert set(preset) == {'id', 'label', 'voice', 'tone', 'note'}
        assert all(isinstance(value, str) for value in preset.values())
        assert preset['label'], 'the picker would render a blank row'
    default = next(p for p in presets if p['id'] == 'default')
    custom = next(p for p in presets if p['id'] == 'custom')
    assert default['voice'] == '' and default['tone'] == ''
    assert custom['voice'] == '' and custom['tone'] == ''


def test_list_voices_is_a_pure_read_of_configuration(voice_settings):
    first = voice_backend.list_voices(voice_settings)
    second = voice_backend.list_voices(voice_settings)
    assert first == second, 'the picker must not depend on mutable server state'
    assert first['presets'] == list(voice_backend.VOICE_PRESETS)
    assert first['enabled'] == bool(voice_settings.voice_enabled)
    assert isinstance(first['presets'], list)
    # A caller that edits the returned list must not change what the next caller sees.
    first['presets'].clear()
    assert voice_backend.list_voices(voice_settings)['presets']
    assert {'model', 'served_models', 'current_voice'} <= set(first)


def test_voice_voices_route_requires_a_session_and_serves_the_presets(client):
    assert client.get('/api/v1/voice/voices').status_code in (401, 403)
    headers, _ = account(client, 'voice-list')
    response = client.get('/api/v1/voice/voices', headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [p['id'] for p in body['presets']] == [
        p['id'] for p in voice_backend.VOICE_PRESETS]
    assert isinstance(body['enabled'], bool)
    assert body['presets'][0]['id'] == 'default'


# -------------------------------------------------- supervision notices speak in it

def test_assess_input_accepts_voice_and_rejects_unknown_fields():
    reading = routes_supervision.AssessInput(voice='mentor', tone='calm, low pitch')
    assert reading.voice == 'mentor'
    assert reading.tone == 'calm, low pitch'
    assert routes_supervision.AssessInput().voice == ''
    with pytest.raises(Exception):
        routes_supervision.AssessInput(voices='two')


def test_assess_pops_voice_preferences_before_the_supervisor(client, monkeypatch):
    """Speech preferences are not evidence, and a spoken notice keeps the chosen voice."""
    headers, _ = account(client, 'voice-assess')

    seen_signals = {}
    notices = []

    def fake_assess(signals, last_notice_at=None):
        seen_signals.update(signals)
        return {'state': 'drifting', 'quiet': False,
                'move': {'kind': 'prompt', 'say': 'Say why that step works.',
                         'why': 'The learner has been idle.'}}

    def fake_notice_speech(settings, text, *, voice='', tone=''):
        notices.append((text, voice, tone))
        return {'state': 'pending', 'url': '', 'digest': '', 'clips': []}

    monkeypatch.setattr(routes_supervision.supervision, 'assess', fake_assess)
    monkeypatch.setattr(routes_supervision, '_notice_speech', fake_notice_speech)

    response = client.post('/api/v1/supervision/assess', headers=headers,
                           json={'idle_seconds': 400, 'voice': 'mentor',
                                 'tone': 'calm, low pitch'})
    assert response.status_code == 200, response.text
    assert 'voice' not in seen_signals and 'tone' not in seen_signals
    assert 'mastery' in seen_signals and 'mastery_known' in seen_signals
    assert response.json()['notice']['say'] is True
    assert notices == [('Say why that step works.', 'mentor', 'calm, low pitch')]


def test_notice_speech_forwards_the_selection_to_the_renderer(monkeypatch):
    from app.harness import speech

    captured = {}

    def fake_request(settings, text, **kwargs):
        captured.update(kwargs)
        return {'state': 'pending', 'url': '/clip', 'digest': 'abc', 'clips': []}

    monkeypatch.setattr(speech, 'request_sequence', fake_request)
    monkeypatch.setattr(speech, 'classify', lambda clip, kind: dict(clip))

    result = routes_supervision._notice_speech(
        object(), 'Take a breath.', voice='mentor', tone='calm, low pitch')
    assert captured['voice'] == 'mentor'
    assert captured['tone'] == 'calm, low pitch'
    assert result['state'] == 'pending'
    # Older callers that pass nothing still resolve to the instance default.
    captured.clear()
    routes_supervision._notice_speech(object(), 'Take a breath.')
    assert captured['voice'] == '' and captured['tone'] == ''
