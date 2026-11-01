"""Tests for finding a source and turning it into a personalised course.

The source extension makes three promises that are each easy to break silently:

1. **The licence gate decides.** A candidate is offered with the licence class it
   really has, and building a course from one that is not cleared for ingestion is
   refused with a reason that names the class. A learner is never shown a link-only
   reference as though it were a source that can be made into a course.

2. **Nothing is invented.** Every URL comes from a provider call or from the audited
   registry, and a provider that fails degrades to fewer candidates plus a note
   rather than to a fabricated result. The network seams are replaced here, so the
   whole feature is exercised with no network and no API key.

3. **Personalised means derived.** The level, the session length and the estimate of
   how long the course will take are arithmetic on the learner's own recorded goal
   and pace - not a guess dressed up as a prediction.

The HTTP layer is exercised for real: a course built through ``/api/v1/create/auto``
is stored, is made active, and is then visible through the endpoints every other
course is visible through.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import course_builder as cb
from app import courses, curriculum
from app import source_extension as se
from app.config import Settings
from app.ingest import policy as ingest_policy
from app.main import create_app
from test_api import account, client, settings  # noqa: F401 - fixtures re-exported


@pytest.fixture(autouse=True)
def _restore_shared_registries():
    """Undo the global registries a created course is published into.

    ``course_builder.save_course`` makes a course studyable by writing it into the
    same module-level registries the shipped courses live in. The database is
    per-test; those registries are per-process, so a course created here would
    otherwise leak into every later test that counts courses or concepts.
    """
    saved = (dict(curriculum.CONCEPTS), dict(curriculum.QUESTIONS),
             dict(curriculum.CONCEPT_COURSE), dict(courses.COURSE_BY_ID),
             dict(cb._RUNTIME_COURSES), dict(cb._RUNTIME_GRAPHS), cb._STORE_FACTORY,
             dict(se._RECENT))
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
        se._RECENT.clear(), se._RECENT.update(saved[7])


# A Wikipedia-shaped article: ``explaintext`` dialect with ``== Heading ==``, long
# enough to clear every size floor, written as definitions so it yields concepts.
ARTICLE = """== Overview ==
Photosynthesis is the process by which green plants convert light energy into chemical energy stored in glucose.

== Light-dependent reactions ==
The light-dependent reactions are the first stage of photosynthesis, where light energy splits water molecules and releases oxygen.

Chlorophyll is the green pigment inside chloroplasts that absorbs light energy for photosynthesis.

== The Calvin cycle ==
The Calvin cycle is the second stage of photosynthesis, where carbon dioxide is fixed into glucose using the energy from the light-dependent reactions.

== Cellular respiration ==
Cellular respiration is the process that releases energy from glucose inside every living cell.

Mitochondria are the organelles where cellular respiration takes place and most ATP is produced.

