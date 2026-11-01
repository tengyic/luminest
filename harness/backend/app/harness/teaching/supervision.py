"""Whether to interrupt at all: the session supervisor.

``policy.py`` decides *what to teach next*. ``procedure.py`` decides *which activities a
lesson runs*. This module answers the question underneath both of them: **should the tutor
say anything right now, and if so, what kind of thing** - given how the learner has been
behaving for the last few minutes.

The distinction matters because the failure mode of a tutoring system is not being wrong
about the subject. It is talking when it should have been quiet, or staying quiet when the
learner has been staring at the same paragraph for six minutes.

Inputs are signals the client already has: idle time, scroll and click counts, how far
through the plan the lesson is, the rest the learner has taken, the mastery belief the
teaching core already computes (:class:`~app.harness.teaching.evidence.LearnerEvidence`),
and how the last answer compared to that learner's own average. Nothing here opens a
socket, reads a camera or needs a model, so the supervisor is real offline.

Three positions this module takes, because they are the difference between a tutor and a
proctor:

* **Away is not guilt.** An idle window is a fact about a screen, not about a person. The
  response is an offer (a break, a smaller step, one retrievable question), never a mark
  against the learner. There is no branch that lowers a score, flags an account or blocks
  a lesson. What the spec called *participation* is reported as a **reading the learner can
  see**, not a deduction applied to them.
* **A timeout re-plans; it does not punish.** If a learner is away past the timeout, the
  useful response is to shorten what is left of the session, not to record a strike.
* **Suspicion is a teaching signal.** "Answered faster than they ever have", "solved the
  original but not the variant", "cannot say why" are the three most reliable signs of
  *fragile knowledge* - the same signs a good teacher uses to ask "explain that to me".
  They route to a variant item or an explain-back prompt. They do not route to a camera, an
  AI-detector, or a ban. See :data:`POSTURE`.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

#: What the supervisor can conclude about the moment.
STATES = ('working', 'drifting', 'away', 'resting', 'struggling')

#: Seconds without interaction before the learner is drifting, and before they are away.
#: 90 s is about the length of a hard paragraph; 300 s is the spec's five-minute timeout.
IDLE_DRIFTING_SECONDS = 90.0
IDLE_AWAY_SECONDS = 300.0

#: A window hidden for this share of the sample is treated as away regardless of idle time.
HIDDEN_AWAY_RATIO = 0.60

#: Progress is "lagging" when it is under this share of where the clock says it should be.
#: Only consulted once the session is old enough for the comparison to mean anything.
PROGRESS_LAG_RATIO = 0.75
PROGRESS_MIN_ELAPSED_SECONDS = 240.0

#: The mastery band the teaching core treats as "not yet" and "secure". Chosen to match
#: the BKT prior in ``evidence.PRIOR`` (0.15) at the bottom and the 0.80 node-milestone
#: threshold the product already uses at the top.
MASTERY_WEAK = 0.45
MASTERY_STRONG = 0.80

#: An answer given in under this share of the learner's own average latency is fast enough
#: to be worth a variant item. It is not evidence of cheating on its own - a learner who
#: has just understood something genuinely speeds up - which is why it routes to a check
#: rather than a verdict.
LATENCY_ANOMALY_RATIO = 0.35

#: Do not repeat the same interruption more often than this. A tutor that asks "are you
#: still there?" every thirty seconds is worse than one that says nothing.
NOTICE_COOLDOWN_SECONDS = 180.0

#: Stated in every payload so a client cannot present a reading as a punishment and claim
#: the engine endorsed it.
POSTURE = {
    'participation_is_a_reading': True,
    'deducts_marks': False,
    'flags_accounts': False,
    'blocks_lessons': False,
    'reads_camera': False,
    'stores_frames': False,
    'suspicion_routes_to': 'a variant item or an explain-back prompt',
}


def _num(signals: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(signals.get(key, default) or default)
    except (TypeError, ValueError):
        return default
    return value if value == value and value not in (float('inf'), float('-inf')) else default


def _flag(signals: Mapping[str, Any], key: str) -> bool:
    value = signals.get(key)
    if isinstance(value, bool):
        return value
    return str(value or '').strip().casefold() in {'1', 'true', 'yes', 'on'}


def progress_reading(signals: Mapping[str, Any]) -> dict[str, Any]:
    """Where the lesson is against the clock, or ``None`` when the comparison is too young.

    The spec compares progress to a threshold ``n``. A fixed ``n`` is wrong in both
    directions - a learner on a hard concept is legitimately behind, and a learner
    re-reading an easy one is legitimately ahead - so the comparison is against *this
    session's own plan*: how much of the planned time has been spent versus how much of the
    planned work is done.
    """
    elapsed = max(0.0, _num(signals, 'elapsed_seconds'))
    planned = max(1.0, _num(signals, 'planned_seconds', 1800.0))
    progress = min(1.0, max(0.0, _num(signals, 'progress')))
    expected = min(1.0, elapsed / planned)
    lag = expected - progress
    too_young = elapsed < PROGRESS_MIN_ELAPSED_SECONDS
    return {
        'progress': round(progress, 4),
        'expected': round(expected, 4),
        'lag': round(lag, 4),
        'lagging': (not too_young) and lag >= (1.0 - PROGRESS_LAG_RATIO) * max(expected, 0.05),
        'elapsed_seconds': round(elapsed, 1),
        'planned_seconds': round(planned, 1),
        'comparable': not too_young,
    }


def participation(signals: Mapping[str, Any]) -> dict[str, Any]:
    """How much of the sampled window the learner was actually interacting with the app.

    A reading, deliberately. It is reported to the learner and to the tutor as context for
    "this was a short session" or "this was a scattered one"; it is never subtracted from
    anything. See :data:`POSTURE`.
    """
    window = max(30.0, _num(signals, 'window_seconds', 300.0))
    active = max(0.0, min(_num(signals, 'active_seconds'), window))
    hidden = max(0.0, min(_num(signals, 'hidden_seconds'), window))
    share = active / window
    visible_share = 1.0 - hidden / window
    return {'active_share': round(share, 3), 'visible_share': round(visible_share, 3),
            'window_seconds': round(window, 1),
            'reading': ('Most of the session was hands-on.' if share >= 0.6 else
                        'About half the session was hands-on.' if share >= 0.3 else
                        'A quiet session: little interaction in the sampled window.')}


def difficulty(signals: Mapping[str, Any]) -> dict[str, Any]:
    """Which way the next item should move, and why. ``up`` / ``down`` / ``hold``.

    The spec's INC / DEC / Normal. It reads the mastery belief and the recent record
    together, because either alone is a bad signal: mastery lags a fast learner by a
    lesson, and a single wrong answer says nothing about a shaky concept.

    An *unknown* belief is not a weak one. ``evidence.PRIOR`` (0.15) is a placeholder for
    "no attempts yet", and moving difficulty down on it would open every new learner on the
    easiest item in the course for no reason.
    """
    mastery = _num(signals, 'mastery', 0.15)
    known = _flag(signals, 'mastery_known')
    accuracy = _num(signals, 'recent_accuracy', -1.0)      # -1 means "no recent record"
    latency = _num(signals, 'answer_latency_seconds', 0.0)
    average = _num(signals, 'personal_average_latency', 0.0)

    if not known:
        return {'direction': 'hold',
                'reason': 'No attempts recorded on this concept, so there is no belief to move.',
                'next': 'keep the current band and teach.'}
    if mastery >= MASTERY_STRONG and (accuracy < 0 or accuracy >= 0.8):
        return {'direction': 'up', 'reason': 'Mastery is secure and the recent record holds.',
                'next': 'harder item on the same concept, not a new concept.'}
    if mastery <= MASTERY_WEAK and (accuracy < 0 or accuracy < 0.6):
        return {'direction': 'down',
                'reason': 'Mastery is below the working band and recent answers are missing.',
                'next': 'smaller step: one sub-skill, worked example first.'}
    if average > 0 and latency and latency <= average * LATENCY_ANOMALY_RATIO and accuracy < 0.5:
        return {'direction': 'down',
                'reason': 'Fast and wrong together: the item is being guessed, not solved.',
                'next': 'drop to the prerequisite sub-skill and ask for the reasoning.'}
    return {'direction': 'hold', 'reason': 'No reliable signal to move the difficulty.',
            'next': 'keep the current band.'}


def provenance(signals: Mapping[str, Any]) -> dict[str, Any] | None:
    """Whether this answer needs a *check*, and which one. ``None`` when nothing is odd.

    The three conditions the spec lists under "very suspicious" are, read correctly, the
    three conditions under which knowledge is fragile rather than owned:

    * ``latency`` - answered in a fraction of this learner's own average time;
    * ``variant`` - the original item was right and a same-concept variant was wrong;
    * ``explained`` - the answer is right but the learner cannot say why.

    Each routes to something a teacher does: give the variant, ask for the reasoning, drop
    to the prerequisite. None of them routes to an accusation, and the payload says so.
    """
    latency = _num(signals, 'answer_latency_seconds', 0.0)
    average = _num(signals, 'personal_average_latency', 0.0)
    variant = str(signals.get('variant_result') or '').strip().casefold()
    explained = signals.get('explained')
    correct = _flag(signals, 'last_answer_correct')

    reasons: list[str] = []
    check = None
    if average > 0 and latency > 0 and latency <= average * LATENCY_ANOMALY_RATIO and correct:
        reasons.append(f'Answered in {latency:.0f} s against a personal average of '
                       f'{average:.0f} s.')
        check = 'variant'
    if variant == 'wrong':
        reasons.append('The original item was right and a same-concept variant was not.')
        check = 'variant'
    if explained is False and correct:
        reasons.append('The answer was right and the reasoning was not given.')
        check = check or 'explain_back'
    if not reasons:
        return None
    return {'check': check, 'reasons': reasons,
            'asks': ('Give one variant item on the same concept before moving on.'
                     if check == 'variant' else
                     'Ask the learner to explain the step in their own words.'),
            'not_a_verdict': ('This is a knowledge check, not an accusation. A learner who '
                              'has just understood something genuinely speeds up.')}


def assess(signals: Mapping[str, Any] | None = None, *, now: float | None = None,
           last_notice_at: float | None = None) -> dict[str, Any]:
    """One decision: the state, why, and the single move worth making.

    ``last_notice_at`` is the epoch second of the previous interruption, so the supervisor
    can stay quiet instead of repeating itself (:data:`NOTICE_COOLDOWN_SECONDS`).
    """
    signals = dict(signals or {})
    now = time.time() if now is None else float(now)

    idle = max(0.0, _num(signals, 'idle_seconds'))
    window = max(30.0, _num(signals, 'window_seconds', 300.0))
    hidden_ratio = min(1.0, max(0.0, _num(signals, 'hidden_seconds')) / window)
    mastery = _num(signals, 'mastery', 0.15)
    known = _flag(signals, 'mastery_known')
    scrolls = max(0.0, _num(signals, 'scroll_events'))
    progress = progress_reading(signals)
    rest_total = max(0, int(_num(signals, 'rest_quota_total', 2)))
    rest_used = max(0, int(_num(signals, 'rest_quota_used', 0)))
    resting = _flag(signals, 'resting')
    on_quiz = str(signals.get('item_context') or '').strip().casefold() in {'quiz', 'test', 'diagnostic'}

    reasons: list[str] = []
    if resting:
        state, move = 'resting', {
            'kind': 'none', 'say': 'Nothing. A break the learner asked for is not an absence.',
            'why': 'The client reports an explicit break.'}
        reasons.append('Resting on purpose.')
        return _payload(state, move, reasons, signals, progress, now, cooldown=False)

    # 1. Away outranks everything: an empty chair cannot be helped by a better explanation.
    if idle >= IDLE_AWAY_SECONDS or hidden_ratio >= HIDDEN_AWAY_RATIO:
        reasons.append(f'No interaction for {idle:.0f} s'
                       if idle >= IDLE_AWAY_SECONDS else
                       f'The window was hidden for {hidden_ratio:.0%} of the sample.')
        if rest_used < rest_total:
            move = {'kind': 'offer_break',
                    'say': 'Offer a two-minute break. Do not ask where they went.',
                    'why': f'{rest_total - rest_used} of {rest_total} breaks remain this session.'}
        else:
            move = {'kind': 'retrieval',
                    'say': ('One short question about the last thing they saw - answerable '
                            'from memory, not from the page.'),
                    'why': ('Breaks are used up. A retrieval question re-enters the task '
                            'better than a reminder does, and it is answerable in one line.'),
                    'shorten_session': True}
        state = 'away'
    # 2. Drifting: interaction stopped, but not long enough to be an absence.
    elif idle >= IDLE_DRIFTING_SECONDS:
        state = 'drifting'
        reasons.append(f'No interaction for {idle:.0f} s (threshold {IDLE_DRIFTING_SECONDS:.0f} s).')
        move = {'kind': 'nudge',
                'say': ('Ask for a prediction about the next step, not for an explanation of '
                        'the whole thing.'),
                'why': 'A small answerable question re-enters the task without an accusation.'}
    # 3. Present, but behind the plan. A learner who is still scrolling is browsing, not stuck.
    elif progress['lagging']:
        if scrolls >= 3:
            state = 'working'
            reasons.append(f'Behind the plan (lag {progress["lag"]:.0%}) but still scrolling.')
            move = {'kind': 'continue',
                    'say': 'Nothing yet. They are reading, not stalled.',
                    'why': 'Progress lag plus active scrolling is browsing; interrupting it is '
                           'the error.'}
        else:
            state = 'struggling'
            reasons.append(f'Behind the plan (lag {progress["lag"]:.0%}) and not scrolling.')
            move = {'kind': 'hint',
                    'say': 'Offer the next single step, not the whole solution.',
                    'why': 'Behind and still is the shape of a learner who does not know how '
                           'to start.'}
    # 4. Present and on pace, but the concept belief is low.
    elif known and mastery <= MASTERY_WEAK:
        state = 'struggling'
        reasons.append(f'Mastery belief {mastery:.2f} is below the working band '
                       f'({MASTERY_WEAK:.2f}).')
        move = {'kind': 'explain',
                'say': 'Teach the sub-skill directly, worked example first.',
                'why': 'The evidence is thin enough that a question would be a guess at what '
                       'is missing.'}
    # 5. Secure, and the last answer was the learner's own.
    elif known and mastery >= MASTERY_STRONG and not on_quiz:
        state = 'working'
        reasons.append(f'Mastery belief {mastery:.2f} is secure.')
        move = {'kind': 'ask_reason',
                'say': 'Ask them to say why it works, in one sentence.',
                'why': 'Explaining a secure idea is what turns it into a transferable one, '
                       'and it is the cheapest way to catch a belief that is only pattern '
                       'matching.'}
    else:
        state = 'working'
        reasons.append('On pace, present, and inside the mastery band.')
        move = {'kind': 'continue', 'say': 'Nothing. Do not interrupt a working learner.',
                'why': 'Interruption is the expensive action here.'}

    payload = _payload(state, move, reasons, signals, progress, now,
                       cooldown=last_notice_at is not None
                       and now - float(last_notice_at) < NOTICE_COOLDOWN_SECONDS)
    check = provenance(signals)
    if check and not on_quiz:
        # A knowledge check outranks a nudge: it is the more informative interruption, and
        # asking for the variant subsumes asking whether they are still there.
        payload['check'] = check
        if payload['move']['kind'] in {'continue', 'ask_reason', 'nudge'}:
            payload['move'] = {'kind': check['check'],
                               'say': check['asks'],
                               'why': '; '.join(check['reasons'])}
    return payload


def _payload(state: str, move: Mapping[str, Any], reasons: list[str],
             signals: Mapping[str, Any], progress: Mapping[str, Any], now: float,
             *, cooldown: bool) -> dict[str, Any]:
    return {
        'state': state if state in STATES else 'working',
        'move': dict(move),
        'reasons': reasons,
        'quiet': bool(cooldown),
        'progress': dict(progress),
        'difficulty': difficulty(signals),
        'participation': participation(signals),
        'at': round(now, 3),
        'posture': dict(POSTURE),
    }


def describe() -> dict[str, Any]:
    """The thresholds and the posture, for the transparency panel and the tests."""
    return {'states': list(STATES),
            'thresholds': {
                'idle_drifting_seconds': IDLE_DRIFTING_SECONDS,
                'idle_away_seconds': IDLE_AWAY_SECONDS,
                'hidden_away_ratio': HIDDEN_AWAY_RATIO,
                'progress_lag_ratio': PROGRESS_LAG_RATIO,
                'mastery_weak': MASTERY_WEAK,
                'mastery_strong': MASTERY_STRONG,
                'latency_anomaly_ratio': LATENCY_ANOMALY_RATIO,
                'notice_cooldown_seconds': NOTICE_COOLDOWN_SECONDS},
            'posture': dict(POSTURE)}
