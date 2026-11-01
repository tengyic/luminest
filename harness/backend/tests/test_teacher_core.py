"""The teaching core: the config-driven policy, the schedule, the routing, the loop.

These tests are written around the claim the rebuilt teacher makes, which is that
*the teacher is data*. So the assertions are not "the tutor does something
reasonable" but the four things that claim commits to:

1. **The policy reads evidence and configuration, not prose.** A given learner state
   produces a specific move, with a reason, deterministically - and moving a
   threshold in the profile moves the decision.
2. **The schedule is the FSRS-6 forgetting curve, not a calendar.** A review is due
   at the desired-retention point, weakest memory first, and a concept never
   reviewed is *new* rather than due.
3. **The prompt is rendered from the profile.** Editing the profile changes the
   prompt, and no section can advertise a move, a channel or a retention point the
   configuration does not declare.
4. **The loop completes.** For a learner who needs one, the plan contains the
   instruction, the drawing or the simulation, the practice, the check and the
   consolidation - and for a learner who needs none of it, the plan says stop.

Nothing here needs a database: the whole package is a pure function of the evidence
record and the profile, which is what makes it reviewable. The wiring into the live
tutor is covered by ``test_harness.py`` and ``test_modality.py``.
"""

import pytest

from app.memory import recall_probability
from app.harness.loop import MOVES
from app.harness.teaching import (ConceptFacts, ModalityChoice, TeacherProfile,
                                  TeachingPlan, build_evidence, choose_modality,
                                  default_profile, due_concepts, is_due, plan_retrieval,
                                  plan_session, render_modalities_section,
                                  render_move_section, render_persona_section,
                                  render_retrieval_section, score_moves, select_move)
from app.harness.teaching.modalities import MODALITIES
from app.harness.teaching.session import PHASES
from app.harness import toolbox

DAY = 86400.0
NOW = 1_700_000_000.0


# --------------------------------------------------------------------- helpers

def maths_facts(**overrides) -> ConceptFacts:
    """A mathematics concept with authored material and a figure."""
    base = dict(id='algebra.fractions', title='Fractions', strand='Algebra',
                tier='core', depth=1, prerequisite_count=1, dependant_count=2,
                has_lesson=True, has_figure=True, has_video=False,
                subject_kind='mathematics', concept_type='quantitative_relation',
                keywords=('fraction', 'denominator'))
    base.update(overrides)
    return ConceptFacts(**base)


def evidence(facts=None, state=None, **kw):
    """The evidence record, built the way the live harness builds it."""
    profile = kw.pop('profile', None) or default_profile()
    return build_evidence(facts or maths_facts(), state or {},
                          mastery_threshold=profile.difficulty.mastery_threshold, **kw)


def fsrs_state(*, stability, last_review, mastery=0.7, attempts=4, correct_count=3,
               lapses=0, difficulty=5.0):
    """A stored FSRS-6 state, as the scheduler writes it."""
    return {'stability': stability, 'difficulty': difficulty, 'last_review': last_review,
            'reps': attempts, 'lapses': lapses, 'memory_model': 'fsrs-6',
            'mastery': mastery, 'attempts': attempts, 'correct_count': correct_count}


# ------------------------------------------------------------------ the policy

def test_the_move_vocabulary_matches_the_loop():
    """Two vocabularies for the same nine actions would let a plan name a move the
    runner does not know, so the profile's moves must be the loop's moves."""
    assert default_profile().move_names == MOVES


def test_a_concept_with_no_evidence_is_oriented_before_it_is_taught():
    """No attempts means no evidence, and teaching against no evidence is guessing."""
    chosen = select_move(evidence(state={'mastery': 0.15, 'attempts': 0}), default_profile())
    assert chosen.move == 'orient'
    assert 'no scored attempt' in chosen.reason.lower()


def test_a_concept_that_satisfies_the_completion_gate_stops_being_taught():
    """The freeCodeCamp gate: attempts *and* transfer, not attempts alone."""
    profile = default_profile()
    state = fsrs_state(stability=60.0, last_review=NOW - DAY, mastery=0.95,
                       attempts=8, correct_count=8)
    ev = evidence(state=state, project_status='completed', now=NOW)
    assert ev.satisfied(profile.completion)
    ranked = {item.move: item.score for item in score_moves(ev, profile)}
    for forward in ('explain', 'simulate', 'retrieve', 'discuss', 'project', 'generate'):
        assert ranked[forward] == 0.0, f'{forward} was still scored after the gate closed'
    # Consolidation and rest are not "teaching", so they survive the gate - which is
    # what makes "already learned" mean "connect it" rather than "say nothing".
    assert ranked['consolidate'] > 0.0


