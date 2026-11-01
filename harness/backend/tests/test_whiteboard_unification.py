"""The whiteboard unification: the tutor's tools and the learner's canvas meet on one
node board.

The defect this file pins down is that two boards existed — the tutor wrote an op-log
``wb-<concept>`` document and the canvas read a node ``board-<concept>`` document — so
the drawing never reached the learner. Every test here asserts the two names resolve
to the *same* document, or asserts a boundary that must survive the unification.

No network: the one media test stubs the acquire pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.config import Settings
from app.harness import board as node_boards
from app.harness import toolbox
from app.harness import whiteboard as boards


@pytest.fixture()
def tmp_settings(tmp_path):
    settings = Settings.from_env()
    object.__setattr__(settings, 'data_dir', tmp_path)
    return settings


class _User:
    def __init__(self, role='teacher', uid='u1', name='Teacher'):
        self.id = uid
        self.role = role
        self.name = name
        self.status = 'active'


class _Ctx:
    def __init__(self, settings, user):
        self.settings = settings
        self.user = user
        self.db = None
        self.client_context = {}


def _teacher(settings):
    return _Ctx(settings, _User(role='teacher', uid='u1'))


def _learner(settings):
    return _Ctx(settings, _User(role='learner', uid='u2', name='Ada'))


# ------------------------------------------------- two ids, one document

def test_wb_and_board_ids_resolve_to_one_document(tmp_settings):
    ctx = _teacher(tmp_settings)
    first = toolbox.invoke(ctx, 'whiteboard_write',
                           {'board_id': 'board-fractions', 'text': 'rise', 'x': 10, 'y': 10})
    assert first.ok, first.refused
    second = toolbox.invoke(ctx, 'whiteboard_write',
                            {'board_id': 'wb-fractions', 'text': 'run', 'x': 20, 'y': 20})
    assert second.ok, second.refused
    # Both spellings wrote the same board and the same id comes back.
    assert first.data['board_id'] == second.data['board_id'] == 'board-fractions'
    doc = node_boards.load(tmp_settings, 'board-fractions')
    assert doc is not None and len(doc['nodes']) == 2
    read = toolbox.invoke(ctx, 'whiteboard_read', {'board_id': 'wb-fractions'})
    assert read.ok and len(read.data['nodes']) == 2
    assert read.data['board_id'] == 'board-fractions'


def test_tutor_node_is_visible_on_the_learner_canvas_path(tmp_settings):
    ctx = _teacher(tmp_settings)
    result = toolbox.invoke(ctx, 'whiteboard_apply', {
        'board_id': 'wb-fractions',
        'ops': [{'type': 'shape', 'shape': 'rect', 'x': 0, 'y': 0, 'w': 100, 'h': 60},
                {'type': 'text', 'text': 'area model', 'x': 5, 'y': 5}]})
    assert result.ok, result.refused
    # board.load is exactly what the native canvas route reads through.
    doc = node_boards.load(tmp_settings, 'board-fractions')
    assert doc is not None
    assert [n['kind'] for n in doc['nodes']] == ['shape', 'text']
    assert all(n['id'] and n['z'] for n in doc['nodes'])


def test_move_survives_and_read_reflects_the_new_geometry(tmp_settings):
    ctx = _teacher(tmp_settings)
    assert toolbox.invoke(ctx, 'whiteboard_write',
                          {'board_id': 'wb-fractions', 'text': 'peak', 'x': 10, 'y': 10}).ok
    read = toolbox.invoke(ctx, 'whiteboard_read', {'board_id': 'wb-fractions'})
    node = read.data['nodes'][0]
    # The op-log board had no node ids, so this move was impossible; the node board
    # addresses the mark and the read sees the new geometry.
    doc, reason = node_boards.apply_mutations(
        tmp_settings, 'board-fractions', owner_id='u1',
        base_version=read.data['version'],
        mutations=[{'action': 'move', 'id': node['id'], 'x': 500, 'y': 400}])
    assert reason == ''
    read2 = toolbox.invoke(ctx, 'whiteboard_read', {'board_id': 'wb-fractions'})
    moved = next(n for n in read2.data['nodes'] if n['id'] == node['id'])
    assert (moved['x'], moved['y']) == (500.0, 400.0)


# ------------------------------------------------- boundaries that must survive

def test_non_teacher_is_refused_by_all_four_tools(tmp_settings):
    ctx = _learner(tmp_settings)
    calls = {
        'whiteboard_read': {'board_id': 'wb-fractions'},
        'whiteboard_apply': {'board_id': 'wb-fractions',
                             'ops': [{'type': 'text', 'text': 'hi', 'x': 0, 'y': 0}]},
        'whiteboard_write': {'board_id': 'wb-fractions', 'text': 'hi', 'x': 0, 'y': 0},
        'whiteboard_place_image': {'board_id': 'wb-fractions', 'query': 'cell'},
    }
    for name, args in calls.items():
        result = toolbox.invoke(ctx, name, args)
        assert not result.ok, name
        assert 'teacher-facing' in result.refused, (name, result.refused)
    # Nothing was written and no board was created for the learner.
    assert node_boards.load(tmp_settings, 'board-fractions') is None


def test_student_ink_refuses_text_and_accepts_path(tmp_settings):
    ctx = _teacher(tmp_settings)
    assert toolbox.invoke(ctx, 'whiteboard_write',
                          {'board_id': 'wb-fractions', 'text': 'x', 'x': 1, 'y': 1}).ok
    # A text op through the pen channel is refused in full.
    refused = boards.apply_ops(tmp_settings, 'wb-fractions',
                               [{'type': 'text', 'text': 'not allowed', 'x': 0, 'y': 0}],
                               layer='student_ink', author='Ada')
    assert refused is None
    # A path op lands — on the one node board, so the tutor's next read sees it.
    accepted = boards.apply_ops(tmp_settings, 'wb-fractions',
                                [{'type': 'path', 'points': [[0, 0], [5, 5]]}],
                                layer='student_ink', author='Ada')
    assert accepted is not None
    assert accepted['layers']['student_ink']['ops'][0]['author'] == 'Ada'
    assert accepted['layers']['student_ink']['ops'][0]['layer'] == 'student_ink'
    # The student's stroke is on the ink layer; it never became a board op.
    assert all(op['type'] != 'path' for op in accepted['layers']['board']['ops'])
    doc = node_boards.load(tmp_settings, 'board-fractions')
    assert any(n['kind'] == 'path' for n in doc['nodes'])


def test_place_image_withheld_places_nothing(tmp_settings, monkeypatch):
    from app.harness import media
    monkeypatch.setattr(media, 'acquire', lambda *a, **k: {
        'outcome': 'withheld', 'asset': None, 'notes': ['licence could not be cleared']})
    ctx = _teacher(tmp_settings)
    result = toolbox.invoke(ctx, 'whiteboard_place_image',
                            {'board_id': 'wb-fractions', 'query': 'cell diagram'})
    assert not result.ok
    assert 'withheld' in result.refused
    assert node_boards.load(tmp_settings, 'board-fractions') is None


def test_place_image_places_a_resolvable_cached_node(tmp_settings, monkeypatch):
    from app.harness import media
    sha = 'a' * 64
    monkeypatch.setattr(media, 'acquire', lambda *a, **k: {
        'outcome': 'downloaded',
        'asset': {'sha256': sha, 'title': 'Mitosis', 'width': 400, 'height': 300,
                  'attribution_text': 'A. Author', 'licence_code': 'CC BY 4.0',
                  'licence_class': 'cc_by', 'landing_page_url': 'https://example.test/x',
                  'source': 'wikimedia'},
        'notes': []})
    ctx = _teacher(tmp_settings)
    result = toolbox.invoke(ctx, 'whiteboard_place_image',
                            {'board_id': 'wb-fractions', 'query': 'mitosis'})
    assert result.ok, result.refused
    node = node_boards.load(tmp_settings, 'board-fractions')['nodes'][0]
    # The node carries the hash board.py resolves bitmaps by, so the canvas can render.
    assert node['kind'] == 'image'
    assert node['payload']['sha256'] == sha
    assert node['payload']['src'] == f'/api/v1/media/images/{sha}/bytes'
    assert node['payload']['credit'] == 'A. Author'


# ------------------------------------------------- the legacy shape

def test_legacy_shim_presents_the_node_board_and_survives_an_empty_one(tmp_settings):
    empty = boards.load_or_create(tmp_settings, 'wb-blank')
    assert empty['layers']['board']['ops'] == []
    assert empty['layers']['student_ink']['ops'] == []
    assert empty['version'] == 1

    ctx = _teacher(tmp_settings)
    assert toolbox.invoke(ctx, 'whiteboard_write',
                          {'board_id': 'wb-blank', 'text': 'slope', 'x': 5, 'y': 6}).ok
    view = boards.load(tmp_settings, 'wb-blank')
    assert any(op['type'] == 'text' and op['text'] == 'slope'
               for op in view['layers']['board']['ops'])
    assert view['layers']['student_ink']['ops'] == []


def test_read_digest_names_what_is_on_the_board(tmp_settings):
    ctx = _teacher(tmp_settings)
    assert toolbox.invoke(ctx, 'whiteboard_write',
                          {'board_id': 'wb-fractions', 'text': 'slope = rise / run',
                           'x': 40, 'y': 60}).ok
    assert boards.apply_ops(tmp_settings, 'wb-fractions',
                            [{'type': 'path', 'points': [[0, 0], [5, 5], [9, 1]]}],
                            layer='student_ink', author='Ada') is not None
    read = toolbox.invoke(ctx, 'whiteboard_read', {'board_id': 'wb-fractions'})
    digest = read.data['digest']
    assert 'slope = rise / run' in digest
    assert 'path of 3 points' in digest
    assert len(digest) <= boards.DIGEST_MAX_CHARS


def test_malformed_id_is_refused_not_created(tmp_settings):
    ctx = _teacher(tmp_settings)
    result = toolbox.invoke(ctx, 'whiteboard_write',
                            {'board_id': 'not-a-board', 'text': 'hi', 'x': 0, 'y': 0})
    assert not result.ok
    assert boards.concept_node_id('not-a-board') is None
    assert list((Path(tmp_settings.data_dir) / 'boards').glob('*.json')) == []
