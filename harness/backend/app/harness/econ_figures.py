"""Deterministic diagrams for economics concepts.

Why this module exists
----------------------
``app/figures.py`` dispatches figures by subject kind, and for every subject except
mathematics it deliberately answers with a concept map rather than a curve. That was the
right decision for physics: handed "Newton's second law", the symbolic engine returns a
parabola and labels it with the concept's name, which presents a meaningless curve as
though it were about the subject.

Economics is the exception that decision does not cover. The picture a learner needs for
tax incidence is not a function of one variable; it is a *market*: two curves, an
intersection, a wedge between what the buyer pays and the seller receives, two shaded
burdens and a deadweight triangle. A concept map cannot carry any of that, and a parabola
would be actively wrong. So economics gets its own small set of templates here, drawn
from stated parameters rather than fitted to data.

Three commitments, inherited from ``render`` and from the authoring audit:

**Every figure says what it assumes.** The parameters are in the caption ("D: P = 10 - Q,
S: P = 2 + Q, t = 2"), because a diagram with unstated slopes invites a learner to read
the burden split as a fact about the real world rather than a consequence of the
elasticities drawn.

**A concept with no honest diagram gets none.** :func:`for_concept` returns ``None``
rather than a generic market for a concept that is not about a market. The audit's rule
that a lesson must not show something it cannot justify applies here too.

**Deterministic.** The same concept always yields byte-identical SVG: no model call, no
randomness, no clock. A figure that changed between two renders of the same lesson would
make the lesson's provenance claim unverifiable.

Canvas conventions match :mod:`app.harness.render` so an economics figure and a
mathematics figure sit on a page without looking like two products.
"""

from __future__ import annotations

import html
from typing import Any

from .render import ACCENT, GRID, HEIGHT, INK, MUTED, PAD_BOTTOM, PAD_LEFT, PAD_RIGHT, \
    PAD_TOP, PAPER, PRIMARY, SECONDARY, WIDTH, Frame, _fmt

#: The default market every template starts from: demand slopes down at unit slope, supply
#: slopes up at unit slope, and they meet at (Q, P) = (4, 6). Symmetric slopes are chosen
#: on purpose: with equal slopes the tax burden splits exactly in half, so a learner can
#: check the incidence formula (Es / (Es + |Ed|) = 0.5) against the picture instead of
#: taking both on trust. The asymmetric case belongs in the lesson's worked example, where
#: the numbers can be argued about.
INTERCEPT = 10.0
SUPPLY_INTERCEPT = 2.0
SLOPE = 1.0
TAX = 2.0


def _frame() -> Frame:
    return Frame(0.0, INTERCEPT, 0.0, INTERCEPT)


def _axes(frame: Frame, *, x_label: str = 'Quantity', y_label: str = 'Price') -> list[str]:
    # No background rectangle here. The paper is painted by :func:`render` before anything
    # else, because a filled rect emitted mid-stream is an opaque plate: it was drawn after
    # the figure title and hid it in every figure that has axes.
    parts = [
        f'<line x1="{PAD_LEFT}" y1="{HEIGHT-PAD_BOTTOM}" x2="{WIDTH-PAD_RIGHT}" '
        f'y2="{HEIGHT-PAD_BOTTOM}" stroke="{INK}" stroke-width="1.4"/>',
        f'<line x1="{PAD_LEFT}" y1="{PAD_TOP}" x2="{PAD_LEFT}" '
        f'y2="{HEIGHT-PAD_BOTTOM}" stroke="{INK}" stroke-width="1.4"/>',
        f'<text x="{WIDTH-PAD_RIGHT}" y="{HEIGHT-PAD_BOTTOM+22}" font-size="12" '
        f'fill="{MUTED}" text-anchor="end">{html.escape(x_label)}</text>',
        f'<text x="{PAD_LEFT-8}" y="{PAD_TOP-8}" font-size="12" fill="{MUTED}" '
        f'text-anchor="end">{html.escape(y_label)}</text>',
    ]
    for value in range(1, int(round(frame.x_max))):
        parts.append(f'<line x1="{frame.sx(value):.2f}" y1="{PAD_TOP}" '
                     f'x2="{frame.sx(value):.2f}" y2="{HEIGHT-PAD_BOTTOM}" '
                     f'stroke="{GRID}" stroke-width="0.8"/>')
    for value in range(1, int(round(frame.y_max))):
        parts.append(f'<line x1="{PAD_LEFT}" y1="{frame.sy(value):.2f}" '
                     f'x2="{WIDTH-PAD_RIGHT}" y2="{frame.sy(value):.2f}" '
                     f'stroke="{GRID}" stroke-width="0.8"/>')
    return parts


def _curve(frame: Frame, fn, *, lo: float | None = None, hi: float | None = None,
           samples: int = 56, colour: str = PRIMARY, width: float = 2.4,
           dash: str = '') -> str:
    """A polyline sampled from ``fn``, for the shapes that are not straight lines.

    Sampled rather than described as an arc because an arc that is not quite the curve
    teaches the wrong curvature - and the curvature is the point of an isoquant.
    """
    lo = frame.x_min if lo is None else lo
    hi = frame.x_max if hi is None else hi
    points = [f'{frame.sx(lo + (hi - lo) * index / samples):.2f},'
              f'{frame.sy(fn(lo + (hi - lo) * index / samples)):.2f}'
              for index in range(samples + 1)]
    style = f' stroke-dasharray="{dash}"' if dash else ''
    return (f'<polyline fill="none" stroke="{colour}" stroke-width="{width}" '
            f'stroke-linecap="round"{style} points="{" ".join(points)}"/>')


def _bar(frame: Frame, x: float, top: float, *, base: float = 0.0, width: float = 0.62,
         fill: str = PRIMARY, opacity: str = '0.30') -> str:
    """A column from ``base`` up to ``top``, for the discrete-quantity figures.

    ``base`` is what lets two columns stack. Drawing each segment from zero instead would
    stack them translucently, so the bottom segment would show through the top one and the
    figure would claim a decomposition it is not showing.
    """
    left = frame.sx(x - width / 2)
    right = frame.sx(x + width / 2)
    upper = frame.sy(top)
    lower = frame.sy(base)
    return (f'<rect x="{left:.2f}" y="{upper:.2f}" width="{right-left:.2f}" '
            f'height="{lower-upper:.2f}" fill="{fill}" fill-opacity="{opacity}" '
            f'stroke="{fill}" stroke-width="1.2"/>')


def _line(frame: Frame, p0: tuple[float, float], p1: tuple[float, float],
          colour: str, *, dash: str = '', width: float = 2.2) -> str:
    style = f' stroke-dasharray="{dash}"' if dash else ''
    return (f'<line x1="{frame.sx(p0[0]):.2f}" y1="{frame.sy(p0[1]):.2f}" '
            f'x2="{frame.sx(p1[0]):.2f}" y2="{frame.sy(p1[1]):.2f}" '
            f'stroke="{colour}" stroke-width="{width}"{style} stroke-linecap="round"/>')


def _polygon(frame: Frame, points: list[tuple[float, float]], fill: str,
             opacity: str = '0.16', stroke: str = 'none') -> str:
    body = ' '.join(f'{frame.sx(x):.2f},{frame.sy(y):.2f}' for x, y in points)
    stroke_attr = f' stroke="{stroke}" stroke-width="1"' if stroke != 'none' else ''
    return (f'<polygon points="{body}" fill="{fill}" fill-opacity="{opacity}"'
            f'{stroke_attr}/>')


def _dot(frame: Frame, x: float, y: float, colour: str, label: str = '',
         *, dx: float = 8, dy: float = -8) -> str:
    parts = [f'<circle cx="{frame.sx(x):.2f}" cy="{frame.sy(y):.2f}" r="4" fill="{colour}"/>']
    if label:
        parts.append(f'<text x="{frame.sx(x)+dx:.2f}" y="{frame.sy(y)+dy:.2f}" '
                     f'font-size="11" fill="{colour}">{html.escape(label)}</text>')
    return ''.join(parts)


