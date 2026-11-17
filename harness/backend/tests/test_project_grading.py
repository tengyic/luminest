"""Human rubric scoring for projects: append-only, configured reviewers only."""
import pytest

from test_api import account, client, settings  # noqa: F401
from test_assessment_and_perspectives import project_id_for


def submit(client, headers, level='hints_only'):
    project_id = project_id_for(client, headers, None)
    response = client.post(f'/api/v1/projects/{project_id}/submit', headers=headers, json={
        'text': 'I model the case with units, show the calculation and name an assumption.',
        'ai_disclosure': 'A hint helped me check the units.',
        'reflection': 'I still want a fresh variant to try alone.',
        'assistance_level': level,
    })
    assert response.status_code == 200, response.text
    return project_id, response.json()


def test_project_grading_requires_a_configured_reviewer(client, monkeypatch):
    monkeypatch.setenv('HARNESS_REVIEWERS', 'grader@example.test')
    learner, _ = account(client, 'grade-learner')
    project_id, body = submit(client, learner)
    assert body['assistance_level'] == 'hints_only'
    assert body['rubric_criteria'], 'a rubric must be published before it can be scored'
    refused = client.post(f'/api/v1/projects/{project_id}/grade', headers=learner, json={
        'criteria': [{'criterion_id': c['id'], 'points': c['max_points'], 'rationale': 'Clear.'}
                     for c in body['rubric_criteria']],
        'status': 'graded', 'rationale': 'Complete.',
    })
    assert refused.status_code == 403
    assert 'reviewer' in refused.json()['detail'].casefold()


def test_grade_history_keeps_an_override_and_never_rewrites_formative_feedback(client, monkeypatch):
    monkeypatch.setenv('HARNESS_REVIEWERS', 'grader@example.test')
    learner, _ = account(client, 'grade-owner')
    reviewer, _ = account(client, 'grader')
    project_id, original = submit(client, learner)
    criteria = [{'criterion_id': c['id'], 'points': c['max_points'], 'rationale': 'Evidence is shown.'}
                for c in original['rubric_criteria']]
    first = client.post(f'/api/v1/projects/{project_id}/grade', headers=reviewer,
                        json={'criteria': criteria, 'status': 'graded', 'rationale': 'Meets the rubric.'})
    assert first.status_code == 200, first.text
    graded = first.json()['grade']
    assert graded['total'] == graded['max_total'] and graded['supersedes'] is None
    assert 'accredited' in first.json()['scope']
    revised = client.post(f'/api/v1/projects/{project_id}/grade', headers=reviewer,
                          json={'criteria': [{**c, 'points': 1} for c in criteria],
                                'status': 'needs_revision', 'rationale': 'Needs a fresh example.'})
    assert revised.status_code == 200, revised.text
    assert revised.json()['grade']['supersedes'] == graded['id']
    assert 'Formative rubric checklist' in revised.json()['formative_feedback']
    history = client.get(f'/api/v1/projects/{project_id}/grades', headers=learner).json()['grades']
    assert [row['total'] for row in history] == [graded['total'], revised.json()['grade']['total']]
    assert all(row['reviewer_email'] == 'grader@example.test' for row in history)


def test_grading_rejects_partial_and_out_of_range_rubrics(client, monkeypatch):
    monkeypatch.setenv('HARNESS_REVIEWERS', 'grader@example.test')
    learner, _ = account(client, 'grade-bad')
    reviewer, _ = account(client, 'grader')
    project_id, original = submit(client, learner)
    base = f'/api/v1/projects/{project_id}/grade'
    partial = {'criteria': [{'criterion_id': original['rubric_criteria'][0]['id'],
                             'points': 4, 'rationale': 'Only one.'}],
               'status': 'graded', 'rationale': 'Incomplete.'}
    assert client.post(base, headers=reviewer, json=partial).status_code == 422
    over = {'criteria': [{'criterion_id': c['id'], 'points': 99, 'rationale': 'Too many.'}
                        for c in original['rubric_criteria']],
            'status': 'graded', 'rationale': 'Out of range.'}
    assert client.post(base, headers=reviewer, json=over).status_code == 422
