"""The agentic loop: what the harness does next, and why.

This module is the difference between a practice app and a harness. A practice app serves
the next item from a fixed sequence. The harness asks a different question first: *given
everything known about this learner on this concept, which kind of interaction has the
best chance of producing durable understanding right now?* Only then does it pick content.

The loop is deliberately legible:

1. **Gather** the evidence - mastery, the shape of recent attempts, which prerequisites are
   weak, what the learner's own memory says, how far into the session they are, and how
   much variety they have had.
2. **Score** every move against that evidence. Scoring is a set of named rules, not a
   black box, and every candidate keeps its own reason string.
3. **Choose** the highest-scoring move, with a deterministic tie-break.
4. **Record** the decision in ``harness_runs``.
5. **Learn** from the outcome: when a move is followed by measured progress, the harness
   records that as procedural memory, so the same move is favoured for this learner next
   time. That is the self-improvement loop, and it is deliberately slow and evidence-bound
   rather than an opaque online update.

Nothing here is random, and nothing here is hidden. Two runs with the same evidence
produce the same decision, which is what makes the decision reviewable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from ..curriculum import CONCEPTS, GRAPH_TO_LESSON, KNOWLEDGE_GRAPH, LESSON_TARGETS
from ..db import HarnessRun, now_ts, uid
from . import modality, socratic
from .toolbox import graph_for

#: The move vocabulary. Fixed on purpose: a bounded set of moves can be scored, reviewed
#: and learned from, whereas free-form action space cannot.
MOVES = ('orient', 'explain', 'simulate', 'retrieve', 'discuss', 'project', 'generate',
         'consolidate', 'rest')

#: How much a move's history can shift its score. Small, so one good session cannot
#: hard-wire a preference, and bounded, so the evidence rules always dominate.
HISTORY_WEIGHT = 0.12
HISTORY_CAP = 3
PROGRESS_THRESHOLD = 0.05

#: Fraction of the day's goal above which the loop starts preferring to consolidate.
LONG_SESSION_MINUTES = 45


@dataclass
class Candidate:
    move: str
    score: float
    reason: str
    tools: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {'move': self.move, 'score': round(self.score, 4), 'reason': self.reason,
                'tools': self.tools}


@dataclass
class Decision:
    run_id: str
    move: str
    reason: str
    evidence: dict[str, Any]
    candidates: list[Candidate]
    tool_plan: list[dict[str, Any]]
    constraints: list[str]
    concept_id: str
    created_at: float
    #: The representation chosen for this decision (see :mod:`app.harness.modality`). The
    #: move is *what kind of interaction*; the channel is *how it is shown*. They are two
    #: axes, and both are recorded so the choice is reviewable. Defaults to ``None`` so a
    #: Decision can still be built without a routing pass.
    modality: dict[str, Any] | None = None
    #: The next dialogue move (see :mod:`app.harness.socratic`): pump, hint, prompt or
    #: assert. Attached from the same evidence as the move and the channel, so the three
    #: cannot disagree about what the learner needs.
    dialogue: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {'run_id': self.run_id, 'move': self.move, 'reason': self.reason,
                'concept_id': self.concept_id, 'evidence': self.evidence,
                'candidates': [c.to_dict() for c in self.candidates],
                'tool_plan': self.tool_plan, 'constraints': self.constraints,
                'modality': self.modality, 'dialogue': self.dialogue,
                'created_at': self.created_at,
                'alternatives': [c.move for c in self.candidates if c.move != self.move][:3]}


# ------------------------------------------------------------------ evidence

def _lesson_id(concept_id: str) -> str:
    if concept_id in CONCEPTS:
        return concept_id
    return GRAPH_TO_LESSON.get(concept_id, '')


def _recent_attempts(db, user_id: str, concept_id: str, limit: int = 8) -> list[Any]:
    from ..db import Attempt
    lesson = _lesson_id(concept_id) or concept_id
    if not db or not user_id:
        return []
    statement = (select(Attempt)
                 .where(Attempt.user_id == user_id, Attempt.concept_id == lesson)
                 .order_by(Attempt.created_at.desc()).limit(limit))
    return list(db.scalars(statement))


def _simulation_touched(db, user_id: str, concept_id: str) -> bool:
    from ..db import TelemetryEvent
    if not db or not user_id:
        return False
    lesson = _lesson_id(concept_id) or concept_id
    # Two honest signals count: the authored simulation's own parameter telemetry, and the
    # fact that the learner opened an external (PhET) simulation for this concept. Neither
    # claims the other: an external sim reports no parameters back, so its event carries
    # only the concept id.
    rows = db.scalars(select(TelemetryEvent).where(
        TelemetryEvent.user_id == user_id,
        TelemetryEvent.type.in_(['simulation_interaction', 'external_simulation_opened']))
        .limit(50))
    return any((row.payload or {}).get('concept_id') == lesson for row in rows)


def gather(ctx, concept_id: str) -> dict[str, Any]:
    """Collect the evidence the policy scores against. Every field is inspectable."""
    from ..db import Project, State
    graph = graph_for(ctx)
    node = graph.nodes.get(concept_id)
    if node is None:
        # A lesson id and a graph node id are different namespaces; resolve either.
        target = LESSON_TARGETS.get(concept_id, '')
        node = graph.nodes.get(target) if target else None
    resolved = node.id if node else concept_id
    lesson = _lesson_id(resolved)
    lesson_data = CONCEPTS.get(lesson) or CONCEPTS.get(concept_id)

    state: dict[str, Any] = {}
    if ctx.db and ctx.user_id:
        row = ctx.db.scalar(select(State).where(State.user_id == ctx.user_id,
                                                State.concept_id == (lesson or concept_id)))
        state = dict(row.data) if row else {}

    attempts = _recent_attempts(ctx.db, ctx.user_id, resolved)
    correct = sum(1 for a in attempts if a.correct)
    # Categories come from incorrect attempts only. A correct response also carries a
    # category ('supported_correct'), and counting it here would let a success be
    # reported as the learner's most common error.
    categories: dict[str, int] = {}
    for attempt in attempts:
        if not attempt.correct:
            categories[attempt.category] = categories.get(attempt.category, 0) + 1
    elapsed = [a.elapsed_seconds for a in attempts]
    confidence = [a.confidence for a in attempts if a.confidence is not None]
    reasoning = sum(1 for a in attempts if (a.payload or {}).get('reasoning'))
    # Leading run of failures, newest first. This is what the dialogue ladder counts: two
    # failed cycles is the point at which asserting becomes honest. Aggregated error
    # categories cannot answer it, because they have lost the order.
    consecutive_failures = 0
    for attempt in attempts:
        if attempt.correct:
            break
        consecutive_failures += 1

    notes: list[dict[str, Any]] = []
    digest = ''
    if ctx.db and ctx.user_id:
        from . import memory
        related = ([*graph.all_parents(resolved), *graph.children(resolved)]
                   if node else [])
        notes = [n.to_dict() for n in memory.recall(ctx.db, ctx.user_id, concept_id=resolved,
                                                    limit=8, now=ctx.now or None, related=related)]
        digest = memory.digest(ctx.db, ctx.user_id, concept_id=resolved, related=related, limit=8)

    weak_prerequisites: list[str] = []
    if node and ctx.db and ctx.user_id:
        for parent in graph.all_parents(resolved):
            parent_lesson = GRAPH_TO_LESSON.get(parent, parent)
            parent_state = ctx.db.scalar(select(State).where(
                State.user_id == ctx.user_id, State.concept_id == parent_lesson))
            data = dict(parent_state.data) if parent_state else {}
            if data.get('attempts', 0) and float(data.get('mastery', 0.15)) < 0.6:
                weak_prerequisites.append(parent)

    project_status = 'unknown'
    if ctx.db and ctx.user_id and lesson:
        row = ctx.db.scalar(select(Project).where(Project.user_id == ctx.user_id,
                                                  Project.concept_id == lesson))
        project_status = row.status if row else 'not_started'

    unit_nodes = [n for n in graph.nodes.values() if n.unit == (node.unit if node else '')]
    unit_mastered = 0
    if ctx.db and ctx.user_id and unit_nodes:
        for other in unit_nodes:
            other_lesson = GRAPH_TO_LESSON.get(other.id, other.id)
            row = ctx.db.scalar(select(State).where(State.user_id == ctx.user_id,
                                                    State.concept_id == other_lesson))
            data = dict(row.data) if row else {}
            if float(data.get('mastery', 0.15)) >= 0.8 and data.get('attempts', 0) >= 3:
                unit_mastered += 1

    history = effectiveness(ctx.db, ctx.user_id) if ctx.db and ctx.user_id else {}
    recent_moves = recent_decisions(ctx.db, ctx.user_id, limit=3) if ctx.db and ctx.user_id else []

    now = ctx.now or now_ts()
    due_at = state.get('due_at')
    return {
        'concept_id': resolved,
        'lesson_id': lesson,
        'title': (node.title if node else (lesson_data or {}).get('title', resolved)),
        'has_lesson': bool(lesson_data),
        'has_figure': node is not None,
        'mastery': round(float(state.get('mastery', 0.15)), 4),
        'attempts': int(state.get('attempts', 0)),
        'due': bool(due_at is not None and due_at <= now),
        'due_in_seconds': None if due_at is None else round(due_at - now, 1),
        'last_correct': state.get('last_correct'),
        'sample': len(attempts),
        'recent_accuracy': round(correct / len(attempts), 4) if attempts else None,
        'consecutive_failures': consecutive_failures,
        'recent_errors': [{'category': k, 'count': v}
                          for k, v in sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))],
        'top_error': max(categories, key=lambda k: (categories[k], k)) if categories else '',
        'mean_elapsed': round(sum(elapsed) / len(elapsed), 1) if elapsed else None,
        'elapsed_trend': _trend(elapsed),
        'mean_confidence': round(sum(confidence) / len(confidence), 3) if confidence else None,
        'reasoning_written': reasoning,
        'weak_prerequisites': weak_prerequisites,
        'prerequisite_count': len(graph.all_parents(resolved)) if node else 0,
        'dependant_count': len(graph.children(resolved)) if node else 0,
        'unit_mastered': unit_mastered,
        'unit_size': len(unit_nodes),
        'project_status': project_status,
        'simulation_touched': _simulation_touched(ctx.db, ctx.user_id, resolved),
        'memory': {'count': len(notes), 'notes': notes, 'digest': digest},
        'history': history,
        'recent_moves': recent_moves,
        'active_minutes_today': _active_minutes(ctx, now),
    }


def _trend(values: Sequence[float]) -> str:
    """Direction of travel in elapsed time: a proxy for struggle, not a measurement."""
    if len(values) < 3:
        return 'insufficient'
    recent = sum(values[:len(values) // 2]) / max(1, len(values) // 2)
    earlier = sum(values[len(values) // 2:]) / max(1, len(values) - len(values) // 2)
    if earlier <= 0:
        return 'flat'
    change = (recent - earlier) / earlier
    if change <= -0.35:
        return 'much_faster'
    if change <= -0.12:
        return 'faster'
    if change >= 0.35:
        return 'much_slower'
    if change >= 0.12:
        return 'slower'
    return 'flat'


def _active_minutes(ctx, now: float) -> float:
    from ..db import TelemetryEvent
    if not ctx.db or not ctx.user_id:
        return 0.0
    rows = ctx.db.scalars(select(TelemetryEvent).where(
        TelemetryEvent.user_id == ctx.user_id,
        TelemetryEvent.received_at >= now - 6 * 3600).limit(500))
    total = sum(float(row.active_seconds or 0) for row in rows)
    return round(total / 60, 2)


def recent_decisions(db, user_id: str, limit: int = 3) -> list[str]:
    if not db or not user_id:
        return []
    rows = db.scalars(select(HarnessRun).where(HarnessRun.user_id == user_id,
                                               HarnessRun.chosen.is_(True))
                      .order_by(HarnessRun.created_at.desc()).limit(limit))
    return [row.move for row in rows]


def effectiveness(db, user_id: str) -> dict[str, dict[str, Any]]:
    """Which moves have actually been followed by progress, for this learner.

    Reads only outcomes the harness itself recorded, so an unmeasured move stays
    unmeasured rather than being assumed to work.
    """
    if not db or not user_id:
        return {}
    rows = db.scalars(select(HarnessRun).where(HarnessRun.user_id == user_id,
                                               HarnessRun.chosen.is_(True)))
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        outcome = row.outcome or {}
        if 'progress' not in outcome:
            continue
        bucket = summary.setdefault(row.move, {'runs': 0, 'progress_total': 0.0, 'positive': 0,
                                               'negative': 0})
        progress = float(outcome['progress'])
        bucket['runs'] += 1
        bucket['progress_total'] += progress
        if progress > PROGRESS_THRESHOLD:
            bucket['positive'] += 1
        elif progress < -PROGRESS_THRESHOLD:
            bucket['negative'] += 1
    for bucket in summary.values():
        bucket['mean_progress'] = round(bucket['progress_total'] / max(1, bucket['runs']), 4)
        bucket.pop('progress_total')
    return summary


# ------------------------------------------------------------------ policy

def _tools_for(move: str, evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The tool calls this move implies. Recorded so the decision is reproducible."""
    if move == 'orient':
        return [{'tool': 'inspect_prerequisites', 'arguments': {'concept_id': evidence['concept_id']}},
                {'tool': 'check_understanding', 'arguments': {'concept_id': evidence['concept_id']}}]
    if move == 'explain':
        return [{'tool': 'read_concept', 'arguments': {'concept_id': evidence['concept_id']}},
                {'tool': 'recall_learner_memory', 'arguments': {'concept_id': evidence['concept_id']}},
                {'tool': 'compose_content', 'arguments': {'concept_id': evidence['concept_id'],
                                                          'kind': 'explanation'}}]
    if move == 'simulate':
        return [{'tool': 'build_figure', 'arguments': {'concept_id': evidence['concept_id']}},
                {'tool': 'recall_learner_memory', 'arguments': {'concept_id': evidence['concept_id']}}]
    if move == 'retrieve':
        return [{'tool': 'check_understanding', 'arguments': {'concept_id': evidence['concept_id']}},
                {'tool': 'read_learner_evidence', 'arguments': {'concept_id': evidence['concept_id']}}]
    if move == 'discuss':
        return [{'tool': 'read_concept', 'arguments': {'concept_id': evidence['concept_id']}},
                {'tool': 'recall_learner_memory', 'arguments': {'concept_id': evidence['concept_id']}}]
    if move == 'project':
        return [{'tool': 'prepare_case_study', 'arguments': {'concept_id': evidence['concept_id']}}]
    if move == 'generate':
        return [{'tool': 'compose_content',
                 'arguments': {'concept_id': evidence['concept_id'],
                               'kind': _artefact_kind(evidence)}}]
    if move == 'consolidate':
        return [{'tool': 'read_concept', 'arguments': {'concept_id': evidence['concept_id']}},
                {'tool': 'search_concepts',
                 'arguments': {'query': evidence.get('title', '')}}]
    return []


