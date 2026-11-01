"""Direct unit tests for ``app.knowledge_graph``.

Until now the concept-graph engine was only exercised *indirectly* - through the
API routes (``test_api`` / ``test_multisubject``), the KST layer (``test_kst``)
and the planner (``test_planner``). A regression in the engine itself (cycle
detection, topological determinism, search scoring, pack round-trip) could
therefore surface as a confusing failure far from its cause. These tests pin the
engine's own contract, plus the structural integrity of every shipped pack.
"""

import pytest

from app.courses import COURSES, graph_for
from app.knowledge_graph import (GRAPH_SCHEMA, ConceptNode, KnowledgeGraph,
                                 Taxonomy, load_pack, slug)


# --------------------------------------------------------------- tiny fixtures

def _chain() -> KnowledgeGraph:
    """a <- b <- c, with a soft teaching edge a -> b."""
    graph = KnowledgeGraph()
    for cid in ('a', 'b', 'c'):
        graph.add(ConceptNode(id=cid, title=cid.upper(), strand='S', unit='U'))
    graph.link('a', 'b')
    graph.link('b', 'c')
    graph.link_sequence('a', 'b')
    return graph


def test_prerequisite_and_sequence_edges_are_tracked_separately():
    graph = _chain()
    assert graph.edges == [('a', 'b'), ('b', 'c')]
    assert graph.sequence_edges == [('a', 'b')]
    assert graph.parents('b') == ['a']
    assert graph.all_parents('b') == ['a']  # hard + sequence, deduplicated
    assert graph.children('a') == ['b']
    assert graph.sequence_children('a') == ['b']
    assert graph.ancestors('c') == ['a', 'b']
    assert graph.descendants('a') == ['b', 'c']


def test_duplicate_ids_are_rejected_unless_replaced():
    graph = KnowledgeGraph()
    graph.add(ConceptNode(id='x', title='X', strand='S', unit='U'))
    with pytest.raises(ValueError, match='Duplicate'):
        graph.add(ConceptNode(id='x', title='X2', strand='S', unit='U'))
    graph.add(ConceptNode(id='x', title='X3', strand='S', unit='U'), replace=True)
    assert graph.nodes['x'].title == 'X3'


# ------------------------------------------------------------------- validation

def test_validate_catches_self_loop_unknown_prerequisite_and_bad_metadata():
    graph = KnowledgeGraph()
    graph.add(ConceptNode(id='a', title='A', strand='S', unit='U',
                          prerequisites=['a', 'ghost'], tier='bogus', difficulty=9))
    kinds = {(issue.kind, issue.concept_id) for issue in graph.validate()}
    assert ('self_loop', 'a') in kinds
    assert ('unknown_prerequisite', 'a') in kinds
    assert ('invalid_tier', 'a') in kinds
    assert ('invalid_difficulty', 'a') in kinds
    assert {i.kind for i in graph.errors()} >= {'self_loop', 'unknown_prerequisite'}


def test_cycles_are_detected_with_a_concrete_path():
    graph = KnowledgeGraph()
    for cid in ('a', 'b'):
        graph.add(ConceptNode(id=cid, title=cid.upper(), strand='S', unit='U'))
    graph.link('a', 'b')
    graph.link('b', 'a')
    cycles = graph._cycles()
    assert cycles, 'a hard prerequisite cycle must be reported'
    node_id, path = cycles[0]
    assert node_id in ('a', 'b') and ' -> ' in path


def test_sequence_contradicting_prerequisites_is_reported():
    graph = KnowledgeGraph()
    for cid in ('a', 'b'):
        graph.add(ConceptNode(id=cid, title=cid.upper(), strand='S', unit='U'))
    graph.link('a', 'b')
    graph.link_sequence('b', 'a')  # teaching order contradicts the hard edge
    kinds = {issue.kind for issue in graph.validate()}
    assert 'sequence_cycle' in kinds


def test_raise_if_invalid_raises_on_errors_only():
    graph = KnowledgeGraph()
    graph.add(ConceptNode(id='a', title='A', strand='S', unit='U', tier='bogus'))
    graph.raise_if_invalid()  # warnings only: must not raise
    graph.add(ConceptNode(id='b', title='B', strand='S', unit='U', prerequisites=['ghost']))
    with pytest.raises(ValueError, match='unknown_prerequisite'):
        graph.raise_if_invalid()


# ------------------------------------------------------------- structure/order

def test_topological_order_is_deterministic_and_respects_edges():
    first = _chain().topological_order()
    second = _chain().topological_order()
    assert first == second, 'same graph must give byte-identical order'
    order = {cid: i for i, cid in enumerate(first)}
    assert order['a'] < order['b'] < order['c']


def test_topological_order_refuses_a_cyclic_graph():
    graph = KnowledgeGraph()
    for cid in ('a', 'b'):
        graph.add(ConceptNode(id=cid, title=cid.upper(), strand='S', unit='U'))
    graph.link('a', 'b')
    graph.link('b', 'a')
    with pytest.raises(ValueError, match='cycle'):
        graph.topological_order()


def test_depths_roots_leaves_and_subgraph():
    graph = _chain()
    assert graph.depths() == {'a': 0, 'b': 1, 'c': 2}
    assert graph.roots() == ['a'] and graph.leaves() == ['c']
    assert graph.subgraph(['c'], radius=1) == {'b', 'c'}
    assert graph.subgraph(['c'], radius=0) == {'c'}


# ------------------------------------------------------------------ search API

