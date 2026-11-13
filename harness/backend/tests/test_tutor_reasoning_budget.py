"""The tutor's live turn must not spend its whole token ceiling on a hidden trace.

Measured 2026-11-13 with the configured ``deepseek-flash`` reasoning model and a real
``POST /chat`` turn: with ``max_tokens: 600`` and no reasoning control, the model spent
all 600 tokens on ``reasoning_content`` and returned an empty ``content`` with
``finish_reason: length``. The learner saw a declared fallback instead of a tutor reply.
On other turns the visible answer was cut off mid-sentence. This was the "tutor turn
failed with no declared reason" defect in the 2026-11-12 acceptance report: intermittent,
because how much of the budget the hidden trace consumes varies per turn.

``app.harness.provider.chat(reasoning='off')`` already solves this for artifact callers by
sending ``reasoning_effort: 'none'``. The tutor builds its own request, so it has to send
the same field. These tests pin that wire contract without a network call.
"""

from types import SimpleNamespace

from app import model_config, tutor


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
    sent = {}
    body = {}

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None, headers=None):
        _Client.sent = {'url': url, 'payload': json, 'headers': headers}
        return _Response(_Client.body)


def _install(monkeypatch, *, content='A worked step, then a question for you.',
             finish_reason='stop'):
    _Client.body = {
        'choices': [{'message': {'content': content},
                     'finish_reason': finish_reason}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
    _Client.sent = {}
    monkeypatch.setattr(tutor.httpx, 'Client', _Client)
    monkeypatch.setattr(tutor.model_config, 'effective', lambda settings: model_config.ModelConfig(
        provider='openai', provider_url='http://provider.test/v1',
        provider_model='reasoning-model', provider_key='k', provider_timeout=5.0))
    return SimpleNamespace(data_dir=None)


def test_tutor_turn_opts_out_of_the_hidden_reasoning_trace(monkeypatch):
    """The 600-token ceiling applies to the visible answer, not a hidden trace."""
    settings = _install(monkeypatch)
    text, answerer, _, _ = tutor.respond(
        settings, 'fractions', 'Why is a fraction a division?', history=[])

    assert _Client.sent['payload']['reasoning_effort'] == 'none'
    assert _Client.sent['payload']['max_tokens'] == 600
    assert answerer == 'openai:reasoning-model'
    assert text.strip()


def test_ollama_turn_is_left_alone(monkeypatch):
    """The flag belongs to the chat/completions wire, not Ollama's /api/chat options."""
    _Client.body = {'message': {'content': 'A worked step.'}, 'done_reason': 'stop'}
    _Client.sent = {}
    monkeypatch.setattr(tutor.httpx, 'Client', _Client)
    monkeypatch.setattr(tutor.model_config, 'effective', lambda settings: model_config.ModelConfig(
        provider='ollama', provider_url='http://provider.test',
        provider_model='reasoning-model', provider_key='', provider_timeout=5.0))

    text, answerer, _, _ = tutor.respond(
        SimpleNamespace(data_dir=None), 'fractions', 'Why?', history=[])

    assert 'reasoning_effort' not in _Client.sent['payload']
    assert answerer == 'ollama:reasoning-model'
    assert text.strip()
