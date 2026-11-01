"""The engine has one worker; the harness must behave as if it knows that.

Two facts about a stock VoiceStudio, both observed rather than assumed:

1. A second concurrent synthesis is **refused** with a 429 ("1 running, 1 already queued
   on 1 worker(s)"), not queued. Firing two sentences at once therefore produces one clip
   and one refusal.
2. The refusal says the request was never started and is safe to retry, and quotes how
   long to wait.

So the harness serialises its own requests, and retries a refusal once after the interval
the engine asked for. Both are pinned here, because both failures look like "the teacher
is sometimes mute" from the outside.
"""

import threading
import time

import pytest

from app.harness import voice
from test_api import settings  # noqa: F401 - fixture


class _Response:
    def __init__(self, status_code, body=b'ID3audio', headers=None, payload=None):
        self.status_code = status_code
        self.content = body
        self.headers = headers or {'content-type': 'audio/mpeg'}
        self.text = body.decode('utf-8', 'replace') if body else ''
        self._payload = payload

    def json(self):
        if self._payload is not None:
            return self._payload
        raise ValueError('not json')


class _Client:
    """Enough of ``httpx.Client`` for ``synthesize``: a GET for the model list, a POST."""

    def __init__(self, posts):
        self.posts = posts
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def get(self, _url):
        return _Response(200, b'{}', {'content-type': 'application/json'},
                         payload={'data': [{'id': 'omnivoice'}]})

    def post(self, _url, json=None):
        index = min(self.calls, len(self.posts) - 1)
        self.calls += 1
        return self.posts[index]


def _patch_client(monkeypatch, factory):
    monkeypatch.setattr(voice, '_client', lambda settings, read_timeout: factory())


def test_two_sentences_never_reach_the_engine_at_once(settings, monkeypatch):
    live = settings
    overlap = {'now': 0, 'peak': 0}
    guard = threading.Lock()

    class Slow(_Client):
        def post(self, _url, json=None):
            with guard:
                overlap['now'] += 1
                overlap['peak'] = max(overlap['peak'], overlap['now'])
            time.sleep(0.15)
            with guard:
                overlap['now'] -= 1
            return _Response(200)

    _patch_client(monkeypatch, lambda: Slow([_Response(200)]))

    threads = [threading.Thread(target=lambda: voice.synthesize(live, 'one sentence'))
               for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert overlap['peak'] == 1, 'the engine was asked to do two at once'


def test_a_busy_engine_is_retried_after_the_interval_it_names(settings, monkeypatch):
    live = settings
    busy = _Response(429, b'{"error":{"message":"the pool is saturated; safe to retry '
                          b'as-is in about 5s"}}',
                     {'content-type': 'application/json'})
    _patch_client(monkeypatch, lambda: _Client([busy, _Response(200)]))

    waits = []
    monkeypatch.setattr(voice.time, 'sleep', lambda seconds: waits.append(seconds))

    assert voice.synthesize(live, 'one sentence') == b'ID3audio'
    assert waits == [5.0], 'the engine asked for about five seconds'


def test_a_second_refusal_is_reported_rather_than_retried_forever(settings, monkeypatch):
    live = settings
    busy = _Response(429, b'{"error":{"message":"saturated; retry in about 2s"}}',
                     {'content-type': 'application/json'})
    _patch_client(monkeypatch, lambda: _Client([busy, busy]))
    monkeypatch.setattr(voice.time, 'sleep', lambda seconds: None)

    with pytest.raises(voice.VoiceError) as raised:
        voice.synthesize(live, 'one sentence')

    assert raised.value.code == 'busy'
    assert raised.value.retryable
