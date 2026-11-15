"""A configured model with no credit must name its cause, not look like a bad URL.

Measured on 2026-11-15 with a real DeepSeek key: ``/models`` authenticated, but the
account balance was -0.01 CNY and every completion answered 402
``{"error": {"message": "Insufficient Balance"}}``. The harness already degrades to a
declared curriculum fallback in that case. These tests pin the part that was missing:
the reason must survive into the ledger, the learner-visible fallback text and the
Settings "test model" screen, so nobody debugs the endpoint for a billing problem.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from app import model_config, routes_model_config, tutor
from app.config import Settings
from app.harness import provider


def _install(monkeypatch, tmp_path, *, status=402, body=None):
    """A provider that answers with a real HTTP error, plus a configured model."""
    original = httpx.Client
    payload = body if body is not None else {'error': {'message': 'Insufficient Balance'}}

    def factory(**kwargs):
        for key in ('timeout', 'follow_redirects', 'trust_env'):
            kwargs.pop(key, None)

        def handler(request):
            return httpx.Response(status, json=payload, request=request)

        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, 'Client', factory)
    monkeypatch.setattr(model_config, 'effective', lambda settings: model_config.ModelConfig(
        provider='openai', provider_url='https://provider.example.test/v1',
        provider_model='deepseek-flash', provider_key='k', provider_timeout=5.0))
    for name, value in (('HARNESS_ENV', 'test'), ('HARNESS_DATA_DIR', str(tmp_path)),
                        ('HARNESS_TUTOR_PROVIDER', 'openai'),
                        ('HARNESS_TUTOR_URL', 'https://provider.example.test/v1'),
                        ('HARNESS_TUTOR_MODEL', 'deepseek-flash'),
                        ('HARNESS_TUTOR_KEY', 'k'),
                        ('HARNESS_TUTOR_TIMEOUT_SECONDS', '5')):
        monkeypatch.setenv(name, value)
    return Settings.from_env()


def _http_error(status, json_body=None, text=None):
    request = httpx.Request('POST', 'https://provider.example.test/v1/chat/completions')
    response = (httpx.Response(status, json=json_body, request=request)
                if json_body is not None
                else httpx.Response(status, text=text or '', request=request))
    return httpx.HTTPStatusError(f'HTTP {status}', request=request, response=response)


def test_error_detail_reads_a_provider_shaped_error():
    detail = provider.error_detail(_http_error(402, {'error': {'message': 'Insufficient Balance'}}))
    assert detail == 'HTTP 402: Insufficient Balance'


def test_error_detail_degrades_without_raising():
    assert provider.error_detail(_http_error(503, text='upstream maintenance')) == \
        'HTTP 503: upstream maintenance'
    assert provider.error_detail(httpx.ConnectError('offline')) == 'ConnectError'
    # A provider that returns a huge or oddly shaped body must not leak it into the UI.
    long = _http_error(400, {'error': {'message': 'x' * 500}})
    assert len(provider.error_detail(long)) < 200


def test_chat_records_the_reason_in_usage(monkeypatch, tmp_path):
    settings = _install(monkeypatch, tmp_path)
    usage: dict = {}
    assert provider.chat(settings, [{'role': 'user', 'content': 'hi'}], usage_out=usage) is None
    assert usage['outcome'] == 'error'
    assert 'Insufficient Balance' in usage['error_detail']


def test_chat_tools_records_the_reason_too(monkeypatch, tmp_path):
    settings = _install(monkeypatch, tmp_path)
    usage: dict = {}
    assert provider.chat_tools(settings, [{'role': 'user', 'content': 'hi'}],
                               tools=[], usage_out=usage) is None
    assert 'Insufficient Balance' in usage['error_detail']


def test_tutor_fallback_names_the_balance_failure(monkeypatch, tmp_path):
    settings = _install(monkeypatch, tmp_path)
    usage: dict = {}
    text, answerer, _, _ = tutor.respond(
        settings, 'fractions', 'Why is a fraction a division?', history=[], usage_out=usage)

    assert 'fallback' in answerer.lower()          # never claims a model wrote it
    assert 'Insufficient Balance' in text
    assert 'curriculum instead of a model' in text  # declared, not silent
    assert usage['error_detail'].startswith('HTTP 402')


def test_settings_test_screen_names_the_balance_failure(monkeypatch, tmp_path):
    settings = _install(monkeypatch, tmp_path)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    result = routes_model_config.test_config(request, auth=(None, SimpleNamespace(role='learner')))

    assert result['ok'] is False
    assert result['state'] == 'unreachable'
    assert 'Insufficient Balance' in result['detail']
    assert 'Insufficient Balance' in result['usage']['error_detail']