def _label(frame: Frame, x: float, y: float, text: str, colour: str,
           *, anchor: str = 'start', dy: float = 0) -> str:
    return (f'<text x="{frame.sx(x):.2f}" y="{frame.sy(y)+dy:.2f}" font-size="11.5" '
            f'fill="{colour}" text-anchor="{anchor}">{html.escape(text)}</text>')


def _dashed_guide(frame: Frame, x: float | None, y: float | None, colour: str = MUTED) -> list[str]:
    parts = []
    if x is not None:
        parts.append(f'<line x1="{frame.sx(x):.2f}" y1="{frame.sy(y or 0):.2f}" '
                     f'x2="{frame.sx(x):.2f}" y2="{HEIGHT-PAD_BOTTOM}" stroke="{colour}" '
                     f'stroke-width="1" stroke-dasharray="4 4"/>')
    if y is not None:
        parts.append(f'<line x1="{PAD_LEFT}" y1="{frame.sy(y):.2f}" x2="{frame.sx(x or 0):.2f}" '
                     f'y2="{frame.sy(y):.2f}" stroke="{colour}" stroke-width="1" '
                     f'stroke-dasharray="4 4"/>')
    return parts


# --------------------------------------------------------------------- templates

def _supply_demand(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
    parts.append(_line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT),
                       ACCENT))
    q = (INTERCEPT - SUPPLY_INTERCEPT) / 2
    p = INTERCEPT - q
    parts.extend(_dashed_guide(frame, q, p))
    parts.append(_dot(frame, q, p, INK, f'E ({_fmt(q)}, {_fmt(p)})'))
    parts.append(_label(frame, INTERCEPT - 0.4, 0.4, 'D', PRIMARY))
    parts.append(_label(frame, INTERCEPT - 0.4, INTERCEPT - SUPPLY_INTERCEPT - 0.4, 'S', ACCENT))
    return parts, 'Supply and demand with the equilibrium price and quantity.', {
        'demand': f'P = {_fmt(INTERCEPT)} - Q', 'supply': f'P = {_fmt(SUPPLY_INTERCEPT)} + Q',
        'quantity': q, 'price': p}


#: The lemons market. Three numbers decide the whole picture and each is stated in the
#: caption: what a good unit is worth to a buyer (7), what a lemon is worth (3), and the
#: value of an *average* unit, which is what a buyer can actually pay for when quality is
#: hidden: P = 6 - 0.5Q. The average-value line is drawn deliberately below what the owners
#: of good units require, because that gap *is* adverse selection - the good market does not
#: clear at a low price, it disappears.
GOOD_UNIT_VALUE = 7.0
LEMON_VALUE = 3.0
AVERAGE_INTERCEPT = 6.0
AVERAGE_SLOPE = 0.5


def _average_value(quantity: float) -> float:
    """What a buyer values an average unit at, given ``quantity`` offered."""
    return AVERAGE_INTERCEPT - AVERAGE_SLOPE * quantity


def _adverse_selection(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    """The market for lemons: selection, not a price that is merely too low.

    A supply-and-demand picture would be the wrong one here - the point of the concept is
    that the good half of the market stops existing rather than trading cheaply, and a
    generic two-curve diagram shows the opposite. So the good units and the lemons get one
    supply line each, and the single demand curve is the value of an *average* unit, which
    is all a buyer can know. Where that curve meets the lemons' line, trade happens; where
    it would need to meet the good units' line, it cannot get there.
    """
    parts = []
    # The band between what buyers can pay for the average unit and what the owners of a
    # good unit require. Its width is the whole argument: no price inside it clears.
    parts.append(_polygon(frame, [(0.0, AVERAGE_INTERCEPT), (0.0, GOOD_UNIT_VALUE),
                                  (frame.x_max, GOOD_UNIT_VALUE),
                                  (frame.x_max, _average_value(frame.x_max))],
                          SECONDARY, opacity='0.13'))
    parts.append(_line(frame, (0.0, AVERAGE_INTERCEPT),
                       (frame.x_max, _average_value(frame.x_max)), PRIMARY))
    parts.append(_line(frame, (0.0, GOOD_UNIT_VALUE), (frame.x_max, GOOD_UNIT_VALUE),
                       ACCENT, dash='7 4'))
    parts.append(_line(frame, (0.0, LEMON_VALUE), (frame.x_max, LEMON_VALUE), SECONDARY))
    q = (AVERAGE_INTERCEPT - LEMON_VALUE) / AVERAGE_SLOPE
    parts.extend(_dashed_guide(frame, q, LEMON_VALUE))
    parts.append(_dot(frame, q, LEMON_VALUE, INK, f'only lemons trade ({_fmt(q)}, '
                                                 f'{_fmt(LEMON_VALUE)})', dy=-10))
    parts.append(_label(frame, frame.x_max - 0.2, _average_value(9.6),
                        'value of an average unit', PRIMARY, anchor='end', dy=-6))
    parts.append(_label(frame, frame.x_max - 0.2, GOOD_UNIT_VALUE, 'good units need 7',
                        ACCENT, anchor='end', dy=-6))
    parts.append(_label(frame, frame.x_max - 0.2, LEMON_VALUE, 'lemons sell at 3',
                        SECONDARY, anchor='end', dy=+14))
    parts.append(_label(frame, 0.3, _average_value(0.8),
                        'buyers cannot reach the good units', MUTED, dy=-4))
    return parts, ('Buyers can only pay for the average unit, so their value sits below what '
                   'the owners of good units will accept: only lemons trade, and the market '
                   'for good units is missing rather than cheap.'), {
        'value_of_average_unit': f'P = {_fmt(AVERAGE_INTERCEPT)} - {_fmt(AVERAGE_SLOPE)}Q',
        'good_units_require': GOOD_UNIT_VALUE, 'lemons_require': LEMON_VALUE,
        'lemons_traded': q, 'price_of_a_lemon': LEMON_VALUE,
        'gap_at_zero_quantity': GOOD_UNIT_VALUE - AVERAGE_INTERCEPT}


def _shift(frame: Frame, *, which: str) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    shift = 2.0
    if which == 'demand':
        parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
        parts.append(_line(frame, (0, INTERCEPT + shift), (INTERCEPT - shift, 0), PRIMARY, dash='6 5'))
        parts.append(_line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT),
                           ACCENT))
        old_q = (INTERCEPT - SUPPLY_INTERCEPT) / 2
        new_q = (INTERCEPT + shift - SUPPLY_INTERCEPT) / 2
        note = 'Demand shifts right: at every price, buyers want more.'
        params = {'demand': f'P = {_fmt(INTERCEPT)} - Q', 'shifted_demand':
                  f'P = {_fmt(INTERCEPT+shift)} - Q', 'supply': f'P = {_fmt(SUPPLY_INTERCEPT)} + Q'}
    else:
        parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
        parts.append(_line(frame, (0, SUPPLY_INTERCEPT + shift),
                           (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT + shift), ACCENT, dash='6 5'))
        parts.append(_line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT),
                           ACCENT))
        old_q = (INTERCEPT - SUPPLY_INTERCEPT) / 2
        new_q = (INTERCEPT - SUPPLY_INTERCEPT - shift) / 2
        note = 'Supply shifts right (a fall in input cost): at every price, sellers offer more.'
        params = {'demand': f'P = {_fmt(INTERCEPT)} - Q', 'supply':
                  f'P = {_fmt(SUPPLY_INTERCEPT)} + Q', 'shifted_supply':
                  f'P = {_fmt(SUPPLY_INTERCEPT+shift)} + Q'}
    old_p = INTERCEPT - old_q
    new_p = INTERCEPT - new_q
    parts.extend(_dashed_guide(frame, old_q, old_p))
    parts.append(_dot(frame, old_q, old_p, MUTED, f'E0 ({_fmt(old_q)}, {_fmt(old_p)})'))
    parts.append(_dot(frame, new_q, new_p, INK, f'E1 ({_fmt(new_q)}, {_fmt(new_p)})'))
    params.update({'old_quantity': old_q, 'old_price': old_p,
                   'new_quantity': new_q, 'new_price': new_p})
    return parts, note, params


