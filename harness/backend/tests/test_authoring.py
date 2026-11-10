"""The content foundry: authoring a course from inside the harness.

What is under test here is the claim the whole subsystem exists to make: that this
product can design, build, audit and serve a course it was not shipped with, without an
authoring session outside the product.

The tests are organised by that claim rather than by module.

* **The blueprint is a document, and a bad one is refused with a location.** A dangling
  prerequisite or a forward edge cannot be repaired by guessing, so it is refused - and
  the refusal names the JSON path, because the primary reader is the model being asked to
  fix it.
* **Synthesis produces the shapes the rest of the harness already reads.** A foundry
  concept has to be indistinguishable from a shipped one to every downstream consumer:
  same keys, same block kinds, four-plus items per concept, a valid answer key.
* **The audit refuses a course that looks complete.** An item whose answer is nowhere in
  the lesson, a lesson with no worked example, a flat difficulty ramp, a course with only
  recall items - each is a real defect that no other check in this codebase would catch.
* **A published course survives a restart.** Stored, re-hydrated, resolvable through
  ``courses.course`` and the curriculum registries, and withdrawn cleanly on delete.
* **Drafting is two passes with the validator in the loop.** The second attempt must
  carry the first attempt's complaint, or the retry is a coin flip.
* **The HTTP surface is teacher-only and its preview is a real dry run.**
* **The review page is readable, correct and escaped.** The JSON is the record, but a
  course is prose and a human has to read it before approving it - with the right answer
  marked, and with a ``<`` in a lesson staying a ``<``.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import courses, curriculum
from app.config import Settings
from app.db import User
from app.harness.authoring import (audit as audit_module, blueprint, draft as draft_module,
                                   illustrate as illustrate_module, methodology, registry,
                                   synthesize)
from app.harness.authoring import tools as authoring_tools
from app.harness import provider, toolbox
from app.harness.toolbox import ToolContext
from app.main import create_app

PASSWORD = 'CorrectHorseBatteryStaple9!'


# --------------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def clean_foundry():
    """Every test starts with no authored course published and none remembered."""
    registry.reset()
    yield
    registry.reset()


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    # Authoring illustrates by default, and a test suite must not reach the network. The
    # illustration tests opt back in through ``media_settings``, which is also the honest
    # shape of the feature: offline is a reported outcome, not a failure.
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '0')
    return Settings.from_env()


@pytest.fixture
def media_settings(settings):
    """The same deployment with outbound media permitted - the stubbed-network case."""
    from dataclasses import replace

    return replace(settings, media_enabled=True)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def media_client(media_settings):
    with TestClient(create_app(media_settings)) as client:
        yield client


def concept(title, summary, prerequisites=(), **extra):
    return {'title': title, 'summary': summary,
            'definition': f'{title} is defined here with its conditions and its limits '
                          f'stated explicitly.',
            'example': [f'Take the standard case for {title}.',
                        'Apply the rule, showing each step.',
                        'Check the result against a case you already know.'],
            'misconception': f'Learners often assume {title} applies in every case.',
            'correction': f'{title} applies only under its stated conditions; check them.',
            'application': f'Use {title} to decide a case you have not seen and justify '
                           f'each step.',
            'objective': f'Explain and apply {title}.',
            'prerequisites': list(prerequisites), **extra}


def blueprint_doc(**overrides):
    """A course that passes the default profile, with one unit per concept family."""
    doc = {
        'schema': 1,
        'course': {
            'id': 'cell_biology',
            'title': 'Cell Biology',
            'subject': 'Biology',
            'description': 'An eight week introduction to how cells are built, how they '
                           'do work, and how they divide.',
            'expected_weeks': 8,
        },
        'units': [
            {'title': 'What a cell is', 'strand': 'Structure',
             'objective': 'Distinguish a cell from the things inside it.',
             'concepts': [
                 concept('Cell theory',
                         'All living things are made of cells, and every new cell comes '
                         'from an existing cell.'),
                 concept('Cell membrane',
                         'A selectively permeable boundary made of a phospholipid bilayer '
                         'with embedded proteins.', ['Cell theory']),
                 concept('Cytoplasm',
                         'The aqueous interior of the cell where most metabolic reactions '
                         'take place.', ['Cell membrane'])]},
            {'title': 'How a cell does work', 'strand': 'Function',
             'objective': 'Trace energy and material through a cell.',
             'concepts': [
                 concept('Enzyme',
                         'A protein catalyst that lowers the activation energy of a '
                         'reaction without being consumed.', ['Cytoplasm']),
                 concept('Diffusion',
                         'The net movement of particles from a region of high '
                         'concentration to a region of low concentration.',
                         ['Cell membrane']),
                 concept('Osmosis',
                         'The diffusion of water across a selectively permeable membrane '
                         'down its own concentration gradient.', ['Diffusion'])]},
            {'title': 'How a cell divides', 'strand': 'Reproduction',
             'objective': 'Explain how genetic material is copied and then separated.',
             'concepts': [
                 concept('Chromosome',
                         'A single DNA molecule packaged with histone proteins so that it '
                         'can be moved during division.', ['Cell theory']),
                 concept('Mitosis',
                         'Division of the nucleus that produces two daughter nuclei with '
                         'identical genetic material.', ['Chromosome']),
                 concept('Cytokinesis',
                         'Division of the cytoplasm that follows mitosis and separates the '
                         'two new cells.', ['Mitosis'])]},
        ],
    }
    doc.update(overrides)
    return doc


def build(doc=None):
    plan, problems = blueprint.parse(doc or blueprint_doc())
    assert plan is not None, [str(problem) for problem in problems]
    return synthesize.build(plan), problems


# --------------------------------------------------------------------- blueprint

def test_blueprint_resolves_prerequisites_by_title():
    """A model reliably knows the title it just wrote and unreliably invents slugs."""
    plan, problems = blueprint.parse(blueprint_doc())
    assert plan is not None, [str(p) for p in problems]
    membrane = plan.by_id()['cell_membrane']
    assert membrane.prerequisites == ('cell_theory',)


def test_blueprint_refuses_a_dangling_prerequisite():
    doc = blueprint_doc()
    doc['units'][0]['concepts'][1]['prerequisites'] = ['Something never mentioned']
    plan, problems = blueprint.parse(doc)
    assert plan is None
    codes = {problem.code for problem in blueprint.blocking(problems)}
    assert 'prerequisite_unresolved' in codes


def test_blueprint_refuses_a_forward_prerequisite():
    """A concept may only depend on something taught earlier; this is the common error."""
    doc = blueprint_doc()
    doc['units'][0]['concepts'][0]['prerequisites'] = ['Cytoplasm']
    plan, problems = blueprint.parse(doc)
    assert plan is None
    assert 'prerequisite_forward' in {problem.code for problem in blueprint.blocking(problems)}


def test_blueprint_refuses_a_cycle():
    doc = blueprint_doc()
    doc['units'][0]['concepts'][0]['prerequisites'] = ['Cytoplasm']
    doc['units'][0]['concepts'][2]['prerequisites'] = ['Cell theory']
    plan, problems = blueprint.parse(doc)
    assert plan is None
    assert 'prerequisite_cycle' in {problem.code for problem in blueprint.blocking(problems)}


def test_blueprint_refuses_a_concept_with_too_many_prerequisites():
    doc = blueprint_doc()
    doc['units'][2]['concepts'][2]['prerequisites'] = ['Cell theory', 'Cell membrane',
                                                       'Cytoplasm']
    plan, problems = blueprint.parse(doc)
    assert plan is None
    assert 'prerequisite_overload' in {p.code for p in blueprint.blocking(problems)}


def test_thin_prose_is_advisory_at_parse_and_blocking_at_audit():
    """The parser reports; the audit refuses. One gate decides what may ship."""
    doc = blueprint_doc()
    doc['units'][0]['concepts'][0]['summary'] = 'Cells are small.'
    plan, problems = blueprint.parse(doc)
    assert plan is not None
    assert 'summary_thin' in {problem.code for problem in problems}
    course, _ = build(doc)
    report = audit_module.audit(course)
    assert not report.ok
    assert 'summary_thin' in {finding.code for finding in report.errors}


def test_unknown_profile_is_refused_rather_than_defaulted():
    with pytest.raises(KeyError):
        methodology.profile('graduate')


def test_override_cannot_invent_a_field():
    with pytest.raises(ValueError):
        methodology.profile('default', {'shape': {'max_consepts': 10}})


# -------------------------------------------------------------------- synthesis

def test_synthesis_matches_the_shipped_concept_shape():
    """A foundry concept must be indistinguishable downstream from a shipped one."""
    course, _ = build()
    shipped = next(iter(curriculum.CONCEPTS.values()))
    for entry in course.concepts.values():
        for key in ('id', 'title', 'unit', 'prerequisites', 'summary', 'blocks',
                    'simulation', 'project', 'media', 'hint', 'course_id'):
            assert key in entry, key
        assert entry['generated'] is True
        assert entry['origin'] == synthesize.ORIGIN
        assert entry['course_id'] == 'cell_biology'
        assert isinstance(entry['blocks'], list) and entry['blocks']
    # The shipped entry is a dict of the same *kind*; the shared keys are what matter.
    assert isinstance(shipped, dict)


def test_every_concept_gets_at_least_four_valid_items():
    course, _ = build()
    by_concept = {}
    for item in course.questions.values():
        by_concept.setdefault(item['concept_id'], []).append(item)
    for concept_id, items in by_concept.items():
        assert len(items) >= 4, concept_id
        for item in items:
            assert len(item['options']) == 4, item['id']
            texts = [option['text'] for option in item['options']]
            assert len(set(texts)) == 4, item['id']
            answer = next(option for option in item['options']
                          if option['id'] == item['answer_id'])
            assert answer['text'] == item['answer_text']


def test_the_foundry_adds_discrimination_and_transfer_items():
    course, _ = build()
    categories = {item['category'] for item in course.questions.values()}
    assert {'misconception_repair', 'application_transfer'} <= categories


def test_the_lesson_carries_the_depth_the_generated_layer_cannot():
    course, _ = build()
    entry = course.concepts['cell_membrane']
    kinds = [block['kind'] for block in entry['blocks']]
    assert kinds[:5] == ['concept', 'concept', 'worked_example', 'misconception',
                         'retrieval']
    worked = next(block for block in entry['blocks'] if block['kind'] == 'worked_example')
    assert '1.' in worked['body']
    misconception = next(block for block in entry['blocks']
                         if block['kind'] == 'misconception')
    assert 'The mistake:' in misconception['body']
    assert 'The repair:' in misconception['body']


def test_a_step_list_the_model_already_numbered_is_not_numbered_again():
    """The review copy said "1. 1. Draw the axes", which reads as carelessness.

    The model is asked for steps as a list and usually returns them numbered. Prefixing
    our own index produced a doubled enumerator in every lesson, so the numbering is
    added only when the steps arrive unnumbered.
    """
    plan, _ = blueprint.parse(blueprint_doc())
    concept_plan = plan.by_id()['cell_membrane']

    numbered = replace(concept_plan, example=['1. Draw the axes.', '2. Read the intercept.',
                                              '3. State the slope.'])
    body = synthesize._example_body(numbered)
    assert body.splitlines()[0] == '1. Draw the axes.'
    assert '1. 1.' not in body

    plain = replace(concept_plan, example=['Draw the axes.', 'Read the intercept.'])
    assert synthesize._example_body(plain) == '1. Draw the axes.\n2. Read the intercept.'


def test_the_worked_example_fades_in_the_final_unit():
    course, _ = build()
    final_unit = course.plan.units[-1].title
    for concept in course.plan.concepts():
        kinds = [block['kind'] for block in course.concepts[concept.id]['blocks']]
        if concept.unit == final_unit:
            assert 'worked_example' not in kinds
            assert any(block['title'] == 'Your turn, without a model'
                       for block in course.concepts[concept.id]['blocks'])
        else:
            assert 'worked_example' in kinds


def test_every_lesson_states_where_it_came_from():
    course, _ = build()
    for entry in course.concepts.values():
        scope = [block for block in entry['blocks']
                 if block['title'] == 'Where this lesson comes from']
        assert len(scope) == 1
        assert course.plan.digest() in scope[0]['body']


def test_difficulty_ramps_across_the_course():
    course, _ = build()
    ordered = [course.graph.nodes[concept.id].difficulty
               for concept in course.plan.concepts()]
    assert ordered[0] < ordered[-1]
    assert len(set(ordered)) > 1


def test_synthesis_is_deterministic():
    first, _ = build()
    second, _ = build()
    assert first.questions.keys() == second.questions.keys()
    for question_id, item in first.questions.items():
        assert item['answer_id'] == second.questions[question_id]['answer_id']


# ------------------------------------------------------------------------ audit

def test_audit_refuses_an_item_whose_answer_is_not_in_the_lesson():
    """The property that makes machine-authored items trustworthy at all."""
    course, _ = build()
    item = next(item for item in course.questions.values()
                if item['category'] == 'misconception_repair')
    correct = next(option for option in item['options']
                   if option['id'] == item['answer_id'])
    # A *consistent* item whose answer the lesson never stated: the answer key and the
    # option agree, so only the answerability check can catch it. Mutating the option
    # alone would trip the answer-key check instead and prove nothing about this one.
    invented = 'A statement that appears nowhere in this lesson.'
    correct['text'] = invented
    item['answer_text'] = invented
    report = audit_module.audit(course)
    assert not report.ok
    assert 'item_unanswerable' in {finding.code for finding in report.errors}


def test_audit_refuses_a_lesson_with_no_worked_example():
    course, _ = build()
    entry = course.concepts['enzyme']
    entry['blocks'] = [block for block in entry['blocks']
                       if block['kind'] != 'worked_example']
    report = audit_module.audit(course)
    assert 'block_missing' in {finding.code for finding in report.errors}


def test_audit_refuses_a_course_that_only_asks_for_recall():
    course, _ = build()
    for question_id in list(course.questions):
        if course.questions[question_id]['category'] in ('misconception_repair',
                                                         'application_transfer'):
            course.questions.pop(question_id)
    report = audit_module.audit(course)
    assert 'category_missing' in {finding.code for finding in report.errors}


def test_audit_reports_a_flat_difficulty_ramp():
    doc = blueprint_doc()
    for unit in doc['units']:
        for item in unit['concepts']:
            item['difficulty'] = 3
    course, _ = build(doc)
    report = audit_module.audit(course)
    assert 'difficulty_flat' in {finding.code for finding in report.errors}


def test_audit_accepts_the_course_it_is_given():
    course, _ = build()
    report = audit_module.audit(course)
    assert report.ok, [finding.to_dict() for finding in report.errors]
    assert report.stats['concepts'] == 9
    assert report.stats['items_per_concept'] >= 4


# --------------------------------------------------------------------- registry

def test_a_published_course_is_resolvable_and_survives_a_restart(settings):
    course, _ = build()
    record = registry.store(settings, course)

    assert courses.course('cell_biology').title == 'Cell Biology'
    assert courses.graph_for('cell_biology').nodes['cell_membrane'].title == 'Cell membrane'
    assert curriculum.CONCEPT_COURSE['cell_membrane'] == 'cell_biology'
    assert 'cell_membrane' in curriculum.CONCEPTS
    assert 'cell_biology' in {spec.id for spec in courses.COURSES}

    stored = Path(settings.data_dir) / registry.ROOT / 'cell_biology.json'
    assert stored.exists()

    # A restart: nothing in memory, everything on disk.
    registry.reset()
    assert registry.get('cell_biology') is None
    summary = registry.hydrate(settings)
    assert summary['published'] == 1
    assert registry.get('cell_biology').card()['digest'] == record.digest
    assert courses.course('cell_biology').title == 'Cell Biology'


def test_deleting_a_course_withdraws_it_from_every_registry(settings):
    course, _ = build()
    registry.store(settings, course)
    assert registry.delete(settings, 'cell_biology') is True
    assert registry.get('cell_biology') is None
    assert 'cell_membrane' not in curriculum.CONCEPTS
    assert 'cell_biology' not in {spec.id for spec in courses.COURSES}
    with pytest.raises(courses.UnknownCourse):
        courses.course('cell_biology')


def test_a_course_may_not_shadow_a_shipped_one(settings):
    course, _ = build()
    shadow = courses.Course(id='physics', title='Physics', subject='Physics',
                            subject_kind='science', description='x', pack='physics',
                            expected_weeks=36, authored=False)
    record = registry.Record(id='physics', course=shadow, graph=course.graph,
                             concepts={}, questions={}, blueprint={})
    with pytest.raises(ValueError, match='shipped'):
        registry.publish(record)


def test_store_refuses_an_unaudited_course(settings):
    course, _ = build()
    entry = course.concepts['enzyme']
    entry['blocks'] = []
    with pytest.raises(audit_module.CourseRefused):
        registry.store(settings, course)
    assert registry.get('cell_biology') is None


def test_republishing_requires_an_explicit_replace(settings):
    course, _ = build()
    registry.store(settings, course)
    with pytest.raises(ValueError, match='already exists'):
        registry.store(settings, course)
    record = registry.store(settings, course, replace=True)
    assert record.card()['concepts'] == 9


# ----------------------------------------------------------------------- drafting

def test_draft_refuses_without_a_model(settings):
    with pytest.raises(draft_module.DraftUnavailable) as caught:
        draft_module.draft(settings, 'thermodynamics')
    assert 'blueprint' in str(caught.value)


@pytest.fixture
def model_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'http://model.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key')
    return Settings.from_env()


def test_draft_retries_with_the_validators_complaint(model_settings, monkeypatch):
    """A retry that re-asks the same question is a second coin flip, not a retry."""
    doc = blueprint_doc()
    skeleton = {'course': doc['course'],
                'units': [{'title': unit['title'], 'strand': unit['strand'],
                           'objective': unit['objective'],
                           'concepts': [{'title': c['title'], 'summary': c['summary'],
                                         'prerequisites': c['prerequisites']}
                                        for c in unit['concepts']]}
                          for unit in doc['units']]}
    expansions = {index: {'concepts': [{'title': c['title'], 'summary': c['summary'],
                                        'definition': c['definition'],
                                        'example': c['example'],
                                        'misconception': c['misconception'],
                                        'correction': c['correction'],
                                        'application': c['application'],
                                        'objective': c['objective']}
                                       for c in unit['concepts']]}
                  for index, unit in enumerate(doc['units'])}

    seen: list[list[dict]] = []

    def fake_chat_json(settings, messages, *, max_tokens=1200, usage_out=None):
        seen.append([dict(message) for message in messages])
        if len(seen) == 1:
            # A skeleton whose only flaw is a dangling prerequisite.
            broken = json.loads(json.dumps(skeleton))
            broken['units'][0]['concepts'][1]['prerequisites'] = ['Nowhere']
            return broken
        if len(seen) == 2:
            return skeleton
        return expansions[len(seen) - 3]

    monkeypatch.setattr(provider, 'chat_json', fake_chat_json)
    drafted = draft_module.draft(model_settings, 'cell biology', units=3)

    assert drafted.attempts >= 4
    retry_prompt = seen[1][-1]['content']
    assert 'prerequisite' in retry_prompt
    assert 'Nowhere' in retry_prompt or 'concept' in retry_prompt
    assert drafted.report.ok


def test_a_refused_lesson_is_rewritten_from_the_complaint(model_settings, monkeypatch):
    """The audit's complaint has to reach the only party that can act on it.

    A summary three words short of the floor used to be a permanent refusal: the run had
    written the lesson, could not fix it, and stored nothing.
    """
    plan, problems = blueprint.parse(blueprint_doc())
    assert plan is not None, [str(problem) for problem in problems]
    refused_concept = plan.concepts()[0]

    seen: list[str] = []

    def fake_chat_json(settings, messages, *, max_tokens=1200, usage_out=None):
        seen.append(messages[-1]['content'])
        return {'concepts': [{'title': refused_concept.title,
                              'summary': 'This summary is comfortably longer than the '
                                         'floor the validator enforces, and says what the '
                                         'idea is.',
                              'example': ['Write the first step out.',
                                          'Carry it through to the answer.'],
                              'application': 'Decide a case the lesson does not state, '
                                             'using exactly this idea, and justify it.'}]}

    monkeypatch.setattr(provider, 'chat_json', fake_chat_json)
    repaired = draft_module.repair(
        model_settings, plan,
        {refused_concept.id: ['summary_thin: the summary is 9 words; the floor is 12']})

    assert 'summary_thin' in seen[0], 'the complaint is quoted back'
    fixed = next(concept for concept in repaired.concepts()
                 if concept.id == refused_concept.id)
    assert fixed.summary.startswith('This summary is comfortably longer')
    assert len(fixed.example) == 2
    untouched = next(concept for concept in repaired.concepts()
                     if concept.id != refused_concept.id)
    original = next(concept for concept in plan.concepts()
                    if concept.id != refused_concept.id)
    assert untouched.summary == original.summary, (
        'a lesson that was not refused must not be rewritten')


def test_draft_gives_up_honestly(model_settings, monkeypatch):
    monkeypatch.setattr(provider, 'chat_json',
                        lambda *args, **kwargs: {'units': []})
    with pytest.raises(draft_module.DraftRefused):
        draft_module.draft(model_settings, 'cell biology')


def _prose_for(title):
    return {'title': title,
            'summary': f'{title} is the idea this lesson is about, stated plainly and '
                       f'sharply enough that a learner could repeat it from memory.',
            'definition': f'{title} holds under its stated conditions, and those '
                          f'conditions are part of the definition rather than a caveat.',
            'example': [f'Take a case of {title} and write down what is fixed.',
                        f'Change one thing and say what follows for {title}.'],
            'misconception': f'Learners often treat {title} as a label to memorise.',
            'correction': f'{title} is a relation with conditions, not a label.',
            'application': f'Decide a case the lesson does not state, using {title}, '
                           f'and justify each step.',
            'objective': f'Explain and apply {title}.'}


def test_an_answer_that_puts_a_summary_in_the_title_still_lands(model_settings,
                                                                monkeypatch):
    """The failure that cost a real run: titles returned as "Name: one-line summary".

    The merge matched on the whole string, so every one of those concepts silently kept a
    pack summary and no lesson, and the audit refused the finished course for thin lessons
    the model had in fact written.
    """
    plan, problems = blueprint.parse(blueprint_doc())
    assert plan is not None, [str(problem) for problem in problems]

    def fake_chat_json(settings, messages, *, max_tokens=1200, usage_out=None):
        asked = [line[2:].split(':')[0]
                 for line in messages[-1]['content'].splitlines() if line.startswith('- ')]
        return {'concepts': [dict(_prose_for(title),
                                  title=f'{title}: the idea this lesson is about, stated '
                                        f'plainly and sharply enough to repeat.')
                             for title in asked]}

    monkeypatch.setattr(provider, 'chat_json', fake_chat_json)
    written = draft_module.expand(model_settings, plan)
    assert all(concept.example for concept in written.concepts()), (
        'every concept in the framed plan came back with prose')
    assert {concept.title for concept in written.concepts()} == {
        concept.title for concept in plan.concepts()}, (
        'the titles are the course\'s own, whatever shape the answer used')


def test_a_half_answered_batch_is_asked_again_for_the_rest(model_settings, monkeypatch):
    """A partial answer used to be accepted, because only the length was checked.

    That is how a run reports every concept present and half of them without a lesson.
    """
    plan, problems = blueprint.parse(blueprint_doc())
    assert plan is not None, [str(problem) for problem in problems]

    calls: list[list[dict]] = []

    def fake_chat_json(settings, messages, *, max_tokens=1200, usage_out=None):
        calls.append([dict(message) for message in messages])
        asked = [line[2:].split(':')[0]
                 for line in messages[-1]['content'].splitlines() if line.startswith('- ')]
        if len(calls) == 1:
            return {'concepts': [_prose_for(asked[0])]}
        return {'concepts': [_prose_for(title) for title in asked]}

    monkeypatch.setattr(provider, 'chat_json', fake_chat_json)
    written = draft_module.expand(model_settings, plan)

    assert len(calls) > 1
    retry = calls[1][-1]['content']
    assert 'covered other concepts' in retry
    assert all(concept.example for concept in written.concepts())


# -------------------------------------------------------------------- agent tools

class _Ctx(ToolContext):
    def __init__(self, settings, role):
        super().__init__(db=None, user=type('U', (), {'id': 'u1', 'role': role})(),
                         settings=settings)


def test_authoring_tools_are_teacher_gated(settings):
    learner = authoring_tools.author_course(_Ctx(settings, 'learner'), blueprint_doc())
    assert learner.ok is False
    assert 'teacher' in learner.refused


def test_authoring_tool_builds_and_publishes(settings):
    result = authoring_tools.author_course(_Ctx(settings, 'teacher'), blueprint_doc())
    assert result.ok is True, result.refused
    assert result.data['course']['id'] == 'cell_biology'
    assert result.data['audit']['ok'] is True
    listed = authoring_tools.list_authored_courses(_Ctx(settings, 'teacher'))
    assert [card['id'] for card in listed.data['courses']] == ['cell_biology']


def test_authoring_tool_reports_audit_findings_rather_than_storing(settings):
    doc = blueprint_doc()
    doc['units'][0]['concepts'][0]['summary'] = 'Cells are small.'
    result = authoring_tools.author_course(_Ctx(settings, 'teacher'), doc)
    assert result.ok is False
    assert registry.get('cell_biology') is None
    codes = {finding['code'] for finding in result.data['audit']['errors']}
    assert 'summary_thin' in codes


def test_extend_course_adds_a_unit_under_the_same_audit(settings):
    assert authoring_tools.author_course(_Ctx(settings, 'teacher'), blueprint_doc()).ok
    unit = {'title': 'How a cell responds', 'strand': 'Regulation',
            'objective': 'Explain how a cell changes behaviour in response to a signal.',
            'concepts': [
                concept('Receptor',
                        'A membrane protein that binds a specific signalling molecule and '
                        'passes the signal inward.'),
                concept('Signal cascade',
                        'A chain of intracellular reactions that amplifies a receptor '
                        'signal into a cellular response.', ['Receptor']),
                concept('Feedback inhibition',
                        'A product of a pathway suppresses an earlier step, holding the '
                        'response within bounds.', ['Signal cascade'])]}
    result = authoring_tools.extend_course(_Ctx(settings, 'teacher'), 'cell_biology', unit)
    assert result.ok is True, result.refused
    assert result.data['course']['concepts'] == 12
    assert result.data['previous_digest'] != result.data['course']['digest']


def test_tools_are_registered_for_the_agent_loop():
    for name in ('author_course', 'draft_course', 'list_authored_courses',
                 'read_course_blueprint', 'extend_course', 'describe_methodology'):
        assert name in toolbox.REGISTRY


# -------------------------------------------------------------------------- HTTP

def _teacher(client, email=None):
    payload = {'name': 'Teacher', 'email': email or f'{uuid4().hex[:8]}@example.test',
               'password': PASSWORD}
    response = client.post('/api/v1/auth/register', json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    with client.app.state.factory() as db:
        user = db.get(User, body['user']['id'])
        user.role = 'teacher'
        db.commit()
    return {'Authorization': 'Bearer ' + body['token']}


def test_http_preview_stores_nothing(client):
    headers = _teacher(client)
    response = client.post('/api/v1/author/preview', headers=headers,
                           json={'blueprint': blueprint_doc()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['ok'] is True
    assert body['stored'] is False
    assert body['lesson_sample']['blocks']
    assert {item['category'] for item in body['items_sample']} >= {'definition_recall'}
    assert registry.get('cell_biology') is None


def test_http_create_then_read_then_delete(client):
    headers = _teacher(client)
    created = client.post('/api/v1/author/courses', headers=headers,
                          json={'blueprint': blueprint_doc()})
    assert created.status_code == 200, created.text
    assert created.json()['course']['id'] == 'cell_biology'

    listed = client.get('/api/v1/author/courses', headers=headers).json()
    assert [card['id'] for card in listed['courses']] == ['cell_biology']

    detail = client.get('/api/v1/author/courses/cell_biology', headers=headers).json()
    assert detail['course']['concepts'] == 9
    assert detail['units'][0]['title'] == 'What a cell is'

    design = client.get('/api/v1/author/courses/cell_biology/blueprint',
                        headers=headers).json()
    assert design['blueprint']['course']['title'] == 'Cell Biology'

    removed = client.delete('/api/v1/author/courses/cell_biology', headers=headers)
    assert removed.status_code == 200
    assert client.get('/api/v1/author/courses/cell_biology',
                      headers=headers).status_code == 404


def test_http_requires_a_teacher(client):
    payload = {'name': 'Learner', 'email': f'{uuid4().hex[:8]}@example.test',
               'password': PASSWORD}
    body = client.post('/api/v1/auth/register', json=payload).json()
    headers = {'Authorization': 'Bearer ' + body['token']}
    response = client.post('/api/v1/author/courses', headers=headers,
                           json={'blueprint': blueprint_doc()})
    assert response.status_code == 403


def test_http_refuses_an_unreadable_blueprint(client):
    headers = _teacher(client)
    doc = blueprint_doc()
    doc['units'][0]['concepts'][1]['prerequisites'] = ['Nowhere']
    response = client.post('/api/v1/author/courses', headers=headers,
                           json={'blueprint': doc})
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['problems']['blocking']


def test_http_refuses_a_thin_course_with_audit_findings(client):
    headers = _teacher(client)
    doc = blueprint_doc()
    doc['units'][0]['concepts'][0]['summary'] = 'Cells are small.'
    response = client.post('/api/v1/author/courses', headers=headers,
                           json={'blueprint': doc})
    assert response.status_code == 422
    assert response.json()['detail']['audit']['ok'] is False


def test_http_draft_without_a_model_is_503(client):
    headers = _teacher(client)
    response = client.post('/api/v1/author/draft', headers=headers,
                           json={'topic': 'cell biology'})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'no_model'


def test_http_methodology_is_readable(client):
    headers = _teacher(client)
    body = client.get('/api/v1/author/methodology', headers=headers).json()
    assert body['name'] == 'default'
    assert body['lineage']
    assert body['shape']['max_prerequisites'] == 2


def test_an_authored_course_is_studyable_through_the_existing_endpoints(client):
    """The claim the whole subsystem rests on: not a special case.

    A learner enrolled in an authored course must see it on the map, open its lessons and
    be served its items through the same routes that serve the shipped courses. If any of
    these needed a branch of its own, the capability would have moved next to the harness
    rather than into it.
    """
    teacher = _teacher(client)
    created = client.post('/api/v1/author/courses', headers=teacher,
                          json={'blueprint': blueprint_doc()})
    assert created.status_code == 200, created.text

    payload = {'name': 'Learner', 'email': f'{uuid4().hex[:8]}@example.test',
               'password': PASSWORD}
    body = client.post('/api/v1/auth/register', json=payload).json()
    learner = {'Authorization': 'Bearer ' + body['token']}
    with client.app.state.factory() as db:
        user = db.get(User, body['user']['id'])
        user.course_id = 'cell_biology'
        db.commit()

    curriculum_payload = client.get('/api/v1/curriculum', headers=learner)
    assert curriculum_payload.status_code == 200, curriculum_payload.text
    data = curriculum_payload.json()
    assert data['course']['id'] == 'cell_biology'
    assert {concept['id'] for concept in data['concepts']} >= {'cell_membrane', 'osmosis'}
    assert all(concept['course_id'] == 'cell_biology' for concept in data['concepts'])

    lesson = client.get('/api/v1/lessons/cell_membrane', headers=learner)
    assert lesson.status_code == 200, lesson.text
    lesson_body = lesson.json()
    assert lesson_body['title'] == 'Cell membrane'
    kinds = [block['kind'] for block in lesson_body['blocks']]
    assert 'worked_example' in kinds and 'misconception' in kinds

    graph = client.get('/api/v1/knowledge-graph', headers=learner)
    assert graph.status_code == 200, graph.text
    nodes = {node['id'] for node in graph.json()['nodes']}
    assert 'cell_membrane' in nodes

    practice = client.get('/api/v1/questions/next', headers=learner,
                          params={'mode': 'practice', 'concept_id': 'cell_membrane'})
    assert practice.status_code == 200, practice.text
    item = practice.json()
    assert len(item['options']) == 4
    assert item['concept_id'] == 'cell_membrane'
    assert item['receipt']


# ------------------------------------------------- the review surface a human reads

@pytest.fixture(scope='module')
def cli_module():
    """Load ``scripts/author_course.py`` the way the other script tests do."""
    import importlib.util

    script = Path(__file__).resolve().parents[1] / 'scripts' / 'author_course.py'
    spec = importlib.util.spec_from_file_location('author_course_cli', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_review_page_shows_the_lessons_the_items_and_the_answer_key(cli_module):
    """The JSON is the record; a human still has to be able to read what was written.

    Every assertion here is a thing a reviewer would otherwise have to open the JSON to
    find: that the lesson text is on the page, that each item carries four options, and
    that exactly one of them is marked correct. A review copy whose answer key is wrong
    is worse than no review copy, because it looks authoritative.
    """
    from html.parser import HTMLParser

    course, _ = build()
    report = audit_module.audit(course)
    page = cli_module.render_html(course, report)

    class Balanced(HTMLParser):
        VOID = {'br', 'meta', 'img', 'hr', 'input', 'link'}

        def __init__(self):
            super().__init__()
            self.open, self.mismatched = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in self.VOID:
                self.open.append(tag)

        def handle_endtag(self, tag):
            if self.open and self.open[-1] == tag:
                self.open.pop()
            else:
                self.mismatched.append(tag)

    parser = Balanced()
    parser.feed(page)
    assert parser.open == [], f'unclosed tags: {parser.open}'
    assert parser.mismatched == [], f'mismatched tags: {parser.mismatched}'

    assert f'<h1>{course.course.title}</h1>' in page
    assert page.count('<h2>') == len(course.plan.units)
    assert page.count('<h3>') == course.concept_count
    assert page.count('What it asks') == course.concept_count
    assert page.count('<span class="tag">') == course.question_count
    assert page.count('<li class="correct">') == course.question_count
    assert page.count('<li>') == course.question_count * 3
    assert page.count('class=""') == 0, 'an empty class attribute is markup noise'

    first = course.concepts['cell_theory']['blocks'][0]['body']
    assert first in page, 'the lesson text is not on the review page'
    assert 'audit: PASS' in page
    assert course.plan.digest() in page


def test_the_review_page_escapes_a_lesson_and_reports_a_refusal(cli_module):
    """A refused course still renders - and the page says so, with the finding.

    An audit refusal is the normal outcome of a bad blueprint, so the review copy has to
    survive one. It also has to escape: the body is model-written text, and a ``<`` in a
    lesson must not become a tag.
    """
    from html import escape

    course, _ = build()
    course.concepts['cell_theory']['blocks'][0]['body'] = 'compare a < b, not <script>'
    bad = audit_module.Audit(
        findings=[audit_module.Finding('item_unanswerable', 'questions[3]',
                                       'the answer is not in the lesson', 'error')],
        stats={})

    page = cli_module.render_html(course, bad)
    assert '&lt;script&gt;' in page
    assert '<script>' not in page
    assert 'audit: REFUSED' in page
    assert 'item_unanswerable' in page
    assert escape('questions[3]') in page


# ------------------------------------------- the textbook is multimodal, with real images

def _stub_media(monkeypatch):
    """Make the image pipeline answer offline, with one real cleared candidate.

    Imported from ``test_image_fetch`` rather than re-implemented: there is one set of
    stubs for the media module, and a second copy here would drift from the first.
    """
    from test_image_fetch import _cleared_candidate, _stub_download, _stub_search

    _stub_search(monkeypatch, [_cleared_candidate()])
    _stub_download(monkeypatch)


def _enrol(client, course_id):
    payload = {'name': 'Learner', 'email': f'{uuid4().hex[:8]}@example.test',
               'password': PASSWORD}
    body = client.post('/api/v1/auth/register', json=payload).json()
    with client.app.state.factory() as db:
        user = db.get(User, body['user']['id'])
        user.course_id = course_id
        db.commit()
    return {'Authorization': 'Bearer ' + body['token']}


def test_an_authored_textbook_carries_a_real_photograph(media_settings, client, monkeypatch):
    """The claim: a lesson of a course the harness wrote itself shows a real photograph.

    Everything downstream is the existing machinery - the assignment index, the manifest,
    the block shape, the lesson route - so what this pins is the *connection*, which is what
    was missing: authoring never asked for an image, so every authored textbook was text.
    """
    from app.harness import media

    _stub_media(monkeypatch)
    course, _ = build()
    illustrated = illustrate_module.illustrate(media_settings, course, only=['cell_theory'])
    assert illustrated.outcome == 'ok', illustrated.to_dict()
    assert illustrated.assigned == 1

    blocks = media.lesson_photograph_blocks(media_settings, 'cell_theory')
    assert len(blocks) == 1
    photo = blocks[0]['block']
    assert photo['kind'] == 'photograph'
    assert photo['src'].startswith('/api/v1/media/images/')
    assert photo['credit'].startswith('"Cell division"'), photo['credit']
    assert photo['licence'] == 'CC BY 4.0'
    assert photo['alt'], 'a photograph with no alt text is invisible to a screen reader'

    teacher = _teacher(client)
    created = client.post('/api/v1/author/courses', headers=teacher,
                          json={'blueprint': blueprint_doc(), 'illustrate': False})
    assert created.status_code == 200, created.text
    learner = _enrol(client, 'cell_biology')
    lesson = client.get('/api/v1/lessons/cell_theory', headers=learner)
    assert lesson.status_code == 200, lesson.text
    served = [block for block in lesson.json()['blocks'] if block.get('kind') == 'photograph']
    assert served, 'the lesson route served no photograph'
    assert served[0]['credit'] == photo['credit']
    # Placed after the first block, so the core idea is not pushed off the top of the page.
    assert lesson.json()['blocks'].index(served[0]) == 1


def test_an_unverified_image_cannot_enter_a_textbook(media_settings, monkeypatch):
    """A clipboard paste has no licence. It is servable to the account that pasted it, and
    it is not printable in a book that renders a credit line."""
    from app.harness import media
    from test_image_fetch import PNG

    course, _ = build()
    media.store_bytes(media_settings, PNG, title='Pasted screenshot', source='clipboard_paste')
    sha = next(row['sha256'] for row in media.cached_assets(media_settings)
               if row.get('source') == 'clipboard_paste')
    result = illustrate_module.attach(media_settings, course, 'cell_theory', sha256=sha)
    assert result['attached'] is False
    assert result['outcome'] == 'unlicensed'
    assert 'licence gate' in ' '.join(result['notes'])
    assert media.lesson_photograph_blocks(media_settings, 'cell_theory') == []


def test_illustrating_an_offline_instance_is_reported_and_changes_nothing(settings, monkeypatch):
    """No network is a state, not a failure: the textbook publishes, text-only, and says so."""
    from dataclasses import replace

    from app.harness import media

    def _forbidden(*args, **kwargs):
        raise AssertionError('a disabled instance reached for the network')

    monkeypatch.setattr(media, '_client', _forbidden)
    monkeypatch.setattr(media, '_download_bytes', _forbidden)
    offline = replace(settings, media_enabled=False)
    course, _ = build()
    illustrated = illustrate_module.illustrate(offline, course)
    assert illustrated.outcome == 'offline'
    assert illustrated.assigned == 0
    assert 'HARNESS_MEDIA_ENABLED' in ' '.join(illustrated.notes)
    assert illustrate_module.coverage(offline, course)['illustrated'] == 0


def test_a_concept_that_finds_nothing_is_reported_rather_than_filled(media_settings, monkeypatch):
    """No placeholder, no generated stand-in: the concept keeps its deterministic figure."""
    from test_image_fetch import _cleared_candidate, _stub_search

    _stub_search(monkeypatch, [_cleared_candidate(licence_code='CC BY-NC 4.0',
                                                  licence_class='cc_by_nc')])
    course, _ = build()
    illustrated = illustrate_module.illustrate(media_settings, course, only=['cell_theory'])
    assert illustrated.outcome == 'refused'
    assert illustrated.assigned == 0
    row = illustrated.concepts[0]
    assert row['assigned'] == 0 and row['why'], 'a concept with no image must say why'
    assert 'licence' in row['why'].lower() or 'rejected' in row['why'].lower()


def test_deleting_a_course_forgets_its_photographs(media_settings, monkeypatch):
    """The image index is keyed by concept and knows nothing about courses.

    Left behind, those rows are a leak *and* a collision: a later course reusing the id
    would inherit photographs nobody chose for it.
    """
    from app.harness import media

    _stub_media(monkeypatch)
    course, _ = build()
    registry.store(media_settings, course)
    illustrate_module.illustrate(media_settings, course, only=['cell_theory'])
    assert media.lesson_image_assignments(media_settings, 'cell_theory')
    assert registry.delete(media_settings, 'cell_biology') is True
    assert media.lesson_image_assignments(media_settings, 'cell_theory') == []


def test_the_tutor_can_create_an_illustrated_textbook_in_one_call(media_settings, monkeypatch):
    """What the agent actually does: author, and the images are already in it."""
    _stub_media(monkeypatch)
    ctx = _Ctx(media_settings, 'teacher')
    result = authoring_tools.author_course(ctx, blueprint_doc(), illustrate=True)
    assert result.ok is True, result.refused
    illustration = result.data['illustration']
    assert illustration['images_attached'] == 9, illustration
    assert illustration['concepts_without_image'] == []

    coverage = authoring_tools.course_images(ctx, 'cell_biology')
    assert coverage.ok is True
    assert coverage.data['illustrated'] == coverage.data['concepts'] == 9
    first = coverage.data['rows'][0]
    assert first['images'][0]['credit'], 'a served image with no credit line'


def test_the_tutor_can_attach_one_chosen_photograph(media_settings, monkeypatch):
    """The move after a search: the tutor has a sha, and pins it next to the definition."""
    _stub_media(monkeypatch)
    ctx = _Ctx(media_settings, 'teacher')
    assert authoring_tools.author_course(ctx, blueprint_doc(),
                                         illustrate=False).ok is True
    found = authoring_tools.attach_lesson_image(ctx, 'cell_biology', 'cell_theory',
                                                query='cell membrane')
    assert found.ok is True, found.refused
    assert found.data['block']['credit']
    assert found.citations and found.citations[0]['licence'] == 'CC BY 4.0'
    # Attaching again at the same position replaces rather than stacks.
    again = authoring_tools.attach_lesson_image(ctx, 'cell_biology', 'cell_theory',
                                                query='cell membrane')
    assert again.ok is True
    assert authoring_tools.course_images(ctx, 'cell_biology').data['rows'][0]['count'] == 1


def test_the_illustration_tools_are_teacher_gated(settings):
    """A learner may be shown a picture; a learner may not publish one into a textbook."""
    learner = _Ctx(settings, 'learner')
    for call in (lambda: authoring_tools.illustrate_course(learner, 'cell_biology'),
                 lambda: authoring_tools.attach_lesson_image(learner, 'cell_biology',
                                                             'cell_theory', query='x')):
        result = call()
        assert result.ok is False
        assert result.refused


def test_http_illustration_reports_what_it_did(media_settings, media_client, monkeypatch):
    """The HTTP surface of the same calls, including the offline report."""
    from dataclasses import replace

    _stub_media(monkeypatch)
    teacher = _teacher(media_client)
    assert media_client.post('/api/v1/author/courses', headers=teacher,
                       json={'blueprint': blueprint_doc(), 'illustrate': False}).status_code == 200
    illustrated = media_client.post('/api/v1/author/courses/cell_biology/illustrate',
                              headers=teacher, json={'limit': 1})
    assert illustrated.status_code == 200, illustrated.text
    body = illustrated.json()
    assert body['outcome'] == 'ok'
    assert body['coverage']['illustrated'] == body['coverage']['concepts']

    images = media_client.get('/api/v1/author/courses/cell_biology/images', headers=teacher)
    assert images.status_code == 200, images.text
    assert images.json()['illustrated'] == 9

    # A learner cannot illustrate, and an unknown concept is a 404 rather than a silent skip.
    learner = _enrol(media_client, 'cell_biology')
    assert media_client.post('/api/v1/author/courses/cell_biology/illustrate',
                       headers=learner, json={}).status_code == 403
    assert media_client.post('/api/v1/author/courses/cell_biology/illustrate', headers=teacher,
                       json={'concept_id': 'no_such_concept'}).status_code == 404


def test_a_concept_with_no_search_hits_is_not_reported_as_a_filter_refusal():
    """Two different facts, two different sentences.

    "The search returned nothing" and "the search returned things we refused" send a
    reviewer to two different places. They used to share one sentence about the licence and
    relevance filter, which was false for the large majority of concepts: for an abstract
    economics title the providers genuinely answered with zero hits, and there was no
    candidate for the filter to have refused.
    """
    from app.harness.authoring import illustrate

    nothing = illustrate._why({'images': [{'outcome': 'no_cleared_candidate', 'seen': 0,
                                          'query': 'Least cost combination of inputs',
                                          'rejections': []}]})
    assert 'returned nothing' in nothing
    assert 'no candidate existed to refuse' in nothing
    assert 'Least cost combination of inputs' in nothing

    refused = illustrate._why({'images': [{
        'outcome': 'no_cleared_candidate', 'seen': 12, 'query': 'Isoquant',
        'rejections': [{'source': 'wikimedia', 'title': 'A cat',
                        'why': 'Licence class cc_by_nc: this project may link to or embed '
                               'the asset but may not cache a copy of it.'}]}]})
    assert 'licence' in refused.lower()
    assert 'refused on licence grounds' in refused

    irrelevant = illustrate._why({'images': [{
        'outcome': 'no_cleared_candidate', 'seen': 40, 'query': 'Monopsony',
        'rejections': [{'source': 'wikimedia', 'title': 'A cat',
                        'why': "Only 0% of the query words appear in the asset's own title"}]}]})
    assert 'none was about' in irrelevant
    assert 'Monopsony' in irrelevant
