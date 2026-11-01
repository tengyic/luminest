"""Render every diagram a stored course carries, as one page a reviewer can read.

Why this exists
---------------
The review copy (``author_course.py --render``) is the artifact a human approves, and it
interleaves fifty-seven lessons with three hundred and forty-two items. That is the right
shape for "is this a course" and the wrong shape for "is this figure honest": the diagram is
one block among eight, and judging fifty-seven of them means scrolling past everything else.

So this page is the other view: the figures alone, in teaching order, each with the concept
it belongs to and the caption that states its parameters. It is generated, never hand-edited,
and it fails loudly rather than skipping - a concept with no figure is printed as such,
because a sheet that silently omitted it would look like full coverage.

Usage::

    python scripts/render_figure_sheet.py ap_microeconomics --out ../outputs/figures.html

Reads the stored blueprint and rebuilds the deterministic layer, so it costs no model call
and no network request.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_course  # noqa: E402 - sibling script, imported for its course loader
from app.config import Settings  # noqa: E402
from app.harness.authoring import registry  # noqa: E402

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{ --paper:#F7F5EF; --ink:#1f2430; --muted:#6b7280; --rule:#dfdbd0; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
         font:16px/1.6 -apple-system, "Iowan Old Style", Georgia, serif; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 48px 28px 96px; }}
  h1 {{ font-size: 30px; line-height:1.2; margin:0 0 6px; }}
  .lede {{ color:var(--muted); font-size:14px; margin:0 0 34px; }}
  h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.09em; color:var(--muted);
        border-top:1px solid var(--rule); padding-top:14px; margin:44px 0 18px; }}
  figure {{ margin:0 0 34px; }}
  h3 {{ font-size:17px; margin:0 0 10px; }}
  svg {{ display:block; width:100%; height:auto; background:#fff;
         border:1px solid var(--rule); border-radius:8px; }}
  figcaption {{ font-size:13px; color:var(--muted); margin-top:8px; }}
  .none {{ border:1px dashed var(--rule); border-radius:8px; padding:14px; font-size:13px;
           color:var(--muted); }}
  .stats {{ font-size:13px; color:var(--muted); border:1px solid var(--rule);
            border-radius:8px; padding:12px 14px; margin-bottom:28px; }}
</style></head>
<body><main>
<h1>{title}</h1>
<p class="lede">Every diagram the stored course carries, in teaching order, with the
parameters each one is drawn from. Generated from the blueprint; no model wrote these.</p>
<p class="stats">{summary}</p>
{body}
</main></body></html>
"""


def _figure_block(concept_title: str, block: dict) -> str:
    svg = str(block.get('svg') or '')
    caption = str(block.get('body') or '')
    if not svg.startswith('<svg'):
        return (f'<figure><h3>{html.escape(concept_title)}</h3>'
                f'<div class="none">This concept carries a figure block with no drawing: '
                f'{html.escape(caption[:200])}</div></figure>')
    return (f'<figure><h3>{html.escape(concept_title)}</h3>{svg}'
            f'<figcaption>{html.escape(caption)}</figcaption></figure>')


def render_sheet(course) -> tuple[str, str]:
    """The page body and the one-line summary that has to agree with it."""
    body: list[str] = []
    with_figure = 0
    kinds: set[str] = set()
    for unit in course.plan.units:
        body.append(f'<h2>{html.escape(unit.title)}</h2>')
        for concept in unit.concepts:
            entry = course.concepts.get(concept.id) or {}
            figure = [block for block in entry.get('blocks') or []
                      if str(block.get('kind')) == 'figure']
            if not figure:
                body.append(f'<figure><h3>{html.escape(concept.title)}</h3>'
                            f'<div class="none">No diagram: no template models this concept, '
                            f'and a generic market picture would teach the opposite.</div>'
                            f'</figure>')
                continue
            with_figure += 1
            for block in figure:
                kinds.add(str(block.get('figure_kind') or '?'))
                body.append(_figure_block(concept.title, block))
    considered = course.concept_count
    summary = (f'{with_figure} of {considered} concepts carry a deterministic diagram, drawn '
               f'from {len(kinds)} distinct templates. Each caption states the parameters it '
               f'was drawn from, so the numbers on the page can be checked against the '
               f'lesson.')
    return ''.join(body), summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('course', help='stored authored course id, e.g. ap_microeconomics')
    parser.add_argument('--out', type=Path, required=True, help='where to write the page')
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    registry.hydrate(settings)
    record = registry.get(args.course)
    if record is None:
        print(f'no authored course {args.course!r}', file=sys.stderr)
        return 2
    course = author_course._course_for(record)
    if course is None:
        print(f'the stored blueprint for {args.course!r} no longer parses', file=sys.stderr)
        return 1
    body, summary = render_sheet(course)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(PAGE.format(title=f'{course.plan.title} — figures',
                                    summary=html.escape(summary), body=body),
                        encoding='utf-8')
    print(summary)
    print(f'figure sheet -> {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
