"""``order_sequence``, ``matching_pairs`` and ``label_diagram`` - the general-purpose
interactions.

These three carry content from *any* subject. Nothing in their schemas names a
discipline: ``order_sequence`` orders steps, ``matching_pairs`` joins two columns, and
``label_diagram`` drops labels onto a picture. A biology teacher uses all three, a
computer-science teacher uses all three, and the same three pages serve both - which is
the point of an archetype. The vocabulary that could have leaked a subject in (a
"market", a "force", a "cell") lives in the *spec*, never in the module.

The mechanics
-------------
``order_sequence``
    A shuffled column of steps, events or stages must be dragged into the correct
    sequence. On Check each position is marked right or wrong; after three tries the
    correct order is revealed with a per-item note explaining why each step sits where
    it does. Water cycle, stages of mitosis, steps of an algorithm, a timeline, the
    order of operations - all the same interaction.

``matching_pairs``
    Two columns - terms and definitions, symbols and meanings, formulas and names -
    joined by the learner. Selection is click-to-select-then-click-to-pair *and* drag,
    so it works with a trackpad, a mouse and a keyboard. A correct pairing locks and is
    connected by a line; a wrong one bounces back and is tallied.

``label_diagram``
    A diagram declared as a short list of shapes, and a tray of labels to drag onto
    hotspots. A drop inside the hotspot locks; a drop outside bounces back to the tray.
    The shape vocabulary is deliberately tiny - ``rect``, ``circle`` and ``line`` - so
    the spec is a labelling exercise and never a drawing tool.

Why these are evidence and not toys
-----------------------------------
None of the three posts an outcome on a mere interaction. ``order_sequence`` commits
only through Check; ``matching_pairs`` and ``label_diagram`` commit by *completing* the
board, which is only reachable once every pairing or label is right (a wrong one bounces
back, so it cannot be brute-forced into a false positive). Live state - how many items
are placed, how many pairs are locked - travels on ``BRIDGE.readout`` and is never
stored. The single ``BRIDGE.outcome`` per board carries whether the learner got there
unaided and, when they did not, that the answer had to be revealed: a run in which
anything was given away is reported as ``correct: false`` with ``gave_up: true`` in the
detail, so a completed-but-aided board can never be mistaken for mastery.

The coordinate note
-------------------
Pointer drags are handled by one full-stage transparent rectangle rather than by each
tile. ``point(event, node)`` maps the event into the node's *own* box, so a drag wired to
a small tile measures against the tile and drifts as the tile moves; wired to a rectangle
that spans the whole viewBox it is exact. Everything in this module drags through that
overlay and hit-tests in viewBox coordinates.
"""

from __future__ import annotations

import html
from typing import Any, Mapping

from .archetypes import Archetype, Field

#: How many tries before ``order_sequence`` reveals the answer. The matching and
#: labelling games reveal a single item after this many wrong attempts on it, so a
#: learner is never left grinding one stubborn pairing.
_MAX_TRIES = 3


def _esc(value: Any) -> str:
    """Escape a spec string for a double-quoted HTML attribute."""
    return html.escape(str(value if value is not None else ''), quote=True)


# --------------------------------------------------------------------------- shared
#: Helpers every engine in this module uses. Prefixed with ``_`` so they cannot collide
#: with the runtime's own names (``scale``, ``fmt``, ``colour`` ...), and small enough
#: that copying them into one string is clearer than a second runtime.
_PRELUDE = r"""
function _range(k) { var a = []; for (var i = 0; i < k; i++) a.push(i); return a; }
function _inRect(p, r) {
  return p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;
}
function _fit(t, m) {
  t = String(t == null ? '' : t);
  return t.length <= m ? t : t.slice(0, Math.max(1, m - 1)) + '\u2026';
}
function _dist(a, b) {
  var dx = a.x - b.x, dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}
// One transparent rectangle over the whole stage. Drags are wired here, never to a
// tile, because point(event, node) measures against the node's own box - exact for a
// full-viewBox rectangle, and drifting for a small tile that is itself moving.
function _overlay(scene) {
  return svg('rect', { x: 0, y: 0, width: W, height: H, fill: 'transparent',
                       'pointer-events': 'all' }, scene);
}
// The in-scene eyebrow: a column heading, not a sentence. SVG text does not inherit
// `color`, so the fill is set explicitly to the tertiary ink the type scale reserves
// for captions. Used for column headings and the ordering axis, so a learner reads
// the structure of the board before reading any of its content.
function _eyebrow(parent, x, y, text, anchor) {
  var t = svg('text', { x: x, y: y, 'text-anchor': anchor || 'start',
                        'font-size': 9.5, 'font-weight': 700, 'letter-spacing': '0.13em',
                        fill: colour('faint') }, parent);
  t.textContent = text;
  return t;
}
// Card text is set explicitly: the `.tile text` rule in the shared CSS only matches
// text *inside* the rect, and these cards put their label as a sibling, so without
// this every card rendered at the 16px SVG default - off the type scale, and wide
// enough that long steps overflowed their tile.
function _cardText(parent, x, y, text, size) {
  var t = svg('text', { x: x, y: y, 'font-size': size || 12.5 }, parent);
  t.textContent = text;
  return t;
}
"""


# ================================================================ order_sequence

def _body_order(spec: Mapping[str, Any]) -> str:
    label = _esc(spec.get('title') or 'Order the steps')
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        'aria-label="' + label + ': a shuffled column of steps on the left, numbered '
        'slots on the right; drag each step into its place"></svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="prompt"></span>'
        '<span class="spacer"></span>'
        '<button id="reset">Reset</button>'
        '<button class="primary" id="check">Check</button>'
        '</div>'
        '</div>')