def _tax_wedge(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    demand = lambda q: INTERCEPT - SLOPE * q
    supply = lambda q: SUPPLY_INTERCEPT + SLOPE * q
    base_q = (INTERCEPT - SUPPLY_INTERCEPT) / (2 * SLOPE)
    buyer_pays = demand(base_q - TAX / 2)
    seller_keeps = supply(base_q - TAX / 2)
    wedge_q = base_q - TAX / 2
    parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
    parts.append(_line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT),
                       ACCENT))
    parts.append(_polygon(frame, [(0, buyer_pays), (wedge_q, buyer_pays),
                                  (0, seller_keeps)], ACCENT, '0.18'))
    parts.append(_polygon(frame, [(wedge_q, buyer_pays), (base_q, INTERCEPT - base_q),
                                  (wedge_q, seller_keeps)], SECONDARY, '0.22'))
    parts.extend(_dashed_guide(frame, wedge_q, None))
    parts.extend(_dashed_guide(frame, base_q, INTERCEPT - base_q))
    parts.append(_line(frame, (wedge_q, seller_keeps), (wedge_q, buyer_pays), INK, width=3.0))
    parts.append(_dot(frame, wedge_q, buyer_pays, PRIMARY, f'buyer pays {_fmt(buyer_pays)}', dy=-8))
    parts.append(_dot(frame, wedge_q, seller_keeps, ACCENT, f'seller keeps {_fmt(seller_keeps)}',
                      dy=16))
    parts.append(_dot(frame, base_q, INTERCEPT - base_q, MUTED,
                      f'no-tax E ({_fmt(base_q)}, {_fmt(INTERCEPT-base_q)})', dy=-10))
    # Both wedge labels sit to the left of the vertical they describe, anchored on its end.
    # The three point labels (buyer pays, seller keeps, no-tax E) all live to the right of
    # x = 3, and putting the wedge text there too produced four labels in a column that a
    # reader has to untangle. Left of the wedge the canvas is empty.
    parts.append(_label(frame, wedge_q - 0.2, (buyer_pays + seller_keeps) / 2, 'tax wedge',
                        INK, anchor='end'))
    parts.append(_label(frame, wedge_q + 0.55, (INTERCEPT - base_q + seller_keeps) / 2 - 0.2,
                        'deadweight loss', SECONDARY))
    share = 0.5
    return parts, (f'A per-unit tax of {_fmt(TAX)} drives a wedge between the price buyers pay '
                   f'and the price sellers keep. With the slopes drawn equal, each side bears '
                   f'half the burden; the triangle is the surplus nobody gets.') , {
        'demand': f'P = {_fmt(INTERCEPT)} - Q', 'supply': f'P = {_fmt(SUPPLY_INTERCEPT)} + Q',
        'tax': TAX, 'buyer_price': buyer_pays, 'seller_price': seller_keeps,
        'quantity': wedge_q, 'buyer_share': share, 'seller_share': share,
        'deadweight_loss': 0.5 * TAX * (base_q - wedge_q)}


def _price_control(frame: Frame, *, ceiling: bool) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    demand = lambda q: INTERCEPT - SLOPE * q
    supply = lambda q: SUPPLY_INTERCEPT + SLOPE * q
    base_q = (INTERCEPT - SUPPLY_INTERCEPT) / (2 * SLOPE)
    base_p = demand(base_q)
    limit = base_p - 1.5 if ceiling else base_p + 1.5
    q_supply = (limit - SUPPLY_INTERCEPT) / SLOPE
    q_demand = (INTERCEPT - limit) / SLOPE
    parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
    parts.append(_line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT),
                       ACCENT))
    parts.append(_line(frame, (0, limit), (INTERCEPT, limit), INK, width=2.0, dash='7 4'))
    parts.append(_dot(frame, base_q, base_p, MUTED, f'E ({_fmt(base_q)}, {_fmt(base_p)})'))
    low, high = sorted((q_supply, q_demand))
    parts.append(f'<line x1="{frame.sx(low):.2f}" y1="{frame.sy(limit)-14:.2f}" '
                 f'x2="{frame.sx(high):.2f}" y2="{frame.sy(limit)-14:.2f}" stroke="{SECONDARY}" '
                 f'stroke-width="2"/>')
    parts.append(_label(frame, (low + high) / 2, limit, 'shortage' if ceiling else 'surplus',
                        SECONDARY, anchor='middle', dy=-20))
    parts.append(_label(frame, INTERCEPT - 0.35, limit, f'{"ceiling" if ceiling else "floor"} '
                        f'{_fmt(limit)}', INK, anchor='end', dy=-6))
    return parts, ('A binding price ceiling below equilibrium: quantity supplied falls short '
                   'of quantity demanded, and the gap is the shortage.' if ceiling else
                   'A binding price floor above equilibrium: quantity supplied exceeds '
                   'quantity demanded, and the gap is the surplus.'), {
        'demand': f'P = {_fmt(INTERCEPT)} - Q', 'supply': f'P = {_fmt(SUPPLY_INTERCEPT)} + Q',
        'limit': limit, 'quantity_demanded': q_demand, 'quantity_supplied': q_supply,
        'gap': abs(q_demand - q_supply)}


def _surplus(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    base_q = (INTERCEPT - SUPPLY_INTERCEPT) / 2
    base_p = INTERCEPT - base_q
    parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
    parts.append(_line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT),
                       ACCENT))
    parts.append(_polygon(frame, [(0, base_p), (0, INTERCEPT), (base_q, base_p)], PRIMARY, '0.20'))
    parts.append(_polygon(frame, [(0, base_p), (0, SUPPLY_INTERCEPT), (base_q, base_p)], ACCENT,
                          '0.20'))
    parts.extend(_dashed_guide(frame, base_q, base_p))
    parts.append(_dot(frame, base_q, base_p, INK, f'E ({_fmt(base_q)}, {_fmt(base_p)})'))
    parts.append(_label(frame, base_q * 0.30, base_p + 1.1, 'consumer surplus', PRIMARY))
    parts.append(_label(frame, base_q * 0.30, base_p - 1.2, 'producer surplus', ACCENT))
    return parts, ('Consumer surplus is the area under demand and above the price; producer '
                   'surplus is the area above supply and below the price.'), {
        'demand': f'P = {_fmt(INTERCEPT)} - Q', 'supply': f'P = {_fmt(SUPPLY_INTERCEPT)} + Q',
        'price': base_p, 'quantity': base_q,
        'consumer_surplus': 0.5 * base_q * (INTERCEPT - base_p),
        'producer_surplus': 0.5 * base_q * (base_p - SUPPLY_INTERCEPT)}


def _elasticity(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    steep = lambda q: INTERCEPT - 3.0 * q
    flat = lambda q: 8.0 - 0.5 * q
    parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT / 3.0, 0), PRIMARY))
    parts.append(_line(frame, (0, 8.0), (INTERCEPT, 8.0 - 0.5 * INTERCEPT), SECONDARY, dash='6 5'))
    price_high, price_low = 7.0, 6.0
    for price in (price_high, price_low):
        parts.append(_line(frame, (0, price), (INTERCEPT, price), GRID, width=1.0))
    q_steep_high = (INTERCEPT - price_high) / 3.0
    q_steep_low = (INTERCEPT - price_low) / 3.0
    q_flat_high = (8.0 - price_high) / 0.5
    q_flat_low = (8.0 - price_low) / 0.5
    parts.append(_dot(frame, q_steep_high, price_high, PRIMARY, 'inelastic: small change in Q'))
    parts.append(_dot(frame, min(q_flat_high, 9.6), price_high, SECONDARY,
                      'elastic: large change in Q', dy=18))
    parts.append(_label(frame, INTERCEPT - 2.2, INTERCEPT - 1.0, 'steep D (inelastic)', PRIMARY))
    parts.append(_label(frame, 5.0, 7.9, 'flat D (elastic)', SECONDARY))
    return parts, ('The same price fall produces a small quantity response on the steep curve '
                   'and a large one on the flat curve. Elasticity is that ratio, not the slope '
                   'alone.'), {
        'steep_demand': f'P = {_fmt(INTERCEPT)} - 3Q',
        'flat_demand': 'P = 8 - 0.5Q',
        'price_change': round(price_high - price_low, 4),
        'quantity_change_inelastic': round(q_steep_low - q_steep_high, 4),
        'quantity_change_elastic': round(q_flat_low - q_flat_high, 4)}