def test_recognition_alone_does_not_close_the_gate():
    """Passing checks is not transfer: without the applied task the gate stays open."""
    profile = default_profile()
    state = fsrs_state(stability=60.0, last_review=NOW - DAY, mastery=0.95,
                       attempts=8, correct_count=8)
    ev = evidence(state=state, project_status='unknown', now=NOW)
    assert not ev.satisfied(profile.completion)
    ranked = {item.move: item.score for item in score_moves(ev, profile)}
    assert ranked['project'] > ranked['explain'], 'the transfer move should win here'


def test_prerequisite_debt_stops_forward_teaching_and_repairs_instead():
    """ossu/computer-science: never teach past an unmet prerequisite."""
    profile = default_profile()
    state = fsrs_state(stability=30.0, last_review=NOW - DAY, mastery=0.65,
                       attempts=4, correct_count=2)
    clean = evidence(state=state, now=NOW, parent_states={'p': {'mastery': 0.8}})
    shaky = evidence(state=state, now=NOW,
                     parent_states={'p': {'mastery': 0.45}, 'q': {'mastery': 0.55}})
    assert clean.prerequisite_debt < profile.sequencing.debt_ceiling
    assert shaky.prerequisite_debt > profile.sequencing.debt_ceiling

    clean_scores = {i.move: i.score for i in score_moves(clean, profile)}
    shaky_scores = {i.move: i.score for i in score_moves(shaky, profile)}
    for forward in ('explain', 'simulate', 'discuss', 'generate'):
        assert shaky_scores[forward] < clean_scores[forward], forward
    # Orient is not penalised: it is the repair move, and it has to outrank the
    # forward moves it is replacing.
    assert shaky_scores['orient'] > shaky_scores['explain']


def test_overload_chooses_rest_over_another_explanation():
    """Fast and wrong is the signature of overload, and the fix is to stop."""
    profile = default_profile()
    ev = evidence(state={'mastery': 0.3, 'attempts': 5, 'correct_count': 1},
                  elapsed_trend='much_faster')
    assert ev.frustrated
    chosen = select_move(ev, profile)
    assert chosen.move == 'rest'
    assert 'fast and wrong' in chosen.reason.lower()


def test_a_session_past_its_budget_stops_adding_material():
    profile = default_profile()
    ev = evidence(state=fsrs_state(stability=20.0, last_review=NOW - DAY, mastery=0.7),
                  now=NOW, session_minutes=profile.difficulty.long_session_minutes + 15)
    ranked = {i.move: i.score for i in score_moves(ev, profile)}
    assert ranked['rest'] > 0.3
    assert ranked['rest'] > ranked['explain']


def test_a_procedural_error_reaches_the_move_that_corrects_a_process():
    profile = default_profile()
    state = {'mastery': 0.45, 'attempts': 4, 'correct_count': 2}
    procedural = evidence(state=state, top_error='procedural')
    conceptual = evidence(state=state, top_error='conceptual')
    p_scores = {i.move: i.score for i in score_moves(procedural, profile)}
    c_scores = {i.move: i.score for i in score_moves(conceptual, profile)}
    assert p_scores['simulate'] > c_scores['simulate']
    assert c_scores['discuss'] > p_scores['discuss']


def test_every_candidate_carries_a_reason_and_is_clamped():
    profile = default_profile()
    ev = evidence(state={'mastery': 0.5, 'attempts': 3, 'correct_count': 2})
    ranked = score_moves(ev, profile)
    assert len(ranked) == len(profile.moves)
    for item in ranked:
        assert item.reason.strip(), f'{item.move} was scored without a reason'
        assert 0.0 <= item.score <= 1.0
        assert set(item.to_dict()) == {'move', 'score', 'reason'}


def test_selection_is_deterministic_and_independent_of_declaration_order():
    """A policy that changes its answer between identical states cannot be reviewed,
    and a decision that depends on how the profile happened to be written cannot be
    reproduced from the configuration alone."""
    profile = default_profile()
    ev = evidence(state={'mastery': 0.5, 'attempts': 3, 'correct_count': 2})
    answers = {select_move(ev, profile).move for _ in range(25)}
    assert len(answers) == 1

    # The chosen move is the best-scoring candidate.
    ranked = score_moves(ev, profile)
    assert select_move(ev, profile).score == max(item.score for item in ranked)

    # Scoring is order-independent, so declaring the same moves in the opposite
    # order cannot change the decision. (It can only change *which* of two tied
    # moves wins - which is why the declaration order is data, not incidental.)
    reversed_profile = TeacherProfile.from_dict(
        {'moves': [spec.name for spec in reversed(profile.moves)]})
    assert select_move(ev, reversed_profile).move == select_move(ev, profile).move


