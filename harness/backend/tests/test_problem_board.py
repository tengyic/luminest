"""Integration test for mounting a Problem onto a real board (app.harness.board).

Exercises the actual node document + apply_mutations path with a temp data_dir, so the
node construction (tikz/tex visuals, stem + choice text nodes) and the per-problem
idempotency are checked against the canonical board validator rather than a mock.
"""
from __future__ import annotations

import pytest

from app.harness.problem import parse_problem
from app.harness.problem_board import render_problem_to_board


class _Settings:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir


def _mc_problem() -> dict:
    return {
        'stem': 'Which statement best describes a derivative?',
        'explanation': 'The derivative is the instantaneous rate of change.',
        'figure_svg': r'\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}',
        'given_equation': r'f^{\prime}(x) = \lim_{h\to0}\frac{f(x+h)-f(x)}{h}',
        'figure_description': 'Tutor-only: show the secant approaching the tangent.',
        'format': 'multipleChoice',
        'choices': [
            {'label': 'A', 'text': 'Instantaneous rate of change.'},
            {'label': 'B', 'text': 'An area under a curve.'},
            {'label': 'C', 'text': 'A discrete sum.'},
            {'label': 'D', 'text': 'A root of the function.'},
        ],
        'correct_label': 'A',
        'distractors': [{'mistake_type': 'conceptual'} for _ in range(3)],
    }


@pytest.fixture
def settings(tmp_path):
    return _Settings(data_dir=str(tmp_path))


def test_render_mounts_tikz_tex_stem_and_choices(settings):
    problem = parse_problem(_mc_problem())
    doc = render_problem_to_board(
        settings, problem, 'board-concept-1', owner_id='teacher', problem_id='q1')
    kinds = [n['kind'] for n in doc['nodes']]
    # 1 tikz + 1 tex + 1 stem text + 4 choice texts = 7
    assert kinds.count('visual') == 2
    assert kinds.count('text') == 5

    visual_types = {n['payload']['type'] for n in doc['nodes'] if n['kind'] == 'visual'}
    assert visual_types == {'tikz', 'tex'}
    tikz = next(n for n in doc['nodes'] if n['payload']['type'] == 'tikz')
    tex = next(n for n in doc['nodes'] if n['payload']['type'] == 'tex')
    assert tikz['payload']['spec']['source'] == problem.figure_svg
    assert tex['payload']['spec']['latex'] == problem.given_equation
    # the board re-cleans the visual and stores the enriched envelope; the core
    # {type,title,spec} triple is preserved with status/provider/schema derived.
    assert {'type', 'title', 'spec'} <= set(tex['payload'])

    texts = [n['payload']['text'] for n in doc['nodes'] if n['kind'] == 'text']
    assert texts[0] == problem.stem
    assert 'A. Instantaneous rate of change.' in texts


def test_render_is_idempotent_per_problem(settings):
    problem = parse_problem(_mc_problem())
    first = render_problem_to_board(
        settings, problem, 'board-concept-1', owner_id='teacher', problem_id='q1')
    first_count = len(first['nodes'])
    # Re-render the same problem onto the same board: no duplicate nodes.
    second = render_problem_to_board(
        settings, problem, 'board-concept-1', owner_id='teacher', problem_id='q1')
    assert len(second['nodes']) == first_count
    # A different problem_id adds its own nodes instead.
    other = parse_problem(_mc_problem())
    third = render_problem_to_board(
        settings, other, 'board-concept-1', owner_id='teacher', problem_id='q2')
    assert len(third['nodes']) == first_count + 7


def test_render_omits_fields_when_absent(settings):
    item = _mc_problem()
    item.pop('figure_svg')
    item.pop('given_equation')
    problem = parse_problem(item)
    doc = render_problem_to_board(
        settings, problem, 'board-concept-2', owner_id='teacher', problem_id='q3')
    assert all(n['payload']['type'] != 'tikz' for n in doc['nodes'] if n['kind'] == 'visual')
    assert all(n['payload']['type'] != 'tex' for n in doc['nodes'] if n['kind'] == 'visual')
