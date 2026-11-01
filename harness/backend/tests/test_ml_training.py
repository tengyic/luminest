"""Tests for the math-model training path: honest protocol, working baselines,
and a license table that cannot silently drift.

The critical property is the split: TRAIN AND TEST SHARE NO STUDENT. A row-wise
split leaks a student's history across the boundary and inflates every metric.
"""

import json

import pytest

from ml.bkt import BKT, fit_em
from ml.datasets import (DATASET_LICENSES, Record, load_csv, synthetic_math,
                         write_synthetic_csv)
from ml.evaluate import auc, evaluate_model, split_by_students
from ml.train_math import BKTModel, run


def test_split_by_students_is_disjoint_and_total():
    records = synthetic_math(n_students=60, seed=7)
    train, test = split_by_students(records, test_fraction=0.25, seed=11)
    train_ids = {r.student_id for r in train}
    test_ids = {r.student_id for r in test}
    assert train_ids and test_ids
    assert not train_ids & test_ids, 'THE leak: a student in both sides'
    assert train_ids | test_ids == {r.student_id for r in records}
    assert len(train) + len(test) == len(records)


def test_split_is_seed_deterministic():
    records = synthetic_math(n_students=40, seed=3)
    a = split_by_students(records, seed=5)
    b = split_by_students(records, seed=5)
    assert {r.student_id for r in a[1]} == {r.student_id for r in b[1]}


def test_auc_recovers_perfect_and_random_rankings():
    assert auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert auc([1, 0], [0.5, 0.5]) == 0.5  # ties count half
    assert auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert auc([1, 1], [0.1, 0.2]) is None  # single-class: undefined, not zero


def test_bkt_em_improves_the_likelihood_on_its_own_data():
    rng_sequences = [[True, True, False, True], [True, True, True],
                     [False, True, True, True], [True, False, True]]
    from ml.bkt import _forward
    before = sum(_forward(seq, BKT())[1] for seq in rng_sequences)
    fitted = fit_em(rng_sequences, iterations=25)
    after = sum(_forward(seq, fitted)[1] for seq in rng_sequences)
    assert after >= before - 1e-9, 'EM must never decrease the training likelihood'
    assert 0 < fitted.prior < 1 and 0 < fitted.learn < 1


def test_trained_model_beats_chance_on_synthetic_data_with_real_learning_curves():
    """The synthetic generator encodes log-linear learning curves and per-student
    ability. A correct protocol must extract signal; a leaky one would report a
    fantasy number. We assert a modest but real margin above 0.5."""
    records = synthetic_math(n_students=150, seed=42)
    result = run(records, seed=42)
    assert result['auc_overall'] is not None
    assert result['auc_overall'] > 0.52
    assert all(0.0 <= v['auc'] <= 1.0 for v in result['per_skill'].values() if v['auc'])
    assert 'disjoint-student' in result['protocol']


def test_evaluation_predictions_use_earlier_responses_only():
    """Instrument the scorer: the history handed to predict() for a response at
    within-skill position k must be exactly that student's first k-1 responses
    on that skill -- never the row being scored."""
    records = [
        Record('s1', 'q1', 'skill', True, 1),
        Record('s1', 'q2', 'skill', False, 2),
        Record('s1', 'q3', 'skill', True, 3),
        Record('s2', 'q1', 'skill', False, 1),
        Record('s2', 'q2', 'skill', True, 2),
    ]
    seen = []

    class SpyModel:
        def fit(self, train_records):
            self.train_ids = {r.student_id for r in train_records}

        def predict(self, history, skill):
            seen.append(list(history))
            return 0.5

    model = SpyModel()
    result = evaluate_model(records, lambda: model, test_fraction=0.5, min_history=1)
    # exactly one student is held out; their predictions come only from their
    # own earlier responses on that skill
    assert result['n_test_students'] == 1
    assert seen in ([[True], [True, False]], [[False]])
    assert all(len(h) >= 1 for h in seen)
    assert result['n_test_predictions'] == len(seen)


def test_bkt_model_cold_start_uses_fitted_prior():
    records = synthetic_math(n_students=30, seed=2)
    model = BKTModel(iterations=3)
    model.fit(records)
    assert model.params  # fitted per-skill parameters exist
    p = model.predict([], 'fractions')
    assert 0.0 < p < 1.0


def test_csv_loader_roundtrip_and_drops_bad_rows(tmp_path):
    path = write_synthetic_csv(tmp_path / 'synth.csv', seed=9)
    records = load_csv(path, {'student': 'user_id', 'problem': 'problem_id',
                              'skill': 'skill', 'correct': 'correct'})
    assert records and all(isinstance(r, Record) for r in records)
    # per-student sequence positions are dense and start at 1
    for student in {r.student_id for r in records}:
        orders = sorted(r.order for r in records if r.student_id == student)
        assert orders == list(range(1, len(orders) + 1))
    # malformed rows are dropped, not imputed
    bad = tmp_path / 'bad.csv'
    bad.write_text('user_id,problem_id,skill,correct\ns1,p1,skill,1\n,p2,skill,0\n')
    assert len(load_csv(bad, {'student': 'user_id', 'problem': 'problem_id',
                              'skill': 'skill', 'correct': 'correct'})) == 1


def test_dataset_license_table_is_complete_and_non_commercial():
    """The make-or-break honesty table. Every entry must carry a real URL, a
    stated license, and an explicit commercial-use verdict. Today every
    verified candidate is research-only or ambiguous -- if someone adds a
    dataset claiming commercial use, this test forces them to have written it
    down deliberately."""
    assert DATASET_LICENSES, 'the license table must not be empty'
    names = set()
    for entry in DATASET_LICENSES:
        for field in ('name', 'url', 'license', 'license_url', 'citation'):
            assert entry.get(field), f'{entry.get("name")}: missing {field}'
        assert entry['url'].startswith(('http://', 'https://'))
        assert isinstance(entry['commercial_use'], bool)
        assert entry['license'] != 'Unknown'
        names.add(entry['name'])
    assert names == {'KDD Cup 2010 (Carnegie Learning tutor logs)',
                     'ASSISTments 2009-2010 (skill builder)',
                     'Eedi (NeurIPS 2020 Education Challenge)',
                     'Junyi Academy learning-activity dataset (2018-2019)',
                     'EdNet (Riiid, TOEIC English -- the current research model)'}
    assert not any(e['commercial_use'] for e in DATASET_LICENSES), \
        'no verified dataset currently grants commercial use; update the table AND the doc if that changes'


def test_run_result_carries_the_research_only_banner():
    records = synthetic_math(n_students=25, seed=4)
    result = run(records)
    banner = result['license_status']
    assert 'inherits the restriction' in banner
    assert 'train_on_opt_in_csv' in banner