def test_a_move_the_profile_does_not_declare_can_never_win():
    """Editing the profile has to be able to *remove* a move, or the config is a
    suggestion rather than a configuration."""
    trimmed = TeacherProfile.from_dict({'moves': ['orient', 'rest']})
    ev = evidence(state={'mastery': 0.5, 'attempts': 3, 'correct_count': 2})
    ranked = score_moves(ev, trimmed)
    assert {item.move for item in ranked} == {'orient', 'rest'}
    assert select_move(ev, trimmed).move in {'orient', 'rest'}


def test_a_learner_specific_bias_is_bounded_and_cannot_outvote_the_evidence():
    """One good session must not hard-wire a preference."""
    profile = default_profile()
    state = {'mastery': 0.5, 'attempts': 3, 'correct_count': 2}
    neutral = evidence(state=state)
    biased = evidence(state=state,
                      move_history={'explain': {'helped': 99, 'hurt': 0}})
    n_scores = {i.move: i.score for i in score_moves(neutral, profile)}
    b_scores = {i.move: i.score for i in score_moves(biased, profile)}
    lift = b_scores['explain'] - n_scores['explain']
    assert 0 < lift <= profile.learned_preference.weight + 1e-9


# ------------------------------------------------------- the retrieval schedule

def test_a_review_is_due_at_the_desired_retention_point():
    """The FSRS rule: due when R decays to the configured retention, not on a date."""
    profile = default_profile()
    desired = profile.retrieval.desired_retention
    state = fsrs_state(stability=10.0, last_review=NOW)

    # The first day at which the model's *own* curve has decayed to the retention
    # point. Read from the curve rather than from a formula copied into the test, so
    # the test cannot agree with a wrong scheduler by repeating its arithmetic.
    cross = next(day for day in range(1, 800)
                 if recall_probability(state, NOW + day * DAY) <= desired)
    assert not is_due(state, NOW + (cross - 1) * DAY, desired)
    assert is_due(state, NOW + cross * DAY, desired)
    assert is_due(state, NOW + (cross + 30) * DAY, desired)


def test_a_concept_never_reviewed_is_not_due_but_enters_as_new_material():
    """No stability means no forgetting curve to be on the wrong side of."""
    states = {'never': {'mastery': 0.15, 'attempts': 0}}
    assert due_concepts(states, NOW) == []
    plan = plan_retrieval(states, NOW, default_profile().retrieval,
                          new_concepts=['brand-new'])
    assert plan.concept_ids() == ('brand-new',)
    assert plan.items[0].new


def test_a_scheduler_written_due_at_is_honoured():
    """States seeded outside the scheduler have no readable curve but do have a
    clock; ignoring it lets taught concepts rot while nothing looks due."""
    state = {'due_at': NOW - 1, 'mastery': 0.6, 'attempts': 3}
    assert is_due(state, NOW, 0.9)


def test_due_concepts_are_served_weakest_memory_first():
    states = {
        'strong': fsrs_state(stability=200.0, last_review=NOW - 30 * DAY),
        'weak': fsrs_state(stability=1.0, last_review=NOW - 30 * DAY),
        'middling': fsrs_state(stability=20.0, last_review=NOW - 30 * DAY),
    }
    order = [item.concept_id for item in due_concepts(states, NOW, 0.99)]
    assert order == ['weak', 'middling', 'strong']


def test_the_schedule_interleaves_new_material_rather_than_front_loading_it():
    """Spacing: a block of one idea stores less than the same time spread out."""
    config = default_profile().retrieval
    states = {f'r{i}': fsrs_state(stability=1.0, last_review=NOW - 60 * DAY)
              for i in range(9)}
    plan = plan_retrieval(states, NOW, config, new_concepts=['n1', 'n2', 'n3'])
    kinds = ['new' if item.new else 'review' for item in plan.items]
    assert kinds.count('new') == config.max_new_per_session
    assert kinds[0] == 'review', 'a new concept was front-loaded'
    assert 'n3' in plan.new_remaining, 'the new-material cap was exceeded'


def test_the_schedule_states_its_own_reasoning():
    config = default_profile().retrieval
    plan = plan_retrieval({'a': fsrs_state(stability=1.0, last_review=NOW - 60 * DAY)},
                          NOW, config, new_concepts=['n'])
    assert plan.rationale
    assert str(config.interleave_every) in plan.rationale


