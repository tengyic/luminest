"""The classroom decision engine: every branch, deterministically.

Pure-function tests (no provider, no network, no database) plus one route test. The merge
contract is pinned here too: the engine must agree with ``supervision`` on the states they
both decide, because both thresholds and readings are imported from it.
"""

import pytest

from app.config import Settings
from app.harness import classroom
from app.harness.teaching import supervision
from app.main import create_app


# --------------------------------------------------------------------------- helpers

def tick(**signals):
    return classroom.evaluate(signals).to_dict()


def _sv(signals):
    """Map a classroom snapshot to the supervisor's signal vocabulary."""
    return {
        'idle_seconds': signals.get('idle_seconds', 0),
        'window_seconds': signals.get('window_seconds', 300),
        'hidden_seconds': signals.get('hidden_seconds', 0),
        'progress': signals.get('progress', 0),
        'elapsed_seconds': signals.get('elapsed_seconds', 0),
        'planned_seconds': signals.get('planned_seconds', 1800),
        'scroll_events': signals.get('scroll_events', 0),
        'mastery': signals.get('node_confidence', 0.5),
        'mastery_known': signals.get('mastery_known', True),
        'resting': signals.get('on_break', False),
    }


# --------------------------------------------------------------------------- 1. rest

def test_a_learner_on_a_break_is_never_disturbed():
    decision = tick(on_break=True, idle_seconds=999, rest_quota=0)
    assert decision['branch'] == 'rest'
    assert decision['state'] == 'resting'
    assert decision['action'] == 'continue'
    assert decision['tts'] == ''
    assert decision['participation_penalty'] == 0.0


# --------------------------------------------------------------------------- 2. other app

def test_another_application_pauses_the_timer_and_docks_participation():
    decision = tick(playing_other=True, idle_seconds=30)
    assert decision['branch'] == 'abnormal'
    assert decision['action'] == 'pause'
    assert decision['participation_penalty'] == pytest.approx(
        classroom.PARTICIPATION_OTHER_APP)
    assert decision['timers'].get('paused') is True


# --------------------------------------------------------------------------- 3. cheat check

def test_very_suspicious_triggers_a_cheat_check_with_every_item():
    decision = tick(very_suspicious=True, explained_procedure=False,
                    answer_speed_ratio=0.1, ai_trace=True, camera_suspicion=True)
    assert decision['branch'] == 'cheat_check'
    assert decision['state'] == 'suspicious'
    assert decision['action'] == 'cheat_check'
    cheat = decision['cheat']
    assert cheat['answer_speed']['unhuman'] is True
    assert cheat['procedure']['ban_candidate'] is True
    assert cheat['ai_trace']['detected'] is True
    assert cheat['camera']['suspicious'] is True
    assert cheat['requires_human_review'] is True
    assert decision['participation_penalty'] == pytest.approx(
        classroom.PARTICIPATION_CHEAT)


def test_a_quiz_tick_with_a_conclusive_signal_runs_the_cheat_check():
    decision = tick(on_quiz=True, solved_variant=False)
    assert decision['branch'] == 'cheat_check'
    assert any('variant' in line.lower() for line in decision['evidence'])


def test_plain_suspicion_without_conclusive_evidence_only_asks():
    decision = tick(suspicious=True, on_quiz=False)
    assert decision['branch'] == 'abnormal'
    assert decision['action'] == 'ask'
    assert decision['timers'].get('stream_correct') is True


# --------------------------------------------------------------------------- 4. away

def test_away_with_rest_quota_left_reminds_without_penalty():
    decision = tick(idle_seconds=400, rest_quota=2)
    assert decision['branch'] == 'away'
    assert decision['state'] == 'away'
    assert decision['action'] == 'notify'
    assert decision['participation_penalty'] == 0.0
    assert decision['tts']
    assert decision['timers']['unactive_timeout_seconds'] == classroom.IDLE_AWAY_SECONDS


def test_away_with_the_rest_quota_spent_marks_the_timeout():
    decision = tick(idle_seconds=400, rest_quota=0)
    assert decision['branch'] == 'away'
    assert decision['action'] == 'notify'
    assert decision['participation_penalty'] == pytest.approx(
        classroom.PARTICIPATION_TIMEOUT)


def test_a_still_unanswered_learner_gets_a_staying_quiz():
    decision = tick(idle_seconds=400, rest_quota=0, unanswered_reminders=1)
    assert decision['branch'] == 'away'
    assert decision['action'] == 'quiz_stay'
    assert decision['quiz'] is True


