"""Tests for the slide editor: the deck document and the real .pptx bridge.

Written around the guarantees the module claims. The load-bearing ones are the two that make
this "actually a PPT" rather than an exporter — a deck that survives an export→reopen with its
runs, sizes, colours and picture bytes intact, and a .pptx that imports back into a document
whose text and geometry survive. The refusals are tested too: a malformed element must be a
422 and not a silent store, and a deck must belong to exactly one account.

None of these tests touch the network. A picture is stored through the media store's own
content-addressed path, so the export embeds the same bytes the media route serves.
"""

import base64
import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.harness import media
from app.main import create_app
from test_api import settings  # noqa: F401 - fixture


@pytest.fixture
def client(settings):  # noqa: F811 - the imported fixture is the argument
    with TestClient(create_app(settings)) as client:
        yield client


def account(client, label):
    response = client.post('/api/v1/auth/register', json={
        'name': label, 'email': f'{label}@example.test', 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def png_bytes(width=64, height=32, colour=(200, 60, 40)):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), colour).save(buffer, format='PNG')
    return buffer.getvalue()


def make_deck(client, headers, title='Physics 101'):
    created = client.post('/api/v1/deck', headers=headers, json={'title': title})
    assert created.status_code == 201, created.text
    doc = created.json()
    slide = doc['slides'][0]
    heading = client.post(f"/api/v1/deck/{doc['id']}/elements", headers=headers, json={
        'slide_id': slide['id'],
        'element': {'kind': 'text', 'x': 48, 'y': 40, 'w': 600, 'h': 80,
                    'style': {'size': 32, 'bold': True, 'color': '#3E7A55'},
                    'text': {'paragraphs': [{'runs': [{'text': 'Newton and motion'}]}]}}}).json()
    return doc, slide, heading


# --------------------------------------------------------------------------- pptx round trip


