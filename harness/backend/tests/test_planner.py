"""The study plan: how a stated goal becomes a session, and how the pace is decided.

Two failures are pinned here, because both were real and both were quiet.

* **Zero evidence is not weakness.** Treating an unmeasured concept as a gap marked every
  non-leaf concept in a fresh course as a "prerequisite gap" and scheduled those first -
  wrong, and discouraging on the first day.
* **Two id namespaces must be reconciled once.** An authored lesson is keyed ``fractions``
  and teaches the node ``fraction_equivalence``. Handing the planner lesson ids made it
  find no node for any authored concept and return a perfectly well-formed empty plan.

The rest of the file pins the properties the plan promises: determinism, an honest pace
derived from a stated divisor, and progress measured over what the course actually offers.
"""

from __future__ import annotations

import time

import pytest

from app import courses, planner
from app.curriculum import LESSON_TARGETS, course_concepts

NOW = time.time()


def node_keyed(course_id):
    """The course's concepts keyed by graph node id, exactly as the API hands them over."""
    graph = courses.graph_for(course_id)
    out = {}
    for concept_id, entry in course_concepts(course_id).items():
        node_id = entry.get('graph_id') or concept_id
        if node_id in graph.nodes:
            out[node_id] = {**entry, 'concept_id': node_id, 'lesson_id': concept_id}
    return out


def build(course_id, states=None, **kwargs):
    graph = courses.graph_for(course_id)
    spec = courses.course(course_id)
    return planner.plan(graph, node_keyed(course_id), states or {},
                        subject=spec.subject, course_title=spec.title, course_id=course_id,
                        now=NOW, **kwargs)


def strong(mastery=0.95, attempts=6, due_at=None):
    return {'mastery': mastery, 'attempts': attempts,
            'due_at': due_at if due_at is not None else NOW + 10 ** 6}


def weak(mastery=0.2, attempts=4):
    return {'mastery': mastery, 'attempts': attempts, 'due_at': NOW + 10 ** 6}


# ------------------------------------------------------------------ pace


def test_pace_is_arithmetic_from_the_stated_budget():
    small, large = planner.pacing(10), planner.pacing(60)
    assert small['daily_minutes'] == 10 and large['daily_minutes'] == 60
    assert small['items_per_day'] < large['items_per_day']
    assert small['concepts_per_day'] >= 1 and large['concepts_per_day'] > small['concepts_per_day']
    assert small['concepts_per_week'] == small['concepts_per_day'] * planner.SESSIONS_PER_WEEK
    # The divisor is stated so the learner can disagree with it.
    assert 'practice share' in small['arithmetic'] and 's per item' in small['arithmetic']


def test_pace_has_a_floor_and_never_divides_by_zero():
    for minutes in (0, -5, 1, 5):
        pace = planner.pacing(minutes)
        assert pace['daily_minutes'] >= 5
        assert pace['items_per_day'] >= 3
        assert pace['concepts_per_day'] >= 1


def test_textbook_pace_slows_or_advances_from_course_performance_without_changing_budget():
    concepts = {'a': {}, 'b': {}, 'c': {}, 'd': {}}
    struggling = planner.pacing(
        20, {'a': {'attempts': 4, 'correct_count': 1}, 'other-course': {
            'attempts': 20, 'correct_count': 20}}, concept_ids=concepts)
    baseline = planner.pacing(20, {}, concept_ids=concepts)
    progressing = planner.pacing(
        20, {'a': {'attempts': 4, 'correct_count': 4}}, concept_ids=concepts)

    assert struggling['daily_minutes'] == baseline['daily_minutes'] == progressing['daily_minutes'] == 20
    assert struggling['performance_adjustment'] == 'slower'
    assert struggling['concepts_per_day'] < baseline['concepts_per_day']
    assert progressing['performance_adjustment'] == 'faster'
    assert progressing['concepts_per_day'] > baseline['concepts_per_day']
    assert struggling['course_accuracy'] == 0.25
    assert struggling['performance_attempts'] == 4, 'unoffered concepts must not affect pace'
    assert 'reading' in struggling['adjustment_reason']
    assert 'time budget' in progressing['adjustment_reason']


def test_textbook_pace_does_not_react_to_insufficient_or_middle_band_evidence():
    baseline = planner.pacing(20, {}, concept_ids=['a'])
    too_few = planner.pacing(20, {'a': {'attempts': 3, 'correct_count': 0}}, concept_ids=['a'])
    middle = planner.pacing(20, {'a': {'attempts': 4, 'correct_count': 3}}, concept_ids=['a'])
    assert too_few['concepts_per_day'] == baseline['concepts_per_day']
    assert middle['concepts_per_day'] == baseline['concepts_per_day']
    assert too_few['performance_adjustment'] == middle['performance_adjustment'] == 'baseline'


