"""Line-only VLM diagrams, math curves, template catalog, and image vectorization."""

import base64
import json
import os
import struct
import zlib
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.harness import diagram
from app.harness import provider
from test_api import account, client, settings


_LIVE_DIAGRAM_SMOKE = os.getenv('HARNESS_DIAGRAM_LIVE_SMOKE', '')


def _board_snapshot_png():
    """A small whiteboard-like raster containing an unfinished ink path."""
    width, height = 512, 320
    rows = []
    for y in range(height):
        row = bytearray([255] * (width * 3))
        for x in range(width):
            if 90 <= x <= 360 and abs(y - int(180 - (x - 90) * 0.22)) <= 3:
                offset = x * 3
                row[offset:offset + 3] = b'\x1d\x4e\xd8'
        rows.append(b'\x00' + bytes(row))

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b''.join(rows)))
            + chunk(b'IEND', b''))


def test_fourier_smoothing_preserves_line_segments_and_curve_endpoints():
    straight = [[0, 0], [4, 2], [8, 4]]
    assert diagram.fourier_smooth(straight) == straight
    smooth = diagram.fourier_smooth([[0, 0], [10, 22], [20, 28], [30, 18], [40, 0]])
    assert len(smooth) >= 24
    assert smooth[0] == [0.0, 0.0] and smooth[-1] == [40.0, 0.0]
    assert all(len(point) == 2 for point in smooth)


def test_proposal_becomes_only_board_paths_and_text():
    nodes = diagram.nodes_from_proposal({
        'title': 'Water cycle',
        'strokes': [{'points': [[0, 500], [300, 200], [600, 500]]},
                    {'points': [[600, 500], [900, 500]]}],
        'labels': [{'text': 'evaporation', 'x': 300, 'y': 140}],
    }, anchor_x=100, anchor_y=200)
    assert [node['kind'] for node in nodes] == ['path', 'path', 'text']
    assert all(node['kind'] != 'shape' for node in nodes)
    assert nodes[0]['payload']['points'][0] == [100.0, 440.0]
    assert nodes[0]['payload']['points'][-1] == [556.0, 440.0]
    assert nodes[-1]['payload']['text'] == 'evaporation'


def test_formula_sampler_handles_functions_parametrics_and_fourier_series():
    function = diagram.sample_curve(curve_type='function', expression='sin(x)', anchor_x=0, anchor_y=0)
    assert function['nodes'] and all(node['kind'] == 'path' for node in function['nodes'])
    parametric = diagram.sample_curve(
        curve_type='parametric', x_expression='cos(t)', y_expression='sin(t)',
        t_min=0, t_max=6.283185, x_min=-1.2, x_max=1.2, y_min=-1.2, y_max=1.2,
        anchor_x=100, anchor_y=100)
    assert parametric['nodes'] and parametric['curve_type'] == 'parametric'
    fourier = diagram.sample_curve(curve_type='fourier', cosine=[0, 1, 0.3], sine=[0, 0.2],
                                   anchor_x=0, anchor_y=0)
    assert fourier['title'].startswith('Fourier series · a=')
    assert any(len(node['payload']['points']) >= 60 for node in fourier['nodes'])


def test_formula_sampler_refuses_python_execution_and_bad_bounds():
    with pytest.raises(diagram.DiagramError):
        diagram.sample_curve(curve_type='function', expression='__import__("os").system("id")',
                             anchor_x=0, anchor_y=0)
    with pytest.raises(diagram.DiagramError):
        diagram.sample_curve(curve_type='function', expression='x', x_min=3, x_max=1,
                             anchor_x=0, anchor_y=0)
    with pytest.raises(diagram.DiagramError):
        diagram.sample_curve(curve_type='fourier', cosine=[], sine=[], anchor_x=0, anchor_y=0)


def test_catalog_has_original_editable_economics_and_biology_templates():
    items = diagram.list_templates()
    assert len(items) >= 7
    assert {'economics', 'biology'} <= {item['subject'] for item in items}
    assert diagram.list_templates(query='supply', subject='economics')
    assert diagram.list_templates(query='cell', subject='biology')
    template = diagram.template_preview('economics.ppf', anchor_x=50, anchor_y=60)
    assert template['source_url'].startswith('https://www.khanacademy.org/')
    assert template['nodes'] and all(node['kind'] in {'path', 'text'} for node in template['nodes'])
    assert 'not copied' in template['provenance']


