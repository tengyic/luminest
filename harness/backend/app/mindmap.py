"""Layout and render a mind map: a tree in, an SVG or an interactive page out.

This lives in the application package rather than in a script because two callers need it -
the CLI renderers under ``scripts/`` and ``routes_mindmap`` - and a layout implemented twice
drifts the moment one of them is touched.

The figure is a left-anchored tree, tier by tier, one colour band per depth, with thin
curved connectors and a chevron on every node that can be opened. Columns are aligned per
depth and a parent is centred on the span of its visible children, which is what makes a
collapsed branch read as one line rather than as a gap.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass, field

FONT = 13
PAD_X = 14
BAR_H = 36
ROW_GAP = 18
TIER_GAP = 74
CHEVRON = 9
RADIUS = 7
MARGIN = 40

#: One band per depth: violet root, blue first tier, green second, then muted neutrals.
#: Deeper levels reuse the neutral rather than inventing another colour family.
BANDS = (
    ('#e8e3f8', '#b6a9e3', '#463a6b'),
    ('#dde8f8', '#a8bfe2', '#2b4a70'),
    ('#d8efe3', '#a3cdb6', '#2a5743'),
    ('#eceae6', '#c9c5bd', '#3f3b33'),
)


@dataclass
class Node:
    label: str
    children: list['Node'] = field(default_factory=list)
    depth: int = 0
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0


def text_width(label: str) -> float:
    """A width estimate, not a measurement: the renderer never truncates, so a few pixels
    of slack read as padding."""
    return sum(1.0 if ch.isascii() and ch not in 'iljtf.,:;' else 1.35 for ch in label)


def measure(node: Node, depth: int = 0) -> None:
    node.depth = depth
    node.w = text_width(node.label) * FONT * 0.52 + 2 * PAD_X
    for child in node.children:
        measure(child, depth + 1)


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


def depth_of(node: Node, depth: int = 0) -> int:
    return max([depth] + [depth_of(child, depth + 1) for child in node.children])


def layout(root: Node) -> tuple[float, float]:
    columns: dict[int, float] = {}
    for node in walk(root):
        columns[node.depth] = max(columns.get(node.depth, 0.0), node.w)
    xs, cursor = {}, MARGIN
    for depth in sorted(columns):
        xs[depth] = cursor
        cursor += columns[depth] + TIER_GAP

    row = [float(MARGIN)]

    def place(node: Node) -> None:
        node.x = xs[node.depth]
        if not node.children:
            node.y = row[0]
            row[0] += BAR_H + ROW_GAP
            return
        for child in node.children:
            place(child)
        node.y = (node.children[0].y + node.children[-1].y) / 2

    place(root)
    return max(cursor - TIER_GAP + MARGIN, 640), max(row[0] - ROW_GAP + MARGIN, 360)


def svg(root: Node) -> str:
    measure(root)
    width, height = layout(root)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
             f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">'
             f'<rect width="100%" height="100%" fill="#ffffff"/>']
    for node in walk(root):
        for child in node.children:
            x1, y1 = node.x + node.w, node.y + BAR_H / 2
            x2, y2 = child.x, child.y + BAR_H / 2
            mid = (x1 + x2) / 2
            parts.append(f'<path d="M {x1:.1f},{y1:.1f} C {mid:.1f},{y1:.1f} {mid:.1f},{y2:.1f} '
                         f'{x2:.1f},{y2:.1f}" fill="none" stroke="#8f9dc0" stroke-width="1.2"/>')
    for node in walk(root):
        fill, stroke, ink = BANDS[min(node.depth, len(BANDS) - 1)]
        parts.append(f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{node.w:.1f}" '
                     f'height="{BAR_H}" rx="{RADIUS}" fill="{fill}" stroke="{stroke}" '
                     f'stroke-width="1"/>')
        parts.append(f'<text x="{node.x + node.w / 2:.1f}" y="{node.y + BAR_H / 2 + 4.5:.1f}" '
                     f'font-family="-apple-system, Helvetica, Arial" font-size="{FONT}" '
                     f'fill="{ink}" text-anchor="middle">{html.escape(node.label)}</text>')
    parts.append('</svg>')
    return ''.join(parts)


# ------------------------------------------------------------------ tree builders

def from_payload(payload: dict) -> Node:
    """The concept's own map: what it rests on, what it unlocks, what sits beside it."""
    title = str(payload.get('title') or (payload.get('focus') or {}).get('label') or 'Concept')
    root = Node(title)

    def group(label: str, items) -> Node | None:
        leaves = [Node(str(item.get('label') or item.get('id') or ''))
                  for item in (items or [])
                  if isinstance(item, dict) and (item.get('label') or item.get('id'))]
        return Node(label, leaves) if leaves else None

    for label, items in (('Rests on', payload.get('prerequisites')),
                         ('Unlocks', payload.get('dependants')),
                         ('Same unit', payload.get('siblings'))):
        node = group(label, items)
        if node:
            root.children.append(node)
    return root


