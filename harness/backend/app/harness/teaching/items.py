"""Structured problem/question items, ported from HeyAristotle's Zod contract.

This mirrors the "Structured problem rendering contract" that HeyAristotle's
teacher model is constrained to emit (recovered from its client bundles). The
Lumen harness keeps an *authoritative, hand-authored* question bank
(see ``app.harness.toolbox.check_understanding``); generation here is a
**complement** used to extend practice material, never a silent replacement of
the bank. A generated item is not signed with a receipt and is not scored
server-side unless the caller chooses to issue one (see ``app.receipts``).

Two formats are supported, discriminated on ``format``:

* ``multipleChoice`` — a stem with four labelled choices (A–D) and a correct
  label; distractors are annotated with the error process they encode
  (``mistake_type``), which is what makes a generated MCQ diagnostically useful
  rather than a guess.
* ``freeResponse`` — a stem with one or more acceptable numeric answers
  (integer / decimal / fraction).

Both carry a **tutor-only** channel, ``figure_description``: solution method or
construction hints that must never be shown to a learner. Use
``Problem.to_learner()`` whenever an item is about to be rendered for a student.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Any, Literal, Mapping, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

__all__ = [
    'Difficulty',
    'Domain',
    'TableCell',
    'ProblemTable',
    'Choice',
    'Distractor',
    'ProblemBase',
    'MultipleChoiceProblem',
    'FreeResponseProblem',
    'Problem',
    'validate_problem',
    'problem_schema',
]

# ----------------------------------------------------------------- enums ----
class Difficulty(str, Enum):
    """SAT-style module/difficulty buckets (HeyAristotle family B)."""

    MODULE_1 = 'Module 1'
    MODULE_2_EASY = 'Module 2 easy'
    MODULE_2_HARD = 'Module 2 hard'


class Domain(str, Enum):
    """Subject domain the problem belongs to."""

    GENERAL = 'general'
    SAT_MATH = 'sat_math'


# A free-response answer must be a number or a simple fraction: integer, decimal
# (with or without leading zero) or "n/d". This is the family-B constraint that
# keeps generated FR answers machine-checkable without a CAS.
_NUMERIC_RE = re.compile(r'^-?(\d+(\.\d+)?|\.\d+|\d+/\d+)$')

# ----------------------------------------------------------------- table ----
class TableCell(BaseModel):
    model_config = ConfigDict(extra='forbid')

    text: str = Field(min_length=1)
    is_header: bool = False


class ProblemTable(BaseModel):
    model_config = ConfigDict(extra='forbid')

    caption: Optional[str] = None
    rows: list[list[TableCell]] = Field(min_length=1)


# --------------------------------------------------------------- choices ----
class Choice(BaseModel):
    """One multiple-choice option.

    Labels are constrained to A–D (family B). A choice may carry text, or a
    structured table when the option itself is tabular, but not both-empty.
    """

    model_config = ConfigDict(extra='forbid')

    label: Literal['A', 'B', 'C', 'D']
    text: Optional[str] = None
    table: Optional[ProblemTable] = None

    @model_validator(mode='after')
    def _needs_content(self) -> 'Choice':
        if not self.text and self.table is None:
            raise ValueError('a choice needs text or a table')
        return self


class Distractor(BaseModel):
    """A wrong answer with a reason.

    ``mistake_type`` names the error process the distractor encodes (MC). ``value``
    is a plausible-but-wrong numeric value (FR). Either may be present.
    """

    model_config = ConfigDict(extra='forbid')

    mistake_type: Optional[str] = None
    value: Optional[str] = None


# ------------------------------------------------------------- base item ----
class ProblemBase(BaseModel):
    model_config = ConfigDict(extra='forbid')

    stem: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    figure_svg: Optional[str] = None
    table: Optional[ProblemTable] = None
    given_equation: Optional[str] = None
    figure_description: Optional[str] = None  # tutor-only; never shown to learner
    figure_caption: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    domain: Domain = Domain.GENERAL

    def to_learner(self) -> dict[str, Any]:
        """Return the item with every tutor-only field stripped.

        The renderer for a learner must never receive ``figure_description``. The
        worked ``explanation`` is retained because, in this harness, a solution is
        surfaced only after an attempt through a separate, teacher-gated channel —
        not as part of the question itself.
        """
        data = self.model_dump(exclude_none=True)
        data.pop('figure_description', None)
        return data


# --------------------------------------------------------- format variants ---
class MultipleChoiceProblem(ProblemBase):
    format: Literal['multipleChoice'] = 'multipleChoice'
    choices: list[Choice] = Field(min_length=4, max_length=4)
    correct_label: Literal['A', 'B', 'C', 'D']
    distractors: list[Distractor] = Field(default_factory=list)

    @field_validator('choices')
    @classmethod
    def _exactly_four(cls, value: list[Choice]) -> list[Choice]:
        if len(value) != 4:
            raise ValueError('multipleChoice must have exactly 4 choices')
        return value

    @model_validator(mode='after')
    def _correct_in_choices(self) -> 'MultipleChoiceProblem':
        labels = {c.label for c in self.choices}
        if self.correct_label not in labels:
            raise ValueError('correct_label must match one of the choice labels')
        return self


class FreeResponseProblem(ProblemBase):
    format: Literal['freeResponse'] = 'freeResponse'
    acceptable_answers: list[str] = Field(min_length=1)
    distractors: list[Distractor] = Field(default_factory=list)

    @field_validator('acceptable_answers')
    @classmethod
    def _numeric_answers(cls, value: list[str]) -> list[str]:
        for answer in value:
            if not _NUMERIC_RE.match(answer):
                raise ValueError(
                    f'acceptable answer must be a number or fraction, got {answer!r}'
                )
        return value


# Discriminated union on ``format`` — exactly how HeyAristotle's Zod schema works.
Problem = Annotated[
    Union[MultipleChoiceProblem, FreeResponseProblem],
    Field(discriminator='format'),
]

_PROBLEM_ADAPTER: TypeAdapter = TypeAdapter(Problem)


def validate_problem(data: Mapping[str, Any]) -> 'Problem':
    """Validate an untrusted dict into a typed :class:`Problem`.

    Raises ``pydantic.ValidationError`` on any malformed input; callers that want
    a fail-closed path should catch and return ``None``.
    """
    return _PROBLEM_ADAPTER.validate_python(data)


def problem_schema() -> dict[str, Any]:
    """JSON schema for the Problem union (with local ``$ref``s inlined).

    OpenAI-compatible function-calling schemas accept ``$ref`` inconsistently;
    inlining the small local ``#/$defs`` keeps the schema portable.
    """
    raw = _PROBLEM_ADAPTER.json_schema()
    defs = raw.get('$defs', {})

    def _inline(node: Any) -> Any:
        if isinstance(node, dict):
            if '$ref' in node:
                key = str(node['$ref']).split('/')[-1]
                return _inline(defs.get(key, {}))
            return {k: _inline(v) for k, v in node.items() if k != '$defs'}
        if isinstance(node, list):
            return [_inline(v) for v in node]
        return node

    schema = _inline(raw)
    schema.pop('$defs', None)
    return schema
