"""The interaction channel: a closed vocabulary, no content, and never evidence.

Three things are being pinned here, and each one is a design decision rather than a
behaviour:

1. **The grammar is closed.** A kind or target outside the lists in
   ``harness.telemetry`` is rejected at the route. That is what stops a client from
   inventing ``kind='scroll'`` and producing a number nobody can interpret later.
2. **No content, ever.** A payload carrying ``window`` (a window title is a document name)
   or ``text`` is refused by name, not silently dropped. ``test_a_window_title_is_refused``
   is the regression guard for the version of this channel that accepted one.
3. **A tap is not an answer.** Posting a hundred clicks moves no mastery, creates no
   ``State`` row and leaves ``/ability`` at zero calibrated items. If that ever stops being
   true, an engagement signal has become a learning claim and the learner record is wrong.

The summary half is tested as a pure function over rows, because its whole job is to count
what is there and to refuse to score it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db import State, TelemetryEvent, User
from app.harness import telemetry
from app.main import create_app


# --------------------------------------------------------------------------- fixtures

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    application = create_app(Settings.from_env())
    with TestClient(application) as client:
        yield application, client


def _learner(application, client, email='tapper@example.com', consent=True):
    registered = client.post('/api/v1/auth/register', json={
        'name': 'Tap probe', 'email': email,
        'password': 'Correct-Horse-9', 'age_confirmed': True}).json()
    headers = {'Authorization': 'Bearer ' + registered['token']}
    if consent:
        client.patch('/api/v1/me', headers=headers, json={'telemetry_consent': True})
    with application.state.factory() as db:
        user = db.query(User).filter(User.email == email).one()
        return headers, user.id


def _tap(kind='click', target='stage.tab.deck', event_id=None, **extra):
    payload = {'kind': kind}
    if target is not None:
        payload['target'] = target
    payload.update(extra)
    return {'id': event_id or f'e-{kind}-{target}-{len(str(payload))}',
            'type': 'interaction',
            'occurred_at': datetime.now(timezone.utc).isoformat(),
            'payload': payload}


# --------------------------------------------------------------------------- the grammar

def test_a_click_with_a_control_id_is_accepted():
    ok, reason = telemetry.validate({'kind': 'click', 'target': 'board.node.cell-theory'})
    assert ok, reason


def test_a_blur_needs_no_target():
    assert telemetry.validate({'kind': 'blur'})[0]
    assert telemetry.validate({'kind': 'focus'})[0]


def test_a_click_without_a_target_is_refused():
    ok, reason = telemetry.validate({'kind': 'click'})
    assert not ok and 'target' in reason


def test_an_unknown_kind_is_refused_by_name():
    ok, reason = telemetry.validate({'kind': 'scroll', 'target': 'board'})
    assert not ok and 'scroll' in reason


def test_a_target_that_is_prose_is_refused():
    """The pattern is what keeps a sentence out of the target field."""
    ok, reason = telemetry.validate({'kind': 'click', 'target': 'the learner opened the deck'})
    assert not ok and 'identifier' in reason
    assert not telemetry.validate({'kind': 'click', 'target': 'x' * 200})[0]


def test_a_window_title_is_refused():
    """A window title is a document name or a URL. The channel has no such field."""
    ok, reason = telemetry.validate({'kind': 'click', 'target': 'board', 'window': 'Budget.xlsx'})
    assert not ok and 'window' in reason
    assert telemetry.describe()['carries_window_titles'] is False


def test_a_text_field_is_refused():
    ok, reason = telemetry.validate({'kind': 'key', 'target': 'question.box', 'text': 'hello'})
    assert not ok and 'text' in reason
    assert telemetry.describe()['carries_free_text'] is False
    assert telemetry.describe()['carries_keystrokes'] is False


def test_a_key_event_names_a_target_and_never_a_key():
    """``key`` records that a key was pressed. There is no field for which one."""
    assert telemetry.validate({'kind': 'key', 'target': 'question.reasoning'})[0]
    assert set(telemetry.FIELDS) == {'kind', 'target'}


def test_a_tap_is_not_evidence():
    assert telemetry.EVIDENCE is False
    assert telemetry.describe()['is_evidence'] is False


# --------------------------------------------------------------------------- the route

def test_the_route_requires_consent(app):
    application, client = app
    headers, _ = _learner(application, client, consent=False)
    response = client.post('/api/v1/events', headers=headers, json={'events': [_tap()]})
    assert response.status_code == 403


def test_the_route_accepts_a_tap_and_replays_it_once(app):
    application, client = app
    headers, _ = _learner(application, client)
    event = _tap()
    assert client.post('/api/v1/events', headers=headers, json={'events': [event]}).json() == {'accepted': 1}
    assert client.post('/api/v1/events', headers=headers, json={'events': [event]}).json() == {'accepted': 0}


def test_the_route_refuses_a_window_title(app):
    application, client = app
    headers, _ = _learner(application, client)
    event = _tap(window='Secret.docx')
    response = client.post('/api/v1/events', headers=headers, json={'events': [event]})
    assert response.status_code == 422
    assert 'window' in response.json()['detail']


def test_a_tap_cannot_move_mastery(app):
    """The whole point of the channel: contact is not comprehension."""
    application, client = app
    headers, user_id = _learner(application, client)
    events = [_tap(target=f'board.node.n{i}', event_id=f'tap-{i}') for i in range(100)]
    assert client.post('/api/v1/events', headers=headers,
                       json={'events': events}).json() == {'accepted': 100}
    with application.state.factory() as db:
        assert list(db.scalars(select(State).where(State.user_id == user_id))) == []
    ability = client.get('/api/v1/ability', headers=headers).json()
    assert ability['n_calibrated'] == 0
    assert ability['level']['known'] is False


def _external_open(concept='fractions', event_id='sim-open-1', **extra):
    payload = {'concept_id': concept}
    payload.update(extra)
    return {'id': event_id, 'type': 'external_simulation_opened',
            'occurred_at': datetime.now(timezone.utc).isoformat(), 'payload': payload}


def test_an_external_simulation_open_is_accepted(app):
    """The one honest fact about a PhET embed: that it was opened.

    This event was emitted by the native app and had a consumer in ``harness/loop.py``, but
    ``schemas.Event.type`` did not list it, so every one of them was rejected by validation
    before the route ran. The producer and the consumer both existed; only the contract did
    not, and nothing noticed because neither side can see the other.
    """
    application, client = app
    headers, _ = _learner(application, client)
    response = client.post('/api/v1/events', headers=headers,
                           json={'events': [_external_open()]})
    assert response.status_code == 200, response.text
    assert response.json() == {'accepted': 1}


def test_an_external_simulation_open_cannot_carry_parameters(app):
    """A PhET iframe reports nothing back, so a parameter would be invented data."""
    application, client = app
    headers, _ = _learner(application, client)
    response = client.post('/api/v1/events', headers=headers,
                           json={'events': [_external_open(value=3)]})
    assert response.status_code == 422


def test_the_summary_counts_and_does_not_score(app):
    application, client = app
    headers, _ = _learner(application, client)
    events = [_tap('click', 'stage.tab.deck', event_id='a'),
              _tap('click', 'stage.tab.deck', event_id='b'),
              _tap('tap', 'board.node.cell-theory', event_id='c'),
              _tap('blur', None, event_id='d')]
    client.post('/api/v1/events', headers=headers, json={'events': events})
    summary = client.get('/api/v1/events/interactions', headers=headers).json()
    assert summary['interactions'] == 4
    assert summary['by_kind'] == {'click': 2, 'tap': 1, 'blur': 1}
    assert summary['top_targets'][0] == {'target': 'stage.tab.deck', 'count': 2}
    assert summary['is_evidence'] is False
    assert 'not an engagement score' in summary['interpretation']
    assert 'score' not in summary


def test_one_learner_never_sees_anothers_taps(app):
    application, client = app
    first, _ = _learner(application, client, email='a@example.com')
    second, _ = _learner(application, client, email='b@example.com')
    client.post('/api/v1/events', headers=first, json={'events': [_tap(event_id='only-a')]})
    assert client.get('/api/v1/events/interactions', headers=second).json()['interactions'] == 0


# --------------------------------------------------------------------------- the summary

class _Row:
    def __init__(self, kind, target=None, occurred_at=None):
        self.type = 'interaction'
        self.payload = {'kind': kind, **({'target': target} if target else {})}
        self.occurred_at = (occurred_at or datetime.now(timezone.utc)).isoformat()


def test_the_summary_skips_kinds_the_vocabulary_does_not_contain():
    rows = [_Row('click', 'a'), _Row('scroll', 'b')]
    payload = telemetry.summarise(rows, now=datetime.now(timezone.utc).timestamp())
    assert payload['interactions'] == 1
    assert payload['by_kind'] == {'click': 1}


def test_the_summary_ignores_rows_outside_the_window():
    now = datetime.now(timezone.utc)
    rows = [_Row('click', 'a', now), _Row('click', 'a', now - timedelta(hours=3))]
    payload = telemetry.summarise(rows, window_seconds=600, now=now.timestamp())
    assert payload['interactions'] == 1


def test_other_event_types_are_not_counted():
    class Heartbeat(_Row):
        def __init__(self):
            super().__init__('click', 'a')
            self.type = 'heartbeat'
            self.payload = {'window_active': True}
    payload = telemetry.summarise([Heartbeat()], now=datetime.now(timezone.utc).timestamp())
    assert payload['interactions'] == 0
