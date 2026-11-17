"""The evidence events the v1.4.0 audit found missing, and the surfaced estimators."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import TelemetryEvent
from test_telemetry import app, _learner  # noqa: F401


def _event(kind, concept_id='fractions', **extra):
    payload = {'concept_id': concept_id, **extra}
    return {'id': f'gap-{kind}-{len(extra)}', 'type': kind,
            'occurred_at': datetime.now(timezone.utc).isoformat(), 'payload': payload}


def test_question_presentation_is_recorded_server_side(app):
    application, client = app
    headers, user_id = _learner(application, client, 'presented@example.com')
    question = client.get('/api/v1/questions/next', headers=headers,
                          params={'mode': 'practice'}).json()
    assert question.get('id')
    with application.state.factory() as db:
        kinds = [row.type for row in db.scalars(select(TelemetryEvent)
                                                .where(TelemetryEvent.user_id == user_id))]
    assert 'question_presented' in kinds


def test_hint_and_explanation_views_are_client_reported_and_validated(app):
    application, client = app
    headers, _ = _learner(application, client, 'views@example.com')
    response = client.post('/api/v1/events', headers=headers, json={'events': [
        _event('hint_viewed', question_id='q1', ladder_move='probe', source='tutor'),
        _event('explanation_viewed', question_id='q1', mode='practice'),
    ]})
    assert response.status_code == 200, response.text
    bad = client.post('/api/v1/events', headers=headers, json={'events': [
        _event('hint_viewed', question_id='q1', ladder_move='eval'),
    ]})
    assert bad.status_code == 422


def test_analytics_surfaces_the_existing_estimators_with_their_scope(app):
    application, client = app
    headers, _ = _learner(application, client, 'insights@example.com')
    dashboard = client.get('/api/v1/dashboard', headers=headers).json()
    assert 'measurement_summary' not in dashboard  # the cheap screen stays cheap
    analytics = client.get('/api/v1/analytics', headers=headers).json()
    summary = analytics['measurement_summary']
    assert 'learning_rate' in summary and 'time_to_criterion' in summary
    assert 'retention' in summary and 'cannot_claim' in summary
    assert 'not a' in summary['scope'].casefold() or 'not' in summary['scope'].casefold()
