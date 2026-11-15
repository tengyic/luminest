"""The per-turn diagnosis gate: a reading, a contract, and an additive repair.

These tests pin the parts that must hold without a model: the band a given BKT
posterior falls into, the direction of the target difficulty, and the fact that a
probe turn with no question gets one appended rather than rewritten.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.harness.teaching import (ConceptFacts, LearnerEvidence, default_profile,
                                  plan_session)
from app.harness.teaching import diagnosis as gate


def _evidence(**overrides) -> LearnerEvidence:
    base = dict(concept_id='slope', mastery=0.5, attempts=3, last_correct=None)
    base.update(overrides)
    return LearnerEvidence(**base)


def test_unmeasured_band_when_nothing_has_been_attempted():
    reading = gate.read(_evidence(mastery=0.15, attempts=0))
    assert reading.band == 'unmeasured'
    assert reading.mastery_known is False
    assert reading.act == 'probe'
    assert reading.must_ask is True


def test_fragile_band_aims_easier_than_the_point_estimate():
    fragile = gate.read(_evidence(mastery=0.2, attempts=4))
    emerging = gate.read(_evidence(mastery=0.55, attempts=4))
    assert fragile.band == 'fragile' and fragile.act == 'hint'
    assert emerging.band == 'emerging' and emerging.act == 'prompt'
    # Lower b is an easier item; a fragile learner must not be pushed upward.
    assert fragile.target_b < emerging.target_b
    assert fragile.expected_success >= 0.6


def test_secure_learner_who_just_failed_is_not_sent_to_transfer():
    reading = gate.read(_evidence(mastery=0.85, attempts=6, last_correct=False))
    assert reading.band == 'secure'
    assert reading.act == 'prompt'
    assert reading.act != 'transfer'


def test_explicit_request_outranks_the_band():
    reading = gate.read(_evidence(mastery=0.2, attempts=4), explicit_request=True)
    assert reading.act == 'reveal'
    assert reading.reveal_allowed is True
    assert reading.must_ask is False


def test_theta_is_absent_rather_than_invented():
    reading = gate.read(_evidence())
    assert reading.theta is None
    assert 'theta absent' in ' '.join(reading.trace)


def test_theta_is_carried_when_the_caller_has_one():
    reading = gate.read(_evidence(), theta=0.8, theta_se=0.31)
    assert reading.theta == 0.8 and reading.theta_se == 0.31
    assert 'theta from IRT' in ' '.join(reading.trace)


def test_reading_survives_a_dict_round_trip():
    reading = gate.read(_evidence(mastery=0.42, attempts=2))
    again = gate.TurnReading.from_dict(reading.to_dict())
    assert again.band == reading.band
    assert again.must_ask == reading.must_ask
    assert abs(again.target_b - reading.target_b) < 0.01


# ------------------------------------------------------------------- contract

def test_a_probe_without_a_question_is_a_violation():
    reading = gate.read(_evidence(mastery=0.3, attempts=2))
    assert 'no_question' in gate.check('Let me walk you through the slope.', reading)


def test_three_questions_are_flagged_but_not_rewritten():
    reading = gate.read(_evidence(mastery=0.3, attempts=2))
    text = 'What is the rise? What is the run? And which one goes on top?'
    assert 'too_many_questions' in gate.check(text, reading)
    repaired, action = gate.apply(text, reading)
    assert repaired == text and action == 'flagged'


def test_stating_the_answer_during_a_probe_is_a_violation():
    reading = gate.read(_evidence(mastery=0.3, attempts=2))
    assert 'states_answer_on_probe' in gate.check('The answer is 4.', reading)


def test_repair_appends_a_question_and_keeps_the_teacher_text():
    reading = gate.read(_evidence(mastery=0.3, attempts=2))
    original = 'Slope is rise over run.'
    repaired, action = gate.apply(original, reading, title='slope')
    assert action == 'appended_probe'
    assert repaired.startswith(original)          # additive, not a rewrite
    assert gate.count_questions(repaired) == 1


def test_a_good_turn_is_left_alone():
    reading = gate.read(_evidence(mastery=0.3, attempts=2))
    text = 'Before I add anything: what is the rise here?'
    assert gate.check(text, reading) == ()
    assert gate.apply(text, reading) == (text, 'ok')


# --------------------------------------------------------------- plan wiring

def test_every_plan_carries_the_diagnosis_it_was_gated_by():
    facts = ConceptFacts(id='slope', title='Slope', subject_kind='mathematics')
    plan = plan_session(_evidence(mastery=0.25, attempts=3), facts, default_profile())
    assert plan.diagnosis is not None
    assert plan.diagnosis['band'] in gate.BANDS
    assert plan.diagnosis['act'] in ('probe', 'hint', 'prompt', 'transfer')
    assert 'target_b' in plan.diagnosis
    # It is serialised with the plan, so a transcript can show why this turn looked
    # the way it did without a second lookup.
    assert plan.to_dict()['diagnosis']['band'] == plan.diagnosis['band']


def test_rest_plan_still_records_the_reading(monkeypatch):
    """The early-return path (a session that stops) is gated like any other."""
    from app.harness.teaching import policy
    from app.harness.teaching import session as session_module

    monkeypatch.setattr(session_module, 'select_move',
                        lambda evidence, profile: policy.MoveScore(
                            move='rest', score=1.0, reason='test: stop now'))
    facts = ConceptFacts(id='slope', title='Slope', subject_kind='mathematics')
    plan = plan_session(_evidence(mastery=0.9, attempts=9), facts, default_profile())
    assert plan.move.move == 'rest'
    assert plan.diagnosis is not None
    assert plan.steps and plan.steps[0].phase == 'close'


# --------------------------------------------------------------- tutor wiring

def _plan_with(move: str, **overrides):
    reading = gate.read(_evidence(mastery=0.3, attempts=2, **overrides))
    return SimpleNamespace(move=SimpleNamespace(move=move),
                           diagnosis=reading.to_dict())


def test_tutor_appends_the_probe_a_retrieval_turn_owed():
    from app import tutor

    usage: dict = {}
    text, action = tutor._enforce_turn_contract(
        'Slope is rise over run.', _plan_with('retrieve'), {'title': 'Slope'}, usage)
    assert action == 'appended_probe'
    assert text.startswith('Slope is rise over run.')
    assert text.count('?') + text.count('？') == 1
    assert usage['gate'] == 'appended_probe'
    assert usage['gate_violations'] == ['no_question']


def test_tutor_leaves_an_explanation_move_alone():
    from app import tutor

    usage: dict = {}
    text, action = tutor._enforce_turn_contract(
        'Slope is rise over run.', _plan_with('explain'), {'title': 'Slope'}, usage)
    assert action == 'not_gated' and text == 'Slope is rise over run.'
    assert 'gate' not in usage


def test_tutor_does_not_gate_without_a_plan():
    from app import tutor

    text, action = tutor._enforce_turn_contract('Anything.', None, {'title': 'x'}, None)
    assert action == 'not_gated' and text == 'Anything.'
