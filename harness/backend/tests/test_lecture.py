"""The 45-minute auto-lecture: storyboard, board pages and media refusals."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def lecture_client(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    # The storyboard and the board are the contract here. Media is exercised as a refusal
    # path: no network, no downloaded file, but the lecture still returns a reference card.
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '0')
    # No VoiceStudio on the test machine: these tests are about the storyboard and the clip
    # *plan*, so the engine is stubbed and a refusal is a legitimate answer here.
    monkeypatch.setenv('HARNESS_VOICE_BASE_URL', 'http://127.0.0.1:9')
    with TestClient(create_app(Settings.from_env())) as client:
        yield client


def _account(client):
    response = client.post('/api/v1/auth/register', json={
        'name': 'lecture', 'email': 'lecture@example.test',
        'password': 'long-secret-password',
    })
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_the_lecture_compiles_to_the_requested_length(lecture_client):
    headers = _account(lecture_client)
    response = lecture_client.get('/api/v1/lecture/fractions?minutes=45', headers=headers)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan['source'] == 'deterministic-fallback'
    assert len(plan['segments']) >= 9
    assert sum(s['duration_seconds'] for s in plan['segments']) == 45 * 60
    assert all(s['narration'].strip() for s in plan['segments'])
    assert all(s['board_ops'] for s in plan['segments'])
    kinds = {s['media']['kind'] for s in plan['segments']}
    assert 'image' in kinds, 'the lecture must have at least one image slot'
    assert 'video' in kinds, 'the lecture must have at least one video slot'


def test_a_longer_lecture_is_longer_rather_than_the_same_nine_pages_stretched(lecture_client):
    """Length is a promise about how much is *taught*, not about how long the clock runs.

    The deterministic storyboard used to emit its nine fixed pages for every ``minutes``,
    so a 45-minute lecture and a 5-minute one were the same words with a longer pause
    between them: the learner was told they were being taught for 45 minutes and heard
    about nine short paragraphs. Speech time must therefore grow with the request.
    """
    headers = _account(lecture_client)
    short = lecture_client.get('/api/v1/lecture/fractions?minutes=5', headers=headers).json()
    long = lecture_client.get('/api/v1/lecture/fractions?minutes=45', headers=headers).json()
    assert long['source'] == short['source'] == 'deterministic-fallback'
    short_speech = sum(s['speech_seconds'] for s in short['segments'])
    long_speech = sum(s['speech_seconds'] for s in long['segments'])
    assert long_speech > short_speech * 2, (
        f'45 minutes spoke {long_speech}s against {short_speech}s for 5 minutes; the '
        f'page count did not follow the request')
    assert len(long['segments']) > len(short['segments'])
    assert sum(s['duration_seconds'] for s in long['segments']) == 45 * 60
    # A request shorter than the nine pages it must still carry is as long as those pages
    # take; the plan reports the real figure rather than claiming a 5-minute lecture.
    assert sum(s['duration_seconds'] for s in short['segments']) >= 5 * 60
    titles = [s['title'] for s in long['segments']]
    assert len(titles) == len(set(titles)), 'two pages of one lecture must not share a title'


def test_starting_the_lecture_draws_the_first_page_on_the_stage_board(lecture_client):
    headers = _account(lecture_client)
    started = lecture_client.post('/api/v1/lecture/fractions/start', headers=headers)
    assert started.status_code == 200, started.text
    body = started.json()
    # The Stage binds ``board-<concept>``; resolving ``fractions`` to a graph node must not
    # move the lecture onto a different document.
    assert body['board_id'] == 'board-fractions'
    assert body['board_version'] >= 1

    segment = lecture_client.post('/api/v1/lecture/fractions/segment/0', headers=headers)
    assert segment.status_code == 200, segment.text
    payload = segment.json()
    assert payload['index'] == 0
    assert payload['board_id'] == 'board-fractions'
    assert payload['board_version'] > body['board_version']

    board = lecture_client.get('/api/v1/boards/board-fractions', headers=headers)
    assert board.status_code == 200, board.text
    nodes = board.json()['board']['nodes']
    assert len(nodes) >= 5
    assert {node['kind'] for node in nodes} & {'text', 'shape', 'path'}


def test_a_lecture_page_carries_speech_from_the_tutor_voice_not_the_device(lecture_client, monkeypatch):
    """One voice across the product.

    The lecture player used the Mac's own synthesiser, so a lesson sounded like a
    different teacher from the one who had just answered in chat. The page must now carry
    the same clip queue the tutor speaks with; the client is free to fall back on-device
    only when this queue is empty.
    """
    from app.harness import speech

    monkeypatch.setattr(speech.voice_backend, 'synthesize',
                        lambda settings, text, **kwargs: b'ID3fee-eff-eff')
    headers = _account(lecture_client)
    response = lecture_client.post('/api/v1/lecture/fractions/segment/0', headers=headers)
    assert response.status_code == 200, response.text
    plan = response.json()['speech']
    assert plan.get('clips'), 'a page with narration must be queued for speech'
    assert plan['clips'][0]['digest'], plan
    # The descriptor is a plan, not a recording: the page cannot wait on a render.
    assert plan['state'] in ('pending', 'ready')


def test_read_aloud_can_answer_with_a_clip_plan_instead_of_waiting(lecture_client):
    """``wait=false`` is what lets a player start on the first sentence.

    The blocking shape stays the default so every existing caller is unchanged.
    """
    headers = _account(lecture_client)
    waiting = lecture_client.post('/api/v1/voice/speak',
                                  json={'text': 'Fractions are equal parts.'}, headers=headers)
    assert waiting.status_code == 503, 'no VoiceStudio in this test: honest refusal'
    quick = lecture_client.post('/api/v1/voice/speak',
                                json={'text': 'Fractions are equal parts.', 'wait': False},
                                headers=headers)
    assert quick.status_code == 200, quick.text
    body = quick.json()
    assert 'clips' in body, body
    # ``pending`` is the honest answer even with no engine: the plan is made up front and
    # the failure arrives as the clip's outcome, so the button can show "preparing" now and
    # the engine's own sentence a moment later, rather than freezing on a 20 s request.
    assert body.get('state') == 'pending', body
    digest = body['clips'][0]['digest']
    for _ in range(200):
        state = lecture_client.get(f'/api/v1/media/audio/{digest}/state',
                                   headers=headers).json()
        if state.get('state') not in ('pending', 'unknown'):
            break
    assert state.get('state') == 'failed', state
    assert state.get('reason'), 'a refusal without a sentence is a silent button'


def test_a_segment_with_media_returns_a_reference_instead_of_faking_an_asset(lecture_client):
    headers = _account(lecture_client)
    segment = lecture_client.post('/api/v1/lecture/fractions/segment/1', headers=headers)
    assert segment.status_code == 200, segment.text
    media = segment.json()['media']
    # With network media off the endpoint must say so, not manufacture an image or crash.
    assert media['kind'] in {'image_reference', 'none', 'image'}
    assert 'asset' not in media or media.get('kind') == 'image'
    if media['kind'] == 'image_reference':
        assert 'licence' in media.get('note', '').lower() or media.get('references') == []


def test_the_board_id_regex_accepts_both_canvas_and_tutor_spellings():
    import re

    pattern = re.compile(r'(?:wb|board)-[a-z0-9_.-]{1,72}')
    assert pattern.fullmatch('wb-fractions')
    assert pattern.fullmatch('board-fractions')
    assert not pattern.fullmatch('fractions')
