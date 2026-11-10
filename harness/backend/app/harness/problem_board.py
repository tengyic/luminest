"""Mount a canonical Problem onto a shared board (the Stage the teacher, learner and
tutor draw on together).

This is the seam between the structured-problem schema (``app.harness.problem``) and the
board node document (``app.harness.board``). A problem renders as a small set of board
nodes: its figure as a tikz ``visual``, its given equation as a tex ``visual``, the stem
as a ``text`` node, and each choice / acceptable answer as a ``text`` node.

Two boundaries, both deliberate:

* **Tutor-only fields are never board nodes.** ``figure_description`` is an annotation for
  the teacher about the figure; it lives on the problem card, where ``to_student()`` strips
  it. The board shows the figure itself (visible to teacher and learner alike); the
  annotation does not get painted, so it cannot leak through the shared canvas.
* **Role gating is not done here.** The board is shared, so the same nodes are visible to
  every role. Hiding ``figure_description`` from a learner is the API layer's job (it
  decides whether to send ``to_student()``), not the board's.

Choices are rendered as ``text`` nodes today - a read-only rendering. True interactive
selection (a learner tapping an option and the board recording the pick, feeding grading)
needs a new node kind (e.g. ``choice``); that is a follow-up, not a board-mounting concern.
The whiteboard *agent* writes to its own ``agent-scratch-*`` namespace and is intentionally
not wired into this board; mounting a problem onto a ``board-*`` Stage is the integration
point the teacher course session uses.
"""
from __future__ import annotations

from typing import Any

from . import board as node_boards
from .problem import Problem

_ACTOR_PREFIX = 'problem:'


def _actor(problem_id: str) -> str:
    return f'{_ACTOR_PREFIX}{problem_id}'


def _visual_node(kind: str, x: float, y: float, w: float, h: float, spec: dict[str, Any]) -> dict[str, Any]:
    # Pass the raw {type, title, spec} envelope; the board re-cleans it through
    # visual_specs.clean_visual_payload, so the derived status/provider/schema keys
    # must NOT be present here (they would be refused as a forged envelope).
    return {'kind': 'visual', 'x': x, 'y': y, 'w': w, 'h': h,
            'payload': {'type': kind, 'title': '', 'spec': spec}}


def render_problem_to_board(settings: Any, problem: Problem, board_id: str, *,
                            owner_id: str, problem_id: str,
                            start_x: float = 60.0, start_y: float = 60.0) -> dict[str, Any]:
    """Render ``problem`` onto ``board_id`` (creating the board if it is absent).

    Idempotent per ``problem_id``: a board that already carries this problem's nodes
    (``author`` == actor) is returned unchanged, so a re-render cannot duplicate them.
    Returns the board doc.

    ``board_id`` is the caller's choice of shared Stage - typically ``board-<concept_id>``.
    It is NOT the whiteboard agent's ``agent-scratch-*`` namespace.
    """
    actor = _actor(problem_id)
    doc = node_boards.load_owned(settings, board_id, owner_id)
    if doc is None:
        doc = node_boards.create(
            settings, owner_id=owner_id, board_id=board_id,
            title=f'Problem {problem_id}')
    else:
        if any(str(n.get('author', '')).startswith(actor) for n in doc.get('nodes', [])):
            return doc

    nodes: list[dict[str, Any]] = []
    y = start_y

    if problem.figure_svg:
        nodes.append(_visual_node(
            'tikz', start_x, y, 520, 380, {'source': problem.figure_svg}))
        y += 400
    if problem.given_equation:
        nodes.append(_visual_node(
            'tex', start_x, y, 360, 120,
            {'latex': problem.given_equation, 'display': True}))
        y += 140

    nodes.append({'kind': 'text', 'x': start_x, 'y': y,
                  'payload': {'text': problem.stem, 'size': 20}})
    y += 40

    choices = getattr(problem, 'choices', None) or []
    for choice in choices:
        label = choice.label
        text = choice.text or ''
        nodes.append({'kind': 'text', 'x': start_x, 'y': y,
                      'payload': {'text': f'{label}. {text}', 'size': 16}})
        y += 30

    acceptable = getattr(problem, 'acceptable_answers', None) or []
    for answer in acceptable:
        nodes.append({'kind': 'text', 'x': start_x, 'y': y,
                      'payload': {'text': f'accept: {answer}', 'size': 16}})
        y += 30

    mutations = [{'action': 'add', 'node': n} for n in nodes]
    updated, reason = node_boards.apply_mutations(
        settings, board_id, owner_id=owner_id,
        base_version=int(doc.get('version', 1)), mutations=mutations, actor=actor)
    if updated is None:
        raise RuntimeError(f'board.apply_mutations refused the problem render: {reason}')
    return updated


__all__ = ['render_problem_to_board']
