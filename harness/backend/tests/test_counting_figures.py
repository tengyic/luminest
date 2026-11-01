"""Counting figures: permutations against combinations, generated rather than drawn.

The template table used to send every "permutation" and "combination" concept to the
binomial rule, which drew a sampling distribution. The concept's own idea is a contrast —
the same selection counted with and without order, differing by exactly r! — and it has a
curve, C(n,r) as r varies, so the symbolic engine can express it without a language model.

These tests pin the mathematics, not the prose: if the readouts and the curve disagree,
the figure is worse than none.
"""

import math

import pytest

from app import figures
from app.mathkit import build as build_simulation
from app.mathkit import expression as ex
from app.mathkit.templates import template_for

CONCEPT = {'id': 'permutations_and_combinations',
           'title': 'Permutations and combinations',
           'topic': 'Conditional probability and counting',
           'keywords': ['combination', 'order', 'permutation', 'selection']}


class IsolatedGraph:
    nodes: dict = {}

    def parents(self, node_id): return []
    def children(self, node_id): return []
    def siblings(self, node_id): return []
    def in_unit(self, node_id): return [node_id]
    def ancestors(self, node_id): return []
    def descendants(self, node_id): return []


def readout(payload, label_start):
    for item in payload['readouts']:
        if item['label'].startswith(label_start):
            return item['value']
    raise AssertionError(f'no readout starting {label_start!r} in '
                         f'{[item["label"] for item in payload["readouts"]]}')


# ---------------------------------------------------------------- the expression engine

def test_factorial_is_defined_on_the_whole_numbers_only():
    assert ex.evaluate(ex.parse('fact(n)', variables=('n',)), {'n': 5}) == 120
    # A continuous slider must not produce a plausible-looking count for 3.7.
    assert math.isnan(ex.evaluate(ex.parse('fact(n)', variables=('n',)), {'n': 3.7}))
    assert math.isnan(ex.evaluate(ex.parse('fact(n)', variables=('n',)), {'n': -1}))


def test_choose_and_permute_agree_with_the_stdlib():
    for n in range(1, 11):
        for r in range(0, n + 1):
            env = {'n': n, 'r': r}
            assert ex.evaluate(ex.parse('choose(n, r)', variables=('n', 'r')), env) == math.comb(n, r)
            assert ex.evaluate(ex.parse('permute(n, r)', variables=('n', 'r')), env) == math.perm(n, r)


def test_choosing_more_than_available_is_zero_not_an_error():
    """The counting convention, and the reason the curve falls to zero past r = n."""
    env = {'n': 4, 'r': 6}
    assert ex.evaluate(ex.parse('choose(n, r)', variables=('n', 'r')), env) == 0
    assert ex.evaluate(ex.parse('permute(n, r)', variables=('n', 'r')), env) == 0


# ---------------------------------------------------------------- the template

def test_the_template_claims_the_concept():
    spec = template_for(CONCEPT)
    assert spec.kind == 'arrangements'


def test_the_curve_is_the_binomial_coefficients():
    payload = figures.figure_for(CONCEPT, IsolatedGraph(), {}, subject_kind='mathematics')
    n = int([p for p in payload['parameters'] if p['id'] == 'n'][0]['value'])
    counts = {int(point[0]): point[1] for point in payload['series']}
    for r in range(0, n + 1):
        assert counts[r] == pytest.approx(math.comb(n, r)), (n, r)
    # Past n there is nothing to choose, so the count is zero rather than undefined.
    assert counts[n + 1] == 0


def test_the_curve_has_one_point_per_integer():
    """The default sample count repeats each integer ~25 times and draws a staircase."""
    payload = figures.figure_for(CONCEPT, IsolatedGraph(), {}, subject_kind='mathematics')
    xs = [point[0] for point in payload['series']]
    assert len(xs) == len(set(xs))


def test_the_two_counts_differ_by_exactly_r_factorial():
    """This is the concept. If the readouts do not show it, the figure teaches nothing."""
    spec = template_for(CONCEPT)
    for n, r in ((5, 2), (7, 3), (6, 4)):
        payload = build_simulation(spec, {'n': n, 'r': r})
        assert int(readout(payload, 'Ordered arrangements')) == math.perm(n, r)
        assert int(readout(payload, 'Unordered selections')) == math.comb(n, r)
        assert int(readout(payload, 'Ratio P')) == math.factorial(r)


def test_an_impossible_selection_is_explained_rather_than_crashing():
    payload = build_simulation(template_for(CONCEPT), {'n': 3, 'r': 5})
    assert 'cannot select 5' in payload['steps'][0]
    assert readout(payload, 'Ordered arrangements') == '0'
    assert readout(payload, 'Ratio P') == '—'


def test_the_figure_is_stable_across_calls():
    """Deterministic by concept id, so a lesson does not change shape between turns."""
    first = build_simulation(template_for(CONCEPT))
    second = build_simulation(template_for(CONCEPT))
    assert first['series'] == second['series']
    assert [p['value'] for p in first['parameters']] == [p['value'] for p in second['parameters']]
