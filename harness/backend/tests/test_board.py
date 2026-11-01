"""Tests for the interactive board: node store, licence rollup, export, share.

Written around the guarantees the module claims, not around its internals. Where a
claim is a refusal — a stale write, a non-owner, a status upgrade, a fabricated
media payload — the test asserts the refusal, because a gate that is never
exercised is a gate that has quietly stopped working. None of these tests need
the network.
"""

import base64
import json

import pytest

from app.harness import board as node_boards
from app.harness import media
from test_api import settings  # noqa: F401 - fixture


@pytest.fixture
def board(settings):
    return node_boards.create(settings, owner_id='user-1', title='Algebra board')


# --------------------------------------------------------------------------- z order

def test_between_orders_and_is_strict():
    assert node_boards._val(node_boards.between('', '1'), 2) < node_boards._val('1', 2)
    assert node_boards._val(node_boards.between('1', '3'), 2) == node_boards._val('2', 2)
    mid = node_boards.between('a1', 'a2')
    assert node_boards._val('a1', len(mid)) < node_boards._val(mid, len(mid)) < node_boards._val('a2', len(mid))
    above = node_boards.between('zz', '')
    assert above > 'zz'


def test_between_refuses_impossible_interval():
    assert node_boards.between('5', '3') is None
    assert node_boards.between('same', 'same') is None


def test_top_z_places_new_nodes_above_existing():
    nodes = [{'id': 'a', 'z': '1V'}, {'id': 'b', 'z': '2V'}]
    z = node_boards.top_z(nodes)
    assert node_boards._val(z, len(z) + 2) > node_boards._val('2V', len(z) + 2)


# --------------------------------------------------------------------------- store

def test_create_and_load_roundtrip(settings, board):
    doc = node_boards.load_owned(settings, board['id'], 'user-1')
    assert doc['title'] == 'Algebra board'
    assert doc['owner_id'] == 'user-1'
    assert doc['nodes'] == []
    # A non-owner gets the same response as a missing board: nothing exists for them.
    assert node_boards.load_owned(settings, board['id'], 'user-2') is None


def test_add_move_update_delete_batch(settings, board):
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[
            {'action': 'add', 'node': {'kind': 'text', 'x': 10, 'y': 20,
                                       'payload': {'text': 'slope = rise / run'}}},
            {'action': 'add', 'node': {'kind': 'path', 'x': 0, 'y': 0,
                                       'payload': {'points': [[0, 0], [10, 10], [20, 5]],
                                                   'colour': '#123456', 'width': 2}}},
        ])
    assert reason == '' and len(doc['nodes']) == 2
    text_node = next(n for n in doc['nodes'] if n['kind'] == 'text')
    assert text_node['id'] and text_node['z'] and text_node['author'] == 'user-1'
    version = doc['version']
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=version,
        mutations=[{'action': 'move', 'id': text_node['id'], 'x': 40, 'y': 50}])
    assert reason == '' and doc['version'] == version + 1
    assert next(n for n in doc['nodes'] if n['id'] == text_node['id'])['x'] == 40
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=doc['version'],
        mutations=[{'action': 'delete', 'id': text_node['id']}])
    assert reason == '' and len(doc['nodes']) == 1


def test_stale_base_version_is_a_conflict_not_a_stomp(settings, board):
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[{'action': 'add', 'node': {'kind': 'text', 'x': 1, 'y': 1,
                                              'payload': {'text': 'first'}}}])
    assert reason == ''
    # A second writer still holding version 1 loses: the refusal names the reason.
    _, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[{'action': 'add', 'node': {'kind': 'text', 'x': 2, 'y': 2,
                                              'payload': {'text': 'stale'}}}])
    assert reason == 'version'


def test_non_owner_cannot_mutate(settings, board):
    _, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-2', base_version=1,
        mutations=[{'action': 'add', 'node': {'kind': 'text', 'x': 1, 'y': 1,
                                              'payload': {'text': 'intruder'}}}])
    assert reason == 'missing'
    assert node_boards.load(settings, board['id'])['nodes'] == []


