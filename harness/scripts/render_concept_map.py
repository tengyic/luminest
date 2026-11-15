"""Draw the concept map that ``figures.concept_map`` computes but does not picture.

``concept_map`` returns the structure - the focus, its prerequisites, its dependants, its
siblings - with an empty ``figure`` field, so a caller that wants a picture has to make one.
This draws it from the payload alone: nothing is added that the payload does not contain.

    backend/.venv/bin/python -u scripts/render_concept_map.py --payload outputs/mindmap.json
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def wrap(text: str, width: int = 22) -> list[str]:
    words, lines, row = text.split(), [], ''
    for word in words:
        if len(row) + len(word) + 1 > width:
            lines.append(row)
            row = word
        else:
            row = f'{row} {word}'.strip()
    if row:
        lines.append(row)
    return lines[:3]


def box(x, y, w, h, label, *, fill, stroke, ink, size=13, bold=False, radius=10):
    lines = wrap(label)
    total = len(lines) * (size + 4)
    text = ''.join(
        f'<text x="{x + w / 2:.0f}" y="{y + h / 2 - total / 2 + (i + 1) * (size + 4) - 4:.0f}" '
        f'font-family="-apple-system, Helvetica, Arial" font-size="{size}" '
        f'font-weight="{700 if bold else 400}" fill="{ink}" text-anchor="middle">'
        f'{html.escape(line)}</text>'
        for i, line in enumerate(lines))
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.5"/>{text}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', default='outputs/mindmap.json')
    parser.add_argument('--out', default='outputs/mindmap.svg')
    args = parser.parse_args()

    payload = json.loads(Path(args.payload).read_text(encoding='utf-8'))
    width, height = 960, 540
    ink, accent = '#073046', '#fa5041'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#ffffff"/>']

    parts.append(f'<text x="48" y="46" font-family="-apple-system, Helvetica, Arial" '
                 f'font-size="11" fill="#8a877f" letter-spacing="1.2">CONCEPT MAP</text>')

    focus = payload.get('focus') or {}
    fx, fy, fw, fh = 330, 228, 300, 84
    parts.append(box(fx, fy, fw, fh, str(payload.get('title') or focus.get('label') or ''),
                     fill='#073046', stroke='#073046', ink='#ffffff', size=16, bold=True))

    def column(items, x, title, colour):
        if not items:
            return
        parts.append(f'<text x="{x + 60}" y="150" font-family="-apple-system, Helvetica, Arial" '
                     f'font-size="11" fill="#8a877f" text-anchor="middle">{title}</text>')
        top = 168
        for index, item in enumerate(items[:5]):
            y = top + index * 66
            parts.append(f'<line x1="{x + 140}" y1="{y + 26}" x2="{fx if x < fx else fx + fw}" '
                         f'y2="{fy + fh / 2}" stroke="{colour}" stroke-width="1" opacity="0.45"/>')
            parts.append(box(x, y, 140, 52, str(item.get('label') or ''), fill='#f8fafc',
                             stroke=colour, ink=ink, size=11))

    column(payload.get('prerequisites') or [], 48, 'COMES AFTER', '#5b7fa6')
    column(payload.get('dependants') or [], 772, 'UNLOCKS', '#4c8b6b')

    siblings = payload.get('siblings') or []
    if siblings:
        parts.append(f'<text x="{width / 2}" y="372" font-family="-apple-system, Helvetica, Arial" '
                     f'font-size="11" fill="#8a877f" text-anchor="middle">SAME UNIT</text>')
        span = min(len(siblings), 5)
        gap = 176
        start = width / 2 - (span - 1) * gap / 2 - 82
        for index in range(span):
            x = start + index * gap
            parts.append(f'<line x1="{x + 82}" y1="398" x2="{fx + fw / 2}" y2="{fy + fh}" '
                         f'stroke="#c9a227" stroke-width="1" opacity="0.4"/>')
            parts.append(box(x, 398, 164, 52, str(siblings[index].get('label') or ''),
                             fill='#fffdf5', stroke='#c9a227', ink=ink, size=10))

    note = (payload.get('steps') or [''])[0]
    parts.append(f'<text x="48" y="{height - 26}" font-family="-apple-system, Helvetica, Arial" '
                 f'font-size="11" fill="#6b7280">{html.escape(str(note)[:130])}</text>')
    parts.append('</svg>')

    out = Path(args.out)
    out.write_text(''.join(parts), encoding='utf-8')
    print(f'wrote {out}  '
          f"prereq={len(payload.get('prerequisites') or [])} "
          f"dependants={len(payload.get('dependants') or [])} "
          f"siblings={len(siblings)}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
