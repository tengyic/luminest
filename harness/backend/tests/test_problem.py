"""Contract tests for the canonical structured-problem schema (app.harness.problem).

The schema mirrors the Aristotle (HeyAristotle) Zod contract recovered from its shipped
client bundle, and the generated-curriculum layer is expected to lift cleanly into it.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.generated_curriculum import as_problem
from app.harness.problem import (
    Choice, MistakeMeta, MultipleChoiceProblem, Problem, ProblemDomain, ProblemModule,
    FreeResponseProblem, parse_problem,
)


# ----------------------------------------------------------------- base contract

def _mc(**overrides) -> dict:
    base = {
        'stem': 'Which statement best describes a derivative?',
        'explanation': 'The derivative is the instantaneous rate of change.',
        'figure_svg': r'\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}',
        'given_equation': r'f^{\prime}(x) = \lim_{h\to0}\frac{f(x+h)-f(x)}{h}',
        'figure_description': 'Tutor-only: show the secant line approaching the tangent.',
        'figure_caption': 'The secant approaches the tangent.',
        'difficulty': 'medium',
        'module': 'Module 2 easy',
        'domain': 'sat_math',
        'format': 'multipleChoice',
        'choices': [
            {'label': 'A', 'text': 'Instantaneous rate of change.'},
            {'label': 'B', 'text': 'An area under a curve.'},
            {'label': 'C', 'text': 'A discrete sum.'},
            {'label': 'D', 'text': 'A root of the function.'},
        ],
        'correct_label': 'A',
        'distractors': [
            {'mistake_type': 'conceptual'},
            {'mistake_type': 'conceptual'},
            {'mistake_type': 'conceptual'},
        ],
    }
    base.update(overrides)
    return base


def test_parse_multiple_choice_discriminates():
    p = parse_problem(_mc())
    assert isinstance(p, MultipleChoiceProblem)
    assert p.format == 'multipleChoice'
    assert p.correct_label == 'A'
    assert len(p.choices) == 4
    assert p.module is ProblemModule.MODULE_2_EASY
    assert p.domain is ProblemDomain.SAT_MATH


def test_parse_free_response():
    fr = {
        'stem': 'State the definition of a limit.',
        'explanation': 'A limit captures the value a function approaches.',
        'format': 'freeResponse',
        'acceptable_answers': ['L = lim f(x)'],
        'distractors': [],
    }
    p = parse_problem(fr)
    assert isinstance(p, FreeResponseProblem)
    assert p.acceptable_answers == ['L = lim f(x)']


def test_correct_label_must_be_a_choice():
    with pytest.raises(ValidationError):
        parse_problem(_mc(correct_label='Z'))


def test_unknown_field_is_refused():
    affected = _mc(distractors=[{'mistake_type': 'x', 'bogus': 1}])
    with pytest.raises(ValidationError):
        parse_problem(affected)


def test_missing_discriminator_is_refused():
    bad = _mc()
    del bad['format']
    with pytest.raises(ValidationError):
        parse_problem(bad)


# ------------------------------------------------------------- tutor-only gating

def test_to_student_strips_figure_description():
    p = parse_problem(_mc())
    student = p.to_student()
    assert 'figure_description' not in student
    assert student['stem'] == p.stem
    assert student['figure_svg'] == p.figure_svg


def test_render_payloads_emits_tikz_and_tex():
    p = parse_problem(_mc())
    payloads = p.render_payloads()
    types = {pl['type'] for pl in payloads}
    assert types == {'tikz', 'tex'}
    tikz = next(pl for pl in payloads if pl['type'] == 'tikz')
    assert tikz['spec']['source'] == p.figure_svg
    tex = next(pl for pl in payloads if pl['type'] == 'tex')
    assert tex['spec']['latex'] == p.given_equation
    assert tex['spec']['display'] is True


def test_render_payloads_omit_empty_fields():
    p = parse_problem(_mc(given_equation=None, figure_svg=None))
    assert p.render_payloads() == []


def test_given_equation_refuses_unsafe_latex():
    # angle brackets are refused at parse time (the card must not accept markup); the
    # equation is rendered inline by KaTeX, never stored as a board node.
    with pytest.raises(ValidationError):
        parse_problem(_mc(given_equation='<script>bad</script>'))


# --------------------------------------------------------- generated-curriculum lift

def _generated_item() -> dict:
    return {
        'prompt': 'Which statement best describes momentum?',
        'explanation': 'Momentum is mass times velocity.',
        'options': [
            {'id': 'a', 'text': 'Mass times velocity.'},
            {'id': 'b', 'text': 'Mass times acceleration.'},
            {'id': 'c', 'text': 'Force divided by time.'},
            {'id': 'd', 'text': 'Energy per unit mass.'},
        ],
        'answer_id': 'a',
        'distractor_diagnoses': {
            'b': {'category': 'conceptual', 'reason': 'Confuses momentum with force.',
                  'next_action': 'Re-read.'},
            'c': {'category': 'conceptual', 'reason': 'Wrong formula.', 'next_action': 'Re-read.'},
            'd': {'category': 'conceptual', 'reason': 'Wrong quantity.', 'next_action': 'Re-read.'},
        },
    }


def test_as_problem_lifts_generated_item():
    item = _generated_item()
    p = as_problem(item)
    assert isinstance(p, MultipleChoiceProblem)
    assert p.stem == item['prompt']
    assert p.correct_label == 'a'
    assert len(p.choices) == 4
    # 3 wrong options -> 3 distractors, each carrying the diagnosis category as mistake_type
    assert len(p.distractors) == 3
    assert all(d.mistake_type == 'conceptual' for d in p.distractors)
    # no authored figure / equation on a generated item
    assert p.figure_svg is None
    assert p.given_equation is None
