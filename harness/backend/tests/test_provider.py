"""The provider's wire contract, pinned where it can be observed.

Three things here are not obvious from reading a caller and have each cost real debugging
time:

* this endpoint is a *reasoning* model whose hidden trace is billed against
  ``max_tokens``, so a caller asking for an artefact must be able to say "no trace";
* ``chat`` returns ``None`` for a refusal, an empty reply and a truncated one alike, so
  the only way a caller can tell them apart is the ``finish_reason`` it reports;
* the reply-size guard is sized for a chat turn, and an artefact larger than that is a
  success the guard would otherwise throw away.
"""

from types import SimpleNamespace

import pytest

from app.harness import provider


def _settings(**overrides):
    base = dict(provider='openai', provider_url='http://provider.test/v1',
                provider_key='k', provider_model='m', provider_timeout=5.0)
    base.update(overrides)
    return SimpleNamespace(**base)


class _Response:
    status_code = 200
    content = b'{}'

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


class _Client:
    """Stands in for httpx.Client, recording the payload the provider would receive."""

    sent: dict = {}
    body: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None, headers=None):
        _Client.sent = {'url': url, 'payload': json, 'headers': headers}
        return _Response(_Client.body)


def _install(monkeypatch, *, content, finish_reason='stop', usage=None):
    _Client.body = {
        'choices': [{'message': {'content': content}, 'finish_reason': finish_reason}],
        'usage': usage or {'prompt_tokens': 10, 'completion_tokens': 5,
                           'total_tokens': 15}}
    _Client.sent = {}
    monkeypatch.setattr(provider.httpx, 'Client', _Client)
    monkeypatch.setattr(provider, 'available', lambda settings: True)


def test_reasoning_off_tells_the_endpoint_not_to_spend_the_budget_on_its_trace(monkeypatch):
    _install(monkeypatch, content='<!doctype html><html></html>')
    provider.chat(_settings(), [{'role': 'user', 'content': 'build a sim'}], reasoning='off')
    assert _Client.sent['payload']['reasoning_effort'] == 'none'


def test_the_default_leaves_the_reasoning_budget_to_the_model(monkeypatch):
    """Only a caller that knows it wants an artefact should switch the trace off."""
    _install(monkeypatch, content='an answer')
    provider.chat(_settings(), [{'role': 'user', 'content': 'explain'}])
    assert 'reasoning_effort' not in _Client.sent['payload']


def test_truncation_is_visible_on_a_reply_that_still_has_text(monkeypatch):
    """A cut-off reply arrives as text; ``finish_reason`` is the only signal it is partial.

    This is the failure that made "the model did not return a complete HTML document"
    unactionable. The transport is right to hand back what arrived -- the caller decides
    whether a half-file is usable -- but it has to say that the generation stopped early,
    or the caller cannot tell a complete document from a truncated one.
    """
    _install(monkeypatch, content='<!doctype html><html><body>half', finish_reason='length',
             usage={'prompt_tokens': 443, 'completion_tokens': 12000, 'total_tokens': 12443})
    usage = {}
    text = provider.chat(_settings(), [{'role': 'user', 'content': 'x'}], usage_out=usage)
    assert text == '<!doctype html><html><body>half'
    assert usage['finish_reason'] == 'length'
    assert usage['completion_tokens'] == 12000


def test_a_reply_that_spent_its_whole_budget_on_reasoning_still_reports_the_reason(monkeypatch):
    """The empty-content case: every token went to the trace, so no answer came back.

    Measured 2026-11-01 on this endpoint: a simulation request at ``max_tokens=8000``
    returned ``completion_tokens: 8000`` and empty content. The return value is ``None``
    either way, so the ``finish_reason`` is what distinguishes it from a refusal.
    """
    _install(monkeypatch, content='', finish_reason='length',
             usage={'prompt_tokens': 443, 'completion_tokens': 8000, 'total_tokens': 8443})
    usage = {}
    assert provider.chat(_settings(), [{'role': 'user', 'content': 'x'}],
                         usage_out=usage) is None
    assert usage['finish_reason'] == 'length'
    assert usage['outcome'] == 'error'


def test_a_large_artefact_can_raise_the_reply_guard_for_one_call(monkeypatch):
    """The default guard is a chat-turn guard; an artefact is legitimately bigger."""
    big = '<!doctype html>' + ('x' * (provider.MAX_REPLY_CHARS + 100))
    _install(monkeypatch, content=big)
    assert provider.chat(_settings(), [{'role': 'user', 'content': 'x'}]) is None
    assert provider.chat(_settings(), [{'role': 'user', 'content': 'x'}],
                         max_reply_chars=len(big) + 10) == big
