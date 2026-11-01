"""The guided-simulation contract at the HTTP boundary.

The module-level contract is tested in ``test_guided_sim.py``. What is tested here is the
part that touches the database: a simulation run that skipped a phase must be refused
*before* anything is written, and a complete run must move mastery on the guided credit
rather than on the game's self-reported flag.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings

#: A bundled game whose concept resolves inside the default course, so the run is
#: attributable and the mastery path is exercised rather than skipped.
GAME = 'math-balance-scale-two-step'


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


@pytest.fixture
def learner(settings):
    from app.main import create_app
    with TestClient(create_app(settings)) as client:
        body = client.post('/api/v1/auth/register', json={
            'name': 'Guided Tester', 'email': 'guided@example.com',
            'password': 'correct-horse-battery'}).json()
        yield client, {'Authorization': f"Bearer {body['token']}"}


def _guided(**overrides):
    block = {
        'sim_id': 'balance-scale',
        'prediction': 'the pan tips left',
        'actual': 'the pan tips left',
        'exploration_score': 0.7,
        'explanation': ('Both sides lost the same amount, so the balance stayed equal and '
                        'the remaining value on each pan is the same.'),
        'steps_completed': ['predict', 'manipulate', 'explain'],
    }
    block.update(overrides)
    return block


def _post(client, headers, **body):
    payload = {'correct': True, 'artifact_id': 'art-1', 'task_id': 't1',
               'tries': 1, 'elapsed_ms': 4000, **body}
    return client.post(f'/api/v1/playground/games/{GAME}/outcome', headers=headers,
                       json=payload)


def test_a_complete_guided_run_is_recorded_and_moves_mastery(learner):
    client, headers = learner
    response = _post(client, headers, guided=_guided())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['scaffolding'] == 'guided'
    assert body['guided_credit']['counts_as_correct'] is True
    assert body['attributed'] is True
    assert body['mastery_after'] > (body['mastery_before'] or 0.0)


def test_a_run_that_skipped_the_explanation_is_refused_before_anything_is_written(learner):
    client, headers = learner
    response = _post(client, headers,
                     guided=_guided(steps_completed=['predict', 'manipulate']))
    assert response.status_code == 422
    detail = response.json()['detail']
    assert any('explain' in problem for problem in detail['problems'])
    assert 'contract' in detail
    # Nothing was recorded: the run list is still empty.
    runs = client.get('/api/v1/playground/runs', headers=headers).json()['runs']
    assert runs == []


def test_a_two_word_explanation_does_not_count_as_explaining(learner):
    client, headers = learner
    response = _post(client, headers, guided=_guided(explanation='idk'))
    assert response.status_code == 422
    assert any('at least' in problem for problem in response.json()['detail']['problems'])


def test_the_guided_credit_overrides_a_self_reported_correct_flag(learner):
    """The game says "correct"; the prediction was wrong. The prediction wins."""
    client, headers = learner
    response = _post(client, headers, correct=True,
                     guided=_guided(prediction='the pan tips right'))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['correct'] is False
    assert body['guided_credit']['counts_as_correct'] is False
    assert body['detail']['reported_correct'] is True


def test_a_run_without_the_guided_block_still_records_as_before(learner):
    client, headers = learner
    response = _post(client, headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['scaffolding'] == 'none'
    assert 'guided_credit' not in body
    assert body['correct'] is True


def test_the_stored_detail_carries_the_scored_cycle_for_audit(learner):
    """The credit decision is stored next to the outcome that produced it, so a reviewer
    can tell a guided run from a bare one without re-deriving anything."""
    client, headers = learner
    body = _post(client, headers, guided=_guided()).json()
    assert body['detail']['guided_sim']['prediction_correct'] is True
    assert body['detail']['guided_credit']['counts_as_correct'] is True
    assert body['detail']['reported_correct'] is True
    # And the run is visible in the learner's own history, like any other run.
    runs = client.get('/api/v1/playground/runs', headers=headers).json()['runs']
    assert [run['task_id'] for run in runs] == ['t1']
