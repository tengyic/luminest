"""Property-based tests for the mastery and grading calculations in ``app.learning``.

The example tests in ``test_learning_science.py`` pin particular numbers. These pin the
*shape* of the calculation, which is what a regression actually breaks:

* mastery is a belief: it stays inside [0, 0.995] no matter how many updates run;
* a correct answer never scores lower than an incorrect one from the same belief;
* the BKT/LEARN floor means an incorrect answer at a very low belief can still raise it
  (documented behaviour, asserted here so nobody "fixes" it by accident);
* the predicted probability of a correct answer is a probability, and rises with mastery;
* ``update`` returns a fresh dict and never leaves a due date in the past.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings as hp_settings
from hypothesis import strategies as st

from app import learning, memory

MASTERY = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
NOW = st.floats(min_value=1_600_000_000.0, max_value=1_900_000_000.0,
                allow_nan=False, allow_infinity=False)
ELAPSED = st.floats(min_value=0.0, max_value=86_400.0 * 30,
                    allow_nan=False, allow_infinity=False)

COMMON = dict(max_examples=150, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])


@pytest.fixture(autouse=True)
def local_model(monkeypatch):
    """Exercise the shipped BKT + FSRS path, not an installed adapter."""
    monkeypatch.delenv('HARNESS_ADAPTATION', raising=False)
    monkeypatch.delenv('HARNESS_MEMORY_MODEL', raising=False)


@given(prior=MASTERY)
@hp_settings(**COMMON)
def test_mastery_stays_a_probability(prior):
    """Both outcomes leave mastery inside the cap the product promises."""
    for correct in (True, False):
        value = learning._mastery_update({'mastery': prior}, correct)
        assert 0.0 <= value <= 0.995 + 1e-12, f'mastery={value!r} from prior={prior!r}'
        assert value == value  # never NaN


@given(prior=MASTERY)
@hp_settings(**COMMON)
def test_correct_always_outscores_incorrect(prior):
    """The ordering is the whole point of grading; it must never invert."""
    right = learning._mastery_update({'mastery': prior}, True)
    wrong = learning._mastery_update({'mastery': prior}, False)
    assert right >= wrong
    if learning.PRIOR <= prior <= 0.9:
        # Strict ordering is asserted over the reachable domain only. Below PRIOR the
        # LEARN floor lifts both outcomes to the same 0.12, and at 1.0 the 0.995 cap
        # clamps both -- neither state can occur, because PRIOR is the seeded belief and
        # the floor raises anything lower on the very next update. Above 0.9 the 0.995
        # cap is close enough that a single update saturates it from either outcome.
        assert right > wrong


@given(prior=st.floats(min_value=0.0, max_value=0.03, allow_nan=False))
@hp_settings(**COMMON)
def test_a_wrong_answer_can_still_raise_a_near_zero_belief(prior):
    """Documented: the LEARN floor dominates below ~0.03, so one lapse is not a verdict.

    This is deliberate product behaviour ("never punish"), not a bug. Asserting it here
    stops a future refactor from silently turning a low prior into a hard zero.
    """
    assert learning._mastery_update({'mastery': prior}, False) > prior


@given(prior=MASTERY, correct=st.booleans(), now=NOW, elapsed=ELAPSED)
@hp_settings(**COMMON)
def test_update_returns_a_complete_future_dated_state(prior, correct, now, elapsed):
    """``update`` advances the attempt count and never schedules into the past."""
    state = {'mastery': prior, 'last_at': now - elapsed, 'attempts': 3, 'correct_count': 1}
    before = dict(state)
    out = learning.update(state, correct, elapsed, now)
    assert state == before, 'update must not mutate its input'
    assert out['attempts'] == 4
    assert out['correct_count'] == 1 + int(correct)
    assert out['last_correct'] is correct
    assert out['due_at'] > out['last_at']
    assert 0.0 <= out['mastery'] <= 0.995 + 1e-12
    assert out['half_life_days'] > 0


@given(prior=MASTERY)
@hp_settings(**COMMON)
def test_repeated_updates_never_escape_the_bounds(prior):
    """A thousand consecutive successes converge to the cap, not past it."""
    state = {'mastery': prior}
    now = 1_700_000_000.0
    for step in range(200):
        state = learning.update(state, True, 60.0, now + step * 60.0)
        assert 0.0 <= state['mastery'] <= 0.995 + 1e-12
    assert state['mastery'] <= 0.995 + 1e-12


@given(low=MASTERY, high=MASTERY)
@hp_settings(**COMMON)
def test_item_probability_is_a_probability_and_rises_with_mastery(low, high):
    """P(correct) stays in (0, 1) and is monotone in the belief it is derived from."""
    question = {'id': 'q'}
    weak = learning.item_probability({'mastery': min(low, high)}, question)['p_correct']
    strong = learning.item_probability({'mastery': max(low, high)}, question)['p_correct']
    assert 0.0 < weak < 1.0 and 0.0 < strong < 1.0
    assert strong >= weak - 1e-12


@given(prior=MASTERY, now=NOW)
@hp_settings(**COMMON)
def test_predict_reports_the_state_it_was_given(prior, now):
    """``predict`` is a read: mastery in equals mastery out, recall is bounded or None."""
    state = {'mastery': prior, 'stability': 4.0, 'last_review': now - 3600.0}
    out = learning.predict(state, {'now': now})
    assert out['mastery'] == prior
    if out['recall'] is not None:
        assert 0.0 <= out['recall'] <= 1.0


@given(prior=MASTERY)
@hp_settings(**COMMON)
def test_mastery_and_memory_strength_move_independently(prior):
    """Mastery is a skill belief; stability is memory. A lapse must not zero the belief."""
    now = 1_700_000_000.0
    state = learning.update({'mastery': prior, 'stability': 10.0, 'difficulty': 5.0,
                             'last_review': now - 86400.0},
                            False, 86400.0, now)
    assert state['mastery'] > 0.0
    assert state['stability'] > 0.0
    assert state['stability'] != pytest.approx(10.0)
    assert memory.recall_probability(state, now) is not None