def _artefact_kind(evidence: Mapping[str, Any]) -> str:
    """Which artefact this learner most needs, from the same evidence the move uses."""
    if len(evidence.get('memory', {}).get('notes', [])) >= 3:
        return 'flashcards'
    if 0.35 <= float(evidence.get('mastery', 0)) <= 0.7:
        return 'slide_deck'
    if float(evidence.get('mastery', 0)) >= 0.75:
        return 'quiz'
    return 'explanation'


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_moves(evidence: Mapping[str, Any]) -> list[Candidate]:
    """Score every move. Returns all of them, so the runner-up is always visible."""
    mastery = float(evidence.get('mastery', 0.15))
    attempts = int(evidence.get('attempts', 0))
    sample = int(evidence.get('sample', 0))
    accuracy = evidence.get('recent_accuracy')
    top_error = evidence.get('top_error', '')
    due = bool(evidence.get('due'))
    has_lesson = bool(evidence.get('has_lesson'))
    has_figure = bool(evidence.get('has_figure'))
    history = evidence.get('history') or {}
    notes = evidence.get('memory', {}).get('notes', [])
    recent_moves = list(evidence.get('recent_moves') or [])
    minutes = float(evidence.get('active_minutes_today', 0))
    trend = evidence.get('elapsed_trend', 'insufficient')

    uncertain = attempts <= 2 and 0.25 <= mastery <= 0.7
    frustration = bool(sample >= 3 and (accuracy or 0) <= 0.34 and trend in {'much_faster', 'faster'})
    overload = minutes >= LONG_SESSION_MINUTES
    repetitive = len(recent_moves) >= 3 and len(set(recent_moves)) == 1

    candidates: list[Candidate] = []

    def add(move: str, score: float, reason: str) -> None:
        candidates.append(Candidate(move, _clamp(score), reason, _tools_for(move, evidence)))

    # orient ---------------------------------------------------------------
    score, why = 0.22, 'Some orientation is always affordable.'
    if attempts == 0:
        score += 0.42
        why = 'No scored attempt exists for this concept, so the harness has no evidence yet.'
    if uncertain:
        score += 0.22
        why = f'Mastery {mastery:.2f} rests on only {attempts} attempt(s); a short check buys more information than teaching.'
    if evidence.get('weak_prerequisites'):
        score += 0.10
        why += f" {len(evidence['weak_prerequisites'])} prerequisite(s) measure below 0.60."
    add('orient', score, why)

    # explain --------------------------------------------------------------
    score, why = 0.20, 'A grounded explanation is a reasonable default.'
    if attempts == 0 and has_lesson:
        score += 0.30
        why = 'The concept has never been attempted and an authored lesson exists to ground an explanation.'
    if top_error == 'conceptual':
        score += 0.38
        why = f"The most frequent recorded error category is conceptual ({top_error}), which an explanation can address."
    if not any(note.get('kind') == 'semantic' for note in notes):
        score += 0.16
        why += ' No semantic note about this concept exists yet.'
    if mastery < 0.45:
        score += 0.10
    add('explain', score, why)

    # simulate -------------------------------------------------------------
    score, why = 0.18, 'A figure is available if changing representation helps.'
    if not has_figure:
        score = 0.02
        why = 'This concept has no generated figure, so the simulation move is unavailable.'
    else:
        if top_error in {'conceptual', 'procedural'}:
            score += 0.40
            why = f'Errors concentrate in {top_error}; a second representation is the standard response.'
        if 0.35 <= mastery <= 0.78:
            score += 0.22
            why += ' Mastery is partial, the range where representation change helps most.'
        if not evidence.get('simulation_touched'):
            score += 0.14
            why += ' The learner has not yet interacted with this figure.'
        if frustration:
            score += 0.22
            why += ' Recent attempts are fast and wrong, which usually means the current framing is not landing.'
    add('simulate', score, why)

    # retrieve -------------------------------------------------------------
    score, why = 0.18, 'Retrieval practice is a default candidate.'
    if due:
        score += 0.55
        why = 'This concept is past its scheduled review interval.'
    if accuracy is not None and accuracy >= 0.75 and attempts >= 3:
        score += 0.24
        why += ' Recent accuracy is high enough that recall, not re-teaching, is the productive step.'
    if 0.6 <= mastery <= 0.9:
        score += 0.20
    if frustration:
        score -= 0.30
        why += ' Recent failure makes another retrieval item a poor immediate choice.'
    if not has_lesson:
        score = 0.02
        why = 'No authored retrieval item exists for this concept yet.'
    add('retrieve', score, why)

    # discuss --------------------------------------------------------------
    score, why = 0.12, 'Discussion is worth it once the learner can produce reasoning.'
    if mastery >= 0.7:
        score += 0.36
        why = f'Mastery {mastery:.2f} is high enough for the learner to carry the reasoning.'
    if int(evidence.get('reasoning_written', 0)) >= 2:
        score += 0.22
        why += f" {evidence['reasoning_written']} recent attempts already include written reasoning."
    if accuracy is not None and accuracy >= 0.7 and attempts >= 4:
        score += 0.16
    add('discuss', score, why)

    # project --------------------------------------------------------------
    score, why = 0.08, 'Applied work is for consolidated understanding.'
    if mastery >= 0.85 and attempts >= 4:
        score += 0.52
        why = f'Mastery {mastery:.2f} over {attempts} attempts supports an applied task.'
    if evidence.get('project_status') == 'not_started':
        score += 0.14
    if int(evidence.get('dependant_count', 0)) >= 3:
        score += 0.12
        why += ' Several concepts depend on this one, so applying it pays forward.'
    if frustration:
        score -= 0.24
    add('project', score, why)

    # generate -------------------------------------------------------------
    score, why = 0.14, 'A generated artefact is available.'
    if repetitive:
        score += 0.34
        why = f"The last {len(recent_moves)} decisions were all '{recent_moves[0]}'; variety is itself a reason to change format."
    if len(notes) >= 3:
        score += 0.18
        why += f" {len(notes)} recorded observations can personalise the artefact."
    if 0.35 <= mastery <= 0.72:
        score += 0.18
    if frustration:
        score += 0.12
    add('generate', score, why)

    # consolidate ----------------------------------------------------------
    score, why = 0.10, 'Consolidation suits near-mastered material.'
    unit_size = max(1, int(evidence.get('unit_size', 1)))
    coverage = int(evidence.get('unit_mastered', 0)) / unit_size
    if mastery >= 0.8:
        score += 0.34
        why = f'Mastery {mastery:.2f} suggests the idea is nearly held and worth connecting.'
    if coverage >= 0.5:
        score += 0.20
        why += f' {coverage:.0%} of the unit is mastered, so the structure is worth summarising.'
    add('consolidate', score, why)

    # rest -----------------------------------------------------------------
    score, why = 0.03, 'Rest is a fallback when nothing else is clearly better.'
    if frustration:
        score += 0.48
        why = 'The last attempts are fast, wrong and clustered: continuing at this pace is unlikely to help.'
    if overload:
        score += 0.34
        why = f'{minutes:.0f} minutes of measured interaction today is a long session.'
    if trend == 'much_slower':
        score += 0.12
    add('rest', score, why)

    # learned preference ---------------------------------------------------
    for candidate in candidates:
        record = history.get(candidate.move)
        if not record:
            continue
        boost = HISTORY_WEIGHT * min(HISTORY_CAP, int(record.get('positive', 0)))
        penalty = HISTORY_WEIGHT * min(HISTORY_CAP, int(record.get('negative', 0)))
        if boost:
            candidate.score = _clamp(candidate.score + boost)
            candidate.reason += (f" This learner's record shows {record['positive']} prior "
                                 f"{candidate.move} decision(s) followed by progress.")
        if penalty:
            candidate.score = _clamp(candidate.score - penalty)
            candidate.reason += (f" {record['negative']} prior {candidate.move} decision(s) were "
                                 f"not followed by progress.")
    candidates.sort(key=lambda c: (-c.score, MOVES.index(c.move)))
    return candidates


