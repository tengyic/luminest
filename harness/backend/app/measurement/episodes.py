"""Turning a flat attempt log into the units measurement actually needs.

Why this exists
---------------
``Attempt`` rows are a stream: one row per graded answer, with a timestamp, a concept and
a correctness bit. Almost nothing useful is computable from that stream directly, because
every quantity worth reporting is a *ratio* - gain per hour, attempts to criterion, error
rate by opportunity number - and a ratio needs a denominator with a defensible boundary.

There is no session table, and ``Attempt`` carries no session id, so a lesson cannot be
looked up. It can, however, be *reconstructed*: activity separated by less than
:data:`~app.measurement.contracts.EPISODE_GAP_SECONDS` is one sitting, and that
reconstruction is deterministic, so the same log always yields the same episodes. Deriving
the boundary from data rather than storing a client-supplied one is not a workaround here,
it is the stronger choice: a client that reports "session: 7" can report it wrongly, and a
boundary that moves changes every efficiency ratio computed from it.

Two denominators, and they are not interchangeable
--------------------------------------------------
``solve_seconds`` sums only the time the client reported *inside* an answer. It is the
narrowest and most honest measure of time-on-task, and it is what a time-to-criterion
should use.

``engaged_seconds`` adds the gaps between consecutive answers, capped at
:data:`~app.measurement.contracts.IDLE_CAP_SECONDS` per gap: reading the explanation,
thinking before starting, reworking. It is an *upper bound* on time-on-task and the right
denominator for "gain per hour of the sitting", because excluding the reading time would
credit the harness with learning that happened during it.

Neither is wall-clock. Wall-clock is the number that makes efficiency look best, and it is
wrong for exactly the learner who leaves the window open.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from . import contracts

#: Fields read off an attempt row. Accepts either an ORM row or a mapping, so the same
#: segmentation runs on live data and on a benchmark fixture without a second code path.
_FIELDS = ('created_at', 'elapsed_seconds', 'concept_id', 'correct', 'mode',
           'question_id', 'confidence')


def as_dict(attempt: Any) -> dict[str, Any]:
    """Normalise an attempt row (ORM object or dict) into the fields this package reads.

    A mapping keeps every key it arrived with; only missing required fields are filled in.
    That is deliberate: a row that has already been through :func:`derive_aid` carries ``aid``
    and ``opportunity``, and stripping them here would silently reset segmentation and the
    learning curve to unlabelled data - the label would appear to work and would not.
    """
    if isinstance(attempt, Mapping):
        row = dict(attempt)
        for name in _FIELDS:
            row.setdefault(name, None)
        return row
    return {name: getattr(attempt, name, None) for name in _FIELDS}


def _seconds(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float('inf'), float('-inf')):  # NaN / inf
        return 0.0
    return max(0.0, number)


def _stamp(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def segment(attempts: Iterable[Any],
            gap: float = contracts.EPISODE_GAP_SECONDS) -> list[dict[str, Any]]:
    """Split an attempt stream into episodes, newest boundary rule described in the module.

    Attempts are sorted by timestamp first: the log arrives in submission order, which is
    *usually* the same thing, but a replayed or merged log need not be, and an out-of-order
    row would otherwise split one sitting into two and halve its measured rate.

    Returns one dict per episode with both denominators, the concept set, and the raw
    attempts so downstream estimators do not need to re-query.
    """
    rows = sorted((as_dict(attempt) for attempt in attempts), key=lambda row: _stamp(row['created_at']))
    if not rows:
        return []
    episodes: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = [rows[0]]
    for row in rows[1:]:
        previous = _stamp(current[-1]['created_at'])
        if _stamp(row['created_at']) - previous > gap:
            episodes.append(_summarise(current))
            current = [row]
        else:
            current.append(row)
    episodes.append(_summarise(current))
    return episodes


def _summarise(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """One episode's totals, with idle time separated from engaged time."""
    solve = sum(_seconds(row['elapsed_seconds']) for row in rows)
    engaged = solve
    for earlier, later in zip(rows, rows[1:]):
        between = _stamp(later['created_at']) - _stamp(earlier['created_at'])
        # Capped, not dropped: a 90-second pause to think is engaged, a 12-minute one is not.
        engaged += min(max(0.0, between), contracts.IDLE_CAP_SECONDS)
    start = _stamp(rows[0]['created_at'])
    end = _stamp(rows[-1]['created_at']) + _seconds(rows[-1]['elapsed_seconds'])
    answered = len(rows)
    correct = sum(1 for row in rows if row['correct'])
    concepts = {str(row['concept_id']) for row in rows if row['concept_id']}
    return {
        'started_at': start,
        'ended_at': end,
        'wall_seconds': round(max(0.0, end - start), 3),
        'solve_seconds': round(solve, 3),
        'engaged_seconds': round(engaged, 3),
        # What the wall clock would have claimed, so the difference is auditable rather
        # than implicit. Wall time minus engaged time is the idle the caps removed.
        'idle_seconds': round(max(0.0, end - start - engaged), 3),
        'answered': answered,
        'correct': correct,
        'accuracy': round(correct / answered, 4) if answered else None,
        'concept_ids': sorted(concepts),
        'attempts': list(rows),
    }


