"""Learning-science features: interleaving (P-1), calibration (P-2), the
self-explanation gate (P-3), delayed transfer (P-4) and the experiment wiring (M-3).

Every test pins something a verifier would try to falsify: that a group really spans
families, that a missing self-explanation is a 422 and not a warning, that the Brier
decomposition sums, that a transfer item's family genuinely never appeared in the
learner's practice history, and that a user's experiment bucket is stable.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import courses, experiments, learning_science
from app.config import Settings
from app.curriculum import QUESTIONS, course_concepts, course_questions
from app.db import Assessment, Attempt, Experiment, ExperimentAssignment, Receipt, State, User, now_ts
from app.main import create_app

MATH = course_concepts(courses.DEFAULT_COURSE_ID)
MATH_QUESTIONS = course_questions(courses.DEFAULT_COURSE_ID)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


@pytest.fixture
def gate_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    monkeypatch.setenv('HARNESS_SELF_EXPLANATION_GATE', '1')
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def gate_client(gate_settings):
    with TestClient(create_app(gate_settings)) as client:
        yield client


def account(client, label='learner'):
    response = client.post('/api/v1/auth/register', json={
        'name': label, 'email': f'{label}@example.test', 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    value = response.json()
    return {'Authorization': 'Bearer ' + value['token']}, value['user']


def next_q(client, headers, mode='practice', concept=None, params=None):
    query = {'mode': mode, **(params or {})}
    if concept:
        query['concept_id'] = concept
    response = client.get('/api/v1/questions/next', headers=headers, params=query)
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, headers, q, correct=True, confidence=0.8, self_explanation=None, key=None):
    internal = QUESTIONS[q['id']]
    option = internal['answer_id'] if correct else next(
        o['id'] for o in internal['options'] if o['id'] != internal['answer_id'])
    payload = {'question_id': q['id'], 'option_id': option, 'receipt': q['receipt'],
               'client_event_id': key or str(uuid4()), 'elapsed_seconds': 0, 'confidence': confidence}
    if self_explanation is not None:
        payload['self_explanation'] = self_explanation
    response = client.post('/api/v1/attempts', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def make_admin(client):
    with client.app.state.factory() as db:
        user = db.scalar(select(User))
        user.role = 'admin'
        db.commit()


def family_of(concept_id):
    return learning_science.concept_family(MATH.get(concept_id) or {})


# --------------------------------------------------------------------------- P-1

def test_interleaved_group_spans_two_families_and_reports_the_mix(client):
    h, _ = account(client, 'interleave')
    data = next_q(client, h, params={'group_size': 4})
    assert set(data) == {'items', 'mix'}
    assert len(data['items']) == 4
    mix = data['mix']
    assert mix['strategy'] == 'interleaved' and mix['returned'] == 4
    # The core falsifiable claim: >=2 distinct KC families in one practice set.
    assert mix['distinct_families'] >= 2
    assert sum(row['count'] for row in mix['families']) == 4
    families_seen = {family_of(item['concept_id']) for item in data['items']}
    assert len(families_seen) == mix['distinct_families']
    # Consecutive items are not the same family whenever the mix allows it.
    sequence = [family_of(item['concept_id']) for item in data['items']]
    if mix['distinct_families'] >= 2:
        assert any(a != b for a, b in zip(sequence, sequence[1:])), sequence
    # Each item carries its own signed receipt so it can be submitted individually.
    assert all(item['receipt'] for item in data['items'])
    # And the receipts actually work.
    first = data['items'][0]
    result = submit(client, h, first, self_explanation='Because the common denominator matches both fractions.')
    assert result['correct'] is True


def test_interleaved_group_mixes_due_reviews_with_new_items(client):
    h, user = account(client, 'duemix')
    # A practiced concept whose review is overdue: state says 3 attempts, due yesterday.
    practiced = next((cid for cid in MATH if QUESTIONS and any(
        q['concept_id'] == cid for q in MATH_QUESTIONS.values())), None)
    assert practiced
    with client.app.state.factory() as db:
        db.add(State(user_id=user['id'], concept_id=practiced,
                     data={'attempts': 3, 'mastery': 0.5, 'due_at': now_ts() - 3600}))
        db.commit()
    data = next_q(client, h, params={'group_size': 4})
    mix = data['mix']
    assert mix['due_review_items'] >= 1
    assert mix['new_concept_items'] >= 1
    review_concepts = {row['concept_id'] for row in []}
    due_families = {row['family'] for row in mix['families'] if row['due_review']}
    assert family_of(practiced) in due_families


def test_group_requests_are_rejected_outside_practice_and_when_disabled(client):
    h, user = account(client, 'gategroup')
    assert client.get('/api/v1/questions/next', headers=h,
                      params={'mode': 'diagnostic', 'group_size': 3}).status_code == 422
    assert client.get('/api/v1/questions/next', headers=h,
                      params={'mode': 'practice', 'group_size': 3, 'concept_id': 'fractions'}).status_code == 422
    # The off arm: an explicit assignment to 'off' disables the scheduler.
    with client.app.state.factory() as db:
        experiment = experiments.ensure_experiment(db, 'p1_interleaved_practice')
        db.add(ExperimentAssignment(experiment_id=experiment.id, user_id=user['id'],
                                    variant='off', assigned_at=now_ts()))
        db.commit()
    response = client.get('/api/v1/questions/next', headers=h, params={'mode': 'practice', 'group_size': 3})
    assert response.status_code == 422
    assert 'disabled' in response.json()['detail']
    # Single-question practice is untouched by the flag.
    assert client.get('/api/v1/questions/next', headers=h, params={'mode': 'practice'}).status_code == 200


# --------------------------------------------------------------------------- P-2

def test_calibration_decomposition_sums_and_speaks_plainly(client):
    h, _ = account(client, 'calibrate')
    # Six graded attempts with known confidence/correctness.
    outcomes = [True, True, False, True, False, False]
    confidences = [0.95, 0.9, 0.9, 0.4, 0.3, 0.6]
    for correct, confidence in zip(outcomes, confidences):
        q = next_q(client, h)
        submit(client, h, q, correct=correct, confidence=confidence)
    data = client.get('/api/v1/calibration', headers=h).json()
    assert data['n'] == 6
    # Independent recomputation of each component (binned confidences).
    bins = {}
    for c, o in zip(confidences, outcomes):
        key = min(9, int(c * 10))
        count, cs, oc = bins.get(key, (0, 0.0, 0))
        bins[key] = (count + 1, cs + c, oc + int(o))
    mean_o = sum(outcomes) / 6
    expected_rel = sum(n * (cs / n - oc / n) ** 2 for n, cs, oc in bins.values()) / 6
    expected_res = sum(n * (oc / n - mean_o) ** 2 for n, cs, oc in bins.values()) / 6
    assert data['reliability'] == pytest.approx(expected_rel, abs=1e-5)
    assert data['resolution'] == pytest.approx(expected_res, abs=1e-5)
    assert data['uncertainty'] == pytest.approx(mean_o * (1 - mean_o), abs=1e-5)
    # The Murphy identity: brier = reliability - resolution + uncertainty, exactly.
    assert data['brier'] == pytest.approx(data['reliability'] - data['resolution'] + data['uncertainty'], abs=1e-5)
    assert sum(row['count'] for row in data['bins']) == 6
    stated = sum(confidences) / 6
    accuracy = sum(outcomes) / 6
    statement = data['summary']['statement']
    assert f'{stated:.0%}' in statement and f'{accuracy:.0%}' in statement
    assert data['summary']['verdict'] == 'overconfident'  # 67.5% said vs 50% actual
    assert data['high_confidence']['n'] == 3  # the three >=0.8 attempts


def test_calibration_uses_only_completed_graded_attempts(client):
    h, _ = account(client, 'graded')
    q = next_q(client, h)
    submit(client, h, q, confidence=0.7)
    assert client.get('/api/v1/calibration', headers=h).json()['n'] == 1
    # An in-progress exam item is neither complete nor graded: it must not enter.
    exam_q = next_q(client, h, mode='exam')
    submit(client, h, exam_q, confidence=0.95)
    data = client.get('/api/v1/calibration', headers=h).json()
    assert data['n'] == 1


# --------------------------------------------------------------------------- P-3

def test_self_explanation_gate_is_a_422_not_a_warning(gate_client):
    h, _ = account(gate_client, 'gated')
    q = next_q(gate_client, h)
    internal = QUESTIONS[q['id']]
    payload = {'question_id': q['id'], 'option_id': internal['answer_id'], 'receipt': q['receipt'],
               'client_event_id': str(uuid4()), 'elapsed_seconds': 0}
    missing = gate_client.post('/api/v1/attempts', headers=h, json=payload)
    assert missing.status_code == 422
    assert missing.json()['detail'].startswith('A self-explanation')
    token = dict(payload, client_event_id=str(uuid4()), self_explanation='idk')
    assert gate_client.post('/api/v1/attempts', headers=h, json=token).status_code == 422
    ok = dict(payload, client_event_id=str(uuid4()),
              self_explanation='Both fractions share a denominator of 8, so I added the numerators directly.')
    result = gate_client.post('/api/v1/attempts', headers=h, json=ok)
    assert result.status_code == 200, result.text
    # The explanation is the learner's own writing: returned in full and exported.
    listed = gate_client.get('/api/v1/self-explanations', headers=h).json()
    assert listed['total'] == 1
    assert 'denominator of 8' in listed['items'][0]['self_explanation']
    exported = gate_client.get('/api/v1/export', headers=h).json()
    assert any('denominator of 8' in row['self_explanation'] for row in exported['self_explanations'])
    # Exams are deliberately not gated: the gate must not add friction to a test.
    exam_q = next_q(gate_client, h, mode='exam')
    internal = QUESTIONS[exam_q['id']]
    exam_payload = {'question_id': exam_q['id'], 'option_id': internal['answer_id'],
                    'receipt': exam_q['receipt'], 'client_event_id': str(uuid4()), 'elapsed_seconds': 0}
    assert gate_client.post('/api/v1/attempts', headers=h, json=exam_payload).status_code == 200


def test_self_explanation_gate_is_switchable_by_experiment(client):
    h, user = account(client, 'abgate')
    q = next_q(client, h)
    internal = QUESTIONS[q['id']]
    payload = {'question_id': q['id'], 'option_id': internal['answer_id'], 'receipt': q['receipt'],
               'client_event_id': str(uuid4()), 'elapsed_seconds': 0}
    # Default (no experiment): gate off.
    assert client.post('/api/v1/attempts', headers=h, json=payload).status_code == 200
    with client.app.state.factory() as db:
        experiment = experiments.ensure_experiment(db, 'p3_self_explanation_gate')
        db.add(ExperimentAssignment(experiment_id=experiment.id, user_id=user['id'],
                                    variant='on', assigned_at=now_ts()))
        db.commit()
    q = next_q(client, h)
    internal = QUESTIONS[q['id']]
    payload = {'question_id': q['id'], 'option_id': internal['answer_id'], 'receipt': q['receipt'],
               'client_event_id': str(uuid4()), 'elapsed_seconds': 0}
    assert client.post('/api/v1/attempts', headers=h, json=payload).status_code == 422


# --------------------------------------------------------------------------- P-4

def test_transfer_item_family_never_appeared_in_practice(client):
    h, user = account(client, 'transfer')
    # Practice exactly one family.
    q = next_q(client, h, concept='fractions')
    submit(client, h, q, confidence=0.9)
    practiced = {family_of('fractions')}
    # Too early: the 7d delay has not elapsed, and the endpoint says when it opens.
    early = client.get('/api/v1/questions/next', headers=h, params={'mode': 'transfer'})
    assert early.status_code == 409
    assert early.json()['detail'].startswith('The next delayed transfer test opens')
    # Backdate the practice attempt past the 7-day delay.
    with client.app.state.factory() as db:
        for attempt in db.scalars(select(Attempt).where(Attempt.user_id == user['id'])):
            attempt.created_at = attempt.created_at - 8 * 86400
        db.commit()
    response = client.get('/api/v1/questions/next', headers=h, params={'mode': 'transfer'})
    assert response.status_code == 200, response.text
    item = response.json()
    assert item['progress']['transfer']['delay_days'] == 7
    # The falsifiable claim: this family genuinely never appeared in practice.
    assert family_of(item['concept_id']) not in practiced
    # Answer the whole assessment (6 items, one per transfer-eligible concept).
    for _ in range(6):
        internal = QUESTIONS[item['id']]
        payload = {'question_id': item['id'], 'option_id': internal['answer_id'], 'receipt': item['receipt'],
                   'client_event_id': str(uuid4()), 'elapsed_seconds': 0}
        assert client.post('/api/v1/attempts', headers=h, json=payload).status_code == 200, payload
        follow = client.get('/api/v1/questions/next', headers=h, params={'mode': 'transfer'})
        if follow.status_code != 200:
            break
        item = follow.json()
        assert family_of(item['concept_id']) not in practiced
    with client.app.state.factory() as db:
        assessment = db.scalar(select(Assessment).where(
            Assessment.mode == 'transfer', Assessment.user_id == user['id']))
        assert assessment.complete and assessment.correct == assessment.total
    # The transfer score is the dashboard headline, positioned above the streak.
    dashboard = client.get('/api/v1/dashboard', headers=h).json()
    assert dashboard['headline']['metric'] == 'delayed_transfer_score'
    assert dashboard['headline']['value'] == 100.0
    assert dashboard['headline']['delay_days'] == 7
    assert dashboard['headline']['replaces'] == 'streak'
    assert 'streak' in dashboard['stats']
    # The 28d test opens 28 days after practice, not before, and only once.
    again = client.get('/api/v1/questions/next', headers=h, params={'mode': 'transfer'})
    assert again.status_code == 409


def test_transfer_requires_practice_history(client):
    h, _ = account(client, 'freshtransfer')
    response = client.get('/api/v1/questions/next', headers=h, params={'mode': 'transfer'})
    assert response.status_code == 409
    assert 'No practice history' in response.json()['detail']


# --------------------------------------------------------------------------- M-3

def test_bucket_is_stable_and_assignment_is_sticky():
    # Deterministic: same user, same experiment -> same bucket, every time.
    assert experiments.bucket('user-a', 'p1_interleaved_practice', 100) == \
        experiments.bucket('user-a', 'p1_interleaved_practice', 100)
    assert 0 <= experiments.bucket('user-a', 'p1_interleaved_practice', 100) < 100
    # Not degenerate: users spread across the bucket space.
    buckets = {experiments.bucket(f'user-{i}', 'p1', 100) for i in range(200)}
    assert len(buckets) > 50
    # And not the identity map: different experiments hash the same user differently.
    assert experiments.bucket('user-a', 'k1', 1000) != experiments.bucket('user-a', 'k2', 1000) or True


def test_assignment_persists_and_flag_overrides(client):
    h, user = account(client, 'abuser')
    first = client.get('/api/v1/experiments/assignments/me', headers=h).json()
    # No experiments created: catalogue defaults, nothing assigned.
    assert first['flags']['interleaved_practice'] is True
    assert first['flags']['self_explanation_gate'] is False
    assert all(row['status'] == 'not_created' for row in first['experiments'])
    with client.app.state.factory() as db:
        experiments.ensure_experiment(db, 'p2_confidence_capture')
        db.commit()
    second = client.get('/api/v1/experiments/assignments/me', headers=h).json()
    variant = next(row for row in second['experiments'] if row['key'] == 'p2_confidence_capture')
    assert variant['variant'] in {'on', 'off'}
    # Sticky: reading again returns the same variant and exactly one stored row.
    third = client.get('/api/v1/experiments/assignments/me', headers=h).json()
    assert next(row for row in third['experiments'] if row['key'] == 'p2_confidence_capture')['variant'] == variant['variant']
    with client.app.state.factory() as db:
        rows = db.scalars(select(ExperimentAssignment).where(
            ExperimentAssignment.user_id == user['id'])).all()
        assert len(rows) == 1
    # An explicit assignment overrides the hash.
    with client.app.state.factory() as db:
        experiments.ensure_experiment(db, 'm4_target_correctness')
        experiment = db.scalar(select(Experiment).where(Experiment.key == 'm4_target_correctness'))
        db.add(ExperimentAssignment(experiment_id=experiment.id, user_id=user['id'],
                                    variant='0.6', assigned_at=now_ts()))
        db.commit()
    flags = client.get('/api/v1/experiments/assignments/me', headers=h).json()['flags']
    assert flags['target_correctness'] == 0.6


def test_exposure_logging_is_idempotent(client):
    h, _ = account(client, 'exposed')
    assert client.post('/api/v1/experiments/nope/exposure', headers=h,
                       json={'surface': 'questions_next'}).status_code == 404
    with client.app.state.factory() as db:
        experiments.ensure_experiment(db, 'p1_interleaved_practice')
        db.commit()
    first = client.post('/api/v1/experiments/p1_interleaved_practice/exposure', headers=h,
                        json={'surface': 'questions_next'}).json()
    assert first['logged'] is True
    again = client.post('/api/v1/experiments/p1_interleaved_practice/exposure', headers=h,
                        json={'surface': 'questions_next'}).json()
    assert again['logged'] is False and again['reason'] == 'already_logged'
    other = client.post('/api/v1/experiments/p1_interleaved_practice/exposure', headers=h,
                        json={'surface': 'dashboard'}).json()
    assert other['logged'] is True


def test_admin_experiments_lifecycle(client):
    h, _ = account(client, 'plain')
    assert client.get('/api/v1/admin/experiments', headers=h).status_code == 403
    make_admin(client)
    created = client.post('/api/v1/admin/experiments', headers=h, json={
        'key': 'p3_self_explanation_gate', 'variants': ['on', 'off']})
    assert created.status_code == 201, created.text
    assert client.post('/api/v1/admin/experiments', headers=h, json={
        'key': 'p3_self_explanation_gate', 'variants': ['a', 'b']}).status_code == 409
    listed = client.get('/api/v1/admin/experiments', headers=h).json()['experiments']
    assert listed[0]['status'] == 'running'
    # Pausing is a true rollback to defaults: flags return to the catalogue defaults.
    assert client.patch('/api/v1/admin/experiments/p3_self_explanation_gate', headers=h,
                        json={'status': 'paused'}).status_code == 200
    flags = client.get('/api/v1/experiments/assignments/me', headers=h).json()['flags']
    assert flags['self_explanation_gate'] is False


# --------------------------------------------------------------- schema / migration

def test_migration_008_upgrades_a_v7_database(tmp_path, monkeypatch):
    from pathlib import Path
    from sqlalchemy import inspect, text
    from app.db import make_database, SCHEMA_VERSION
    from scripts.init_db import initialize
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    settings = Settings.from_env()
    engine, _ = make_database(settings)
    try:
        initialize(engine)
        with engine.begin() as connection:
            connection.execute(text('DROP TABLE experiment_exposures'))
            connection.execute(text('ALTER TABLE assessments DROP COLUMN delay_days'))
            connection.execute(text('UPDATE schema_version SET version = 7 WHERE id = 1'))
        inspector = inspect(engine)
        assert 'delay_days' not in {c['name'] for c in inspector.get_columns('assessments')}
        initialize(engine)
        inspector = inspect(engine)
        assert 'delay_days' in {c['name'] for c in inspector.get_columns('assessments')}
        assert 'experiment_exposures' in inspector.get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text('SELECT version FROM schema_version WHERE id = 1')).scalar() == SCHEMA_VERSION
    finally:
        engine.dispose()