def _ppf(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    points = []
    for index in range(41):
        share = index / 40.0
        x = INTERCEPT * share
        y = INTERCEPT * (1 - share ** 2) ** 0.5
        points.append(f'{frame.sx(x):.2f},{frame.sy(y):.2f}')
    parts.append(f'<polyline fill="none" stroke="{PRIMARY}" stroke-width="2.4" '
                 f'points="{" ".join(points)}"/>')
    parts.append(_polygon(frame, [(0, 0), (INTERCEPT, 0), (0, INTERCEPT)], PRIMARY, '0.08'))
    ax, ay = 4.0, INTERCEPT * (1 - 0.16) ** 0.5
    bx, by = 7.0, INTERCEPT * (1 - 0.49) ** 0.5
    parts.append(_dot(frame, ax, ay, INK, f'A ({_fmt(ax)}, {_fmt(ay)})'))
    parts.append(_dot(frame, bx, by, ACCENT, f'B ({_fmt(bx)}, {_fmt(by)})', dy=16))
    # The long name does not fit beside the point labelled A without crossing it, and the
    # caption spells the frontier out anyway: a diagram label is a pointer, not a subtitle.
    parts.append(_label(frame, 0.4, 9.3, 'frontier', PRIMARY))
    return parts, ('Moving from A to B along the frontier buys more of the horizontal good at '
                   'the cost of the vertical good; the frontier bows out because resources '
                   'are not equally suited to both.'), {
        'frontier': 'x^2 + y^2 = 100 (illustrative, bowed out)',
        'from': {'x': ax, 'y': round(ay, 3)}, 'to': {'x': bx, 'y': round(by, 3)}}


def _externality(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    demand = lambda q: INTERCEPT - SLOPE * q
    private = lambda q: SUPPLY_INTERCEPT + SLOPE * q
    external_cost = 2.0
    social = lambda q: private(q) + external_cost
    market_q = (INTERCEPT - SUPPLY_INTERCEPT) / (2 * SLOPE)
    social_q = (INTERCEPT - SUPPLY_INTERCEPT - external_cost) / (2 * SLOPE)
    parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
    parts.append(_line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT),
                       ACCENT))
    parts.append(_line(frame, (0, SUPPLY_INTERCEPT + external_cost),
                       (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT + external_cost), ACCENT,
                       dash='6 5'))
    parts.append(_polygon(frame, [(social_q, social(social_q)), (market_q, demand(market_q)),
                                  (social_q, social(market_q))], SECONDARY, '0.22'))
    parts.extend(_dashed_guide(frame, social_q, social(social_q)))
    parts.append(_dot(frame, market_q, demand(market_q), MUTED,
                      f'market Q {_fmt(market_q)}'))
    parts.append(_dot(frame, social_q, social(social_q), INK,
                      f'social optimum {_fmt(social_q)}', dy=-10))
    parts.append(_label(frame, INTERCEPT - 2.0, INTERCEPT - 1.2, 'MSB = demand', PRIMARY))
    parts.append(_label(frame, INTERCEPT - 2.4, INTERCEPT - SUPPLY_INTERCEPT - 1.0,
                        'MPC = supply', ACCENT))
    # The wedge itself is three points wide, so its name goes to the left of it: the only
    # space inside it is the size of the text.
    parts.append(_label(frame, 1.7, demand(market_q) + 0.6, 'deadweight loss', SECONDARY))
    return parts, ('The private supply curve leaves out the external cost, so the market '
                   'trades past the point where marginal social cost equals marginal social '
                   'benefit. The shaded triangle is the loss that gap creates.'), {
        'demand_msb': f'P = {_fmt(INTERCEPT)} - Q',
        'private_cost': f'P = {_fmt(SUPPLY_INTERCEPT)} + Q',
        'external_cost': external_cost,
        'market_quantity': market_q, 'social_quantity': social_q}


def _cost_curves(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    fixed = 6.0

    def mc(q: float) -> float:
        return 1.0 + 0.8 * q

    def atc(q: float) -> float:
        return fixed / q + 1.0 + 0.4 * q

    mc_points = []
    atc_points = []
    for index in range(1, 91):
        q = index * 0.1
        y_mc, y_atc = mc(q), atc(q)
        if 0 < y_mc <= INTERCEPT:
            mc_points.append(f'{frame.sx(q):.2f},{frame.sy(y_mc):.2f}')
        if 0 < y_atc <= INTERCEPT:
            atc_points.append(f'{frame.sx(q):.2f},{frame.sy(y_atc):.2f}')
    parts.append(f'<polyline fill="none" stroke="{ACCENT}" stroke-width="2.2" '
                 f'points="{" ".join(mc_points)}"/>')
    parts.append(f'<polyline fill="none" stroke="{PRIMARY}" stroke-width="2.2" '
                 f'points="{" ".join(atc_points)}"/>')
    low, high = 0.5, 9.0
    for _ in range(40):
        middle = (low + high) / 2
        if mc(middle) < atc(middle):
            low = middle
        else:
            high = middle
    minimum_q = (low + high) / 2
    minimum_y = atc(minimum_q)
    parts.append(_dot(frame, minimum_q, minimum_y, INK,
                      f'minimum efficient scale {_fmt(round(minimum_q, 2))}', dy=-10))
    parts.extend(_dashed_guide(frame, minimum_q, minimum_y))
    parts.append(_label(frame, INTERCEPT - 2.2, mc(INTERCEPT - 2.2) + 0.3, 'MC', ACCENT))
    parts.append(_label(frame, INTERCEPT - 1.6, atc(INTERCEPT - 1.6) - 0.4, 'ATC', PRIMARY))
    return parts, ('Average total cost falls while fixed cost is spread over more units and '
                   'rises once diminishing returns dominate; marginal cost crosses it at the '
                   'minimum, which is the long-run competitive price.'), {
        'marginal_cost': 'MC = 1 + 0.8Q', 'average_total_cost': 'ATC = 6/Q + 1 + 0.4Q',
        'minimum_efficient_scale': round(minimum_q, 3), 'minimum_atc': round(minimum_y, 3)}


def _labour_market(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    parts = []
    demand = lambda n: INTERCEPT - SLOPE * n
    supply = lambda n: SUPPLY_INTERCEPT + SLOPE * n
    employment = (INTERCEPT - SUPPLY_INTERCEPT) / (2 * SLOPE)
    wage = demand(employment)
    parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
    parts.append(_line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT),
                       ACCENT))
    parts.extend(_dashed_guide(frame, employment, wage))
    parts.append(_dot(frame, employment, wage, INK,
                      f'E ({_fmt(employment)}, {_fmt(wage)})'))
    parts.append(_label(frame, INTERCEPT - 3.0, INTERCEPT - 1.6, 'MRP = demand for labour',
                        PRIMARY))
    parts.append(_label(frame, INTERCEPT - 2.0, INTERCEPT - SUPPLY_INTERCEPT - 1.2,
                        'supply of labour', ACCENT))
    return parts, ('A firm hires labour up to the point where the marginal revenue product '
                   'equals the wage; the demand for labour is derived from the demand for '
                   'what the labour produces.'), {
        'labour_demand_mrp': f'W = {_fmt(INTERCEPT)} - L',
        'labour_supply': f'W = {_fmt(SUPPLY_INTERCEPT)} + L',
        'employment': employment, 'wage': wage}


