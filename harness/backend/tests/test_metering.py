"""Every model turn must be accounted for, including the ones that reach no model.

The Beta's cost model is "meter everything and observe before limiting", which only works if
the ledger is actually written. These tests pin the two halves of that:

* a turn that reaches a provider records the provider's own token counts, and
* a turn that falls back to the offline tutor still records a row, with zero tokens, so the
  fallback rate stays visible instead of looking like no traffic at all.

They also guard the first-write path. ``mapped_column(default=0)`` is applied at flush, not at
construction, so a freshly built counter row reads ``None`` and the first metered call for a
new account used to raise ``TypeError`` inside ``accounts.record_usage``. That failure is
invisible until metering is wired up, which is exactly why it needs a test.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


def _account(client):
    response = client.post('/api/v1/auth/register',
                           json={'name': 'Ada', 'email': 'ada@example.test',
                                 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def _chat(client, headers):
    response = client.post('/api/v1/chat', headers=headers,
                           json={'concept_id': 'fractions', 'message': 'Explain fractions'})
    assert response.status_code == 200, response.text
    return response.json()


def test_offline_turn_is_recorded_as_a_fallback_with_no_tokens(settings):
    with TestClient(create_app(settings)) as client:
        headers = _account(client)
        before = client.get('/api/v1/usage', headers=headers).json()
        assert before['used'] == {'requests': 0, 'total_tokens': 0, 'cost_micros': 0}
        assert before['recent'] == []

        _chat(client, headers)

        after = client.get('/api/v1/usage', headers=headers).json()
        assert after['used']['requests'] == 1
        assert after['used']['total_tokens'] == 0
        assert len(after['recent']) == 1
        row = after['recent'][0]
        assert row['feature'] == 'tutor_chat'
        assert row['outcome'] == 'fallback'


@pytest.fixture
def fake_provider(settings, monkeypatch):
    """A minimal OpenAI-compatible endpoint that reports its own token usage.

    Depends on ``settings`` so the test still gets an isolated data directory -- without it
    ``Settings.from_env()`` falls back to the real one and the second account collides.
    """
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers.get('content-length', 0)))
            payload = json.dumps({
                'choices': [{'message': {'content': 'A grounded explanation of fractions.'}}],
                'usage': {'prompt_tokens': 1200, 'completion_tokens': 340, 'total_tokens': 1540},
            }).encode()
            self.send_response(200)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_URL', f'http://127.0.0.1:{server.server_address[1]}/v1')
    try:
        yield calls
    finally:
        server.shutdown()
        server.server_close()


def test_provider_token_counts_reach_the_ledger(settings, fake_provider):
    # Rebuilt after ``fake_provider`` set the tutor variables, so the provider points at the
    # fake endpoint while the data directory stays the per-test temporary one.
    settings = Settings.from_env()
    with TestClient(create_app(settings)) as client:
        headers = _account(client)
        reply = _chat(client, headers)
        assert reply['provider'] == 'openai:test-model'
        assert fake_provider, 'the tutor never called the configured provider'

        used = client.get('/api/v1/usage', headers=headers).json()
        assert used['used']['requests'] == 1
        assert used['used']['total_tokens'] == 1540          # 1200 prompt + 340 completion
        row = used['recent'][0]
        assert row['outcome'] == 'ok'
        assert row['provider'] == 'openai'
        assert row['model'] == 'test-model'
        assert row['total_tokens'] == 1540
        assert row['latency_ms'] is not None
