"""The teacher decides *what* and *when*; the server owns *which* lesson artifact.

A local 1.5B model reliably copies schema examples into identifier slots:
``whiteboard_write(board_id="board_id_example")`` and
``stage_surface(concept_id="concept_id_example")``. The whiteboard tool correctly
refuses the malformed id, so from the outside this looked like a broken whiteboard
when the actual defect was that the live lesson's identifiers were never bound to
the tool call. ``toolbox.invoke`` is the one gate every tool passes through, so the
binding lives there and is restricted to placeholder-shaped values: a real,
explicit id is a deliberate decision by the teacher and must survive untouched.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.harness import toolbox


def _ctx(**overrides):
    values = dict(surface='', client_context={'board_id': 'board-live-concept',
                                              'concept_id': 'live_concept'})
    values.update(overrides)
    return SimpleNamespace(**values)


def _install(monkeypatch, fn):
    monkeypatch.setattr(toolbox, 'REGISTRY', {'probe_tool': (object(), fn)})


def test_schema_example_board_id_is_replaced_by_the_live_board(monkeypatch):
    seen = {}

    def fn(ctx, *, board_id, text=''):
        seen['board_id'] = board_id
        return toolbox.ToolResult('probe_tool', True)

    _install(monkeypatch, fn)
    result = toolbox.invoke(_ctx(), 'probe_tool',
                            {'board_id': 'board_id_example', 'text': 'reinforcement'})
    assert seen['board_id'] == 'board-live-concept'
    assert result.ok is True
    assert any('Server-bound board_id' in note for note in result.notes)


def test_concept_id_placeholder_is_replaced(monkeypatch):
    seen = {}

    def fn(ctx, *, concept_id, reason=''):
        seen['concept_id'] = concept_id
        return toolbox.ToolResult('probe_tool', True)

    _install(monkeypatch, fn)
    toolbox.invoke(_ctx(), 'probe_tool', {'concept_id': 'concept_id_example', 'reason': 'draw'})
    assert seen['concept_id'] == 'live_concept'


def test_an_explicit_real_id_is_never_overwritten(monkeypatch):
    seen = {}

    def fn(ctx, *, board_id):
        seen['board_id'] = board_id
        return toolbox.ToolResult('probe_tool', True)

    _install(monkeypatch, fn)
    result = toolbox.invoke(_ctx(), 'probe_tool', {'board_id': 'board-another-concept'})
    assert seen['board_id'] == 'board-another-concept'
    assert result.notes == []


def test_omitted_identifier_is_bound_when_the_tool_declares_it(monkeypatch):
    seen = {}

    def fn(ctx, *, board_id):
        seen['board_id'] = board_id
        return toolbox.ToolResult('probe_tool', True)

    _install(monkeypatch, fn)
    toolbox.invoke(_ctx(), 'probe_tool', {})
    assert seen['board_id'] == 'board-live-concept'


def test_a_tool_without_identifiers_gets_no_extra_kwargs(monkeypatch):
    def fn(ctx, *, text=''):
        return toolbox.ToolResult('probe_tool', True, data={'text': text})

    _install(monkeypatch, fn)
    result = toolbox.invoke(_ctx(), 'probe_tool', {'text': 'hello'})
    assert result.ok is True, result.refused
    assert result.data == {'text': 'hello'}
    assert result.notes == []


def test_no_live_context_leaves_the_model_arguments_alone(monkeypatch):
    seen = {}

    def fn(ctx, *, board_id):
        seen['board_id'] = board_id
        return toolbox.ToolResult('probe_tool', True)

    _install(monkeypatch, fn)
    toolbox.invoke(_ctx(client_context=None), 'probe_tool',
                   {'board_id': 'board_id_example'})
    assert seen['board_id'] == 'board_id_example'


def test_invented_ids_that_are_not_placeholder_shaped_are_still_bound(monkeypatch):
    """The 1.5B model also emits ``lesson_1`` / ``board_1``. Spelling lists miss them;
    the board layer's own validity rule catches every unresolvable address."""
    seen = []

    def fn(ctx, *, board_id):
        seen.append(board_id)
        return toolbox.ToolResult('probe_tool', True)

    _install(monkeypatch, fn)
    for value in ('lesson_1', 'board_1', 'b1', 'my-board', '12345'):
        toolbox.invoke(_ctx(), 'probe_tool', {'board_id': value})
    assert seen == ['board-live-concept'] * 5


def test_an_unresolvable_context_board_is_not_injected(monkeypatch):
    seen = []

    def fn(ctx, *, board_id):
        seen.append(board_id)
        return toolbox.ToolResult('probe_tool', True)

    _install(monkeypatch, fn)
    toolbox.invoke(_ctx(client_context={'board_id': 'garbage'}), 'probe_tool',
                   {'board_id': 'board_id_example'})
    assert seen == ['board_id_example']


def test_placeholder_shapes_are_bound_and_real_ids_are_not(monkeypatch):
    seen = []

    def fn(ctx, *, board_id):
        seen.append(board_id)
        return toolbox.ToolResult('probe_tool', True)

    _install(monkeypatch, fn)
    for value in ('board_id_example', 'concept_id_example', 'your_board_id',
                  '<board_id>', 'placeholder', 'board_id', '  ', ''):
        toolbox.invoke(_ctx(), 'probe_tool', {'board_id': value})
    assert seen == ['board-live-concept'] * 8
    toolbox.invoke(_ctx(), 'probe_tool', {'board_id': 'board-live-concept'})
    assert seen[-1] == 'board-live-concept'