def _solve(fn, lo: float, hi: float, *, steps: int = 80) -> float:
    """A root of ``fn`` by bisection, for the prices that have no closed form.

    Used where a figure needs an intersection no algebra in this module would state more
    clearly - the regulated price under average-cost pricing, for instance. Bisection is
    enough and cannot be subtly wrong: the caption states the number it found.
    """
    for _ in range(steps):
        mid = (lo + hi) / 2
        if fn(lo) * fn(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


#: Templates that draw no axes. A payoff matrix is a table, and putting it on a price-and-
#: quantity frame would be worse than not drawing it.
NO_AXES: frozenset[str] = frozenset({'payoff_matrix'})

#: Templates whose numbers do not run 0-10. The frame is what maps them onto the canvas,
#: so the gridlines have to be drawn from the same range the data uses.
AXIS_FRAMES: dict[str, Frame] = {
    'production_function': Frame(0.0, 6.0, 0.0, 6.0),
    'marginal_utility': Frame(0.0, 6.0, 0.0, 6.0),
}


def _production_function(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    additions = [4.0, 5.5, 5.0, 4.0, 2.8, 1.5]
    running = 0.0
    averages = []
    for index, step in enumerate(additions, 1):
        running += step
        averages.append(running / index)
    parts = []
    for index, step in enumerate(additions, 1):
        parts.append(_bar(frame, index, step))
        parts.append(_label(frame, index, step, _fmt(step), PRIMARY, anchor='middle', dy=-7))
    parts.append(_curve(frame, lambda x: averages[min(max(int(round(x)), 1),
                                                    len(averages)) - 1],
                        lo=1.0, hi=float(len(additions)), samples=60, colour=ACCENT,
                        width=2.3, dash='6 4'))
    peak = averages.index(max(averages)) + 1
    parts.append(_dot(frame, peak, max(averages), INK,
                      f'average product peaks at {peak} workers', dy=-12))
    parts.append(_label(frame, 5.9, 0.55, 'average product', ACCENT, anchor='end', dy=-4))
    return parts, ('With capital fixed, each extra worker first adds more than the last and '
                   'then adds less. The bars are the marginal product of each worker; the '
                   'dashed line is the average, which peaks exactly where the two cross. '
                   'Diminishing returns is the falling part, not the whole story.'), {
        'workers': len(additions),
        'marginal_product': additions,
        'average_product_peak': {'worker': peak, 'value': round(max(averages), 3)},
        'total_product': round(running, 3)}


def _isoquant(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    # Worked from the tangency outwards rather than solved for it: pick the input bundle,
    # read the isoquant's slope there, and let that slope *be* the input price ratio. The
    # numbers are then exact - (-2) is the slope of K x L = 8 at K = 2 - and a learner can
    # check them, which a bisection result to three decimals does not allow.
    product = 8.0
    capital, labour = 2.0, 4.0
    price_ratio = product / capital ** 2
    intercept = labour + price_ratio * capital
    parts = [
        _curve(frame, lambda k: product / k, lo=product / 7.4, hi=product / 1.1,
               colour=PRIMARY),
        _line(frame, (0, intercept), (intercept / price_ratio, 0), ACCENT),
        _dot(frame, capital, labour, INK, f'least cost ({_fmt(capital)}, {_fmt(labour)})',
             dy=-10),
    ]
    parts.extend(_dashed_guide(frame, capital, labour))
    parts.append(_label(frame, 5.4, 3.6, 'isoquant: every input mix', PRIMARY))
    parts.append(_label(frame, 5.4, 2.9, 'that makes this output', PRIMARY))
    parts.append(_label(frame, 0.3, intercept - 0.5, 'isocost line', ACCENT))
    return parts, (f'The isoquant lists every input combination that produces the same '
                   f'output; the straight line is what that output costs at a given budget. '
                   f'The cheapest combination is where they touch, at '
                   f'{_fmt(capital)} of capital and {_fmt(labour)} of labour. Only there does '
                   f'the last dollar spent on either input buy the same extra output - '
                   f'otherwise shifting spending towards the cheaper-in-output input would '
                   f'produce more for the same money.'), {
        'output': product,
        'isoquant': f'K x L = {_fmt(product)}',
        'isocost': f'L = {_fmt(intercept)} - {_fmt(price_ratio)}K',
        'input_price_ratio': _fmt(price_ratio),
        'cost_minimising_inputs': {'capital': capital, 'labour': labour},
        'slope_at_tangency': _fmt(-price_ratio)}


def _marginal_utility(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    utilities = [5.0, 4.0, 3.0, 2.0, 1.0]
    price = 2.0
    bought = sum(1 for value in utilities if value >= price)
    parts = []
    for index, value in enumerate(utilities, 1):
        parts.append(_bar(frame, index, value, opacity='0.34' if value >= price else '0.13'))
        parts.append(_label(frame, index, value, _fmt(value), PRIMARY, anchor='middle', dy=-7))
    parts.append(_line(frame, (0, price), (float(len(utilities)) + 0.7, price), INK,
                       width=2.0, dash='7 4'))
    parts.append(_label(frame, 5.9, price, f'price {_fmt(price)}', INK, anchor='end', dy=-8))
    for index in range(1, bought + 1):
        surplus = utilities[index - 1] - price
        if surplus > 0:
            top = frame.sy(utilities[index - 1])
            parts.append(f'<rect x="{frame.sx(index - 0.31):.2f}" y="{top:.2f}" '
                         f'width="{frame.sx(index + 0.31) - frame.sx(index - 0.31):.2f}" '
                         f'height="{frame.sy(price) - top:.2f}" fill="{SECONDARY}" '
                         f'fill-opacity="0.22"/>')
    parts.append(_label(frame, 2.5, (utilities[0] + price) / 2 + 0.2,
                        'surplus over price', SECONDARY, anchor='middle'))
    return parts, (f'Marginal utility falls with every unit consumed. At a price of '
                   f'{_fmt(price)} the buyer keeps buying while the next unit is worth at '
                   f'least its price, and stops at {bought} units. The shaded steps are the '
                   f'surplus each earlier unit delivers - the same triangle as the market '
                   f'diagram, drawn in utility rather than money.'), {
        'marginal_utility': utilities, 'price': price, 'quantity_bought': bought,
        'total_utility': round(sum(utilities[:bought]), 3),
        'consumer_surplus': round(sum(u - price for u in utilities[:bought] if u > price), 3)}


def _lorenz(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    bend = 1.8
    span = frame.x_max - frame.x_min
    lorenz = lambda x: span * (max(x, 0.0) / span) ** bend
    outline = []
    for index in range(41):
        share = span * index / 40.0
        outline.append(f'{frame.sx(share):.2f},{frame.sy(lorenz(share)):.2f}')
    parts = [
        f'<polygon points="{frame.sx(0):.2f},{frame.sy(0):.2f} '
        f'{frame.sx(span):.2f},{frame.sy(span):.2f} {" ".join(outline)}" '
        f'fill="{SECONDARY}" fill-opacity="0.16"/>',
        _line(frame, (0, 0), (span, span), MUTED, width=1.8, dash='6 4'),
        _curve(frame, lorenz, lo=0.0, hi=span, colour=PRIMARY),
        _dot(frame, span * 0.5, lorenz(span * 0.5), INK),
    ]
    gini = 1 - 2 / (bend + 1)
    parts.append(_label(frame, 6.4, 4.1, 'line of equality', MUTED))
    parts.append(_label(frame, 6.4, 3.0, 'actual distribution', PRIMARY))
    parts.append(_label(frame, 3.4, 1.9, 'the gap is the inequality', SECONDARY))
    return parts, (f'The straight line is what incomes would look like if every household had '
                   f'the same. The curve below it is the actual distribution: the poorest '
                   f'half of households hold about {round(100 * lorenz(span * 0.5) / span)}% of '
                   f'the income. The area between the two curves is summarised as a Gini '
                   f'coefficient - here {round(gini, 3)} - and redistribution moves the curve '
                   f'back towards the line.'), {
        'lorenz_curve': f'cumulative share = (population share)^{bend}',
        'gini': round(gini, 3),
        'income_share_of_poorest_half': round(lorenz(span * 0.5) / span, 3)}


def _subsidy(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    per_unit = 2.0
    demand = lambda q: INTERCEPT - SLOPE * q
    supply = lambda q: SUPPLY_INTERCEPT + SLOPE * q
    before = (INTERCEPT - SUPPLY_INTERCEPT) / (2 * SLOPE)
    after = (INTERCEPT - SUPPLY_INTERCEPT + per_unit) / (2 * SLOPE)
    buyer_pays = demand(after)
    parts = [
        _line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY),
        _line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT), ACCENT),
        _line(frame, (0, SUPPLY_INTERCEPT - per_unit),
              (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT - per_unit), ACCENT, dash='6 5'),
        _polygon(frame, [(after, buyer_pays), (before, demand(before)),
                         (after, supply(after))], SECONDARY, '0.22'),
        _line(frame, (after, buyer_pays), (after, supply(after)), INK, width=3.0),
        _dot(frame, after, buyer_pays, PRIMARY, f'buyer pays {_fmt(buyer_pays)}', dy=-8),
        _dot(frame, after, supply(after), ACCENT, f'seller keeps {_fmt(supply(after))}', dy=16),
    ]
    parts.extend(_dashed_guide(frame, after, None))
    parts.append(_label(frame, INTERCEPT - 2.6, INTERCEPT - 1.1, 'demand', PRIMARY))
    parts.append(_label(frame, INTERCEPT - 2.4, INTERCEPT - SUPPLY_INTERCEPT - 0.8,
                        'supply', ACCENT))
    parts.append(_label(frame, after + 0.4, supply(after) + 0.9,
                        f'subsidy {_fmt(per_unit)}', INK))
    parts.append(_label(frame, 2.2, supply(after) - 1.4, 'deadweight loss', SECONDARY))
    return parts, (f'A per-unit subsidy of {_fmt(per_unit)} shifts supply down by exactly that '
                   f'much: buyers pay {_fmt(buyer_pays)}, sellers keep {_fmt(supply(after))}, '
                   f'and the quantity rises from {_fmt(before)} to {_fmt(after)}. The '
                   f'triangle is output that costs more to make than buyers value it - the '
                   f'same deadweight loss a tax would cause, from the opposite direction.'), {
        'demand': f'P = {_fmt(INTERCEPT)} - Q',
        'supply': f'P = {_fmt(SUPPLY_INTERCEPT)} + Q',
        'subsidy': per_unit, 'buyer_price': buyer_pays, 'seller_price': supply(after),
        'quantity_before': before, 'quantity_after': after,
        'government_cost': round(per_unit * after, 3),
        'deadweight_loss': round(0.5 * per_unit * (after - before), 3)}


def _public_good(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    private = lambda q: INTERCEPT - SLOPE * q
    social = lambda q: INTERCEPT - 0.5 * SLOPE * q
    supply = lambda q: SUPPLY_INTERCEPT + SLOPE * q
    market_q = (INTERCEPT - SUPPLY_INTERCEPT) / (2 * SLOPE)
    social_q = (INTERCEPT - SUPPLY_INTERCEPT) / (1.5 * SLOPE)
    parts = [
        _line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY),
        _line(frame, (0, INTERCEPT), (2 * INTERCEPT, 0), SECONDARY, dash='6 5'),
        _line(frame, (0, SUPPLY_INTERCEPT), (INTERCEPT, INTERCEPT - SUPPLY_INTERCEPT), ACCENT),
        _polygon(frame, [(market_q, private(market_q)), (social_q, social(social_q)),
                         (market_q, supply(market_q))], SECONDARY, '0.22'),
        _dot(frame, market_q, private(market_q), MUTED,
             f'market provides {_fmt(market_q)}', dy=-10),
        _dot(frame, social_q, social(social_q), INK, f'optimum {_fmt(social_q)}'),
    ]
    parts.extend(_dashed_guide(frame, social_q, social(social_q)))
    parts.append(_label(frame, 4.4, 8.0, 'marginal social benefit', SECONDARY))
    parts.append(_label(frame, 4.4, 5.6, 'what one buyer will pay', PRIMARY))
    parts.append(_label(frame, 6.4, 3.0, 'marginal cost', ACCENT))
    return parts, (f'A public good is non-excludable, so no buyer pays for what everyone '
                   f'receives: the demand curve records only private willingness to pay, '
                   f'which sits below the benefit society actually gets. The market supplies '
                   f'{_fmt(market_q)} units where {_fmt(social_q)} is optimal, and the '
                   f'triangle is the value the free-rider problem leaves on the table.'), {
        'private_demand': f'P = {_fmt(INTERCEPT)} - Q',
        'social_benefit': f'P = {_fmt(INTERCEPT)} - 0.5Q',
        'marginal_cost': f'P = {_fmt(SUPPLY_INTERCEPT)} + Q',
        'market_quantity': market_q, 'optimal_quantity': round(social_q, 3),
        'deadweight_loss': round(0.5 * (social_q - market_q) *
                                 (social(social_q) - supply(social_q) +
                                  social(market_q) - supply(market_q)), 3)}


def _firm_market(frame: Frame, *, power: bool = False,
                 regulated: bool = False) -> tuple[list[str], str, dict[str, float]]:
    marginal = lambda q: 2.0 + 0.9 * q
    average = lambda q: 4.0 / max(q, 0.2) + 1.0 + 0.08 * q
    parts = []
    if power:
        demand = lambda q: INTERCEPT - SLOPE * q
        revenue = lambda q: INTERCEPT - 2 * SLOPE * q
        # Marginal revenue falls at twice the rate of demand, so the divisor carries the
        # 2 * SLOPE - using SLOPE alone would put the profit-maximising quantity at the
        # point where average revenue, not marginal revenue, meets marginal cost.
        quantity = (INTERCEPT - 2.0) / (2 * SLOPE + 0.9)
        price = demand(quantity)
        parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT, 0), PRIMARY))
        parts.append(_line(frame, (0, INTERCEPT), (INTERCEPT / 2, 0), PRIMARY, dash='6 5'))
        parts.append(_curve(frame, average, lo=1.2, hi=8.4, colour=SECONDARY, width=2.0))
        parts.append(_label(frame, INTERCEPT - 1.4, INTERCEPT - 1.1, 'demand', PRIMARY))
        parts.append(_label(frame, 5.2, 0.7, 'marginal revenue', PRIMARY))
        parts.append(_label(frame, 7.0, average(7.0) - 0.5, 'average total cost', SECONDARY))
        caption = ('A firm facing a downward-sloping demand curve sets output where marginal '
                   'revenue equals marginal cost and then charges what demand will bear: '
                   f'{_fmt(quantity)} units at {_fmt(price)}, above the {_fmt(marginal(quantity))} '
                   'it costs to make the last one. That gap is the markup.')
    else:
        price = 6.0
        quantity = (price - 2.0) / 0.9
        revenue = lambda q: price
        parts.append(_curve(frame, average, lo=1.2, hi=8.4, colour=SECONDARY, width=2.0))
        parts.append(_line(frame, (0, price), (8.6, price), PRIMARY))
        parts.append(_label(frame, 6.9, price, 'P = MR', PRIMARY, dy=-8))
        parts.append(_label(frame, 7.0, average(7.0) - 0.5, 'average total cost', SECONDARY))
        caption = ('A price taker sells at the market price however much it produces, so its '
                   f'marginal revenue is the price: {_fmt(price)}. It produces {_fmt(quantity)} '
                   f'units, where marginal cost catches up with price, and the rectangle '
                   'between price and average cost is economic profit. Nothing it does moves '
                   'the price, which is why the same diagram cannot show it choosing one.')
    parts.append(_curve(frame, marginal, lo=0.3, hi=9.0, colour=ACCENT))
    parts.append(_label(frame, 8.6, marginal(8.6) + 0.3, 'marginal cost', ACCENT,
                        anchor='end'))
    if regulated:
        regulated_q = _solve(lambda q: demand(q) - average(q), 1.2, 8.0)
        regulated_p = average(regulated_q)
        parts.append(_dot(frame, regulated_q, regulated_p, MUTED,
                          f'regulated price {_fmt(regulated_p)}', dy=-10))
        parts.extend(_dashed_guide(frame, regulated_q, regulated_p))
        caption += (' A regulator setting price equal to average cost would require '
                    f'{_fmt(regulated_q)} units at {_fmt(regulated_p)}: no profit, but also '
                    'no reason for the firm to refuse to serve.')
    parts.extend(_dashed_guide(frame, quantity, price))
    parts.append(_dot(frame, quantity, price, INK, f'Q {_fmt(quantity)} at {_fmt(price)}'))
    if not power:
        top = frame.sy(price)
        bottom = frame.sy(average(quantity))
        parts.append(f'<rect x="{frame.sx(0):.2f}" y="{top:.2f}" '
                     f'width="{frame.sx(quantity) - frame.sx(0):.2f}" '
                     f'height="{bottom - top:.2f}" fill="{SECONDARY}" fill-opacity="0.20"/>')
    return parts, caption, {
        'marginal_cost': 'MC = 2 + 0.9Q',
        'average_total_cost': 'ATC = 4/Q + 1 + 0.08Q',
        'quantity': round(quantity, 3), 'price': round(price, 3),
        'marginal_revenue_at_quantity': round(revenue(quantity), 3),
        'profit_per_unit': round(price - average(quantity), 3)}


