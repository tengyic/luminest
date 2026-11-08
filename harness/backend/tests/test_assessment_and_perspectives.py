"""Unit grade book and multi-perspective evidence: real scores, honest absences.

The November 8 audit named both as missing. These tests pin the part that is easy to
fake: a dimension with no evidence must be ``null`` rather than 0, a unit with an
unevidenced standard must have no grade at all, and a score may only be attached to an
artifact that exists. Foreground activity is never allowed to stand in for a judgement.
"""
import pytest
from sqlalchemy import func, select

from app import assessment_book, courses, perspectives
from app.db import (Attempt, Project, Receipt, State, User, now_ts, uid)
from test_api import account, client, settings  # noqa: F401


def seed_attempts(client, user_id, concept_ids, per_concept=2, correct=True):
    """Insert server-graded attempts on the given concepts, with their receipt anchors."""
    with client.app.state.factory() as db:
        for index, concept_id in enumerate(concept_ids):
            for n in range(per_concept):
                receipt = Receipt(id=uid(), user_id=user_id,
                                  question_id=f'seed-{concept_id}-{n}', mode='practice',
                                  expires_at=now_ts() + 600, used=True)
                db.add(receipt)
                db.flush()  # the attempt's FK needs the receipt row to exist first
                db.add(Attempt(id=uid(), user_id=user_id, receipt_id=receipt.id,
                               client_event_id=f'seed-{concept_id}-{index}-{n}',
                               question_id=receipt.question_id, concept_id=concept_id,
                               mode='practice', correct=correct if n % 2 == 0 else not correct,
                               elapsed_seconds=4.0, confidence=0.7, category='conceptual',
                               payload={'reasoning': 'I checked the units.'},
                               payload_hash=f'seed-hash-{concept_id}-{n}',
                               response={'option_id': 'a'}, created_at=now_ts() + n))
        db.commit()


def first_unit(client, user_id):
    graph = courses.graph_for(courses.DEFAULT_COURSE_ID)
    units = assessment_book.units_of(graph)
    assert units, 'the default course must declare at least one unit'
    return units[0]


def all_concept_ids(units):
    return [cid for unit in units for standard in unit['standards']
            for cid in standard['aliases']]


def project_id_for(client, headers, user_id):
    response = client.get('/api/v1/projects', headers=headers)
    assert response.status_code == 200, response.text
    items = response.json()['items']
    assert items, 'the projects surface must materialise a real artifact'
    return items[0]['id']


# --------------------------------------------------------------------------- grade book


