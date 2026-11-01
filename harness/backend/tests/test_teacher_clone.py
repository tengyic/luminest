from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import courses, teacher_clone, tutor
from app.config import Settings
from app.db import Message
from app.main import create_app


TRANSCRIPT = (
    "First, try this problem yourself. What do you notice? Let's work through it one step at a time. "
    "Good question. Next, explain why that step keeps both sides equal. Finally, check your answer. "
    "This short transcript contains enough words to meet the analysis endpoint's minimum length."
)


def test_normalize_profile_requires_verbatim_evidence():
    raw = {
        'methodology': [
            {'claim': 'Invites the learner to attempt the problem first.',
             'evidence_quote': 'try this problem yourself'},
            {'claim': 'Uses a flipped classroom and group projects.',
             'evidence_quote': 'not in the transcript'},
        ],
        'teaching_style': [{'claim': 'Uses stepwise scaffolding.',
                            'evidence_quote': 'one step at a time'}],
        'content_procedure': [],
        'interaction_prompts': [],
        'tone': [],
        'uncertainties': ['Acoustic voice cannot be inferred.'],
    }
    result = teacher_clone.normalize_profile(raw, TRANSCRIPT)
    assert result['methodology'] == [raw['methodology'][0]]
    assert result['teaching_style'] == raw['teaching_style']
    assert result['content_procedure'] == []
    assert result['uncertainties'] == ['Acoustic voice cannot be inferred.']


def test_invalid_model_output_uses_bounded_offline_signals(monkeypatch):
    monkeypatch.setattr(teacher_clone.provider, 'chat_json', lambda *args, **kwargs: {
        'methodology': [{'claim': 'unsupported', 'evidence_quote': 'invented words'}],
        'teaching_style': [], 'content_procedure': [], 'interaction_prompts': [], 'tone': [],
    })
    result = teacher_clone.analyze(None, TRANSCRIPT)
    assert result['analysis_mode'] == 'offline_heuristic_review_required'
    assert result['review_required'] is True
    assert result['transcript_retention'] == 'not_saved'
    assert result['profile']['methodology']
    assert result['profile']['interaction_prompts']
    assert all(item['evidence_quote'].casefold() in TRANSCRIPT.casefold()
               for values in result['profile'].values() if isinstance(values, list)
               for item in values if isinstance(item, dict))
    assert result['tutor_profile']['methodology']


def test_profile_limits_and_consent_gate(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    settings = Settings.from_env()
    with TestClient(create_app(settings)) as client:
        registered = client.post('/api/v1/auth/register', json={
            'name': 'teacher', 'email': 'teacher@example.test', 'password': 'long-secret-password',
        }).json()
        headers = {'Authorization': 'Bearer ' + registered['token']}
        payload = {
            'transcript': TRANSCRIPT,
            'authorization': 'self',
            'student_identifiers_removed': True,
            'ai_processing_confirmed': True,
        }
        assert client.post('/api/v1/teacher-profiles/analyze', json=payload).status_code == 401
        privacy_denied = client.post('/api/v1/teacher-profiles/analyze', headers=headers,
                                     json={**payload, 'student_identifiers_removed': False})
        assert privacy_denied.status_code == 422
        denied = client.post('/api/v1/teacher-profiles/analyze', headers=headers,
                             json={**payload, 'ai_processing_confirmed': False})
        assert denied.status_code == 422
        result = client.post('/api/v1/teacher-profiles/analyze', headers=headers, json=payload)
        assert result.status_code == 200, result.text
        body = result.json()
        assert body['authorization_basis'] == 'self'
        assert body['transcript_retention'] == 'not_saved'
        assert 'processed locally' in body['processing_notice']
        assert body['tutor_profile']['methodology']

        chat = client.post('/api/v1/chat', headers=headers, json={
            'concept_id': 'fractions',
            'message': 'Can you help me add these fractions?',
            'teacher_profile': {
                'methodology': ['Ask me to predict before revealing the answer.'],
                'teaching_style': ['Supportive and patient.'],
                'content_procedure': [],
                'interaction_prompts': [],
                'tone': ['Warm and encouraging.'],
            },
        })
        assert chat.status_code == 200, chat.text
        assert chat.json()['content'].startswith('We can work through this one step at a time.')
        assert client.get('/api/v1/chat', headers=headers,
                          params={'concept_id': 'fractions'}).status_code == 200
        with client.app.state.factory() as db:
            rows = list(db.query(Message).where(Message.user_id == registered['user']['id']).all())
            assert len(rows) == 2
            assert all(TRANSCRIPT not in row.content for row in rows)


def test_generated_course_map_lesson_is_taught_with_its_limits_named(tmp_path, monkeypatch):
    """A generated lesson is real course content, so it is taught — not refused.

    It carries a summary, a placement note, a retrieval check and a reflection prompt,
    but no worked example. The answer must teach from those blocks and say plainly what
    is missing, because the requested courses are all generated lessons.
    """
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    settings = Settings.from_env()
    node = courses.graph_for('biology').nodes['active_transport'].to_dict()
    text, provider, grounding, _ = tutor.respond(
        settings, 'active_transport', 'Please explain active transport in detail.', [],
        retrieval_context={'node': node, 'prerequisites': [], 'dependants': []})
    assert provider == 'Grounded offline tutor'
    assert 'course-map lesson' in text
    assert 'Active transport' in text
    assert 'no worked example' in text
    assert 'orientation only' not in text
    assert grounding[0]['title'].startswith('Generated course-map lesson:')


def test_concept_with_no_lesson_gets_orientation_only(tmp_path, monkeypatch):
    """The one case that still refuses: a concept with no lesson record at all."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    settings = Settings.from_env()
    text, provider, grounding, _ = tutor.respond(
        settings, 'no_such_concept_at_all', 'Explain this.', [],
        retrieval_context={'node': {'title': 'Ghost concept', 'unit': 'Nowhere',
                                    'summary': 'A graph summary that is not a lesson.'},
                           'prerequisites': [], 'dependants': []})
    assert provider == 'Grounded offline tutor'
    assert 'course-map orientation only' in text
    assert 'Ghost concept' in text
    assert 'will not invent' in text
    assert grounding[0]['title'].startswith('Course concept map:')


def test_transcript_length_is_checked():
    with pytest.raises(ValueError, match='100-40000'):
        teacher_clone.analyze(None, 'short')