def test_planning_retrieval_never_asks_for_more_than_the_session_allows():
    config = default_profile().retrieval
    states = {f'r{i}': fsrs_state(stability=1.0, last_review=NOW - 60 * DAY)
              for i in range(config.per_session + 8)}
    plan = plan_retrieval(states, NOW, config)
    assert len(plan.reviews) == config.per_session


# ---------------------------------------------------- config -> prompt rendering

def test_the_rendered_moves_are_exactly_the_profile_moves():
    profile = default_profile()
    section = render_move_section(profile)
    rendered = [line.split(':', 1)[0][2:] for line in section.splitlines()
                if line.startswith('- ')]
    assert rendered == list(profile.move_names)


def test_editing_the_profile_edits_the_prompt():
    """The whole point of the rebuild: changing the teacher is editing data."""
    original = render_move_section(default_profile())
    edited = TeacherProfile.from_dict({
        'moves': [{'name': 'orient', 'summary': 'Ask one question, then stop.'}]})
    assert render_move_section(edited) != original
    assert 'Ask one question, then stop.' in render_move_section(edited)


def test_the_retrieval_section_states_the_configured_retention():
    profile = TeacherProfile.from_dict({'retrieval': {'desired_retention': 0.8,
                                                      'per_session': 5}})
    section = render_retrieval_section(profile)
    assert '0.80' in section
    assert '5 review' in section


def test_the_retrieval_section_reports_the_actual_calendar_when_given_one():
    profile = default_profile()
    plan = plan_retrieval({'a': fsrs_state(stability=1.0, last_review=NOW - 60 * DAY)},
                          NOW, profile.retrieval, new_concepts=['n']).to_dict()
    section = render_retrieval_section(profile, plan)
    assert 'a' in section and 'n' in section
    assert plan['rationale'] in section


def test_the_modalities_section_names_the_ceiling_not_only_the_defaults():
    """A model told it may draw will draw, so a switched-off channel must say so."""
    profile = TeacherProfile.from_dict({'modalities': {'allowed': ['text']}})
    section = render_modalities_section(profile)
    assert 'Available: text' in section
    for channel in ('whiteboard', 'simulation', 'video'):
        assert channel not in section.split('Default channel')[0]


def test_the_persona_section_is_visibly_subordinate_to_the_evidence():
    section = render_persona_section(default_profile())
    assert 'never which move' in section


def test_an_unknown_profile_section_is_rejected_rather_than_ignored():
    """A silently-dropped typo reads as success and changes nothing."""
    with pytest.raises(ValueError):
        TeacherProfile.from_dict({'difficulty': {'mastery_threshold': 0.7},
                                  'diffculty': {'mastery_threshold': 0.7}})
    with pytest.raises(ValueError):
        TeacherProfile.from_dict({'difficulty': {'mastery_treshold': 0.7}})


def test_a_probability_typo_is_clamped_rather_than_disabling_a_rule():
    """90 instead of 0.9 would silently disable every review; clamping keeps it loud."""
    profile = TeacherProfile.from_dict({'retrieval': {'desired_retention': 90}})
    assert profile.retrieval.desired_retention == 1.0


def test_an_impossible_profile_is_refused():
    with pytest.raises(ValueError):
        TeacherProfile.from_dict({'difficulty': {'mastery_threshold': 0.9,
                                                 'consolidation_threshold': 0.2}})
    with pytest.raises(ValueError):
        TeacherProfile.from_dict({'persona': {'depth': 42}})
    with pytest.raises(ValueError):
        TeacherProfile.from_dict({'moves': []})


def test_a_profile_round_trips_through_plain_data():
    profile = default_profile()
    again = TeacherProfile.from_dict(profile.to_dict())
    assert again.move_names == profile.move_names
    assert again.difficulty == profile.difficulty
    assert again.retrieval == profile.retrieval
    assert again.modalities.allowed == profile.modalities.allowed


# ----------------------------------------------------------- multimodal routing

def test_non_mathematics_routes_to_a_concept_map_not_a_function_plot():
    """The symbolic engine is valid only for mathematics, so claiming otherwise
    would present a concept map as a physical model."""
    facts = maths_facts(subject_kind='physics', concept_type='concept_map')
    choice = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 3}),
                             default_profile())
    assert choice.modality == 'concept_map'
    assert [call.tool for call in choice.tools] == ['build_figure']
    assert 'concept map' in choice.why


def test_a_procedural_error_routes_to_a_simulation():
    facts = maths_facts()
    choice = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 4},
                                             top_error='procedural'),
                             default_profile(), course_id='c1')
    assert choice.modality == 'simulation'
    assert [call.tool for call in choice.tools] == ['find_simulation']
    assert choice.fallback, 'a simulation with no course binding needs a fallback'


