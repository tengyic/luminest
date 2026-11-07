"""What a client can learn when a clip does not arrive.

The speech path is asynchronous by design: a turn returns ``pending`` and the client
polls. That makes one failure mode unusually quiet -- a render that dies writes no
bytes, so every poll gets the same 404 whether the clip is coming or never will. These
tests pin the answer: ``state`` distinguishes the two, and it carries the engine's own
sentence so the operator has something to act on.
"""

import time

import pytest

from app.config import Settings
from app.harness import speech, voice as voice_backend


def settings_for(tmp_path, monkeypatch, *, media_enabled=True, voice_enabled=True):
    """Voice output is its own gate.

    It used to be implied by ``HARNESS_MEDIA_ENABLED``, so a test that wanted "nothing
    is spoken here" switched media off. They are separate switches now, and voice
    defaults **on** outside production -- which means a test that only cleared media
    still had a speaking engine and saw ``pending`` where it expected ``unavailable``.
    State the gate you mean.
    """
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '1' if media_enabled else '0')
    monkeypatch.setenv('HARNESS_VOICE_ENABLED', '1' if voice_enabled else '0')
    return Settings.from_env()


@pytest.fixture(autouse=True)
def clean_module_state():
    """The render bookkeeping is module-level, so it outlives a test.

    Without this, a digest left in flight by one test is read as ``pending`` by the next
    -- and the failure looks like a broken warm-up rather than a shared cache.
    """
    with speech._guard:
        speech._in_flight.clear()
        speech._outcomes.clear()
    yield
    with speech._guard:
        speech._in_flight.clear()
        speech._outcomes.clear()


def fake_engine(monkeypatch, payload=b'ID3fake-audio-bytes'):
    monkeypatch.setattr(speech.voice_backend, 'synthesize',
                        lambda settings, text, **kwargs: payload)


def broken_engine(monkeypatch, reason='VoiceStudio is not running at http://127.0.0.1:3900.'):
    def refuse(settings, text, **kwargs):
        raise voice_backend.VoiceError('not_running', reason)
    monkeypatch.setattr(speech.voice_backend, 'synthesize', refuse)


