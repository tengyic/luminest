"""Tests for the HeyAristotle-style structured problem generation port.

Offline and fail-closed: the model is mocked, so no provider, network or receipt
signing is involved. These cover the schema contract (items.py) and the
generator's graceful degradation (generate_problems.py).
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from pydantic import ValidationError

from app.harness.teaching import generate_problems
from app.harness.teaching.items import (
    Difficulty,
    Domain,
    FreeResponseProblem,
    MultipleChoiceProblem,
    ProblemTable,
    TableCell,
    problem_schema,
    validate_problem,
)

VALID_MC = {
    'format': 'multipleChoice',
    'stem': 'What is \\(2 + 2\\)?',
    'explanation': 'Addition of two integers.',
    'choices': [
        {'label': 'A', 'text': '3'},
        {'label': 'B', 'text': '4'},
        {'label': 'C', 'text': '5'},
        {'label': 'D', 'text': '6'},
    ],
    'correct_label': 'B',
    'difficulty': 'Module 1',
    'domain': 'general',
}


# --------------------------------------------------------------- schema -----
def test_mc_valid():
    problem = validate_problem(VALID_MC)
    assert isinstance(problem, MultipleChoiceProblem)
    assert problem.correct_label == 'B'
    assert problem.difficulty is Difficulty.MODULE_1


def test_fr_valid():
    fr = validate_problem({
        'format': 'freeResponse',
        'stem': 'Solve \\(x + 1 = 4\\).',
        'explanation': 'Subtract one from both sides.',
        'acceptable_answers': ['3'],
        'domain': 'sat_math',
    })
    assert isinstance(fr, FreeResponseProblem)
    assert fr.acceptable_answers == ['3']
    assert fr.domain is Domain.SAT_MATH


def test_fr_rejects_non_numeric():
    with pytest.raises(ValidationError):
        validate_problem({
            'format': 'freeResponse',
            'stem': 'Name the theorem.',
            'explanation': 'It is the Pythagorean theorem.',
            'acceptable_answers': ['pythagoras'],  # not a number/fraction
        })


def test_mc_bad_label():
    bad = {**VALID_MC, 'choices': [
        {'label': 'Z', 'text': '3'},
        {'label': 'B', 'text': '4'},
        {'label': 'C', 'text': '5'},
        {'label': 'D', 'text': '6'},
    ]}
    with pytest.raises(ValidationError):
        validate_problem(bad)


def test_mc_wrong_choice_count():
    bad = {**VALID_MC, 'choices': [
        {'label': 'A', 'text': '3'},
        {'label': 'B', 'text': '4'},
        {'label': 'C', 'text': '5'},
    ]}
    with pytest.raises(ValidationError):
        validate_problem(bad)


def test_mc_correct_label_not_in_choices():
    # correct_label names a label that is not present among the choices.
    broken = {**VALID_MC, 'correct_label': 'Z'}
    with pytest.raises(ValidationError):
        validate_problem(broken)


def test_mc_choice_needs_content():
    # A choice with neither text nor a table must be rejected.
    broken = {**VALID_MC}
    broken = dict(broken)
    broken['choices'] = [
        {'label': 'A'},
        {'label': 'B', 'text': '4'},
        {'label': 'C', 'text': '5'},
        {'label': 'D', 'text': '6'},
    ]
    with pytest.raises(ValidationError):
        validate_problem(broken)


def test_to_learner_strips_tutor_only():
    problem = validate_problem({**VALID_MC, 'figure_description': 'Tell them to count on.'})
    learner = problem.to_learner()
    assert 'figure_description' not in learner
    assert learner['explanation'] == 'Addition of two integers.'


def test_problem_schema_is_self_contained():
    schema = problem_schema()
    blob = json.dumps(schema)
    assert '$ref' not in blob
    assert '$defs' not in schema
    # The union must be present so the model knows the two formats.
    assert any(k in schema for k in ('anyOf', 'oneOf'))


# ------------------------------------------------------------ generator -----
def _settings():
    return object()


def test_generator_returns_problem_when_provider_returns_call():
    with mock.patch.object(generate_problems, 'available', return_value=True), \
         mock.patch.object(generate_problems, 'chat_tools', return_value={
             'tool_calls': [{'id': '1', 'name': 'generate_problem', 'arguments': VALID_MC}]}):
        result = generate_problems.generate_problem(_settings(), title='addition')
    assert isinstance(result, MultipleChoiceProblem)
    assert result.correct_label == 'B'


def test_generator_returns_none_when_unavailable():
    with mock.patch.object(generate_problems, 'available', return_value=False):
        result = generate_problems.generate_problem(_settings(), title='addition')
    assert result is None


def test_generator_returns_none_when_no_tool_call():
    with mock.patch.object(generate_problems, 'available', return_value=True), \
         mock.patch.object(generate_problems, 'chat_tools', return_value={'tool_calls': []}):
        result = generate_problems.generate_problem(_settings(), title='addition')
    assert result is None


def test_generator_returns_none_on_malformed_args():
    with mock.patch.object(generate_problems, 'available', return_value=True), \
         mock.patch.object(generate_problems, 'chat_tools', return_value={
             'tool_calls': [{'id': '1', 'name': 'generate_problem',
                             'arguments': {**VALID_MC, 'choices': VALID_MC['choices'][:3]}}]}):
        result = generate_problems.generate_problem(_settings(), title='addition')
    assert result is None
