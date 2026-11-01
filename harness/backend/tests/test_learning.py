import math
from fractions import Fraction

import pytest

from app import learning
from app.curriculum import QUESTIONS, validate_curriculum


def test_fallback_evidence_and_recall(monkeypatch):
    monkeypatch.setenv('HARNESS_ADAPTATION', '0')
    before = learning.predict({}, {'now': 100})
    assert before['recall'] is None and before['mastery'] == 0.15
    state = learning.update({}, True, 20, 100)
    assert state['mastery'] > before['mastery']
    assert learning.predict(state, {'now': 100})['recall'] == 1
    later = learning.predict(state, {'now': 100+86400})['recall']
    assert 0 < later < 1
    missed = learning.update(state, False, 10, 200)
    assert missed['mastery'] < state['mastery']
    assert missed['due_at'] > 200
    assert learning.model_status()['trained'] is False
    assert learning.model_status()['commercial_ready'] is False


def test_domain_gate_rejects_toeic(monkeypatch):
    class Candidate:
        MODEL_METADATA = {'domain': 'TOEIC', 'trained': True, 'validated_for_math': False}
        predict = staticmethod(lambda *args: {})
        update = staticmethod(lambda *args: {})
        recommend = staticmethod(lambda *args: {})
    monkeypatch.setenv('HARNESS_ADAPTATION', '1')
    monkeypatch.setattr(learning, '_adapter', None)
    monkeypatch.setattr(learning, '_adapter_error', None)
    monkeypatch.setattr(learning.importlib, 'import_module', lambda name: Candidate)
    assert learning.adapter() is None
    assert 'domain gate' in learning._adapter_error
    assert learning.predict({}, {'now': 0})['mastery'] == 0.15


def test_numeric_answers_independently_recomputed():
    for variant in range(4):
        n = variant+2
        expected = {
            'fractions': Fraction(3, 2*n),
            'signed_numbers': 4,
            'ratios': (4+n)*(5+n),
            'equations': n+1,
            'coordinates': n,
            'linear_functions': 4*n-3,
            'probability': Fraction(n, 2*n+3),
            'descriptive_stats': n+2,
        }
        for cid, value in expected.items():
            assert Fraction(QUESTIONS[f'{cid}-{variant+1}']['answer_text']) == value


def test_symbolic_variants_by_substitution():
    for variant in range(4):
        n = variant+2
        for x in (-3, 0, 2, 7):
            assert n*(x+3)+2*x == (n+2)*x+3*n
            assert (x+n)*(x+1) == x*x+(n+1)*x+n
        for x in (n, n+2):
            assert (x-n)*(x-n-2) == 0


def test_dag_cycle_rejected(monkeypatch):
    from app.curriculum import CONCEPTS
    monkeypatch.setitem(CONCEPTS['fractions'], 'prerequisites', ['quadratics'])
    with pytest.raises(ValueError, match='cycle'):
        validate_curriculum()


def test_item_calibration_monotonic_and_smoothed():
    q = QUESTIONS['fractions-1']
    easier = {q['id']: {'count': 40, 'successes': 35, 'pooled_rate': 0.5}}
    harder = {q['id']: {'count': 40, 'successes': 5, 'pooled_rate': 0.5}}
    assert learning.item_probability({'mastery': 0.4}, q, easier)['p_correct'] > learning.item_probability({'mastery': 0.4}, q, harder)['p_correct']
    assert learning.item_probability({'mastery': 0.8}, q, harder)['p_correct'] > learning.item_probability({'mastery': 0.2}, q, harder)['p_correct']
    cold = learning.item_probability({}, q)
    assert cold['item_logit_offset'] == 0 and cold['calibration_status'] == 'low_data'
    assert 0 < cold['p_correct'] < 1


def test_diagnostic_order_depends_on_uncertainty_and_prerequisites():
    candidates = list(QUESTIONS.values())
    cold, reason = learning.recommend({}, candidates, 'diagnostic')
    assert 'Coverage-constrained' in reason and 'not a certainty' in reason
    states = {cold['concept_id']: {'mastery': 0.995, 'attempts': 20}}
    informed, _ = learning.recommend(states, candidates, 'diagnostic')
    assert informed['concept_id'] != cold['concept_id']


def test_every_distractor_has_specific_tentative_crosscheck():
    for q in QUESTIONS.values():
        assert set(q['distractor_diagnoses']) == {o['id'] for o in q['options'] if o['id'] != q['answer_id']}
        for option_id in q['distractor_diagnoses']:
            d = learning.diagnose(q, False, option_id, 0.8)
            assert d['category'] in {'conceptual', 'calculation', 'procedural'}
            assert d['alternatives'] and d['next_action'] and d['confidence'] < 0.5
            assert 'does not prove' in d['reason']