def test_image_vectorizer_extracts_line_only_nodes_from_raster():
    image = Image.new('RGB', (160, 120), 'white')
    ImageDraw.Draw(image).line((15, 100, 80, 20, 145, 100), fill='black', width=4)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    result = diagram.vectorize_image(buffer.getvalue(), anchor_x=100, anchor_y=200,
                                     canvas_width=320, canvas_height=180)
    paths = [node for node in result['nodes'] if node['kind'] == 'path']
    assert paths and result['trace_count'] > 0
    assert all(len(node['payload']['points']) >= 2 for node in paths)
    assert all(node['kind'] != 'shape' for node in result['nodes'])
    all_points = [point for node in paths for point in node['payload']['points']]
    assert min(point[0] for point in all_points) >= 100
    assert max(point[0] for point in all_points) <= 420
    assert min(point[1] for point in all_points) >= 200
    assert max(point[1] for point in all_points) <= 380


def test_image_vectorizer_refuses_blank_or_unsupported_bytes():
    image = Image.new('RGB', (80, 60), 'white')
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    with pytest.raises(diagram.DiagramError):
        diagram.vectorize_image(buffer.getvalue(), anchor_x=0, anchor_y=0)
    with pytest.raises(diagram.DiagramError):
        diagram.vectorize_image(b'not an image', anchor_x=0, anchor_y=0)


