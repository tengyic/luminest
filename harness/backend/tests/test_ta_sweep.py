"""The TA's interval check: ``POST /api/v1/ta/sweep``.

The sweep is the TA's job in one call — does this concept have an asset, is the asset about
this concept, and is now a moment worth interrupting for. These tests pin the boundaries
that matter: only a teacher may run it, a learner cannot talk it into a verdict, an unknown
concept is a 404 rather than a fabricated review, and it does not write.

The instance is ``development`` rather than ``test`` on purpose: that is the only
environment where ``_ensure_operator`` promotes the first account, and the desktop app is
what this route exists for. A hosted instance would assign the role deliberately.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.db import State
from app.main import create_app

CONCEPT = 'permutations_and_combinations'
API = '/api/v1/ta/sweep'


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'development')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    with TestClient(create_app(Settings.from_env())) as client:
        yield client


def register(client, label):
    response = client.post('/api/v1/auth/register',
                           json={'name': label, 'email': f'{label}@example.test',
                                 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    value = response.json()
    return {'Authorization': 'Bearer ' + value['token']}, value


@pytest.fixture
def teacher(app_client):
    """The first account on a local instance is the operator, so it is the teacher."""
    headers, user = register(app_client, 'teacher')
    assert user['user']['role'] == 'teacher'
    return headers


# ---------------------------------------------------------------- the review itself

def test_a_teacher_gets_an_asset_review_for_the_concept(app_client, teacher):
    response = app_client.post(API, json={'concept_id': CONCEPT}, headers=teacher)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body['concept']['id'] == CONCEPT
    assert body['concept']['course_id']
    assert body['concept']['subject_kind'] == 'mathematics'
    assert body['figure']['kind'] == 'arrangements'
    assert body['assets']['clean'], body['assets']
    assert body['ready'] is True
    assert body['plan'] == []
    assert body['report'] == ''


def test_the_figure_returned_is_the_one_that_was_reviewed(app_client, teacher):
    """Rebuilt rather than cached, so a client can render exactly what was judged."""
    body = app_client.post(API, json={'concept_id': CONCEPT}, headers=teacher).json()
    assert body['figure']['series']
    assert body['figure']['readouts']
    assert body['figure']['parameters']


def test_a_learner_cannot_run_the_sweep(app_client, teacher):
    learner, _user = register(app_client, 'learner')
    response = app_client.post(API, json={'concept_id': CONCEPT}, headers=learner)
    assert response.status_code == 403


def test_an_unknown_concept_is_not_fabricated(app_client, teacher):
    response = app_client.post(API, json={'concept_id': 'not_a_concept'}, headers=teacher)
    assert response.status_code == 404
    assert 'not_a_concept' in response.json()['detail']


def test_a_client_cannot_state_its_own_mastery(app_client, teacher):
    """Same refusal as ``/supervision/assess``: the check must not grade its own homework."""
    response = app_client.post(API, json={'concept_id': CONCEPT,
                                          'signals': {'mastery': 1.0, 'mastery_known': True}},
                               headers=teacher)
    assert response.status_code == 422


# ---------------------------------------------------------------- supervision half

def test_signals_turn_the_sweep_into_a_decision(app_client, teacher):
    body = app_client.post(API, json={'concept_id': CONCEPT,
                                      'signals': {'idle_seconds': 900, 'window_seconds': 300}},
                           headers=teacher).json()
    assert body['supervision']['state'] == 'away'
    assert body['ready'] is False
    assert 'away' in body['report']


def test_a_working_learner_is_left_alone(app_client, teacher):
    """The sweep must not manufacture a reason to speak for someone who is on task."""
    body = app_client.post(API, json={'concept_id': CONCEPT,
                                      'signals': {'active_seconds': 280, 'window_seconds': 300,
                                                  'scroll_events': 12, 'click_events': 4}},
                           headers=teacher).json()
    assert body['supervision']['state'] == 'working'
    assert body['supervision']['move']['kind'] == 'continue'
    assert body['report'] == ''
    assert body['ready'] is True


def test_the_sweep_does_not_write(app_client, teacher):
    """A reading is not a record; the only thing a caller may keep is the output."""
    from app import user_scope

    factory = app_client.app.state.factory

    def state_rows() -> int:
        # Counting every row is cross-user by design, so it goes through the audited
        # escape hatch rather than being quietly exempted.
        with user_scope.unscoped('test: count learning_states before and after a sweep'):
            with factory() as db:
                return db.scalar(select(func.count()).select_from(State))

    before = state_rows()
    for _ in range(3):
        app_client.post(API, json={'concept_id': CONCEPT, 'signals': {'idle_seconds': 900}},
                        headers=teacher)
    assert state_rows() == before
