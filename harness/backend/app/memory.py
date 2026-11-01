"""The DSR memory model: Difficulty, Stability, Retrievability, per FSRS-6.

This module replaces the Leitner-style two-constant heuristic that used to live in
``app.learning.update`` (``half_life_days`` scaled by a fixed 1.6/0.55 factor on
right/wrong). That heuristic could not distinguish "recalled barely" from "recalled
easily", because a boolean only ever moved the multiplier one step. The FSRS-6 / DSR
model fixes exactly that: the stability gain on a successful review is a function of
*how retrievable* the memory was at review time — the computable form of "desirable
difficulty".

Formulas are reimplemented from the published FSRS-6 scheduler (open-spaced-repetition/
py-fsrs, ``fsrs/scheduler.py``); no code from that repository is imported or vendored.
The default weights are the published defaults fitted by the FSRS project from a large
multi-user review corpus — they are quoted verbatim from the upstream source with
commit provenance recorded in ``WEIGHTS_PROVENANCE``. Nothing here is hand-tuned.

State is a plain JSON-serialisable dict so it drops straight into the existing
``State.data`` column with no schema change:

    {'stability': S (days), 'difficulty': D (1-10), 'last_review': epoch_seconds,
     'reps': int, 'lapses': int, 'memory_model': 'fsrs-6', ...}

Public API:
    recall_probability(state, now) -> float | None
    review(state, rating, now)     -> state          # rating 1=Again .. 4=Easy
    due_time(state, desired_retention) -> (due_at_seconds, interval_seconds)
    apply_implicit_credit(state, credit, now) -> state   # FIRe-style fractional credit

The legacy path stays runnable: set ``HARNESS_MEMORY_MODEL=leitner`` to restore the
old behaviour (``app.learning`` keeps it as the fallback branch).
"""

from __future__ import annotations

import math
import os

# ---------------------------------------------------------------------------
# Published FSRS-6 default weights — provenance-critical, do not edit by hand.
#
# Source: https://github.com/open-spaced-repetition/py-fsrs
# File:   fsrs/scheduler.py, constant DEFAULT_PARAMETERS
# Tag:    v6.3.2, commit 9446cb06605c597a063aeee49f7d188d42e34dc2
# (fetched 2026-10-11)
#
# Verbatim from upstream:
#
# FSRS_DEFAULT_DECAY = 0.1542
# DEFAULT_PARAMETERS = (
#     0.212,
#     1.2931,
#     2.3065,
#     8.2956,
#     6.4133,
#     0.8334,
#     3.0194,
#     0.001,
#     1.8722,
#     0.1666,
#     0.796,
#     1.4835,
#     0.0614,
#     0.2629,
#     1.6483,
#     0.6014,
#     1.8729,
#     0.5425,
#     0.0912,
#     0.0658,
#     FSRS_DEFAULT_DECAY,
# )
# ---------------------------------------------------------------------------

WEIGHTS_PROVENANCE = {
    'source_url': 'https://github.com/open-spaced-repetition/py-fsrs',
    'file': 'fsrs/scheduler.py::DEFAULT_PARAMETERS',
    'tag': 'v6.3.2',
    'commit': '9446cb06605c597a063aeee49f7d188d42e34dc2',
    'fetched': '2026-10-11',
    'note': 'Published defaults fitted by the FSRS project on a large multi-user '
            'review corpus; used unmodified. Not hand-tuned.',
}