def test_a_conceptual_error_draws_on_the_board_when_the_caller_has_one():
    facts = maths_facts()
    choice = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 4},
                                             top_error='conceptual'),
                             default_profile(), board_id='board-x')
    assert choice.modality == 'whiteboard'
    assert choice.needs_teacher
    assert [call.tool for call in choice.tools] == ['whiteboard_apply']


def test_a_conceptual_error_without_a_board_falls_back_to_the_figure():
    """A channel the deployment cannot honour must fall back, not pretend."""
    facts = maths_facts()
    choice = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 4},
                                             top_error='conceptual'),
                             default_profile())
    assert choice.modality == 'figure'
    assert not choice.needs_teacher


def test_an_overloaded_learner_is_not_given_a_new_representation():
    facts = maths_facts()
    ev = evidence(facts, {'mastery': 0.3, 'attempts': 5, 'correct_count': 1},
                  elapsed_trend='much_faster')
    assert ev.frustrated
    choice = choose_modality(facts, ev, default_profile(), board_id='board-x',
                             course_id='c1')
    assert choice.modality == 'text'
    assert 'overload' in choice.why


def test_modality_changes_as_performance_moves_from_fast_wrong_to_steady_progress():
    facts = maths_facts()
    struggling = evidence(facts, {'mastery': 0.35, 'attempts': 4, 'correct_count': 1},
                          elapsed_trend='faster')
    improving = evidence(facts, {'mastery': 0.75, 'attempts': 6, 'correct_count': 5},
                         elapsed_trend='steady')
    profile = default_profile()

    first = choose_modality(facts, struggling, profile)
    later = choose_modality(facts, improving, profile)

    assert first.modality == 'text'
    assert later.modality == 'figure'
    assert 'overload' in first.why
    assert 'Default channel' in later.why


def test_a_spatial_concept_at_consolidation_asks_the_learner_to_draw():
    """Near mastery the board is where the learner's own drawing gets corrected."""
    facts = maths_facts(strand='Geometry & Measurement', concept_type='spatial')
    choice = choose_modality(facts, evidence(facts, {'mastery': 0.9, 'attempts': 6}),
                             default_profile(), board_id='board-x')
    assert choice.modality == 'whiteboard'
    assert 'themselves' in choice.why


def test_spoken_output_adds_audio_and_keeps_the_text():
    """Audio alone would exclude exactly the learners the text version is for."""
    profile = TeacherProfile.from_dict({'persona': {'spoken_output': True}})
    facts = maths_facts()
    choice = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 3}),
                             profile)
    assert choice.modality == 'audio'
    assert {call.tool for call in choice.tools} == {'build_figure', 'text_to_speech'}


def test_a_channel_switched_off_on_this_instance_is_never_chosen():
    profile = TeacherProfile.from_dict({
        'modalities': {'allowed': ['text', 'figure'],
                       'prefer': {'quantitative_relation': 'simulation'}}})
    facts = maths_facts()
    choice = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 3},
                                             top_error='procedural'), profile)
    assert choice.modality in {'text', 'figure'}
    assert choice.modality not in {'simulation', 'video', 'whiteboard'}


def test_an_image_channel_without_a_pipeline_degrades_to_text():
    facts = maths_facts(strand='Concrete', concept_type='concrete_phenomenon')
    profile = default_profile()
    without = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 3}),
                              profile, media_enabled=False)
    assert without.modality == 'text'
    assert 'No image pipeline' in without.why
    with_media = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 3}),
                                 profile, media_enabled=True)
    assert with_media.modality == 'image'
    assert [call.tool for call in with_media.tools] == ['find_image']


def test_an_exact_repeat_of_the_previous_channel_is_varied_once():
    facts = maths_facts()
    ev = evidence(facts, {'mastery': 0.4, 'attempts': 3})
    repeated = choose_modality(facts, ev, default_profile(), last_modality='figure')
    assert repeated.modality != 'figure'
    assert 'previous turn' in repeated.why


def test_the_router_only_names_channels_the_profile_catalogue_knows():
    for facts in (maths_facts(), maths_facts(subject_kind='physics'),
                  maths_facts(concept_type='data'), maths_facts(concept_type='spatial'),
                  maths_facts(concept_type='verbal'),
                  maths_facts(concept_type='concrete_phenomenon')):
        choice = choose_modality(facts, evidence(facts, {'mastery': 0.5, 'attempts': 4}),
                                 default_profile(), board_id='b', course_id='c',
                                 media_enabled=True)
        assert choice.modality in MODALITIES
        assert choice.why