def choose(evidence: Mapping[str, Any]) -> Candidate:
    """The argmax with a deterministic tie-break. Same evidence, same decision."""
    return score_moves(evidence)[0]


# ------------------------------------------------------------------ recording

def plan(ctx, concept_id: str, *, exam_active: bool = False) -> Decision:
    """Gather, score, choose and record. The harness's single decision point."""
    evidence = gather(ctx, concept_id)
    candidates = score_moves(evidence)
    constraints: list[str] = []
    if exam_active:
        # A penalty would not be enough: a strong teaching signal can outscore a weak
        # rest signal, and the harness would still be teaching during an exam. The move
        # set is restricted instead, and the exclusion is recorded rather than hidden.
        constraints.append('An exam is active: the harness stands down. Only the rest move '
                           'is available until the exam ends or expires.')
        for candidate in candidates:
            if candidate.move != 'rest':
                candidate.reason += ' (unavailable: an exam is active)'
                candidate.score = 0.0
            else:
                candidate.score = _clamp(candidate.score + 0.6)
                candidate.reason = ('An exam is active, so the harness stands down rather than '
                                    'competing with the assessment.')
        candidates.sort(key=lambda c: (-c.score, MOVES.index(c.move)))
    chosen = candidates[0]
    if not evidence.get('has_lesson') and chosen.move in {'retrieve', 'project'}:
        constraints.append('No authored lesson covers this node, so retrieval and project moves '
                           'fall back to the graph description.')
    reason = _learner_reason(chosen, evidence)
    # The representation is routed from the same evidence, so the interaction kind and the
    # way it is shown cannot be decided from two different pictures of the learner.
    routed = modality.route(evidence)
    # And the next dialogue move comes from the same evidence, for the same reason: a
    # decision that says "explain" while the ladder says "assert" is two policies arguing.
    dialogue = socratic.step(socratic.state_from_evidence(evidence))
    decision = Decision(run_id=uid(), move=chosen.move, reason=reason, evidence=evidence,
                        candidates=candidates, tool_plan=chosen.tools,
                        constraints=constraints, concept_id=evidence['concept_id'],
                        created_at=ctx.now or now_ts(), modality=routed,
                        dialogue=dialogue)
    if ctx.db and ctx.user_id:
        ctx.db.add(HarnessRun(id=decision.run_id, user_id=ctx.user_id,
                              concept_id=decision.concept_id, move=chosen.move, reason=reason,
                              evidence=_compact_evidence(evidence, routed, dialogue),
                              chosen=True, outcome={}, created_at=decision.created_at))
        ctx.db.commit()
    return decision


