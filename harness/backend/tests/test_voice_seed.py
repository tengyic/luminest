"""The voice lock: one teacher, one speaker, every sentence.

VoiceStudio's OmniVoice *designs* a speaker per request. Unseeded, two takes of the
same sentence come back as two different people (measured 2026-11-15: zero-crossing
rate 3152 vs 2733, different durations); seeded, they are byte-identical. These
tests pin the payload contract without touching a live engine.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.harness import voice


class _Response:
    status_code = 200
    content = b'ID3\x03\x00\x00'
    headers = {'content-type': 'audio/mpeg'}
    text = ''


def _settings(**overrides) -> SimpleNamespace:
    base = dict(
        voice_base_url='http://127.0.0.1:3900',
        voice_model='omnivoice',
        voice_name='default',
        voice_timeout=30.0,
        voice_api_key='',
        voice_seed=voice.DEFAULT_SEED,
        voice_language='',
        voice_num_step=None,
        voice_enabled=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _capture(monkeypatch) -> list:
    payloads: list = []

    def fake_post(settings, root, payload):
        payloads.append(payload)
        return _Response()

    monkeypatch.setattr(voice, '_post_speech', fake_post)
    monkeypatch.setattr(voice, 'resolve_model', lambda settings: ('omnivoice', ''))
    return payloads


def test_synthesis_pins_the_voice_design_seed(monkeypatch):
    payloads = _capture(monkeypatch)
    audio = voice.synthesize(_settings(), '先看常数项。')
    assert audio.startswith(b'ID3')
    assert payloads[0]['seed'] == 1234


def test_seed_zero_is_an_explicit_opt_out(monkeypatch):
    payloads = _capture(monkeypatch)
    voice.synthesize(_settings(voice_seed=0), 'word')
    assert 'seed' not in payloads[0]


def test_seed_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv('HARNESS_VOICE_SEED', '77')
    settings = _settings()
    del settings.voice_seed                       # simulate a settings type without it
    assert voice.voice_seed(settings) == 77


def test_unparseable_seed_falls_back_instead_of_failing(monkeypatch):
    assert voice.voice_seed(_settings(voice_seed='not-a-number')) == voice.DEFAULT_SEED


def test_language_is_sent_only_when_configured(monkeypatch):
    payloads = _capture(monkeypatch)
    voice.synthesize(_settings(), 'word')
    assert 'language' not in payloads[0]

    voice.synthesize(_settings(voice_language='zh'), 'word')
    assert payloads[1]['language'] == 'zh'


def test_num_step_is_off_by_default(monkeypatch):
    payloads = _capture(monkeypatch)
    voice.synthesize(_settings(), 'word')
    assert 'num_step' not in payloads[0]

    voice.synthesize(_settings(voice_num_step=8), 'word')
    assert payloads[1]['num_step'] == 8


def test_the_seed_survives_a_voice_preset_change(monkeypatch):
    """Changing the profile must not silently re-roll the speaker's design seed."""
    payloads = _capture(monkeypatch)
    voice.synthesize(_settings(), 'word', voice='warm_teacher')
    voice.synthesize(_settings(), 'word', voice='clear_narrator')
    assert payloads[0]['seed'] == payloads[1]['seed'] == 1234
    assert payloads[0]['voice'] != payloads[1]['voice']