def _profit_bars(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    revenue, explicit, implicit = 10.0, 7.0, 2.0
    accounting = revenue - explicit
    economic = accounting - implicit
    parts = []
    columns = ((1.6, ((revenue, PRIMARY, 'revenue'),)), (4.2, ((explicit, ACCENT, 'explicit'),
                                                             (accounting, SECONDARY,
                                                              'accounting profit'))),
               (6.8, ((explicit, ACCENT, 'explicit'), (implicit, MUTED, 'implicit'),
                      (economic, SECONDARY, 'economic profit'))))
    for x, stack in columns:
        base = 0.0
        for height, colour, name in stack:
            parts.append(_bar(frame, x, base + height, base=base, fill=colour,
                              opacity='0.30'))
            parts.append(_label(frame, x, base + height / 2, name, INK, anchor='middle'))
            base += height
    parts.append(_line(frame, (0.6, revenue), (7.6, revenue), MUTED, dash='5 4', width=1.2))
    return parts, (f'Accounting profit subtracts only the costs that appear on an invoice: '
                   f'{_fmt(revenue)} of revenue less {_fmt(explicit)} of explicit cost leaves '
                   f'{_fmt(accounting)}. Economic profit also charges the owner for what the '
                   f'next best use of their own time and money would have earned - '
                   f'{_fmt(implicit)} here - so the same firm earns {_fmt(economic)}. When '
                   f'economic profit is zero the firm is still covering everything; that is '
                   f'normal profit, not failure.'), {
        'revenue': revenue, 'explicit_cost': explicit, 'implicit_cost': implicit,
        'accounting_profit': accounting, 'economic_profit': economic}


def _discount_bars(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    rate = 0.10
    receipts = [4.0, 4.0, 4.0]
    present = [amount / (1 + rate) ** year for year, amount in enumerate(receipts, 1)]
    parts = []
    for year, (amount, value) in enumerate(zip(receipts, present), 1):
        x = 1.0 + 2.6 * (year - 1)
        parts.append(_bar(frame, x, amount, width=0.92, fill=MUTED, opacity='0.18'))
        parts.append(_bar(frame, x, value, width=0.46))
        parts.append(_label(frame, x, value, _fmt(value), PRIMARY, anchor='middle', dy=-7))
        parts.append(_label(frame, x + 0.42, amount, f'{_fmt(amount)}', MUTED, dy=4))
        parts.append(_label(frame, x, 0.0, f'year {year}', MUTED, anchor='middle', dy=18))
    return parts, (f'Each {_fmt(receipts[0])} receipt is worth less the later it arrives: at a '
                   f'{int(rate * 100)}% discount rate the year-three receipt is worth '
                   f'{_fmt(present[2])} today. The pale bars are the cash amounts and the '
                   f'solid bars are what they are worth now, so an investment decision '
                   f'compares present values rather than totals.'), {
        'discount_rate': rate, 'receipts': receipts,
        'present_values': [round(value, 3) for value in present],
        'present_value_total': round(sum(present), 3),
        'nominal_total': round(sum(receipts), 3)}


def _payoff_matrix(frame: Frame) -> tuple[list[str], str, dict[str, float]]:
    left, top, cell_w, cell_h = PAD_LEFT + 54, PAD_TOP + 46, 168.0, 74.0
    moves = ('hold the price', 'undercut')
    payoffs = {(0, 0): (8, 8), (0, 1): (2, 10), (1, 0): (10, 2), (1, 1): (4, 4)}
    nash = (1, 1)
    parts: list[str] = []
    for column, label in enumerate(moves):
        cx = left + cell_w * (column + 0.5)
        parts.append(f'<text x="{cx:.2f}" y="{top - 12:.2f}" font-size="12" fill="{INK}" '
                     f'text-anchor="middle">{html.escape(label)}</text>')
    for row, label in enumerate(moves):
        cy = top + cell_h * (row + 0.5)
        parts.append(f'<text x="{left - 12:.2f}" y="{cy + 4:.2f}" font-size="12" fill="{INK}" '
                     f'text-anchor="end">{html.escape(label)}</text>')
    for row in range(2):
        for column in range(2):
            x, y = left + cell_w * column, top + cell_h * row
            fill = SECONDARY if (row, column) == nash else 'none'
            opacity = '0.20' if (row, column) == nash else '0'
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell_w:.2f}" '
                         f'height="{cell_h:.2f}" fill="{fill}" fill-opacity="{opacity}" '
                         f'stroke="{INK}" stroke-width="1.1"/>')
            first, second = payoffs[(row, column)]
            parts.append(f'<text x="{x + cell_w / 2:.2f}" y="{y + 30:.2f}" font-size="13" '
                         f'fill="{INK}" text-anchor="middle">'
                         f'{first} , {second}</text>')
            if (row, column) == nash:
                parts.append(f'<text x="{x + cell_w / 2:.2f}" y="{y + 52:.2f}" '
                             f'font-size="11" fill="{SECONDARY}" text-anchor="middle">'
                             f'Nash equilibrium</text>')
    parts.append(f'<text x="{left:.2f}" y="{top + 2 * cell_h + 26:.2f}" font-size="11.5" '
                 f'fill="{MUTED}">payoffs shown as (row firm, column firm), in profit</text>')
    return parts, ('Each firm does better by undercutting whatever the other does - 10 against '
                   '8, and 4 against 2 - so both undercut and both end up at 4. Neither can '
                   'improve by moving alone, which is what makes it a Nash equilibrium; and '
                   'both would have preferred to hold the price at 8. A cartel is an attempt '
                   'to hold the top-left square, and it is unstable for exactly this reason.'), {
        'cooperate_payoff': payoffs[(0, 0)], 'defect_payoff': payoffs[(1, 1)],
        'undercut_gain': payoffs[(1, 0)][0] - payoffs[(0, 0)][0],
        'nash_equilibrium': 'both undercut'}


