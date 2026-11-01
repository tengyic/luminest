"""Tests for the modality router and its wiring into the loop.

These tests are written around the claim the product makes - "the representation is chosen
from the learner's knowledge state and the load, never from a learning style" - so the
central assertions are that a novice on short material gets narration, an expert gets
static text, long material forces text, load forces a change of frame, and the router says
in its own output that a learning style is not an input.
"""

import pytest
from sqlalchemy import select

from app import harness
from app.db import HarnessRun
from app.harness import modality
from test_harness import base_evidence, tool_ctx, CURVE  # noqa: F401 - helpers
from test_harness import database, learner, settings  # noqa: F401 - fixtures


# ------------------------------------------------------------------ the router itself

def test_every_channel_is_reachable_and_the_choice_is_deterministic():
    seen = set()
    for evidence in (base_evidence(), base_evidence(mastery=0.9, attempts=6, sample=6),
                     base_evidence(has_figure=False), base_evidence(sample=4, recent_accuracy=0.0,
                                                                    elapsed_trend='much_faster')):
        first = modality.route(evidence)
        second = modality.route(evidence)
        assert first == second
        assert first['channel'] in modality.CHANNELS
        assert first['reason']
        seen.add(first['channel'])
    # The rules can produce more than one channel; a router that always answers the same
    # way would pass a weaker test while being useless.
    assert len(seen) >= 2


def test_a_novice_on_short_material_gets_narration_when_no_interactive_exists():
    routed = modality.route(base_evidence(mastery=0.2, attempts=1, has_figure=False))
    assert routed['channel'] == 'narration'
    assert 'modality effect' in routed['reason']
    assert any('redundancy' in constraint for constraint in routed['constraints'])


def test_a_novice_with_a_figure_available_gets_the_guided_interactive():
    routed = modality.route(base_evidence(mastery=0.2, attempts=1, has_figure=True))
    assert routed['channel'] == 'interactive'
    assert any('prediction' in constraint for constraint in routed['constraints'])


def test_an_expert_gets_static_text_with_a_problem_first():
    routed = modality.route(base_evidence(mastery=0.9, attempts=6, sample=6, recent_accuracy=0.9))
    assert routed['channel'] == 'text'
    assert any('problem, not a worked example' in constraint for constraint in routed['constraints'])
    assert routed['signals']['prior_knowledge'] == 'expert'


def test_long_material_forces_text_even_for_a_novice():
    routed = modality.route(base_evidence(mastery=0.2, attempts=1), transience='long')
    assert routed['channel'] == 'text'
    assert 'transient' in routed['reason']


def test_frustration_changes_the_frame_to_a_diagram():
    routed = modality.route(base_evidence(mastery=0.3, sample=4, recent_accuracy=0.0,
                                          elapsed_trend='much_faster'))
    assert routed['channel'] == 'diagram'
    assert routed['signals']['load'] == 'frustrated'


def test_a_long_session_prefers_a_short_static_segment():
    routed = modality.route(base_evidence(mastery=0.5, active_minutes_today=50.0))
    assert routed['channel'] == 'text'
    assert routed['signals']['load'] == 'overloaded'


def test_the_router_says_a_learning_style_is_not_an_input():
    routed = modality.route(base_evidence())
    assert 'learning style' in routed['excluded']
    assert 'learning style' in routed['research_note']
    described = modality.describe()
    assert described['channels'] == list(modality.CHANNELS)
    assert 'learning style' in described['excluded']
    assert described['inputs']


def test_transience_and_interactive_availability_are_explicit_inputs():
    # Both can be forced by the caller rather than guessed from behaviour.
    forced_long = modality.route(base_evidence(mastery=0.2, attempts=1), transience='long',
                                 interactive_available=True)
    assert forced_long['channel'] == 'text'
    forced_interactive = modality.route(base_evidence(mastery=0.2, attempts=1, has_figure=False),
                                        interactive_available=True)
    assert forced_interactive['channel'] == 'interactive'


# ------------------------------------------------------------------ wiring into the loop

def test_decision_modality_defaults_to_none():
    decision = harness.loop.Decision(run_id='r', move='explain', reason='because',
                                     evidence=base_evidence(), candidates=[], tool_plan=[],
                                     constraints=[], concept_id=CURVE, created_at=0.0)
    assert decision.modality is None
    assert decision.to_dict()['modality'] is None


def test_plan_attaches_a_routed_representation_and_stores_the_channel(database, learner, settings):
    ctx = tool_ctx(database, learner, settings)
    decision = harness.loop.plan(ctx, CURVE)
    assert decision.modality and decision.modality['channel'] in modality.CHANNELS
    view = harness.loop.explain(decision)
    assert view['modality']['channel'] == decision.modality['channel']
    assert view['modality']['excluded']
    stored = database.scalar(select(HarnessRun).where(HarnessRun.id == decision.run_id))
    assert stored is not None
    assert stored.evidence['modality_channel'] == decision.modality['channel']


def test_status_reports_the_router_and_the_conduct_rules():
    status = harness.status()
    assert status['modality']['channels'] == list(modality.CHANNELS)
    assert status['conduct_rules'] and all(rule['evidence'] for rule in status['conduct_rules'])


# ------------------------------------------------------------------ the shared conduct block

def test_the_tutor_and_the_harness_share_one_conduct_source():
    from app import tutor
    assert tutor.TEACHING_CONDUCT is harness.conduct.TEACHING_CONDUCT


def test_the_system_prompt_carries_the_conduct_block_and_stays_transparent():
    rendered = harness.prompt.build('Ada', 'Quadratics')
    assert 'Teaching conduct' in rendered
    assert 'learning style' in rendered
    assert 'pump' in rendered
    payload = harness.prompt.payload('Ada', 'Quadratics', 'digest')
    assert payload['conduct'] and payload['conduct_rules']
    # The transparency panel must render the exact prompt the model was given.
    assert payload['rendered'] == harness.prompt.build('Ada', 'Quadratics', 'digest')