def test_unknown_kind_and_fabricated_media_are_refused(settings, board):
    _, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[{'action': 'add', 'node': {'kind': 'iframe', 'x': 1, 'y': 1,
                                              'payload': {}}}])
    assert reason == 'invalid'
    _, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[{'action': 'add', 'node': {
            'kind': 'image', 'x': 0, 'y': 0,
            'payload': {'src': 'https://evil.example/x.png', 'sha256': 'ab'}}}])
    assert reason == 'invalid'
    assert node_boards.load(settings, board['id'])['nodes'] == []


def test_video_node_rejects_off_allowlist_embeds(settings, board):
    _, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[{'action': 'add', 'node': {
            'kind': 'video', 'x': 0, 'y': 0,
            'payload': {'status': 'verified_embed',
                        'embed_url': 'https://vimeo.com/123456'}}}])
    assert reason == 'invalid'
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[{'action': 'add', 'node': {
            'kind': 'video', 'x': 0, 'y': 0,
            'payload': {'status': 'verified_embed',
                        'embed_url': 'https://www.youtube-nocookie.com/embed/x?si=1',
                        'title': 'Linear functions'}}}])
    assert reason == ''


def test_update_cannot_touch_media_status(settings, board):
    sha = 'a' * 64
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[{'action': 'add', 'node': {
            'kind': 'video', 'x': 0, 'y': 0,
            'payload': {'status': 'withheld', 'withheld_reason': 'revoked',
                        'watch_url': 'https://youtube.com/watch?v=x',
                        'title': 'Withheld clip'}}}])
    assert reason == ''
    video_node = doc['nodes'][0]
    _, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=doc['version'],
        mutations=[{'action': 'update', 'id': video_node['id'],
                    'fields': {'status': 'verified_embed'}}])
    assert reason == 'invalid'
    fresh = node_boards.load(settings, board['id'])
    assert fresh['nodes'][0]['payload']['status'] == 'withheld'


# --------------------------------------------------------------------------- rollup + export

def _image_node(sha, licence_class='cc_by', licence='CC BY 4.0'):
    return {'kind': 'image', 'x': 0, 'y': 0, 'w': 320, 'h': 240,
            'payload': {'src': f'/api/v1/media/images/{sha}/bytes', 'sha256': sha,
                        'title': 'Photo', 'credit': 'a', 'licence': licence,
                        'licence_class': licence_class, 'source_url': 'https://x/y'}}


def test_licence_rollup_share_alike_wins(settings, board):
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[
            {'action': 'add', 'node': _image_node('b' * 64)},
            {'action': 'add', 'node': _image_node('c' * 64, 'cc_by_sa', 'CC BY-SA 4.0')},
        ])
    assert reason == ''
    rollup = node_boards.licence_rollup(settings, doc)
    assert rollup['share_alike'] is True
    assert len(rollup['attributions']) == 2


def test_svg_export_embeds_and_stamps(settings, board):
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[
            {'action': 'add', 'node': {'kind': 'text', 'x': 10, 'y': 10,
                                       'payload': {'text': 'a < b & c'}}},
            {'action': 'add', 'node': _image_node('d' * 64, 'cc_by_sa', 'CC BY-SA 4.0')},
        ])
    assert reason == ''
    svg = node_boards.to_svg(settings, doc)
    assert svg.startswith('<svg')
    assert 'a &lt; b &amp; c' in svg
    assert 'share' in svg.lower() and 'CC BY-SA' in svg