def _learner_reason(candidate: Candidate, evidence: Mapping[str, Any]) -> str:
    """The internal reason, plus a plain sentence a learner could read."""
    plain = {
        'orient': 'We will start with a short check so I know what you already hold.',
        'explain': 'We will work through the idea itself, with the figure alongside it.',
        'simulate': 'We will look at this a different way and predict what changes.',
        'retrieve': 'We will pull this back out of memory, which is how it sticks.',
        'discuss': 'You will do the reasoning out loud and I will push on it.',
        'project': 'You will apply this to a real task and justify your method.',
        'generate': 'I will build you something to keep: a deck, a card set or a figure.',
        'consolidate': 'We will connect this to what sits around it.',
        'rest': 'We will slow down or stop here rather than push on.',
    }[candidate.move]
    return f'{candidate.reason} In practice: {plain}'


def _compact_evidence(evidence: Mapping[str, Any],
                      routed: Mapping[str, Any] | None = None,
                      dialogue: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The evidence worth storing: the signals, not the full transcript."""
    keys = ('concept_id', 'mastery', 'attempts', 'due', 'recent_accuracy', 'top_error',
            'elapsed_trend', 'weak_prerequisites', 'unit_mastered', 'unit_size',
            'project_status', 'simulation_touched', 'active_minutes_today', 'recent_moves')
    compact = {key: evidence.get(key) for key in keys}
    compact['memory_notes'] = len(evidence.get('memory', {}).get('notes', []))
    compact['recent_errors'] = evidence.get('recent_errors', [])
    if routed:
        compact['modality_channel'] = routed.get('channel')
    if dialogue:
        compact['dialogue_move'] = dialogue.get('move')
    return compact


def record_outcome(ctx, run_id: str, outcome: Mapping[str, Any]) -> dict[str, Any]:
    """Attach what actually happened to a recorded decision, and learn from it.

    This is the self-improvement step. It is deliberately conservative: a move is only
    remembered as working when progress crosses a threshold, and the note carries the
    measured delta so a later reader can judge whether the claim holds.
    """
    if not ctx.db or not ctx.user_id:
        raise ValueError('An outcome needs a bound learner')
    row = ctx.db.scalar(select(HarnessRun).where(HarnessRun.id == run_id,
                                                 HarnessRun.user_id == ctx.user_id))
    if row is None:
        raise ValueError(f'No harness decision {run_id!r} for this learner')
    progress = float(outcome.get('progress', 0.0))
    payload = {'progress': round(progress, 4),
               'mastery_after': outcome.get('mastery_after'),
               'accuracy_after': outcome.get('accuracy_after'),
               'engaged_seconds': outcome.get('engaged_seconds'),
               'note': str(outcome.get('note', ''))[:400]}
    row.outcome = payload
    from . import memory
    if abs(progress) > PROGRESS_THRESHOLD:
        direction = 'was followed by progress' if progress > 0 else 'was not followed by progress'
        memory.remember(ctx.db, ctx.user_id, 'procedural',
                        f"{row.move} {direction} on {row.concept_id} "
                        f"(measured change {progress:+.2f}).",
                        concept_id=row.concept_id,
                        evidence={'run_id': run_id, 'progress': round(progress, 4),
                                  'move': row.move},
                        confidence=0.30)
    ctx.db.commit()
    return {'run_id': run_id, 'move': row.move, 'outcome': payload}


def explain(decision: Decision) -> dict[str, Any]:
    """A reviewable account of a decision, for the API and the learner-facing panel."""
    runner_up = next((c for c in decision.candidates if c.move != decision.move), None)
    return {'chosen': decision.move, 'why': decision.reason,
            'runner_up': runner_up.to_dict() if runner_up else None,
            'constraints': decision.constraints,
            'modality': decision.modality,
            'top_signals': {key: decision.evidence.get(key) for key in
                            ('mastery', 'attempts', 'recent_accuracy', 'top_error', 'due',
                             'weak_prerequisites', 'active_minutes_today')},
            'scored': [c.to_dict() for c in decision.candidates]}


def fingerprint(evidence: Mapping[str, Any], move: str) -> str:
    """A stable hash of the signals behind a decision, for deduplication in analysis."""
    material = f"{evidence.get('concept_id')}|{move}|{evidence.get('mastery')}|{evidence.get('attempts')}"
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def available_moves() -> list[dict[str, str]]:
    return [{'move': move} for move in MOVES]
