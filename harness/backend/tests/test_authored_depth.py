"""Depth is a measured property, not a label.

The 2026-11-13 review noted that a 2,205-node graph carried only 30 hand-written
lessons and the rest were generated four-block outlines with no worked example.
These tests pin the honest distinction: authored lessons live in the source tree,
carry a numbered worked example and an independent check, map to a real graph
node, and are never marked generated. Generated lessons must keep saying that
they have no worked example.
"""

from app import curriculum
from app import model_config, tutor
from app.authored_unit_exponents import TARGETS as UNIT_TARGETS


def test_the_authored_unit_is_present_and_fully_written():
    share = curriculum.authored_share('integrated_math_1')
    assert share['authored_concepts'] >= 38
    assert share['written_concepts'] == share['authored_concepts']
    assert share['reviewed_concepts'] == share['authored_concepts']
    assert share['model_drafted_concepts'] == 0
    assert share['overlay_concepts'] == 0

    for cid in UNIT_TARGETS:
        entry = curriculum.CONCEPTS[cid]
        assert not entry.get('generated'), f'{cid} must not be flagged generated'
        assert entry.get('has_lesson') is True
        blocks = entry.get('blocks') or []
        assert len(blocks) == 8, f'{cid} must have the full authored lesson shape'
        worked = [b for b in blocks if b.get('kind') == 'worked_example']
        assert len(worked) == 1, f'{cid} needs exactly one worked example'
        body = worked[0]['body']
        assert '1.' in body and '4.' in body, f'{cid} worked example needs numbered steps'
        assert any(word in body.lower() for word in ('check', 'verify', 'confirm')), \
            f'{cid} worked example must name its own verification'


def test_every_authored_lesson_maps_to_a_real_graph_node():
    for cid, node_id in UNIT_TARGETS.items():
        assert node_id in curriculum.KNOWLEDGE_GRAPH.nodes, f'{cid} -> missing node {node_id}'
        node = curriculum.KNOWLEDGE_GRAPH.nodes[node_id]
        assert getattr(node, 'has_lesson', False), f'{node_id} not marked as taught'
        assert curriculum.LESSON_TARGETS[cid] == node_id


def test_the_unit_has_four_answerable_variants_per_concept():
    for cid in UNIT_TARGETS:
        variants = [q for q in curriculum.QUESTIONS.values() if q['concept_id'] == cid]
        assert len(variants) == 4, f'{cid} needs four variants'
        for q in variants:
            texts = [o['text'] for o in q['options']]
            assert len(set(texts)) == 4, f'{q["id"]} has duplicate choices'
            assert q['answer_text'] in texts
            assert q['explanation'].strip()
            assert len(q['distractor_diagnoses']) == 3


def test_generated_lessons_still_declare_the_missing_worked_example(monkeypatch):
    """A generated lesson must never be presented as an authored one."""
    generated = [e for e in curriculum.CONCEPTS.values() if e.get('generated')]
    assert generated, 'the generated layer must still exist'
    # Pin "no model configured" rather than depending on .env or the override cache.
    monkeypatch.setattr(tutor.model_config, 'effective',
                        lambda settings: model_config.ModelConfig())
    from types import SimpleNamespace
    settings = SimpleNamespace(data_dir=None)
    cid = next(c for c, e in curriculum.CONCEPTS.items() if e.get('generated'))
    text, answerer, grounding, actions = tutor.respond(
        settings, cid, 'Explain this idea.', history=[])
    assert 'no worked example' in text.lower()
    assert not any('worked example' in a.lower() for a in actions)
    assert answerer == tutor.MODEL_REQUIRED_LABEL


def test_health_reports_the_split_honestly():
    """`authored_share` is the number the API publishes; it cannot be inflated."""
    share = curriculum.authored_share('integrated_math_1')
    assert share['concepts'] == share['authored_concepts'] + share['generated_concepts']
    assert share['written_concepts'] == share['reviewed_concepts'] + share['model_drafted_concepts']
