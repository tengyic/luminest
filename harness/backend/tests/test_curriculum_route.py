"""Tests for the single curriculum-routing layer.

``app.curriculum_route`` exists because three families of course had grown up
answering the same questions in different ways: an authored concept carried no
owning course, a generated one did, and the API's key whitelist silently dropped the
field for both. These tests pin what the layer promises now, and each of them was a
real bug before it existed:

1. **every concept, in every course, names the course it belongs to** - including the
   hand-authored mathematics course, which for years did not;
2. **every course's references come from the licence gate**, so a learner is shown a
   rights position rather than a bare URL, in the course's own subject's language;
3. **a course that owns nothing returns nothing**, rather than returning another
   course's concepts with its own id stamped on them - the failure mode a shared
   payload function invites;
4. **the learner's own course routes through the same layer as the shipped ones**, so
   building a course is not a second code path.
"""

from __future__ import annotations

from typing import Mapping

import pytest
from fastapi.testclient import TestClient

from app import course_builder as cb
from app import courses, curriculum
from app import curriculum_route
from app.config import Settings
from app.main import create_app
from test_api import account, client, settings  # noqa: F401 - fixtures re-exported


@pytest.fixture(autouse=True)
def _restore_shared_registries():
    """Undo the global registries a created course is published into.

    One test here builds a course through the API to prove it routes like any other,
    and publishing a course writes into the *same* module-level registries the shipped
    courses live in. The database is per-test; those registries are per-process, so
    without this the concepts of a course built here would still be counted by a later
    test that asserts the registries and the catalogue agree.
    """
    saved = (dict(curriculum.CONCEPTS), dict(curriculum.QUESTIONS),
             dict(curriculum.CONCEPT_COURSE), dict(courses.COURSE_BY_ID),
             dict(cb._RUNTIME_COURSES), dict(cb._RUNTIME_GRAPHS), cb._STORE_FACTORY)
    try:
        yield
    finally:
        curriculum.CONCEPTS.clear(), curriculum.CONCEPTS.update(saved[0])
        curriculum.QUESTIONS.clear(), curriculum.QUESTIONS.update(saved[1])
        curriculum.CONCEPT_COURSE.clear(), curriculum.CONCEPT_COURSE.update(saved[2])
        courses.COURSE_BY_ID.clear(), courses.COURSE_BY_ID.update(saved[3])
        cb._RUNTIME_COURSES.clear(), cb._RUNTIME_COURSES.update(saved[4])
        cb._RUNTIME_GRAPHS.clear(), cb._RUNTIME_GRAPHS.update(saved[5])
        cb._STORE_FACTORY = saved[6]


COURSE_IDS = sorted(spec.id for spec in courses.COURSES)

#: The exploration kinds the native renderer switches on, read from
#: ``native/Sources/LearningHarness/SimulationDetail.swift`` (``kinds``) and
#: ``Studio.swift`` (``kinds``). Pinned here on purpose: the backend's job is to
#: report a kind the client can draw, and a kind outside this set renders as a blank
#: panel rather than as an error, which is the kind of failure nobody reports.
RENDERABLE_KINDS = frozenset({
    'fraction', 'number_line', 'ratio', 'expression', 'balance', 'slope', 'linear',
    'systems', 'equations', 'polynomial', 'quadratic', 'probability', 'statistics',
    'sampling', 'concept_map',
})


def test_the_layer_resolves_a_real_course_for_every_course_the_harness_ships():
    """Every shipped course routes, and routes to non-empty content."""
    assert len(COURSE_IDS) >= 6, 'this test is about the courses that ship, not a fixture'
    for course_id in COURSE_IDS:
        route = curriculum_route.route(course_id)
        assert route.course.id == course_id
        assert route.concepts, f'{course_id} routed to no concepts at all'
        assert route.sources, f'{course_id} offered no curriculum references'


def test_every_concept_in_every_course_names_the_course_it_belongs_to():
    """The field this layer exists for, checked across every course.

    The authored mathematics course is the case that used to be missing: its
    registry entries predate the generated ones and carry no ``course_id``, so a
    client holding a concept id could not tell whose it was.
    """
    for course_id in COURSE_IDS:
        route = curriculum_route.route(course_id)
        for payload in route.payloads():
            assert payload['course_id'] == course_id
            assert route.owns(payload['id']), (f'{payload["id"]} is in {course_id}\'s '
                                               f'routing but is not owned by it')
        # A concept belonging to a *different* course is not owned here. This is the
        # invariant that stops one course's lesson being served under another's name.
        for other_id in COURSE_IDS:
            if other_id == course_id:
                continue
            for concept_id in curriculum_route.route(other_id).concepts:
                assert not route.owns(concept_id), (
                    f'{course_id} claims {other_id!r} concept {concept_id!r}')