def test_a_frame_that_shows_work_reads_as_reading_not_absence():
    decision = tick(idle_seconds=400, vision_state='on_task', vision_confidence=0.9)
    assert decision['branch'] == 'active'
    assert decision['state'] == 'working'
    assert decision['action'] == 'continue'


def test_a_low_confidence_frame_does_not_override_the_away_reading():
    decision = tick(idle_seconds=400, vision_state='on_task', vision_confidence=0.3,
                    rest_quota=2)
    assert decision['branch'] == 'away'


# --------------------------------------------------------------------------- 5. drifting

def test_drifting_between_the_two_idle_thresholds_asks_one_question():
    decision = tick(idle_seconds=150)
    assert decision['branch'] == 'drifting'
    assert decision['state'] == 'drifting'
    assert decision['action'] == 'ask'
    assert decision['participation_penalty'] == 0.0
    assert decision['tts']


# --------------------------------------------------------------------------- 6. lagging

def test_lagging_but_still_browsing_is_allowed_to_continue():
    decision = tick(progress=0.5, progress_target=0.6, idle_seconds=10, scroll_events=4)
    assert decision['branch'] == 'lagging'
    assert decision['state'] == 'working'
    assert decision['action'] == 'continue'


def test_lagging_and_stopped_gets_help_and_lowers_difficulty():
    decision = tick(progress=0.1, progress_target=0.6, idle_seconds=10)
    assert decision['branch'] == 'lagging'
    assert decision['state'] == 'struggling'
    assert decision['action'] == 'ask_help'
    assert decision['difficulty'] == 'dec'


def test_progress_is_measured_against_the_sessions_own_plan():
    # 600 s of a 1800 s plan is 33 % expected; 10 % done is a lag, and 600 s is old enough.
    decision = tick(progress=0.10, elapsed_seconds=600, planned_seconds=1800,
                    idle_seconds=10, scroll_events=4)
    assert decision['branch'] == 'lagging'
    assert decision['timers']['progress']['comparable'] is True
    assert decision['timers']['progress']['lag'] > 0


def test_ahead_of_the_plan_is_not_lagging():
    decision = tick(progress=0.9, elapsed_seconds=600, planned_seconds=1800,
                    idle_seconds=10, scroll_events=5)
    assert decision['branch'] == 'active'


# --------------------------------------------------------------------------- 7. stay too long

def test_staying_far_too_long_on_a_node_suggests_and_notes():
    decision = tick(progress=0.9, idle_seconds=10, scroll_events=4,
                    seconds_in_node=500, expected_node_seconds=180)
    assert decision['branch'] == 'struggling'
    assert decision['action'] == 'hint'
    assert decision['hint']


# --------------------------------------------------------------------------- 8. struggling

def test_an_error_streak_reads_as_struggling_and_asks_for_help():
    decision = tick(progress=0.9, idle_seconds=10, scroll_events=4, error_streak=3)
    assert decision['branch'] == 'struggling'
    assert decision['action'] == 'ask_help'
    assert decision['tts']


def test_a_learner_who_asks_for_help_gets_a_hint_and_a_skip():
    decision = tick(progress=0.9, idle_seconds=10, scroll_events=4, error_streak=3,
                    help_requested=True)
    assert decision['branch'] == 'struggling'
    assert decision['action'] == 'hint'
    assert decision['grant_skip'] is True


# --------------------------------------------------------------------------- 9. active

def test_an_active_on_track_learner_is_left_alone():
    decision = tick(progress=0.9, idle_seconds=10, scroll_events=6, node_confidence=0.5)
    assert decision['branch'] == 'active'
    assert decision['action'] == 'continue'
    assert decision['difficulty'] == 'normal'


# --------------------------------------------------------------------------- memory layer

def test_low_node_memory_explains_instead_of_advancing():
    decision = tick(progress=0.9, idle_seconds=10, scroll_events=6, node_confidence=0.2)
    assert decision['action'] == 'explain'
    assert decision['difficulty'] == 'dec'


def test_strong_node_memory_asks_the_learner_to_reason_aloud():
    decision = tick(progress=0.9, idle_seconds=10, scroll_events=6, node_confidence=0.9)
    assert decision['action'] == 'ask_reason'
    assert decision['difficulty'] == 'inc'


def test_low_node_memory_on_a_quiz_allows_a_skip():
    decision = tick(progress=0.9, idle_seconds=10, scroll_events=6, on_quiz=True,
                    node_confidence=0.2)
    assert decision['grant_skip'] is True


def test_an_unknown_belief_is_not_a_weak_one():
    decision = tick(progress=0.9, idle_seconds=10, scroll_events=6,
                    node_confidence=0.15, mastery_known=False)
    assert decision['action'] == 'continue'
    assert decision['difficulty'] == 'normal'
    assert any('unknown' in line.lower() for line in decision['evidence'])