ATP is the molecule that carries usable energy between reactions inside a cell.
"""


def wiki_pages(title='Photosynthesis', key='Photosynthesis'):
    return [{'title': title, 'key': key, 'description': 'a plant process',
             'excerpt': 'Photosynthesis is <span class="searchmatch">light</span> to sugar',
             'url': f'https://en.wikipedia.org/wiki/{key}'}]


def stub_wikipedia(monkeypatch, pages=None, article=None):
    """Replace both network seams at once, so no test touches the network."""
    monkeypatch.setattr(se, 'WIKIPEDIA_SEARCH',
                        lambda query, limit: list(pages if pages is not None else wiki_pages()))
    monkeypatch.setattr(se, 'WIKIPEDIA_ARTICLE',
                        lambda title: ARTICLE if article is None else article)


# --------------------------------------------------------------------- the gate

def test_a_search_returns_licence_cleared_candidates_with_what_may_be_done(monkeypatch):
    stub_wikipedia(monkeypatch)
    result = se.search('photosynthesis')
    wikipedia = [c for c in result.candidates if c.provider == 'wikipedia']
    assert wikipedia, 'a stubbed Wikipedia result must be offered'
    for candidate in wikipedia:
        # The real policy entry, not a string restated here: if the gate's position on
        # Wikipedia changes, this test moves with it rather than pinning a stale copy.
        entry = ingest_policy.apply_overrides(ingest_policy.WIKIPEDIA_REST)
        assert candidate.licence_class == entry.licence_class.value
        assert candidate.licence == entry.licence
        assert candidate.attribution == entry.attribution
        assert candidate.ingestible == entry.ingestible
        assert candidate.can_build_course == entry.ingestible
        assert candidate.url.startswith('https://en.wikipedia.org/')


def test_a_link_only_reference_is_offered_and_never_buildable(monkeypatch):
    """The audited references are offered, and are honestly offered as read-only.

    OpenStax's current books and Khan Academy are the reason this matters: a learner
    who searches for one of them must be told the harness may link to it and read
    nothing from it, before they try to build a course out of it.
    """
    stub_wikipedia(monkeypatch, pages=[])
    result = se.search('physics')
    link_only = [c for c in result.candidates if c.licence_class == 'link_only']
    assert link_only, 'the audited physics references must answer a search for physics'
    for candidate in link_only:
        assert candidate.can_build_course is False
        assert candidate.ingestible is False
        assert candidate.url.startswith('https://')
        if candidate.provider == 'wikipedia':
            continue
        with pytest.raises(se.SourceRefused) as excinfo:
            se.build_course(None, candidate_id=candidate.id)
        assert excinfo.value.code == 'source_not_buildable'
        assert excinfo.value.licence_class == 'link_only'
        assert candidate.title in str(excinfo.value)


def test_building_from_a_candidate_that_is_not_wikipedia_is_refused():
    """Only a source with cleared text can be read; the rest are references."""
    candidate = se._remember(se.Candidate(
        id='handmade', title='Hand-made', url='https://example.test', provider='registry',
        summary='', licence='CC BY 4.0', licence_class='cc_by', ingestible=True,
        can_build_course=True, attribution='Someone', why='for the test'))
    with pytest.raises(se.SourceRefused) as excinfo:
        se.intake_for(candidate)
    assert excinfo.value.code == 'source_not_buildable'


def test_a_provider_failure_degrades_to_a_note_and_not_a_fabrication(monkeypatch):
    def explode(query, limit):
        raise OSError('network unreachable')

    monkeypatch.setattr(se, 'WIKIPEDIA_SEARCH', explode)
    result = se.search('thermodynamics')
    assert not [c for c in result.candidates if c.provider == 'wikipedia']
    assert result.providers['wikipedia'] is False
    assert any('could not be reached' in note for note in result.notes)
    # No fabricated URL survived the failure.
    for candidate in result.candidates:
        assert candidate.url == '' or candidate.url.startswith('https://en.wikipedia.org/') is False


def test_search_holds_slots_for_the_learners_own_material(monkeypatch):
    """A popular phrase must not crowd out what the learner already has."""
    stub_wikipedia(monkeypatch, pages=[dict(key=f'Page {index}', title=f'Page {index}',
                                            description='', excerpt='',
                                            url='https://en.wikipedia.org/wiki/x')
                                       for index in range(8)])
    result = se.search('physics')
    providers = {c.provider for c in result.candidates}
    assert 'wikipedia' in providers
    assert providers & {'curriculum', 'registry'}, (
        'the offline providers must survive a full page of network results')


def test_a_query_with_no_buildable_source_is_refused_with_what_was_offered(monkeypatch):
    monkeypatch.setattr(se, 'WIKIPEDIA_SEARCH', lambda query, limit: [])
    with pytest.raises(se.SourceRefused) as excinfo:
        se.build_course(None, query='openstax college physics')
    assert excinfo.value.code == 'no_buildable_source'


def test_supplying_nothing_is_refused_with_the_ways_to_supply_one():
    with pytest.raises(se.SourceRefused) as excinfo:
        se.build_course(None)
    assert excinfo.value.code == 'missing_source'
    assert 'paste' in str(excinfo.value).lower()


def test_an_expired_candidate_is_a_refusal_rather_than_a_crash():
    with pytest.raises(se.SourceRefused) as excinfo:
        se.build_course(None, candidate_id='not-a-remembered-id')
    assert excinfo.value.code == 'candidate_expired'


# ------------------------------------------------------------------ provenance

def test_a_course_built_from_wikipedia_is_stamped_with_its_real_rights(monkeypatch):
    stub_wikipedia(monkeypatch)
    built = se.build_course(None, candidate_id=se.search('photosynthesis').candidates[0].id)
    plan = built.plan
    assert len(plan.concepts) >= cb.MIN_CONCEPTS
    entry = ingest_policy.apply_overrides(ingest_policy.WIKIPEDIA_REST)
    assert plan.source is not cb.LEARNER_SOURCE
    assert plan.source.licence_class is entry.licence_class
    assert plan.source.name == entry.name
    # The same stamp is on every node, so a learner reading the map sees where the
    # course came from without having to open a lesson.
    for node in plan.graph.nodes.values():
        assert node.provenance['licence_class'] == entry.licence_class.value
        assert node.provenance['source'] == entry.name
        assert node.provenance['attribution'] == entry.attribution
    preview = plan.to_preview()['source_rights']
    assert preview['licence_class'] == 'cc_by_sa'
    assert preview['needs_attribution'] is True


def test_a_course_from_pasted_text_is_stamped_the_learners_own():
    plan = cb.plan_course(cb.intake_text(ARTICLE.replace('== ', '# ').replace(' ==', '')))
    assert plan.source is cb.LEARNER_SOURCE
    built = se.build_course(None, text=ARTICLE.replace('== ', '# ').replace(' ==', ''))
    assert built.plan.source.licence_class.value == 'cc_by'
    assert built.candidate is None


def test_wiki_headings_are_reconciled_with_the_extractors_dialect():
    assert se.normalise_wiki_text('== Overview ==\ntext') == '## Overview\ntext'
    assert se.normalise_wiki_text('=== Deep ===\ntext') == '### Deep\ntext'
    assert se.normalise_wiki_text('== Spaced ==') == '## Spaced'
    # A heading already in the extractor's dialect is untouched, and body text that
    # merely *contains* an equals sign is not mistaken for a heading.
    assert se.normalise_wiki_text('## Already') == '## Already'
    assert se.normalise_wiki_text('a == b') == 'a == b'


def test_an_unreadable_article_is_a_refusal_not_a_crash(monkeypatch):
    stub_wikipedia(monkeypatch)
    candidate = se.search('photosynthesis').candidates[0]
    monkeypatch.setattr(se, 'WIKIPEDIA_ARTICLE', lambda title: '')
    with pytest.raises(se.SourceRefused) as excinfo:
        se.intake_for(candidate)
    assert excinfo.value.code == 'empty_source'


# -------------------------------------------------------------- personalising

class Learner:
    goal = ''
    daily_minutes = 20


def test_the_level_comes_from_the_learners_own_goal():
    assert se.level_for('I need to pass the AP physics exam')[0] == 'exam_preparation'
    assert se.level_for('I want to understand why this works')[0] == 'conceptual'
    assert se.level_for('help me revise what I forgot')[0] == 'revision'
    assert se.level_for('quick crash course before Friday')[0] == 'accelerated'
    assert se.level_for('I want to build a portfolio project')[0] == 'project_led'
    level, reason = se.level_for('photosynthesis')
    assert level == 'custom'
    assert 'does not name' in reason


def test_the_estimate_uses_the_planners_own_arithmetic(monkeypatch):
    stub_wikipedia(monkeypatch)
    built = se.build_course(Learner(), candidate_id=se.search('photosynthesis').candidates[0].id)
    Learner.goal, Learner.daily_minutes = 'pass the AP exam', 30
    personalisation = se.personalise(Learner(), built.plan)
    by_hand = len(built.plan.concepts) * se.planner.ITEMS_PER_CONCEPT
    assert personalisation.concepts == len(built.plan.concepts)
    assert personalisation.practice_items == by_hand
    assert personalisation.sessions_to_finish == max(
        1, -(-int(by_hand * se.planner.SECONDS_PER_ITEM
                   * se.planner.FEEDBACK_OVERHEAD / 60) // 30))
    assert personalisation.weeks_to_finish == max(
        1, -(-personalisation.sessions_to_finish // se.planner.SESSIONS_PER_WEEK))
    assert personalisation.level == 'exam_preparation'
    assert personalisation.daily_minutes == 30
    # The first session is a real, ordered prefix of the plan's own read order, and
    # never longer than one session's worth of concepts.
    assert 0 < len(personalisation.first_session) <= se.planner.MAX_TODAY
    assert all(title in [entry['title'] for entry in built.plan.concepts.values()]
               for title in personalisation.first_session)
    # The level the goal implies is on the plan the learner reads, not only in the
    # personalisation: the two read the same function, so they cannot disagree.
    assert built.plan.level == 'custom'
    assert se.level_for('pass the AP exam')[0] == personalisation.level
    Learner.goal, Learner.daily_minutes = '', 20


def test_the_level_the_goal_implies_is_on_the_plan_too(monkeypatch):
    stub_wikipedia(monkeypatch)
    Learner.goal, Learner.daily_minutes = 'pass the AP exam', 20
    built = se.build_course(Learner(), candidate_id=se.search('photosynthesis').candidates[0].id)
    assert built.plan.level == 'exam_preparation'
    assert built.personalisation.level == built.plan.level
    Learner.goal, Learner.daily_minutes = '', 20


def test_a_goal_that_names_concepts_matches_them(monkeypatch):
    stub_wikipedia(monkeypatch)
    built = se.build_course(Learner(), candidate_id=se.search('photosynthesis').candidates[0].id)
    Learner.goal, Learner.daily_minutes = 'I want to understand the calvin cycle', 20
    personalisation = se.personalise(Learner(), built.plan)
    assert 'The Calvin cycle' in personalisation.goal_matches
    Learner.goal, Learner.daily_minutes = '', 20


# ------------------------------------------------------------------- the routes

def test_search_route_returns_candidates_with_their_rights(client, monkeypatch):
    stub_wikipedia(monkeypatch)
    headers, _ = account(client)
    response = client.post('/api/v1/create/search', headers=headers,
                           json={'query': 'photosynthesis'})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['count'] >= 1
    assert payload['providers']['wikipedia'] is True
    candidate = payload['results'][0]
    assert set(candidate) >= {'id', 'title', 'url', 'provider', 'licence',
                              'licence_class', 'ingestible', 'can_build_course',
                              'attribution', 'why'}


def test_auto_route_builds_personalises_enrols_and_teaches(client, monkeypatch):
    headers, _ = account(client)
    body = {
        'text': ARTICLE.replace('== ', '# ').replace(' ==', ''),
        'title': 'Photosynthesis from a Wikipedia article',
        'subject': 'Biology',
    }
    # The user's goal and pace are what personalise the course, so they are set on the
    # account before the build, exactly as a learner would have set them at signup.
    profile = client.patch('/api/v1/me', headers=headers,
                            json={'goal': 'pass the biology exam', 'daily_minutes': 25})
    assert profile.status_code == 200, profile.text

    response = client.post('/api/v1/create/auto', headers=headers, json=body)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload['enrolled'] is True and payload['created'] is True
    assert payload['concepts'] >= cb.MIN_CONCEPTS
    assert payload['level'] == 'exam_preparation'   # the learner's own goal, on the plan
    assert payload['personalisation']['level'] == 'exam_preparation'
    assert payload['personalisation']['daily_minutes'] == 25
    assert payload['personalisation']['sessions_to_finish'] >= 1
    assert payload['source_rights']['licence_class'] == 'cc_by'  # the learner's own text
    course_id = payload['course_id']

    # ...and it is now a real course, through the endpoints every course uses.
    curriculum = client.get('/api/v1/curriculum', headers=headers)
    assert curriculum.status_code == 200, curriculum.text
    assert curriculum.json()['course']['id'] == course_id
    concepts = client.get('/api/v1/curriculum', headers=headers).json()['concepts']
    assert concepts, 'an enrolled course must expose its concepts on the shared surface'
    assert all(concept['course_id'] == course_id for concept in concepts)
    lesson = client.get(f"/api/v1/lessons/{concepts[0]['id']}", headers=headers)
    assert lesson.status_code == 200, lesson.text
    assert lesson.json()['course_id'] == course_id


def test_auto_route_can_build_a_plan_without_saving_it(client, monkeypatch):
    headers, _ = account(client)
    response = client.post('/api/v1/create/auto', headers=headers, json={
        'text': ARTICLE.replace('== ', '# ').replace(' ==', ''), 'save': False})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['created'] is False and payload['enrolled'] is False
    mine = client.get('/api/v1/my-courses', headers=headers)
    assert mine.json()['count'] == 0, 'a plan saved nowhere must not appear in my courses'


def test_auto_route_refuses_a_link_only_candidate_with_a_reason(client, monkeypatch):
    stub_wikipedia(monkeypatch, pages=[])
    headers, _ = account(client)
    search = client.post('/api/v1/create/search', headers=headers, json={'query': 'physics'})
    assert search.status_code == 200, search.text
    link_only = next((c for c in search.json()['results']
                      if c['licence_class'] == 'link_only'), None)
    assert link_only is not None, 'the audited references must be offered as unbuildable'
    response = client.post('/api/v1/create/auto', headers=headers,
                           json={'candidate_id': link_only['id']})
    assert response.status_code == 422, response.text
    detail = response.json()['detail']
    assert detail['refused'] is True
    assert detail['code'] == 'source_not_buildable'
    assert detail['licence_class'] == 'link_only'
    assert 'paste' in detail['reason'].lower()


def test_auto_route_refuses_a_source_too_thin_for_a_course(client):
    headers, _ = account(client)
    response = client.post('/api/v1/create/auto', headers=headers,
                           json={'text': 'ATP carries energy. That is all.'})
    assert response.status_code == 422, response.text
    assert response.json()['detail']['code'] == 'source_too_short'