#: Ordered rules. The first match wins, so the most specific concept shape is tested first:
#: "price elasticity of demand" must not be captured by the generic market rule.
RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    # The shapes whose names collide with a broader rule go first. "Income inequality
    # and redistribution" mentions taxes; "least-cost combination of inputs" mentions
    # cost. Both are drawn by their own template and would otherwise be captured by the
    # tax and cost-curve rules below.
    (('lorenz', 'gini', 'income inequality', 'redistribution', 'quintile'), 'lorenz'),
    (('isoquant', 'isocost', 'least-cost', 'least cost', 'cost minimis', 'cost minimiz'),
     'isoquant'),
    (('payoff matrix', 'game theory', 'prisoner', 'dominant strategy', 'nash',
      'oligopoly', 'collusion', 'cartel'), 'payoff_matrix'),
    # A common resource is non-excludable *and* rival, so it is over-used rather than
    # under-provided. That is a negative externality, not the public-good picture, and
    # the two concepts share the vocabulary that would otherwise route one to the other.
    (('tragedy of the commons', 'common resource', 'common pool'), 'externality'),
    (('public good', 'free-rider', 'free rider', 'non-excludable', 'non-rival',
      'nonexcludable', 'nonrival'), 'public_good'),
    (('accounting profit', 'economic profit', 'explicit cost', 'implicit cost'),
     'profit_bars'),
    (('production function', 'diminishing marginal return', 'diminishing returns',
      'short-run production', 'total product', 'marginal product', 'law of diminishing'),
     'production_function'),
    (('marginal utility', 'utility-maximis', 'utility-maximiz', 'consumer choice',
      'indifference curve'), 'marginal_utility'),
    (('perfect competition', 'price taker', 'price-taker'), 'firm_competitive'),
    (('natural monopoly', 'price discrimination', 'monopolistic competition',
      'markup', 'monopoly'), 'firm_market'),
    (('subsidy', 'subsidies', 'production subsidy'), 'subsidy'),
    (('present value', 'net present', 'discount rate', 'discounted', 'rate of return'),
     'discount_bars'),
    # Ceilings and floors before the tax rule, because a chapter on price controls
    # discusses deadweight loss and would otherwise be drawn as a tax wedge.
    (('price ceiling', 'price control', 'rent control', 'price cap'), 'price_ceiling'),
    (('price floor', 'minimum wage', 'price support'), 'price_floor'),
    (('deadweight', 'tax incidence', 'incidence', 'per-unit tax', 'excise', 'tax wedge',
      'tax on', 'taxation'), 'tax_wedge'),
    (('externality', 'marginal social', 'corrective', 'pigouvian', 'coase'), 'externality'),
    (('consumer surplus', 'producer surplus', 'total surplus', 'surplus'), 'surplus'),
    (('cost curve', 'average total cost', 'economies of scale', 'diseconomies',
      'fixed cost', 'variable cost', 'marginal cost', 'long-run average'), 'cost_curves'),
    (('marginal revenue product', 'derived demand', 'labour market', 'labor market',
      'wage', 'monopsony'), 'labour_market'),
    (('elasticity', 'elastic'), 'elasticity'),
    (('production possibilit', 'ppf', 'opportunity cost', 'trade-off', 'tradeoff'), 'ppf'),
    (('shift', 'determinant'), 'shift'),
    # Adverse selection before every market rule. Its own vocabulary ("asymmetric
    # information", "lemons") shares the word *market* with the catch-all below, and the
    # catch-all would answer with a clearing market - the exact opposite of the concept,
    # whose claim is that a market fails to exist.
    (('asymmetric information', 'adverse selection', 'lemons', 'moral hazard',
      'hidden characteristic', 'signalling', 'signaling'), 'adverse_selection'),
    (('supply and demand', 'demand and supply', 'equilibrium', 'market clearing'),
     'supply_demand'),
)