def test_native_parameter_contracts_and_independent_crosschecks():
    from app import courses
    from app.curriculum import CONCEPTS, SOURCES, course_concepts
    # Authored mathematics lessons carry eight blocks. Every other course is materialised
    # into the same registry with four, so the assertion is scoped to the authored course
    # rather than the merged registry.
    authored = course_concepts(courses.DEFAULT_COURSE_ID)
    expected = {'linear_functions': {'m', 'b', 'value'}, 'quadratics': {'a', 'b', 'c', 'value'},
                'systems': {'m1', 'b1', 'm2', 'b2', 'value'}, 'probability': {'n', 'p'}}
    for cid, parameters in expected.items():
        assert {p['id'] for p in CONCEPTS[cid]['simulation']['parameters']} == parameters
    p = {p['id']: p['value'] for p in CONCEPTS['systems']['simulation']['parameters']}
    x = (p['b2'] - p['b1']) / (p['m1'] - p['m2'])
    assert x == 4 and p['m1'] * x + p['b1'] == 3
    assert p['m1'] * x + p['b1'] == p['m2'] * x + p['b2']
    assert all(len(c['blocks']) == 8 for c in authored.values())
    assert all(len(c['blocks']) == 4 for cid, c in CONCEPTS.items() if cid not in authored)
    assert all(s['status'] == 'external_link_only' for s in SOURCES)
    assert 'CC BY-NC-SA 4.0' in SOURCES[0]['license']
    assert not any('CC BY 4.0' in s['license'] for s in SOURCES)


def _mastered(concept_id, times=60, now=1000):
    """A learner state for one concept after ``times`` consecutive correct answers."""
    state = {}
    for step in range(times):
        state = learning.update(state, True, None, now + step)
    return {concept_id: state}


def test_practice_skips_a_concept_the_learner_has_already_mastered(monkeypatch):
    """The knowledge map has to save time by skipping known content, not re-drill it.

    Regression: the selector ranked candidates by missing prerequisites and then by how
    close the predicted success probability sat to the target. Neither term penalised a
    mastered concept, so a learner at mastery 0.995 out-ranked every unseen concept on
    both counts and was served the same concept forever - the graph was measured and
    then ignored.
    """
    monkeypatch.setenv('HARNESS_ADAPTATION', '0')
    mastered = _mastered('fractions')
    assert mastered['fractions']['mastery'] >= learning.MASTERY_THRESHOLD

    # Two unseen candidates, one of which has unmet prerequisites.
    candidates = [QUESTIONS['fractions-1'], QUESTIONS['signed_numbers-1'],
                  QUESTIONS['ratios-1']]
    picked, reason = learning.recommend(mastered, candidates, 'practice', None, 0.7)
    assert picked['concept_id'] != 'fractions', (
        'a mastered concept was selected again while unseen concepts were available')
    assert 'skipped' in reason or 'Advanced past' in reason


def test_practice_falls_back_to_a_mastered_concept_when_nothing_else_remains(monkeypatch):
    """Mastered concepts are demoted, never dropped: ``min`` must always return one."""
    monkeypatch.setenv('HARNESS_ADAPTATION', '0')
    states = _mastered('fractions')
    states['ratios'] = _mastered('ratios', times=10)['ratios']
    candidates = [QUESTIONS['fractions-1'], QUESTIONS['ratios-1']]
    picked, reason = learning.recommend(states, candidates, 'practice', None, 0.7)
    assert picked['concept_id'] in {'fractions', 'ratios'}
    assert 'Every available concept is at or above mastery' in reason


def test_practice_prefers_a_concept_whose_prerequisites_are_met(monkeypatch):
    """Unmet prerequisites still gate new material, after the mastery rule."""
    monkeypatch.setenv('HARNESS_ADAPTATION', '0')
    from app.curriculum import CONCEPTS
    dependent = next(cid for cid, c in CONCEPTS.items()
                     if c['prerequisites'] and cid != 'ratios')
    gated = next((cid for cid in CONCEPTS[dependent]['prerequisites']), None)
    assert gated, 'expected at least one concept with a prerequisite'
    candidates = [QUESTIONS[f'{dependent}-1'], QUESTIONS['ratios-1']]
    picked, _ = learning.recommend({}, candidates, 'practice', None, 0.7)
    assert picked['concept_id'] == 'ratios', (
        f'picked {picked["concept_id"]}, which has unmet prerequisites')


def test_mastery_threshold_is_shared_by_gating_and_the_skip_rule(monkeypatch):
    """One constant decides both, so the two cannot drift apart."""
    assert 0 < learning.MASTERY_THRESHOLD < 1
    monkeypatch.setenv('HARNESS_ADAPTATION', '0')
    # A single correct answer is still below the threshold, so the concept stays "new":
    # the payload must not claim to have skipped known content.
    states = {'fractions': dict(_mastered('fractions', times=1)['fractions'])}
    assert states['fractions']['mastery'] < learning.MASTERY_THRESHOLD
    picked, reason = learning.recommend(states, [QUESTIONS['fractions-1']], 'practice', None, 0.7)
    assert picked['concept_id'] == 'fractions'
    assert 'Advanced past' not in reason