FSRS_DEFAULT_DECAY = 0.1542
DEFAULT_PARAMETERS = (
    0.212,      # w0  initial stability for Again
    1.2931,     # w1  initial stability for Hard
    2.3065,     # w2  initial stability for Good
    8.2956,     # w3  initial stability for Easy
    6.4133,     # w4  difficulty prior anchor
    0.8334,     # w5  difficulty from rating slope
    3.0194,     # w6  difficulty delta scale
    0.001,      # w7  mean-reversion weight (toward prior)
    1.8722,     # w8  recall stability gain base
    0.1666,     # w9  stability damping exponent
    0.796,      # w10 desirable-difficulty exponent (gain grows as R falls)
    1.4835,     # w11 post-lapse stability base
    0.0614,     # w12 post-lapse difficulty exponent
    0.2629,     # w13 post-lapse stability-from-S exponent
    1.6483,     # w14 post-lapse retrievability exponent
    0.6014,     # w15 Hard penalty
    1.8729,     # w16 Easy bonus
    0.5425,     # w17 short-term stability base
    0.0912,     # w18 short-term rating offset
    0.0658,     # w19 short-term stability damping
    FSRS_DEFAULT_DECAY,  # w20 forgetting-curve decay (w20; DECAY = -w20)
)

STABILITY_MIN = 0.001
DIFFICULTY_MIN, DIFFICULTY_MAX = 1.0, 10.0
MAX_INTERVAL_DAYS = 36500
MIN_DUE_SECONDS = 300  # keep the legacy five-minute floor

RATING_AGAIN, RATING_HARD, RATING_GOOD, RATING_EASY = 1, 2, 3, 4
_VALID_RATINGS = (RATING_AGAIN, RATING_HARD, RATING_GOOD, RATING_EASY)


def enabled() -> bool:
    """The model switch. 'fsrs' (default) uses DSR; 'leitner' restores the old path."""
    return os.getenv('HARNESS_MEMORY_MODEL', 'fsrs') != 'leitner'


def _params():
    """Weights, optionally overridden wholesale by an operator for A/B experiments.
    Reading published defaults is the supported path; overrides are env-explicit."""
    raw = os.getenv('HARNESS_FSRS_PARAMETERS', '')
    if not raw:
        return DEFAULT_PARAMETERS
    values = tuple(float(x) for x in raw.split(','))
    if len(values) != len(DEFAULT_PARAMETERS):
        raise ValueError(f'Expected {len(DEFAULT_PARAMETERS)} FSRS parameters, got {len(values)}')
    return values


_DECAY = None  # cached lazily so env overrides in tests are picked up per call


def _decay() -> float:
    return -_params()[20]


def _factor(decay: float) -> float:
    return 0.9 ** (1.0 / decay) - 1.0


def _clamp_stability(stability: float) -> float:
    return max(STABILITY_MIN, stability)


def _clamp_difficulty(difficulty: float) -> float:
    return min(DIFFICULTY_MAX, max(DIFFICULTY_MIN, difficulty))


def _initial_stability(rating: int) -> float:
    w = _params()
    return _clamp_stability(float(w[rating - 1]))


def _initial_difficulty(rating: int) -> float:
    w = _params()
    return _clamp_difficulty(w[4] - math.e ** (w[5] * (rating - 1)) + 1)


def retrievability(stability: float, elapsed_seconds: float, decay: float | None = None) -> float:
    """The power-law forgetting curve: R(t) = (1 + FACTOR·t/S)^DECAY.

    R(0) = 1; R(S) = 0.9 by construction of FACTOR. Monotonically decreasing in t.
    This is the recall probability the scheduler schedules against.
    """
    if decay is None:
        decay = _decay()
    factor = _factor(decay)
    t = max(0.0, elapsed_seconds) / 86400.0
    return (1.0 + factor * t / stability) ** decay


def recall_probability(state: dict, now: float) -> float | None:
    """Probability the learner can recall this item right now. None if never seen."""
    last = state.get('last_review', state.get('last_at'))
    stability = state.get('stability')
    if last is None or stability is None:
        return None
    return retrievability(float(stability), now - float(last))


def _recall_stability(stability: float, difficulty: float, r_at_review: float,
                      rating: int) -> float:
    """Successful-review stability gain. The w10 term is FSRS's core quantified
    claim: the LOWER the retrievability at review time, the LARGER the stability
    gain — desirable difficulty, in one line of algebra."""
    w = _params()
    hard_penalty = w[15] if rating == RATING_HARD else 1.0
    easy_bonus = w[16] if rating == RATING_EASY else 1.0
    return stability * (1.0
                        + math.e ** w[8]
                        * (11.0 - difficulty)
                        * stability ** -w[9]
                        * (math.e ** (w[10] * (1.0 - r_at_review)) - 1.0)
                        * hard_penalty
                        * easy_bonus)


