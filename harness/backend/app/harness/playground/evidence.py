"""Turning a completed game into an observation the harness can actually use.

This module is the answer to the question the playground exists to raise: *does
playing a game teach the harness anything?* For a third-party simulation the answer
is no, permanently - :mod:`app.simulation_map` marks PhET and Gizmos cards
``observable: false`` because PhET's free tier exposes no telemetry and Gizmos is a
per-seat product we may not instrument. A first-party game is different: it runs in
our own web view and reports what the learner committed to.

Two things are recorded, and keeping them separate is the point
--------------------------------------------------------------
1. A :class:`~app.db.PlaygroundRun` row. The honest, self-contained record: which
   game, which task, right or wrong, how many tries, how long, and the game's own
   telemetry. It is *not* an ``Attempt``, because an attempt answers a vetted item
   from the question bank under a receipt, and a game answer should not borrow that
   authority. A reviewer reading the two tables can tell them apart.

2. An update to the learner's mastery state for the concept, through the **same**
   ``learning.update`` and ``propagate_implicit_credit`` calls the question route
   uses. This is what makes the playground count. It is the same estimator, on the
   same state, so a run cannot inflate mastery through a private path - it moves the
   number by exactly as much as an equivalent question would.

The row stores mastery before and after, so the second claim is auditable from the
database rather than asserted in a docstring.

What is deliberately *not* done here
------------------------------------
A sandbox archetype (``scored=False``) produces no outcome at all, and a game whose
concept is outside the learner's course is refused. Both refusals exist for the same
reason: an observation the harness cannot attribute to a concept it is tracking is
not evidence, it is noise with a timestamp.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from sqlalchemy import select

from ... import learning
from ...db import PlaygroundRun, State, now_ts, uid

#: Words too common to prove a concept match. The same closed function-word list
#: ``simulation_map`` uses - no subject vocabulary is hardcoded here either.
_STOPWORDS = frozenset({
    'the', 'and', 'for', 'with', 'from', 'into', 'that', 'this', 'are', 'was', 'has',
    'its', 'their', 'how', 'why', 'what', 'when', 'where', 'using', 'use', 'used',
    'basics', 'intro', 'introduction', 'explore', 'exploring', 'model', 'models',
})


def _tokens(text: str) -> set[str]:
    """Content words with a light plural fold, so "fraction" matches "fractions"."""
    words = re.split(r'[^a-z0-9]+', (text or '').casefold())
    out: set[str] = set()
    for word in words:
        if len(word) <= 2 or word in _STOPWORDS:
            continue
        if len(word) > 4 and word.endswith('ies'):
            word = word[:-3] + 'y'
        elif len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
            word = word[:-1]
        if len(word) > 2 and word not in _STOPWORDS:
            out.add(word)
    return out


def _overlap(left: str, right: str) -> float:
    """How much of the shorter phrase the longer one covers.

    The overlap coefficient rather than Jaccard, for the reason recorded in
    ``simulation_map``: a game's concept is a terse phrase and a curriculum concept is
    another terse phrase, but they are rarely the same length, and Jaccard punishes
    that difference so hard that a correct match scores near zero.
    """
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def resolve_concept(game: Mapping[str, Any],
                    concepts: Mapping[str, Mapping[str, Any]],
                    *, threshold: float = 0.6) -> tuple[str | None, str]:
    """Which concept in the learner's course does this game teach? Returns ``(id, why)``.

    Three attempts, in order of how much they can be trusted:

    1. An explicit ``concept_id`` in the pack. Unambiguous, and the only path that
       cannot be wrong.
    2. An exact case-insensitive title match.
    3. A token-overlap match above ``threshold``.

    The threshold is high on purpose. Attribution decides whether a run moves a
    learner's mastery estimate, and a loose match would silently credit the wrong
    concept - which is worse than not crediting at all, because it is invisible. When
    nothing clears the bar the run is still recorded; it simply does not feed mastery,
    and the reason says so.
    """
    if not concepts:
        return None, 'the learner\'s course has no concepts to attribute this to'
    declared = str(game.get('concept_id') or '')
    if declared:
        if declared in concepts:
            return declared, 'the pack declares this concept id explicitly'
        return None, (f'the pack declares concept id {declared!r}, which is not in the '
                      f'learner\'s course')
    title = str(game.get('concept') or '')
    if not title:
        return None, 'the game declares no concept'
    for concept_id, entry in concepts.items():
        if str(entry.get('title') or '').strip().casefold() == title.strip().casefold():
            return concept_id, 'exact title match against the learner\'s course'
    scored = sorted(((_overlap(title, str(entry.get('title') or '')), concept_id)
                     for concept_id, entry in concepts.items()), reverse=True)
    if scored and scored[0][0] >= threshold:
        return scored[0][1], (f'title match to {scored[0][0]:.2f} on word overlap; '
                              'above the attribution threshold')
    best = f'{scored[0][0]:.2f}' if scored else 'nothing'
    return None, (f'no concept in the learner\'s course matches {title!r} closely '
                  f'enough (best overlap {best}, threshold {threshold}); the run is '
                  f'recorded but does not move mastery')


def _seconds(elapsed_ms: Any) -> float:
    """Milliseconds from the browser to the seconds ``learning.update`` expects.

    Clamped, because the elapsed time crosses a trust boundary: a page that reports a
    negative or absurd duration would otherwise distort the memory model's estimate of
    how well something was remembered. A five-minute ceiling is generous for one task
    in a game and is the same order as the answer route's own expectations.
    """
    try:
        value = float(elapsed_ms)
    except (TypeError, ValueError):
        return 0.0
    if value < 0:
        return 0.0
    return min(value, 300_000.0) / 1000.0


def record(db, user, *, slug: str, artifact_id: str, archetype: str, concept_id: str,
           correct: bool, tries: Any = 1, elapsed_ms: Any = None, task_id: str = '',
           detail: Mapping[str, Any] | None = None,
           feed_mastery: bool = True) -> dict[str, Any]:
    """Record one committed, scored task. Returns the row as a plain dict.

    ``concept_id`` must already be resolved and verified against the learner's own
    course by the caller: this function will happily record a run for a concept it
    cannot attribute, and the caller is where that check belongs because only the
    caller has the course table.
    """
    now = now_ts()
    try:
        tries_value = max(1, int(tries))
    except (TypeError, ValueError):
        tries_value = 1
    before: float | None = None
    after: float | None = None
    if feed_mastery:
        state_row = db.scalar(select(State).where(State.user_id == user.id,
                                                  State.concept_id == concept_id)
                              .with_for_update())
        if state_row is None:
            state_row = State(user_id=user.id, concept_id=concept_id, data={})
            db.add(state_row)
        before = state_row.data.get('mastery')
        state_row.data = learning.update(state_row.data, bool(correct),
                                         _seconds(elapsed_ms), now)
        # The same FIRe-style implicit credit the question route applies: a success
        # here is weak evidence the prerequisites are solid too.
        learning.propagate_implicit_credit(db, user.id, concept_id, state_row.data, now)
        after = state_row.data.get('mastery')
    run_id = uid()
    db.add(PlaygroundRun(
        id=run_id, user_id=user.id, artifact_id=str(artifact_id or ''),
        slug=str(slug), archetype=str(archetype), concept_id=concept_id,
        task_id=str(task_id or ''), correct=bool(correct), tries=tries_value,
        elapsed_ms=int(elapsed_ms) if isinstance(elapsed_ms, (int, float)) else None,
        mastery_before=before, mastery_after=after,
        detail=dict(detail or {}), created_at=now))
    db.commit()
    return {
        'id': run_id, 'slug': slug, 'archetype': archetype, 'concept_id': concept_id,
        'task_id': task_id, 'correct': bool(correct), 'tries': tries_value,
        'elapsed_ms': elapsed_ms, 'mastery_before': before, 'mastery_after': after,
        'mastery_delta': (round(after - before, 5)
                          if isinstance(before, (int, float)) and isinstance(after, (int, float))
                          else None),
        'detail': dict(detail or {}),
        'note': ('This is a playground run, not a graded attempt: the answer key belongs '
                 'to the game. It moved the same mastery estimate a question would.'),
    }


def recent(db, user, *, limit: int = 20) -> list[dict[str, Any]]:
    """The learner's most recent runs, newest first."""
    rows = db.scalars(select(PlaygroundRun).where(PlaygroundRun.user_id == user.id)
                      .order_by(PlaygroundRun.created_at.desc()).limit(max(1, min(limit, 200))))
    return [{'id': row.id, 'slug': row.slug, 'archetype': row.archetype,
             'concept_id': row.concept_id, 'task_id': row.task_id,
             'correct': row.correct, 'tries': row.tries, 'elapsed_ms': row.elapsed_ms,
             'mastery_before': row.mastery_before, 'mastery_after': row.mastery_after,
             'created_at': row.created_at} for row in rows]


