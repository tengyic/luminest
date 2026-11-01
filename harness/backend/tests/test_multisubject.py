"""The harness is not a mathematics app.

These tests exist because the mathematics-only build had a specific, quiet failure: the
symbolic engine matches a concept against mathematics templates and falls back to a
generic quadratic. Handed "Newton's second law" it did not error - it returned a parabola
labelled with the concept's name. A learner would have seen a meaningless curve presented
as physics, and nothing in the system would have objected.

So the tests here do two jobs.

1. **Pin the dispatch.** A mathematics course goes through the symbolic engine; every
   other subject gets a concept map built from real graph edges. Neither is allowed to
   silently become the other.
2. **Pin the isolation.** A learner enrolled in one course must never see another
   course's concepts, questions, projects or graph - in any endpoint, in any direction.

Everything asserted here is derived from the registry, so adding a course cannot make
these tests stale.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import course_builder, courses, figures
from app.config import Settings
from app.curriculum import (CONCEPTS, CONCEPT_COURSE, LESSON_TARGETS, QUESTIONS,
                            course_concepts, course_questions)
from app.ingest import policy
from app.main import create_app

NON_MATHEMATICS = [c for c in courses.COURSES if not c.uses_symbolic_engine]
MATHEMATICS = [c for c in courses.COURSES if c.uses_symbolic_engine]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def account(client, label):
    response = client.post('/api/v1/auth/register',
                           json={'name': label, 'email': f'{label}@example.test',
                                 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}, response.json()


def enrol(client, headers, course_id):
    response = client.patch('/api/v1/me', headers=headers, json={'course_id': course_id})
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ the registry


def test_every_declared_course_is_real():
    """A course that is declared but empty would be a picker entry that leads nowhere."""
    assert len(courses.COURSES) >= 2, 'the harness must ship more than one subject'
    assert len(NON_MATHEMATICS) >= 1, 'at least one non-mathematics course must exist'
    assert len(MATHEMATICS) >= 1, 'the authored mathematics course must exist'
    for spec in courses.COURSES:
        graph = courses.graph_for(spec.id)
        assert len(graph.nodes) >= 10, f'{spec.id} has only {len(graph.nodes)} nodes'
        assert not graph.errors(), f'{spec.id} graph is structurally unsound: {graph.errors()}'
        assert course_concepts(spec.id), f'{spec.id} exposes no concepts'
        assert course_questions(spec.id), f'{spec.id} exposes no questions'


def test_subject_kind_decides_the_symbolic_engine():
    """Only mathematics may be routed through the symbolic engine."""
    for spec in courses.COURSES:
        assert spec.uses_symbolic_engine is (spec.subject_kind == courses.MATHEMATICS)


def test_concept_ids_do_not_collide_across_courses():
    """The node index is flat, so a shared id would silently resolve to one course."""
    seen: dict[str, str] = {}
    for spec in courses.COURSES:
        for node_id in courses.graph_for(spec.id).nodes:
            assert node_id not in seen, f'{node_id} appears in both {seen[node_id]} and {spec.id}'
            seen[node_id] = spec.id
    assert len(seen) == courses.total_concepts()


def test_course_for_node_resolves_every_concept():
    for spec in courses.COURSES:
        for node_id in courses.graph_for(spec.id).nodes:
            assert courses.course_for_node(node_id) == spec.id
            assert courses.subject_kind_for(node_id) == spec.subject_kind
    assert courses.course_for_node('not_a_real_concept_slug') == ''


# ------------------------------------------------------------------ figures


def test_non_mathematics_figure_is_a_concept_map_not_a_quadratic():
    """The exact regression: a physics concept must never render a parabola."""
    for spec in NON_MATHEMATICS:
        graph = courses.graph_for(spec.id)
        for node_id, node in graph.nodes.items():
            payload = figures.figure_for(node.to_dict(), graph, {}, spec.subject_kind)
            assert payload['figure'] == 'map', f'{spec.id}/{node_id} rendered {payload["figure"]}'
            assert payload['kind'] == figures.CONCEPT_MAP
            assert payload['engine'] == 'concept-map'
            assert payload['series'] == [], 'a concept map must carry no plot series'
            assert payload['parameters'] == [], 'a concept map has no tunable parameters'
            # The map is derived, not decorative: the neighbours are real edges.
            assert {n['id'] for n in payload['prerequisites']} == set(graph.parents(node_id))
            assert {n['id'] for n in payload['dependants']} == set(graph.children(node_id))


def test_mathematics_figure_is_still_symbolic():
    for spec in MATHEMATICS:
        graph = courses.graph_for(spec.id)
        node = next(iter(graph.nodes.values()))
        payload = figures.figure_for(node.to_dict(), graph, {}, spec.subject_kind)
        assert payload['engine'] == 'symbolic'
        assert payload['figure'] in {'curve', 'scene'}


# ------------------------------------------------------------------ API isolation


@pytest.mark.parametrize('spec', courses.COURSES, ids=[c.id for c in courses.COURSES])
def test_curriculum_is_scoped_to_the_enrolled_course(client, spec):
    headers, _ = account(client, f'user-{spec.id}')
    user = enrol(client, headers, spec.id)
    assert user['course_id'] == spec.id

    payload = client.get('/api/v1/curriculum', headers=headers).json()
    returned = {c['id'] for c in payload['concepts']}
    assert returned == set(course_concepts(spec.id))
    assert payload['course']['id'] == spec.id
    # No other course's concept may appear, in either direction.
    for other in courses.COURSES:
        if other.id == spec.id:
            continue
        assert not (returned & set(course_concepts(other.id)))


@pytest.mark.parametrize('spec', NON_MATHEMATICS, ids=[c.id for c in NON_MATHEMATICS])
def test_lesson_and_question_are_served_for_a_generated_course(client, spec):
    headers, _ = account(client, f'gen-{spec.id}')
    enrol(client, headers, spec.id)
    concept_id = next(iter(course_concepts(spec.id)))

    lesson = client.get(f'/api/v1/lessons/{concept_id}', headers=headers)
    assert lesson.status_code == 200, lesson.text
    body = lesson.json()
    assert body['generated'] is True
    assert body['simulation']['kind'] == figures.CONCEPT_MAP
    assert body['blocks'], 'a generated lesson must still carry teaching blocks'

    question = client.get('/api/v1/questions/next', headers=headers,
                          params={'mode': 'practice', 'concept_id': concept_id})
    assert question.status_code == 200, question.text
    q = question.json()
    assert len({o['text'] for o in q['options']}) == 4
    assert q['kind'] == 'generated_multiple_choice'


def test_generated_items_are_gradeable_through_the_real_attempt_path(client):
    """Generated content must not be second-class: the same receipt path must score it."""
    spec = NON_MATHEMATICS[0]
    headers, _ = account(client, 'grading')
    enrol(client, headers, spec.id)
    concept_id = next(iter(course_concepts(spec.id)))
    q = client.get('/api/v1/questions/next', headers=headers,
                   params={'mode': 'practice', 'concept_id': concept_id}).json()

    internal = QUESTIONS[q['id']]
    assert internal['generated'] is True
    submission = {'question_id': q['id'], 'option_id': internal['answer_id'], 'receipt': q['receipt'],
                  'client_event_id': str(uuid4()), 'elapsed_seconds': 0, 'confidence': 0.8}
    result = client.post('/api/v1/attempts', headers=headers, json=submission)
    assert result.status_code == 200, result.text
    value = result.json()
    assert value['correct'] is True
    assert value['mastery'] > 0
    assert value['review_at']

    # A wrong answer must be diagnostic, not merely marked wrong. A receipt is single-use,
    # so this needs its own issued question.
    q2 = client.get('/api/v1/questions/next', headers=headers,
                    params={'mode': 'practice', 'concept_id': concept_id}).json()
    internal2 = QUESTIONS[q2['id']]
    wrong = next(o['id'] for o in internal2['options'] if o['id'] != internal2['answer_id'])
    submission = {'question_id': q2['id'], 'option_id': wrong, 'receipt': q2['receipt'],
                  'client_event_id': str(uuid4()), 'elapsed_seconds': 0, 'confidence': 0.8}
    result = client.post('/api/v1/attempts', headers=headers, json=submission)
    assert result.status_code == 200, result.text
    diagnosis = result.json()['diagnosis']
    assert diagnosis['category'], 'a wrong generated answer must produce a category'
    assert diagnosis['next_action']


def test_a_concept_from_another_course_is_refused(client):
    """Course isolation has to hold for a client that holds a foreign concept id."""
    physics = next(c for c in courses.COURSES if c.id == 'physics')
    maths = next(c for c in courses.COURSES if c.uses_symbolic_engine)
    foreign = next(iter(course_concepts(maths.id)))

    headers, _ = account(client, 'isolation')
    enrol(client, headers, physics.id)

    assert client.get(f'/api/v1/lessons/{foreign}', headers=headers).status_code == 404
    assert client.get('/api/v1/questions/next', headers=headers,
                      params={'mode': 'practice', 'concept_id': foreign}).status_code == 404
    assert client.get(f'/api/v1/chat', headers=headers,
                      params={'concept_id': foreign}).status_code == 404
    assert client.get(f'/api/v1/knowledge-graph/{foreign}', headers=headers).status_code == 404


def test_projects_materialise_only_for_the_enrolled_course(client):
    """A row per concept across every course would write hundreds of rows nobody asked for."""
    spec = NON_MATHEMATICS[0]
    headers, _ = account(client, 'projects')
    enrol(client, headers, spec.id)
    items = client.get('/api/v1/projects', headers=headers).json()['items']
    assert {i['concept_id'] for i in items} == set(course_concepts(spec.id))
    assert len(items) == len(course_concepts(spec.id))
    for item in items:
        assert item['title'] and item['prompt'] and item['rubric']


def test_recommendation_never_crosses_courses(client):
    """The dashboard pools questions for the next-item recommendation; it must be scoped."""
    physics = next(c for c in courses.COURSES if c.id == 'physics')
    headers, _ = account(client, 'recommend')
    enrol(client, headers, physics.id)
    dashboard = client.get('/api/v1/dashboard', headers=headers).json()
    recommended = dashboard['recommendation']['concept_id']
    assert CONCEPT_COURSE.get(recommended) == physics.id


def test_graph_endpoints_report_the_enrolled_course(client):
    physics = next(c for c in courses.COURSES if c.id == 'physics')
    headers, _ = account(client, 'graph')
    enrol(client, headers, physics.id)

    graph = client.get('/api/v1/knowledge-graph', headers=headers).json()
    assert graph['course']['id'] == physics.id
    assert {n['id'] for n in graph['nodes']} == set(courses.graph_for(physics.id).nodes)
    assert graph['lesson_targets'] == {}, 'a generated course has no authored lesson layer'
    assert all(n['simulation_kind'] == figures.CONCEPT_MAP for n in graph['nodes'])

    units = client.get('/api/v1/knowledge-graph/units', headers=headers).json()
    assert units['course']['id'] == physics.id
    assert units['units'], 'a course graph must expose units'
    assert sum(u['concepts'] for u in units['units']) == len(courses.graph_for(physics.id).nodes)


def test_switching_course_switches_the_whole_view(client):
    """Enrolment is the single switch; nothing may stay behind from the previous course."""
    physics = next(c for c in courses.COURSES if c.id == 'physics')
    maths = next(c for c in courses.COURSES if c.uses_symbolic_engine)
    headers, _ = account(client, 'switch')

    enrol(client, headers, maths.id)
    before = {c['id'] for c in client.get('/api/v1/curriculum', headers=headers).json()['concepts']}
    assert before == set(course_concepts(maths.id))

    enrol(client, headers, physics.id)
    after = {c['id'] for c in client.get('/api/v1/curriculum', headers=headers).json()['concepts']}
    assert after == set(course_concepts(physics.id))
    assert not (after & before)


def test_unknown_course_is_rejected_and_does_not_take_the_server_down(client):
    headers, _ = account(client, 'badcourse')
    assert client.patch('/api/v1/me', headers=headers, json={'course_id': 'not_a_course'}).status_code == 422
    # The learner keeps working on the course they already had.
    assert client.get('/api/v1/curriculum', headers=headers).status_code == 200


def test_course_catalogue_lists_every_course_with_its_size(client):
    headers, _ = account(client, 'catalogue')
    payload = client.get('/api/v1/courses', headers=headers).json()
    listed = {c['id'] for c in payload['courses']}
    assert listed == {c.id for c in courses.COURSES}
    assert payload['enrolled'] == courses.DEFAULT_COURSE_ID
    assert payload['total_concepts'] == courses.total_concepts()
    for entry in payload['courses']:
        assert entry['stats']['concepts'] == len(courses.graph_for(entry['id']).nodes)
    # Exactly one course is marked as the enrolled one.
    assert sum(1 for c in payload['courses'] if c.get('enrolled')) == 1


# ------------------------------------------------------------------ the harness layer


@pytest.mark.parametrize('spec', courses.COURSES, ids=[c.id for c in courses.COURSES])
def test_tutor_answers_for_every_course(client, spec):
    """The tutor must retrieve against the learner's own course graph.

    Regression: the chat endpoint called retrieval with no tool context, so `graph_for` fell back
    to the mathematics course. A physics learner's question resolved to no node and the tutor
    returned an empty string - a silent failure, because an empty answer is not an error and
    nothing downstream objected. The native client showed a blank assistant turn.
    """
    headers, _ = account(client, f'tutor-{spec.id}')
    enrol(client, headers, spec.id)
    concept_id = next(iter(course_concepts(spec.id)))

    reply = client.post('/api/v1/chat', headers=headers,
                        json={'concept_id': concept_id, 'session_id': 'probe',
                              'message': 'Explain this concept step by step and give a small worked example.'})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body['role'] == 'assistant'
    assert len(body['content']) > 200, f'{spec.id}: tutor replied {body["content"]!r}'
    assert body['grounding'], f'{spec.id}: tutor returned no grounding'


@pytest.mark.parametrize('spec', courses.COURSES, ids=[c.id for c in courses.COURSES])
def test_harness_plan_and_generate_work_for_every_course(client, spec):
    """The harness surface must answer for any subject, not only mathematics."""
    headers, _ = account(client, f'harness-{spec.id}')
    enrol(client, headers, spec.id)
    concept_id = next(iter(course_concepts(spec.id)))

    plan = client.get('/api/v1/harness/plan', headers=headers, params={'concept_id': concept_id})
    assert plan.status_code == 200, plan.text
    decision = plan.json()['decision']
    moves = {m['move'] for m in client.get('/api/v1/harness/tools', headers=headers).json()['moves']}
    assert decision['move'] in moves
    assert decision['reason']
    # The harness works in graph node ids, so an authored lesson id resolves to the node
    # it teaches. Both namespaces must name the same idea.
    assert decision['concept_id'] == LESSON_TARGETS.get(concept_id, concept_id)

    figure = client.get(f'/api/v1/simulations/{concept_id}', headers=headers)
    assert figure.status_code == 200, figure.text
    payload = figure.json()
    expected_engine = 'symbolic' if spec.uses_symbolic_engine else 'concept-map'
    assert payload['engine'] == expected_engine

    for kind in ('explanation', 'flashcards', 'quiz', 'slide_deck', 'image_brief'):
        response = client.post('/api/v1/harness/generate', headers=headers,
                               json={'concept_id': concept_id, 'kind': kind})
        assert response.status_code == 200, f'{spec.id}/{kind}: {response.text}'
        assert response.json()['kind'] == kind


def test_harness_memory_is_scoped_to_the_learner(client):
    headers, _ = account(client, 'memory')
    assert client.get('/api/v1/harness/memory', headers=headers).json()['notes'] == []
    other, _ = account(client, 'memory-other')
    assert client.get('/api/v1/harness/memory', headers=other).json()['notes'] == []


def test_every_course_has_four_questions_per_concept():
    """The item count is a contract: validate_curriculum requires at least four variants."""
    for spec in courses.COURSES:
        concepts = course_concepts(spec.id)
        questions = course_questions(spec.id)
        assert len(questions) == len(concepts) * 4, f'{spec.id} item count is wrong'
        for q in questions.values():
            assert len({o['text'] for o in q['options']}) == 4
            assert q['answer_id'] in {o['id'] for o in q['options']}
            assert q['concept_id'] in concepts
            assert q['explanation']


#: The four things a generated item may ask about a concept. A category outside this
#: set is a question about the course - a unit, an order, an edge - not about the idea.
CONCEPTUAL_CATEGORIES = {'definition_recall', 'term_association',
                         'concept_identification', 'term_set_identification'}


def test_generated_items_ask_about_concepts_not_the_course():
    """A diagnostic must measure understanding, not outline navigation.

    The first generated layer asked which unit a concept sat in, which idea had to
    come first and which came later. Every one of those is answerable from the course
    tree by a learner who has never read the material, so the diagnostic that was
    supposed to place a learner measured whether they had browsed the outline. Every
    generated item now asks about the concept itself, which is pinned here from the
    answer side: the correct option is always a fact the course states about the
    concept - its own summary, its own title, or one of its own terms.
    """
    for spec in courses.COURSES:
        if spec.authored:
            continue
        graph = courses.graph_for(spec.id)
        prompts_per_concept = {}
        for qid, question in course_questions(spec.id).items():
            node = graph.nodes[question['concept_id']]
            assert question['category'] in CONCEPTUAL_CATEGORIES, (
                f'{qid} asks a {question["category"]!r} question, which is about the '
                f'course rather than about {node.title}')
            stated = {node.summary, node.title, *node.keywords}
            assert question['answer_text'].strip(), f'{qid} has an empty correct option'
            assert question['answer_text'] in stated, (
                f'{qid} is answered by something the course never states about '
                f'{node.title}')
            prompts_per_concept.setdefault(question['concept_id'], set()).add(question['prompt'])
        # Four variants means four different questions. A concept whose items all
        # collapsed onto one prompt would be answerable once and unanswerable after.
        for concept_id, prompts in prompts_per_concept.items():
            assert len(prompts) == 4, (
                f'{spec.id}/{concept_id} has {len(prompts)} distinct prompts, not 4')


def test_authored_mathematics_content_is_unchanged_by_the_generated_layer():
    """The generated layer must extend the registries, never overwrite better material."""
    maths = next(c for c in courses.COURSES if c.uses_symbolic_engine)
    concepts = course_concepts(maths.id)
    assert all(not c.get('generated') for c in concepts.values())
    assert all(len(c['blocks']) == 8 for c in concepts.values())
    # The shared registry holds three populations: authored, generated, and the
    # learner-built courses this process has resident (``publish`` indexes those there
    # so ``course_concepts`` and the tutor can resolve a course that lives only in the
    # database). The invariant is therefore that the registry is *exactly* those three
    # and nothing else - which is what makes it a real check rather than a count that
    # silently rots the first time a test creates a course. Counting only the authored
    # list here failed the moment ``tests/test_course_builder.py`` started passing.
    runtime = course_builder.runtime_courses()
    authored = sum(len(course_concepts(s.id)) for s in courses.COURSES)
    built = sum(len(course_concepts(cid)) for cid in runtime)
    assert len(CONCEPTS) == authored + built, (
        f'{len(CONCEPTS)} concepts in the registry, but {authored} authored and '
        f'{built} in {len(runtime)} learner-built course(s)')
    assert len(QUESTIONS) == sum(len(course_questions(s.id)) for s in courses.COURSES) + \
        sum(len(course_questions(cid)) for cid in runtime)


def test_every_course_offers_a_citable_reference():
    """Each course must point a learner somewhere real to read or watch more.

    The five generated courses shipped with an empty media list, which meant two things at
    once: a science learner had nowhere to go beyond the app, and the tutor's grounding
    contained no curriculum reference at all. The tutor is instructed to cite only supplied
    references, so for those courses it had nothing to cite and answered without one.

    This is a link check, not a content check. Nothing here is fetched, and the assertion
    that no reference is ingestible is the point of the whole licence gate.
    """
    for spec in courses.COURSES:
        for concept_id, concept in course_concepts(spec.id).items():
            media = concept.get('media') or []
            assert media, f'{spec.id}/{concept_id} has no external reference'
            for entry in media:
                assert entry['status'] == 'reference_link'
                assert entry['url'].startswith('https://')
                assert entry['licence'] and entry['licence_class']
                # A reference that became ingestible would mean the app had started treating
                # somebody else's book as its own material.
                assert not policy.SourcePolicy(
                    name=entry['title'], url=entry['url'], licence=entry['licence'],
                    licence_class=policy.LicenceClass(entry['licence_class']), scope=entry['scope']
                ).ingestible


def test_reference_links_are_subject_appropriate():
    """A chemistry learner must not be handed the astronomy book.

    The media list now carries three kinds of card: the course's reading references, its video
    hubs and its simulation providers. The assertion is therefore split by kind. The reading
    cards must still be exactly the course's own references in order - that is the property
    the test was written for - and the added cards are checked for the property that matters
    about them, which is that each one carries its licence and its integration mode rather
    than arriving as a bare URL.
    """
    for spec in courses.COURSES:
        if spec.uses_symbolic_engine:
            continue
        expected = policy.COURSE_REFERENCES[spec.id]
        media = course_concepts(spec.id)[next(iter(course_concepts(spec.id)))]['media']
        readings = [card for card in media if card.get('kind') == 'reading']
        assert [card['url'] for card in readings] == [p.url for p in expected], \
            f'{spec.id} reference set drifted'
        for kind in ('video', 'simulation'):
            cards = [card for card in media if card.get('kind') == kind]
            if kind == 'simulation' and spec.id in policy.COURSES_WITHOUT_SIMULATIONS:
                # The absence is a declared position, not an oversight: a provider card here
                # would be a resource that does not exist for the subject. Pin it so that
                # neither the gap nor a fabricated fix can appear unnoticed.
                assert not cards, f'{spec.id} declares no simulation provider but ships one'
                continue
            assert cards, f'{spec.id} has no {kind} card'
            for card in cards:
                assert card.get('licence'), f'{spec.id} {kind} card has no licence'
                assert card.get('licence_class'), f'{spec.id} {kind} card has no licence class'
                assert card.get('integration_mode'), f'{spec.id} {kind} card has no mode'
                assert card.get('policy_name'), f'{spec.id} {kind} card is not traceable to a policy'


@pytest.mark.parametrize('spec', NON_MATHEMATICS, ids=[c.id for c in NON_MATHEMATICS])
def test_tutor_cites_a_real_reference_for_every_course(client, spec):
    """The tutor's grounding must contain a resolvable curriculum reference, not just prose."""
    headers, _ = account(client, f'ref-{spec.id}')
    enrol(client, headers, spec.id)
    concept_id = next(iter(course_concepts(spec.id)))
    reply = client.post('/api/v1/chat', headers=headers,
                        json={'concept_id': concept_id, 'session_id': 'ref',
                              'message': 'Which curriculum reference supports this concept?'})
    assert reply.status_code == 200, reply.text
    references = [item for item in reply.json()['grounding'] if item.get('url')]
    assert references, f'{spec.id}: tutor grounding carried no reference URL'
    assert any(item['url'].startswith('https://') for item in references)
