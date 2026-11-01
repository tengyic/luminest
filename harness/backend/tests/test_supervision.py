"""The session supervisor: whether to speak, and the three things it refuses to do.

The interesting cases are the ones where the obvious product decision is wrong: interrupting
a learner who is behind but still reading, and treating a fast answer as dishonesty.
"""
import pytest

from app.harness.teaching import motivation, supervision


def base(**overrides):
    signals = {'idle_seconds': 5.0, 'window_seconds': 300.0, 'active_seconds': 200.0,
               'scroll_events': 6.0, 'mastery': 0.60, 'mastery_known': True, 'progress': 0.5,
               'elapsed_seconds': 600.0, 'planned_seconds': 1200.0}
    signals.update(overrides)
    return signals


def test_a_concept_with_no_attempts_is_not_treated_as_a_weak_one():
    """``PRIOR`` is "we know nothing", not "they are struggling". Opening every new learner
    with an unsolicited explanation is the failure this rule prevents."""
    reading = supervision.assess(base(mastery=0.15, mastery_known=False))
    assert reading['state'] == 'working'
    assert reading['move']['kind'] == 'continue'
    assert reading['difficulty']['direction'] == 'hold'


def test_a_learner_who_is_present_and_on_pace_is_left_alone():
    reading = supervision.assess(base())
    assert reading['state'] == 'working'
    assert reading['move']['kind'] == 'continue'
    assert 'Do not interrupt' in reading['move']['say']


def test_an_empty_chair_gets_a_break_offer_while_breaks_remain():
    reading = supervision.assess(base(idle_seconds=400.0, rest_quota_used=0, rest_quota_total=2))
    assert reading['state'] == 'away'
    assert reading['move']['kind'] == 'offer_break'
    assert '2 of 2 breaks' in reading['move']['why']


def test_with_breaks_used_up_the_move_is_a_question_not_a_nag():
    reading = supervision.assess(base(idle_seconds=400.0, rest_quota_used=2, rest_quota_total=2))
    assert reading['move']['kind'] == 'retrieval'
    # The timeout re-plans the session; it does not record anything against the learner.
    assert reading['move']['shorten_session'] is True
    assert 'score' not in reading['move']['say'].lower()


def test_a_break_the_learner_asked_for_is_not_an_absence():
    reading = supervision.assess(base(idle_seconds=900.0, resting=True))
    assert reading['state'] == 'resting'
    assert reading['move']['kind'] == 'none'


def test_ninety_seconds_of_silence_is_a_nudge_not_an_accusation():
    reading = supervision.assess(base(idle_seconds=120.0))
    assert reading['state'] == 'drifting'
    assert reading['move']['kind'] == 'nudge'


def test_being_behind_the_plan_while_still_scrolling_is_not_an_emergency():
    """The spec's `If active (small scroll)/proceed`. Interrupting this is the error."""
    reading = supervision.assess(base(progress=0.10, elapsed_seconds=900.0, planned_seconds=1200.0,
                                      scroll_events=8.0))
    assert reading['progress']['lagging'] is True
    assert reading['state'] == 'working'
    assert reading['move']['kind'] == 'continue'
    assert 'browsing' in reading['move']['why']


def test_being_behind_and_still_earns_the_next_step_only():
    reading = supervision.assess(base(progress=0.10, elapsed_seconds=900.0, planned_seconds=1200.0,
                                      scroll_events=0.0))
    assert reading['state'] == 'struggling'
    assert reading['move']['kind'] == 'hint'
    assert 'not the whole solution' in reading['move']['say']


def test_thin_mastery_is_taught_rather_than_quizzed():
    reading = supervision.assess(base(mastery=0.20))
    assert reading['move']['kind'] == 'explain'


def test_secure_mastery_earns_a_why_question():
    reading = supervision.assess(base(mastery=0.92))
    assert reading['move']['kind'] == 'ask_reason'


def test_progress_is_not_judged_before_the_session_has_any_shape():
    reading = supervision.assess(base(progress=0.0, elapsed_seconds=60.0, planned_seconds=1200.0))
    assert reading['progress']['comparable'] is False
    assert reading['progress']['lagging'] is False


# ---------------------------------------------------------------- provenance checks

def test_an_impossibly_fast_right_answer_asks_for_a_variant():
    reading = supervision.assess(base(answer_latency_seconds=4.0, personal_average_latency=60.0,
                                      last_answer_correct=True))
    assert reading['check']['check'] == 'variant'
    assert 'not an accusation' in reading['check']['not_a_verdict']


def test_a_right_answer_without_reasoning_asks_for_the_reasoning():
    reading = supervision.assess(base(last_answer_correct=True, explained=False,
                                      personal_average_latency=60.0, answer_latency_seconds=55.0))
    assert reading['check']['check'] == 'explain_back'


def test_solving_the_original_but_not_the_variant_is_fragile_knowledge():
    reading = supervision.assess(base(variant_result='wrong'))
    assert reading['check']['check'] == 'variant'
    assert any('variant' in reason for reason in reading['check']['reasons'])


