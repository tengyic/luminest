import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import courses
from app.config import Settings
from app.curriculum import (CONCEPTS, QUESTIONS, course_concepts, course_questions,
                            validate_curriculum)
from app.db import Assessment, Attempt, Message, Project, Receipt, SCHEMA_VERSION, State, TelemetryEvent, Token, User, now_ts
from app.main import create_app

# The authored mathematics course is the default course. Assertions about *authored*
# content count that course, not the merged registry, which now spans every subject.
MATH = course_concepts(courses.DEFAULT_COURSE_ID)
MATH_QUESTIONS = course_questions(courses.DEFAULT_COURSE_ID)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def long_ttl_client(tmp_path, monkeypatch):
    """A client whose access token outlives a deliberate clock shift.

    The shipped default access TTL is one hour (refresh rotation carries the long
    session), so tests that move the server clock past a receipt TTL or across UTC
    days must explicitly configure a longer access token -- otherwise their 410/200
    assertions silently turn into 401s about a rule they are not about.
    """
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    monkeypatch.setenv('HARNESS_ACCESS_TOKEN_TTL_SECONDS', '7200')
    with TestClient(create_app(Settings.from_env())) as client:
        yield client


def account(client, label='one'):
    response = client.post('/api/v1/auth/register', json={'name': label, 'email': f'{label}@example.test', 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    value = response.json()
    return {'Authorization': 'Bearer ' + value['token']}, value


def next_q(client, headers, mode='practice', concept='fractions'):
    params = {'mode': mode}
    if concept is not None:
        params['concept_id'] = concept
    response = client.get('/api/v1/questions/next', headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def answer(q, correct=True, key=None):
    internal = QUESTIONS[q['id']]
    option = internal['answer_id'] if correct else next(o['id'] for o in internal['options'] if o['id'] != internal['answer_id'])
    return {'question_id': q['id'], 'option_id': option, 'receipt': q['receipt'],
            'client_event_id': key or str(uuid4()), 'elapsed_seconds': 0, 'reasoning': 'I checked the common unit.', 'confidence': 0.8}


def test_auth_session_and_profile(client):
    h, registered = account(client)
    # Registration returns a session, not just a token: the refresh token is what lets a hosted
    # deployment keep the access token short, so the envelope is part of the contract.
    assert set(registered) == {'token', 'refresh_token', 'token_type', 'expires_in', 'user'}
    assert registered['token_type'] == 'Bearer'
    assert registered['expires_in'] > 0 and registered['refresh_token'] != registered['token']
    # The full public profile, pinned. `referral_code` is absent on purpose: the column exists for a
    # feature that was never built, so it could only ever be null.
    assert set(registered['user']) == {'id', 'name', 'email', 'goal', 'daily_minutes', 'telemetry_consent',
                                       'training_consent', 'course_id', 'onboarding_complete', 'email_verified',
                                       'role', 'status', 'cohort_id'}
    # A brand-new account has not chosen a course or a goal yet, so the client must be told to
    # run onboarding. Without this flag the native app would drop the learner straight into a
    # plan for a course they never picked.
    assert registered['user']['onboarding_complete'] is False
    # Role and status are gates, not decoration: the admin surface checks the role, and every
    # authenticated request checks the status, so a default that drifted would either expose admin
    # routes or lock every learner out.
    assert registered['user']['role'] == 'learner'
    assert registered['user']['status'] == 'active'
    assert registered['user']['email_verified'] is False
    assert registered['user']['cohort_id'] is None
    assert not registered['user']['telemetry_consent']
    assert client.get('/api/v1/me').status_code == 401
    assert client.post('/api/v1/auth/login', json={'email': 'one@example.test', 'password': 'incorrect-password'}).status_code == 401
    login = client.post('/api/v1/auth/login', json={'email': 'ONE@EXAMPLE.TEST', 'password': 'long-secret-password'})
    assert login.status_code == 200
    update = client.patch('/api/v1/me', headers=h, json={'goal': 'Understand equations', 'daily_minutes': 35, 'telemetry_consent': True})
    assert update.json()['daily_minutes'] == 35
    assert client.patch('/api/v1/me', headers=h, json={'daily_minutes': 0}).status_code == 422
    assert client.patch('/api/v1/me', headers=h, json={'goal': None}).status_code == 422
    with client.app.state.factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith('$argon2id$')
        assert registered['token'] not in {t.digest for t in db.scalars(select(Token).where(Token.user_id == user.id))}
    assert client.post('/api/v1/auth/logout', headers=h).status_code == 204
    assert client.get('/api/v1/me', headers=h).status_code == 401


def test_expired_token(client):
    h, value = account(client)
    with client.app.state.factory() as db:
        for token in db.scalars(select(Token).where(Token.user_id == value['user']['id'])):
            token.expires_at = now_ts()-1
        db.commit()
    assert client.get('/api/v1/me', headers=h).status_code == 401


def test_receipts_hiding_idempotence_and_variants(client):
    h, _ = account(client)
    q = next_q(client, h)
    assert not {'answer', 'answer_id', 'answer_text', 'correct_answer', 'explanation'} & set(q)
    assert set(q) == {'id', 'concept_id', 'concept_title', 'prompt', 'options', 'kind', 'mode', 'issued_at', 'receipt', 'progress', 'expected_seconds', 'selection_reason'}
    assert next_q(client, h)['receipt'] == q['receipt']
    payload = answer(q)
    result = client.post('/api/v1/attempts', headers=h, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()['correct'] and result.json()['grade'] is None
    assert 'Tentative' in result.json()['diagnosis']['reason']
    assert client.post('/api/v1/attempts', headers=h, json=payload).json() == result.json()
    assert client.post('/api/v1/attempts', headers=h, json={**payload, 'reasoning': 'different'}).status_code == 409
    assert client.post('/api/v1/attempts', headers=h, json={**payload, 'client_event_id': str(uuid4())}).status_code == 409
    assert next_q(client, h)['id'] != q['id']
    assert client.get('/api/v1/dashboard', headers=h).json()['stats']['attempts'] == 1


def test_cross_user_isolation(client):
    h1, u1 = account(client, 'first')
    h2, u2 = account(client, 'second')
    q = next_q(client, h1)
    assert client.post('/api/v1/attempts', headers=h2, json=answer(q)).status_code == 400
    projects = client.get('/api/v1/projects', headers=h1).json()['items']
    payload = {'text': 'Two servings require 1/2 cup, five require 5/4 cup. I verify the ratio.', 'ai_disclosure': 'No AI used.', 'reflection': 'I checked the unit rate.'}
    assert client.post(f'/api/v1/projects/{projects[0]["id"]}/submit', headers=h2, json=payload).status_code == 404
    chat = client.post('/api/v1/chat', headers=h1, json={'concept_id': 'fractions', 'message': 'How do I add fractions?', 'session_id': 'shared'})
    assert chat.status_code == 200 and chat.json()['provider'] == 'Grounded offline tutor'
    assert client.get('/api/v1/chat', headers=h2, params={'concept_id': 'fractions'}).json()['messages'] == []
    client.post('/api/v1/attempts', headers=h1, json=answer(q))
    assert client.get('/api/v1/dashboard', headers=h2).json()['stats']['attempts'] == 0
    export = client.get('/api/v1/export', headers=h2).json()
    assert u1['user']['id'] not in json.dumps(export)
    assert not export['attempts'] and not export['messages']


@pytest.mark.parametrize('change,code', [({'receipt': 'invalid.receipt.signature'}, 400), ({'question_id': 'equations-1'}, 400), ({'option_id': 'z'}, 422), ({'elapsed_seconds': 500}, 422), ({'mode': 'exam'}, 422), ({'confidence': 2}, 422)])
def test_invalid_attempt(client, change, code):
    h, _ = account(client)
    q = next_q(client, h)
    assert client.post('/api/v1/attempts', headers=h, json={**answer(q), **change}).status_code == code
    assert client.get('/api/v1/dashboard', headers=h).json()['stats']['attempts'] == 0


def test_expired_receipt(long_ttl_client, monkeypatch):
    h, _ = account(long_ttl_client)
    q = next_q(long_ttl_client, h)
    # This test is about the receipt's own deadline, not about session expiry, so the clock shift
    # has to clear the receipt TTL while staying inside the access token lifetime. The access TTL
    # here is configured to 7200s by the fixture for exactly that reason; the skip guard stays so
    # a future default change still reports itself instead of turning this into a 401 test.
    import app.main as main
    receipt_ttl = Settings.from_env().receipt_ttl  # 3600 unless an operator changed it
    shift = receipt_ttl + 60
    if shift >= 7200:
        pytest.skip(f'receipt TTL {receipt_ttl}s leaves no room inside the '
                    f'7200s access token to observe receipt expiry alone')
    original = main.now_ts
    main.now_ts = lambda: original() + shift
    try:
        assert long_ttl_client.post('/api/v1/attempts', headers=h, json=answer(q)).status_code == 410
    finally:
        main.now_ts = original


def test_diagnostic_and_exam(client):
    h, _ = account(client)
    covered = set()
    for i in range(len(MATH)):
        q = next_q(client, h, 'diagnostic', None)
        assert q['progress'] == {'answered': i, 'total': len(MATH)}
        assert q['concept_id'] not in covered
        covered.add(q['concept_id'])
        result = client.post('/api/v1/attempts', headers=h, json=answer(q, correct=(i % 2 == 0)))
        assert result.status_code == 200, result.text
        assert result.json()['grade'] is None
    assert client.get('/api/v1/questions/next', headers=h, params={'mode': 'diagnostic'}).status_code == 409
    q = next_q(client, h, 'exam', None)
    for path in ('/api/v1/lessons/fractions', '/api/v1/projects', '/api/v1/chat?concept_id=fractions'):
        assert client.get(path, headers=h).status_code == 403
    assert client.post('/api/v1/chat', headers=h, json={'concept_id': 'fractions', 'message': 'help'}).status_code == 403
    assert client.get('/api/v1/questions/next', headers=h).status_code == 403
    for i in range(len(MATH)):
        if i:
            q = next_q(client, h, 'exam', None)
        result = client.post('/api/v1/attempts', headers=h, json=answer(q))
        assert result.status_code == 200, result.text
        assert result.json()['exam_complete'] is (i == len(MATH)-1)
        if i < len(MATH)-1:
            value = result.json()
            assert value['correct'] is None
            assert value['correct_answer'] == 'Withheld until exam completion'
            assert value['explanation'] == 'Withheld until exam completion'
            assert value['mastery'] is None and value['review_at'] is None
            assert 'item_breakdown' not in value
    assert result.json()['grade'] == 100
    assert len(result.json()['item_breakdown']) == len(MATH)
    assert all(item['correct'] for item in result.json()['item_breakdown'])
    assert client.get('/api/v1/lessons/fractions', headers=h).status_code == 200


def test_reviews_and_analytics(client):
    h, value = account(client)
    assert client.get('/api/v1/reviews', headers=h).json() == {'items': [], 'total': 0}
    assert client.get('/api/v1/questions/next', headers=h, params={'mode': 'review'}).status_code == 404
    q = next_q(client, h)
    result = client.post('/api/v1/attempts', headers=h, json=answer(q, False)).json()
    with client.app.state.factory() as db:
        state = db.scalar(select(State).where(State.user_id == value['user']['id']))
        state.data = {**state.data, 'due_at': now_ts()-10}
        db.commit()
    reviews = client.get('/api/v1/reviews', headers=h).json()
    assert reviews['total'] == 1 and reviews['items'][0]['recall'] is not None
    assert next_q(client, h, 'review')['concept_id'] == 'fractions'
    analytics = client.get('/api/v1/analytics', headers=h).json()
    assert analytics['daily'][0]['attempts'] == 1 and analytics['errors'][0]['count'] == 1
    assert analytics['streak'] == 1
    assert analytics['dimensions'][-1]['value'] is None


def heartbeat(event_id, active=True, interval=15):
    return {'id': event_id, 'type': 'heartbeat', 'occurred_at': datetime.now(timezone.utc).isoformat(),
            'payload': {'window_active': active, 'interval_seconds': interval}}


def test_consent_heartbeat_bounds_and_replays(client):
    h, _ = account(client)
    event = heartbeat('first')
    assert client.post('/api/v1/events', headers=h, json={'events': [event]}).status_code == 403
    client.patch('/api/v1/me', headers=h, json={'telemetry_consent': True})
    assert client.post('/api/v1/events', headers=h, json={'events': [event]}).json() == {'accepted': 1}
    assert client.post('/api/v1/events', headers=h, json={'events': [event]}).json() == {'accepted': 0}
    with client.app.state.factory() as db:
        user = db.scalar(select(User))
        user.last_heartbeat = now_ts()-10
        db.commit()
    assert client.post('/api/v1/events', headers=h, json={'events': [heartbeat('second')]}).status_code == 200
    seconds = sum(d['active_seconds'] for d in client.get('/api/v1/analytics', headers=h).json()['daily'])
    assert 9 <= seconds <= 15
    batch = [heartbeat(f'batch-{i}') for i in range(100)]
    assert client.post('/api/v1/events', headers=h, json={'events': batch}).status_code == 200
    after = sum(d['active_seconds'] for d in client.get('/api/v1/analytics', headers=h).json()['daily'])
    assert after-seconds < 2
    assert client.post('/api/v1/events', headers=h, json={'events': [heartbeat('invalid', interval=16)]}).status_code == 422
    assert client.post('/api/v1/events', headers=h, json={'events': [heartbeat('inactive', False)]}).status_code == 200
    client.patch('/api/v1/me', headers=h, json={'telemetry_consent': False})
    assert client.post('/api/v1/events', headers=h, json={'events': [heartbeat('denied')]}).status_code == 403


def test_project_formative_export_and_deletion(client):
    h1, deleted = account(client, 'delete')
    h2, _ = account(client, 'retain')
    deleted_id = deleted['user']['id']
    q = next_q(client, h1)
    client.post('/api/v1/attempts', headers=h1, json=answer(q))
    project = client.get('/api/v1/projects', headers=h1).json()['items'][0]
    result = client.post(f'/api/v1/projects/{project["id"]}/submit', headers=h1, json={
        'text': 'I scale 1/2 cup by 5/2 and verify 5/4 cup.', 'ai_disclosure': 'Offline tutor used.', 'reflection': 'I checked the serving ratio.'})
    assert result.status_code == 200 and 'no certified grade' in result.json()['feedback']
    exported = client.get('/api/v1/export', headers=h1).json()
    assert len(exported['attempts']) == 1 and exported['projects'][0]['ai_disclosure']
    assert 'password_hash' not in exported['user']
    assert all('digest' not in session for session in exported['sessions'])
    assert client.request('DELETE', '/api/v1/me', headers=h1, json={'confirmation': 'DELETE'}).status_code == 422
    assert client.request('DELETE', '/api/v1/me', headers=h1, json={'confirmation': 'DELETE MY ACCOUNT'}).status_code == 204
    assert client.get('/api/v1/me', headers=h1).status_code == 401
    assert client.get('/api/v1/me', headers=h2).status_code == 200
    with client.app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        # Scoped to the deleted learner: the guard requires a user_id predicate on
        # user-owned tables, and "the *deleted* user's rows are gone" is the actual claim.
        for cls in (Attempt, Receipt, Assessment, State, Project, TelemetryEvent, Message):
            assert db.scalars(select(cls).where(cls.user_id == deleted_id)).all() == []


def test_persistence_restart(settings):
    with TestClient(create_app(settings)) as c:
        h, _ = account(c)
        q = next_q(c, h)
        payload = answer(q)
        original = c.post('/api/v1/attempts', headers=h, json=payload).json()
        pending = next_q(c, h)
    with TestClient(create_app(settings)) as c:
        assert c.get('/api/v1/me', headers=h).status_code == 200
        assert c.post('/api/v1/attempts', headers=h, json=payload).json() == original
        assert next_q(c, h)['receipt'] == pending['receipt']
        assert c.get('/api/v1/dashboard', headers=h).json()['stats']['attempts'] == 1


def test_provider_failure_falls_back_to_the_curriculum(settings, monkeypatch):
    """A dead provider must not end the turn as an empty bubble.

    Measured against a real DeepSeek key out of credit: the provider answers HTTP 402, the
    turn used to raise 503, and the app drew nothing at all — the learner typed, pressed
    send, and got no reply and no reason. The curriculum is still on this machine, so the
    turn now answers from it and says so. The two things that must not happen are a claim
    that a model wrote it, and a silent substitution.
    """
    settings = replace(settings, provider='openai', provider_url='http://127.0.0.1:9999/v1', provider_model='test')
    def fail(*args, **kwargs):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx.Client, 'post', fail)
    with TestClient(create_app(settings)) as c:
        # Avoid patched TestClient.post by using request.
        registered = c.request('POST', '/api/v1/auth/register', json={'name': 'provider', 'email': 'provider@example.test', 'password': 'long-secret-password'}).json()
        h = {'Authorization': 'Bearer ' + registered['token']}
        result = c.request('POST', '/api/v1/chat', headers=h, json={'concept_id': 'equations', 'message': 'Explain an equation.'})
        assert result.status_code == 200
        body = result.json()
        assert 'unavailable' in body['content']
        assert 'curriculum instead of a model' in body['content']
        assert 'offline' in body['provider'].lower(), body['provider']
        # The turn is saved, so the next render of the transcript shows it.
        messages = c.get('/api/v1/chat', headers=h, params={'concept_id': 'equations'}).json()['messages']
        assert [m['role'] for m in messages] == ['user', 'assistant']
        assert 'unavailable' in messages[-1]['content']


def test_dag_questions_health(client):
    assert validate_curriculum()
    # Floor: the default course must expose a practisable amount of authored math.
    # The upper bound is only a runaway guard — authored coverage GROWS with the
    # curriculum (15 lessons when this pin was written, 30 now), so it is set wide.
    assert 12 <= len(MATH) <= 96
    assert len(MATH_QUESTIONS) == len(MATH)*4
    # Every other course is materialised into the same two registries, so the merged set
    # is strictly larger and every declared course exposes content a learner can practise.
    assert len(CONCEPTS) > len(MATH)
    assert len(QUESTIONS) == len(CONCEPTS)*4
    for spec in courses.COURSES:
        assert course_concepts(spec.id), f'{spec.id} exposes no concepts'
        assert course_questions(spec.id), f'{spec.id} exposes no questions'
    for q in QUESTIONS.values():
        assert len({o['text'] for o in q['options']}) == 4
        assert q['answer_id'] in {o['id'] for o in q['options']}
    assert client.get('/api/v1/health').json()['ready']
    h, _ = account(client)
    curriculum = client.get('/api/v1/curriculum', headers=h).json()
    # The learner's curriculum mirrors the default course's practisable concepts
    # (was pinned to the literal 15 when the course had 15 authored lessons).
    assert len(curriculum['concepts']) == len(MATH)
    assert all(c['due_at'] is None for c in curriculum['concepts'])
    # `/` serves the web workbench since the web_routes router was mounted (it was 404 before
    # that router existed, which is what this assertion used to pin). The workbench is the
    # product surface, so the contract is now: 200 + the workbench HTML, and it must still be
    # the workbench (not an error page) once the app is fully wired.
    root = client.get('/')
    assert root.status_code == 200
    assert 'text/html' in root.headers.get('content-type', '')


def test_concurrent_idempotence(client):
    h, _ = account(client)
    payload = answer(next_q(client, h))
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post('/api/v1/attempts', headers=h, json=payload), range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()['id'] for r in responses}) == 1


def test_production_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setenv('HARNESS_ENV', 'production')
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    with pytest.raises(ValueError, match='PostgreSQL'):
        Settings.from_env()
    monkeypatch.setenv('HARNESS_DATABASE_URL', 'postgresql://user:password@db/harness')
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    with pytest.raises(ValueError, match='strong'):
        Settings.from_env()


def test_contract_and_invalid_event_boundaries(client):
    h, _ = account(client)
    dashboard = client.get('/api/v1/dashboard', headers=h).json()
    assert set(dashboard) == {'user', 'stats', 'recommendation', 'recent', 'dimensions', 'model_status', 'diagnostic_complete', 'activity_note', 'headline', 'transfer'}
    assert set(dashboard['headline']) == {'metric', 'value', 'unit', 'delay_days', 'assessed_at', 'replaces', 'note'}
    assert dashboard['headline']['metric'] == 'delayed_transfer_score'
    assert set(dashboard['stats']) == {'active_minutes', 'today_active_minutes', 'lifetime_active_minutes', 'day_boundary', 'accuracy', 'attempts', 'mastered', 'due', 'streak'}
    lesson = client.get('/api/v1/lessons/equations', headers=h).json()
    # `course_id` is pinned because it was missing. The lesson payload used to be built
    # from a whitelist of registry keys, and the whitelist did not include the course
    # the concept belongs to - so a lesson served from a course the learner built
    # themselves arrived unattributable, with no way for a client to tell which course
    # it came from. `generated` is in the registry rather than the payload, so a
    # learner-built lesson reports it through the same field an authored one would.
    assert set(lesson) == {'id', 'title', 'unit', 'strand', 'topic', 'tier', 'difficulty', 'blocks',
                           'simulation', 'project', 'media', 'hint', 'prerequisites', 'summary',
                           'course_id'}
    assert lesson['course_id'] == courses.DEFAULT_COURSE_ID
    q = next_q(client, h)
    payload = answer(q)
    payload['receipt'] = q['receipt'][:-1] + ('0' if q['receipt'][-1] != '0' else '1')
    assert client.post('/api/v1/attempts', headers=h, json=payload).status_code == 400
    client.patch('/api/v1/me', headers=h, json={'telemetry_consent': True})
    stale = heartbeat('stale')
    stale['occurred_at'] = datetime.fromtimestamp(now_ts()-120, timezone.utc).isoformat()
    assert client.post('/api/v1/events', headers=h, json={'events': [stale]}).status_code == 422
    sensitive = heartbeat('sensitive')
    sensitive['payload']['keyboard_log'] = 'must not be accepted'
    assert client.post('/api/v1/events', headers=h, json={'events': [sensitive]}).status_code == 422
    assert client.get('/api/v1/questions/next', headers=h, params={'mode': 'exam', 'concept_id': 'fractions'}).status_code == 422


def test_password_whitespace_preserved(client):
    details = {'name': ' spaced ', 'email': ' spaced@example.test ', 'password': ' long-secret-password '}
    assert client.post('/api/v1/auth/register', json=details).status_code == 201
    assert client.post('/api/v1/auth/login', json={'email': 'spaced@example.test', 'password': 'long-secret-password'}).status_code == 401
    assert client.post('/api/v1/auth/login', json={'email': 'spaced@example.test', 'password': details['password']}).status_code == 200


def test_persisted_rate_limit(client):
    from app.security import rate_limit
    for _ in range(2):
        rate_limit(client.app.state.factory, 'testing-limit', 2, 60)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        rate_limit(client.app.state.factory, 'testing-limit', 2, 60)
    assert exc.value.status_code == 429


def test_option_specific_tentative_diagnosis_and_targeted_variant(client):
    h, value = account(client)
    q = next_q(client, h, concept='expressions')
    internal = QUESTIONS[q['id']]
    choices = internal['distractor_diagnoses']
    chosen = next(option for option, d in choices.items() if d['category'] == 'conceptual')
    result = client.post('/api/v1/attempts', headers=h, json={**answer(q), 'option_id': chosen, 'confidence': 0.9}).json()
    diagnosis = result['diagnosis']
    assert diagnosis['category'] == 'conceptual'
    assert diagnosis['response_confidence'] == 0.9
    assert 'Tentative' in diagnosis['reason'] and 'does not prove' in diagnosis['reason']
    assert diagnosis['alternatives'] and diagnosis['next_action']
    with client.app.state.factory() as db:
        state = db.scalar(select(State).where(State.user_id == value['user']['id']))
        assert state.data['next_check']['question_id'] == q['id']
    fresh = next_q(client, h, concept='expressions')
    assert fresh['id'] != q['id'] and 'conceptual' in fresh['selection_reason']


def test_exam_no_leak_from_history_export_or_state(client):
    h, _ = account(client)
    practice = next_q(client, h)
    payload = answer(practice)
    client.post('/api/v1/attempts', headers=h, json=payload)
    q = next_q(client, h, 'exam', None)
    submitted = answer(q, False)
    result = client.post('/api/v1/attempts', headers=h, json=submitted).json()
    assert result['correct'] is None and result['grade'] is None
    assert result['diagnosis']['category'] == 'withheld'
    assert client.post('/api/v1/attempts', headers=h, json=submitted).json() == result
    for endpoint in ('dashboard', 'analytics', 'curriculum', 'reviews', 'export'):
        assert client.get('/api/v1/' + endpoint, headers=h).status_code == 403
    assert client.post('/api/v1/attempts', headers=h, json=payload).status_code == 403
    assert client.post('/api/v1/assessments/exam/end', headers=h, json={'abandoned': False}).status_code == 422
    ended = client.post('/api/v1/assessments/exam/end', headers=h, json={'abandoned': True})
    assert ended.status_code == 200
    assert ended.json()['abandoned'] and ended.json()['grade'] is None
    assert len(ended.json()['item_breakdown']) == 1
    assert not ended.json()['item_breakdown'][0]['correct']
    assert client.get('/api/v1/lessons/fractions', headers=h).status_code == 200
    assert client.get('/api/v1/assessments/exam/end', headers=h).status_code == 405


def test_training_consent_ledger_and_minimized_export(client, tmp_path):
    from app.training import export_training, verify_export
    h, value = account(client)
    h2, _ = account(client, 'not-consented')
    assert value['user']['training_consent'] is False
    client.patch('/api/v1/me', headers=h, json={'telemetry_consent': True})
    assert not client.get('/api/v1/training/status', headers=h).json()['training_consent']
    client.post('/api/v1/attempts', headers=h, json=answer(next_q(client, h)))
    assert client.post('/api/v1/training/consent', headers=h, json={'enabled': 'true'}).status_code == 422
    status = client.post('/api/v1/training/consent', headers=h, json={'enabled': True}).json()
    assert status['consented_samples'] == 0 and not status['automatic_promotion']
    client.post('/api/v1/attempts', headers=h, json=answer(next_q(client, h)))
    client.post('/api/v1/attempts', headers=h2, json=answer(next_q(client, h2)))
    status = client.get('/api/v1/training/status', headers=h).json()
    assert status['consented_samples'] == 1 and status['qualified_samples'] == 0
    with client.app.state.factory() as db:
        data, manifest = export_training(db, client.app.state.signing_secret, tmp_path)
        verified = verify_export(db, client.app.state.signing_secret, data, manifest)
        assert verified['domain'] == 'math' and len(verified['opt_in_student_ids']) == 1
        assert value['user']['id'] not in data.read_text() + manifest.read_text()
        assert 'email' not in data.read_text() and 'reasoning' not in data.read_text()
        from app.adaptation import _runtime_module
        import importlib
        _runtime_module()
        trainer = importlib.import_module('harness_owned_model.train')
        frame, metadata = trainer.load_opt_in(data, manifest, 1500)
        assert len(frame) == 1 and metadata['ownership_verified']
    client.patch('/api/v1/me', headers=h, json={'training_consent': False})
    assert client.get('/api/v1/training/status', headers=h).json()['consented_samples'] == 0
    with client.app.state.factory() as db:
        with pytest.raises(ValueError, match='revoked'):
            verify_export(db, client.app.state.signing_secret, data, manifest)
    client.post('/api/v1/training/consent', headers=h, json={'enabled': True})
    assert client.get('/api/v1/training/status', headers=h).json()['consented_samples'] == 0
    forged = json.loads(manifest.read_text())
    forged['consent_verified'] = False
    manifest.write_text(json.dumps(forged))
    with client.app.state.factory() as db:
        with pytest.raises(ValueError, match='signature'):
            verify_export(db, client.app.state.signing_secret, data, manifest)


def test_all_simulation_parameters_and_integer_trials(client):
    h, _ = account(client)
    client.patch('/api/v1/me', headers=h, json={'telemetry_consent': True})
    def event(cid, pid, value):
        return {'id': str(uuid4()), 'type': 'simulation_interaction', 'occurred_at': datetime.now(timezone.utc).isoformat(),
                'payload': {'concept_id': cid, 'parameter': pid, 'value': value}}
    # Authored lessons carry eight teaching blocks and tunable simulation parameters.
    # Generated lessons carry four and a concept map, which has no parameters - so this
    # walks the authored mathematics course, and separately asserts the generated shape.
    for cid, concept in MATH.items():
        assert len(concept['blocks']) == 8
        for p in concept['simulation']['parameters']:
            assert p['min'] <= p['value'] <= p['max']
            assert client.post('/api/v1/events', headers=h, json={'events': [event(cid, p['id'], p['value'])]}).status_code == 200
    for cid, concept in CONCEPTS.items():
        if cid in MATH:
            continue
        assert len(concept['blocks']) == 4
        assert concept['generated'] is True
        assert concept['simulation']['kind'] == 'concept_map'
        assert concept['simulation']['parameters'] == []
    assert client.post('/api/v1/events', headers=h, json={'events': [event('probability', 'n', 2.5)]}).status_code == 422
    assert client.post('/api/v1/events', headers=h, json={'events': [event('probability', 'p', 1.1)]}).status_code == 422


def test_empirical_calibration_uses_authoritative_actual_attempts(client):
    from app.main import calibration_for
    h, _ = account(client)
    q = next_q(client, h)
    client.post('/api/v1/attempts', headers=h, json=answer(q, False))
    with client.app.state.factory() as db:
        calibration = calibration_for(db)
        assert calibration[q['id']]['count'] == 1
        assert calibration[q['id']]['successes'] == 0
    dashboard = client.get('/api/v1/dashboard', headers=h).json()
    assert 'target=0.70' in dashboard['recommendation']['reason']
    assert 'low_data' in dashboard['recommendation']['reason']


def test_exam_default_abandon_body(client):
    h, _ = account(client)
    next_q(client, h, 'exam', None)
    result = client.post('/api/v1/assessments/exam/end', headers=h)
    assert result.status_code == 200 and result.json()['abandoned']


def test_explicit_schema_migration_preserves_existing_users(settings):
    from sqlalchemy import inspect, text
    from app.db import make_database, SchemaVersion
    from scripts.init_db import initialize
    engine, factory = make_database(settings)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, name VARCHAR(100) NOT NULL, email VARCHAR(254) UNIQUE NOT NULL, password_hash TEXT NOT NULL, goal VARCHAR(500) NOT NULL, daily_minutes INTEGER NOT NULL, telemetry_consent BOOLEAN NOT NULL, created_at FLOAT NOT NULL, last_heartbeat FLOAT)'))
        connection.execute(text("INSERT INTO users VALUES ('old', 'Existing', 'old@example.test', 'old-hash', 'Learn', 20, FALSE, 1, NULL)"))
    with pytest.raises(RuntimeError, match='Schema upgrade required'):
        with TestClient(create_app(settings)):
            pass
    assert 'training_consent' not in {c['name'] for c in inspect(engine).get_columns('users')}
    initialize(engine)
    initialize(engine)
    with factory() as db:
        assert db.get(User, 'old').training_consent is False
        assert db.get(SchemaVersion, 1).version == SCHEMA_VERSION
    engine.dispose()


