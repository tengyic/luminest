#!/usr/bin/env python3
"""Layout lint for the deterministic figures.

A figure is a picture, so the honest way to review one is to look at it. That is also the
one thing a text-only review cannot do, which is how 57 lessons shipped with a title painted
over by their own background rectangle: every assertion in the test suite was about
arithmetic, and the arithmetic was right.

This script is the substitute that can run in CI. It parses the SVG each template emits,
turns every ``<text>`` into an estimated box (SVG has no text metrics until it is laid out,
so the estimate is deliberately conservative), and reports:

* text boxes that fall outside the canvas - a label clipped by the viewBox is a label the
  learner never sees;
* text boxes that overlap each other by more than a quarter of the smaller one - two labels
  on top of each other read as one wrong label;
* a title painted before the paper, or the plot painted over the title.

Exits non-zero when it finds a problem, so it can be a gate rather than a report nobody
reads. ``--verbose`` prints every figure, not only the ones with findings.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness import econ_figures  # noqa: E402

#: Average glyph advance as a fraction of the font size. Deliberately on the wide side: an
#: over-estimated box produces a warning, an under-estimated one hides a collision.
_ADVANCE = 0.56

_TEXT = re.compile(
    r'<text(?P<attrs>[^>]*)>(?P<body>[^<]*)</text>', re.S)
_ATTR = re.compile(r'(?P<name>[a-zA-Z-]+)="(?P<value>[^"]*)"')
_RECT = re.compile(r'<rect[^>]*fill="(?P<fill>[^"]+)"[^>]*/>')
_VIEWBOX = re.compile(r'viewBox="0 0 (?P<w>[\d.]+) (?P<h>[\d.]+)"')


@dataclass
class Box:
    left: float
    top: float
    right: float
    bottom: float
    text: str

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def intersect(self, other: 'Box') -> float:
        dx = min(self.right, other.right) - max(self.left, other.left)
        dy = min(self.bottom, other.bottom) - max(self.top, other.top)
        return dx * dy if dx > 0 and dy > 0 else 0.0


def _boxes(svg: str) -> list[Box]:
    out: list[Box] = []
    for match in _TEXT.finditer(svg):
        attrs = dict(_ATTR.findall(match.group('attrs')))
        body = (match.group('body') or '').strip()
        if not body:
            continue
        try:
            x = float(attrs.get('x', '0') or 0)
            y = float(attrs.get('y', '0') or 0)
            size = float(attrs.get('font-size', '12') or 12)
        except ValueError:
            continue
        width = _ADVANCE * size * len(body)
        anchor = attrs.get('text-anchor', 'start')
        if anchor == 'middle':
            left = x - width / 2
        elif anchor == 'end':
            left = x - width
        else:
            left = x
        # SVG's y is the baseline; the cap height above it is what the eye reads as the box.
        out.append(Box(left, y - size * 0.78, left + width, y + size * 0.22, body))
    return out


def examine(kind: str, *, title: str = '') -> list[str]:
    svg = econ_figures.render(kind, title=title)['svg']
    view = _VIEWBOX.search(svg)
    canvas_w = float(view.group('w')) if view else 640.0
    canvas_h = float(view.group('h')) if view else 400.0
    findings: list[str] = []

    paper = _RECT.search(svg)
    title_at = svg.find(f'>{title}</text>') if title else -1
    if title_at != -1 and paper:
        paper_at = svg.find(f'fill="{paper.group("fill")}"')
        if paper_at != -1 and paper_at > title_at:
            findings.append('the paper is painted after the title (the title is invisible)')

    boxes = _boxes(svg)
    for box in boxes:
        if box.left < -1 or box.right > canvas_w + 1:
            findings.append(
                f'text {box.text!r} runs outside the canvas horizontally '
                f'({box.left:.0f}..{box.right:.0f} of {canvas_w:.0f})')
        if box.top < -1 or box.bottom > canvas_h + 1:
            findings.append(
                f'text {box.text!r} runs outside the canvas vertically '
                f'({box.top:.0f}..{box.bottom:.0f} of {canvas_h:.0f})')

    ordered = sorted(boxes, key=lambda b: b.left)
    for index, first in enumerate(ordered):
        for second in ordered[index + 1:]:
            if second.left >= first.right:
                break
            overlap = first.intersect(second)
            if not overlap:
                continue
            smaller = min(first.width * first.height, second.width * second.height)
            ratio = overlap / smaller if smaller else 0.0
            if ratio >= 0.25:
                findings.append(
                    f'labels {first.text!r} and {second.text!r} overlap by {ratio:.0%}')
    return findings


def _kinds() -> list[str]:
    return sorted({kind for _, kind in econ_figures.RULES} | set(econ_figures.AXIS_FRAMES)
                  | {'payoff_matrix'})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verbose', action='store_true', help='print every figure')
    parser.add_argument('--kind', action='append', default=[], help='only this template')
    args = parser.parse_args(argv)

    kinds = args.kind or _kinds()
    total = 0
    dirty = 0
    for kind in kinds:
        for title in ('', 'A reasonably long figure title for the layout check'):
            findings = examine(kind, title=title)
            total += 1
            label = f'{kind}{" (titled)" if title else ""}'
            if findings:
                dirty += 1
                print(f'FAIL {label}')
                for finding in sorted(set(findings)):
                    print(f'     {finding}')
            elif args.verbose:
                print(f'ok   {label}')
    print(f'\n{total - dirty}/{total} figure renderings clean, {dirty} with findings')
    return 1 if dirty else 0


if __name__ == '__main__':
    raise SystemExit(main())