def test_search_scores_exact_id_above_title_above_keywords():
    graph = KnowledgeGraph()
    graph.add(ConceptNode(id='fraction_equivalence', title='Fraction Equivalence',
                          strand='S', unit='U', keywords=['equivalence'],
                          summary='two fractions naming one number'))
    graph.add(ConceptNode(id='equivalence_relations', title='Equivalence Relations',
                          strand='S', unit='U', summary=''))
    hits = graph.search('equivalence')
    # exact-title 'Fraction Equivalence'? no - 'equivalence_relations' has the
    # needle as an id; both title matches outrank the keyword-only hit.
    assert hits[0]['id'] in ('fraction_equivalence', 'equivalence_relations')
    assert hits[0]['score'] >= hits[-1]['score']
    assert all(row['score'] > 0 for row in hits)


def test_search_is_bounded_and_empty_safe():
    graph = _chain()
    assert graph.search('') == []
    assert graph.search('   ') == []
    hits = graph.search('c', limit=1)
    assert len(hits) == 1 and hits[0]['id'] == 'c'


# ------------------------------------------------------- serialisation round-trip

def test_from_pack_restores_the_same_graph():
    graph = KnowledgeGraph(Taxonomy({'S': {'U': ['T1', 'T2']}}))
    graph.add(ConceptNode(id='a', title='A', strand='S', unit='U', topic='T1',
                          prerequisites=['b'], keywords=['k'],
                          provenance={'source': 'test', 'licence': 'cc0'}))
    graph.add(ConceptNode(id='b', title='B', strand='S', unit='U', topic='T2'))
    restored = KnowledgeGraph.from_pack(graph.to_pack(name='test_pack'))
    assert set(restored.nodes) == {'a', 'b'}
    assert restored.edges == [('b', 'a')]  # edges point prerequisite -> concept
    assert restored.taxonomy.topics('S', 'U') == ['T1', 'T2']
    assert restored.nodes['a'].provenance['source'] == 'test'


def test_combine_merges_packs_with_later_wins():
    left = KnowledgeGraph()
    left.add(ConceptNode(id='x', title='Old', strand='S', unit='U'))
    right = KnowledgeGraph()
    right.add(ConceptNode(id='x', title='New', strand='S', unit='U'))
    from app.knowledge_graph import combine
    merged = combine([left, right])
    assert merged.nodes['x'].title == 'New'


def test_from_dict_normalises_malformed_records():
    node = ConceptNode.from_dict({'id': '', 'title': 'Fractions!', 'prerequisites': 'oops',
                                  'difficulty': 'not-a-number', 'junk': 'dropped'})
    assert node.id == slug('Fractions!')
    # a bare string is ONE reference, never one entry per character
    assert node.prerequisites == ['oops']
    assert node.difficulty == 3  # bad int falls back to the default
    assert not hasattr(node, 'junk')  # unknown fields are dropped, not crashes
    assert ConceptNode.from_dict({'title': 'X', 'prerequisites': '   '}).prerequisites == []
    assert ConceptNode.from_dict({'title': 'X'}).keywords == []


def test_slug_is_stable_ascii_and_lowercase():
    assert slug('Équations du Second Degré') == 'equations_du_second_degre'
    assert slug('   ') == 'unnamed'
    assert slug('A  B') == slug('A  B')


# ----------------------------------------------------------------- coverage

def test_coverage_reports_mastery_ready_and_units():
    graph = _chain()
    report = graph.coverage({'a': {'mastery': 0.9}, 'b': {'mastery': 0.2}}, threshold=0.6)
    assert report['mastered'] == 1 and report['total'] == 3
    assert report['units']['U']['mastered'] == 1
    assert report['ready'] == ['b'], 'b has its only prerequisite mastered'


def test_payload_carries_both_edge_kinds_and_stats():
    graph = _chain()
    payload = graph.to_payload()
    kinds = {edge['kind'] for edge in payload['edges']}
    assert kinds == {'prerequisite', 'sequence'}
    assert payload['schema'] == GRAPH_SCHEMA
    assert payload['stats']['concepts'] == 3
    node_ids = [node['id'] for node in payload['nodes']]
    assert node_ids == graph.topological_order()


# ------------------------------------------------------------- shipped packs

@pytest.mark.parametrize('course_spec', COURSES, ids=lambda c: c.id)
def test_every_shipped_pack_is_structurally_valid(course_spec):
    graph = graph_for(course_spec.id)
    assert len(graph.nodes) > 0, f'{course_spec.id} ships an empty pack'
    graph.raise_if_invalid()


def test_shipped_packs_carry_provenance_and_unique_ids():
    import json
    from pathlib import Path
    from app.courses import PACK_DIR
    for spec in COURSES:
        pack = json.loads((PACK_DIR / f'{spec.pack}.json').read_text(encoding='utf-8'))
        ids = [c['id'] for c in pack['concepts']]
        assert len(ids) == len(set(ids)), f'{spec.pack}: duplicate concept ids'
        for node in pack['concepts']:
            assert node.get('provenance', {}).get('licence'), \
                f'{spec.pack}:{node["id"]} has no licence provenance'
            assert isinstance(node.get('prerequisites'), list)


def test_shipped_packs_declared_metadata_names_the_pipeline():
    import json
    from pathlib import Path
    from app.courses import PACK_DIR
    for spec in COURSES:
        pack = json.loads((PACK_DIR / f'{spec.pack}.json').read_text(encoding='utf-8'))
        assert pack.get('metadata', {}).get('generated_by') == 'app.ingest.pipeline'
