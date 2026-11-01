"""Vector rendering for generated figures.

The native client draws figures live in a canvas so a learner can drag a parameter and
watch the curve move. This module exists for the other direction: turning the same
payload into a self-contained SVG, so a figure can be dropped into a slide deck, printed
on a worksheet, or exported without the app.

Because both paths read the same payload, a printed figure and an on-screen figure cannot
disagree. The renderer also refuses to draw a scene as a curve: a fraction bar has no
series, and drawing an empty axis for it would be a lie about what the concept is.
"""

from __future__ import annotations

import html
from typing import Any, Mapping, Sequence

WIDTH = 640
HEIGHT = 400
PAD_LEFT = 56
PAD_RIGHT = 24
PAD_TOP = 28
PAD_BOTTOM = 44

INK = '#1f2430'
MUTED = '#6b7280'
GRID = '#e5e7eb'
PAPER = '#ffffff'
PRIMARY = '#2f6f6b'
ACCENT = '#b5651d'
SECONDARY = '#7b5ea7'


def _fmt(value: float) -> str:
    if value is None:
        return ''
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f'{value:.4g}'


def _nice(value: float) -> str:
    return html.escape(_fmt(value))


class Frame:
    """Maps data coordinates onto the drawing area."""

    def __init__(self, x_min: float, x_max: float, y_min: float, y_max: float,
                 width: int = WIDTH, height: int = HEIGHT):
        if x_max - x_min < 1e-9:
            x_min, x_max = x_min - 1, x_max + 1
        if y_max - y_min < 1e-9:
            y_min, y_max = y_min - 1, y_max + 1
        pad = 0.06 * (y_max - y_min)
        self.x_min, self.x_max = x_min, x_max
        self.y_min, self.y_max = y_min - pad, y_max + pad
        self.width, self.height = width, height

    def sx(self, x: float) -> float:
        span = self.x_max - self.x_min
        return PAD_LEFT + (x - self.x_min) / span * (self.width - PAD_LEFT - PAD_RIGHT)

    def sy(self, y: float) -> float:
        span = self.y_max - self.y_min
        return self.height - PAD_BOTTOM - (y - self.y_min) / span * (self.height - PAD_TOP - PAD_BOTTOM)


