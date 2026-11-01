"""What the teacher knows about the learner and the concept, as one record.

The policy, the retrieval planner and the modality router all read the same evidence
record, so they cannot disagree about the learner's state. Two details matter:

* The mastery/recall separation is preserved exactly as ``app.learning`` defines it:
  ``mastery`` is the BKT-style belief about current skill; ``recall`` is the FSRS-6
  retrievability - "how likely a review succeeds right now". A high-mastery concept
  whose recall has decayed is the one case where teaching forward is the wrong
  choice and retrieval is right, and only a record that keeps both fields separate
  can express it.
* Prerequisite debt is computed from prerequisite *states*, not from the graph
  alone: a satisfied edge on paper can still be shaky in the learner.

Import trap worth naming: ``...memory`` (three dots) is this app's FSRS-6 model
(``app.memory``). ``..memory`` (two dots) is the harness's note memory
(``app.harness.memory``) - beliefs about the learner, not the forgetting curve.
They are different systems answering different questions; importing the wrong one
produces a teacher that confuses "the learner said they were confused once" with
"probability of recall".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ...memory import recall_probability  # FSRS-6: retrievability R(t)

#: BKT-style prior for a concept with no recorded attempts. Mirrors
#: ``app.learning.PRIOR`` so a never-attempted concept is equally "unknown"
#: in both modules instead of being unknown twice by different amounts.
PRIOR = 0.15


@dataclass(frozen=True)
class ConceptFacts:
    """The concept as the teaching core needs it: where it sits in the graph, and
    what *kind* of concept it is. ``concept_type`` is the routing key the modality
    rules branch on; it is derived from the graph's strand and tier, never invented.
    """

    id: str
    title: str = ''
    strand: str = ''
    tier: str = 'core'
    depth: int = 0
    prerequisite_count: int = 0
    dependant_count: int = 0
    has_lesson: bool = False
    has_figure: bool = False
    has_video: bool = False
    subject_kind: str = 'mathematics'
    concept_type: str = 'verbal'
    keywords: tuple[str, ...] = ()


def concept_type_for(strand: str, subject_kind: str, tier: str = 'core') -> str:
    """Map a graph strand to a teaching-relevant concept type.

    The non-mathematics case first: the symbolic engine is valid only for
    mathematics, so for every other subject the honest figure is a concept map
    derived from prerequisite edges (the same constraint the harness prompt's
    grounding rule 6 states), and teaching a physics concept as if it were a
    plottable function would present a concept map as a physical model.
    """
    if subject_kind != 'mathematics':
        return 'concept_map'
    if strand in ('Number & Quantity', 'Algebra', 'Functions'):
        return 'quantitative_relation'
    if strand == 'Geometry & Measurement':
        return 'spatial'
    if strand == 'Statistics & Probability':
        return 'data'
    return 'verbal'


def concept_facts(concept_id: str, graph=None, *, subject_kind: str = 'mathematics') -> ConceptFacts:
    """Resolve a lesson id or a graph node id into :class:`ConceptFacts`.

    The lesson layer and the graph layer use different id namespaces (a lesson id
    maps to a graph node through ``curriculum.GRAPH_TO_LESSON``). Resolving both
    here keeps every caller from re-deriving the mapping - and keeps "no node found"
    a valid, honest outcome rather than a crash mid-lesson.
    """
    from ...curriculum import CONCEPTS, GRAPH_TO_LESSON, KNOWLEDGE_GRAPH, LESSON_TARGETS
    graph = graph if graph is not None else KNOWLEDGE_GRAPH
    node = graph.nodes.get(concept_id)
    if node is None and concept_id in LESSON_TARGETS:
        node = graph.nodes.get(LESSON_TARGETS[concept_id])
    if node is None:
        # A lesson id with no graph node: fall back to the lesson record itself.
        lesson = CONCEPTS.get(concept_id) or {}
        media = lesson.get('media') or []
        return ConceptFacts(
            id=concept_id, title=str(lesson.get('title', concept_id)),
            strand='', tier='core', depth=0,
            prerequisite_count=len(lesson.get('prerequisites') or []),
            has_lesson=bool(lesson),
            has_figure=concept_id in GRAPH_TO_LESSON,
            has_video=any(item.get('kind') == 'video' for item in media
                          if isinstance(item, dict)),
            subject_kind=subject_kind,
            concept_type=concept_type_for('', subject_kind),
            keywords=tuple(str(k) for k in (lesson.get('keywords') or [])[:8]))
    has_lesson = bool(node.lesson_id) or concept_id in CONCEPTS
    lesson_media = (CONCEPTS.get(node.lesson_id) or {}).get('media') or []
    return ConceptFacts(
        id=node.id, title=node.title, strand=node.strand, tier=node.tier,
        depth=graph.depths().get(node.id, 0),
        prerequisite_count=len(graph.parents(node.id)),
        dependant_count=len(graph.children(node.id)),
        has_lesson=has_lesson,
        has_figure=node.lesson_id in GRAPH_TO_LESSON or bool(node.lesson_id),
        has_video=any(item.get('kind') == 'video' for item in lesson_media
                      if isinstance(item, dict)),
        subject_kind=subject_kind,
        concept_type=concept_type_for(node.strand, subject_kind, node.tier),
        keywords=tuple(node.keywords[:8]))


@dataclass(frozen=True)
class LearnerEvidence:
    """Everything the policy is allowed to know when it chooses a move.

    Fields are grouped by the question they answer. The record is a value object:
    built once per concept per turn, then read by the policy, the retrieval planner
    and the modality router without any of them mutating or re-deriving it.
    """

    # -- the concept
    concept_id: str = ''
    concept_type: str = 'verbal'
    tier: str = 'core'
    has_lesson: bool = False
    has_figure: bool = False
    subject_kind: str = 'mathematics'
    # -- learner state on this concept (BKT-style belief + FSRS-6 memory)
    mastery: float = PRIOR
    attempts: int = 0
    recent_accuracy: float | None = None
    top_error: str = ''
    elapsed_trend: str = 'insufficient'
    recall: float | None = None          # FSRS-6 R(t); None when never reviewed
    stability_days: float | None = None
    lapses: int = 0
    due_at: float | None = None          # epoch seconds from the FSRS scheduler
    last_correct: bool | None = None
    # -- the graph around it (OSSB-style prerequisite debt)
    prerequisite_debt: float = 0.0
    weak_prerequisites: int = 0
    dependants: int = 0
    # -- the session
    unit_coverage: float = 0.0
    project_status: str = 'unknown'
    simulation_touched: bool = False
    session_minutes: float = 0.0
    recent_moves: tuple[str, ...] = ()
    move_history: Mapping[str, Mapping[str, int]] = field(default_factory=dict)

    @property
    def frustrated(self) -> bool:
        """Fast and wrong: the pattern where another retrieval item is noise."""
        return (self.attempts >= 3 and (self.recent_accuracy is not None)
                and self.recent_accuracy <= 0.34
                and self.elapsed_trend in {'much_faster', 'faster'})

    def satisfied(self, completion) -> bool:
        """The freeCodeCamp-style completion gate: attempts *and* transfer.

        Recognising an idea (accurate attempts) is not the same as being able to
        use it (a finished applied task), so a concept that has never had a project
        is never "satisfied" when transfer is required.
        """
        if self.attempts < completion.min_attempts:
            return False
        if self.recent_accuracy is None or self.recent_accuracy < completion.min_accuracy:
            return False
        if completion.transfer_required and self.project_status != 'completed':
            return False
        return True

    @property
    def uncertain(self) -> bool:
        """Mastery that rests on almost no evidence - the orient window."""
        return self.attempts <= 2 and 0.25 <= self.mastery <= 0.7


def fsrs_recall(state: Mapping[str, Any] | None, now: float | None = None) -> float | None:
    """FSRS-6 retrievability right now, or None when the model cannot say.

    None is the honest answer for a never-reviewed concept (and for legacy Leitner
    states the DSR model cannot read), and the policy treats None as "unknown",
    never as zero - otherwise a brand-new learner would look maximally due.
    """
    if not state:
        return None
    now = time.time() if now is None else now
    if state.get('stability') is None:
        return None
    return recall_probability(state, now)


def parent_states_for(concept_id: str, states: Mapping[str, Mapping[str, Any]],
                      graph=None) -> dict[str, Mapping[str, Any]]:
    """The stored state of each direct prerequisite, for the debt measure.

    Debt has to come from prerequisite *states*, not from the graph's shape: an edge
    that is satisfied on paper can still be shaky in the learner. A prerequisite with
    no recorded state is included as an empty mapping rather than skipped, so it
    counts at ``PRIOR`` - a prerequisite nobody has attempted is exactly the shaky
    ground the measure exists to find.

    Resolves both id namespaces, like :func:`concept_facts`: a lesson id and a graph
    node id name the same concept, and a caller holding one should not have to know
    which.
    """
    from ...curriculum import KNOWLEDGE_GRAPH, LESSON_TARGETS
    graph = graph if graph is not None else KNOWLEDGE_GRAPH
    node_id = concept_id
    if node_id not in graph.nodes and concept_id in LESSON_TARGETS:
        node_id = LESSON_TARGETS[concept_id]
    if node_id not in graph.nodes:
        return {}
    return {parent: dict(states.get(parent) or {}) for parent in graph.parents(node_id)}


def prerequisite_debt(parent_states: Mapping[str, Any] | None,
                      threshold: float = 0.6) -> tuple[float, int]:
    """(debt, weak_count): how far the prerequisites are from the mastery bar.

    Debt is ``1 - mean(mastery)`` over recorded prerequisites; unrecorded parents
    count at ``PRIOR`` rather than being skipped, because a prerequisite nobody has
    attempted is exactly the shaky ground being measured (echoing the app's
    recommend(), which demotes mastered concepts rather than ignoring unmet ones).
    """
    if not parent_states:
        return 0.0, 0
    values = [float((s or {}).get('mastery', PRIOR)) for s in parent_states.values()]
    weak = sum(1 for v in values if v < threshold)
    return round(1.0 - (sum(values) / len(values)), 4), weak


def build_evidence(facts: ConceptFacts, state: Mapping[str, Any] | None = None, *,
                   parent_states: Mapping[str, Any] | None = None,
                   now: float | None = None, session_minutes: float = 0.0,
                   recent_moves: Sequence[str] = (),
                   move_history: Mapping[str, Mapping[str, int]] | None = None,
                   project_status: str = 'unknown', simulation_touched: bool = False,
                   unit_coverage: float = 0.0, top_error: str = '',
                   recent_accuracy: float | None = None,
                   elapsed_trend: str = 'insufficient',
                   mastery_threshold: float = 0.6) -> LearnerEvidence:
    """Assemble the evidence record from the raw learner state.

    ``state`` is the stored per-concept dict (mastery/attempts/FSRS fields/due_at);
    ``parent_states`` maps each prerequisite id to its stored state so debt can be
    computed from evidence rather than from the graph's shape.
    """
    state = dict(state or {})
    recall = fsrs_recall(state, now)
    debt, weak = prerequisite_debt(parent_states, mastery_threshold)
    accuracy = recent_accuracy
    if accuracy is None:
        attempts = int(state.get('attempts', 0))
        correct = int(state.get('correct_count', 0))
        accuracy = (correct / attempts) if attempts >= 3 else None
    return LearnerEvidence(
        concept_id=facts.id,
        concept_type=facts.concept_type,
        tier=facts.tier,
        has_lesson=facts.has_lesson,
        has_figure=facts.has_figure,
        subject_kind=facts.subject_kind,
        mastery=float(state.get('mastery', PRIOR)),
        attempts=int(state.get('attempts', 0)),
        recent_accuracy=accuracy,
        top_error=top_error,
        elapsed_trend=elapsed_trend,
        recall=recall,
        stability_days=(float(state['stability']) if state.get('stability') is not None
                        else None),
        lapses=int(state.get('lapses', 0)),
        due_at=state.get('due_at'),
        last_correct=state.get('last_correct'),
        prerequisite_debt=debt,
        weak_prerequisites=weak,
        dependants=facts.dependant_count,
        unit_coverage=float(unit_coverage),
        project_status=project_status,
        simulation_touched=simulation_touched,
        session_minutes=float(session_minutes),
        recent_moves=tuple(recent_moves),
        move_history=dict(move_history or {}),
    )
