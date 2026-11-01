"""One learner, one session, every surface: the whole-use test.

Every other test file proves one feature. This one proves the features *compose* -
that a learner who arrives with a document can leave with a course they own, a deck
that opens in PowerPoint, cards scheduled by FSRS, a board they drew on, and a
tutor that answered from the same course. Each step uses the previous step's real
output, over the real HTTP surface, so a break in the chain fails here even when
every unit test still passes.

The order is the order a learner actually works in, which is why it is one test and
not nine: the failure this catches is a *contract* failure between features - a
course id that the deck route does not accept, a concept id that the flashcard
generator cannot resolve, a tutor that cannot see the course the learner just
enrolled in.
"""

import io

import pytest
from pptx import Presentation

from app import capabilities
from app.config import Settings
from test_api import account  # noqa: F401 - shared fixture helper
from test_course_builder import SOURCE  # the same document the intake tests use


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """The shipped default: the offline tutor, no network, no model configured.

    The whole-use test deliberately runs the configuration a learner gets from the
    packaged app rather than a mocked provider. If the offline path cannot carry the
    session, the product does not work on first launch, which is the claim that
    matters most.
    """
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(Settings.from_env())) as test_client:
        yield test_client


def test_a_learner_can_go_from_a_document_to_a_taught_course(wired):
    headers, _ = account(wired, 'whole')

    # -- 1. source in -------------------------------------------------------
    # The upload path is what a learner with a file uses; the preview it returns is
    # what the client shows before committing.
    preview = wired.post('/api/v1/create/upload', headers=headers,
                         files={'file': ('photosynthesis.txt', SOURCE.encode('utf-8'),
                                         'text/plain')})
    assert preview.status_code == 200, preview.text
    plan = preview.json()
    assert plan['graph_stats']['concepts'] >= 4
    assert plan['source']['label'] == 'photosynthesis.txt'

    # -- 2. course out, owned by this account --------------------------------
    created = wired.post('/api/v1/create/course', headers=headers,
                         json={'title': 'Photosynthesis', 'text': SOURCE,
                               'subject': 'Biology'})
    assert created.status_code == 201, created.text
    course_id = created.json()['course']['id']
    assert created.json()['concepts'] >= 4

    enrolled = wired.post(f'/api/v1/my-courses/{course_id}/enrol', headers=headers)
    assert enrolled.status_code == 200, enrolled.text
    assert enrolled.json()['enrolled'] is True

    detail = wired.get(f'/api/v1/my-courses/{course_id}', headers=headers).json()
    assert detail['enrolled'] is True
    concepts = detail['concepts_list']
    assert len(concepts) >= 4
    concept_id = concepts[0]['id']
    # The graph the learner now studies from is the one their document produced.
    assert detail['graph_stats']['concepts'] == len(concepts)

    # -- 3. a deck that is actually a .pptx ---------------------------------
    deck_response = wired.get(f'/api/v1/deck/from-concept/{concept_id}', headers=headers)
    assert deck_response.status_code == 200, deck_response.text
    deck_doc = deck_response.json()
    assert len(deck_doc['slides']) >= 3

    exported = wired.get(f"/api/v1/deck/{deck_doc['id']}/export.pptx", headers=headers)
    assert exported.status_code == 200, exported.text
    assert exported.content[:2] == b'PK'
    opened = Presentation(io.BytesIO(exported.content))
    assert len(opened.slides) == len(deck_doc['slides'])
    # Real text in real shapes, not an empty shell with the right slide count.
    text = ' '.join(shape.text_frame.text for slide in opened.slides
                    for shape in slide.shapes if shape.has_text_frame)
    assert len(text.strip()) > 100

    # -- 4. cards, scheduled ------------------------------------------------
    generated = wired.post('/api/v1/flashcards/generate', headers=headers,
                           json={'concept_id': concept_id})
    assert generated.status_code == 200, generated.text
    cards = generated.json()['cards']
    assert cards, 'a concept with a lesson must yield at least one card'
    assert all(card['source'] for card in cards), 'every card cites its provenance'

    reviewed = wired.post(f"/api/v1/flashcards/{cards[0]['id']}/review", headers=headers,
                          json={'grade': 3})
    assert reviewed.status_code == 200, reviewed.text
    session = wired.get('/api/v1/flashcards/session', headers=headers).json()
    assert 'cards' in session
    stats = wired.get('/api/v1/flashcards/stats', headers=headers).json()
    assert stats.get('reviews', stats.get('reviewed', 0)) >= 1

    # -- 5. the tutor answers from that course ------------------------------
    reply = wired.post('/api/v1/chat', headers=headers,
                       json={'concept_id': concept_id, 'message': 'What is the main idea?'})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body['content'].strip()
    # The offline tutor refuses to invent a lesson; a course built from a document
    # has no hand-authored lesson blocks, and the answer must say so rather than
    # fabricate one.
    assert body['grounding'], 'an answer with no grounding is not grounded'

    # -- 6. a figure for the same concept -----------------------------------
    figure = wired.get(f'/api/v1/simulations/{concept_id}', headers=headers)
    assert figure.status_code == 200, figure.text
    assert figure.json()

    # -- 7. a board to draw it on -------------------------------------------
    board = wired.post('/api/v1/boards', headers=headers, json={'title': 'Photosynthesis'})
    assert board.status_code == 201, board.text
    board_doc = board.json()['board']
    board_id = board_doc['id']
    # The same mutations the native editor sends: a labelled box for the idea, a path
    # for the arrow between the two stages. This is the board path a learner uses; the
    # AI diagram proposal needs a configured model and is exercised separately.
    drawn = wired.patch(f'/api/v1/boards/{board_id}', headers=headers, json={
        'base_version': board_doc['version'],
        'mutations': [
            {'action': 'add', 'node': {'kind': 'shape', 'x': 40, 'y': 60, 'w': 220, 'h': 90,
                                       'payload': {'shape': 'rect', 'colour': '#3E7A55'}}},
            {'action': 'add', 'node': {'kind': 'text', 'x': 56, 'y': 88,
                                       'payload': {'text': 'Light reactions'}}},
            {'action': 'add', 'node': {'kind': 'path', 'x': 0, 'y': 0,
                                       'payload': {'points': [[0, 0], [40, 40], [80, 60]],
                                                   'colour': '#3E7A55', 'width': 2}}},
        ]})
    assert drawn.status_code == 200, drawn.text
    assert len(drawn.json()['board']['nodes']) == 3
    saved = wired.get(f'/api/v1/boards/{board_id}', headers=headers).json()['board']
    assert saved['nodes'], 'the diagram must have produced nodes'
    svg = wired.get(f'/api/v1/boards/{board_id}/export', headers=headers,
                    params={'format': 'svg'})
    assert svg.status_code == 200, svg.text
    assert b'<svg' in svg.content[:400]
    # The board is also a lesson bundle: the same drawing, portable out of the app.
    bundle = wired.get(f'/api/v1/boards/{board_id}/export', headers=headers,
                       params={'format': 'lesson'})
    assert bundle.status_code == 200 and bundle.content[:2] == b'PK'

    # -- 8. what this instance offers, and what it charges for --------------
    matrix = wired.get('/api/v1/capabilities', headers=headers)
    assert matrix.status_code == 200, matrix.text
    rows = {row['id']: row for row in matrix.json()['capabilities']}
    # The free tier really is free: nothing a learner needs to study is gated. A free
    # capability needs no entitlement row, so its state -- not `granted` -- is the
    # honest field to read.
    for capability_id in ('simulations', 'whiteboard_rich', 'flashcards_auto', 'pptx_export'):
        assert rows[capability_id]['tier'] == 'free', capability_id
        assert rows[capability_id]['state'] == capabilities.STATE_ENABLED, capability_id
    # And the paid ones are withheld with a reason, not a silent 404.
    assert rows['images']['granted'] is False
    assert rows['images']['reason']
    assert rows['images']['state'] == capabilities.STATE_WITHHELD