def test_export_roundtrip_reopens_with_real_runs_and_picture(client, settings):
    headers = account(client, 'exporter')
    doc, slide, heading = make_deck(client, headers)

    # A real picture, stored through the media store's content-addressed path.
    body = png_bytes()
    media.store_bytes(settings, body, title='a red block')
    sha = hashlib.sha256(body).hexdigest()
    added = client.post(f"/api/v1/deck/{doc['id']}/elements", headers=headers, json={
        'slide_id': slide['id'],
        'element': {'kind': 'image', 'x': 680, 'y': 120, 'w': 240, 'h': 160,
                    'image': {'sha256': sha, 'fit': 'cover', 'alt': 'a red block'}}})
    assert added.status_code == 201, added.text

    response = client.get(f"/api/v1/deck/{doc['id']}/export.pptx", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('application/vnd.openxmlformats')

    reopened = Presentation(io.BytesIO(response.content))
    assert len(reopened.slides) == 1

    runs = [run for shape in reopened.slides[0].shapes if shape.has_text_frame
            for para in shape.text_frame.paragraphs for run in para.runs]
    match = next(run for run in runs if run.text == 'Newton and motion')
    assert match.font.size.pt == 32
    assert str(match.font.color.rgb) == '3E7A55'
    assert match.font.bold is True

    pictures = [shape for shape in reopened.slides[0].shapes
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1
    assert len(pictures[0].image.blob) == len(body)


def test_import_roundtrip_survives_text_and_geometry(client, settings):
    headers = account(client, 'importer')
    doc, slide, heading = make_deck(client, headers)
    exported = client.get(f"/api/v1/deck/{doc['id']}/export.pptx", headers=headers)
    assert exported.status_code == 200

    imported = client.post('/api/v1/deck/import', headers=headers, json={
        'title': 'Reimported', 'data_base64': base64.b64encode(exported.content).decode()})
    assert imported.status_code == 201, imported.text
    back = imported.json()
    assert back['title'] == 'Reimported'
    assert len(back['slides']) == 1

    text_elements = [e for e in back['slides'][0]['elements'] if e['kind'] == 'text']
    found = next(e for e in text_elements
                 if e['text']['paragraphs'][0]['runs'][0]['text'] == 'Newton and motion')
    # Geometry and the run's size survive the EMU <-> point boundary to within a rounding step.
    assert (found['x'], found['y'], found['w'], found['h']) == (48.0, 40.0, 600.0, 80.0)
    assert found['text']['paragraphs'][0]['runs'][0]['style']['size'] == 32


def test_import_refuses_bytes_that_are_not_a_pptx(client):
    headers = account(client, 'badimport')
    response = client.post('/api/v1/deck/import', headers=headers, json={
        'data_base64': base64.b64encode(b'not a zip at all').decode()})
    assert response.status_code == 422
    assert 'PK' in response.text


# --------------------------------------------------------------------------- svg thumbnail


def test_slide_svg_contains_real_text_and_font_size(client):
    headers = account(client, 'svgtaker')
    doc, slide, heading = make_deck(client, headers)
    response = client.get(f"/api/v1/deck/{doc['id']}/slide/{slide['id']}.svg", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('image/svg+xml')
    assert 'Newton and motion' in response.text
    assert 'font-size="32' in response.text
    assert '#3E7A55' in response.text


# --------------------------------------------------------------------------- refusals


def test_malformed_element_is_rejected_with_422(client):
    headers = account(client, 'refuser')
    doc, slide, heading = make_deck(client, headers)

    negative = client.post(f"/api/v1/deck/{doc['id']}/elements", headers=headers, json={
        'slide_id': slide['id'],
        'element': {'kind': 'text', 'x': 10, 'y': 10, 'w': -50, 'h': 40,
                    'text': {'paragraphs': [{'runs': [{'text': 'bad'}]}]}}})
    assert negative.status_code == 422
    assert 'w must be positive' in negative.text

    unknown = client.post(f"/api/v1/deck/{doc['id']}/elements", headers=headers, json={
        'slide_id': slide['id'],
        'element': {'kind': 'hologram', 'x': 10, 'y': 10, 'w': 50, 'h': 40}})
    assert unknown.status_code == 422
    assert 'unknown kind' in unknown.text

    # The refusal stored nothing: the deck still has exactly the one element it started with.
    stored = client.get(f"/api/v1/deck/{doc['id']}", headers=headers).json()
    assert len(stored['slides'][0]['elements']) == 1


def test_replace_with_malformed_document_is_422(client):
    headers = account(client, 'putrefuser')
    doc, slide, heading = make_deck(client, headers)
    broken = dict(doc)
    broken['slides'] = [{'id': slide['id'], 'layout': 'nonsense', 'elements': []}]
    response = client.put(f"/api/v1/deck/{doc['id']}", headers=headers, json=broken)
    assert response.status_code == 422
    assert 'layout must be one of' in response.text


def test_export_route_returns_a_real_zip(client):
    headers = account(client, 'zipper')
    doc, slide, heading = make_deck(client, headers)
    response = client.get(f"/api/v1/deck/{doc['id']}/export.pptx", headers=headers)
    assert response.status_code == 200
    assert response.content[:2] == b'PK'          # a .pptx is a zip
    assert 'attachment' in response.headers['content-disposition']
    assert response.headers['content-disposition'].endswith('.pptx"')


# --------------------------------------------------------------------------- ownership


def test_decks_are_per_account(client):
    alice = account(client, 'alice')
    bob = account(client, 'bob')
    doc, slide, heading = make_deck(client, alice, title='Alice private deck')

    assert client.get(f"/api/v1/deck/{doc['id']}", headers=alice).status_code == 200
    # Bob gets the same answer as for a deck that does not exist: 404, never 403.
    assert client.get(f"/api/v1/deck/{doc['id']}", headers=bob).status_code == 404
    assert client.get(f"/api/v1/deck/{doc['id']}/export.pptx", headers=bob).status_code == 404
    assert client.delete(f"/api/v1/deck/{doc['id']}", headers=bob).status_code == 404

    listed = client.get('/api/v1/deck', headers=bob).json()['decks']
    assert doc['id'] not in {row['id'] for row in listed}


# --------------------------------------------------------------------------- slide ops


def test_slide_add_move_duplicate_delete(client):
    headers = account(client, 'mover')
    doc, slide, heading = make_deck(client, headers)

    second = client.post(f"/api/v1/deck/{doc['id']}/slides", headers=headers,
                         json={'layout': 'idea', 'notes': 'say this'}).json()
    assert second['layout'] == 'idea' and second['notes'] == 'say this'

    moved = client.post(f"/api/v1/deck/{doc['id']}/slides/{second['id']}/move",
                        headers=headers, json={'to': 0}).json()
    assert moved['slides'][0]['id'] == second['id']

    clone = client.post(f"/api/v1/deck/{doc['id']}/slides/{second['id']}/duplicate",
                        headers=headers).json()
    assert clone['id'] != second['id']
    assert len(client.get(f"/api/v1/deck/{doc['id']}", headers=headers).json()['slides']) == 3

    assert client.delete(f"/api/v1/deck/{doc['id']}/slides/{clone['id']}",
                         headers=headers).status_code == 204
    assert len(client.get(f"/api/v1/deck/{doc['id']}", headers=headers).json()['slides']) == 2


def test_element_patch_moves_and_restyles(client):
    headers = account(client, 'patcher')
    doc, slide, heading = make_deck(client, headers)
    updated = client.patch(f"/api/v1/deck/{doc['id']}/elements/{heading['id']}",
                           headers=headers, json={'x': 120, 'style': {'size': 44}})
    assert updated.status_code == 200, updated.text
    assert updated.json()['x'] == 120
    assert updated.json()['style']['size'] == 44
    assert updated.json()['style']['color'] == '#3E7A55'   # the untouched key survives


def test_deck_images_reports_attribution(client, settings):
    headers = account(client, 'imagist')
    doc, slide, heading = make_deck(client, headers)
    body = png_bytes()
    media.store_bytes(settings, body, title='Sunset')
    sha = hashlib.sha256(body).hexdigest()
    client.post(f"/api/v1/deck/{doc['id']}/elements", headers=headers, json={
        'slide_id': slide['id'],
        'element': {'kind': 'image', 'x': 10, 'y': 10, 'w': 100, 'h': 100,
                    'image': {'sha256': sha, 'fit': 'contain'}}})
    payload = client.get(f"/api/v1/deck/{doc['id']}/images", headers=headers).json()
    row = next(r for r in payload['images'] if r['sha256'] == sha)
    assert row['resolved'] is True
    assert row['bytes'] == len(body)
    assert row['bytes_url'].endswith(f'/media/images/{sha}/bytes')


def test_upload_image_then_embed_in_pptx(client, settings):
    """An inserted local image goes into the content-addressed store and then embeds in the
    .pptx through exactly the same path a licence-cleared download does."""
    headers = account(client, 'inserter')
    doc, slide, heading = make_deck(client, headers)
    body = png_bytes(90, 50, (10, 120, 200))
    upload = client.post(f"/api/v1/deck/{doc['id']}/images", headers=headers, json={
        'data_base64': base64.b64encode(body).decode(), 'title': 'blue block'})
    assert upload.status_code == 201, upload.text
    sha = upload.json()['sha256']
    assert sha == hashlib.sha256(body).hexdigest()

    added = client.post(f"/api/v1/deck/{doc['id']}/elements", headers=headers, json={
        'slide_id': slide['id'],
        'element': {'kind': 'image', 'x': 20, 'y': 20, 'w': 180, 'h': 100,
                    'image': {'sha256': sha, 'fit': 'stretch'}}})
    assert added.status_code == 201, added.text
    exported = client.get(f"/api/v1/deck/{doc['id']}/export.pptx", headers=headers)
    reopened = Presentation(io.BytesIO(exported.content))
    pictures = [s for s in reopened.slides[0].shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1 and len(pictures[0].image.blob) == len(body)

    # Bytes that are not an image are refused, so the store never holds a non-image.
    bad = client.post(f"/api/v1/deck/{doc['id']}/images", headers=headers, json={
        'data_base64': base64.b64encode(b'plain text, not an image').decode()})
    assert bad.status_code == 422


def test_deck_from_concept_builds_an_editable_deck(client):
    headers = account(client, 'curriculum')
    concept = client.get('/api/v1/curriculum', headers=headers).json()['concepts'][0]['id']
    response = client.get(f'/api/v1/deck/from-concept/{concept}', headers=headers)
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc['slides'], 'a curriculum concept must produce at least one slide'
    assert all(slide['elements'] for slide in doc['slides'])
    # It is a stored deck, not a one-off render: it can be fetched back by id.
    assert client.get(f"/api/v1/deck/{doc['id']}", headers=headers).status_code == 200