_ENGINE_ORDER = _PRELUDE + r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var items = (spec.items || []).slice();
  var n = items.length;
  var answer = items.map(function (it) { return it.id; });
  var seed = (spec.seed === undefined || spec.seed === null) ? 11 : (+spec.seed || 11);
  var dealt = shuffle(answer, seed);
  if (n > 1 && dealt.join('|') === answer.join('|')) dealt = shuffle(answer, seed + 1);

  // The shuffled column is wide enough for the longest step these games actually carry
  // ("If it matches, stop and report the position."). At 300 the card text ellipsised
  // the one step a learner most needs to read in full.
  var POOL_X = 26, POOL_W = 320, SLOT_X = 392, SLOT_W = 442;
  var MAX_TRIES = __MAX_TRIES__;
  // Rows are fitted to the height the canvas actually has instead of being pinned to
  // a 38px constant. With five steps a fixed row left the bottom 40% of the stage
  // empty - the page looked unfinished rather than sparse - and the note text only
  // appeared after a failed try, so the tiles had nothing to fill that space with.
  var TOP = 48, ROW_H = 38, ROW_GAP = 8;
  (function fitRows() {
    var band = 434 - TOP;
    var h = clamp((band - (n - 1) * 22) / n, 38, 74);
    var gap = n > 1 ? clamp((band - n * h) / (n - 1), 8, 22) : 0;
    var used = n * h + (n - 1) * gap;
    ROW_H = h;
    ROW_GAP = gap;
    TOP = TOP + Math.max(0, (band - used) / 2);
  })();

  var state = { slots: [], pool: dealt.slice(), tries: 0, solved: false,
                selected: null, revealed: false, layout: {}, nodes: {},
                slotBoxes: [], gesture: false };
  for (var i = 0; i < n; i++) state.slots.push(null);

  var gSlots = svg('g', { 'data-series': 'order-slots' }, scene);
  var gTiles = svg('g', { 'data-series': 'order-tiles' }, scene);
  var overlay = _overlay(scene);

  var placedChip = UI.chip('placed', 'Placed', 'a');

  function itemById(id) {
    for (var i = 0; i < n; i++) if (items[i].id === id) return items[i];
    return null;
  }
  function slotIndexOf(id) {
    for (var k = 0; k < n; k++) if (state.slots[k] === id) return k;
    return -1;
  }
  function rowY(k) { return TOP + k * (ROW_H + ROW_GAP); }

  function drawTile(id, x, y, w, showNote) {
    var it = itemById(id);
    var g = svg('g', { 'data-series': id, transform: 'translate(' + x + ',' + y + ')' },
                gTiles);
    var r = svg('rect', { x: 0, y: 0, width: w, height: ROW_H, rx: 9, class: 'tile' }, g);
    if (state.selected === id) {
      // Inline style, not attributes: the `.tile` rule in the shared stylesheet wins
      // over a presentation attribute, which made the selected tile look unselected.
      r.style.fill = 'rgba(71,81,156,0.10)';
      r.style.stroke = colour('a');
      r.style.strokeWidth = '2.4';
    }
    var main = _cardText(g, 13, showNote ? ROW_H / 2 - 3 : ROW_H / 2 + 4.5,
                         _fit(it ? it.text : id, Math.floor((w - 26) / 6.3)));
    // A step longer than its card still ellipsises, so the full sentence is available
    // on hover rather than lost.
    var full = svg('title', null, g);
    full.textContent = it ? it.text : id;
    if (showNote && it && it.note) {
      var nt = svg('text', { x: 13, y: ROW_H / 2 + 15, class: 'note' }, g);
      nt.textContent = _fit(it.note, Math.floor((w - 26) / 5.4));
    }
    state.nodes[id] = g;
    state.layout[id] = { x: x, y: y, w: w, h: ROW_H };
  }

  function render() {
    clear(gSlots);
    clear(gTiles);
    state.layout = {}; state.nodes = {}; state.slotBoxes = [];
    // Column headings as eyebrows rather than sentences: they name the two zones, and
    // at 9.5px they stop competing with the steps themselves for the eye.
    _eyebrow(gSlots, POOL_X, rowY(0) - 16, 'SHUFFLED STEPS');
    _eyebrow(gSlots, SLOT_X, rowY(0) - 16, 'YOUR ORDER');
    for (var k = 0; k < n; k++) {
      var y = rowY(k);
      var box = svg('rect', { x: SLOT_X, y: y, width: SLOT_W, height: ROW_H, rx: 9,
                              class: 'bin' }, gSlots);
      box.setAttribute('data-slot', k);
      state.slotBoxes.push(box);
      // The slot number sits in a badge so it reads as a position marker rather than as
      // a stray digit in the gutter.
      svg('circle', { cx: SLOT_X - 20, cy: y + ROW_H / 2, r: 12, fill: colour('surface2'),
                      stroke: colour('edge'), 'stroke-width': 1 }, gSlots);
      var num = svg('text', { x: SLOT_X - 20, y: y + ROW_H / 2 + 4, 'text-anchor': 'middle',
                              'font-size': 11, 'font-weight': 700,
                              fill: colour('dim') }, gSlots);
      num.textContent = String(k + 1);
    }
    for (var a = 0; a < n; a++) {
      if (state.slots[a] !== null) drawTile(state.slots[a], SLOT_X, rowY(a), SLOT_W, state.revealed);
    }
    for (var p = 0; p < state.pool.length; p++) {
      drawTile(state.pool[p], POOL_X, rowY(p), POOL_W, false);
    }
  }

  function hitTile(pt) {
    var best = null, bestD = 1e9;
    Object.keys(state.layout).forEach(function (id) {
      var r = state.layout[id];
      if (_inRect(pt, r)) {
        var d = _dist(pt, { x: r.x + r.w / 2, y: r.y + r.h / 2 });
        if (d < bestD) { bestD = d; best = id; }
      }
    });
    return best;
  }
  function slotAt(pt) {
    if (pt.x < SLOT_X - 30 || pt.x > SLOT_X + SLOT_W + 30) return { kind: 'pool' };
    if (pt.y < TOP - 12 || pt.y > rowY(n - 1) + ROW_H + 12) return { kind: 'pool' };
    return { kind: 'slot', index: clamp(Math.floor((pt.y - TOP) / (ROW_H + ROW_GAP)), 0, n - 1) };
  }

  function moveTo(id, target) {
    var fromSlot = slotIndexOf(id);
    if (fromSlot >= 0) state.slots[fromSlot] = null;
    else { var pi = state.pool.indexOf(id); if (pi >= 0) state.pool.splice(pi, 1); }
    if (target.kind === 'pool') { state.pool.push(id); return; }
    var occ = state.slots[target.index];
    if (occ !== null && occ !== id) {
      if (fromSlot >= 0) state.slots[fromSlot] = occ;
      else state.pool.push(occ);
    }
    state.slots[target.index] = id;
  }

  function readout() {
    var placed = 0;
    for (var k = 0; k < n; k++) if (state.slots[k] !== null) placed++;
    placedChip.set(placed + '/' + n);
    UI.progress(placed, n);
    BRIDGE.readout({ placed: placed, total: n, remaining: n - placed });
  }

  function markPositions() {
    for (var k = 0; k < n; k++) {
      var id = state.slots[k];
      if (id === null) continue;
      var g = state.nodes[id];
      if (!g) continue;
      var r = g.querySelector('rect');
      if (r) r.setAttribute('data-state', id === answer[k] ? 'correct' : 'wrong');
    }
  }

  function notesLine() {
    var parts = [];
    for (var i = 0; i < n; i++) if (items[i].note) parts.push((i + 1) + '. ' + items[i].note);
    return parts.join('  ');
  }

  function finish(correct, gaveUp) {
    state.solved = true;
    state.selected = null;
    document.getElementById('check').disabled = true;
    document.getElementById('reset').disabled = true;
    BRIDGE.outcome({
      correct: correct, tries: gaveUp ? state.tries : state.tries + 1, total: n,
      detail: { gave_up: !!gaveUp, order: state.slots.slice(), answer: answer.slice(),
                seed: seed }
    });
  }

  function check() {
    if (state.solved) return;
    var missing = state.pool.length;
    if (missing > 0) {
      UI.feedback('Place all ' + n + ' steps before checking - ' + missing
        + (missing === 1 ? ' is' : ' are') + ' still in the shuffled column.', false);
      return;
    }
    state.selected = null;
    var ok = true;
    for (var k = 0; k < n; k++) if (state.slots[k] !== answer[k]) { ok = false; break; }
    if (ok) {
      render();
      markPositions();
      UI.feedback('Correct - that is the right order. ' + (spec.why || '') + ' '
        + notesLine(), true);
      finish(true, false);
      return;
    }
    state.tries += 1;
    if (state.tries >= MAX_TRIES) {
      state.revealed = true;
      state.pool = [];
      state.slots = answer.slice();
      render();
      markPositions();
      UI.feedback('Three tries, so here is the correct order, with a note on each step. '
        + notesLine(), false);
      finish(false, true);
      return;
    }
    render();
    markPositions();
    var firstWrong = -1, rightCount = 0;
    for (var j = 0; j < n; j++) {
      if (state.slots[j] === answer[j]) rightCount++;
      else if (firstWrong < 0) firstWrong = j;
    }
    UI.feedback(rightCount + ' of ' + n + ' are already in the right place. Position '
      + (firstWrong + 1) + ' is not: ask what has to happen immediately *before* the step '
      + 'you put there. ' + (MAX_TRIES - state.tries) + ' try left.', false);
  }

  function handleTap(pt) {
    if (state.solved) return;
    var id = hitTile(pt);
    if (id) { state.selected = (state.selected === id ? null : id); render(); readout(); return; }
    if (state.selected) {
      moveTo(state.selected, slotAt(pt));
      state.selected = null;
      render();
      readout();
    }
  }

  // One pointerdown can be a tap (handled by drag()'s end) or a click (handled below).
  // This listener runs first and clears the flag; drag() sets it again only when it
  // accepts the gesture. So the click that follows an accepted tap is ignored - no
  // double handling - while a pointerdown drag() refuses still reaches handleTap.
  // (A timestamp guard cannot do this: it would also swallow a fast second click.)
  overlay.addEventListener('pointerdown', function () { state.gesture = false; });

  drag(overlay, {
    start: function (pt) {
      if (state.solved) return false;
      var id = hitTile(pt);
      if (!id) return false;
      var l = state.layout[id];
      state.gesture = true;
      // Selection is deliberately NOT set here: a pointerdown that turns out to be a
      // tap is finished by handleTap(), which owns the toggle. Setting it here would
      // make a tap select and immediately deselect.
      return { id: id, dx: pt.x - l.x, dy: pt.y - l.y, sx: pt.x, sy: pt.y, moved: false };
    },
    move: function (pt, held) {
      if (_dist(pt, { x: held.sx, y: held.sy }) > 5) held.moved = true;
      var g = state.nodes[held.id];
      if (g) g.setAttribute('transform',
        'translate(' + (pt.x - held.dx) + ',' + (pt.y - held.dy) + ')');
      var t = slotAt(pt);
      state.slotBoxes.forEach(function (b, k) {
        if (t.kind === 'slot' && k === t.index) b.setAttribute('data-over', '1');
        else b.removeAttribute('data-over');
      });
    },
    end: function (pt, held) {
      state.slotBoxes.forEach(function (b) { b.removeAttribute('data-over'); });
      if (!held.moved) { handleTap(pt); return; }
      moveTo(held.id, slotAt(pt));
      state.selected = null;
      render();
      readout();
    }
  });

  // A pointerdown over empty space is refused by drag(), so no pointerup fires there;
  // the browser's own click still does, and this is where a tap-on-a-slot lands.
  overlay.addEventListener('click', function (ev) {
    if (state.gesture) return;
    handleTap(point(ev, overlay));
  });

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    state.slots = [];
    for (var i = 0; i < n; i++) state.slots.push(null);
    state.pool = dealt.slice();
    state.tries = 0; state.solved = false; state.selected = null; state.revealed = false;
    document.getElementById('check').disabled = false;
    document.getElementById('reset').disabled = false;
    UI.feedback('');
    render();
    readout();
  });

  document.getElementById('prompt').textContent = spec.prompt || '';
  render();
  readout();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