def _forget_stability(stability: float, difficulty: float, r_at_review: float) -> float:
    w = _params()
    long_term = (w[11] * difficulty ** -w[12]
                 * ((stability + 1.0) ** w[13] - 1.0)
                 * math.e ** (w[14] * (1.0 - r_at_review)))
    short_term = stability / math.e ** (w[17] * w[18])
    return min(long_term, short_term)


def _short_term_stability(stability: float, rating: int) -> float:
    """Same-session re-review: a bounded adjustment, not a full spaced update."""
    w = _params()
    increase = math.e ** (w[17] * (rating - 3 + w[18])) * stability ** -w[19]
    if rating != RATING_AGAIN:
        increase = max(increase, 1.0)
    return _clamp_stability(stability * increase)


def _next_difficulty(difficulty: float, rating: int) -> float:
    """Performance moves difficulty with linear damping, then mean-reverts toward
    the difficulty prior (the Easy-rated initial difficulty). Hard items drift
    easier over many successes; easy items drift harder over many lapses."""
    w = _params()
    delta = -w[6] * (rating - 3)
    damped = (DIFFICULTY_MAX - difficulty) * delta / (DIFFICULTY_MAX - DIFFICULTY_MIN)
    reverted = difficulty + damped
    prior = _initial_difficulty(RATING_EASY)
    return _clamp_difficulty(w[7] * prior + (1.0 - w[7]) * reverted)


def next_interval_days(stability: float, desired_retention: float = 0.9) -> float:
    """Days until retrievability decays to ``desired_retention``."""
    decay = _decay()
    factor = _factor(decay)
    return (stability / factor) * (desired_retention ** (1.0 / decay) - 1.0)


def due_time(state: dict, desired_retention: float = 0.9) -> tuple[float, float]:
    """(due_at epoch seconds, interval seconds). Legacy floors/caps preserved."""
    stability = float(state.get('stability', STABILITY_MIN))
    interval = max(MIN_DUE_SECONDS, min(MAX_INTERVAL_DAYS, next_interval_days(stability, desired_retention)) * 86400.0)
    return state.get('last_review', 0.0) + interval, interval


def new_state(rating: int, now: float) -> dict:
    """First review of an unseen item: initial stability and difficulty priors."""
    return {
        'stability': _initial_stability(rating),
        'difficulty': _initial_difficulty(rating),
        'last_review': float(now),
        'reps': 1,
        'lapses': int(rating == RATING_AGAIN),
        'memory_model': 'fsrs-6',
    }


def _legacy_seed(state: dict) -> dict | None:
    """Adopt a legacy Leitner state without throwing its history away. The old
    ``half_life_days`` is used as the initial stability estimate (same unit: days)."""
    if state.get('stability') is not None:
        return None
    seed = dict(state)
    half_life = state.get('half_life_days', 1.0)
    seed['stability'] = _clamp_stability(float(half_life))
    seed.setdefault('difficulty', _initial_difficulty(RATING_GOOD))
    seed.setdefault('last_review', state.get('last_at'))
    seed.setdefault('reps', int(state.get('attempts', 0)))
    seed.setdefault('lapses', 0)
    seed['memory_model'] = 'fsrs-6'
    seed['memory_model_note'] = ('stability seeded from legacy half_life_days '
                                 '(Leitner heuristic); FSRS updates take over from here')
    return seed