def test_only_mathematics_routes_through_the_symbolic_engine():
    """``symbolic`` is the flag that keeps a physics concept out of the maths engine.

    ``mathkit`` answers a template for any concept handed to it and returns a generic
    quadratic for the ones it has no template for, so a wrong ``True`` here presents a
    curve as though it were about the subject the learner is studying.
    """
    for course_id in COURSE_IDS:
        route = curriculum_route.route(course_id)
        assert route.symbolic is (route.course.subject_kind == 'mathematics'), course_id
        payloads = route.payloads()
        kinds = {payload['simulation_kind'] for payload in payloads}
        # No concept in any course reports an empty kind. This is the regression the
        # layer's declared-first resolution fixed: every concept in ``algebra_2`` and
        # ``ap_calculus`` used to report '' because the maths template map predated
        # those courses and nothing looked at the concept's own declaration.
        assert '' not in kinds, f'{course_id} reported a concept with no simulation kind'
        # The kind is what the concept itself declares, or the map's answer for one
        # that declares nothing - never something the routing layer made up.
        for payload in payloads:
            entry = route.concepts[payload['id']]
            declared = entry.get('simulation')
            declared_kind = (str(declared.get('kind') or '')
                             if isinstance(declared, Mapping) else '')
            assert payload['simulation_kind'] == (declared_kind or (
                SIMULATION_KINDS.get(payload['graph_id'], '')
                if route.symbolic else 'concept_map'))
        if route.symbolic:
            # A mathematics concept's kind must be one the native renderer can
            # actually draw. This is the assertion that catches the vocabulary
            # mismatch: ``SIMULATION_KINDS`` is keyed by graph node id and carries the
            # maths *template* kinds (``fraction_bar``, ``circle``), while the client
            # switches on the kinds the concepts themselves declare (``fraction``,
            # ``number_line``). Reporting the former would have shown a blank panel.
            assert kinds <= RENDERABLE_KINDS, (f'{course_id} reported a kind the native '
                                               f'renderer does not switch on: '
                                               f'{sorted(kinds - RENDERABLE_KINDS)}')
        else:
            assert kinds == {'concept_map'}, course_id

    # The maths path is proven on the course that declares per-concept explorations:
    # a course whose concepts all say "concept map" would still be routed correctly,
    # and ``algebra_2`` and ``ap_calculus`` do declare exactly that today. That is
    # their data's choice, not the layer's, and it is visible in the payload rather
    # than being hidden - so the maths path is checked where it is exercised.
    maths_kinds = {payload['simulation_kind']
                   for payload in curriculum_route.route('integrated_math_1').payloads()}
    assert maths_kinds, 'the authored maths course must resolve its maths explorations'
    assert maths_kinds <= RENDERABLE_KINDS
    assert maths_kinds - {'concept_map'}, 'the maths course must offer real explorations'


def test_every_reference_card_carries_a_rights_position_and_both_spellings():
    for course_id in COURSE_IDS:
        for card in curriculum_route.route(course_id).sources:
            assert card['licence_class'], f'{course_id} offered a reference with no licence class'
            assert card['licence'] or card['license']
            # The native client reads ``license``; the gate speaks ``licence_class``.
            # Both travel so the rights vocabulary lives in exactly one module.
            assert card['license'] == card['licence']
            assert card['status'], 'a card must state its status, not leave it to be inferred'
            if card['url']:
                assert card['url'].startswith('https://')


def test_a_course_the_learner_built_routes_through_the_same_layer(client):
    headers, _ = account(client)
    source = ('# Photosynthesis\n\nPhotosynthesis is the process by which green plants '
              'convert light energy into chemical energy stored in glucose.\n\n'
              'Chlorophyll is the green pigment inside chloroplasts that absorbs light '
              'energy for photosynthesis.\n\nThe light-dependent reactions are the first '
              'stage of photosynthesis, where light energy splits water molecules and '
              'releases oxygen.\n\nThe Calvin cycle is the second stage of photosynthesis, '
              'where carbon dioxide is fixed into glucose using the energy from the '
              'light-dependent reactions.\n\nCellular respiration is the process that '
              'releases energy from glucose inside every living cell.\n')
    response = client.post('/api/v1/create/auto', headers=headers,
                           json={'text': source, 'title': 'My photosynthesis notes',
                                 'subject': 'Biology', 'enrol': True})
    assert response.status_code == 201, response.text
    course_id = response.json()['course_id']

    # Built courses own their own concepts and nothing else's.
    route = curriculum_route.route(course_id)
    payloads = route.payloads()
    assert payloads, 'a built course must route to the concepts extracted from its source'
    assert all(payload['course_id'] == course_id for payload in payloads)
    assert not route.owns(courses.DEFAULT_COURSE_ID + '_anything')

    # ...and every other course still refuses to claim them.
    foreign = curriculum_route.route(courses.DEFAULT_COURSE_ID)
    assert not any(foreign.owns(payload['id']) for payload in payloads)


def test_an_unknown_course_raises_at_the_edge_rather_than_looking_empty():
    with pytest.raises(courses.UnknownCourse):
        curriculum_route.route('no-such-course')


def test_route_for_user_falls_back_when_the_account_names_a_course_that_is_gone():
    class Stale:
        course_id = 'a-course-that-was-deleted'

    class Missing:
        course_id = None

    route = curriculum_route.route_for_user(Stale())
    assert route.course.id == courses.DEFAULT_COURSE_ID
    assert curriculum_route.route_for_user(Missing()).course.id == courses.DEFAULT_COURSE_ID


# ------------------------------------------------------------------ the surfaces

def test_the_curriculum_surface_stamps_every_concept_and_offers_the_sources(client):
    headers, registered = account(client)
    response = client.get('/api/v1/curriculum', headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['course']['id'] == courses.DEFAULT_COURSE_ID
    assert payload['sources'], 'the maths course must offer its routed references'
    assert payload['authored_share']['concepts'] > 0
    concepts = payload['concepts']
    assert concepts
    for concept in concepts:
        assert concept['course_id'] == courses.DEFAULT_COURSE_ID
        assert set(concept) >= {'id', 'title', 'unit', 'prerequisites', 'summary', 'strand',
                                'topic', 'tier', 'difficulty', 'graph_id', 'course_id',
                                'generated', 'has_lesson', 'simulation_kind'}


def test_a_lesson_surface_stamps_the_course_that_owns_the_concept(client):
    headers, _ = account(client)
    concept = next(iter(curriculum_route.route(courses.DEFAULT_COURSE_ID).concepts))
    response = client.get(f'/api/v1/lessons/{concept}', headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['course_id'] == courses.DEFAULT_COURSE_ID