def test_live_study_plan_uses_performance_adjusted_textbook_pace():
    concepts = node_keyed('physics')
    graph = courses.graph_for('physics')
    first = next(iter(concepts))
    neutral = planner.plan(graph, concepts, {}, course_id='physics', daily_minutes=30, now=NOW)
    struggling = planner.plan(
        graph, concepts, {first: {'mastery': 0.3, 'attempts': 4, 'correct_count': 1}},
        course_id='physics', daily_minutes=30, now=NOW)
    progressing = planner.plan(
        graph, concepts, {first: {'mastery': 0.95, 'attempts': 4, 'correct_count': 4,
                                  'due_at': NOW + 10 ** 6}},
        course_id='physics', daily_minutes=30, now=NOW)

    assert struggling['pace']['concepts_per_day'] < neutral['pace']['concepts_per_day']
    assert progressing['pace']['concepts_per_day'] > neutral['pace']['concepts_per_day']
    assert len(struggling['today']['concepts']) <= struggling['pace']['concepts_per_day']
    assert struggling['today']['items'] < neutral['today']['items']


# ------------------------------------------------------------------ classification


@pytest.mark.parametrize('spec', courses.COURSES, ids=[c.id for c in courses.COURSES])
def test_a_fresh_learner_is_never_told_they_have_a_gap(spec):
    """No attempts means unmeasured, not weak. Everything should be next_in_order."""
    graph = courses.graph_for(spec.id)
    concepts = node_keyed(spec.id)
    reasons = {planner.classify(graph, concepts, {}, node_id, NOW) for node_id in concepts}
    assert reasons == {'next_in_order'}, f'{spec.id} classified a fresh learner as {reasons}'


def test_an_unmeasured_prerequisite_does_not_block_its_dependants():
    """Otherwise a brand-new learner is blocked on everything below the roots."""
    graph = courses.graph_for('physics')
    concepts = node_keyed('physics')
    child = next(n for n in graph.nodes if graph.parents(n) and n in concepts)
    assert planner.classify(graph, concepts, {}, child, NOW) == 'next_in_order'


def test_a_measured_weak_prerequisite_does_block_its_dependants():
    graph = courses.graph_for('physics')
    concepts = node_keyed('physics')
    parent = next(n for n in graph.nodes
                  if n in concepts and any(c in concepts for c in graph.children(n)))
    child = next(c for c in graph.children(parent) if c in concepts)
    states = {parent: weak()}
    assert planner.classify(graph, concepts, states, child, NOW) == 'blocked'
    assert planner.classify(graph, concepts, states, parent, NOW) == 'prerequisite_gap'


def test_a_weak_leaf_is_a_diagnostic_gap_not_a_blocker():
    """A concept nothing depends on cannot be blocking anything."""
    graph = courses.graph_for('physics')
    concepts = node_keyed('physics')
    leaf = next(n for n in concepts
                if not any(c in concepts for c in graph.children(n)))
    assert planner.classify(graph, concepts, {leaf: weak()}, leaf, NOW) == 'diagnostic_gap'


def test_secure_requires_evidence_not_only_a_high_estimate():
    """One lucky answer must not read as mastery."""
    graph = courses.graph_for('physics')
    concepts = node_keyed('physics')
    node_id = next(iter(concepts))
    assert not planner.is_secure({node_id: {'mastery': 0.95, 'attempts': 1}}, node_id)
    assert planner.is_secure({node_id: {'mastery': 0.95, 'attempts': planner.MIN_EVIDENCE}}, node_id)
    assert not planner.is_secure({node_id: {'mastery': 0.5, 'attempts': 20}}, node_id)


def test_due_review_outranks_everything_else():
    graph = courses.graph_for('physics')
    concepts = node_keyed('physics')
    node_id = next(iter(concepts))
    states = {node_id: {'mastery': 0.7, 'attempts': 4, 'due_at': NOW - 60}}
    assert planner.classify(graph, concepts, states, node_id, NOW) == 'review_due'
    queue = planner.order_concepts(graph, concepts, states, NOW)
    assert queue[0]['concept_id'] == node_id


# ------------------------------------------------------------------ the queue


@pytest.mark.parametrize('spec', courses.COURSES, ids=[c.id for c in courses.COURSES])
def test_the_queue_is_never_empty_for_a_course_with_content(spec):
    """The regression that mattered: an authored course produced an empty plan."""
    graph = courses.graph_for(spec.id)
    concepts = node_keyed(spec.id)
    queue = planner.order_concepts(graph, concepts, {}, NOW)
    assert len(queue) == len(concepts), f'{spec.id} queued {len(queue)} of {len(concepts)}'
    assert {row['concept_id'] for row in queue} == set(concepts)


def test_the_queue_is_deterministic():
    """Two runs with the same evidence must produce the same plan, or it is not reviewable."""
    graph = courses.graph_for('physics')
    concepts = node_keyed('physics')
    first = planner.order_concepts(graph, concepts, {}, NOW)
    second = planner.order_concepts(graph, concepts, {}, NOW)
    assert [r['concept_id'] for r in first] == [r['concept_id'] for r in second]


