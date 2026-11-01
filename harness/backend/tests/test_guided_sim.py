"""Tests for the guided-simulation cycle and its interaction contract.

The claim under test is the one the research supports: a simulation only counts as evidence
when the learner predicted before interacting and explained afterwards. A run that skipped
the scaffolding must be refused, and the refusal must name the missing step.
"""

import pytest

from app import harness
from app.harness import guided_sim


def _good_outcome(**overrides):
    outcome = guided_sim.outcome_payload(
        sim_id='supply-demand', concept_id='market_equilibrium',
        prediction='price rises', actual='price rises', exploration_score=0.8,
        explanation='Demand rose while supply was fixed, so the clearing price moved up.')
    outcome.update(overrides)
    return outcome


def test_a_complete_guided_run_is_acceptable_evidence():
    assert guided_sim.validate_outcome(_good_outcome()) == []


def test_the_cycle_prompts_cover_all_three_phases():
    planned = guided_sim.cycle('the market price')
    assert planned['steps'] == list(guided_sim.STEPS)
    assert set(planned['prompts']) == set(guided_sim.STEPS)
    assert 'market price' in planned['prompts']['predict']
    assert planned['scored_only_with_scaffolding'] is True


def test_a_run_without_a_prediction_or_explanation_is_refused():
    for missing in ('predict', 'explain'):
        steps = [step for step in guided_sim.STEPS if step != missing]
        problems = guided_sim.validate_outcome(_good_outcome(steps_completed=steps))
        assert problems and any(missing in problem for problem in problems)


def test_a_short_explanation_does_not_count():
    problems = guided_sim.validate_outcome(_good_outcome(explanation='idk'))
    assert any('at least' in problem for problem in problems)


def test_missing_required_fields_are_named():
    problems = guided_sim.validate_outcome({'sim_id': 'x'})
    assert problems
    assert any('concept_id' in problem for problem in problems)


def test_an_out_of_range_or_non_boolean_field_is_refused():
    assert guided_sim.validate_outcome(_good_outcome(exploration_score=1.5))
    assert guided_sim.validate_outcome(_good_outcome(exploration_score='lots'))
    assert guided_sim.validate_outcome(_good_outcome(prediction_correct='yes'))
    # A boolean is not a number, even though bool subclasses int in Python.
    assert guided_sim.validate_outcome(_good_outcome(exploration_score=True))


def test_the_prediction_is_scored_by_the_payload_builder_not_asserted_by_the_caller():
    hit = guided_sim.outcome_payload(sim_id='s', concept_id='c', prediction='UP', actual='up',
                                     exploration_score=0.5, explanation='a' * 30)
    assert hit['prediction_correct'] is True
    miss = guided_sim.outcome_payload(sim_id='s', concept_id='c', prediction='up', actual='down',
                                      exploration_score=0.5, explanation='a' * 30)
    assert miss['prediction_correct'] is False
    # And the builder's output always passes its own contract.
    assert guided_sim.validate_outcome(miss) == []


def test_a_wrong_prediction_is_not_scolded():
    scored = guided_sim.evaluate_prediction('up', 'down')
    assert scored['prediction_correct'] is False
    assert 'wrong' not in scored['statement'].casefold()


def test_status_reports_the_simulation_cycle():
    described = guided_sim.describe()
    assert described['steps'] == list(guided_sim.STEPS)
    assert described['scored_only_with_scaffolding'] is True
    status = harness.status()
    assert status['simulation_cycle']['steps'] == list(guided_sim.STEPS)
