"""The positive half of the loop: streaks, milestones, badges, the certificate.

Every rule here is a *record of something the learner did*, never a penalty for something
they did not do. That is the whole point of the module, and it is why ``strike`` lives here
rather than beside the supervisor: a streak counts consecutive days of work, and a missed
day simply ends the count. There is no negative counterpart that takes something away.

Two rules the spec is explicit about, and that are easy to get wrong:

* **A question streak counts small practice items only.** Unit tests and diagnostic tests
  are assessments; paying a streak bonus for them changes how a learner answers them, which
  is the opposite of what an assessment is for. ``quiz_streak`` refuses those contexts by
  name instead of trusting a caller to filter them.
* **A streak is not a nudge.** It is announced when it grows (5, 10, 15 days; 5, 10 correct
  in a row) and it says nothing when it breaks. A system that mourns a broken streak is
  using loss aversion to keep a learner at a screen, and that is not a teaching motive.

Pure functions over data the app already stores; no database, no clock of its own.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

#: Day counts that earn an announcement, and the label that goes with each.
STREAK_MILESTONES = {5: 'five days in a row', 10: 'ten days in a row', 15: 'fifteen days in a row'}

#: Consecutive correct *practice* answers that earn an announcement.
QUIZ_MILESTONES = {5: 'five in a row', 10: 'ten in a row'}

#: Item contexts that count toward a question streak. Anything else - a unit test, a
#: diagnostic - is an assessment and is excluded by design, not by accident.
STREAK_CONTEXTS = ('quiz', 'practice')

#: Mastery crossings worth telling the learner about.
NODE_MILESTONES = (0.80, 1.00)


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or '').strip()[:10]
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def streak(days: Iterable[Any], *, today: Any = None) -> dict[str, Any]:
    """Consecutive-day streak from the days a learner actually studied.

    A streak that ends yesterday is still current: the day is not over, and telling a
    learner at 09:00 that their streak is broken is both wrong and demoralising.
    """
    today = _as_date(today) or date.today()
    unique = sorted({d for d in (_as_date(day) for day in days) if d is not None})
    if not unique:
        return {'current': 0, 'longest': 0, 'last_day': None, 'milestone': None,
                'announce': None}

    longest = run = 1
    for previous, current in zip(unique, unique[1:]):
        run = run + 1 if current - previous == timedelta(days=1) else 1
        longest = max(longest, run)

    last = unique[-1]
    if last < today - timedelta(days=1):
        current = 0
    else:
        current = 1
        for previous, later in zip(reversed(unique[:-1]), reversed(unique)):
            if later - previous == timedelta(days=1):
                current += 1
            else:
                break
    milestone = STREAK_MILESTONES.get(current)
    return {'current': current, 'longest': max(longest, current),
            'last_day': last.isoformat(),
            'milestone': milestone,
            'announce': (f'{current} days in a row - {milestone}.' if milestone else None)}


def quiz_streak(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Consecutive correct practice answers, counting only practice contexts.

    ``results`` is newest-last: ``[{'context': 'quiz', 'correct': True}, ...]``. Items in
    an assessment context are skipped entirely - they neither extend nor break the count -
    because the streak is a practice habit, and a test should not be able to break it.
    """
    count = 0
    for row in results:
        context = str(row.get('context') or '').strip().casefold()
        if context not in STREAK_CONTEXTS:
            continue
        if bool(row.get('correct')):
            count += 1
        else:
            break
    milestone = QUIZ_MILESTONES.get(count)
    return {'current': count, 'milestone': milestone,
            'announce': (f'{count} correct practice answers in a row - {milestone}.'
                         if milestone else None),
            'counts': list(STREAK_CONTEXTS)}


def node_milestone(before: float, after: float) -> dict[str, Any] | None:
    """Whether this update crossed a mastery milestone, and which one.

    Crossing is compared against the previous value, so a concept that sits at 0.85 for a
    week announces once rather than on every attempt.
    """
    before, after = float(before or 0.0), float(after or 0.0)
    if after <= before:
        return None
    for threshold in NODE_MILESTONES:
        if before < threshold <= after:
            return {'threshold': threshold,
                    'announce': (f'This concept reached {threshold:.0%}.'
                                 if threshold < 1.0 else
                                 'This concept is fully mastered.')}
    return None


def badges(*, days_studied: int = 0, longest_streak: int = 0, nodes_mastered: int = 0,
           units_complete: int = 0, quizzes_in_a_row: int = 0) -> list[dict[str, Any]]:
    """Conditional badges, each naming the condition that earned it.

    Ordered from cheapest to hardest so a UI can show the next one as a target rather than
    showing a wall of grey.
    """
    earned: list[dict[str, Any]] = []

    def award(name: str, condition: str, met: bool) -> None:
        if met:
            earned.append({'name': name, 'condition': condition})

    award('First session', 'study on one day', days_studied >= 1)
    award('Week one', 'study on seven different days', days_studied >= 7)
    award('Habit', 'a five-day streak', longest_streak >= 5)
    award('Fortnight', 'a ten-day streak', longest_streak >= 10)
    award('Node master', 'master one concept', nodes_mastered >= 1)
    award('Deep roots', 'master ten concepts', nodes_mastered >= 10)
    award('Clean run', 'five practice answers in a row', quizzes_in_a_row >= 5)
    award('Unit complete', 'finish a unit', units_complete >= 1)
    return earned


def certificate(units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Whether the course certificate is earned, and what is still outstanding.

    A unit counts only when its test is passed *and* its assignments are in - the spec's
    "TEST & Assignments" - so a learner cannot reach the certificate by skipping the work
    that the certificate is supposed to attest to.
    """
    total = len(units)
    passed = [u for u in units
              if bool(u.get('test_passed')) and bool(u.get('assignments_complete'))]
    outstanding = [str(u.get('unit') or u.get('id') or '?') for u in units
                   if u not in passed]
    return {'earned': total > 0 and len(passed) == total,
            'units_total': total, 'units_complete': len(passed),
            'outstanding': outstanding,
            'announce': ('Course certificate earned.' if total and len(passed) == total
                         else f'{len(passed)} of {total} units complete.')}
