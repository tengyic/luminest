"""Goal-driven study planning.

A learner does not ask "which item is next". They ask "I want to understand physics by
June - what do I actually do today, and am I on track". This module answers that, and it
answers it from evidence the system already holds: the course graph's prerequisite edges,
the learner's own recorded states, the spaced-review schedule, and the session budget the
learner chose.

Three commitments shape it.

1. **The order is derived, not curated.** The queue is built from the graph's real edges
   and the learner's real mastery. There is no hidden difficulty ranking and no editorial
   opinion about what matters - the same inputs always produce the same plan.

2. **The pace is arithmetic, not aspiration.** Minutes a day is a number the learner set.
   Converting it into items and concepts is division, and the divisor is stated so the
   learner can disagree with it.

3. **It says what it cannot know.** Weeks-remaining is a projection from current pace, not
   a promise. Concepts that are genuinely blocked are named as blocked rather than being
   quietly scheduled.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

#: A generated item is budgeted at 75 seconds and an authored one at 60. Answering plus
#: reading the diagnosis costs about a third more than answering alone.
SECONDS_PER_ITEM = 75
FEEDBACK_OVERHEAD = 1.35
#: The share of a session spent on retrieval practice. The rest is reading, figures and
#: consolidation, which the plan budgets for but does not schedule as items.
PRACTICE_SHARE = 0.75
#: Four items cover one concept (``generated_curriculum.VARIANTS``).
ITEMS_PER_CONCEPT = 4

#: A prerequisite at or above this is treated as ready to build on.
READY = 0.6
#: The operational target: mastery at or above this, on at least ``MIN_EVIDENCE`` attempts.
SECURE = 0.85
MIN_EVIDENCE = 3
#: Five study days a week, so a daily budget is not silently multiplied by seven.
SESSIONS_PER_WEEK = 5

#: How many concepts a single session will name before it stops being a plan and starts
#: being a list.
MAX_TODAY = 4

#: The reasons a concept can be at the front of the queue, in the order they are served.
#: Retrieval first because a short session spent on material already met is the highest
#: return; then the gap that is blocking something else; then a plain gap; then new
#: material whose prerequisites are actually ready.
REASON_ORDER = ('review_due', 'prerequisite_gap', 'diagnostic_gap', 'next_in_order')

REASON_TEXT = {
    'review_due': 'Learned earlier and now due for retrieval - the highest-value use of a short session.',
    'prerequisite_gap': 'Something later in the course depends on this and it is not yet secure, so it is blocking you.',
    'diagnostic_gap': 'Already attempted but not yet secure, so it needs a fresh look before moving on.',
    'next_in_order': 'The next idea in prerequisite order whose foundations are ready.',
    'blocked': 'Its prerequisites are not ready yet, so it is listed but not scheduled.',
    'secure': 'Secure enough to leave alone for now.',
}


def pacing(daily_minutes: int, states: Mapping[str, Mapping[str, Any]] | None = None,
           concept_ids=None) -> dict[str, Any]:
    """Turn the chosen time budget and scored performance into a daily learning pace.

    Time remains the learner's ceiling. The number of concepts moves only after enough
    scored evidence exists: a weak course-wide response rate slows new coverage, while a
    consistently strong rate permits one more concept within the same time budget. A cold
    start never gets treated as poor performance.
    """
    minutes = max(5, int(daily_minutes or 20))
    practice_seconds = minutes * 60 * PRACTICE_SHARE
    items_per_day = max(3, int(practice_seconds / (SECONDS_PER_ITEM * FEEDBACK_OVERHEAD)))
    budget_concepts = max(1, round(items_per_day / ITEMS_PER_CONCEPT))
    budget_concepts = min(MAX_TODAY, budget_concepts)

    states = states or {}
    ids = concept_ids if concept_ids is not None else states.keys()
    attempts = correct = 0
    for concept_id in ids:
        state = states.get(concept_id) or {}
        count = max(0, int(state.get('attempts', 0) or 0))
        successes = min(count, max(0, int(state.get('correct_count', 0) or 0)))
        attempts += count
        correct += successes
    accuracy = correct / attempts if attempts else None

    concepts_per_day = budget_concepts
    adjustment = 'baseline'
    if attempts >= 4 and accuracy is not None and accuracy < 0.55:
        concepts_per_day = max(1, math.floor(budget_concepts * 0.5))
        adjustment = 'slower' if concepts_per_day < budget_concepts else 'minimum_pace'
        pace_reason = (f'Course accuracy is {accuracy:.0%} across {attempts} scored attempts; '
                       + ('the plan slows new-concept coverage to leave more room for reading, '
                          'worked steps and review. Your daily time budget is unchanged.'
                          if adjustment == 'slower' else
                          'the plan is already at one new concept, its minimum pace. It keeps '
                          'your chosen time budget and focuses on review instead of slowing '
                          'coverage further.'))
    elif attempts >= 4 and accuracy is not None and accuracy >= 0.85:
        concepts_per_day = min(MAX_TODAY, math.ceil(budget_concepts * 1.25))
        adjustment = 'faster' if concepts_per_day > budget_concepts else 'budget_capped'
        pace_reason = (f'Course accuracy is {accuracy:.0%} across {attempts} scored attempts; '
                       + ('the plan can advance through more concepts within your chosen daily '
                          'time budget.' if adjustment == 'faster' else
                          'the plan is already at its four-concept session cap, so the daily '
                          'time budget remains the limiting factor.'))
    else:
        pace_reason = (f'Pace stays at the time-budget estimate until at least 4 scored '
                       f'attempts are available (currently {attempts}); no performance-based '
                       'speed-up or slow-down is inferred.')

    return {
        'daily_minutes': minutes,
        'items_per_day': items_per_day,
        'concepts_per_day': concepts_per_day,
        'budget_concepts_per_day': budget_concepts,
        'concepts_per_week': concepts_per_day * SESSIONS_PER_WEEK,
        'sessions_per_week': SESSIONS_PER_WEEK,
        'performance_adjustment': adjustment,
        'course_accuracy': None if accuracy is None else round(accuracy, 4),
        'performance_attempts': attempts,
        'adjustment_reason': pace_reason,
        'arithmetic': (f'{minutes} min x 60 x {PRACTICE_SHARE:.0%} practice share = '
                       f'{practice_seconds:.0f}s of items; '
                       f'{SECONDS_PER_ITEM}s per item x {FEEDBACK_OVERHEAD} for answering and '
                       f'reading the diagnosis gives {items_per_day} items, about '
                       f'{budget_concepts} concepts a day before the evidence-based adjustment.'),
        'basis': ('Item seconds, feedback overhead and practice share are project constants, '
                  'not measurements of this learner. Pace adjustments use only this course\'s '
                  'scored attempts; the selected daily minutes are never changed.'),
    }


def _state(states: Mapping[str, Mapping[str, Any]], concept_id: str) -> Mapping[str, Any]:
    return states.get(concept_id) or {}


def _mastery(states, concept_id: str) -> float:
    return float(_state(states, concept_id).get('mastery', 0.0))


def _attempts(states, concept_id: str) -> int:
    return int(_state(states, concept_id).get('attempts', 0))


def is_secure(states, concept_id: str) -> bool:
    """Secure means both a high estimate and enough evidence to believe it."""
    return _mastery(states, concept_id) >= SECURE and _attempts(states, concept_id) >= MIN_EVIDENCE


def _offered(concepts: Mapping[str, Any], concept_id: str) -> bool:
    """Whether this course actually offers practice for the concept.

    The algebra graph has 164 nodes and 15 authored lessons. Scheduling a node the course
    cannot teach would hand the learner a task with no material behind it, and blocking on
    one would strand them permanently - so coverage is checked explicitly rather than
    assumed from the presence of a node.
    """
    return concept_id in concepts


def classify(graph, concepts, states, concept_id: str, now: float) -> str:
    """Which bucket this concept belongs in. Pure function of graph, coverage and state.

    The distinction that matters here is between *unknown* and *weak*. A concept with no
    attempts has not been measured, so it is not a gap and it does not block anything - it
    simply has not been met yet. Treating zero evidence as weakness would mark every
    non-leaf concept in a fresh course as a "prerequisite gap", which is both wrong and
    discouraging. Only measured evidence can make something a gap.
    """
    if is_secure(states, concept_id):
        return 'secure'
    attempts = _attempts(states, concept_id)
    mastery = _mastery(states, concept_id)
    state = _state(states, concept_id)
    due_at = state.get('due_at')
    if attempts and due_at is not None and float(due_at) <= now:
        return 'review_due'
    if attempts and mastery < READY:
        # A measured weakness. Whether it is blocking is a fact about the course: does
        # anything this course offers depend on it?
        if any(_offered(concepts, child) for child in graph.children(concept_id)):
            return 'prerequisite_gap'
        return 'diagnostic_gap'
    # Not measured, or measured as adequate but not yet secure. It is blocked only by an
    # upstream *measured* weakness; an unstarted prerequisite just sorts earlier.
    if any(_offered(concepts, parent) and _attempts(states, parent)
           and _mastery(states, parent) < READY for parent in graph.parents(concept_id)):
        return 'blocked'
    return 'next_in_order'


def coverage_gaps(graph, concepts, concept_id: str) -> list[str]:
    """Prerequisites this course names but does not offer practice for."""
    return [parent for parent in graph.parents(concept_id) if not _offered(concepts, parent)]


def order_concepts(graph, concepts, states, now: float) -> list[dict[str, Any]]:
    """The work queue, in the order it should be attempted, over offered concepts only.

    Deterministic: bucket first, then graph depth, then difficulty, then id. Two runs with
    the same evidence produce the same queue, which is what makes the plan reviewable.
    """
    depths = graph.depths()
    queue: list[dict[str, Any]] = []
    for concept_id in concepts:
        node = graph.nodes.get(concept_id)
        if node is None:
            continue
        reason = classify(graph, concepts, states, concept_id, now)
        if reason == 'secure':
            continue
        queue.append({
            'concept_id': concept_id,
            'title': node.title,
            'unit': node.unit or '',
            'strand': node.strand or '',
            'topic': node.topic or '',
            'difficulty': int(node.difficulty or 3),
            'mastery': round(_mastery(states, concept_id), 3),
            'attempts': _attempts(states, concept_id),
            'reason': reason,
            'why': REASON_TEXT[reason],
            'depth': depths.get(concept_id, 0),
            'unlocks': sum(1 for child in graph.children(concept_id) if _offered(concepts, child)),
            'blocked_by': ([parent for parent in graph.parents(concept_id)
                            if _offered(concepts, parent) and _attempts(states, parent)
                            and _mastery(states, parent) < READY]
                           if reason == 'blocked' else []),
            'not_offered_prerequisites': coverage_gaps(graph, concepts, concept_id),
        })
    rank = {reason: index for index, reason in enumerate(REASON_ORDER)}
    # Within a bucket: shallower first (you cannot meet a concept before its foundations),
    # then the concept that unlocks the most, then the easier one, then id for determinism.
    # The unlocks term is what stops the plan opening on an arbitrary leaf.
    queue.sort(key=lambda row: (rank.get(row['reason'], len(REASON_ORDER)), row['depth'],
                                -row['unlocks'], row['difficulty'], row['concept_id']))
    return queue


def milestones(graph, concepts, states) -> list[dict[str, Any]]:
    """Per-unit progress over offered concepts, so the learner sees the course not a queue."""
    rows: list[dict[str, Any]] = []
    for strand in graph.strands():
        for unit in graph.units(strand):
            members = [m for m in graph.in_unit(unit, strand) if _offered(concepts, m.id)]
            if not members:
                continue
            mastered = sum(1 for m in members if is_secure(states, m.id))
            rows.append({'strand': strand, 'unit': unit, 'concepts': len(members),
                         'secure': mastered, 'remaining': len(members) - mastered,
                         'progress': round(mastered / len(members), 3)})
    rows.sort(key=lambda row: (-row['remaining'], row['strand'], row['unit']))
    return rows


def plan(graph, concepts: Mapping[str, Mapping[str, Any]], states: Mapping[str, Mapping[str, Any]],
         *, goal: str = '', daily_minutes: int = 20, subject: str = '',
         course_title: str = '', course_id: str = '', now: float) -> dict[str, Any]:
    """The whole plan: pace, today's session, the queue behind it, and the projections."""
    pace = pacing(daily_minutes, states, concept_ids=concepts.keys())
    queue = order_concepts(graph, concepts, states, now)
    units = milestones(graph, concepts, states)

    schedulable = [row for row in queue if row['reason'] != 'blocked']
    blocked = [row for row in queue if row['reason'] == 'blocked']
    today = schedulable[:min(MAX_TODAY, pace['concepts_per_day'])]
    items_today = min(pace['items_per_day'], max(1, len(today)) * ITEMS_PER_CONCEPT)

    # Progress counts what the course actually offers, because a learner can only master
    # material that exists. The wider graph is reported separately so the difference is
    # visible rather than hidden.
    offered = len(concepts)
    secure = sum(1 for concept_id in concepts if is_secure(states, concept_id))
    remaining = offered - secure
    weeks = (remaining / pace['concepts_per_week']) if pace['concepts_per_week'] else None

    due = [row for row in queue if row['reason'] == 'review_due']
    return {
        'course': {'id': course_id, 'title': course_title, 'subject': subject},
        'goal': {
            'stated': (goal or '').strip(),
            'operational_target': (f'Mastery at or above {SECURE:.2f} with at least '
                                   f'{MIN_EVIDENCE} scored attempts on every concept this '
                                   f'course offers, met in prerequisite order.'),
            'note': ('The stated goal is your framing; the operational target is what the '
                     'harness can actually measure. Reaching the target is evidence toward '
                     'the goal, not proof of it.'),
        },
        'pace': pace,
        'today': {
            'concepts': today,
            'items': items_today,
            'minutes': pace['daily_minutes'],
            'rationale': (f'{len(today)} concept(s) and about {items_today} items fit '
                          f'{pace["daily_minutes"]} minutes at the stated divisor.'),
        },
        'due_for_review': due[:MAX_TODAY],
        'queue': queue[:25],
        'queue_total': len(queue),
        'blocked': blocked[:10],
        'blocked_total': len(blocked),
        'milestones': units,
        'progress': {
            'concepts_offered': offered,
            'graph_nodes': len(graph.nodes),
            'secure': secure, 'remaining': remaining,
            'percent_secure': round(100 * secure / offered, 1) if offered else 0.0,
            'weeks_remaining_at_current_pace': None if weeks is None else round(weeks, 1),
            'projection_basis': ('Remaining concepts divided by concepts-per-week. A '
                                 'projection from today\'s pace, not a promise: it assumes '
                                 'every session happens and nothing is forgotten.'),
        },
        'honesty': [
            'This plan is derived from the course graph and your own recorded responses. It '
            'is not a validated curriculum standard or an accredited sequence.',
            'Mastery is a heuristic posterior over responses, not a measurement of '
            'understanding, and it is not calibrated.',
            'Progress counts the concepts this course offers practice for. Where the graph '
            'names a prerequisite with no material behind it, that is a coverage gap and is '
            'reported rather than scheduled.',
            'A blocked concept is named rather than scheduled, because scheduling something '
            'whose foundations are missing is how learners end up stuck and blaming '
            'themselves.',
            'The plan re-derives on every request, so it responds to what you actually do '
            'rather than to what you were expected to do.',
        ],
    }