def wait_for(settings, digest, wanted, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = speech.state(settings, digest)
        if state.get('state') == wanted:
            return state
        time.sleep(0.02)
    return speech.state(settings, digest)


def test_a_render_that_fails_says_so_instead_of_staying_pending(tmp_path, monkeypatch):
    settings = settings_for(tmp_path, monkeypatch)
    broken_engine(monkeypatch)

    descriptor = speech.request(settings, 'Permutations count ordered arrangements.')
    assert descriptor['state'] == speech.PENDING

    state = wait_for(settings, descriptor['digest'], speech.FAILED)
    assert state['state'] == speech.FAILED
    assert state['code'] == 'not_running'
    assert 'not running' in state['reason']


def test_a_render_that_lands_is_ready_and_state_agrees(tmp_path, monkeypatch):
    settings = settings_for(tmp_path, monkeypatch)
    fake_engine(monkeypatch)

    descriptor = speech.request(settings, 'Combinations count unordered selections.')
    state = wait_for(settings, descriptor['digest'], speech.READY)
    assert state['state'] == speech.READY
    assert state['bytes'] == len(b'ID3fake-audio-bytes')


def test_an_unknown_digest_is_not_reported_as_a_failure(tmp_path, monkeypatch):
    """``unknown`` and ``failed`` are different answers, and only one is actionable."""
    settings = settings_for(tmp_path, monkeypatch)
    assert speech.state(settings, 'a' * 16)['state'] == 'unknown'


def test_a_failure_is_never_cached_as_a_clip(tmp_path, monkeypatch):
    settings = settings_for(tmp_path, monkeypatch)
    broken_engine(monkeypatch)
    descriptor = speech.request(settings, 'Nothing will be spoken here.')
    wait_for(settings, descriptor['digest'], speech.FAILED)
    assert speech.file_for(settings, descriptor['digest']) is None


def test_warm_up_is_skipped_when_voice_output_is_off(tmp_path, monkeypatch):
    settings = settings_for(tmp_path, monkeypatch, voice_enabled=False)
    called = []
    monkeypatch.setattr(speech.voice_backend, 'probe', lambda _s: called.append(1) or (True, ''))
    speech.warm(settings)
    time.sleep(0.2)
    assert called == []


def test_warm_up_touches_the_engine_before_a_learner_does(tmp_path, monkeypatch):
    """The cold load belongs at launch: it outlasts a render timeout otherwise."""
    settings = settings_for(tmp_path, monkeypatch)
    fake_engine(monkeypatch)
    monkeypatch.setattr(speech.voice_backend, 'probe', lambda _s: (True, ''))

    speech.warm(settings)
    digest = speech.plan(settings, speech.WARM_PHRASE)['digest']
    state = wait_for(settings, digest, speech.READY, seconds=10.0)
    assert state['state'] == speech.READY


def test_the_digest_follows_the_engine_that_will_speak(tmp_path, monkeypatch):
    """A substituted model is different audio, so it must not reuse the old clip."""
    monkeypatch.setenv('HARNESS_VOICE_MODEL', 'omnivoice')
    settings = settings_for(tmp_path, monkeypatch)
    # The engine advertises only the alias, so ``omnivoice`` is rerouted to ``tts-1``.
    monkeypatch.setattr(speech.voice_backend, 'served_models', lambda _s: ('tts-1',))

    substituted = speech.plan(settings, 'Same words, different engine.')
    monkeypatch.setenv('HARNESS_VOICE_MODEL', 'tts-1')
    explicit = speech.plan(settings_for(tmp_path, monkeypatch), 'Same words, different engine.')

    # Both end up spoken by tts-1, so they are the same audio and may share a clip...
    assert substituted['digest'] == explicit['digest']
    # ...whereas asking for an engine that is actually served must not.
    monkeypatch.setenv('HARNESS_VOICE_MODEL', 'omnivoice')
    monkeypatch.setattr(speech.voice_backend, 'served_models', lambda _s: ('omnivoice', 'tts-1'))
    served = speech.plan(settings_for(tmp_path, monkeypatch), 'Same words, different engine.')
    assert served['digest'] != substituted['digest']


# ------------------------------------------------------- speaking a whole reply

LONG_REPLY = (
    'Good, let us start by finding out what you already have, rather than me guessing. '
    'Here is the first quick question. One of these four is the right description of '
    "today's topic. Pick one, and say in a sentence why you picked it. Even a guess is "
    'useful, because I want to hear your reasoning, not just the letter. One thing to '
    'hold for you: the interactive you asked for is coming later in the lesson, after '
    'the deck, so keep the question you want to test with it.')


def test_a_reply_is_split_into_clips_short_enough_to_be_heard_soon():
    clips = speech.utterances(LONG_REPLY)
    assert len(clips) > 1
    assert all(len(clip) <= speech.CHUNK_CHARS for clip in clips), [len(c) for c in clips]
    # Nothing is dropped: the clips are the reply, in order.
    assert ' '.join(clips).split() == LONG_REPLY.split()


def test_a_split_never_lands_mid_word():
    for clip in speech.utterances(LONG_REPLY * 2):
        assert not clip.startswith(' '), clip
        assert clip[-1] in '.!?,;' or clip[-1].isalpha(), clip


def test_an_empty_reply_has_nothing_to_speak():
    assert speech.utterances('   ') == []


def test_the_sequence_renders_every_clip_and_names_the_first(tmp_path, monkeypatch):
    settings = settings_for(tmp_path, monkeypatch)
    fake_engine(monkeypatch)

    sequence = speech.request_sequence(settings, LONG_REPLY)

    assert sequence['total'] == len(sequence['clips'])
    assert sequence['url'] == sequence['clips'][0]['url']
    for clip in sequence['clips']:
        assert wait_for(settings, clip['digest'], speech.READY)['state'] == speech.READY


def test_a_sequence_with_voice_output_off_says_so_once(tmp_path, monkeypatch):
    settings = settings_for(tmp_path, monkeypatch, voice_enabled=False)
    sequence = speech.request_sequence(settings, LONG_REPLY)
    assert sequence['state'] == speech.UNAVAILABLE
    assert 'HARNESS_VOICE_ENABLED' in sequence['reason']
