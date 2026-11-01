"""The reward layer: rules in ``motivation``, presentation in ``rewards``, one thin route.

The tests here are in two halves, and the split matters.

*The emitter* is a pure function of data, so it is tested directly: a milestone produces
exactly one event with a stable id, a test item never produces a question strike, and the
heaviest ceremony sorts first. These are the assertions that would catch a celebration
firing for something the backend withheld.

*The route* is tested through the app, because its whole job is to read the caller's own
rows and nothing else. That half exists to prove two things a pure test cannot: that a
learner cannot post their way to a streak, and that one learner never sees another's.

A note on what is deliberately absent: there is no test for a "streak broken" event,
because no such event exists. That is the design, not an omission, and
``test_there_is_no_negative_event_kind`` pins it.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Attempt, Receipt, State, User
from app.harness import rewards
from app.harness.teaching import motivation
from app.main import create_app


# --------------------------------------------------------------------------- fixtures

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    application = create_app(Settings.from_env())
    with TestClient(application) as client:
        yield application, client


def _learner(application, client, email='rewarder@example.com'):
    """Register through the API, then resolve the row the route will read."""
    registered = client.post('/api/v1/auth/register', json={
        'name': 'Reward probe', 'email': email,
        'password': 'Correct-Horse-9', 'age_confirmed': True}).json()
    headers = {'Authorization': 'Bearer ' + registered['token']}
    with application.state.factory() as db:
        user = db.query(User).filter(User.email == email).one()
        return headers, user.id


def _add_attempts(application, user_id, days, *, mode='practice', correct=True):
    """One attempt per day, at noon UTC, so a run of days is unambiguous.

    An ``Attempt`` is not a free-standing row: the teaching loop always writes it behind a
    ``Receipt`` and fills the diagnosis columns, so the fixture does the same rather than
    inventing a shape the route would never see in production.
    """
    with application.state.factory() as db:
        stamps = [datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).replace(
            hour=12).timestamp() for day in days]
        # Receipts first and flushed: there is no ORM relationship to order the inserts, so
        # an attempt added in the same batch would hit the foreign key.
        for offset, stamp in enumerate(stamps):
            db.add(Receipt(id=f'r{user_id[:6]}{offset}', user_id=user_id,
                           question_id=f'q{offset}', mode=mode, issued_at=stamp,
                           expires_at=stamp + 600, used=True))
        db.flush()
        for offset, stamp in enumerate(stamps):
            db.add(Attempt(id=f'a{user_id[:6]}{offset}', user_id=user_id,
                           receipt_id=f'r{user_id[:6]}{offset}', client_event_id=f'e{offset}',
                           question_id=f'q{offset}', concept_id='fractions', mode=mode,
                           correct=correct, elapsed_seconds=12.0, category='correct',
                           payload={}, payload_hash='0' * 64, response={},
                           created_at=stamp))
        db.commit()


def _utc_days(count, *, ending=None):
    """``count`` consecutive UTC days ending today (or ``ending``)."""
    end = ending or datetime.now(timezone.utc).date()
    return [end - timedelta(days=offset) for offset in range(count)][::-1]


# --------------------------------------------------------------------------- the emitter

def test_a_learner_with_no_history_is_not_told_anything():
    assert rewards.events() == []


def test_one_day_counts_quietly():
    today = date(2026, 10, 24)
    found = rewards.events(days=[today], today=today)
    assert [event['kind'] for event in found] == ['streak_notification']
    event = found[0]
    assert event['tier'] == 'toast', 'a single day is a nudge, not a celebration'
    assert event['mascot'] == 'greeting'
    assert event['id'] == 'day:2026-10-24', 'the id must be stable for the client to dedupe'


def test_five_days_is_a_milestone_and_not_also_a_daily_notice():
    today = date(2026, 10, 24)
    days = [today - timedelta(days=offset) for offset in range(5)]
    found = rewards.events(days=days, today=today)
    assert len(found) == 1, 'one fact, one card - two cards for the same day reads as a bug'
    event = found[0]
    assert event['kind'] == 'streak_milestone'
    assert event['value'] == 5
    assert event['tier'] == 'celebrate'
    assert event['sound'] == 'fanfare'
    assert event['id'] == 'streak:2026-10-24:5'
    assert 'five days' in event['announce']


def test_a_run_that_ended_yesterday_is_still_current():
    """The rule lives in `motivation`; this pins that the emitter does not undo it."""
    today = date(2026, 10, 24)
    days = [today - timedelta(days=offset) for offset in range(1, 6)]
    found = rewards.events(days=days, today=today)
    assert found and found[0]['kind'] == 'streak_milestone'


def test_the_same_achievement_always_produces_the_same_id():
    today = date(2026, 10, 24)
    days = [today - timedelta(days=offset) for offset in range(5)]
    first = rewards.events(days=days, today=today)
    second = rewards.events(days=days, today=today)
    assert [event['id'] for event in first] == [event['id'] for event in second]


def test_five_correct_practice_answers_are_a_banner_and_ten_are_a_moment():
    five = rewards.events(quiz_results=[{'context': 'practice', 'correct': True}] * 5)
    ten = rewards.events(quiz_results=[{'context': 'practice', 'correct': True}] * 10)
    assert five[0]['kind'] == 'question_strike' and five[0]['tier'] == 'banner'
    assert ten[0]['tier'] == 'celebrate' and ten[0]['sound'] == 'fanfare'


def test_an_assessment_cannot_earn_a_question_strike():
    """The boundary is `motivation.STREAK_CONTEXTS`, and it must survive the emitter."""
    for context in ('test', 'diagnostic', 'exam', 'transfer'):
        found = rewards.events(quiz_results=[{'context': context, 'correct': True}] * 10)
        assert not [event for event in found if event['kind'] == 'question_strike'], context


def test_a_wrong_answer_ends_the_run():
    results = [{'context': 'practice', 'correct': True}] * 4 + [{'context': 'practice', 'correct': False}]
    found = rewards.events(quiz_results=results)
    assert not [event for event in found if event['kind'] == 'question_strike']


def test_crossing_into_full_mastery_announces_once_not_twice():
    """0.80 then 1.00 would be two cards for one concept that was never between them."""
    found = rewards.events(concepts=[{'concept_id': 'fractions', 'mastery': 1.0}])
    assert len(found) == 1
    assert found[0]['kind'] == 'node_milestone'
    assert found[0]['value'] == 1.0
    assert found[0]['tier'] == 'celebrate'
    assert found[0]['id'] == 'node:fractions:1'


def test_mastery_below_the_first_threshold_says_nothing():
    assert rewards.events(concepts=[{'concept_id': 'fractions', 'mastery': 0.79}]) == []


def test_junk_in_a_concept_row_does_not_raise():
    """These rows are JSON written by another module; a bad value is not a crash."""
    found = rewards.events(concepts=[{'concept_id': '', 'mastery': 0.9},
                                     {'concept_id': 'decimals', 'mastery': 'not a number'}])
    assert found == []


def test_badges_come_from_the_rule_module():
    found = rewards.events(counters={'days_studied': 8, 'longest_streak': 5})
    names = [event['title'] for event in found if event['kind'] == 'badge']
    assert 'Week one' in names and 'Habit' in names


def test_the_heaviest_ceremony_is_shown_first():
    today = date(2026, 10, 24)
    days = [today - timedelta(days=offset) for offset in range(5)]
    found = rewards.events(days=days, concepts=[{'concept_id': 'fractions', 'mastery': 0.85}],
                           counters={'days_studied': 5})
    tiers = [event['tier'] for event in found]
    assert tiers[0] == 'celebrate', f'a 5-day run must not queue behind a badge: {tiers}'
    assert tiers == sorted(tiers, key=lambda tier: rewards.TIER_ORDER[tier])


def test_there_is_no_negative_event_kind():
    """The positive posture, pinned: nothing here can take something away."""
    forbidden = ('broken', 'lost', 'missed', 'penalty', 'failed', 'decay')
    assert not [kind for kind in rewards.PRESENTATION
                if any(word in kind for word in forbidden)]
    assert 'no kind for a broken streak' in rewards.describe()['posture']


def test_every_kind_has_a_complete_presentation():
    for kind, (tier, mascot, sound) in rewards.PRESENTATION.items():
        assert tier in rewards.TIERS, kind
        assert mascot in ('idle', 'blink', 'greeting', 'listening', 'thinking',
                          'celebrating', 'resting'), f'{kind} names a sprite that does not exist'
        assert sound, kind
    assert set(rewards.PRESENTATION) == set(rewards.EMITTED_HERE) | set(rewards.EMITTED_ELSEWHERE)


# --------------------------------------------------------------------------- the route

def test_the_route_requires_a_token(app):
    application, client = app
    assert client.get('/api/v1/rewards/events').status_code == 401


def test_a_new_learner_gets_an_empty_list_rather_than_an_error(app):
    application, client = app
    headers, _user_id = _learner(application, client)
    body = client.get('/api/v1/rewards/events', headers=headers).json()
    assert body['events'] == [] and body['count'] == 0


def test_five_stored_days_produce_the_milestone_through_the_route(app):
    application, client = app
    headers, user_id = _learner(application, client)
    _add_attempts(application, user_id, _utc_days(5))
    body = client.get('/api/v1/rewards/events', headers=headers).json()
    kinds = [event['kind'] for event in body['events']]
    assert 'streak_milestone' in kinds, body
    milestone = next(event for event in body['events'] if event['kind'] == 'streak_milestone')
    assert milestone['value'] == 5


def test_a_review_item_counts_as_practice_but_an_exam_does_not(app):
    """`review` is retrieval practice; `exam` is an assessment and buys no streak."""
    application, client = app
    review_headers, review_user = _learner(application, client, 'review@example.com')
    _add_attempts(application, review_user, _utc_days(1), mode='review')
    review_body = client.get('/api/v1/rewards/events', headers=review_headers).json()
    assert any(event['kind'] == 'streak_notification' for event in review_body['events'])

    exam_headers, exam_user = _learner(application, client, 'exam@example.com')
    _add_attempts(application, exam_user, _utc_days(1), mode='exam')
    with application.state.factory() as db:
        for offset in range(10):
            stamp = 1000.0 + offset
            db.add(Receipt(id=f'xr{offset}', user_id=exam_user, question_id=f'xq{offset}',
                           mode='exam', issued_at=stamp, expires_at=stamp + 600, used=True))
        db.flush()
        for offset in range(10):
            stamp = 1000.0 + offset
            db.add(Attempt(id=f'x{offset}', user_id=exam_user, receipt_id=f'xr{offset}',
                           client_event_id=f'xe{offset}', question_id=f'xq{offset}',
                           concept_id='fractions', mode='exam', correct=True,
                           elapsed_seconds=9.0, category='correct', payload={},
                           payload_hash='0' * 64, response={}, created_at=stamp))
        db.commit()
    exam_body = client.get('/api/v1/rewards/events', headers=exam_headers).json()
    assert not [event for event in exam_body['events'] if event['kind'] == 'question_strike']


def test_one_learner_never_sees_another_learners_events(app):
    application, client = app
    quiet_headers, _quiet = _learner(application, client, 'quiet@example.com')
    busy_headers, busy_user = _learner(application, client, 'busy@example.com')
    _add_attempts(application, busy_user, _utc_days(5))
    with application.state.factory() as db:
        db.add(State(id='s1', user_id=busy_user, concept_id='fractions', data={'mastery': 0.9}))
        db.commit()

    assert client.get('/api/v1/rewards/events', headers=busy_headers).json()['count'] > 0
    assert client.get('/api/v1/rewards/events', headers=quiet_headers).json()['count'] == 0


def test_the_route_cannot_be_talked_into_an_event(app):
    """A body cannot add an achievement: the route reads stored rows and takes no input."""
    application, client = app
    headers, _user_id = _learner(application, client)
    response = client.post('/api/v1/rewards/events', headers=headers,
                           json={'events': [{'kind': 'streak_milestone', 'value': 15}]})
    assert response.status_code == 405, 'the reward surface must stay read-only'
