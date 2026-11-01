"""Tests for the Socratic dialogue ladder.

The claim under test is procedural and checkable: the tutor escalates one rung per failed
cycle, and the answer is not revealed before the ladder has been worked - except when the
learner explicitly asks to be shown, which is honoured immediately.
"""

import pytest

from app import harness
from app.harness import socratic


def test_the_ladder_escalates_one_rung_per_failed_cycle():
    assert socratic.step({'consecutive_failures': 0})['move'] == 'pump'
    assert socratic.step({'consecutive_failures': 1})['move'] == 'hint'
    assert socratic.step({'consecutive_failures': 2})['move'] == 'prompt'
    assert socratic.step({'consecutive_failures': 3})['move'] == 'assert'
    # Past the last rung it stays at assertion rather than inventing a new move.
    assert socratic.step({'consecutive_failures': 9})['move'] == 'assert'


def test_the_answer_is_not_revealed_before_two_failed_cycles():
    for failures in (0, 1, 2):
        assert socratic.may_reveal_answer({'consecutive_failures': failures}) is False
    assert socratic.may_reveal_answer({'consecutive_failures': 3}) is True


def test_every_rung_is_on_the_ladder_and_states_its_position():
    for failures, move in enumerate(socratic.LADDER):
        result = socratic.step({'consecutive_failures': failures})
        assert result['move'] == move
        assert result['ladder_position'] == socratic.LADDER.index(move)
        assert result['say'] and result['reason']


def test_an_explicit_request_for_a_worked_explanation_is_honoured_at_once():
    result = socratic.step({'asked_for_explanation': True, 'consecutive_failures': 0})
    assert result['move'] == 'assert'
    assert result['reveal_answer'] is True
    assert 'asked' in result['reason']


def test_a_learner_who_has_explained_is_asked_to_go_deeper_not_corrected():
    result = socratic.step({'learner_explained': True, 'consecutive_failures': 0})
    assert result['move'] == 'pump'
    assert result['reveal_answer'] is False


def test_a_climbing_latency_trend_narrows_the_space():
    result = socratic.step({'trend': 'much_slower', 'consecutive_failures': 0})
    assert result['move'] == 'hint'


def test_the_step_is_deterministic_and_the_guard_agrees_with_the_policy():
    state = {'consecutive_failures': 2, 'trend': 'flat'}
    assert socratic.step(state) == socratic.step(state)
    # The leakage guard must never disagree with the dialogue policy.
    for failures in range(6):
        probe = {'consecutive_failures': failures}
        assert socratic.may_reveal_answer(probe) == socratic.step(probe)['reveal_answer']


def test_status_reports_the_dialogue_ladder():
    described = socratic.describe()
    assert described['ladder'] == list(socratic.LADDER)
    assert described['assert_after_failures'] >= 1
    assert described['honours_explicit_request'] is True
    status = harness.status()
    assert status['dialogue_ladder']['ladder'] == list(socratic.LADDER)