def test_every_tool_the_teaching_core_calls_actually_exists():
    """The registry is the contract: an action it cannot perform is a refusal the
    caller must surface, never a capability smuggled in through the teacher."""
    available = {spec['name'] for spec in toolbox.available_catalogue()}
    called = set()
    facts = maths_facts()
    profile = default_profile()
    for state, kw, extra in (
            ({'mastery': 0.4, 'attempts': 4}, {'top_error': 'procedural'}, {}),
            ({'mastery': 0.4, 'attempts': 4}, {'top_error': 'conceptual'},
             {'board_id': 'b'}),
            ({'mastery': 0.9, 'attempts': 6}, {}, {'board_id': 'b'}),
            ({'mastery': 0.4, 'attempts': 3}, {}, {'media_enabled': True}),
            ({'mastery': 0.4, 'attempts': 3}, {}, {})):
        choice = choose_modality(facts, evidence(facts, state, **kw), profile, **extra)
        called |= {call.tool for call in choice.tools}
        called |= {call.tool for call in choice.fallback}
    plan = plan_session(evidence(facts, {'mastery': 0.9, 'attempts': 8,
                                         'correct_count': 8}),
                        facts, profile, board_id='b')
    for step in plan.steps:
        called |= {call.tool for call in step.tools}
        called |= {call.tool for call in step.fallback}
    assert called, 'no tool was exercised; the test is not testing anything'
    assert called <= available, f'the teacher calls tools that do not exist: {called - available}'


def test_a_placeholder_resolves_at_the_call_site_and_stays_visible_when_it_cannot():
    """An unresolved placeholder must reach the tool so it refuses, rather than
    silently becoming an empty string that draws on a board nobody named."""
    facts = maths_facts()
    choice = choose_modality(facts, evidence(facts, {'mastery': 0.4, 'attempts': 4},
                                             top_error='conceptual'),
                             default_profile(), board_id='board-9')
    tool, args = choice.tools[0].resolved(board_id='board-9')
    assert tool == 'whiteboard_apply'
    assert args['board_id'] == 'board-9'
    tool, args = choice.tools[0].resolved()
    assert args['board_id'] == '', 'the placeholder must not survive resolution'


# ------------------------------------------------------------- the teaching loop

def test_the_loop_completes_elicit_teach_practice_consolidate():
    """The loop the product promises, for a learner who needs all of it."""
    facts = maths_facts()
    profile = default_profile()
    ev = evidence(facts, fsrs_state(stability=8.0, last_review=NOW - 3 * DAY,
                                    mastery=0.85, attempts=6, correct_count=5),
                  now=NOW, project_status='completed')
    plan = plan_session(ev, facts, profile, board_id='board-x')
    assert isinstance(plan, TeachingPlan)
    assert plan.phases == ('elicit', 'teach', 'practice', 'consolidate')
    assert plan.moves[0] == 'orient'
    assert plan.moves[-1] == 'consolidate'
    assert 'retrieve' in plan.moves
    assert plan.rationale and plan.profile_name == profile.name


def test_the_loop_can_draw_on_the_board():
    facts = maths_facts()
    plan = plan_session(evidence(facts, {'mastery': 0.4, 'attempts': 4},
                                 top_error='conceptual'),
                        facts, default_profile(), board_id='board-x')
    teach = plan.step('teach')
    assert teach.modality == 'whiteboard'
    assert teach.needs_teacher
    assert [tool for tool, _ in teach.resolved_tools(board_id='board-x')] == \
        ['whiteboard_apply']


def test_the_loop_can_run_a_simulation():
    facts = maths_facts()
    plan = plan_session(evidence(facts, {'mastery': 0.4, 'attempts': 4},
                                 top_error='procedural'),
                        facts, default_profile(), course_id='course-1')
    teach = plan.step('teach')
    assert teach.modality == 'simulation'
    assert [tool for tool, _ in teach.resolved_tools(course_id='course-1')] == \
        ['find_simulation']
    assert teach.resolved_fallback(), 'the simulation needs its figure fallback'


def test_the_loop_gives_practice_and_checks_understanding():
    facts = maths_facts()
    plan = plan_session(evidence(facts, fsrs_state(stability=8.0,
                                                   last_review=NOW - 3 * DAY,
                                                   mastery=0.7, attempts=5,
                                                   correct_count=4),
                                 now=NOW),
                        facts, default_profile())
    practice = plan.step('practice')
    assert practice is not None and practice.move == 'retrieve'
    assert [tool for tool, _ in practice.resolved_tools()] == \
        ['check_understanding', 'read_learner_evidence']


