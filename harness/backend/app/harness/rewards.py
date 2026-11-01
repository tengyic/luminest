"""Milestones as *things the client can animate*.

:mod:`app.harness.teaching.motivation` owns the rules - what counts, which day counts,
which threshold earns an announcement. This module owns the other half of the question:
when a rule fires, what exactly should appear on screen, and with what weight of ceremony.

Keeping them apart matters because the rules are pedagogy and the presentation is taste.
A designer should be able to retune the celebration without touching the definition of a
streak, and a pedagogue should be able to change a milestone without opening SwiftUI.

The contract is deliberately dumb data. An event is a flat dict the client renders; it
never recomputes a threshold, and it never decides *whether* to celebrate. That is what
keeps a celebration from appearing for something the backend withheld - notably a question
streak earned in a test, which ``motivation.quiz_streak`` refuses by name.

Two properties are load-bearing:

* **``id`` is an idempotency key.** The same achievement always produces the same id
  (``streak:2026-10-24:5``, ``node:fractions:0.8``), so a retry, a second poll, or a
  client that reconnects cannot double-celebrate. The client shows each id once.
* **Tier is a weight, not a size.** ``toast`` is a nudge, ``banner`` is praise,
  ``celebrate`` is a moment. When several events land together the client shows the
  heaviest first, so a 10-day streak is not buried under a "today counted" toast.

Nothing here is a penalty. There is no event kind for a broken streak, a missed day, or a
dropped score, and adding one would be a design change rather than a feature.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .teaching import motivation

#: The three weights of ceremony, lightest to heaviest.
TIERS = ('toast', 'banner', 'celebrate')

#: Which tier wins when several events queue at once (lower is shown first).
TIER_ORDER = {'celebrate': 0, 'banner': 1, 'toast': 2}

#: ``kind -> (tier, mascot sprite, sound)``. The single place a kind becomes a look.
#:
#: The mascot names are ``LumiSprite`` raw values, so a client can resolve the sprite by
#: name and never hardcode its own table. The sound names are the synthesized recipes in
#: ``SoundBank``; a client that has no audio falls back silently rather than failing.
PRESENTATION: dict[str, tuple[str, str, str]] = {
    # A day counted, no milestone: quiet, daily, not a celebration.
    'streak_notification': ('toast', 'greeting', 'chime_soft'),
    # 5 / 10 / 15 consecutive days: the big one.
    'streak_milestone': ('celebrate', 'celebrating', 'fanfare'),
    # A practice run of correct answers. Promoted to `celebrate` at ten.
    'question_strike': ('banner', 'celebrating', 'chime'),
    # Mastery crossed 0.80 / 1.00 for a concept. Promoted at full mastery.
    'node_milestone': ('banner', 'celebrating', 'chime'),
    # A composite condition from `motivation.badges()`.
    'badge': ('celebrate', 'celebrating', 'badge'),
    # Emitted by the interruption path, not by this module - see `events()`.
    'unactive_notification': ('toast', 'listening', 'chime_soft'),
    'active_watch': ('toast', 'greeting', 'sparkle'),
}

#: Kinds this module can produce from stored learning data.
EMITTED_HERE = ('streak_notification', 'streak_milestone', 'question_strike',
                'node_milestone', 'badge')

#: Kinds that belong to the interruption path (supervision / classroom), which already has
#: the signals this module would otherwise have to invent. Declared here so a client has one
#: table for every kind it may ever be handed, produced elsewhere.
EMITTED_ELSEWHERE = ('unactive_notification', 'active_watch')

#: The stable prefix of an event id. ``streak_milestone`` and ``streak_notification`` are
#: different achievements - one is a five-day run, the other is "a Tuesday counted" - so
#: they must not share an id namespace or the client would suppress one with the other.
ID_PREFIX = {
    'streak_notification': 'day',
    'streak_milestone': 'streak',
    'question_strike': 'quiz',
    'node_milestone': 'node',
    'badge': 'badge',
    'unactive_notification': 'idle',
    'active_watch': 'focus',
}


def _event(kind: str, value: float, *, key: str, title: str, announce: str,
           tier: str | None = None, sound: str | None = None) -> dict[str, Any]:
    """One event, with its presentation filled in from :data:`PRESENTATION`."""
    default_tier, mascot, default_sound = PRESENTATION[kind]
    return {
        'id': f'{ID_PREFIX[kind]}:{key}',
        'kind': kind,
        'value': value,
        'tier': tier or default_tier,
        'mascot': mascot,
        'sound': sound or default_sound,
        'title': title,
        'announce': announce,
    }


def events(*, days: Iterable[Any] = (), quiz_results: Sequence[Mapping[str, Any]] = (),
           concepts: Iterable[Mapping[str, Any]] = (), counters: Mapping[str, int] | None = None,
           today: Any = None) -> list[dict[str, Any]]:
    """Every reward event this learner's stored data currently justifies.

    ``days`` are the days studied (any date-like), ``quiz_results`` are practice items
    newest-last, ``concepts`` are ``{'concept_id', 'mastery'}`` rows. ``counters`` feeds
    :func:`motivation.badges` when a caller has those totals.

    A day that counted and *also* hit a milestone produces one event, not two: the
    milestone is the better sentence, and two cards for the same fact reads as a bug.

    ``unactive_notification`` and ``active_watch`` are **not** produced here even though
    they appear in :data:`PRESENTATION`. Both describe a *moment inside a session* - idle
    time, share of the window spent active - which the supervisor and the classroom engine
    already measure from live signals. Recomputing them from stored attempts would be a
    second, worse measurement of the same thing.
    """
    found: list[dict[str, Any]] = []

    reading = motivation.streak(days, today=today)
    if reading['current']:
        if reading['milestone']:
            found.append(_event(
                'streak_milestone', reading['current'],
                key=f"{reading['last_day']}:{reading['current']}",
                title=f"{reading['current']} days in a row",
                announce=reading['announce']))
        else:
            found.append(_event(
                'streak_notification', reading['current'], key=str(reading['last_day']),
                title='Today counted', announce='A day of practice recorded.'))

    quiz = motivation.quiz_streak(quiz_results)
    if quiz['milestone']:
        # Ten correct is the same achievement as five, only further along, so it gets the
        # heavier ceremony rather than the same banner twice.
        ten = max(motivation.QUIZ_MILESTONES)
        found.append(_event(
            'question_strike', quiz['current'], key=str(quiz['current']),
            title=f"{quiz['current']} correct in a row", announce=quiz['announce'],
            tier='celebrate' if quiz['current'] >= ten else None,
            sound='fanfare' if quiz['current'] >= ten else None))

    for row in concepts:
        concept_id = str(row.get('concept_id') or '').strip()
        if not concept_id:
            continue
        try:
            mastery = float(row.get('mastery') or 0.0)
        except (TypeError, ValueError):
            continue
        reached = [t for t in motivation.NODE_MILESTONES if mastery >= t]
        if not reached:
            continue
        # Only the highest threshold reached: a concept at 1.00 announces full mastery,
        # not 0.80 followed by 1.00, because the learner never sat between them.
        threshold = max(reached)
        # Ask the rule module what *crossing this threshold* says, rather than restating
        # its wording here: `before` sits just below so exactly one threshold is crossed.
        crossing = motivation.node_milestone(threshold - 0.01, threshold)
        found.append(_event(
            'node_milestone', threshold, key=f'{concept_id}:{threshold:g}',
            title=(f'{concept_id} mastered' if threshold >= 1.0
                   else f'{concept_id} at {threshold:.0%}'),
            announce=(crossing or {}).get('announce', ''),
            tier='celebrate' if threshold >= 1.0 else None,
            sound='fanfare' if threshold >= 1.0 else None))

    if counters:
        for badge in motivation.badges(**dict(counters)):
            found.append(_event(
                'badge', 1, key=str(badge['name']), title=str(badge['name']),
                announce=f"Badge earned - {badge['name']}: {badge['condition']}."))

    found.sort(key=lambda event: TIER_ORDER.get(str(event['tier']), 9))
    return found


def describe() -> dict[str, Any]:
    """The presentation table, so a client or a designer can read it without Swift."""
    return {'tiers': list(TIERS), 'tier_order': dict(TIER_ORDER),
            'presentation': {kind: {'tier': tier, 'mascot': mascot, 'sound': sound}
                             for kind, (tier, mascot, sound) in PRESENTATION.items()},
            'emitted_here': list(EMITTED_HERE),
            'emitted_elsewhere': list(EMITTED_ELSEWHERE),
            'posture': 'Every event records something the learner did. There is no kind '
                       'for a broken streak, a missed day or a lost score.'}