def test_no_check_is_run_during_an_assessment():
    """A variant item inside a unit test is a second test, not a check."""
    reading = supervision.assess(base(variant_result='wrong', item_context='test',
                                      answer_latency_seconds=3.0, personal_average_latency=60.0))
    assert 'check' not in reading


def test_a_normal_answer_raises_nothing():
    reading = supervision.assess(base(answer_latency_seconds=58.0, personal_average_latency=60.0,
                                      last_answer_correct=True, explained=True))
    assert 'check' not in reading


# ---------------------------------------------------------------- difficulty

def test_secure_mastery_and_a_holding_record_move_the_item_up():
    assert supervision.difficulty(base(mastery=0.9, recent_accuracy=0.9))['direction'] == 'up'


def test_thin_mastery_moves_the_item_down():
    assert supervision.difficulty(base(mastery=0.2, recent_accuracy=0.3))['direction'] == 'down'


def test_fast_and_wrong_together_moves_down_even_at_middling_mastery():
    moved = supervision.difficulty(base(mastery=0.5, recent_accuracy=0.4,
                                        answer_latency_seconds=3.0,
                                        personal_average_latency=60.0))
    assert moved['direction'] == 'down'
    assert 'guessed' in moved['reason']


def test_no_record_means_hold():
    assert supervision.difficulty(base(mastery=0.5))['direction'] == 'hold'


# ---------------------------------------------------------------- posture

def test_the_supervisor_never_deducts_flags_or_watches():
    posture = supervision.describe()['posture']
    assert posture['deducts_marks'] is False
    assert posture['flags_accounts'] is False
    assert posture['reads_camera'] is False
    assert posture['blocks_lessons'] is False
    # And the reading says so itself, so a client cannot present it as a penalty.
    assert supervision.assess(base(idle_seconds=400.0))['posture']['deducts_marks'] is False


def test_participation_is_reported_as_a_reading_not_a_score():
    reading = supervision.participation(base(active_seconds=240.0, window_seconds=300.0))
    assert reading['active_share'] == pytest.approx(0.8, abs=0.01)
    assert reading['reading'] == 'Most of the session was hands-on.'


def test_the_same_interruption_is_not_repeated_inside_the_cooldown():
    reading = supervision.assess(base(idle_seconds=120.0), now=1000.0, last_notice_at=900.0)
    assert reading['quiet'] is True


# ---------------------------------------------------------------- motivation

def test_a_streak_that_ends_yesterday_is_still_current():
    """Telling a learner at 09:00 that their streak broke is wrong and demoralising."""
    assert motivation.streak(['2026-10-20', '2026-10-21', '2026-10-22'],
                             today='2026-10-23')['current'] == 3


def test_a_streak_that_ends_two_days_ago_is_over():
    assert motivation.streak(['2026-10-20', '2026-10-21'], today='2026-10-23')['current'] == 0


def test_the_longest_run_survives_a_break():
    reading = motivation.streak(['2026-10-01', '2026-10-02', '2026-10-03',
                                 '2026-10-10', '2026-10-23'], today='2026-10-23')
    assert reading['current'] == 1
    assert reading['longest'] == 3


def test_five_days_in_a_row_is_announced_once():
    reading = motivation.streak([f'2026-10-{day:02d}' for day in range(19, 24)], today='2026-10-23')
    assert reading['current'] == 5
    assert 'five days in a row' in reading['announce']


def test_a_question_streak_counts_practice_and_ignores_assessments():
    """The spec's correction: a unit test must not be able to break or inflate the streak."""
    results = [{'context': 'quiz', 'correct': True},
               {'context': 'test', 'correct': False},      # skipped, neither extends nor breaks
               {'context': 'practice', 'correct': True},
               {'context': 'diagnostic', 'correct': False},
               {'context': 'quiz', 'correct': True}]
    reading = motivation.quiz_streak(results)
    assert reading['current'] == 3
    assert reading['milestone'] is None


def test_five_practice_answers_in_a_row_is_announced():
    results = [{'context': 'quiz', 'correct': True} for _ in range(5)]
    assert 'five in a row' in motivation.quiz_streak(results)['announce']


def test_a_milestone_announces_on_the_crossing_not_on_every_attempt():
    assert motivation.node_milestone(0.72, 0.84)['threshold'] == 0.80
    assert motivation.node_milestone(0.84, 0.88) is None
    assert motivation.node_milestone(0.88, 0.70) is None


def test_badges_name_the_condition_that_earned_them():
    earned = motivation.badges(days_studied=7, longest_streak=5)
    names = [badge['name'] for badge in earned]
    assert names == ['First session', 'Week one', 'Habit']
    assert all(badge['condition'] for badge in earned)


def test_the_certificate_needs_the_tests_and_the_assignments():
    units = [{'unit': '1', 'test_passed': True, 'assignments_complete': True},
             {'unit': '2', 'test_passed': True, 'assignments_complete': False}]
    reading = motivation.certificate(units)
    assert reading['earned'] is False
    assert reading['outstanding'] == ['2']
    assert motivation.certificate([units[0]])['earned'] is True