ORDER_SEQUENCE = Archetype(
    id='order_sequence',
    title='Put it in order',
    blurb='Drag a shuffled set of steps into the correct sequence, then check your order.',
    interaction='drag steps into numbered slots and commit with Check',
    subjects=('mathematics', 'science', 'economics'),
    tags=('sequence', 'ordering', 'process', 'timeline', 'drag-and-drop'),
    reference='Sequencing / ordering tasks across the curriculum (water cycle, mitosis, '
              'algorithms, historical timelines)',
    telemetry='One outcome per board: whether the final order was right, the tries taken, '
              'and whether the answer had to be revealed (gave_up).',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('prompt', 'text', 'The question above the board, e.g. "Put the stages of '
                                'mitosis in order."'),
        Field('items', 'table',
              'The steps in their CORRECT order; the game shuffles them for the learner. '
              'One row per step.',
              minimum_items=3, maximum_items=8,
              item_fields=(
                  Field('id', 'text', 'Stable identifier, unique within the game.'),
                  Field('text', 'text', 'The step as the learner sees it.'),
                  Field('note', 'text', 'Why this step sits here; shown when the order is '
                                        'revealed.', required=False),
              )),
        Field('seed', 'int', 'Optional shuffle seed; the same seed always deals the same '
                             'board.', required=False, minimum=0, maximum=100000),
        Field('why', 'text', 'One sentence on what the sequence represents, shown on a '
                             'correct answer.', required=False),
    ),
    body=_body_order,
    engine=lambda spec: _ENGINE_ORDER,
)


# ================================================================ matching_pairs

def _body_match(spec: Mapping[str, Any]) -> str:
    label = _esc(spec.get('title') or 'Match the pairs')
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        'aria-label="' + label + ': two columns; select an item on one side, then its '
        'partner on the other, or drag one onto the other"></svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="prompt"></span>'
        '<span class="spacer"></span>'
        '<button id="reset">Reset</button>'
        '</div>'
        '</div>')