def classify(concept_id: str, title: str = '', summary: str = '') -> str:
    """Which template, if any, honestly fits this concept.

    Matched on the id first and the prose second, because the id is authored and stable
    while a summary may be rewritten. Returns ``''`` when nothing fits.
    """
    haystack_id = str(concept_id or '').replace('_', ' ').lower()
    haystack = f'{haystack_id} {title} {summary}'.lower()
    for needles, kind in RULES:
        if any(needle in haystack for needle in needles):
            return kind
    return ''


def render(kind: str, *, title: str = '') -> dict[str, Any]:
    """Draw one template. Returns the payload a lesson block carries."""
    frame = AXIS_FRAMES.get(kind) or _frame()
    builders = {
        'supply_demand': lambda: _supply_demand(frame),
        'adverse_selection': lambda: _adverse_selection(frame),
        'shift': lambda: _shift(frame, which='demand'),
        'supply_shift': lambda: _shift(frame, which='supply'),
        'tax_wedge': lambda: _tax_wedge(frame),
        'price_ceiling': lambda: _price_control(frame, ceiling=True),
        'price_floor': lambda: _price_control(frame, ceiling=False),
        'surplus': lambda: _surplus(frame),
        'elasticity': lambda: _elasticity(frame),
        'ppf': lambda: _ppf(frame),
        'externality': lambda: _externality(frame),
        'cost_curves': lambda: _cost_curves(frame),
        'labour_market': lambda: _labour_market(frame),
        'production_function': lambda: _production_function(frame),
        'isoquant': lambda: _isoquant(frame),
        'marginal_utility': lambda: _marginal_utility(frame),
        'lorenz': lambda: _lorenz(frame),
        'subsidy': lambda: _subsidy(frame),
        'public_good': lambda: _public_good(frame),
        'firm_market': lambda: _firm_market(frame, power=True, regulated=True),
        'firm_competitive': lambda: _firm_market(frame, power=False),
        'profit_bars': lambda: _profit_bars(frame),
        'discount_bars': lambda: _discount_bars(frame),
        'payoff_matrix': lambda: _payoff_matrix(frame),
    }
    builder = builders.get(kind)
    if builder is None:
        raise ValueError(f'No economics figure template named {kind!r}')
    body, caption, parameters = builder()
    parts = ([] if kind in NO_AXES else _axes(frame)) + body
    header = ''
    if title:
        header = (f'<text x="{PAD_LEFT}" y="18" font-size="13.5" font-weight="600" '
                  f'fill="{INK}">{html.escape(title[:72])}</text>')
    # Paint order, not decoration order: paper, then title, then everything drawn on it.
    # The paper rect used to arrive inside ``_axes``, i.e. after the title, and an opaque
    # white rect over a title is a title nobody can read.
    paper = f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{PAPER}"/>'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
           f'width="100%" role="img" aria-label="{html.escape(title or kind)}">'
           f'{paper}{header}{"".join(parts)}</svg>')
    return {'figure': 'economics', 'kind': kind, 'svg': svg, 'caption': caption,
            'parameters': parameters}


def for_concept(concept_id: str, title: str = '', summary: str = '') -> dict[str, Any] | None:
    """The figure this concept honestly gets, or ``None``.

    ``None`` is a real answer, not a failure: most economics concepts in a survey course
    are definitions and institutions, and drawing a market for them would teach the
    learner that every economics idea is a crossing of two lines.
    """
    kind = classify(concept_id, title, summary)
    if not kind:
        return None
    return render(kind, title=title)


def caption_with_parameters(payload: dict[str, Any]) -> str:
    """The caption a lesson shows: the teaching sentence plus the stated parameters."""
    caption = str(payload.get('caption') or '')
    parameters = payload.get('parameters') or {}
    if not parameters:
        return caption
    stated = ', '.join(f'{key} = {value}' for key, value in parameters.items()
                       if isinstance(value, (int, float, str)))
    return f'{caption} Drawn with {stated}.' if stated else caption


__all__ = ['RULES', 'caption_with_parameters', 'classify', 'for_concept', 'render']
