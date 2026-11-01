"""The retrieval schedule: which concepts are due, in which order.

Adapted from Anki's FSRS scheduler (ankitects/anki, ~31k stars, verified
2026-10-13). Two mechanisms were adopted and re-implemented against this app's own
FSRS-6 model rather than copied:

1. **Due at the desired-retention point.** A review is scheduled for the moment
   retrievability ``R`` decays to the configured desired retention (default 0.9).
   This is Bjork's desirable difficulty in schedulable form: reviewing early (R
   high) is easy and adds little stability; reviewing late (R low) is a lapse.
   ``is_due`` reads the same ``app.memory`` forgetting curve the scheduler uses, so
   the teacher's calendar and the app's review clock cannot disagree.

2. **Weakest memory first, interleaved.** Among due concepts the one whose memory
   has decayed furthest is served first - within a session that is the cheaper
   rescue. New material is interleaved one concept at a time rather than batched,
   because a block of same-session study of one idea feels fluent and stores far
   less than the same total time spread across ideas (the spacing effect the
   interleaving implements).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ...memory import recall_probability


@dataclass(frozen=True)
class ReviewItem:
    """One entry on the session's retrieval calendar."""

    concept_id: str
    recall: float | None          # FSRS-6 R now; None = never reviewed
    stability_days: float | None
    lapses: int
    due: bool
    new: bool = False             # never seen: scheduled for first exposure

    def to_dict(self) -> dict[str, Any]:
        return {'concept_id': self.concept_id,
                'recall': None if self.recall is None else round(self.recall, 4),
                'stability_days': (None if self.stability_days is None
                                   else round(self.stability_days, 3)),
                'lapses': self.lapses, 'due': self.due, 'new': self.new}


@dataclass(frozen=True)
class RetrievalPlan:
    """The ordered session calendar: what to review, when to interleave new work."""

    items: tuple[ReviewItem, ...] = ()
    new_remaining: tuple[str, ...] = ()
    #: Why this order - kept with the plan so a reviewer can audit the schedule.
    rationale: str = ''

    @property
    def reviews(self) -> tuple[ReviewItem, ...]:
        return tuple(item for item in self.items if not item.new)

    def concept_ids(self) -> tuple[str, ...]:
        return tuple(item.concept_id for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {'items': [i.to_dict() for i in self.items],
                'new_remaining': list(self.new_remaining), 'rationale': self.rationale}


def is_due(state: Mapping[str, Any] | None, now: float,
           desired_retention: float = 0.9) -> bool:
    """Due when retrievability has decayed to the desired-retention point.

    Two due signals are honoured, and the *earlier* one wins, because both mean
    the same thing in different evidence states: the scheduler's own ``due_at``
    (set by :func:`app.memory.due_time`), and the direct forgetting-curve check
    ``R(now) <= desired_retention``. The direct check covers states seeded outside
    the scheduler (legacy Leitner hand-offs, implicit-credit seeds) where
    ``due_at`` was never written - a review clock that silently ignores those
    states lets the taught concepts rot while nothing looks due.
    """
    if not state:
        return False
    due_at = state.get('due_at')
    if due_at is not None and float(due_at) <= now:
        return True
    if state.get('stability') is None or state.get('last_review') is None:
        return False
    return recall_probability(state, now) <= desired_retention


def due_concepts(states: Mapping[str, Mapping[str, Any]], now: float,
                 desired_retention: float = 0.9) -> list[ReviewItem]:
    """Every concept whose memory is due, weakest first.

    Ordering is by ascending recall (the most-forgotten first), with lapses and the
    concept id as deterministic tie-breaks - two runs with the same states must
    produce the same session, or the schedule cannot be reviewed after the fact.
    Concepts never reviewed are not "due": with no stability there is no forgetting
    curve to be on the wrong side of, and scheduling them as reviews would burn the
    session re-teaching what was never taught. They enter through ``plan_retrieval``
    as new material instead.
    """
    items: list[ReviewItem] = []
    for concept_id, state in sorted(states.items()):
        state = state or {}
        if state.get('stability') is None:
            continue
        recall = recall_probability(state, now)
        items.append(ReviewItem(
            concept_id=concept_id,
            recall=recall,
            stability_days=(float(state['stability'])
                            if state.get('stability') is not None else None),
            lapses=int(state.get('lapses', 0)),
            due=is_due(state, now, desired_retention)))
    due = [item for item in items if item.due]
    due.sort(key=lambda i: ((i.recall if i.recall is not None else 1.0), -i.lapses,
                            i.concept_id))
    return due


def plan_retrieval(states: Mapping[str, Mapping[str, Any]], now: float,
                   config, *, new_concepts: Sequence[str] = ()) -> RetrievalPlan:
    """Build the session calendar: due reviews interleaved with capped new material.

    ``states`` maps every known concept id to its stored learner state;
    ``new_concepts`` is the ordered list of never-reviewed concepts the course
    offers next (the caller applies prerequisite gating - see
    :mod:`app.harness.teaching.policy`). Interleaving inserts one new concept after
    every ``interleave_every`` reviews rather than front-loading novelty, so a
    session alternates retrieval (durable, cheap) with exposure (expensive,
    fragile) instead of front-loading the fragile half.
    """
    desired = config.desired_retention
    reviews = due_concepts(states, now, desired)[:max(0, config.per_session)]
    fresh = [c for c in new_concepts if c not in states][:config.max_new_per_session]
    remaining = [c for c in new_concepts if c not in states][config.max_new_per_session:]

    items: list[ReviewItem] = []
    new_queue = list(fresh)
    since_new = 0
    for review in reviews:
        # Cap reached early if the review list itself is short: interleave only
        # while there are both reviews left and new material left to place.
        if new_queue and since_new >= max(1, config.interleave_every):
            concept_id = new_queue.pop(0)
            items.append(ReviewItem(concept_id, recall=None,
                                    stability_days=None, lapses=0, due=False, new=True))
            since_new = 0
        items.append(review)
        since_new += 1
    for concept_id in new_queue:  # leftover new material still fits the cap
        items.append(ReviewItem(concept_id, recall=None, stability_days=None,
                                lapses=0, due=False, new=True))
    rationale = (
        f'{len(reviews)} review(s) due at desired retention {desired:.2f}, served '
        f'weakest-memory first; {len(fresh)} new concept(s) interleaved after '
        f'every {config.interleave_every} review(s); {len(remaining)} new concept(s) '
        f'held for later sessions.')
    return RetrievalPlan(items=tuple(items), new_remaining=tuple(remaining),
                         rationale=rationale)
