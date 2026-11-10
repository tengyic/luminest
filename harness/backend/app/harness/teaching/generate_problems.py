"""Generate a structured practice problem via the harness's *required* model.

This is the Lumen port of HeyAristotle's live structured-output generation. It
does **not** invent answers: when no model is configured it returns ``None`` (the
declared ``model-required`` state), and on any malformed model output it returns
``None`` rather than a half-parsed object. A generated problem is practice
material only — it is not signed with a receipt and is not scored server-side
unless the caller chooses to issue one.

Design notes for the port
-------------------------
* The renderer this harness ships is node/board + client-side TikZ (TikZJax WASM)
  and KaTeX-style inline math, so ``figure_svg`` is expected to carry TikZ source
  and needs **no** server-side ``/api/tikz`` compilation step — the existing
  visual host renders it. That is one place Lumen is already ahead of the
  server-compiled HeyAristotle flow.
* The contract below is the "Structured problem rendering contract" recovered
  from HeyAristotle's bundle, adapted to Lumen's renderer. It is the single
  source of truth for how the model must shape its output.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from ..provider import available, chat_tools
from .items import (
    Difficulty,
    Domain,
    Problem,
    problem_schema,
    validate_problem,
)

# The contract is reproduced (translated to English, substance preserved) from
# the HeyAristotle bundle. It is authoritative for what the model may emit.
# Raw string: the contract contains literal backslashes for \( ... \) / \[ ... \].
CONTRACT = r"""
You are a careful problem author for a tutoring harness. The learner sees a
renderer that supports plain text with authored line breaks, structured tables
and figures, and LaTeX math.

Text fields (stem, choices[].text, table cells, figure_caption, figure_description,
explanation) use plain text plus supported LaTeX. Only two Markdown forms are
recognised: **bold** and `single-backtick inline code` (short identifiers or
expressions). Other Markdown — italics, headings, list bullets, Markdown tables,
fenced code blocks, links, HTML tags — is shown literally, not parsed.

* Do not put multi-line programs in any field. Use blank lines, plain-text
  labels, and one item per line to organise.
* Tabular information belongs in the structured `table` field, not prose. Header
  cells set is_header:true. In-cell math uses \( ... \). The student-visible
  caption/notes go in table.caption, not in a separate stem paragraph.
* Necessary assumptions stay in the visible caption or stem. NEVER put them in
  the tutor-only figure_description.
* Do not build tables with Markdown/LaTeX table or array environments.
* If a multiple-choice option is itself a table, use that choice's structured
  `table` field — do not encode the table into choices[].text.
* Figures, curves, geometry and visualisations use `figure_svg`.
* When you use figure_svg you MUST also supply figure_description (tutor-only;
  it may contain the solution method and must NEVER be shown to the student).
* figure_caption holds only student-visible notes (units, "not drawn to scale").
* If the prompt asks for a figure/curve/diagram, produce that visual; do not
  substitute prose or a table.
* The stem is the "introduce + ask" prose. When a structured table or figure is
  present, refer to it naturally from the stem; do not copy its full content.
* Math formatting contract: wrap every piece of math in \( ... \) or \[ ... \].
  Wrap a whole relation at once (operators, absolute bars, bounds). Do not stitch
  plain-text operators into the middle of math.
* In SVG, declare fill="none" on strokes (or the fill a region expects). Do not
  rely on SVG's default black fill.
""".strip()


def generate_problem(
    settings: Any,
    *,
    title: str,
    summary: str = '',
    difficulty: Optional[Difficulty] = None,
    domain: Domain = Domain.GENERAL,
    with_figure: bool = False,
    history: Optional[Sequence[Mapping[str, str]]] = None,
) -> Optional[Problem]:
    """Produce one structured practice problem, or ``None``.

    Fail-closed on every path: no configured model, a model that returns nothing,
    a reply with no tool call, or output that fails validation all yield ``None``
    rather than a fabricated or partial item.
    """
    if not available(settings):
        return None

    user_lines = [f"Write one practice problem on the concept: {title}."]
    if summary:
        user_lines.append(
            f"Concept summary for grounding (do not copy verbatim): {summary}"
        )
    if difficulty is not None:
        user_lines.append(f"Target difficulty: {difficulty.value}")
    user_lines.append(f"Domain: {domain.value}")
    if with_figure:
        user_lines.append(
            "The problem needs a figure or diagram: include figure_svg (TikZ) and "
            "figure_description (tutor-only solution method)."
        )
    user_lines.append(
        "Respond ONLY by calling the generate_problem function with the structured object."
    )

    messages: list[dict[str, str]] = [
        {'role': 'system', 'content': "You are a careful mathematics problem author. " + CONTRACT},
        {'role': 'user', 'content': '\n'.join(user_lines)},
    ]
    if history:
        inserted = [{'role': str(m.get('role', 'user')), 'content': str(m.get('content', ''))}
                    for m in history]
        messages[1:1] = inserted

    schema = problem_schema()
    result = chat_tools(
        settings,
        messages,
        tools=[{
            'name': 'generate_problem',
            'description': 'Emit one structured practice problem matching the required schema.',
            'parameters': schema,
        }],
        tool_choice={'type': 'function', 'function': {'name': 'generate_problem'}},
        max_tokens=2000,
        temperature=0.3,
    )
    if result is None:
        return None
    calls = result.get('tool_calls') or []
    if not calls:
        return None
    arguments = calls[0].get('arguments')
    if not isinstance(arguments, dict):
        return None
    try:
        return validate_problem(arguments)
    except Exception:
        return None