def test_lesson_bundle_roundtrip(settings, board):
    png = (b'\x89PNG\r\n\x1a\n' + b'0' * 64)
    sha = __import__('hashlib').sha256(png).hexdigest()
    stored = media.store_bytes(settings, png, sha=sha, title='roundtrip')
    assert stored == 1
    assert media.store_bytes(settings, png, sha=sha) == 0  # content-addressed dedupe
    doc, reason = node_boards.apply_mutations(
        settings, board['id'], owner_id='user-1', base_version=1,
        mutations=[{'action': 'add', 'node': _image_node(sha)}])
    assert reason == ''
    bundle = node_boards.to_lesson_bundle(settings, doc)
    result = node_boards.import_bundle(settings, owner_id='user-1', data=bundle)
    reimported = result['board']
    assert reimported['id'] != board['id']
    assert reimported['title'].endswith('(imported)')
    assert len(reimported['nodes']) == 1
    assert reimported['nodes'][0]['payload']['sha256'] == sha
    assert node_boards.image_file(settings, sha) is not None
    assert result['media_restored'] == 0  # the sha was already cached


def test_import_rejects_non_bundle(settings):
    with pytest.raises(ValueError):
        node_boards.import_bundle(settings, owner_id='user-1', data=b'not a zip')
    with pytest.raises(ValueError):
        node_boards.import_bundle(settings, owner_id='user-1', data=b'PK\x03\x04garbage')


# --------------------------------------------------------------------------- share

def test_share_create_resolve_revoke(settings, board):
    share = node_boards.create_share(settings, board['id'], owner_id='user-1', ttl_days=7)
    assert share and share['token']
    snapshot = node_boards.resolve_share(settings, share['token'])
    assert snapshot and snapshot['title'] == 'Algebra board'
    assert snapshot['nodes'] == []
    # The stored index never contains the plaintext token.
    stored = (node_boards._shares_path(settings)).read_text()
    assert share['token'] not in stored
    assert node_boards.revoke_shares(settings, board['id'], owner_id='user-1') is True
    assert node_boards.resolve_share(settings, share['token']) is None


def test_share_requires_ownership_and_expires(settings, board):
    assert node_boards.create_share(settings, board['id'], owner_id='user-2') is None
    share = node_boards.create_share(settings, board['id'], owner_id='user-1', ttl_days=1)
    # Force expiry: resolve must treat it exactly like a revocation.
    path = node_boards._shares_path(settings)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['expires_at'] = 1.0
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    assert node_boards.resolve_share(settings, share['token']) is None


# --------------------------------------------------------------------------- image bytes

def test_image_file_resolves_only_real_cache_entries(settings, board):
    png = (b'\x89PNG\r\n\x1a\n' + b'1' * 32)
    sha = __import__('hashlib').sha256(png).hexdigest()
    media.store_bytes(settings, png, sha=sha)
    path = node_boards.image_file(settings, sha)
    assert path is not None and path.is_file()
    assert node_boards.image_file(settings, 'e' * 64) is None
    assert node_boards.image_file(settings, 'not-a-sha') is None


# --------------------------------------------------------------------------- HTTP surface

