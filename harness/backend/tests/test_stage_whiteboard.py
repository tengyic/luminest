"""Stage whiteboard + TA tests. No network: every gate walks the refusal path, and
the TA runner is exercised through a stub so pool accounting is verified without a
provider."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.config import Settings
from app.harness import ta, toolbox, whiteboard as boards


# --------------------------------------------------------------------- fixtures

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


# ------------------------------------------------------------------- whiteboard

def test_board_creates_on_first_use(tmp_settings):
    doc = boards.load_or_create(tmp_settings, 'wb-equations', title='x')
    assert doc['version'] == 1
    assert doc['layers']['board']['ops'] == []
    assert boards.load(tmp_settings, 'wb-equations')['version'] == 1


def test_clean_op_rejects_bad_shapes(tmp_settings):
    space = dict(boards.DEFAULT_SPACE)
    assert boards.clean_op({'type': 'nuclear'}, space, layer='board') is None
    assert boards.clean_op({'type': 'path', 'points': [[0, 'x']]}, space, layer='board') is None
    assert boards.clean_op({'type': 'path', 'points': [[1, 2]] * 900}, space, layer='board') is None
    assert boards.clean_op({'type': 'text', 'text': 'hi', 'x': 0, 'y': 0}, space,
                           layer='student_ink') is None  # students may only path
    ok = boards.clean_op({'type': 'path', 'points': [[1, 2], [3, 4]]}, space,
                         layer='student_ink')
    assert ok is not None and ok['layer'] == 'student_ink'


def test_student_ink_layer_is_forced(tmp_settings):
    boards.load_or_create(tmp_settings, 'wb-x')
    doc = boards.apply_ops(tmp_settings, 'wb-x',
                           [{'type': 'path', 'points': [[0, 0], [10, 10]]}],
                           layer='student_ink', author='Ada')
    assert doc['layers']['student_ink']['ops'][0]['author'] == 'Ada'
    # A client-sent layer field cannot promote itself onto the board layer.
    op = {'type': 'path', 'points': [[0, 0], [1, 1]], 'layer': 'board'}
    doc = boards.apply_ops(tmp_settings, 'wb-x', [op], layer='student_ink', author='Ada')
    assert doc['layers']['student_ink']['ops'][-1]['layer'] == 'student_ink'
    assert doc['layers']['board']['ops'] == []


def test_board_layer_ops_round_trip(tmp_settings):
    boards.load_or_create(tmp_settings, 'wb-y')
    doc = boards.apply_ops(tmp_settings, 'wb-y', [
        {'type': 'text', 'text': 'y = mx + b', 'x': 10, 'y': 20},
        {'type': 'shape', 'shape': 'rect', 'x': 0, 'y': 0, 'w': 100, 'h': 60},
    ], layer='board', author='tutor')
    assert doc is not None and doc['version'] == 2
    assert len(doc['layers']['board']['ops']) == 2
    # text over the cap is dropped as a whole op
    doc = boards.apply_ops(tmp_settings, 'wb-y',
                           [{'type': 'text', 'text': 'x' * 201, 'x': 0, 'y': 0}],
                           layer='board', author='tutor')
    assert doc is None


def test_interrupts_raise_and_clear(tmp_settings):
    boards.load_or_create(tmp_settings, 'wb-z')
    doc = boards.raise_interrupt(tmp_settings, 'wb-z', user='Ada', message='stuck on step 2')
    assert len(doc['interrupts']) == 1
    doc = boards.clear_interrupts(tmp_settings, 'wb-z')
    assert doc['interrupts'] == []


# ------------------------------------------------------------- whiteboard tools

def test_whiteboard_tools_refuse_learners(tmp_settings):
    ctx = _Ctx(tmp_settings, _User(role='learner'))
    result = toolbox.invoke(ctx, 'whiteboard_write',
                            {'board_id': 'wb-x', 'text': 'hi', 'x': 0, 'y': 0})
    assert not result.ok and 'teacher-facing' in result.refused


def test_whiteboard_write_and_read(tmp_settings):
    teacher = _User()
    ctx = _Ctx(tmp_settings, teacher)
    boards.load_or_create(tmp_settings, 'wb-x')
    result = toolbox.invoke(ctx, 'whiteboard_write',
                            {'board_id': 'wb-x', 'text': 'slope = rise / run',
                             'x': 40, 'y': 60})
    assert result.ok, result.refused
    read = toolbox.invoke(ctx, 'whiteboard_read', {'board_id': 'wb-x'})
    assert read.ok
    assert any(op['type'] == 'text' for op in read.data['board_ops'])


def test_place_image_refused_when_pipeline_returns_nothing(tmp_settings, monkeypatch):
    # Stub the pipeline: this test is about the refusal path, not the network. Left
    # unstubbed it depended on the environment being offline, and the retired code only
    # "passed" because it dropped the acquired image's src and rejected its own op.
    from app.harness import media
    monkeypatch.setattr(media, 'acquire', lambda *a, **k: {
        'outcome': 'no_cleared_candidate', 'asset': None, 'notes': []})
    ctx = _Ctx(tmp_settings, _User())
    result = toolbox.invoke(ctx, 'whiteboard_place_image',
                            {'board_id': 'wb-x', 'query': 'anything'})
    assert not result.ok  # pipeline returned nothing → honest refusal, no fake URL


# --------------------------------------------------------------------------- TA

def test_ta_dispatch_requires_runner(tmp_settings):
    ta.configure(None) if hasattr(ta, 'configure') else None
    # runner unconfigured in a fresh import state only if never set; configure() binds a
    # module global, so restore a stub either way.
    ta.configure(lambda *a, **k: (_ for _ in ()).throw(AssertionError('not used')))


def test_ta_pool_cap_and_results(tmp_settings):
    ta._jobs.clear()
    gate = threading.Event()
    released = threading.Event()

    def slow_runner(message, concept_id, teacher_id):
        gate.wait(2)
        return {'summary': 'done', 'payload': {'summary': 'done', 'media': [],
                                               'cards': [{'kind': 'game', 'title': 'T'}]}}

    ta.configure(slow_runner)
    jobs = [ta.dispatch(f'job {i}', teacher_id='u1') for i in range(ta.MAX_JOBS)]
    with pytest.raises(ta.DispatchFull):
        ta.dispatch('one too many', teacher_id='u1')
    gate.set()
    released.set()
    deadline = time.time() + 5
    while time.time() < deadline and len(ta.results()) < ta.MAX_JOBS:
        time.sleep(0.02)
    results = ta.results()
    assert len(results) == ta.MAX_JOBS
    assert results[0]['result']['cards'][0]['kind'] == 'game'
    # cursor semantics: already-seen results are not re-delivered
    assert ta.results(since_version=results[-1]['created_at']) == []
    assert all(job['status'] in ('done', 'running') for job in ta.status())
