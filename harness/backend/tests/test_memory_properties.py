"""Property-based tests for the memory model (FSRS-6 DSR) in ``app.memory``.

Why these exist alongside the example tests in ``test_memory.py``: the scheduler decides
*when a learner sees an item again*, and a single wrong constant in the forgetting curve
is invisible to a handful of hand-picked examples. The properties below are the ones a
reviewer can check against the published model:

* R(t) is a probability: 0 < R <= 1, R(0) = 1, R(S) = 0.9 by construction;
* R is non-increasing in elapsed time and non-decreasing in stability;
* the interval is bounded by the product's own floor and cap;
* a review never yields a non-positive stability or an out-of-range difficulty;
* ratings order correctly (Easy schedules further out than Again);
* ``review`` is pure — the caller's dict is not mutated.

These are invariants, not snapshots: they must hold for *every* state the model can
reach, which is exactly what Hypothesis searches for.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings as hp_settings
from hypothesis import strategies as st

from app import memory

# Bounds wide enough to cover every state the scheduler can produce, including a
# just-lapsed item at the stability floor and a long-lived item near the cap.
STABILITY = st.floats(min_value=memory.STABILITY_MIN, max_value=1e5,
                      allow_nan=False, allow_infinity=False)
ELAPSED_DAYS = st.floats(min_value=0.0, max_value=365.0 * 20,
                         allow_nan=False, allow_infinity=False)
RATING = st.integers(min_value=1, max_value=4)
NOW = st.floats(min_value=1_600_000_000.0, max_value=1_900_000_000.0,
                allow_nan=False, allow_infinity=False)

COMMON = dict(max_examples=200, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])


@given(stability=STABILITY, elapsed=ELAPSED_DAYS)
@hp_settings(**COMMON)
def test_retrievability_is_a_probability(stability, elapsed):
    """R is a probability for every reachable (S, t), and 1.0 exactly at t = 0."""
    value = memory.retrievability(stability, elapsed * 86400.0)
    assert 0.0 < value <= 1.0 + 1e-12, f'R={value!r} for S={stability!r}, t={elapsed!r}d'
    assert memory.retrievability(stability, 0.0) == pytest.approx(1.0, abs=1e-12)


@given(stability=STABILITY)
@hp_settings(**COMMON)
def test_retrievability_at_stability_is_desired_retention(stability):
    """R(t=S) = 0.9 is the definition the scheduler inverts to choose an interval."""
    assert memory.retrievability(stability, stability * 86400.0) == pytest.approx(0.9, abs=1e-9)


@given(stability=STABILITY, first=ELAPSED_DAYS, second=ELAPSED_DAYS)
@hp_settings(**COMMON)
def test_retrievability_is_monotone_in_elapsed_time(stability, first, second):
    """Waiting longer never makes recall more likely. (Ties allowed: the curve flattens.)"""
    early = memory.retrievability(stability, min(first, second) * 86400.0)
    late = memory.retrievability(stability, max(first, second) * 86400.0)
    assert late <= early + 1e-12


@given(low=STABILITY, high=STABILITY, elapsed=ELAPSED_DAYS)
@hp_settings(**COMMON)
def test_retrievability_is_monotone_in_stability(low, high, elapsed):
    """A stronger memory is never less retrievable than a weaker one at the same delay."""
    weaker = memory.retrievability(min(low, high), elapsed * 86400.0)
    stronger = memory.retrievability(max(low, high), elapsed * 86400.0)
    assert stronger >= weaker - 1e-12


@given(stability=STABILITY)
@hp_settings(**COMMON)
def test_interval_respects_the_products_floor_and_cap(stability):
    """The scheduled interval is always inside [MIN_DUE_SECONDS, MAX_INTERVAL_DAYS]."""
    _due, interval = memory.due_time({'stability': stability, 'last_review': 0.0})
    assert memory.MIN_DUE_SECONDS - 1e-9 <= interval
    assert interval <= memory.MAX_INTERVAL_DAYS * 86400.0 + 1e-9
    assert interval == interval and interval > 0


@given(stability=STABILITY, now=NOW)
@hp_settings(**COMMON)
def test_due_time_is_never_before_the_last_review(stability, now):
    """A card must not come back before it was answered."""
    due, _interval = memory.due_time({'stability': stability, 'last_review': now})
    assert due >= now + memory.MIN_DUE_SECONDS - 1e-6


@given(rating=RATING, now=NOW)
@hp_settings(**COMMON)
def test_review_keeps_state_inside_its_declared_bounds(rating, now):
    """Stability stays positive, difficulty stays in [1, 10], reps increment exactly once."""
    fresh = memory.new_state(memory.RATING_GOOD, now - 86400.0)
    out = memory.review(fresh, rating, now)
    assert out['stability'] > 0.0 and math.isfinite(out['stability'])
    assert memory.DIFFICULTY_MIN <= out['difficulty'] <= memory.DIFFICULTY_MAX
    assert out['reps'] == fresh['reps'] + 1
    assert out['last_review'] == now
    assert out['lapses'] == fresh['lapses'] + (1 if rating == memory.RATING_AGAIN else 0)


@given(fresh_rating=RATING, later_rating=RATING, now=NOW)
@hp_settings(**COMMON)
def test_review_is_pure(fresh_rating, later_rating, now):
    """``review`` returns a new state; the caller's dict is untouched."""
    state = memory.new_state(fresh_rating, now - 86400.0)
    before = dict(state)
    memory.review(state, later_rating, now)
    assert state == before


@given(now=NOW)
@hp_settings(**COMMON)
def test_easier_ratings_schedule_further_out(now):
    """Easy > Good > Hard > Again when everything else is held constant."""
    intervals = {}
    for rating in (memory.RATING_AGAIN, memory.RATING_HARD,
                   memory.RATING_GOOD, memory.RATING_EASY):
        state = memory.new_state(rating, now)
        _due, intervals[rating] = memory.due_time(state)
    assert (intervals[memory.RATING_EASY] >= intervals[memory.RATING_GOOD]
            >= intervals[memory.RATING_HARD] >= intervals[memory.RATING_AGAIN])


@given(rating=st.integers().filter(lambda value: value not in (1, 2, 3, 4)))
@hp_settings(max_examples=50, deadline=None)
def test_unknown_ratings_are_refused(rating):
    """An out-of-range rating is a programming error, not silently coerced."""
    with pytest.raises(ValueError):
        memory.review(memory.new_state(memory.RATING_GOOD, 0.0), rating, 86400.0)


@given(stability=STABILITY, now=NOW, rating=RATING)
@hp_settings(**COMMON)
def test_recall_probability_matches_the_forgetting_curve(stability, now, rating):
    """``recall_probability`` reads the same curve, not a second implementation of it."""
    state = {'stability': stability, 'last_review': now - 86400.0}
    assert memory.recall_probability(state, now) == pytest.approx(
        memory.retrievability(stability, 86400.0), rel=1e-12)
    assert memory.recall_probability({}, now) is None