from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def auth(client):
    response = client.post('/api/v1/auth/register', json={
        'name': 'Board User', 'email': 'board@example.test', 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_board_http_crud_and_conflict(client, auth):
    created = client.post('/api/v1/boards', headers=auth, json={'title': 'Chem lab'})
    assert created.status_code == 201, created.text
    board_id = created.json()['board']['id']
    listed = client.get('/api/v1/boards', headers=auth).json()['boards']
    assert [row['id'] for row in listed] == [board_id]
    patch = client.patch(f'/api/v1/boards/{board_id}', headers=auth, json={
        'base_version': 1,
        'mutations': [{'action': 'add', 'node': {'kind': 'text', 'x': 1, 'y': 2,
                                                 'payload': {'text': 'Avogadro'}}}]})
    assert patch.status_code == 200, patch.text
    version = patch.json()['board']['version']
    stale = client.patch(f'/api/v1/boards/{board_id}', headers=auth, json={
        'base_version': 1, 'mutations': [{'action': 'delete', 'id': 'n-nope'}]})
    assert stale.status_code == 409
    fetched = client.get(f'/api/v1/boards/{board_id}', headers=auth)
    assert fetched.json()['board']['nodes'][0]['payload']['text'] == 'Avogadro'
    assert client.delete(f'/api/v1/boards/{board_id}', headers=auth).status_code == 204
    assert client.get(f'/api/v1/boards/{board_id}', headers=auth).status_code == 404


def test_board_is_per_account(client, auth):
    board_id = client.post('/api/v1/boards', headers=auth, json={'title': 'mine'}).json()['board']['id']
    other = client.post('/api/v1/auth/register', json={
        'name': 'Other', 'email': 'other@example.test', 'password': 'long-secret-password'}).json()
    other_auth = {'Authorization': 'Bearer ' + other['token']}
    assert client.get(f'/api/v1/boards/{board_id}', headers=other_auth).status_code == 404
    assert client.delete(f'/api/v1/boards/{board_id}', headers=other_auth).status_code == 404
    patched = client.patch(f'/api/v1/boards/{board_id}', headers=other_auth, json={
        'base_version': 1, 'mutations': [{'action': 'delete', 'id': 'x'}]})
    assert patched.status_code == 404


def test_share_endpoint_serves_without_auth_and_revokes(client, auth):
    board_id = client.post('/api/v1/boards', headers=auth, json={'title': 'shared'}).json()['board']['id']
    share = client.post(f'/api/v1/boards/{board_id}/share', headers=auth, json={'ttl_days': 7})
    assert share.status_code == 201, share.text
    url = share.json()['url']
    # No Authorization header: the token is the credential.
    snapshot = client.get(url)
    assert snapshot.status_code == 200
    assert snapshot.json()['title'] == 'shared'
    assert client.get(url + 'x').status_code == 410
    assert client.delete(f'/api/v1/boards/{board_id}/share', headers=auth).status_code == 204
    assert client.get(url).status_code == 410


def test_image_bytes_endpoint(client, settings, auth):
    png = (b'\x89PNG\r\n\x1a\n' + b'2' * 48)
    sha = __import__('hashlib').sha256(png).hexdigest()
    media.store_bytes(settings, png, sha=sha)
    served = client.get(f'/api/v1/media/images/{sha}/bytes', headers=auth)
    assert served.status_code == 200
    assert served.headers['content-type'] == 'image/png'
    assert served.content == png
    assert client.get(f'/api/v1/media/images/{"f" * 64}/bytes', headers=auth).status_code == 404
    # No token: the cache is not a public CDN.
    assert client.get(f'/api/v1/media/images/{sha}/bytes').status_code in (401, 403)


def test_agent_chat_rejects_bad_image_payloads(client, auth):
    bad = client.post('/api/v1/agent/chat', headers=auth, json={
        'message': 'explain', 'images': ['https://evil.example/pic.png']})
    assert bad.status_code == 422
    bad = client.post('/api/v1/agent/chat', headers=auth, json={
        'message': 'explain', 'images': ['data:text/html;base64,PGh0bWw+']})
    assert bad.status_code == 422


def test_export_endpoint_formats(client, auth):
    board_id = client.post('/api/v1/boards', headers=auth, json={'title': 'exp'}).json()['board']['id']
    client.patch(f'/api/v1/boards/{board_id}', headers=auth, json={
        'base_version': 1,
        'mutations': [{'action': 'add', 'node': {'kind': 'shape', 'x': 0, 'y': 0, 'w': 10, 'h': 10,
                                                 'payload': {'shape': 'rect'}}}]})
    svg = client.get(f'/api/v1/boards/{board_id}/export', headers=auth, params={'format': 'svg'})
    assert svg.status_code == 200 and svg.text.startswith('<svg')
    lesson = client.get(f'/api/v1/boards/{board_id}/export', headers=auth, params={'format': 'lesson'})
    assert lesson.status_code == 200 and lesson.content[:2] == b'PK'
    # Reimport the bundle just exported: the round trip is the product promise.
    imported = client.post('/api/v1/boards/import', headers=auth,
                           json={'data_base64': base64.b64encode(lesson.content).decode()})
    assert imported.status_code == 201, imported.text
    assert imported.json()['board']['nodes'][0]['payload']['shape'] == 'rect'