def summary(db, user) -> dict[str, Any]:
    """Counts over the learner's playground history.

    Per-game accuracy is reported with its denominator, because "100% correct" from a
    single run and from forty runs are not the same claim and a bare percentage cannot
    tell them apart.
    """
    rows = list(db.scalars(select(PlaygroundRun).where(PlaygroundRun.user_id == user.id)))
    by_slug: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_slug.setdefault(row.slug, {'runs': 0, 'correct': 0, 'tries': 0,
                                               'archetype': row.archetype})
        bucket['runs'] += 1
        bucket['correct'] += int(bool(row.correct))
        bucket['tries'] += int(row.tries or 1)
    games = [{'slug': slug, **bucket,
              'accuracy': round(bucket['correct'] / bucket['runs'], 3) if bucket['runs'] else None}
             for slug, bucket in sorted(by_slug.items())]
    return {
        'runs': len(rows),
        'games_played': len(by_slug),
        'by_game': games,
        'note': 'Accuracy is reported with its run count: one run and forty runs are not '
                'the same evidence, and a bare percentage cannot say which it is.',
    }


def describe() -> dict[str, Any]:
    """The module's posture, for the transparency panel."""
    return {
        'recorded': 'A PlaygroundRun row: game, task, correctness, tries, elapsed time, '
                    'the game\'s own telemetry, and mastery before and after.',
        'not_recorded': 'Continuous readouts while a learner explores. A readout is the '
                        'simulation talking to the screen; only a committed answer is an '
                        'observation.',
        'mastery_effect': 'A run moves the same mastery state, through the same estimator, '
                          'that answering a question does. The before/after values are '
                          'stored so this is checkable rather than claimed.',
        'distinction_from_attempts': 'A playground run is not an Attempt. An attempt '
                                     'answers a vetted item from the question bank under a '
                                     'receipt; a run answers the game\'s own question. They '
                                     'are stored separately so the two cannot be confused.',
        'refusals': [
            'A sandbox archetype (scored=false) reports no outcome and records nothing.',
            'A concept outside the learner\'s own course is refused before recording.',
        ],
    }