def test_the_memory_layer_never_overrides_a_pause_or_cheat_check():
    paused = tick(playing_other=True, node_confidence=0.1)
    assert paused['action'] == 'pause'
    cheated = tick(very_suspicious=True, node_confidence=0.9)
    assert cheated['action'] == 'cheat_check'


# --------------------------------------------------------------------------- cooldown

def test_an_interruption_inside_the_cooldown_is_marked_quiet():
    decision = tick(idle_seconds=400, rest_quota=0, last_notice_at=1000, now=1030)
    assert decision['action'] == 'notify'
    assert decision['quiet'] is True
    assert any('cooldown' in line.lower() for line in decision['evidence'])


def test_an_interruption_after_the_cooldown_is_not_quiet():
    decision = tick(idle_seconds=400, rest_quota=0, last_notice_at=1000, now=1400)
    assert decision['quiet'] is False


def test_the_cooldown_never_silences_a_cheat_check():
    decision = tick(very_suspicious=True, last_notice_at=1000, now=1030)
    assert decision['action'] == 'cheat_check'
    assert decision['quiet'] is False


# --------------------------------------------------------------------------- participation

def test_the_decision_carries_a_participation_reading():
    decision = tick(idle_seconds=10, active_seconds=240, window_seconds=300,
                    hidden_seconds=30)
    reading = decision['participation']
    assert reading['active_share'] == pytest.approx(0.8)
    assert 'reading' in reading


# --------------------------------------------------------------------------- robustness

def test_from_mapping_tolerates_missing_and_junk_fields():
    snapshot = classroom.Snapshot.from_mapping(
        {'idle_seconds': 'not-a-number', 'scroll_events': None, 'rest_quota': 'x'})
    assert snapshot.idle_seconds == 0.0
    assert snapshot.scroll_events == 0
    assert snapshot.rest_quota == 1


def test_the_same_snapshot_always_yields_the_same_decision():
    signals = {'idle_seconds': 400, 'rest_quota': 0, 'node_id': 'fractions'}
    assert classroom.evaluate(signals).to_dict() == classroom.evaluate(signals).to_dict()


def test_describe_exposes_the_reviewable_thresholds():
    posture = classroom.describe()
    assert posture['branches'] == list(classroom.BRANCHES)
    assert posture['thresholds']['idle_away_seconds'] == classroom.IDLE_AWAY_SECONDS
    assert posture['thresholds']['cooldown_seconds'] == classroom.NOTICE_COOLDOWN_SECONDS
    assert posture['participation_penalties']['cheat'] == classroom.PARTICIPATION_CHEAT


# --------------------------------------------------------------------------- consistency

@pytest.mark.parametrize('signals,expected', [
    ({'on_break': True}, 'resting'),
    ({'idle_seconds': 400}, 'away'),
    ({'idle_seconds': 150}, 'drifting'),
    ({'progress': 0.10, 'elapsed_seconds': 600, 'planned_seconds': 1800,
      'scroll_events': 4}, 'working'),
    ({'progress': 0.10, 'elapsed_seconds': 600, 'planned_seconds': 1800,
      'scroll_events': 0}, 'struggling'),
    ({'progress': 0.9, 'elapsed_seconds': 600, 'planned_seconds': 1800,
      'scroll_events': 5, 'node_confidence': 0.5, 'mastery_known': True}, 'working'),
])
def test_classroom_and_supervision_agree_on_shared_states(signals, expected):
    """Both engines are mounted; on the states they both decide they must not disagree."""
    assert classroom.evaluate(signals).state == expected
    assert supervision.assess(_sv(signals))['state'] == expected


# --------------------------------------------------------------------------- route

@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key-not-real')
    from fastapi.testclient import TestClient
    with TestClient(create_app(Settings.from_env())) as client:
        yield client


def _account(client, label='classroom'):
    response = client.post('/api/v1/auth/register', json={
        'name': label, 'email': f'{label}@example.test',
        'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_the_tick_route_returns_a_decision(wired):
    headers = _account(wired)
    response = wired.post('/api/v1/classroom/tick', headers=headers,
                          json={'signals': {'idle_seconds': 400, 'rest_quota': 0}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['branch'] == 'away'
    assert body['action'] == 'notify'
    assert body['participation_penalty'] == pytest.approx(classroom.PARTICIPATION_TIMEOUT)


def test_the_tick_route_needs_a_session(wired):
    assert wired.post('/api/v1/classroom/tick', json={'signals': {}}).status_code == 401