def from_dict(raw: dict) -> Node:
    return Node(str(raw.get('label') or raw.get('title') or ''),
                [from_dict(child) for child in raw.get('children') or []])


def to_dict(node: Node) -> dict:
    return {'label': node.label, 'children': [to_dict(child) for child in node.children]}


# ------------------------------------------------------------------ interactive page

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
  html, body { margin: 0; background: #f4f4f2; font-family: -apple-system, BlinkMacSystemFont,
    "Helvetica Neue", Arial, sans-serif; color: #23262d; }
  #frame { position: relative; margin: 0 auto; }
  svg { display: block; background: #fff; }
  .node rect, .node text { transition: opacity .18s ease; }
  .node { transition: transform .28s cubic-bezier(.25,.8,.3,1); cursor: pointer; }
  .node.leaf { cursor: default; }
  .node.hidden { opacity: 0; pointer-events: none; }
  .edge { transition: opacity .18s ease; }
  .edge.hidden { opacity: 0; }
  #hint { position: fixed; left: 16px; bottom: 14px; font-size: 12px; color: #7a7f8a;
    background: #fff; border: 1px solid #e2e0da; border-radius: 8px; padding: 7px 11px; }
  #hint b { color: #23262d; font-weight: 600; }
</style></head>
<body>
<div id="frame"><svg id="map"></svg></div>
<div id="hint">Click a bar to <b>expand</b> or <b>collapse</b> its branch</div>
<script>
const TREE = __TREE__;
const BANDS = __BANDS__;
const FONT = __FONT__, BAR_H = __BAR_H__, ROW_GAP = __ROW_GAP__, TIER_GAP = __TIER_GAP__,
      MARGIN = __MARGIN__, PAD_X = __PAD_X__, RADIUS = __RADIUS__, OPEN_DEPTH = __OPEN_DEPTH__;
const SVGNS = 'http://www.w3.org/2000/svg';

let seq = 0;
(function number(node, depth) {
  node.id = 'n' + (seq++);
  node.depth = depth;
  node.w = measure(node.label);
  node.open = depth < OPEN_DEPTH;
  (node.children || []).forEach(child => number(child, depth + 1));
})(TREE, 0);

function measure(label) {
  let units = 0;
  for (const ch of label) units += (/[iljtf.,:;]/.test(ch) && ch.charCodeAt(0) < 128) ? 1 : 1.35;
  return units * FONT * 0.52 + PAD_X * 2;
}
function visibleChildren(node) { return node.open ? (node.children || []) : []; }

const nodes = new Map(), edges = new Map();
const svg = document.getElementById('map');

function el(name, attrs) {
  const node = document.createElementNS(SVGNS, name);
  for (const key in attrs) node.setAttribute(key, attrs[key]);
  return node;
}

(function build() {
  (function walkAll(node) {
    const g = el('g', {class: 'node'});
    const rect = el('rect', {height: BAR_H, rx: RADIUS, stroke: 'none', 'stroke-width': 1});
    const text = el('text', {'font-size': FONT, 'text-anchor': 'middle',
                             'font-family': '-apple-system, Helvetica, Arial'});
    text.textContent = node.label;
    // A drawn chevron, not a glyph: the connector fan converges exactly where it sits.
    const chev = el('path', {fill: 'none', stroke: '#5b6473', 'stroke-width': 1.8,
                             'stroke-linecap': 'round', 'stroke-linejoin': 'round'});
    g.append(rect, text, chev);
    if ((node.children || []).length) {
      g.addEventListener('click', () => { node.open = !node.open; apply(); });
    } else {
      g.classList.add('leaf');
    }
    svg.appendChild(g);
    nodes.set(node.id, {node, g, rect, text, chev});
    (node.children || []).forEach(child => {
      const path = el('path', {fill: 'none', stroke: '#8f9dc0', 'stroke-width': 1.2,
                               class: 'edge'});
      svg.insertBefore(path, g);
      edges.set(node.id + '>' + child.id, {path, from: node, to: child});
      walkAll(child);
    });
  })(TREE);
})();

function layout() {
  const widths = {};
  (function collect(node) {
    widths[node.depth] = Math.max(widths[node.depth] || 0, node.w);
    visibleChildren(node).forEach(collect);
  })(TREE);
  const xs = {};
  let cursor = MARGIN;
  Object.keys(widths).map(Number).sort((a, b) => a - b).forEach(depth => {
    xs[depth] = cursor;
    cursor += widths[depth] + TIER_GAP;
  });
  let row = MARGIN;
  (function place(node) {
    node.x = xs[node.depth];
    const kids = visibleChildren(node);
    if (!kids.length) { node.y = row; row += BAR_H + ROW_GAP; return; }
    kids.forEach(place);
    node.y = (kids[0].y + kids[kids.length - 1].y) / 2;
  })(TREE);
  return {width: cursor - TIER_GAP + MARGIN, height: row - ROW_GAP + MARGIN};
}

function apply() {
  const {width, height} = layout();
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

  const shown = new Set();
  (function walk(node) { shown.add(node.id); visibleChildren(node).forEach(walk); })(TREE);

  nodes.forEach(({node, g, rect, text, chev}, id) => {
    const on = shown.has(id);
    g.classList.toggle('hidden', !on);
    if (!on) return;
    const [fill, stroke, ink] = BANDS[Math.min(node.depth, BANDS.length - 1)];
    g.setAttribute('transform', `translate(${node.x},${node.y})`);
    rect.setAttribute('width', node.w);
    rect.setAttribute('fill', fill);
    rect.setAttribute('stroke', stroke);
    text.setAttribute('x', node.w / 2);
    text.setAttribute('y', BAR_H / 2 + 4.5);
    text.setAttribute('fill', ink);
    const kids = (node.children || []).length;
    chev.setAttribute('transform', `translate(${node.w + 9},${BAR_H / 2 - 6})`);
    chev.setAttribute('d', !kids ? '' : (node.open ? 'M 6,0 L 1,6 L 6,12' : 'M 1,0 L 6,6 L 1,12'));
  });

  edges.forEach(({path, from, to}) => {
    const on = shown.has(from.id) && shown.has(to.id);
    path.classList.toggle('hidden', !on);
    if (!on) return;
    const x1 = from.x + from.w, y1 = from.y + BAR_H / 2;
    const x2 = to.x, y2 = to.y + BAR_H / 2;
    const mid = (x1 + x2) / 2;
    path.setAttribute('d', `M ${x1},${y1} C ${mid},${y1} ${mid},${y2} ${x2},${y2}`);
  });
}

apply();
</script>
</body></html>
"""


def interactive_page(root: Node, *, open_depth: int = 1, title: str = '') -> str:
    """The whole map as one page: no network, no build step, clicking expands a branch."""
    body = (_PAGE
            .replace('__TITLE__', html.escape(title or root.label or 'Mind map'))
            .replace('__TREE__', json.dumps(to_dict(root), ensure_ascii=False))
            .replace('__BANDS__', json.dumps(BANDS))
            .replace('__FONT__', str(FONT))
            .replace('__BAR_H__', str(BAR_H))
            .replace('__ROW_GAP__', str(ROW_GAP))
            .replace('__TIER_GAP__', str(TIER_GAP))
            .replace('__MARGIN__', str(MARGIN))
            .replace('__PAD_X__', str(PAD_X))
            .replace('__RADIUS__', str(RADIUS))
            .replace('__OPEN_DEPTH__', str(max(0, open_depth))))
    return body


def course_tree(graph, *, per_unit: int = 5, max_units: int = 8) -> Node:
    """A course as a mind map: the course, its units, and the first few concepts of each."""
    root = Node('Course')
    units: dict[str, list[str]] = {}
    for node in graph.nodes.values():
        unit = str(getattr(node, 'unit', '') or 'Other')
        units.setdefault(unit, []).append(str(node.title))
    for unit, titles in list(units.items())[:max_units]:
        leaves = [Node(title) for title in sorted(set(titles))[:per_unit]]
        root.children.append(Node(unit, leaves))
    return root


__all__ = ['Node', 'BANDS', 'measure', 'layout', 'svg', 'walk', 'depth_of', 'from_payload',
           'from_dict', 'to_dict', 'interactive_page', 'course_tree']