def test_the_queue_opens_on_a_load_bearing_concept():
    """Shallower first, then the concept that unlocks the most."""
    graph = courses.graph_for('physics')
    concepts = node_keyed('physics')
    queue = planner.order_concepts(graph, concepts, {}, NOW)
    assert queue[0]['depth'] == min(row['depth'] for row in queue)
    at_min_depth = [row for row in queue if row['depth'] == queue[0]['depth']]
    assert queue[0]['unlocks'] == max(row['unlocks'] for row in at_min_depth)


def test_a_prerequisite_is_never_scheduled_after_its_dependant():
    """The order must respect the graph, or the plan teaches in the wrong sequence."""
    graph = courses.graph_for('physics')
    concepts = node_keyed('physics')
    queue = planner.order_concepts(graph, concepts, {}, NOW)
    position = {row['concept_id']: index for index, row in enumerate(queue)}
    for concept_id, index in position.items():
        for parent in graph.parents(concept_id):
            if parent in position:
                assert position[parent] < index, f'{parent} is scheduled after {concept_id}'


# ------------------------------------------------------------------ the plan


def test_progress_counts_what_the_course_offers():
    """A graph is not a course: 164 nodes, 15 of which the mathematics course can teach."""
    plan = build('integrated_math_1')
    offered = plan['progress']['concepts_offered']
    assert offered == len(node_keyed('integrated_math_1'))
    assert plan['progress']['graph_nodes'] == len(courses.graph_for('integrated_math_1').nodes)
    assert offered < plan['progress']['graph_nodes']
    assert plan['progress']['percent_secure'] == 0.0


def test_today_fits_the_stated_budget():
    plan = build('physics', daily_minutes=20)
    pace = plan['pace']
    assert plan['today']['minutes'] == 20
    assert len(plan['today']['concepts']) <= planner.MAX_TODAY
    assert plan['today']['items'] <= pace['items_per_day']
    assert plan['today']['rationale']


def test_mastered_concepts_leave_the_queue_and_move_progress():
    concepts = node_keyed('physics')
    graph = courses.graph_for('physics')
    node_id = next(iter(concepts))
    states = {node_id: strong()}
    plan = planner.plan(graph, concepts, states, course_id='physics', now=NOW)
    assert plan['progress']['secure'] == 1
    assert node_id not in {row['concept_id'] for row in plan['queue']}
    assert all(row['concept_id'] != node_id for row in plan['today']['concepts'])


def test_weeks_remaining_is_a_projection_with_its_basis_stated():
    plan = build('physics', daily_minutes=30)
    weeks = plan['progress']['weeks_remaining_at_current_pace']
    expected = plan['progress']['remaining'] / plan['pace']['concepts_per_week']
    assert weeks == round(expected, 1)
    assert 'not a promise' in plan['progress']['projection_basis']


def test_the_plan_states_what_it_is_not():
    plan = build('physics', goal='Get ready for university physics')
    assert plan['goal']['stated'] == 'Get ready for university physics'
    assert 'not proof of it' in plan['goal']['note']
    honesty = ' '.join(plan['honesty'])
    assert 'not a validated curriculum standard' in honesty
    assert 'not calibrated' in honesty
    assert 'coverage gap' in honesty


def test_the_plan_names_an_empty_goal_rather_than_inventing_one():
    plan = build('physics', goal='')
    assert plan['goal']['stated'] == ''
    assert plan['goal']['operational_target']


def test_milestones_cover_every_unit_that_has_content():
    plan = build('physics')
    assert plan['milestones'], 'a course graph must expose units'
    assert sum(m['concepts'] for m in plan['milestones']) == plan['progress']['concepts_offered']
    for milestone in plan['milestones']:
        assert milestone['secure'] + milestone['remaining'] == milestone['concepts']


def test_coverage_gaps_are_reported_not_scheduled():
    """A prerequisite the course does not teach must be named, never silently queued."""
    graph = courses.graph_for('integrated_math_1')
    concepts = node_keyed('integrated_math_1')
    gaps = {row['concept_id']: row['not_offered_prerequisites']
            for row in planner.order_concepts(graph, concepts, {}, NOW)}
    assert any(gaps.values()), 'the authored course is known to reference nodes it does not teach'
    for concept_id, missing in gaps.items():
        assert concept_id in concepts
        for parent in missing:
            assert parent not in concepts
            assert parent in graph.nodes


def test_a_lesson_id_resolves_to_the_node_it_teaches():
    """The reconciliation that made the authored course's plan non-empty."""
    concepts = node_keyed('integrated_math_1')
    for lesson_id, node_id in LESSON_TARGETS.items():
        assert concepts[node_id]['lesson_id'] == lesson_id
        assert concepts[node_id]['concept_id'] == node_id