_ENGINE_MATCH = _PRELUDE + r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var pairs = (spec.pairs || []).slice();
  var n = pairs.length;
  var seed = (spec.seed === undefined || spec.seed === null) ? 5 : (+spec.seed || 5);
  var leftOrder = shuffle(_range(n), seed);
  var rightOrder = shuffle(_range(n), seed + 101);
  if (n > 1 && leftOrder.join('|') === rightOrder.join('|')) {
    rightOrder = shuffle(_range(n), seed + 202);
  }

  // The two columns use the full height of the canvas, not a fixed 42px row: a board
  // of six pairs pinned to the top left two thirds of the stage empty. The pitch is
  // derived from the height so three pairs and seven pairs both sit as a column.
  var LEFT_X = 32, RIGHT_X = 476, COL_W = 352;
  var MID = (LEFT_X + COL_W + RIGHT_X) / 2;
  var HEAD_Y = 46, TOP_LIMIT = 64, BOT_LIMIT = H - 24;
  var span = BOT_LIMIT - TOP_LIMIT;
  var pitch = span / Math.max(1, n);
  var ROW_H = clamp(Math.round(pitch * 0.74), 34, 56);
  var ROW_GAP = Math.max(10, Math.round(pitch) - ROW_H);
  var totalH = n * ROW_H + (n - 1) * ROW_GAP;
  var TOP = Math.round(TOP_LIMIT + (span - totalH) / 2);

  var state = { matched: {}, revealed: {}, selected: null, wrong: 0, wrongBy: {},
                flash: null, done: false, nodes: {}, rects: {}, gesture: false };
  var flashTimer = null;

  var gLinks = svg('g', { 'data-series': 'matches' }, scene);
  var gNubs = svg('g', { 'data-series': 'connectors' }, scene);
  var gItems = svg('g', { 'data-series': 'terms' }, scene);
  var rubber = svg('line', { stroke: colour('a'), 'stroke-width': 2,
                             'stroke-dasharray': '5 4', opacity: 0 }, gLinks);
  var overlay = _overlay(scene);

  // No series dot on this one. Every other chip names a *thing* - a pair, a term, a
  // colour - and the dot ties the number to the mark it describes. A count of wrong
  // attempts names no mark, and tinting it clay put a series hue on a judgement, which
  // is the one thing the palette forbids.
  var wrongChip = UI.chip('wrong', 'Wrong attempts', '');

  function rowY(i) { return TOP + i * (ROW_H + ROW_GAP); }

  // Column headings and a hairline rule under each. Without them the two columns are
  // just two lists of cards; with them the board reads as "these join to those", and
  // the gutter between the rules is visibly the space a connection crosses.
  _eyebrow(gItems, LEFT_X, HEAD_Y, 'ITEMS');
  _eyebrow(gItems, RIGHT_X, HEAD_Y, 'PARTNERS');
  [LEFT_X, RIGHT_X].forEach(function (x) {
    svg('line', { x1: x, y1: HEAD_Y + 10, x2: x + COL_W, y2: HEAD_Y + 10,
                  stroke: colour('line'), 'stroke-width': 1 }, gItems);
  });

  function makeItem(side, pair, rowIndex, x) {
    var key = side + pair;
    var text = side === 'L' ? pairs[pair].left : pairs[pair].right;
    var g = svg('g', { 'data-series': key, transform: 'translate(' + x + ',' + rowY(rowIndex) + ')',
                       tabindex: '0', role: 'button' }, gItems);
    g.setAttribute('aria-label', (side === 'L' ? 'Item: ' : 'Partner: ') + text);
    var r = svg('rect', { x: 0, y: 0, width: COL_W, height: ROW_H, rx: 10, class: 'tile' }, g);
    _cardText(g, 14, ROW_H / 2 + 4.5, _fit(text, Math.floor((COL_W - 28) / 6.3)));
    var full = svg('title', null, g);
    full.textContent = text;
    state.nodes[key] = g;
    state.rects[key] = r;
    g.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
        ev.preventDefault();
        tap(side, pair);
      }
    });
    g.addEventListener('focus', function () {
      r.style.stroke = colour('a');
      r.style.strokeWidth = '2.5';
    });
    g.addEventListener('blur', function () { update(); });
    return g;
  }

  leftOrder.forEach(function (p, i) { makeItem('L', p, i, LEFT_X); });
  rightOrder.forEach(function (p, i) { makeItem('R', p, i, RIGHT_X); });

  function update() {
    clear(gLinks);
    gLinks.appendChild(rubber);
    Object.keys(state.nodes).forEach(function (key) {
      var r = state.rects[key];
      var pair = +key.slice(1), side = key.charAt(0);
      var isMatched = !!state.matched[pair];
      var isSel = state.selected && state.selected.side === side && state.selected.p === pair;
      var isFlash = state.flash && (state.flash.l === pair || state.flash.r === pair);
      // Presentation attributes lose to the `.tile` rules in the shared stylesheet, so
      // the selected and revealed states are set as inline style. Set as attributes,
      // they were silently overridden and the selected card looked exactly like every
      // other card - the affordance existed only in the code.
      r.removeAttribute('data-state');
      r.style.stroke = '';
      r.style.strokeWidth = '';
      r.style.fill = '';
      if (isFlash) {
        r.setAttribute('data-state', 'wrong');
      } else if (isMatched) {
        r.setAttribute('data-state', 'correct');
        r.style.fill = 'rgba(44,92,62,0.06)';
        if (state.revealed[pair]) r.style.stroke = colour('d');
      } else if (isSel) {
        r.style.fill = 'rgba(71,81,156,0.10)';
        r.style.stroke = colour('a');
        r.style.strokeWidth = '2.4';
      }
    });
    var li = {}, ri = {};
    leftOrder.forEach(function (p, i) { li[p] = i; });
    rightOrder.forEach(function (p, i) { ri[p] = i; });
    Object.keys(state.matched).forEach(function (ps) {
      var p = +ps;
      var col = colour(state.revealed[p] ? 'd' : 'good');
      var y1 = rowY(li[p]) + ROW_H / 2, y2 = rowY(ri[p]) + ROW_H / 2;
      svg('line', { x1: LEFT_X + COL_W, y1: y1, x2: RIGHT_X, y2: y2, stroke: col,
                    'stroke-width': 2.4, opacity: 0.85 }, gLinks);
      svg('circle', { cx: LEFT_X + COL_W, cy: y1, r: 4, fill: col }, gLinks);
      svg('circle', { cx: RIGHT_X, cy: y2, r: 4, fill: col }, gLinks);
    });
    // At rest every card carries a connector nub on its inner edge. They are what make
    // the gutter read as the place a connection goes, before anything is connected; a
    // matched pair replaces its two nubs with the line itself.
    clear(gNubs);
    Object.keys(state.nodes).forEach(function (key) {
      var pair = +key.slice(1), side = key.charAt(0);
      if (state.matched[pair]) return;
      var i = side === 'L' ? li[pair] : ri[pair];
      svg('circle', { cx: side === 'L' ? LEFT_X + COL_W + 9 : RIGHT_X - 9,
                      cy: rowY(i) + ROW_H / 2, r: 2.6, fill: colour('edge') }, gNubs);
    });
    // A half-drawn connector from the selected card into the gutter: the board says
    // "now pick the other side" instead of leaving the learner to remember.
    if (state.selected) {
      var sp = state.selected.p;
      var si = state.selected.side === 'L' ? li[sp] : ri[sp];
      var cy = rowY(si) + ROW_H / 2;
      var x0 = state.selected.side === 'L' ? LEFT_X + COL_W : RIGHT_X;
      var x1 = state.selected.side === 'L' ? MID - 6 : MID + 6;
      svg('line', { x1: x0, y1: cy, x2: x1, y2: cy, stroke: colour('a'), 'stroke-width': 2,
                    'stroke-dasharray': '4 4', 'stroke-linecap': 'round' }, gLinks);
      svg('circle', { cx: x1, cy: cy, r: 4.5, fill: colour('a') }, gLinks);
    }
    rubber.setAttribute('opacity', 0);
  }

  function readout() {
    wrongChip.set(String(state.wrong));
    UI.progress(Object.keys(state.matched).length, n);
    BRIDGE.readout({ matched: Object.keys(state.matched).length, total: n,
                     wrong_attempts: state.wrong,
                     selected: state.selected ? (state.selected.side + state.selected.p) : null });
  }

  function finish() {
    state.done = true;
    var revealed = Object.keys(state.revealed).length;
    var gaveUp = revealed > 0;
    // The attempts worth reporting are the ones spent on the hardest item, not the total
    // across the board: a give-up is caused by a single pair reaching the three-try
    // budget, so this reads 3 on a give-up and the worst pair's count otherwise. Same
    // shape as order_sequence's `gaveUp ? tries : tries + 1`.
    var maxWrong = 0;
    Object.keys(state.wrongBy).forEach(function (k) {
      if (state.wrongBy[k] > maxWrong) maxWrong = state.wrongBy[k];
    });
    UI.feedback(gaveUp
      ? 'All ' + n + ' pairs are matched - but ' + revealed + ' had to be revealed after '
        + 'three tries each. The ones you found unaided: ' + (n - revealed) + '.'
      : 'All ' + n + ' pairs matched with ' + state.wrong + ' wrong attempt'
        + (state.wrong === 1 ? '' : 's') + '. Every item is connected to its partner.',
      !gaveUp);
    BRIDGE.outcome({ correct: !gaveUp, tries: gaveUp ? maxWrong : maxWrong + 1,
                     wrong_attempts: state.wrong, pairs: n,
                     detail: { revealed: revealed, gave_up: gaveUp } });
  }

  function attempt(lp, rp) {
    if (state.done || state.matched[lp] || state.matched[rp]) return;
    state.selected = null;
    if (lp === rp) {
      state.matched[lp] = true;
      update();
      readout();
      UI.feedback('Correct - "' + pairs[lp].left + '" matches "' + pairs[lp].right + '". '
        + (pairs[lp].note || ''), true);
      if (Object.keys(state.matched).length >= n) finish();
      return;
    }
    state.wrong += 1;
    state.wrongBy[lp] = (state.wrongBy[lp] || 0) + 1;
    if (state.wrongBy[lp] >= 3 && !state.matched[lp]) {
      state.revealed[lp] = true;
      state.matched[lp] = true;
      state.flash = null;
      update();
      readout();
      UI.feedback('Three tries on "' + pairs[lp].left + '", so here is its partner: "'
        + pairs[lp].right + '". ' + (pairs[lp].note || ''), false);
      if (Object.keys(state.matched).length >= n) finish();
      return;
    }
    state.flash = { l: lp, r: rp };
    update();
    readout();
    UI.feedback('Not a match: "' + pairs[lp].left + '" does not belong with "'
      + pairs[rp].right + '". Ask what each one means before joining them.', false);
    if (flashTimer) window.clearTimeout(flashTimer);
    flashTimer = window.setTimeout(function () { state.flash = null; update(); }, 700);
  }

  function tap(side, pair) {
    if (state.done || state.matched[pair]) return;
    if (state.selected && state.selected.side === side && state.selected.p === pair) {
      state.selected = null;
      update();
      return;
    }
    if (!state.selected) {
      state.selected = { side: side, p: pair };
      update();
      readout();
      return;
    }
    if (state.selected.side === side) {
      state.selected = { side: side, p: pair };
      update();
      return;
    }
    var lp = side === 'L' ? pair : state.selected.p;
    var rp = side === 'R' ? pair : state.selected.p;
    attempt(lp, rp);
  }

  function itemAt(pt) {
    var found = null;
    Object.keys(state.rects).forEach(function (key) {
      var pair = +key.slice(1), side = key.charAt(0);
      if (state.matched[pair]) return;
      var i = side === 'L' ? leftOrder.indexOf(pair) : rightOrder.indexOf(pair);
      if (i < 0) return;
      var x = side === 'L' ? LEFT_X : RIGHT_X;
      if (_inRect(pt, { x: x, y: rowY(i), w: COL_W, h: ROW_H })) {
        found = { side: side, p: pair };
      }
    });
    return found;
  }

  // Cleared on every pointerdown, set again only when drag() accepts it - so the
  // click that follows an accepted tap is ignored, while a refused one still reaches
  // the click handler. A timestamp guard would also swallow a fast second click.
  overlay.addEventListener('pointerdown', function () { state.gesture = false; });

  drag(overlay, {
    start: function (pt) {
      if (state.done) return false;
      var it = itemAt(pt);
      if (!it) return false;
      state.gesture = true;
      return { side: it.side, p: it.p, sx: pt.x, sy: pt.y, moved: false };
    },
    move: function (pt, held) {
      if (_dist(pt, { x: held.sx, y: held.sy }) > 6) held.moved = true;
      if (!held.moved) return;
      var i = held.side === 'L' ? leftOrder.indexOf(held.p) : rightOrder.indexOf(held.p);
      rubber.setAttribute('x1', held.side === 'L' ? LEFT_X + COL_W : RIGHT_X);
      rubber.setAttribute('y1', rowY(i) + ROW_H / 2);
      rubber.setAttribute('x2', pt.x);
      rubber.setAttribute('y2', pt.y);
      rubber.setAttribute('opacity', 0.9);
    },
    end: function (pt, held) {
      rubber.setAttribute('opacity', 0);
      if (!held.moved) { tap(held.side, held.p); return; }
      var target = itemAt(pt);
      if (!target || target.side === held.side) { update(); return; }
      var lp = held.side === 'L' ? held.p : target.p;
      var rp = held.side === 'R' ? held.p : target.p;
      attempt(lp, rp);
    }
  });

  overlay.addEventListener('click', function (ev) {
    if (state.gesture) return;
    var it = itemAt(point(ev, overlay));
    if (it) tap(it.side, it.p);
  });

  document.getElementById('reset').addEventListener('click', function () {
    state.matched = {}; state.revealed = {}; state.selected = null;
    state.wrong = 0; state.wrongBy = {}; state.flash = null; state.done = false;
    if (flashTimer) { window.clearTimeout(flashTimer); flashTimer = null; }
    UI.feedback('');
    update();
    readout();
  });

  document.getElementById('prompt').textContent = spec.prompt || '';
  update();
  readout();
}
"""


MATCHING_PAIRS = Archetype(
    id='matching_pairs',
    title='Match the pairs',
    blurb='Join each item on the left to its partner on the right - click, or drag them together.',
    interaction='select-then-select or drag one item onto its partner',
    subjects=('mathematics', 'science', 'economics'),
    tags=('matching', 'vocabulary', 'definitions', 'drag-and-drop', 'keyboard'),
    reference='Match-the-pairs / connect-the-columns activities across the curriculum',
    telemetry='One outcome per board: the tries taken on the hardest pair, how many wrong '
              'attempts were made and how many pairs had to be revealed; correct is false '
              'when anything was given away.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('prompt', 'text', 'The question above the board, e.g. "Match each term to '
                                'its meaning."'),
        Field('pairs', 'table',
              'One row per match: a left item and the right item it belongs with.',
              minimum_items=3, maximum_items=7,
              item_fields=(
                  Field('left', 'text', 'Left-hand item (term, symbol, formula).'),
                  Field('right', 'text', 'Right-hand partner (definition, meaning, name).'),
                  Field('note', 'text', 'The reasoning shown when the pair is matched.',
                        required=False),
              )),
        Field('seed', 'int', 'Optional shuffle seed; the same seed always deals the same '
                             'columns.', required=False, minimum=0, maximum=100000),
    ),
    body=_body_match,
    engine=lambda spec: _ENGINE_MATCH,
)


# ================================================================ label_diagram

def _body_label(spec: Mapping[str, Any]) -> str:
    label = _esc(spec.get('title') or 'Label the diagram')
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        'aria-label="' + label + ': a diagram with dashed hotspots above a tray of '
        'labels; drag each label onto the hotspot it belongs to"></svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="prompt"></span>'
        '<span class="spacer"></span>'
        '<button id="reset">Reset</button>'
        '</div>'
        '</div>')


_ENGINE_LABEL = _PRELUDE + r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var shapes = (spec.shapes || []).slice();
  var labels = (spec.labels || []).slice();
  var n = labels.length;
  var seed = (spec.seed === undefined || spec.seed === null) ? 3 : (+spec.seed || 3);
  var order = shuffle(_range(n), seed);
  var DEF_R = 40;

  var TRAY_Y = 398, PILL_H = 34;
  var state = { placed: {}, tries: {}, revealed: 0, wrong: 0, done: false,
                selected: null, nodes: {}, rects: {}, dragNode: null, gesture: false };

  var gDiagram = svg('g', { 'data-series': 'diagram' }, scene);
  var gHot = svg('g', { 'data-series': 'hotspots' }, scene);
  var gPlaced = svg('g', { 'data-series': 'placed-labels' }, scene);
  var gTray = svg('g', { 'data-series': 'label-tray' }, scene);
  var overlay = _overlay(scene);

  var placedChip = UI.chip('placed', 'Labels placed', 'a');

  // ---- fit the diagram to the canvas --------------------------------------
  // A spec describes its parts in its own units: a cell of radius 200, a network of
  // radius 60. Drawn literally, the small ones sit as a stamp in the middle of a
  // mostly empty card - the animal cell occupied 43% of its canvas, the star network
  // 55%. Rather than ask every author to guess a scale, measure what the spec
  // describes and fit it to the space above the tray.
  //
  // The transform is applied to the coordinates as they are drawn, never as an SVG
  // group transform. A group transform would leave `hotspotAt` comparing a pointer
  // position in scene space against hotspot centres in the group's local space, and
  // every drop would miss.
  var DIAG_TOP = 8, DIAG_BOTTOM = TRAY_Y - 30;
  function diagramBounds() {
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    function take(ax, ay, bx, by) {
      x0 = Math.min(x0, ax); y0 = Math.min(y0, ay);
      x1 = Math.max(x1, bx); y1 = Math.max(y1, by);
    }
    shapes.forEach(function (s) {
      if (s.kind === 'line') take(Math.min(+s.x, +s.w), Math.min(+s.y, +s.h),
                                  Math.max(+s.x, +s.w), Math.max(+s.y, +s.h));
      else if (s.kind === 'circle') {
        var r = Math.max(2, (+s.w) / 2);
        take(+s.x - r, +s.y - r, +s.x + r, +s.y + r);
      } else take(+s.x, +s.y, +s.x + Math.max(1, +s.w), +s.y + Math.max(1, +s.h));
    });
    labels.forEach(function (lb) {
      var r = (+lb.radius) || DEF_R;
      take(+lb.x - r, +lb.y - r, +lb.x + r, +lb.y + r);
    });
    return Number.isFinite(x0) && x1 > x0
      ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : null;
  }
  var dBounds = diagramBounds();

  // Where the tray goes is decided *before* the diagram is fitted, because the answer
  // changes how much canvas the diagram may use. A wide drawing already spans the card
  // and keeps the tray underneath it; a square or tall one cannot, and the gutter it
  // leaves either side is exactly where a column of pills belongs. The animal cell
  // (1.2:1) was fitted above a full-width row and so used 44% of its canvas; the star
  // network (2.6:1) is untouched by this.
  function pillW(text) { return clamp(30 + String(text).length * 6.4, 78, 190); }
  var gap = 10;
  var widestPill = n ? Math.max.apply(null, labels.map(function (l) { return pillW(l.text); })) : 120;
  var aspect = dBounds ? dBounds.w / Math.max(1, dBounds.h) : 1;
  var sideTray = aspect < 1.5;
  var trayColW = sideTray ? Math.round(clamp(widestPill + 4, 120, 210)) : 0;
  var trayColX = W - 16 - trayColW;

  var DIAG_TOP = 8, DIAG_BOTTOM = sideTray ? 452 : TRAY_Y - 30;
  var DIAG_L = 16, DIAG_R = sideTray ? trayColX - 20 : W - 16;
  var dk = 1, dox = 0, doy = 0;
  if (dBounds) {
    var availW = DIAG_R - DIAG_L, availH = DIAG_BOTTOM - DIAG_TOP;
    dk = Math.min(availW / Math.max(1, dBounds.w), availH / Math.max(1, dBounds.h));
    dk = clamp(dk, 0.2, 2.6);                 // never shrink to a dot, never balloon
    dox = DIAG_L + (availW - dBounds.w * dk) / 2 - dBounds.x * dk;
    doy = DIAG_TOP + (availH - dBounds.h * dk) / 2 - dBounds.y * dk;
  }
  function dx(v) { return dox + v * dk; }
  function dy(v) { return doy + v * dk; }
  function ds(v) { return v * dk; }

  // ---- the declarative diagram -------------------------------------------
  // Only three shapes, and one optional fill switch. A labelling exercise must not
  // become a drawing tool: the spec says where the parts are, and the archetype draws
  // them. Colours come from the shared palette so a diagram matches every other game.
  //
  // A connector declared centre-to-centre would run straight through the node it joins
  // and show as a chord across the tinted fill - on the star network the two diagonals
  // crossed inside the hub and read as a mistake. Connectors are therefore trimmed to
  // the rim of any circle they start or end on. The trim is a drawing decision only:
  // `diagramBounds()` above still uses the declared endpoints, so the fit - and every
  // coordinate a drop is tested against - is unchanged.
  var circles = shapes.filter(function (s) { return s.kind === 'circle'; })
    .map(function (s) { return { x: +s.x, y: +s.y, r: Math.max(2, (+s.w) / 2) }; });
  function trimToRim(x0, y0, x1, y1) {
    var hit = null;
    circles.forEach(function (c) {
      if (Math.abs(c.x - x0) <= 4 && Math.abs(c.y - y0) <= 4 && (!hit || c.r > hit.r)) hit = c;
    });
    if (!hit) return [x0, y0];
    var ux = x1 - x0, uy = y1 - y0;
    var len = Math.sqrt(ux * ux + uy * uy) || 1;
    var push = Math.min(hit.r + 2, len * 0.45);
    return [x0 + ux / len * push, y0 + uy / len * push];
  }
  shapes.forEach(function (s) {
    var c = colour(s.colour || 'a');
    var mode = s.fill || 'light';
    var attrs = { fill: mode === 'none' ? 'none' : c,
                  'fill-opacity': mode === 'solid' ? 0.9 : 0.14,
                  stroke: c, 'stroke-width': 1.6 };
    if (s.kind === 'rect') {
      svg('rect', { x: dx(s.x), y: dy(s.y), width: Math.max(1, ds(+s.w)),
                    height: Math.max(1, ds(+s.h)),
                    rx: 6, fill: attrs.fill, 'fill-opacity': attrs['fill-opacity'],
                    stroke: c, 'stroke-width': 1.6 }, gDiagram);
    } else if (s.kind === 'circle') {
      svg('circle', { cx: dx(s.x), cy: dy(s.y), r: Math.max(2, ds((+s.w) / 2)),
                      fill: attrs.fill, 'fill-opacity': attrs['fill-opacity'],
                      stroke: c, 'stroke-width': 1.6 }, gDiagram);
    } else if (s.kind === 'line') {
      var a = trimToRim(+s.x, +s.y, +s.w, +s.h);
      var b = trimToRim(+s.w, +s.h, +s.x, +s.y);
      svg('line', { x1: dx(a[0]), y1: dy(a[1]), x2: dx(b[0]), y2: dy(b[1]), stroke: c,
                    'stroke-width': 2.4 }, gDiagram);
    }
  });

  // A hotspot is a *target*, not part of the drawing, so it must not look like an
  // organelle. Drawn at the label's own radius it did: on the cell the dashed circle
  // sat just inside the nucleus and read as a second membrane, and on the star network
  // it doubled every node's outline. A small fixed-size target ring around a numbered
  // badge cannot be mistaken for artwork - it is the same size on a 40px vacuole and a
  // 200px cell - while the *hit* area stays the spec's radius, so a drop anywhere on
  // the organelle still lands.
  labels.forEach(function (lb, i) {
    // Proportional to the hotspot so it never swamps a small part, but capped: past
    // 22px it stops being a target marker and becomes another organelle outline.
    var rr = clamp(ds((+lb.radius) || DEF_R) * 0.42, 14, 22);
    svg('circle', { cx: dx(lb.x), cy: dy(lb.y), r: rr,
                    fill: colour('card'), 'fill-opacity': 0.55,
                    stroke: colour('edge'), 'stroke-width': 1.2,
                    'stroke-dasharray': '4 3' }, gHot);
    svg('circle', { cx: dx(lb.x), cy: dy(lb.y), r: rr * 0.64, fill: colour('card'),
                    stroke: colour('edge'), 'stroke-width': 1.2 }, gHot);
    var num = svg('text', { x: dx(lb.x), y: dy(lb.y) + 4, 'text-anchor': 'middle',
                            'font-size': 11, 'font-weight': 700,
                            fill: colour('dim') }, gHot);
    num.textContent = String(i + 1);
  });

  // ---- the tray -----------------------------------------------------------
  // Two placements, chosen above from the diagram's own aspect ratio. In the row layout
  // every pill is capped to an equal share of the width and the row is centred; in the
  // column layout every pill is as wide as the column and the stack is centred, so the
  // tray never hugs an edge and never reads as a leftover.
  var trayPos = {};
  if (sideTray) {
    var stackH = n * PILL_H + (n - 1) * gap;
    var sy = Math.round((H - stackH) / 2);
    order.forEach(function (i, k) {
      trayPos[i] = { x: trayColX, y: sy + k * (PILL_H + gap), w: trayColW };
    });
  } else {
    var avail = W - 48 - (n - 1) * gap;
    var per = Math.floor(avail / n);
    var trayW = order.map(function (i) {
      return Math.min(pillW(labels[i].text), per);
    });
    var trayTotal = trayW.reduce(function (a, b) { return a + b; }, 0) + (n - 1) * gap;
    var tx = Math.max(24, Math.round((W - trayTotal) / 2));
    order.forEach(function (i, k) {
      trayPos[i] = { x: tx, y: TRAY_Y, w: trayW[k] };
      tx += trayW[k] + gap;
    });
  }

  function renderTray() {
    clear(gTray);
    state.nodes = {};
    state.rects = {};
    order.forEach(function (i) {
      if (state.placed[i]) return;
      var pos = trayPos[i];
      var g = svg('g', { 'data-series': 'label-' + i,
                         transform: 'translate(' + pos.x + ',' + pos.y + ')' }, gTray);
      var r = svg('rect', { x: 0, y: 0, width: pos.w, height: PILL_H, rx: 8,
                            class: 'tile' }, g);
      if (state.selected === i) {
        r.setAttribute('stroke', colour('a'));
        r.setAttribute('stroke-width', 2.5);
      }
      var t = svg('text', { x: 10, y: PILL_H / 2 + 4 }, g);
      t.textContent = _fit(labels[i].text, Math.floor((pos.w - 20) / 6.2));
      state.nodes[i] = g;
      state.rects[i] = { x: pos.x, y: pos.y, w: pos.w, h: PILL_H };
    });
  }

  function renderPlaced() {
    clear(gPlaced);
    labels.forEach(function (lb, i) {
      if (!state.placed[i]) return;
      var r = ds((+lb.radius) || DEF_R);
      var cx = dx(lb.x), cy = dy(lb.y);
      var tone = colour(state.tries[i] >= 3 ? 'd' : 'good');
      svg('circle', { cx: cx, cy: cy, r: 5, fill: tone }, gPlaced);
      var ty = (cy - r - 8 < 16) ? cy + r + 16 : cy - r - 8;
      // A paper-coloured halo keeps the label legible where it crosses the diagram.
      var t = svg('text', { x: cx, y: ty, 'text-anchor': 'middle', class: 'lbl',
                            fill: tone, 'paint-order': 'stroke',
                            stroke: colour('card'), 'stroke-width': 3.5,
                            'stroke-linejoin': 'round' }, gPlaced);
      t.textContent = lb.text;
    });
  }

  function hotspotAt(pt) {
    var best = null, bestD = 1e9;
    labels.forEach(function (lb, j) {
      var d = _dist(pt, { x: dx(lb.x), y: dy(lb.y) });
      if (d <= ds((+lb.radius) || DEF_R) && d < bestD) { bestD = d; best = j; }
    });
    return best;
  }

  function trayAt(pt) {
    var found = null;
    Object.keys(state.rects).forEach(function (k) {
      if (_inRect(pt, state.rects[k])) found = +k;
    });
    return found;
  }

  function readout() {
    var placed = Object.keys(state.placed).length;
    placedChip.set(placed + '/' + n);
    // Progress belongs in the chip and nowhere else. This used to overwrite `#prompt`
    // with "N labels left", which said the same thing twice and left the *task* off the
    // page entirely - the spec's own prompt never survived the first readout() call.
    BRIDGE.readout({ placed: placed, total: n, wrong_attempts: state.wrong });
  }

  function finish() {
    state.done = true;
    state.selected = null;
    var gaveUp = state.revealed > 0;
    // The attempts worth reporting are the ones spent on the hardest label, not the total
    // across the board: a give-up is caused by a single label reaching the three-try
    // budget, so this reads 3 on a give-up and the worst label's count otherwise. Same
    // shape as order_sequence's `gaveUp ? tries : tries + 1`.
    var maxWrong = 0;
    Object.keys(state.tries).forEach(function (k) {
      if (state.tries[k] > maxWrong) maxWrong = state.tries[k];
    });
    UI.feedback(gaveUp
      ? 'All ' + n + ' labels are placed - but ' + state.revealed + ' had to be revealed '
        + 'after three tries each.'
      : 'All ' + n + ' labels placed with ' + state.wrong + ' wrong drop'
        + (state.wrong === 1 ? '' : 's') + '. The diagram is labelled correctly.',
      !gaveUp);
    BRIDGE.outcome({ correct: !gaveUp, tries: gaveUp ? maxWrong : maxWrong + 1,
                     wrong_attempts: state.wrong, labels: n,
                     detail: { revealed: state.revealed, gave_up: gaveUp } });
  }

  function drop(i, pt) {
    var j = hotspotAt(pt);
    if (j === null) {
      renderTray();
      renderPlaced();
      UI.feedback('Drop the label onto one of the dashed hotspots - a drop outside them '
        + 'comes back to the tray.', false);
      readout();
      return;
    }
    if (j === i) {
      state.placed[i] = true;
      state.selected = null;
      renderTray();
      renderPlaced();
      UI.feedback('Correct - "' + labels[i].text + '" belongs here. '
        + (labels[i].note || ''), true);
      readout();
      if (Object.keys(state.placed).length >= n) finish();
      return;
    }
    state.wrong += 1;
    state.tries[i] = (state.tries[i] || 0) + 1;
    if (state.tries[i] >= 3) {
      state.revealed += 1;
      state.placed[i] = true;
      state.selected = null;
      renderTray();
      renderPlaced();
      UI.feedback('Three tries on "' + labels[i].text + '", so here it is: the hotspot '
        + 'that stays highlighted is its home. ' + (labels[i].note || ''), false);
      readout();
      if (Object.keys(state.placed).length >= n) finish();
      return;
    }
    renderTray();
    renderPlaced();
    UI.feedback('"' + labels[i].text + '" does not belong at that hotspot - a different '
      + 'label does. Try another.', false);
    readout();
  }

  function handleTap(pt) {
    if (state.done) return;
    var i = trayAt(pt);
    if (i !== null) {
      state.selected = (state.selected === i ? null : i);
      renderTray();
      return;
    }
    if (state.selected !== null) {
      var j = hotspotAt(pt);
      if (j !== null) {
        var held = state.selected;
        state.selected = null;
        drop(held, pt);
      }
    }
  }

  // See order_sequence: cleared on every pointerdown, set again only when drag()
  // accepts it, so an accepted tap's synthetic click is ignored but a refused
  // pointerdown (a tap on a hotspot) still reaches the click handler.
  overlay.addEventListener('pointerdown', function () { state.gesture = false; });

  drag(overlay, {
    start: function (pt) {
      if (state.done) return false;
      var i = trayAt(pt);
      if (i === null) return false;
      var pos = trayPos[i];
      state.gesture = true;
      state.dragNode = state.nodes[i];
      if (state.dragNode && state.dragNode.parentNode) {
        state.dragNode.parentNode.appendChild(state.dragNode);
      }
      return { i: i, dx: pt.x - pos.x, dy: pt.y - pos.y, sx: pt.x, sy: pt.y, moved: false };
    },
    move: function (pt, held) {
      if (_dist(pt, { x: held.sx, y: held.sy }) > 5) held.moved = true;
      if (state.dragNode) {
        state.dragNode.setAttribute('transform',
          'translate(' + (pt.x - held.dx) + ',' + (pt.y - held.dy) + ')');
      }
    },
    end: function (pt, held) {
      state.dragNode = null;
      if (!held.moved) { handleTap(pt); return; }
      state.selected = null;
      drop(held.i, pt);
    }
  });

  overlay.addEventListener('click', function (ev) {
    if (state.gesture) return;
    handleTap(point(ev, overlay));
  });

  document.getElementById('reset').addEventListener('click', function () {
    state.placed = {}; state.tries = {}; state.revealed = 0; state.wrong = 0;
    state.done = false; state.selected = null; state.dragNode = null;
    UI.feedback('');
    renderTray();
    renderPlaced();
    readout();
  });

  document.getElementById('prompt').textContent = spec.prompt || '';
  renderTray();
  renderPlaced();
  readout();
}
"""


