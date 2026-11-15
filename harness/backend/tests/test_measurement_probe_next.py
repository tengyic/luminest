"""``GET /measurement/probe/next`` must answer for a learner *with* attempts.

``episodes.label_attempts`` normalises attempts into dictionaries. The cold-probe
decision read ``row.question_id`` as an ORM attribute on one line while using
``row.get(...)`` everywhere else, so the first graded attempt in a sitting turned
the read-only budget endpoint into a 500. That is precisely the population the
measurement surface exists for, and the bug was invisible to tests that only
called ``probe.cold_probe_decision`` with hand-built inputs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app, graded_attempts


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


def test_probe_next_answers_when_the_learner_has_graded_attempts(env, monkeypatch):
    now = 1_700_000_000.0
    rows = [
        {'created_at': now + i * 60.0, 'elapsed_seconds': 12.0,
         'concept_id': 'fractions', 'correct': i % 2 == 0, 'mode': 'practice',
         'question_id': f'q-{i}', 'aid': 'none', 'tutor': False, 'lesson': False}
        for i in range(1, 6)
    ]
    monkeypatch.setattr('app.main.graded_attempts', lambda db, user: rows)

    with TestClient(create_app(env)) as client:
        registered = client.post('/api/v1/auth/register', json={
            'name': 'probe learner', 'email': 'probe@example.test',
            'password': 'long-secret-password'})
        assert registered.status_code == 201, registered.text
        headers = {'Authorization': 'Bearer ' + registered.json()['token']}
        response = client.get('/api/v1/measurement/probe/next', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        # The decision itself is the contract: a named state, not an exception.
        assert isinstance(body, dict) and body


def test_probe_next_still_answers_with_no_attempts(env):
    with TestClient(create_app(env)) as client:
        registered = client.post('/api/v1/auth/register', json={
            'name': 'fresh learner', 'email': 'fresh@example.test',
            'password': 'long-secret-password'})
        assert registered.status_code == 201, registered.text
        headers = {'Authorization': 'Bearer ' + registered.json()['token']}
        response = client.get('/api/v1/measurement/probe/next', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['due'] is False and body['reason'] == 'no_eligible_concept'
        assert body['why']