def learning_opportunities(attempts: Iterable[Any]) -> dict[str, list[dict[str, Any]]]:
    """Per-concept attempt sequences, in order, as the unit of a learning curve.

    One concept's opportunities are its own sequence of graded retrievals: opportunity 1 is
    the first time the learner ever answered it, opportunity *n* the *n*th. This ordering is
    what makes a rate estimable from a single person, and it must be per concept rather than
    global - averaging across concepts would mix a curve the learner climbed with curves they
    had not started, and the average of several curves is not any of them.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for attempt in sorted((as_dict(row) for row in attempts), key=lambda r: _stamp(r['created_at'])):
        concept = str(attempt.get('concept_id') or '')
        if not concept:
            continue
        grouped.setdefault(concept, []).append(attempt)
    for sequence in grouped.values():
        for index, attempt in enumerate(sequence, start=1):
            attempt['opportunity'] = index
    return grouped


def derive_aid(attempts: Sequence[dict[str, Any]],
               tutor_timestamps: Iterable[float] = (),
               lesson_timestamps: Iterable[float] = ()) -> list[dict[str, Any]]:
    """Attach an aid level to each attempt, from evidence that already exists.

    The harness has no hint button, so the support conditions that can manufacture a
    correct answer here are the ones that actually exist in the product:

    * **tutor turns** - a conversation with the model that may have stated the answer. This
      is the strongest confound and the one the 2024 evidence is about, so one turn during
      the window is enough to reclassify the attempt.
    * **feedback already shown** - a repeat of an item whose answer feedback has already
      been revealed. Withheld on exams and transfer tests, where feedback is not delivered
      until completion, which is exactly why those modes can supply unaided observations.
    * **lesson open** - lesson material presented in this episode before the attempt.
    * **item repetition** - the same item answered before, so a correct answer may be
      recognition of the item rather than retrieval of the idea.

    ``tutor_timestamps`` and ``lesson_timestamps`` are epoch seconds. An attempt is affected
    by a tutor turn or lesson view that occurred at or before it, never after: that direction
    is the difference between "help preceded this answer" and "help followed it", and only
    the first is a confound.
    """
    tutor_times = sorted(_stamp(value) for value in tutor_timestamps)
    lesson_times = sorted(_stamp(value) for value in lesson_timestamps)
    seen_first: dict[str, float] = {}
    labelled: list[dict[str, Any]] = []
    window = contracts.RECOGNITION_WINDOW_HOURS * 3600
    for attempt in sorted(attempts, key=lambda row: _stamp(row['created_at'])):
        at = _stamp(attempt['created_at'])
        question = str(attempt.get('question_id') or '')
        previous = seen_first.get(question)
        item_seen = previous is not None
        within_window = previous is not None and (at - previous) <= window
        # Feedback is withheld during a closed assessment, so a repeat there is not
        # feedback-aided. Every other mode has already shown the answer by the time a
        # repeat is possible.
        feedback_before = bool(within_window and str(attempt.get('mode')) not in {'exam', 'transfer'})
        tutor_turns = sum(1 for stamp in tutor_times if stamp <= at)
        lesson_open = any(stamp <= at for stamp in lesson_times)
        level = contracts.aid_level(tutor_turns=tutor_turns, lesson_open=lesson_open,
                                    feedback_before=feedback_before, item_seen=item_seen)
        row = dict(attempt)
        row['aid'] = level
        row['aid_reason'] = contracts.describe_aid(level)
        labelled.append(row)
        seen_first.setdefault(question, at)
    return labelled


def label_attempts(attempts: Iterable[Any],
                   tutor_timestamps: Iterable[float] = (),
                   lesson_timestamps: Iterable[float] = ()) -> list[dict[str, Any]]:
    """Convenience: normalise, then derive aid. The entry point report code should use."""
    return derive_aid([as_dict(row) for row in attempts],
                      tutor_timestamps=tutor_timestamps,
                      lesson_timestamps=lesson_timestamps)


def aid_by_episode(episodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Re-summarise episodes once attempts carry aid labels.

    The episode totals do not change - aid is a property of an observation, not of a
    sitting - but the unaided count per episode is what makes "this sitting produced two
    pieces of real evidence out of fifteen answers" visible.
    """
    out = []
    for episode in episodes:
        attempts = list(episode.get('attempts') or [])
        unaided = [row for row in attempts if contracts.unaided(str(row.get('aid')))]
        out.append({**episode,
                    'unaided_answered': len(unaided),
                    'unaided_correct': sum(1 for row in unaided if row.get('correct')),
                    'aid_mix': contracts.summarise_aid(attempts)})
    return out


__all__ = ['aid_by_episode', 'as_dict', 'derive_aid', 'label_attempts',
           'learning_opportunities', 'segment']