def _bounds(payload: Mapping[str, Any]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for pair in payload.get('series') or []:
        if pair and pair[0] is not None:
            xs.append(float(pair[0]))
        if pair and len(pair) > 1 and pair[1] is not None:
            ys.append(float(pair[1]))
    for series in payload.get('secondary_series') or []:
        for pair in series or []:
            if pair and pair[0] is not None:
                xs.append(float(pair[0]))
            if pair and len(pair) > 1 and pair[1] is not None:
                ys.append(float(pair[1]))
    for mark in payload.get('marks') or []:
        xs.append(float(mark.get('x', 0)))
        ys.append(float(mark.get('y', 0)))
    for root in (payload.get('features') or {}).get('roots') or []:
        xs.append(float(root))
        ys.append(0.0)
    for point in (payload.get('features') or {}).get('extrema') or []:
        xs.append(float(point.get('x', 0)))
        ys.append(float(point.get('y', 0)))
    if not xs or not ys:
        return -5.0, 5.0, -5.0, 5.0
    return min(xs), max(xs), min(ys), max(ys)


def _axes(frame: Frame) -> list[str]:
    parts = [f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{PAPER}"/>']
    ticks = 5
    for index in range(ticks + 1):
        y = PAD_TOP + index * (HEIGHT - PAD_TOP - PAD_BOTTOM) / ticks
        value = frame.y_max - index * (frame.y_max - frame.y_min) / ticks
        parts.append(f'<line x1="{PAD_LEFT}" y1="{y:.2f}" x2="{WIDTH-PAD_RIGHT}" y2="{y:.2f}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{PAD_LEFT-8}" y="{y+4:.2f}" font-size="11" fill="{MUTED}" '
                     f'text-anchor="end">{_nice(value)}</text>')
    for index in range(ticks + 1):
        x = PAD_LEFT + index * (WIDTH - PAD_LEFT - PAD_RIGHT) / ticks
        value = frame.x_min + index * (frame.x_max - frame.x_min) / ticks
        parts.append(f'<line x1="{x:.2f}" y1="{PAD_TOP}" x2="{x:.2f}" y2="{HEIGHT-PAD_BOTTOM}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{x:.2f}" y="{HEIGHT-PAD_BOTTOM+16}" font-size="11" fill="{MUTED}" '
                     f'text-anchor="middle">{_nice(value)}</text>')
    if frame.y_min <= 0 <= frame.y_max:
        y = frame.sy(0)
        parts.append(f'<line x1="{PAD_LEFT}" y1="{y:.2f}" x2="{WIDTH-PAD_RIGHT}" y2="{y:.2f}" '
                     f'stroke="{MUTED}" stroke-width="1.4"/>')
    if frame.x_min <= 0 <= frame.x_max:
        x = frame.sx(0)
        parts.append(f'<line x1="{x:.2f}" y1="{PAD_TOP}" x2="{x:.2f}" y2="{HEIGHT-PAD_BOTTOM}" '
                     f'stroke="{MUTED}" stroke-width="1.4"/>')
    return parts


def _polyline(frame: Frame, points: Sequence[Sequence[float | None]], colour: str,
              dashed: bool = False) -> list[str]:
    parts: list[str] = []
    run: list[str] = []
    for pair in points:
        if not pair or len(pair) < 2 or pair[1] is None:
            if len(run) > 1:
                parts.append(_path(run, colour, dashed))
            run = []
            continue
        run.append(f'{frame.sx(float(pair[0])):.2f},{frame.sy(float(pair[1])):.2f}')
    if len(run) > 1:
        parts.append(_path(run, colour, dashed))
    return parts


def _path(run: list[str], colour: str, dashed: bool) -> str:
    dash = ' stroke-dasharray="6 5"' if dashed else ''
    return (f'<polyline fill="none" stroke="{colour}" stroke-width="2.2" '
            f'stroke-linejoin="round" stroke-linecap="round"{dash} points="{" ".join(run)}"/>')


def _dot(frame: Frame, x: float, y: float, colour: str, label: str = '') -> str:
    parts = [f'<circle cx="{frame.sx(x):.2f}" cy="{frame.sy(y):.2f}" r="4" fill="{colour}"/>']
    if label:
        parts.append(f'<text x="{frame.sx(x)+8:.2f}" y="{frame.sy(y)-8:.2f}" font-size="11" '
                     f'fill="{colour}">{html.escape(label)}</text>')
    return ''.join(parts)


def figure_svg(payload: Mapping[str, Any], *, title: str = '', caption: str = '') -> str:
    """Render a simulation payload as a standalone SVG document."""
    kind = payload.get('figure', 'curve')
    if kind == 'scene':
        body = _scene(payload)
    else:
        body = _curve(payload)
    header = ''
    if title:
        header = (f'<text x="{PAD_LEFT}" y="20" font-size="14" font-weight="600" '
                  f'fill="{INK}">{html.escape(title)}</text>')
    footer = ''
    if caption:
        footer = (f'<text x="{PAD_LEFT}" y="{HEIGHT-10}" font-size="11" fill="{MUTED}">'
                  f'{html.escape(caption[:110])}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
            f'width="{WIDTH}" height="{HEIGHT}" role="img" '
            f'aria-label="{html.escape(title or "Generated figure")}">'
            f'{header}{"".join(body)}{footer}</svg>')


def _curve(payload: Mapping[str, Any]) -> list[str]:
    x_min, x_max, y_min, y_max = _bounds(payload)
    frame = Frame(x_min, x_max, y_min, y_max)
    parts = _axes(frame)
    parts.extend(_polyline(frame, payload.get('series') or [], PRIMARY))
    for series in payload.get('secondary_series') or []:
        parts.extend(_polyline(frame, series, SECONDARY, dashed=True))
    features = payload.get('features') or {}
    for root in features.get('roots') or []:
        if y_min <= 0 <= y_max:
            parts.append(_dot(frame, float(root), 0.0, ACCENT, f'x={_fmt(float(root))}'))
    for point in features.get('extrema') or []:
        parts.append(_dot(frame, float(point.get('x', 0)), float(point.get('y', 0)), ACCENT,
                          str(point.get('kind', ''))))
    probe = payload.get('probe')
    if probe and probe.get('y') is not None:
        parts.append(_dot(frame, float(probe['x']), float(probe['y']), INK,
                          f'f({_fmt(float(probe["x"]))})={_fmt(float(probe["y"]))}'))
    for mark in payload.get('marks') or []:
        parts.append(_dot(frame, float(mark.get('x', 0)), float(mark.get('y', 0)),
                          mark.get('colour', ACCENT), str(mark.get('label', ''))))
    return parts


def _scene(payload: Mapping[str, Any]) -> list[str]:
    """Draw part-whole rows. A scene has no axes because it has no function."""
    parts = [f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{PAPER}"/>']
    rows = payload.get('parts') or []
    if not rows:
        parts.append(f'<text x="{WIDTH//2}" y="{HEIGHT//2}" font-size="13" fill="{MUTED}" '
                     f'text-anchor="middle">No part-whole model was declared for this concept.</text>')
        return parts
    top = 64.0
    row_height = min(86.0, (HEIGHT - top - 96) / max(1, len(rows)))
    for index, row in enumerate(rows):
        y = top + index * row_height
        parts.append(f'<text x="{PAD_LEFT}" y="{y+14:.1f}" font-size="12" fill="{INK}">'
                     f'{html.escape(str(row.get("label", "")))}</text>')
        denominator = max(1, int(row.get('denominator', 1)))
        shaded = max(0, min(denominator, int(row.get('shaded', 0))))
        bar_width = WIDTH - PAD_LEFT - PAD_RIGHT
        cell = bar_width / denominator
        bar_y = y + 22
        bar_height = min(38.0, row_height - 40)
        colour = row.get('colour', 'primary')
        fill = PRIMARY if colour == 'primary' else (ACCENT if colour == 'accent' else SECONDARY)
        for cell_index in range(denominator):
            x = PAD_LEFT + cell_index * cell
            body = fill if cell_index < shaded else '#ffffff'
            parts.append(f'<rect x="{x:.2f}" y="{bar_y:.2f}" width="{cell:.2f}" '
                         f'height="{bar_height:.2f}" fill="{body}" stroke="{INK}" stroke-width="1"/>')
        note = row.get('note', '')
        if note:
            parts.append(f'<text x="{PAD_LEFT}" y="{bar_y+bar_height+15:.2f}" font-size="11" '
                         f'fill="{MUTED}">{html.escape(str(note)[:96])}</text>')
    for mark in payload.get('marks') or []:
        x, y = float(mark.get('x', 0)), float(mark.get('y', 0))
        if 0 <= x <= 1 and 0 <= y <= 1:
            parts.append(f'<circle cx="{PAD_LEFT + x*(WIDTH-PAD_LEFT-PAD_RIGHT):.2f}" '
                         f'cy="{HEIGHT-PAD_BOTTOM - y*(HEIGHT-PAD_BOTTOM-PAD_TOP):.2f}" r="4" '
                         f'fill="{ACCENT}"/>')
    return parts


def deck_svg(deck: Mapping[str, Any], *, figure: Mapping[str, Any] | None = None) -> str:
    """Render one slide as SVG: title, bullets and, when present, the concept figure."""
    title = str(deck.get('title', ''))
    bullets = [str(b) for b in (deck.get('bullets') or [])]
    formula = str(deck.get('formula', '') or '')
    parts = [f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{PAPER}"/>',
             f'<text x="40" y="56" font-size="22" font-weight="600" fill="{INK}">'
             f'{html.escape(title[:64])}</text>']
    y = 100.0
    for bullet in bullets[:7]:
        parts.append(f'<circle cx="46" cy="{y-5:.1f}" r="3" fill="{PRIMARY}"/>')
        parts.append(f'<text x="60" y="{y:.1f}" font-size="13" fill="{INK}">'
                     f'{html.escape(bullet[:96])}</text>')
        y += 30
    if formula:
        parts.append(f'<rect x="40" y="{y-6:.1f}" width="{WIDTH-80}" height="40" rx="8" '
                     f'fill="#f3f4f6"/>')
        parts.append(f'<text x="60" y="{y+20:.1f}" font-size="15" fill="{PRIMARY}">'
                     f'{html.escape(formula[:72])}</text>')
    if figure:
        # Embed the figure's *body*, not its document. Keeping the inner closing tag would
        # nest one SVG document inside another and produce markup no parser accepts.
        inner = figure_svg(figure, title='')
        body = inner[inner.index('>') + 1:]
        if body.endswith('</svg>'):
            body = body[:-len('</svg>')]
        parts.append(f'<g transform="translate(340,180) scale(0.44)">{body}</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
            f'width="{WIDTH}" height="{HEIGHT}" role="img" '
            f'aria-label="{html.escape(title or "Slide")}">{"".join(parts)}</svg>')
