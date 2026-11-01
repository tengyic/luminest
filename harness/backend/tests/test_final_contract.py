from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main
from app import courses
from app.curriculum import CONCEPTS, course_concepts
from app.db import Assessment, Message, SCHEMA_VERSION, TelemetryEvent, now_ts
from app.main import create_app
from test_api import account, answer, client, next_q, settings

# The authored mathematics course is the default course. Counts of authored content
# refer to it, not to the merged registry, which now spans every subject.
MATH = course_concepts(courses.DEFAULT_COURSE_ID)


@pytest.mark.parametrize('mode,label', [('diagnostic', 'Curriculum diagnostic'), ('exam', 'Curriculum practice exam')])
def test_final_assessment_completion_and_progress(client, mode, label):
    headers, _ = account(client)
    other_headers, _ = account(client, 'other')
    initial = client.get('/api/v1/dashboard', headers=headers)
    assert initial.status_code == 200
    assert initial.json()['diagnostic_complete'] is False
    for index in range(len(MATH)):
        question = next_q(client, headers, mode, None)
        assert question['progress'] == {'answered': index, 'total': len(MATH)}
        payload = answer(question, correct=(index % 2 == 0))
        response = client.post('/api/v1/attempts', headers=headers, json=payload)
        assert response.status_code == 200, response.text
        value = response.json()
        complete = index == len(MATH) - 1
        assert value['assessment_complete'] is complete
        assert value['assessment_progress'] == {'answered': index + 1, 'total': len(MATH)}
        assert value['assessment_label'] == label
        assert 'not an AP score' in value['scope']
        assert value['exam_complete'] is (mode == 'exam' and complete)
        assert client.post('/api/v1/attempts', headers=headers, json=payload).json() == value
        if mode == 'exam' and not complete:
            assert value['correct'] is None and value['grade'] is None
            assert value['correct_answer'] == 'Withheld until exam completion'
            assert value['explanation'] == 'Withheld until exam completion'
            assert value['diagnosis']['category'] == 'withheld'
            assert value['mastery'] is None and value['review_at'] is None
            assert 'item_breakdown' not in value
            assert client.get('/api/v1/dashboard', headers=headers).status_code == 403
        elif mode == 'diagnostic':
            assert value['grade'] is None
            assert 'item_breakdown' not in value
            assert client.get('/api/v1/dashboard', headers=headers).json()['diagnostic_complete'] is complete
    dashboard = client.get('/api/v1/dashboard', headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()['diagnostic_complete'] is (mode == 'diagnostic')
    assert client.get('/api/v1/dashboard', headers=other_headers).json()['diagnostic_complete'] is False
    if mode == 'diagnostic':
        assert client.get('/api/v1/questions/next', headers=headers, params={'mode': mode}).status_code == 409
        next_q(client, headers, 'exam', None)
        assert client.get('/api/v1/dashboard', headers=headers).status_code == 403
        assert client.post('/api/v1/attempts', headers=headers, json=payload).status_code == 403
    else:
        assert len(value['item_breakdown']) == len(MATH)
        assert value['grade'] == round(100 * sum(index % 2 == 0 for index in range(len(MATH))) / len(MATH), 2)


def test_final_diagnostic_status_uses_completed_assessment(client):
    headers, value = account(client)
    with client.app.state.factory() as db:
        assessment = Assessment(user_id=value['user']['id'], mode='diagnostic', total=len(MATH),
                                answered=len(MATH), complete=False, expires_at=now_ts() - 1)
        db.add(assessment)
        db.commit()
        assessment_id = assessment.id
    dashboard = client.get('/api/v1/dashboard', headers=headers).json()
    assert dashboard['stats']['attempts'] == 0
    assert dashboard['diagnostic_complete'] is False
    with client.app.state.factory() as db:
        db.get(Assessment, assessment_id).complete = True
        db.commit()
    dashboard = client.get('/api/v1/dashboard', headers=headers).json()
    assert dashboard['stats']['attempts'] == 0
    assert dashboard['diagnostic_complete'] is True
    assert not {'correct_answer', 'answer_id', 'item_breakdown'} & set(dashboard)


def test_final_practice_is_not_an_assessment(client):
    headers, _ = account(client)
    question = next_q(client, headers)
    response = client.post('/api/v1/attempts', headers=headers, json=answer(question))
    assert response.status_code == 200
    value = response.json()
    assert value['assessment_complete'] is False
    assert value['assessment_progress'] == {'answered': 0, 'total': 0}
    assert value['exam_complete'] is False and value['grade'] is None
    assert 'assessment_label' not in value
    assert client.get('/api/v1/dashboard', headers=headers).json()['diagnostic_complete'] is False


def test_final_daily_active_minutes_are_utc_day_isolated(tmp_path, monkeypatch):
    # The test moves the server clock backwards to midnight and then a full day forward, so the
    # session issued at the start has to survive both shifts. The shipped access TTL is one hour
    # (refresh rotation carries the long session), so this test explicitly configures a three-day
    # access token: it is about UTC-day accounting, not about session lifetime. The skip guard
    # stays as a loud fallback if that configuration is ever removed.
    from fastapi.testclient import TestClient as _TC
    from app.config import Settings as _Settings
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    monkeypatch.setenv('HARNESS_ACCESS_TOKEN_TTL_SECONDS', '259200')
    settings = _Settings.from_env()
    if settings.access_token_ttl < 2 * 86400:
        pytest.skip(f'{settings.access_token_ttl}s access token cannot span the two-day clock shift '
                    'this accounting test performs')
    with _TC(create_app(settings)) as client:
        headers, value = account(client)
        _, other = account(client, 'other')
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        now = midnight.timestamp() + 2
        monkeypatch.setattr(main, 'now_ts', lambda: now)
        empty = client.get('/api/v1/dashboard', headers=headers).json()['stats']
        assert empty['active_minutes'] == empty['today_active_minutes'] == empty['lifetime_active_minutes'] == 0
        with client.app.state.factory() as db:
            for index, offset in enumerate((-1, 0, 1)):
                received = midnight.timestamp() + offset
                db.add(TelemetryEvent(user_id=value['user']['id'], client_id=f'boundary-{index}', type='heartbeat',
                                      payload={'window_active': True, 'interval_seconds': 15},
                                      occurred_at=(midnight - timedelta(days=1)).isoformat(), received_at=received, active_seconds=15))
            db.add(TelemetryEvent(user_id=other['user']['id'], client_id='other-event', type='heartbeat',
                                  payload={'window_active': True, 'interval_seconds': 15},
                                  occurred_at=midnight.isoformat(), received_at=now, active_seconds=15))
            db.commit()
        dashboard = client.get('/api/v1/dashboard', headers=headers).json()
        stats = dashboard['stats']
        assert stats['active_minutes'] == stats['today_active_minutes'] == 0.5
        assert stats['lifetime_active_minutes'] == 0.75
        assert 'UTC' in dashboard['activity_note'] and 'server receipt' in dashboard['activity_note']
        assert 'does not measure cognitive attention' in dashboard['activity_note']
        analytics = client.get('/api/v1/analytics', headers=headers).json()
        assert [(day['date'], day['active_seconds']) for day in analytics['daily']] == [
            ((midnight - timedelta(days=1)).date().isoformat(), 15), (midnight.date().isoformat(), 30)]
        assert analytics['dimensions'][-1]['value'] is None
        now = (midnight + timedelta(days=1)).timestamp()
        stats = client.get('/api/v1/dashboard', headers=headers).json()['stats']
        assert stats['active_minutes'] == stats['today_active_minutes'] == 0
        assert stats['lifetime_active_minutes'] == 0.75


def test_final_chat_history_preserves_exact_provider_after_restart(settings, monkeypatch):
    original_grounding = [{'title': 'Reply-time reference metadata', 'url': ''}]
    with TestClient(create_app(settings)) as current:
        headers, value = account(current)
        other_headers, _ = account(current, 'other')
        first = current.post('/api/v1/chat', headers=headers, json={'concept_id': 'fractions', 'message': 'Explain fractions.'})
        assert first.status_code == 200
        first_reply = first.json()
        assert first_reply['provider'] == 'Grounded offline tutor'
        monkeypatch.setattr(main.tutor, 'respond', lambda *args, **kwargs: (
            'Which common unit would you choose?', 'openai:model-snapshot-v1', original_grounding, []))
        second = current.post('/api/v1/chat', headers=headers, json={'concept_id': 'fractions', 'message': 'What should I check next?'})
        assert second.status_code == 200
        second_reply = second.json()
        assert second_reply['grounding'] == original_grounding
        assert current.get('/api/v1/chat', headers=other_headers, params={'concept_id': 'fractions'}).json()['messages'] == []
        assert current.get('/api/v1/chat', headers=headers, params={'concept_id': 'equations'}).json()['messages'] == []
        with current.app.state.factory() as db:
            saved = list(db.scalars(select(Message).where(Message.user_id == value['user']['id'], Message.role == 'assistant').order_by(Message.created_at)))
            assert [row.provider for row in saved] == [first_reply['provider'], second_reply['provider']]
    with TestClient(create_app(replace(settings, provider='ollama', provider_model='current-model'))) as restarted:
        response = restarted.get('/api/v1/chat', headers=headers, params={'concept_id': 'fractions'})
        assert response.status_code == 200
        messages = response.json()['messages']
        assert [message['role'] for message in messages] == ['user', 'assistant', 'user', 'assistant']
        assert messages[0]['provider'] is None and messages[2]['provider'] is None
        current_references = [{'title': 'Original hand-authored curriculum: ' + CONCEPTS['fractions']['title'], 'url': ''}]
        current_references.extend({'title': media['title'], 'url': media['url']} for media in CONCEPTS['fractions']['media'])
        for message, original in zip((messages[1], messages[3]), (first_reply, second_reply)):
            for key in ('id', 'content', 'created_at', 'provider'):
                assert message[key] == original[key]
            assert message['grounding'] == current_references
            assert message['source_context'] == 'source_context_current'
            assert 'not persisted historical grounding' in message['source_note']
        assert messages[3]['grounding'] != original_grounding
        assert restarted.get('/api/v1/health').json()['schema_version'] == SCHEMA_VERSION
        assert SCHEMA_VERSION >= 3, 'the harness tables require at least schema v3'


def test_final_invalid_payload_has_field_level_422_details(client):
    headers, _ = account(client)
    response = client.patch('/api/v1/me', headers=headers, json={'daily_minutes': 0})
    assert response.status_code == 422
    assert any(error['loc'] == ['body', 'daily_minutes'] and error['msg'] for error in response.json()['detail'])
    assert client.get('/api/v1/me', headers=headers).json()['daily_minutes'] == 20
