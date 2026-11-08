"""Answer receipts and personal creation must keep the authenticated boundary intact."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app import courses
from app.curriculum import LESSON_TARGETS, QUESTIONS, course_concepts, course_questions
from app.db import Assessment, Attempt, Receipt, Secret, State, User, now_ts, uid
from app.harness import toolbox
from app.main import harness_context
from test_api import account, answer, client, settings  # noqa: F401


def check(client, user_id, concept_id='fractions', **kwargs):
    with client.app.state.factory() as db:
        user = db.get(User, user_id)
        result = toolbox.invoke(harness_context(db, user, client.app.state.settings),
                                'check_understanding',
                                {'concept_id': concept_id, **kwargs})
        db.commit()
        return result


def receipt_count(client, user_id):
    with client.app.state.factory() as db:
        return db.scalar(select(func.count(Receipt.id)).where(Receipt.user_id == user_id))


@pytest.mark.parametrize('concept_id', ['fractions', LESSON_TARGETS['fractions']])
def test_check_issues_real_answerable_receipt_and_persists_attempt(client, concept_id):
    headers, registered = account(client)
    user_id = registered['user']['id']
    result = check(client, user_id, concept_id)
    assert result.ok, result.to_dict()
    question = result.data['question']
    assert question['receipt'] and question['mode'] == 'practice'
    assert question['options'] and question['concept_id'] == 'fractions'
    assert not {'answer_id', 'answer_text', 'explanation', 'diagnosis', 'correct_answer'} & set(question)
    with client.app.state.factory() as db:
        receipt = db.get(Receipt, question['receipt'].split('.')[0])
        assert receipt.user_id == user_id and not receipt.used
        assert db.scalar(select(func.count(Attempt.id)).where(Attempt.user_id == user_id)) == 0
        assert db.scalar(select(func.count(State.user_id)).where(State.user_id == user_id)) == 0
    response = client.post('/api/v1/attempts', headers=headers, json=answer(question))
    assert response.status_code == 200, response.text
    assert response.json()['correct'] is True
    with client.app.state.factory() as db:
        attempt = db.scalar(select(Attempt).where(Attempt.user_id == user_id))
        assert attempt.question_id == question['id']
        assert attempt.receipt_id == question['receipt'].split('.')[0]
        state = db.scalar(select(State).where(State.user_id == user_id,
                                             State.concept_id == 'fractions'))
        assert state.data['attempts'] == 1
        assert db.get(Receipt, attempt.receipt_id).used


def test_check_receipt_rejects_wrong_user_and_tampering(client):
    headers, registered = account(client, 'first-check')
    other_headers, other = account(client, 'other-check')
    question = check(client, registered['user']['id']).data['question']
    assert client.post('/api/v1/attempts', headers=other_headers,
                       json=answer(question)).status_code == 400
    bad = answer(question)
    bad['receipt'] += 'bad-signature'
    assert client.post('/api/v1/attempts', headers=headers, json=bad).status_code == 400
    with client.app.state.factory() as db:
        for user_id in [registered['user']['id'], other['user']['id']]:
            assert db.scalar(select(func.count(Attempt.id)).where(Attempt.user_id == user_id)) == 0


def test_check_resolves_enrollment_not_context_graph(client):
    headers, registered = account(client)
    user_id = registered['user']['id']
    selected = 'physics'
    with client.app.state.factory() as db:
        user = db.get(User, user_id)
        user.course_id = selected
        db.commit()
    question = next(iter(course_questions(selected).values()))
    result = check(client, user_id, question['concept_id'])
    assert result.ok, result.to_dict()
    assert result.data['question']['id'] in course_questions(selected)
    assert client.post('/api/v1/attempts', headers=headers,
                       json=answer(result.data['question'])).status_code == 200
    before = receipt_count(client, user_id)
    refused = check(client, user_id, 'fractions')
    assert not refused.ok and 'enrolled course' in refused.refused
    assert receipt_count(client, user_id) == before
    with client.app.state.factory() as db:
        user = db.get(User, user_id)
        mismatched = toolbox.ToolContext(db=db, user=user, settings=client.app.state.settings,
                                          course_id=courses.DEFAULT_COURSE_ID)
        result = toolbox.check_understanding(mismatched, question['concept_id'])
        assert not result.ok and 'enrollment' in result.refused


def test_check_exclusions_choose_alternate_question(client):
    _, registered = account(client)
    user_id = registered['user']['id']
    first = check(client, user_id).data['question']
    second = check(client, user_id, exclude=[first['id']]).data['question']
    assert second['id'] != first['id']


def test_check_active_exam_refuses_issue_and_practice_submission(client):
    headers, registered = account(client)
    user_id = registered['user']['id']
    question = check(client, user_id).data['question']
    with client.app.state.factory() as db:
        db.add(Assessment(id=uid(), user_id=user_id, mode='exam', total=10,
                          created_at=now_ts(), expires_at=now_ts() + 3600))
        db.commit()
    before = receipt_count(client, user_id)
    refused = check(client, user_id)
    assert not refused.ok and 'active exam' in refused.refused
    assert receipt_count(client, user_id) == before
    response = client.post('/api/v1/attempts', headers=headers, json=answer(question))
    assert response.status_code == 403, response.text
    with client.app.state.factory() as db:
        assert db.scalar(select(func.count(Attempt.id)).where(Attempt.user_id == user_id)) == 0
        assert not db.get(Receipt, question['receipt'].split('.')[0]).used


@pytest.mark.parametrize('missing', ['db', 'user', 'settings'])
def test_check_without_runtime_explicitly_refuses(client, missing):
    _, registered = account(client)
    with client.app.state.factory() as db:
        ctx = harness_context(db, db.get(User, registered['user']['id']), client.app.state.settings)
        setattr(ctx, missing, None)
        result = toolbox.check_understanding(ctx, 'fractions')
        assert not result.ok and 'required' in result.refused
        assert result.data is None


def test_check_without_signing_storage_refuses_without_initializing(client):
    _, registered = account(client)
    with client.app.state.factory() as db:
        row = db.get(Secret, 'receipt')
        db.delete(row)
        db.commit()
        result = toolbox.check_understanding(harness_context(
            db, db.get(User, registered['user']['id']), client.app.state.settings), 'fractions')
        assert not result.ok and 'signing is unavailable' in result.refused
        assert db.get(Secret, 'receipt') is None
        assert not db.new


def test_check_inactive_account_and_unknown_enrollment_fail_closed(client):
    _, registered = account(client)
    user_id = registered['user']['id']
    with client.app.state.factory() as db:
        user = db.get(User, user_id)
        user.status = 'suspended'
        db.commit()
    assert 'Account unavailable' in check(client, user_id).refused
    with client.app.state.factory() as db:
        user = db.get(User, user_id)
        user.status = 'active'
        user.course_id = 'does-not-exist'
        db.commit()
    result = check(client, user_id)
    assert not result.ok and 'enrolled course is unavailable' in result.refused
    assert receipt_count(client, user_id) == 0


@pytest.mark.parametrize('route', ['/api/v1/author/preview', '/api/v1/author/courses'])
def test_learner_can_build_own_preview_without_global_publication(client, route):
    from app.harness.authoring import registry
    from test_authoring import blueprint_doc

    headers, registered = account(client)
    body = {'blueprint': blueprint_doc(), 'save': False, 'illustrate': False,
            'replace': True, 'role': 'admin', 'owner_id': 'another-user'}
    response = client.post(route, headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()['ok'] and response.json()['stored'] is False
    assert registry.get('cell_biology') is None
    assert 'cell_biology' not in courses.COURSE_BY_ID
    with client.app.state.factory() as db:
        assert db.get(User, registered['user']['id']).role == 'learner'
    assert client.post(route, json=body).status_code == 401


@pytest.mark.parametrize('method,path,body', [
    ('post', '/api/v1/author/courses', {'blueprint': {}}),
    ('post', '/api/v1/author/draft', {'topic': 'Cell biology'}),
    ('get', '/api/v1/author/courses', None),
    ('get', '/api/v1/author/courses/other-author/blueprint', None),
    ('post', '/api/v1/author/courses/other-author/units', {'unit': {}}),
    ('post', '/api/v1/author/courses/other-author/rebuild', None),
    ('post', '/api/v1/author/courses/other-author/illustrate', {}),
    ('delete', '/api/v1/author/courses/other-author', None),
])
def test_learner_personal_authoring_does_not_grant_global_admin_operations(
        client, method, path, body):
    headers, _ = account(client)
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 403, response.text


def test_personal_draft_preserves_provider_absence_and_exam_gate(client):
    headers, registered = account(client)
    body = {'topic': 'Cell biology', 'save': False, 'illustrate': False}
    response = client.post('/api/v1/author/draft', headers=headers, json=body)
    assert response.status_code == 503, response.text
    assert response.json()['detail']['code'] == 'no_model'
    with client.app.state.factory() as db:
        db.add(Assessment(user_id=registered['user']['id'], mode='exam', total=10,
                          expires_at=now_ts() + 3600))
        db.commit()
    for path, payload in [('/api/v1/author/draft', body),
                          ('/api/v1/author/preview', {'blueprint': {}}),
                          ('/api/v1/author/courses', {'blueprint': {}, 'save': False})]:
        response = client.post(path, headers=headers, json=payload)
        assert response.status_code == 403, response.text
        assert 'active exam' in response.json()['detail']


def test_learner_personal_compose_and_board_scope_not_role_promotion(client):
    headers, registered = account(client, 'board-owner')
    other_headers, other = account(client, 'board-other')
    created = client.post('/api/v1/boards', headers=headers, json={'title': 'Own learning'})
    assert created.status_code == 201, created.text
    board_id = created.json()['board']['id']
    mutation = {'board_id': board_id, 'mutations': [
        {'action': 'add', 'node': {'kind': 'text', 'x': 0, 'y': 0,
                                 'payload': {'text': 'My own notes'}}}]}
    with client.app.state.factory() as db:
        ctx = harness_context(db, db.get(User, registered['user']['id']), client.app.state.settings)
        assert toolbox.invoke(ctx, 'compose_content',
                              {'concept_id': 'fractions', 'kind': 'explanation'}).ok
        assert toolbox.invoke(ctx, 'board_apply', mutation).ok
        ctx.user = db.get(User, other['user']['id'])
        assert not toolbox.invoke(ctx, 'board_apply', mutation).ok
        assert not toolbox.invoke(ctx, 'board_read', {'board_id': board_id}).ok
        assert ctx.user.role == 'learner'
    assert client.get(f'/api/v1/boards/{board_id}', headers=other_headers).status_code == 404


def test_learner_media_and_voice_keep_disabled_provider_flags(client):
    _, registered = account(client)
    with client.app.state.factory() as db:
        ctx = harness_context(db, db.get(User, registered['user']['id']), client.app.state.settings)
        ctx.settings = replace(ctx.settings, media_enabled=False, voice_enabled=False)
        for tool, args, flag in [
                ('image_generate', {'prompt': 'An illustration of a cell'}, 'HARNESS_MEDIA_ENABLED'),
                ('text_to_speech', {'text': 'Here is a fraction.'}, 'HARNESS_VOICE_ENABLED')]:
            result = toolbox.invoke(ctx, tool, args)
            assert not result.ok and flag in result.refused
            assert 'teacher-facing' not in result.refused
        assert ctx.user.role == 'learner'