def test_vlm_route_sends_snapshot_and_returns_nonmutating_path_preview(client, monkeypatch):
    monkeypatch.setenv('HARNESS_DIAGRAM_URL', 'https://api.deepseek.com/v1')
    monkeypatch.setenv('HARNESS_DIAGRAM_KEY', 'test-key-not-real')
    captured = {}

    def fake_chat_json(settings, messages, **kwargs):
        captured['settings'] = settings
        captured['messages'] = messages
        return {'title': 'Simple food chain',
                'strokes': [{'points': [[100, 500], [500, 500], [900, 500]]}],
                'labels': [{'text': 'grass → rabbit → fox', 'x': 260, 'y': 420}]}

    monkeypatch.setattr(provider, 'chat_json', fake_chat_json)
    headers, _ = account(client)
    board_id = client.post('/api/v1/boards', headers=headers,
                           json={'title': 'Teacher diagram'}).json()['board']['id']
    png = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=')
    response = client.post(f'/api/v1/boards/{board_id}/diagram', headers=headers, json={
        'prompt': 'Draw a food chain using hand-drawn line strokes.', 'x': 40, 'y': 80,
        'snapshot_data_url': 'data:image/png;base64,' + base64.b64encode(png).decode(),
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['provider'].startswith('DeepSeek V4.1 Flash')
    assert [node['kind'] for node in body['nodes']] == ['path', 'text']
    assert captured['settings'].provider_model == 'deepseek-flash'
    assert captured['messages'][1]['content'][1]['type'] == 'image_url'
    assert client.get(f'/api/v1/boards/{board_id}', headers=headers).json()['board']['nodes'] == []


def test_curve_template_and_catalog_routes_are_preview_only(client):
    headers, _ = account(client)
    board_id = client.post('/api/v1/boards', headers=headers,
                           json={'title': 'Curve board'}).json()['board']['id']
    curve = client.post(f'/api/v1/boards/{board_id}/diagram/curve', headers=headers, json={
        'curve_type': 'function', 'expression': 'sin(x)', 'x': 200, 'y': 220,
        'x_min': -4, 'x_max': 4, 'y_min': -1.5, 'y_max': 1.5,
    })
    assert curve.status_code == 200, curve.text
    assert curve.json()['nodes'] and curve.json()['nodes'][0]['kind'] == 'path'
    template = client.post(f'/api/v1/boards/{board_id}/diagram/template', headers=headers, json={
        'template_id': 'biology.plant-cell', 'x': 300, 'y': 400,
    })
    assert template.status_code == 200, template.text
    assert all(node['kind'] in {'path', 'text'} for node in template.json()['nodes'])
    assert client.get('/api/v1/diagram-templates', headers=headers,
                      params={'q': 'demand', 'subject': 'economics'}).json()['templates']
    assert client.get('/api/v1/diagram-templates').status_code == 401
    assert client.get(f'/api/v1/boards/{board_id}', headers=headers).json()['board']['nodes'] == []


def test_vectorization_route_checks_image_and_returns_path_nodes(client):
    headers, _ = account(client)
    board_id = client.post('/api/v1/boards', headers=headers,
                           json={'title': 'Image traces'}).json()['board']['id']
    image = Image.new('RGB', (128, 96), 'white')
    ImageDraw.Draw(image).line((10, 80, 60, 15, 115, 80), fill='black', width=3)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    response = client.post(f'/api/v1/boards/{board_id}/diagram/trace', headers=headers, json={
        'image_data_url': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode(),
        'x': 50, 'y': 60,
    })
    assert response.status_code == 200, response.text
    assert response.json()['nodes'] and all(n['kind'] == 'path' for n in response.json()['nodes'])
    invalid = client.post(f'/api/v1/boards/{board_id}/diagram/trace', headers=headers, json={
        'image_data_url': 'data:image/png;base64,' + base64.b64encode(b'not png').decode(),
        'x': 0, 'y': 0,
    })
    assert invalid.status_code == 422


def test_diagram_route_refuses_non_owner_and_invalid_snapshot(client):
    headers, _ = account(client)
    board_id = client.post('/api/v1/boards', headers=headers,
                           json={'title': 'Private'}).json()['board']['id']
    stranger = client.post('/api/v1/auth/register', json={
        'name': 'Stranger', 'email': 'diagram-stranger@example.test',
        'password': 'long-secret-password'}).json()
    stranger_headers = {'Authorization': 'Bearer ' + stranger['token']}
    body = {'prompt': 'Draw a cell', 'x': 0, 'y': 0}
    assert client.post(f'/api/v1/boards/{board_id}/diagram',
                       headers=stranger_headers, json=body).status_code == 404
    invalid = {**body, 'snapshot_data_url': 'https://example.test/image.png'}
    assert client.post(f'/api/v1/boards/{board_id}/diagram',
                       headers=headers, json=invalid).status_code == 422


def test_clipboard_paste_caches_image_and_board_can_reload_it(client):
    auth, _ = account(client)
    png = b'\x89PNG\r\n\x1a\n' + b'educational image bytes'
    response = client.post('/api/v1/images/paste', headers=auth, json={
        'data_base64': base64.b64encode(png).decode(), 'filename': 'Cell sketch.png'})
    assert response.status_code == 201, response.text
    asset = response.json()['asset']
    assert asset['mime'] == 'image/png'
    assert asset['credit'].endswith('not verified')
    assert asset['licence'] == 'User-provided (unverified)'
    board = client.post('/api/v1/boards', headers=auth, json={'title': 'Pasted image'}).json()['board']
    image_node = {'kind': 'image', 'x': 10, 'y': 15, 'w': 160, 'h': 120,
                  'payload': {'sha256': asset['sha256'], 'src': asset['src'],
                              'title': asset['title'], 'credit': asset['credit'],
                              'licence': asset['licence']}}
    patched = client.patch(f"/api/v1/boards/{board['id']}", headers=auth, json={
        'base_version': board['version'], 'mutations': [{'action': 'add', 'node': image_node}]})
    assert patched.status_code == 200, patched.text
    assert patched.json()['board']['nodes'][0]['payload']['sha256'] == asset['sha256']
    assert client.get(asset['src'], headers=auth).content == png


def test_clipboard_paste_rejects_invalid_or_unsupported_image(client):
    auth, _ = account(client)
    assert client.post('/api/v1/images/paste', headers=auth,
                       json={'data_base64': 'not-base64'}).status_code == 422
    unsupported = client.post('/api/v1/images/paste', headers=auth, json={
        'data_base64': base64.b64encode(b'<svg>not an image</svg>').decode()})
    assert unsupported.status_code == 422


@pytest.mark.live
def test_live_deepseek_v41_flash_reads_board_snapshot_and_commits_line_paths(client):
    """Opt-in live VLM run; ordinary tests never spend tokens."""
    if _LIVE_DIAGRAM_SMOKE != '1':
        pytest.skip('Live DeepSeek diagram smoke disabled; set HARNESS_DIAGRAM_LIVE_SMOKE=1')
    headers, _ = account(client)
    board = client.post('/api/v1/boards', headers=headers,
                        json={'title': 'Live VLM diagram smoke'}).json()['board']
    snapshot = 'data:image/png;base64,' + base64.b64encode(_board_snapshot_png()).decode()
    response = client.post(f"/api/v1/boards/{board['id']}/diagram", headers=headers, json={
        'prompt': 'Create a clear three-step water cycle diagram, using this board snapshot as context.',
        'x': 160, 'y': 140, 'snapshot_data_url': snapshot,
    })
    assert response.status_code == 200, response.text
    proposal = response.json()
    assert proposal['provider'].startswith('DeepSeek V4.1 Flash')
    assert proposal['nodes'] and all(node['kind'] in {'path', 'text'} for node in proposal['nodes'])
    persisted = client.patch(f"/api/v1/boards/{board['id']}", headers=headers, json={
        'base_version': board['version'],
        'mutations': [{'action': 'add', 'node': node} for node in proposal['nodes']],
    })
    assert persisted.status_code == 200, persisted.text
    assert len(persisted.json()['board']['nodes']) == len(proposal['nodes'])
