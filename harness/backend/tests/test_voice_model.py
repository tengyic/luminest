"""Which model the harness asks VoiceStudio to speak with.

A wrong ``HARNESS_VOICE_MODEL`` does not fail cleanly. VoiceStudio 0.5.6 accepts the
synthesis request for a model it does not serve and then never answers, so the render
thread blocks until its timeout and the teacher is mute with nothing in the log. These
tests pin the guard that turns that into a substitution the operator can see.

No network: the advertised list is stubbed, because the point is the decision, not the
probe.
"""

from dataclasses import replace

from app.harness import voice
from test_api import settings  # noqa: F401 - fixture


def _with_models(monkeypatch, served):
    monkeypatch.setattr(voice, 'served_models', lambda _settings: tuple(served))


def test_a_served_model_is_used_as_configured(settings, monkeypatch):
    _with_models(monkeypatch, ['tts-1', 'omnivoice'])
    chosen, note = voice.resolve_model(replace(settings, voice_model='omnivoice'))
    assert chosen == 'omnivoice'
    assert note == '', 'no substitution means nothing to report'


def test_an_unserved_model_falls_back_to_an_alias(settings, monkeypatch):
    """The teacher keeps speaking; the operator is told why the voice changed."""
    _with_models(monkeypatch, ['tts-1', 'tts-1-hd', 'whisper-1'])
    chosen, note = voice.resolve_model(replace(settings, voice_model='omnivoice'))
    assert chosen == 'tts-1'
    assert 'omnivoice' in note and 'HARNESS_VOICE_MODEL=tts-1' in note


def test_the_alias_preference_is_stable(settings, monkeypatch):
    """``tts-1`` before ``tts-1-hd``: the cheaper alias, deterministically."""
    _with_models(monkeypatch, ['gpt-4o-mini-tts', 'tts-1-hd', 'tts-1'])
    chosen, _note = voice.resolve_model(replace(settings, voice_model='nope'))
    assert chosen == 'tts-1'


def test_an_unreadable_model_list_trusts_the_configuration(settings, monkeypatch):
    """No list is not evidence of a wrong name, and guessing would be worse than asking."""
    _with_models(monkeypatch, [])
    chosen, note = voice.resolve_model(replace(settings, voice_model='omnivoice'))
    assert chosen == 'omnivoice'
    assert note == ''


def test_the_substitution_is_reported_by_the_probe(settings, monkeypatch):
    _with_models(monkeypatch, ['tts-1'])
    monkeypatch.setattr(voice, '_client', lambda *_a, **_k: _FakeClient(200))
    answering, sentence = voice.probe(replace(settings, voice_model='omnivoice'))
    assert answering, 'the service is up, so this is not a liveness failure'
    assert 'omnivoice' in sentence and 'tts-1' in sentence


class _FakeResponse:
    def __init__(self, status):
        self.status_code = status


class _FakeClient:
    """Enough of ``httpx.Client`` for ``probe``: a GET that always answers 200."""

    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def get(self, _url):
        return _FakeResponse(self.status)
