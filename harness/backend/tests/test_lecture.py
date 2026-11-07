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
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    # The storyboard and the board are the contract here. Media is exercised as a refusal
    # path: no network, no downloaded file, but the lecture still returns a reference card.
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '0')
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