def review(state: dict, rating: int, now: float) -> dict:
    """Apply one review with FSRS-6 semantics and return the updated state.

    ``rating``: 1=Again (lapse) .. 4=Easy. Immutable input; returns a new dict.
    """
    if rating not in _VALID_RATINGS:
        raise ValueError(f'rating must be one of {_VALID_RATINGS}')
    seed = _legacy_seed(state)
    if seed is not None:
        state = seed
    out = dict(state)
    last = state.get('last_review')
    if last is None or state.get('stability') is None:
        if state.get('stability') is not None:
            # A stability prior without a review timestamp (implicit-credit
            # seed): keep it as the starting strength and apply the bounded
            # short-term update; do not throw the prior away.
            out['stability'] = _short_term_stability(float(state['stability']), rating)
            out['difficulty'] = _next_difficulty(float(state['difficulty']), rating)
            out['last_review'] = float(now)
            out['last_recall_probability'] = None
            out['last_stability_gain'] = out['stability'] - float(state['stability'])
            out['reps'] = int(state.get('reps', 0)) + 1
            out['lapses'] = int(state.get('lapses', 0)) + int(rating == RATING_AGAIN)
            out['memory_model'] = 'fsrs-6'
            return out
        out.update(new_state(rating, now))
        out['last_stability_gain'] = out['stability']
        return out

    stability = float(state['stability'])
    difficulty = float(state['difficulty'])
    days_elapsed = max(0.0, now - float(last)) / 86400.0

    if days_elapsed < 1.0:
        next_stability = _short_term_stability(stability, rating)
        r_at_review = recall_probability(state, now)
    else:
        r_at_review = recall_probability(state, now)
        if rating == RATING_AGAIN:
            next_stability = _forget_stability(stability, difficulty, r_at_review)
        else:
            next_stability = _recall_stability(stability, difficulty, r_at_review, rating)
        next_stability = _clamp_stability(next_stability)

    out['stability'] = next_stability
    out['difficulty'] = _next_difficulty(difficulty, rating)
    out['last_review'] = float(now)
    out['last_recall_probability'] = r_at_review
    out['last_stability_gain'] = next_stability - stability
    out['reps'] = int(state.get('reps', 0)) + 1
    out['lapses'] = int(state.get('lapses', 0)) + int(rating == RATING_AGAIN)
    out['memory_model'] = 'fsrs-6'
    return out


# ---------------------------------------------------------------------------
# FIRe-style implicit repetition credit (reimplementation of the published idea,
# not Math Academy's code — see outputs/impl/u1_model_memory.md).
#
# When a learner successfully recalls concept X, X's prerequisites receive a
# FRACTIONAL stability increment, decayed by graph distance: getting X right is
# weak evidence that what X depends on is still solid. The credit is an increment
# on the same DSR stability — there is no second memory system.
# ---------------------------------------------------------------------------

#: Fraction of the reviewed item's stability gain granted to each direct prerequisite.
IMPLICIT_CREDIT_FRACTION = 0.3
#: Per-hop decay of the credit through the prerequisite graph.
IMPLICIT_CREDIT_DECAY = 0.5
#: Maximum graph distance credited. Evidence decays fast; direct prerequisites only
#: plus one hop keeps the weak-evidence justification honest.
IMPLICIT_CREDIT_MAX_DISTANCE = 2


def apply_implicit_credit(state: dict, credit: float, now: float) -> dict:
    """Increment DSR stability by a fractional implicit-repetition credit.

    The review clock is deliberately NOT reset: implicit evidence is weaker than
    an actual review and must not make the item look fresher than it is. For a
    never-reviewed prerequisite the credit seeds a weak initial memory state
    rather than being discarded -- it is (weak) evidence of knowledge.
    """
    if credit <= 0:
        return state
    out = dict(state)
    if out.get('stability') is None:
        out['stability'] = max(STABILITY_MIN, credit)
        out['difficulty'] = out.get('difficulty', _initial_difficulty(RATING_GOOD))
        out['last_review'] = out.get('last_review')
        out['memory_model'] = 'fsrs-6'
        out['memory_model_note'] = 'stability seeded by implicit repetition credit'
    else:
        out['stability'] = _clamp_stability(float(state['stability']) + credit)
    out['implicit_credit_total'] = float(state.get('implicit_credit_total', 0.0)) + credit
    out['last_implicit_credit'] = credit
    out['last_implicit_credit_at'] = float(now)
    return out
