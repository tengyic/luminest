"""Tests for the Socratic dialogue ladder.

The claim under test is procedural and checkable: the tutor escalates one rung per failed
cycle, and the answer is not revealed before the ladder has been worked - except when the
learner explicitly asks to be shown, which is honoured immediately.
"""

import pytest

from app import harness
from app.harness import conduct, socratic


def test_the_ladder_escalates_one_rung_per_failed_cycle():
    assert socratic.step({'consecutive_failures': 0})['move'] == 'pump'
    assert socratic.step({'consecutive_failures': 1})['move'] == 'hint'
    assert socratic.step({'consecutive_failures': 2})['move'] == 'prompt'
    assert socratic.step({'consecutive_failures': 3})['move'] == 'assert'
    # Past the last rung it stays at assertion rather than inventing a new move.
    assert socratic.step({'consecutive_failures': 9})['move'] == 'assert'


def test_the_answer_is_not_revealed_before_the_ladder_is_worked():
    for failures in range(socratic.ASSERT_AFTER_FAILURES):
        assert socratic.may_reveal_answer({'consecutive_failures': failures}) is False
    assert socratic.may_reveal_answer(
        {'consecutive_failures': socratic.ASSERT_AFTER_FAILURES}) is True


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


def test_the_prompt_conduct_and_the_server_guard_state_the_same_threshold():
    """The decision and its enforcement must not drift apart.

    Bridge (Wang et al., NAACL 2024, arXiv:2310.10648) shows that an LLM tutor
    degrades sharply when the pedagogical decision it is given does not match the
    one it should be following: GPT-4 responses were +76% preferred with expert
    decisions and -97% worse with random ones. Bastani et al. (PNAS 2025,
    https://doi.org/10.1073/pnas.2422633122) shows the harm when an answer-first
    shortcut is available. If the system prompt says "two failed cycles" while the
    server-side leakage guard only permits revelation at three, the model is being
    handed exactly that mismatched decision. This test keeps the three surfaces -
    the ladder, ``describe()`` and both injected conduct blocks - on one number.
    """
    threshold = socratic.LADDER.index('assert')
    assert socratic.ASSERT_AFTER_FAILURES == threshold == 3
    assert socratic.describe()['assert_after_failures'] == threshold

    assert 'three failed cycles' in conduct.TEACHING_CONDUCT
    assert 'two failed cycles' not in conduct.TEACHING_CONDUCT
    dialogue_rules = [r for r in conduct.CONDUCT_RULES if r['rule'] == 'dialogue']
    assert len(dialogue_rules) == 1
    assert 'three failed cycles' in dialogue_rules[0]['text']

    for failures in range(6):
        expected_reveal = failures >= threshold
        assert socratic.may_reveal_answer(
            {'consecutive_failures': failures}) is expected_reveal


def test_the_research_note_does_not_turn_a_guardrail_into_an_effect_claim():
    """Avoiding a measured harm is not the same as proving a learning gain."""
    note = socratic.describe()['research_note']
    assert '10.1073/pnas.2422633122' in note
    assert 's41598-025-97652-6' in note
    assert 'did not produce a statistically significant learning gain' in note
    assert 'No learner-outcome trial has been run on this harness.' in note
