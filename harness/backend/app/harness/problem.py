"""Canonical structured-problem schema, mirroring the Aristotle (HeyAristotle) Zod contract.

Reconstructed from the shipped client bundle ``41qsyyj-7sq3m.js`` (the Zod object at byte
offsets 29390-30192 and its system-prompt contract at 246-295, 26826) so the Luminest
teacher course session can author and serve the same shape of *structured, schema-validated*
problems - instruction + structured-output, not free chat.

Field-for-field mapping (Luminest snake_case wire shape on the left, Aristotle camelCase
on the right)::

    stem                 <-> stem
    explanation          <-> explanation
    figure_svg           <-> figureSvg          (the figure; carries TikZ source in Luminest)
    figure_description   <-> figureDescription   (TUTOR-ONLY: never sent to a learner)
    figure_caption       <-> figureCaption
    given_equation       <-> givenEquation       (a single LaTeX equation, rendered inline by the client's KaTeX)
    difficulty           <-> difficulty
    format               <-> format              (discriminated union key)
    choices[].label/text <-> choices[].label/text
    correct_label        <-> correctLabel
    distractors[].mistake_type <-> distractors[].mistakeType  (per-option error attribution)
    acceptable_answers   <-> acceptableAnswers   (free-response correct set)
    module / domain      <-> enum axes          (Aristotle's taxonomy; Luminest's native axis
                                                 is Course.subject_kind)

Two boundaries, copied from the source design:

* ``figure_description`` is tutor-only. ``to_student`` strips it so a learner payload can
  never leak the solution-annotation the author wrote for the teacher.
* ``render_payloads`` turns the renderable field (``figure_svg`` -> tikz) into the validated
  visual-spec payload the board already knows how to draw. ``given_equation`` is NOT a board
  node: it is rendered inline by the client's KaTeX from the problem card, so it carries no
  visual-spec payload here. Nothing here executes a spec; it only produces data the client
  renderer consumes.
"""
from __future__ import annotations

import enum
import re
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from . import visual_specs

# ``given_equation`` is a single LaTeX expression rendered inline by the client's KaTeX -
# never a board node. It is held to the same closed character set the board uses for LaTeX
# (visual_specs._LATEX_SAFE), with an explicit angle-bracket refusal because that regex
# intentionally permits '<' / '>' (plain TikZ arrows) but a problem card must not accept
# markup. Shell-escape and file-inclusion commands are refused outright.
_MAX_GIVEN_EQUATION_CHARS = 600
_LATEX_MARKUP = re.compile(r'[<>]')
_LATEX_FORBIDDEN = ('\\write18', '\\input{', '\\include{')


class ProblemModule(str, enum.Enum):
    """Aristotle's module/difficulty axis. Optional; Luminest's native axis is Course.subject_kind."""
    MODULE_1 = "Module 1"
    MODULE_2_EASY = "Module 2 easy"
    MODULE_2_HARD = "Module 2 hard"


class ProblemDomain(str, enum.Enum):
    """Aristotle's subject/domain axis."""
    GENERAL = "general"
    SAT_MATH = "sat_math"


class ProblemTableCell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    is_header: bool = False


class ProblemTable(BaseModel):
    """A small structured table (``choices[].table`` / base ``table``)."""
    model_config = ConfigDict(extra="forbid")
    rows: list[list[ProblemTableCell]] = Field(default_factory=list)
    caption: Optional[str] = None


class Choice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1)  # "A".."D"
    text: Optional[str] = Field(default=None, min_length=1)
    table: Optional[ProblemTable] = None


class MistakeMeta(BaseModel):
    """Per-distractor error attribution (Aristotle's ``mistakeType``)."""
    model_config = ConfigDict(extra="forbid")
    mistake_type: str = Field(min_length=1)


class ProblemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stem: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    figure_svg: Optional[str] = Field(default=None, min_length=1)
    table: Optional[ProblemTable] = None
    given_equation: Optional[str] = Field(default=None, min_length=1)
    figure_description: Optional[str] = Field(default=None, min_length=1)  # tutor-only
    figure_caption: Optional[str] = Field(default=None, min_length=1)
    difficulty: Optional[str] = Field(default=None, min_length=1)
    module: Optional[ProblemModule] = None
    domain: Optional[ProblemDomain] = None

    @field_validator('given_equation')
    @classmethod
    def _validate_given_equation(cls, v: Optional[str]) -> Optional[str]:
        """Hold the inline LaTeX to the board's closed LaTeX character set.

        ``given_equation`` is rendered by the client's KaTeX from the problem card - it is
        never a board node, so it does not go through ``visual_specs.clean_visual_payload``.
        It is still held to the same safety bar: ``visual_specs._LATEX_SAFE`` plus an explicit
        angle-bracket refusal (that regex intentionally permits '<' / '>' for plain TikZ
        arrows, but a problem card must reject markup) and a shell-escape / file-inclusion
        refusal.
        """
        if v is None:
            return v
        if len(v) > _MAX_GIVEN_EQUATION_CHARS:
            raise ValueError(
                f"given_equation exceeds {_MAX_GIVEN_EQUATION_CHARS} characters")
        if _LATEX_MARKUP.search(v) or not visual_specs._LATEX_SAFE.match(v):
            raise ValueError(
                "given_equation contains characters outside the safe LaTeX set")
        if any(token in v for token in _LATEX_FORBIDDEN):
            raise ValueError("given_equation contains a forbidden LaTeX command")
        return v

    def to_student(self) -> dict[str, Any]:
        """The learner-visible payload: ``figure_description`` is always removed."""
        return self.model_dump(exclude={"figure_description"}, mode="json")

    def render_payloads(self) -> list[dict[str, Any]]:
        """Validated visual-spec payloads for the renderable fields.

        ``figure_svg`` is emitted as a TikZ spec (Luminest's diagram renderer consumes TikZ
        source; a raw-SVG string would be refused by the validator and dropped).
        ``given_equation`` is NOT emitted here - it is rendered inline by the client's KaTeX
        from the problem card, not drawn as a board node.
        """
        out: list[dict[str, Any]] = []
        if self.figure_svg:
            node = visual_specs.clean_visual_payload(
                {"type": "tikz", "title": "", "spec": {"source": self.figure_svg}})
            if node is not None:
                out.append(node)
        return out


class MultipleChoiceProblem(ProblemBase):
    format: Literal["multipleChoice"] = "multipleChoice"
    choices: list[Choice] = Field(min_length=2, max_length=4)
    correct_label: str = Field(min_length=1)
    distractors: list[MistakeMeta] = Field(default_factory=list)

    def model_post_init(self, _info: Any) -> None:  # noqa: D401 - pydantic hook
        labels = {c.label for c in self.choices}
        if self.correct_label not in labels:
            raise ValueError(
                f"correct_label {self.correct_label!r} is not among choices {sorted(labels)!r}")


class FreeResponseProblem(ProblemBase):
    format: Literal["freeResponse"] = "freeResponse"
    acceptable_answers: list[str] = Field(min_length=1)
    distractors: list[MistakeMeta] = Field(default_factory=list)


#: Discriminated union on ``format`` - the same shape Aristotle uses (z.discriminatedUnion).
Problem = Annotated[
    Union[MultipleChoiceProblem, FreeResponseProblem],
    Field(discriminator="format"),
]

_PROBLEM_ADAPTER: TypeAdapter[Problem] = TypeAdapter(Problem)


def parse_problem(data: Any) -> "Problem":
    """Validate an untyped dict/JSON into the right Problem subclass via the discriminator."""
    return _PROBLEM_ADAPTER.validate_python(data)


def dump_problem(problem: "Problem") -> dict[str, Any]:
    """Serialise a Problem (enums -> values, tutor-only field included)."""
    return _PROBLEM_ADAPTER.dump_python(problem, mode="json")


__all__ = [
    "Problem", "ProblemBase", "ProblemModule", "ProblemDomain", "ProblemTable",
    "ProblemTableCell", "Choice", "MistakeMeta", "MultipleChoiceProblem",
    "FreeResponseProblem", "parse_problem", "dump_problem",
]
