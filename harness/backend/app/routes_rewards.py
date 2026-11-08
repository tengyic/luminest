"""HTTP surface for the positive record: ``/api/v1/rewards``.

Thin on purpose, like :mod:`app.routes_supervision`: the rules live in
:mod:`app.harness.teaching.motivation`, the presentation lives in
:mod:`app.harness.rewards`, and this module only *reads the caller's own stored data* and
serialises the result.

Why a route at all, rather than letting the client compute its own streak: a client that
counts its own streak also decides what deserves a celebration, and the one thing a reward
system must not do is award something the backend withheld. ``motivation.quiz_streak``
refuses test and diagnostic items by name; if the client did the counting, that rule would
be a suggestion.

Two boundaries:

**Read-only.** ``GET`` never writes, never marks an event "seen", never stores a queue. The
id in each event is the idempotency key and the client keeps the seen-set, so a retry or a
second tab cannot double-celebrate and the server needs no state to prevent it.

**No client claims.** Nothing here takes the learner's word for a streak, a mastery value or
a correct answer. Every number is read from ``attempts``, ``learning_states`` and
``procedure_runs``, which are written by the teaching loop itself.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select

from .db import Attempt, ProcedureRun, State, now_ts
#: The same bearer dependency the other feature routers use. Imported rather than pasted:
#: a third copy of the auth check is a third place for it to drift.
from .routes_supervision import authenticated
from .security import require_principal


router = APIRouter(dependencies=[Depends(require_principal("api", 180))])

API = '/api/v1/rewards'

#: How many recent attempts to read for the practice run. A run of ten is the deepest
#: milestone, so this only has to be comfortably larger than the largest milestone.
RECENT_ATTEMPTS = 50

#: Stored attempt modes mapped onto the vocabulary ``motivation.STREAK_CONTEXTS`` speaks.
#:
#: ``review`` is scheduled retrieval *practice* - small items, no grade - so it counts as
#: practice. Assessments are passed through unchanged on purpose: ``quiz_streak`` refuses
#: them by name, and mapping them to something it accepts would defeat the rule that a test
#: cannot buy a streak.
CONTEXT = {'review': 'practice'}


def _day(timestamp: float | None):
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp), timezone.utc).date()


@router.get(API + '/events')
def reward_events(principal=Depends(authenticated)):
    """Every reward event this learner's own history currently justifies."""
    from .harness import rewards
    from .harness.teaching import motivation

    db, user = principal

    attempts = list(db.scalars(
        select(Attempt).where(Attempt.user_id == user.id)
        .order_by(Attempt.created_at.desc()).limit(RECENT_ATTEMPTS)))

    runs = list(db.scalars(
        select(ProcedureRun).where(ProcedureRun.user_id == user.id)
        .order_by(ProcedureRun.updated_at.desc()).limit(RECENT_ATTEMPTS)))

    # A day counts if the learner answered something or ran a lesson that day. Reading only
    # attempts would call a deck-only evening a missed day, which is both wrong and the kind
    # of wrong that makes a streak feel arbitrary.
    days = [day for day in (_day(row.created_at) for row in attempts) if day]
    days += [day for day in (_day(row.updated_at) for row in runs) if day]

    # `attempts` is newest-first; the streak rule reads newest-last.
    quiz_results = [{'context': CONTEXT.get(str(row.mode or '').casefold(), str(row.mode or '')),
                     'correct': bool(row.correct)}
                    for row in reversed(attempts)]

    concepts = []
    for row in db.scalars(select(State).where(State.user_id == user.id)):
        data = dict(getattr(row, 'data', None) or {})
        if 'mastery' not in data:
            continue
        concepts.append({'concept_id': row.concept_id, 'mastery': data['mastery']})

    reading = motivation.streak(days)
    counters = {
        'days_studied': len(set(days)),
        'longest_streak': int(reading['longest']),
        'nodes_mastered': sum(1 for row in concepts
                              if float(row['mastery'] or 0) >= max(motivation.NODE_MILESTONES[:1])),
        # Unit completion is not derivable from attempts - it needs the assessment record -
        # so it is left at zero rather than guessed. The badge simply does not fire here.
        'units_complete': 0,
        'quizzes_in_a_row': int(motivation.quiz_streak(quiz_results)['current']),
    }

    events = rewards.events(days=days, quiz_results=quiz_results, concepts=concepts,
                            counters=counters)
    return {'events': events, 'count': len(events),
            'generated_at': datetime.fromtimestamp(now_ts(), timezone.utc).isoformat(),
            'posture': rewards.describe()['posture']}
