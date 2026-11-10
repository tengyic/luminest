"""Teaching and practice coverage for the requested courses.

The six courses the product promises — AP Macroeconomics, AP Microeconomics,
AP Biology, AP Chemistry, Algebra 2 and AP Calculus — are materialised from their own
scope-and-sequence rather than hand-authored. That makes coverage a property worth
asserting rather than assuming: every unit must have practice, every concept must be
teachable, and a concept with no lesson record at all must say so instead of inventing
one.

These assertions are deliberately about the *requested* courses. Other courses in the
registry are covered by ``test_multisubject.py``'s per-course harness checks.
"""

import pytest

from app import courses, curriculum, tutor
from app.config import Settings

REQUESTED = ('ap_macroeconomics', 'ap_microeconomics', 'ap_biology',
             'ap_chemistry', 'algebra_2', 'ap_calculus')

#: A generated course-map lesson is four blocks (summary, placement, retrieval,
#: reflection). The tutor must treat that as teachable material, not as an absence.
TEACHABLE_TIERS = {'authored', 'generated'}


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    # Empty, not merely absent: a developer checkout has a real provider in backend/.env,
    # and clearing the variable alone lets dotenv fill it back in, which turned this
    # coverage test into 500+ live HTTP calls and a timeout. An explicit empty value is
    # the only way to say "no model" that survives .env loading.
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', '')
    for name in ('HARNESS_TUTOR_URL', 'HARNESS_TUTOR_MODEL', 'HARNESS_TUTOR_KEY'):
        monkeypatch.delenv(name, raising=False)
    return Settings.from_env()


def test_every_requested_course_is_registered():
    for course_id in REQUESTED:
        spec = courses.course(course_id)
        assert spec.id == course_id
        graph = courses.graph_for(course_id)
        assert graph.nodes, f'{course_id} has no concepts'
        assert not graph.errors(), f'{course_id} has graph errors: {graph.errors()}'


def test_every_requested_course_has_practice_in_every_unit():
    for course_id in REQUESTED:
        graph = courses.graph_for(course_id)
        questions = curriculum.course_questions(course_id)
        units_with_items = {q['concept_id'] for q in questions.values()}
        missing = [n.id for n in graph.nodes.values() if n.id not in units_with_items]
        assert not missing, f'{course_id} has concepts with no practice item: {missing[:5]}'


def test_every_requested_course_concept_has_four_distinct_options():
    for course_id in REQUESTED:
        for qid, question in curriculum.course_questions(course_id).items():
            texts = [option['text'] for option in question['options']]
            assert len(texts) == 4, f'{qid} has {len(texts)} options'
            assert len(set(texts)) == 4, f'{qid} repeats an option'
            assert question['answer_id'] in {o['id'] for o in question['options']}, qid
            assert set(question['distractor_diagnoses']) == (
                {o['id'] for o in question['options']} - {question['answer_id']}), qid


def test_every_requested_course_concept_is_teachable(settings):
    """No concept in a requested course may be a dead end for the tutor."""
    for course_id in REQUESTED:
        graph = courses.graph_for(course_id)
        for node_id in graph.nodes:
            concept = curriculum.CONCEPTS.get(node_id)
            assert tutor._lesson_tier(concept) in TEACHABLE_TIERS, (
                f'{course_id}/{node_id} has no teachable lesson record')
            node = graph.nodes[node_id].to_dict()
            text, provider, grounding, actions = tutor.respond(
                settings, node_id, 'Explain this concept.', [],
                retrieval_context={'node': node,
                                   'prerequisites': [graph.nodes[p].to_dict()
                                                     for p in graph.parents(node_id)][:8],
                                   'dependants': [graph.nodes[c].to_dict()
                                                  for c in graph.children(node_id)][:6]})
            assert text.strip(), f'{course_id}/{node_id} produced an empty answer'
            # No model is configured in this fixture, so the answer must be the declared
            # curriculum fallback and must name itself as such rather than pretending a
            # model wrote it.
            assert provider == 'model-required', (course_id, node_id, provider)
            assert grounding and grounding[0]['title'], node_id
            assert actions, node_id


def test_a_generated_lesson_names_the_thing_it_lacks(settings):
    """The answer must not imply a worked example that the course does not contain."""
    node_id = 'ap_biology_passive_versus_active_transport'
    graph = courses.graph_for('ap_biology')
    node = graph.nodes[node_id].to_dict()
    text, _, grounding, actions = tutor.respond(
        settings, node_id, 'Why does active transport stop when respiration stops?', [],
        retrieval_context={'node': node,
                           'prerequisites': [graph.nodes[p].to_dict()
                                             for p in graph.parents(node_id)],
                           'dependants': [graph.nodes[c].to_dict()
                                          for c in graph.children(node_id)]})
    assert 'no worked example' in text
    # Case-insensitive: the concept is titled "Passive versus Active Transport", and the
    # assertion is that the answer names the concept, not that it repeats its casing.
    assert 'active transport' in text.lower()
    assert grounding[0]['title'].startswith('Generated course-map lesson:')
    # It teaches from the course's own summary rather than deflecting the question. The
    # summary was rewritten when the course was rebuilt, so the assertion names the idea
    # (a gradient crossed with ATP) instead of one word from the old prose.
    assert 'gradient' in text.lower() or 'atp' in text.lower()
    # And it must not offer an action the lesson cannot deliver.
    assert 'Check the worked example' not in actions
    assert any('course source' in action for action in actions)