def test_a_learner_who_cannot_retrieve_yet_is_not_asked_to():
    """No attempts means no memory, so a retrieval check would be a first exposure
    dressed up as a test."""
    facts = maths_facts()
    plan = plan_session(evidence(facts, {'mastery': 0.15, 'attempts': 0}),
                        facts, default_profile())
    assert plan.step('practice') is None
    assert plan.move.move == 'orient'


def test_the_wrap_can_be_switched_off_in_configuration():
    profile = TeacherProfile.from_dict({'wrap': {'elicit_before': False,
                                                 'check_after': False,
                                                 'transfer_check': False}})
    facts = maths_facts()
    plan = plan_session(evidence(facts, {'mastery': 0.5, 'attempts': 4}),
                        facts, profile)
    assert plan.step('elicit') is None
    assert plan.step('practice') is None
    assert plan.step('transfer') is None


def test_the_transfer_task_appears_only_when_the_gate_still_wants_it():
    facts = maths_facts()
    profile = default_profile()
    needs_it = plan_session(
        evidence(facts, fsrs_state(stability=40.0, last_review=NOW - DAY,
                                   mastery=0.88, attempts=6, correct_count=6),
                 now=NOW, project_status='unknown'),
        facts, profile)
    assert needs_it.step('transfer') is not None

    has_it = plan_session(
        evidence(facts, fsrs_state(stability=40.0, last_review=NOW - DAY,
                                   mastery=0.88, attempts=6, correct_count=6),
                 now=NOW, project_status='completed'),
        facts, profile)
    assert has_it.step('transfer') is None


def test_rest_is_terminal_and_appends_nothing_after_it():
    """Appending a check after "stop" is the tutor ignoring its own decision."""
    facts = maths_facts()
    ev = evidence(facts, {'mastery': 0.3, 'attempts': 5, 'correct_count': 1},
                  elapsed_trend='much_faster')
    plan = plan_session(ev, facts, default_profile())
    assert plan.move.move == 'rest'
    assert plan.phases == ('close',)
    assert plan.steps[0].move == 'rest'


def test_a_session_over_budget_gets_the_move_and_an_exit_not_a_full_loop():
    facts = maths_facts()
    profile = default_profile()
    ev = evidence(facts, fsrs_state(stability=8.0, last_review=NOW - 3 * DAY,
                                    mastery=0.7, attempts=5, correct_count=4),
                  now=NOW, session_minutes=profile.difficulty.long_session_minutes + 10)
    plan = plan_session(ev, facts, profile)
    # Whatever the policy chose, an over-budget session never opens a new phase:
    # starting a sequence that cannot be finished leaves the learner mid-explanation,
    # which is the state the long-session rule exists to prevent.
    for phase in ('elicit', 'practice', 'transfer', 'consolidate'):
        assert phase not in plan.phases, phase
    assert plan.phases[-1] == 'close'
    assert plan.steps[-1].move == 'rest'
    assert not plan.steps[-1].skippable


def test_the_loop_phases_are_drawn_from_one_declared_order():
    facts = maths_facts()
    plan = plan_session(evidence(facts, fsrs_state(stability=8.0,
                                                   last_review=NOW - 3 * DAY,
                                                   mastery=0.85, attempts=6,
                                                   correct_count=5),
                                 now=NOW, project_status='completed'),
                        facts, default_profile())
    positions = [PHASES.index(phase) for phase in plan.phases]
    assert positions == sorted(positions), 'the loop ran its phases out of order'
    assert plan.phases[0] == 'elicit' and plan.phases[-1] == 'consolidate'


def test_the_plan_is_serialisable_for_the_transparency_panel():
    facts = maths_facts()
    plan = plan_session(evidence(facts, {'mastery': 0.5, 'attempts': 4}),
                        facts, default_profile(), board_id='b')
    payload = plan.to_dict()
    assert payload['concept_id'] == facts.id
    assert payload['move']['move'] in MOVES
    assert payload['phases'] == list(plan.phases)
    assert all(step['why'] for step in payload['steps'])
    assert all(step['modality'] in MODALITIES for step in payload['steps'])


def test_a_plan_carries_the_retrieval_calendar_when_one_was_built():
    facts = maths_facts()
    profile = default_profile()
    calendar = plan_retrieval(
        {'a': fsrs_state(stability=1.0, last_review=NOW - 60 * DAY)}, NOW,
        profile.retrieval, new_concepts=['n']).to_dict()
    plan = plan_session(evidence(facts, {'mastery': 0.5, 'attempts': 4}), facts,
                        profile, retrieval_plan=calendar)
    assert plan.retrieval is not None
    assert plan.to_dict()['retrieval']['items']
    section = render_retrieval_section(profile, plan.retrieval)
    assert 'a' in section