def test_gradebook_declares_standards_and_refuses_a_grade_without_evidence(client):
    headers, registered = account(client, 'grade-empty')
    user_id = registered['user']['id']
    response = client.get('/api/v1/gradebook', headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['units'] and body['scope_note']
    assert 'accredited' in body['scope_note']
    unit = body['units'][0]
    assert unit['standards'] and unit['percent'] is None and unit['gradeable'] is False
    assert unit['missing'] and all(s['score'] is None for s in unit['standards'])
    assert all(s['status'] == 'insufficient_evidence' for s in unit['standards'])
    refused = client.post(f"/api/v1/gradebook/{unit['key']}/grade", headers=headers)
    assert refused.status_code == 409, refused.text
    assert refused.json()['detail']['missing_standards']


def test_gradebook_finalises_only_when_every_declared_standard_has_evidence(client):
    headers, registered = account(client, 'grade-full')
    user_id = registered['user']['id']
    units = assessment_book.units_of(courses.graph_for(courses.DEFAULT_COURSE_ID))
    # Seed only one standard, then prove the unit still has no grade.
    target = units[0]
    seed_attempts(client, user_id, target['standards'][0]['aliases'], per_concept=2)
    partial = client.get(f"/api/v1/gradebook/{target['key']}", headers=headers).json()
    assert any(s['score'] is not None for s in partial['standards'])
    if len(target['standards']) > 1:
        assert partial['gradeable'] is False and partial['percent'] is None
        assert client.post(f"/api/v1/gradebook/{target['key']}/grade",
                          headers=headers).status_code == 409
    # Now evidence every standard in that unit.
    for standard in target['standards'][1:]:
        seed_attempts(client, user_id, standard['aliases'], per_concept=2)
    complete = client.get(f"/api/v1/gradebook/{target['key']}", headers=headers).json()
    assert complete['gradeable'] is True and complete['percent'] is not None
    assert complete['standards_total'] == len(target['standards'])
    graded = client.post(f"/api/v1/gradebook/{target['key']}/grade", headers=headers)
    assert graded.status_code == 200, graded.text
    grade = graded.json()
    assert grade['status'] == 'final' and grade['max_score'] == grade['attempts']
    assert grade['standards'] and 'accredited' in grade['scope_note']
    stored = client.get('/api/v1/gradebook', headers=headers).json()['units'][0]
    assert stored['grade']['id'] == grade['id']
    with client.app.state.factory() as db:
        assert db.scalar(select(func.count(assessment_book.UnitGrade.id)).where(
            assessment_book.UnitGrade.user_id == user_id)) == 1
    # Re-grading is an update, never a second contradictory row.
    again = client.post(f"/api/v1/gradebook/{target['key']}/grade", headers=headers)
    assert again.status_code == 200 and again.json()['id'] == grade['id']


def test_gradebook_detail_is_scoped_to_the_enrolled_course(client):
    headers, _ = account(client, 'grade-scope')
    assert client.get('/api/v1/gradebook/not-a-real-unit', headers=headers).status_code == 404


# --------------------------------------------------------------------------- perspectives


def test_empty_perspectives_are_absent_not_zero(client):
    headers, _ = account(client, 'persp-empty')
    body = client.get('/api/v1/perspectives', headers=headers).json()
    assert len(body['dimensions']) == len(perspectives.DIMENSIONS)
    assert all(row['value'] is None for row in body['dimensions'])
    assert {row['code'] for row in body['dimensions']} == set(perspectives.CODES)
    collaboration = next(r for r in body['dimensions'] if r['code'] == 'collaboration')
    assert collaboration['status'] == 'not_measured'
    definitions = client.get('/api/v1/perspectives/dimensions', headers=headers).json()
    assert 'privacy' in definitions and 'accreditation' in definitions
    assert definitions['scale']['max'] == 4
    # Analytics must carry the same rows, and cognitive attention stays last with no value.
    analytics = client.get('/api/v1/analytics', headers=headers).json()
    assert analytics['dimensions'][-1]['name'] == 'Cognitive attention'
    assert analytics['dimensions'][-1]['value'] is None
    codes = {row.get('code') for row in analytics['dimensions']}
    assert set(perspectives.CODES) <= codes


def test_self_review_needs_a_real_artifact_and_written_evidence(client):
    headers, registered = account(client, 'persp-self')
    user_id = registered['user']['id']
    pid = project_id_for(client, headers, user_id)
    base = {'subject_id': user_id, 'artifact_type': 'project', 'artifact_id': pid,
            'dimension': 'communication', 'score': 3,
            'evidence_note': 'The explanation defined each quantity before using it.'}
    assert client.post('/api/v1/perspectives/reviews', headers=headers,
                       json=base | {'evidence_note': 'ok'}).status_code == 422
    assert client.post('/api/v1/perspectives/reviews', headers=headers,
                       json=base | {'artifact_id': 'invented'}).status_code == 422
    assert client.post('/api/v1/perspectives/reviews', headers=headers,
                       json=base | {'dimension': 'intelligence'}).status_code == 422
    created = client.post('/api/v1/perspectives/reviews', headers=headers, json=base)
    assert created.status_code == 200, created.text
    body = client.get('/api/v1/perspectives', headers=headers).json()
    row = next(r for r in body['dimensions'] if r['code'] == 'communication')
    assert row['value'] == 0.75 and row['status'] == 'observed'
    assert body['reviews'][0]['reviewer_role'] == 'self'
    # One reviewer, one dimension, one artifact: re-scoring updates rather than stacking.
    updated = client.post('/api/v1/perspectives/reviews', headers=headers,
                          json=base | {'score': 1})
    assert updated.status_code == 200 and updated.json()['id'] == created.json()['id']
    assert len(client.get('/api/v1/perspectives', headers=headers).json()['reviews']) == 1
    withdrawn = client.delete(f"/api/v1/perspectives/reviews/{created.json()['id']}",
                              headers=headers)
    assert withdrawn.status_code == 200
    assert client.get('/api/v1/perspectives', headers=headers).json()['reviews'] == []


def test_a_learner_cannot_score_another_learners_work(client):
    headers, me = account(client, 'persp-me')
    other_headers, other = account(client, 'persp-other')
    pid = project_id_for(client, other_headers, other['user']['id'])
    payload = {'subject_id': other['user']['id'], 'artifact_type': 'project',
               'artifact_id': pid, 'dimension': 'creativity', 'score': 4,
               'evidence_note': 'Tried an independent representation before the formula.'}
    assert client.post('/api/v1/perspectives/reviews', headers=headers,
                       json=payload | {'reviewer_role': 'self'}).status_code == 422
    assert client.post('/api/v1/perspectives/reviews', headers=headers,
                       json=payload | {'reviewer_role': 'teacher'}).status_code == 422
    with client.app.state.factory() as db:
        assert db.scalar(select(func.count(perspectives.PerspectiveReview.id)).where(
            perspectives.PerspectiveReview.user_id == other['user']['id'])) == 0


def test_collaboration_requires_a_real_group_observation_by_a_teacher(client):
    teacher_headers, teacher = account(client, 'persp-teacher')
    learner_headers, learner = account(client, 'persp-learner')
    with client.app.state.factory() as db:
        db.get(User, teacher['user']['id']).role = 'teacher'
        db.commit()
    pid = project_id_for(client, learner_headers, learner['user']['id'])
    base = {'subject_id': learner['user']['id'], 'artifact_type': 'group_project',
            'artifact_id': pid, 'dimension': 'collaboration', 'score': 3,
            'evidence_note': 'Led the group check and reconciled two conflicting results.',
            'reviewer_role': 'peer'}
    assert client.post('/api/v1/perspectives/reviews', headers=teacher_headers,
                       json=base).status_code == 422  # no group_size
    assert client.post('/api/v1/perspectives/reviews', headers=teacher_headers,
                       json=base | {'group_size': 2, 'artifact_type': 'project'}).status_code == 422
    ok = client.post('/api/v1/perspectives/reviews', headers=teacher_headers,
                     json=base | {'group_size': 3})
    assert ok.status_code == 200, ok.text
    mine = client.get('/api/v1/perspectives', headers=learner_headers).json()
    collaboration = next(r for r in mine['dimensions'] if r['code'] == 'collaboration')
    assert collaboration['value'] == 0.75 and collaboration['status'] == 'observed'
    # The subject sees the observation; the teacher's own view must stay empty.
    assert client.get('/api/v1/perspectives', headers=teacher_headers).json()['reviews'] == []


def test_new_records_are_exported_and_erased_with_the_account(client):
    headers, registered = account(client, 'persp-erase')
    user_id = registered['user']['id']
    pid = project_id_for(client, headers, user_id)
    client.post('/api/v1/perspectives/reviews', headers=headers, json={
        'subject_id': user_id, 'artifact_type': 'project', 'artifact_id': pid,
        'dimension': 'soft_skills', 'score': 2,
        'evidence_note': 'Revised the method after reading the worked example again.'})
    export = client.get('/api/v1/export', headers=headers)
    assert export.status_code == 200, export.text
    assert len(export.json()['perspective_reviews']) == 1
    assert 'unit_grades' in export.json()
    deleted = client.request('DELETE', '/api/v1/me', headers=headers,
                             json={'confirmation': 'DELETE MY ACCOUNT'})
    assert deleted.status_code == 204, deleted.text
    with client.app.state.factory() as db:
        assert db.scalar(select(func.count(perspectives.PerspectiveReview.id)).where(
            perspectives.PerspectiveReview.user_id == user_id)) == 0
