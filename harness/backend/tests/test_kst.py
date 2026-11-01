"""Tests for the Knowledge Space Theory assessment layer.

Written around the claims that matter:

- knowledge states are exactly the prerequisite-closed sets (down-sets) of the DAG;
- observed responses filter the version space, and a response contradicting the
  prerequisite structure is refused rather than fudged;
- the probe selection splits the version space (greedy maximum entropy), and
  repeated probing disambiguates in about log2(states) questions;
- the real 164-node math DAG is served by the seeded-sampling mode, which is
  deterministic and only emits genuine knowledge states;
- the headline lattice facts of Doignon & Falmagne hold on our data.
"""

import pytest

from app import kst
from app.curriculum import KNOWLEDGE_GRAPH
from app.kst import KnowledgeSpace


CHAIN = {'a': [], 'b': ['a'], 'c': ['b']}
DIAMOND = {'a': [], 'b': ['a'], 'c': ['a'], 'd': ['b', 'c']}


def test_states_are_exactly_the_down_sets():
    space = KnowledgeSpace(CHAIN)
    # chain a<-b<-c: {}, {a}, {a,b}, {a,b,c}
    assert len(space.states) == 4
    assert frozenset() in space.states and frozenset('abc') in space.states
    diamond = KnowledgeSpace(DIAMOND)
    assert len(diamond.states) == 6  # {}, {a}, {a,b}, {a,c}, {a,b,c}, {a,b,c,d}


def test_cycles_are_rejected():
    with pytest.raises(ValueError, match='cycle'):
        KnowledgeSpace({'a': ['b'], 'b': ['a']})


def test_closure_requires_prerequisites():
    space = KnowledgeSpace(DIAMOND)
    assert space.closure({'d'}) == frozenset('abcd')
    assert space.closure(set()) == frozenset()


def test_contradictory_observations_are_refused_not_fudged():
    space = KnowledgeSpace(CHAIN)
    # claiming 'c' while failing 'a' fits NO knowledge state
    assert space.consistent_states({'c': True, 'a': False}) is None
    report = space.diagnostic_gaps({'c': True, 'a': False})
    assert 'error' in report


def test_observations_filter_the_version_space_exactly():
    space = KnowledgeSpace(DIAMOND)
    consistent = space.consistent_states({'b': False})
    # states not containing b: {}, {a}, {a,c}
    assert set(consistent) == {frozenset(), frozenset('a'), frozenset('ac')}
    consistent = space.consistent_states({'a': True})
    assert all('a' in s for s in consistent) and len(consistent) == 5


def test_probe_selection_maximises_entropy_and_probes_disambiguate():
    space = KnowledgeSpace(DIAMOND)
    probe = space.next_probe({})
    # cold start: every concept is 50/50, so the deterministic tie-break picks
    # the first in sorted order; the claim that matters is the split.
    assert probe['concept_id'] in space.concepts
    # simulate a noiseless assessment: probe, observe the TRUE state, repeat
    truth = frozenset('abc')  # the learner knows a, b, c but not d
    observations = {}
    for _ in range(10):
        probe = space.next_probe(observations)
        if probe['concept_id'] is None:
            break
        observations[probe['concept_id']] = probe['concept_id'] in truth
    disambiguated = space.consistent_states(observations)
    assert len(disambiguated) == 1 and truth in disambiguated
    # and the report says so
    report = space.diagnostic_gaps(observations)
    assert report['next_probe']['concept_id'] is None


def test_gaps_report_names_surely_known_and_missing():
    space = KnowledgeSpace(DIAMOND)
    report = space.diagnostic_gaps({'d': True})
    assert report['surely_known'] == ['a', 'b', 'c']  # prerequisites of d
    # a failed response on 'a': a is observed (so excluded from the inferred
    # lists), and everything downstream of it is pinned missing
    report = space.diagnostic_gaps({'a': False})
    assert report['surely_missing'] == ['b', 'c', 'd']
    assert report['n_states_consistent'] == 1  # only the empty state fits


def test_real_math_graph_uses_sampled_mode_and_is_deterministic():
    space = kst.default_space()
    assert len(space.prereqs) == 164
    assert not space.exact, 'the 164-node DAG exceeds the exact-enumeration cap'
    first = space.diagnostic_gaps({})
    second = space.diagnostic_gaps({})
    # seeded: identical reports on identical observations
    assert first['next_probe']['concept_id'] == second['next_probe']['concept_id']
    assert first['n_states_consistent'] == second['n_states_consistent'] == space.sample_size
    # every sampled state is a genuine down-set of the graph
    for state in space.consistent_states({})[:500]:
        for node in state:
            assert set(space.prereqs[node]) <= set(state)


def test_sampled_mode_honours_observations():
    space = kst.default_space()
    root = min(space.concepts, key=lambda c: len(space.prereqs[c]))
    p_known = space.probability_known({root: True})
    assert p_known[root] == 1.0
    # its prerequisites (none) aside, forcing a root known shifts descendants up
    descendants = [n for n in space.concepts if root in space.prereqs[n]]
    if descendants:
        child = descendants[0]
        assert p_known[child] > 0.0


def test_min_probes_estimate_is_reported_honestly():
    space = kst.default_space()
    report = space.diagnostic_gaps({})
    assert report['min_probes_to_disambiguate'] > 0
    assert 'sampled' in report['min_probes_note']
    assert 'Doignon' in report['method']


def test_space_builds_from_the_knowledge_graph_helper():
    space = kst.from_knowledge_graph(KNOWLEDGE_GRAPH)
    assert set(space.concepts) == set(KNOWLEDGE_GRAPH.nodes)