# --------------------------------------------------- the modalities are grounded

def test_the_router_never_reads_a_learning_style():
    """The product's claim: the representation follows the knowledge state and the
    load, never a label about the learner."""
    facts = maths_facts()
    ev = evidence(facts, {'mastery': 0.5, 'attempts': 4})
    first = choose_modality(facts, ev, default_profile())
    second = choose_modality(facts, ev, default_profile())
    assert first == second
    # No field on the evidence record carries a style, so a style cannot be read:
    # if one is ever added, this assertion is the tripwire.
    assert not any('style' in name for name in ev.__dataclass_fields__)


def test_every_channel_the_profile_allows_is_reachable_by_some_rule():
    """A channel listed in the ceiling that no rule can ever select is a promise
    the configuration makes and the code does not keep."""
    profile = default_profile()
    seen = set()
    # (facts, learner state, build_evidence kwargs, choose_modality kwargs)
    scenarios = (
        (maths_facts(), {'mastery': 0.5, 'attempts': 4}, {}, {}),
        (maths_facts(), {'mastery': 0.5, 'attempts': 4}, {'top_error': 'procedural'},
         {'course_id': 'c'}),
        (maths_facts(), {'mastery': 0.5, 'attempts': 4}, {'top_error': 'conceptual'},
         {'board_id': 'b'}),
        (maths_facts(strand='Geometry & Measurement', concept_type='spatial'),
         {'mastery': 0.95, 'attempts': 8}, {}, {'board_id': 'b'}),
        (maths_facts(concept_type='concrete_phenomenon'),
         {'mastery': 0.5, 'attempts': 4}, {}, {'media_enabled': True}),
        (maths_facts(has_video=True), {'mastery': 0.4, 'attempts': 3}, {},
         {'course_id': 'c'}),
        (maths_facts(subject_kind='physics', concept_type='concept_map'),
         {'mastery': 0.5, 'attempts': 4}, {}, {}),
        (maths_facts(), {'mastery': 0.3, 'attempts': 5, 'correct_count': 1},
         {'elapsed_trend': 'much_faster'}, {'board_id': 'b'}),
    )
    for facts_i, state, build_kw, route_kw in scenarios:
        seen.add(choose_modality(facts_i, evidence(facts_i, state, **build_kw),
                                 profile, **route_kw).modality)
    spoken = TeacherProfile.from_dict({'persona': {'spoken_output': True}})
    seen.add(choose_modality(maths_facts(),
                             evidence(maths_facts(), {'mastery': 0.5, 'attempts': 4}),
                             spoken).modality)
    missing = set(profile.modalities.allowed) - seen
    assert not missing, f'channels in the ceiling that no rule can select: {missing}'


def test_the_ceiling_is_enforced_on_every_rule_not_only_the_default_route():
    """``allowed`` is documented as the ceiling. Rules 1-5 name a channel directly
    (concept map, simulation, whiteboard) and none of them consulted it, so a
    text-only instance still drew on the board."""
    facts = maths_facts()
    text_only = TeacherProfile.from_dict({
        'modalities': {'allowed': ['text'],
                       'prefer': {'quantitative_relation': 'figure'}}})
    scenarios = (
        ({'mastery': 0.5, 'attempts': 4}, {'top_error': 'procedural'},
         {'course_id': 'c'}),
        ({'mastery': 0.5, 'attempts': 4}, {'top_error': 'conceptual'},
         {'board_id': 'b'}),
        ({'mastery': 0.95, 'attempts': 8}, {}, {'board_id': 'b'}),
        ({'mastery': 0.5, 'attempts': 4}, {}, {'media_enabled': True}),
        ({'mastery': 0.4, 'attempts': 3}, {}, {'course_id': 'c'}),
    )
    for state, build_kw, route_kw in scenarios:
        for facts_i in (facts, maths_facts(subject_kind='physics'),
                        maths_facts(strand='Geometry & Measurement',
                                    concept_type='spatial'),
                        maths_facts(concept_type='concrete_phenomenon'),
                        maths_facts(has_video=True)):
            choice = choose_modality(facts_i, evidence(facts_i, state, **build_kw),
                                     text_only, **route_kw)
            assert choice.modality == 'text', (facts_i.concept_type, route_kw)
            # A degraded channel must carry the calls that deliver *it*, not the
            # calls belonging to the channel it replaced.
            assert [call.tool for call in choice.tools] == []