def test_generated_simulation_covers_every_course_concept(client):
    """Every node in the course graph must serve a figure, not just the authored few."""
    h, _ = account(client)
    graph = client.get('/api/v1/knowledge-graph', headers=h).json()
    assert len(graph['nodes']) >= 160
    assert all(node['simulation_kind'] for node in graph['nodes'])
    for node in graph['nodes']:
        response = client.get(f"/api/v1/simulations/{node['id']}", headers=h)
        assert response.status_code == 200, (node['id'], response.text)
        payload = response.json()
        assert payload['steps'] and payload['readouts'], node['id']
        assert payload['concept']['id'] == node['id']


def test_generated_simulation_accepts_lesson_ids_and_overrides(client):
    h, _ = account(client)
    # A lesson id resolves to the node that lesson teaches.
    lesson = client.get('/api/v1/simulations/fractions', headers=h)
    assert lesson.status_code == 200
    assert lesson.json()['concept']['lesson_id'] == 'fractions'

    path = '/api/v1/simulations/quadratic_expressions_and_their_graphs'
    base = client.get(path, headers=h).json()
    moved = client.get(path, headers=h, params={'b': 5, 'c': -6}).json()
    assert base['expression']['substituted'] != moved['expression']['substituted']
    assert moved['expression']['substituted'] == 'x^2 + 5x \u2212 6'
    assert sorted(moved['features']['roots']) == [-6.0, 1.0]

    # Out-of-range values are clamped to the declared slider bounds, not rejected.
    clamped = client.get(path, headers=h, params={'b': 9999}).json()
    assert clamped['overrides']['b'] == 8
    # Unknown query keys are ignored rather than treated as parameters.
    ignored = client.get(path, headers=h, params={'nonsense': 1}).json()
    assert 'nonsense' not in ignored['overrides']

    assert client.get(path, headers=h, params={'b': 'abc'}).status_code == 422
    assert client.get('/api/v1/simulations/not_a_concept', headers=h).status_code == 404
    assert client.get('/api/v1/simulations/fractions').status_code == 401


def test_scene_figure_is_not_drawn_as_a_curve(client):
    """A fraction bar is a part-whole model, so it must not ship a sampled series."""
    h, _ = account(client)
    payload = client.get('/api/v1/simulations/fraction_equivalence', headers=h).json()
    assert payload['figure'] == 'scene'
    assert payload['series'] == [] and payload['table'] == []
    assert len(payload['parts']) == 3