LABEL_DIAGRAM = Archetype(
    id='label_diagram',
    title='Label the diagram',
    blurb='Drag each label from the tray onto the hotspot it names.',
    interaction='drag labels onto hotspots on a simple declarative diagram',
    subjects=('mathematics', 'science', 'economics'),
    tags=('diagram', 'labelling', 'drag-and-drop', 'vocabulary'),
    reference='Label-the-diagram tasks across the curriculum (cells, circuits, triangles, '
              'network topologies)',
    telemetry='One outcome per board: the tries taken on the hardest label, how many wrong '
              'drops were made and how many labels had to be revealed; correct is false '
              'when anything was given away.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('prompt', 'text', 'The question above the diagram, e.g. "Label the parts of '
                                'the cell."'),
        Field('shapes', 'table',
              'The diagram, drawn from three shapes. Coordinates are in the 860 x 372 '
              'diagram area; the label tray sits in the strip below it.',
              minimum_items=1, maximum_items=20,
              item_fields=(
                  Field('kind', 'text', 'Shape to draw.',
                        choices=('rect', 'circle', 'line')),
                  Field('x', 'float', 'rect/circle: left or centre x. line: start x.'),
                  Field('y', 'float', 'rect/circle: top or centre y. line: start y.'),
                  Field('w', 'float', 'rect: width. circle: diameter. line: end x.'),
                  Field('h', 'float', 'rect: height. line: end y. circle: ignored (repeat w).'),
                  Field('colour', 'text', 'Palette name.',
                        choices=('a', 'b', 'c', 'd', 'e', 'ink', 'dim', 'faint', 'edge'),
                        required=False),
                  Field('fill', 'text', 'How the shape is filled. Lines are always '
                                        'stroke-only.', choices=('none', 'light', 'solid'),
                        required=False),
              )),
        Field('labels', 'table',
              'Each label names one hotspot it must be dragged onto.',
              minimum_items=2, maximum_items=6,
              item_fields=(
                  Field('text', 'text', 'The label text.'),
                  Field('x', 'float', 'Hotspot centre x.'),
                  Field('y', 'float', 'Hotspot centre y.'),
                  Field('radius', 'float', 'Hotspot radius in stage units; defaults to 40.',
                        required=False, minimum=8, maximum=200),
                  Field('note', 'text', 'Why this label belongs here; shown when it locks '
                                        'in.', required=False),
              )),
        Field('seed', 'int', 'Optional shuffle seed for the tray order; the same seed '
                             'always deals the same tray.', required=False, minimum=0,
              maximum=100000),
    ),
    body=_body_label,
    engine=lambda spec: _ENGINE_LABEL,
)


#: The module's public export. ``__init__`` imports this and registers the tuple, so a
#: new game in any of these three shapes costs a JSON object and nothing else.
GENERAL_ARCHETYPES = (ORDER_SEQUENCE, MATCHING_PAIRS, LABEL_DIAGRAM)
