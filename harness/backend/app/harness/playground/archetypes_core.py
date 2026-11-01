"""``curve_shift`` - the reference archetype, and the shape every other one copies.

This is the worked example. It is written out in full, with the reasoning, so that
the other archetype modules are variations on a demonstrated pattern rather than
twenty-three independent guesses at one.

What the game is
----------------
The learner is shown a market in equilibrium and told about a shock ("household
incomes rise"). They drag the curve the shock affects, watch the intersection move
as they do, and commit to an answer about which way price and quantity go. It is a
direct reproduction of the *Shifting Markets* activity in the economics reference
set, and it is the mechanic behind *Production Possibilities* and *Supply &
Demand* too - which is exactly why it is an archetype and not three pages.

What makes it evidence rather than a toy
----------------------------------------
The drag itself proves nothing: a learner can waggle the curve until it lands
right. What is checkable is the *direction*, committed deliberately via Check, and
the reasoning revealed afterwards. So the game posts ``luminfest:readout`` while the
curve moves - live state, never stored - and exactly one ``luminfest:outcome`` when
the learner commits, carrying whether the direction was right, which shock it was,
and how many tries it took. Only the second is recorded, which is the rule stated
in :mod:`app.harness.playground.runtime`.
"""

from __future__ import annotations

from typing import Any, Mapping

from .archetypes import Archetype, Field

#: How many tries before the game offers the answer. Offering it is better than
#: letting a learner grind: the alternative is a stuck learner and a game that has
#: taught them only that dragging is frustrating.
_MAX_TRIES = 3


def _body(spec: Mapping[str, Any]) -> str:
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" '
        'role="img" aria-label="A supply and demand chart"></svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="shock"></span>'
        '<span class="spacer"></span>'
        '<button id="reset">Reset</button>'
        '<button class="primary" id="check">Check</button>'
        '<button id="next" class="hidden">Next shock</button>'
        '</div>'
        '</div>')


_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var shocks = spec.shocks || [];
  var curves = spec.curves || [];
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 44;          // plot box, px
  var xMax = +spec.x_max || 10, yMax = +spec.y_max || 10;

  var toX = scale([0, xMax], [X0, X1]);
  var toY = scale([0, yMax], [Y0, Y1]);
  var price = UI.chip('price', 'Price', 'c');
  var quantity = UI.chip('quantity', 'Quantity', 'c');
  var shiftChip = UI.chip('shift', 'Shift', 'a');

  var state = { index: 0, delta: 0, tries: 0, solved: false };

  // ---- static chrome -------------------------------------------------------
  var gGrid = svg('g', null, scene);
  for (var i = 0; i <= 10; i++) {
    svg('line', { x1: toX(i * xMax / 10), x2: toX(i * xMax / 10), y1: Y0, y2: Y1,
                  class: 'gridline' }, gGrid);
    svg('line', { x1: X0, x2: X1, y1: toY(i * yMax / 10), y2: toY(i * yMax / 10),
                  class: 'gridline' }, gGrid);
  }
  var gAxes = svg('g', null, scene);
  svg('line', { x1: X0, x2: X1, y1: Y0, y2: Y0, class: 'axis' }, gAxes);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, gAxes);
  svg('text', { x: X1, y: Y0 + 22, 'text-anchor': 'end', class: 'tick' },
      gAxes).textContent = spec.x_label || 'Quantity';
  svg('text', { x: X0 - 8, y: Y1 - 4, 'text-anchor': 'end', class: 'tick' },
      gAxes).textContent = spec.y_label || 'Price';
  for (var t = 0; t <= 10; t += 2) {
    svg('text', { x: toX(t * xMax / 10), y: Y0 + 14, 'text-anchor': 'middle',
                  class: 'tick' }, gAxes).textContent = fmt(t * xMax / 10, 0);
    svg('text', { x: X0 - 6, y: toY(t * yMax / 10) + 3.5, 'text-anchor': 'end',
                  class: 'tick' }, gAxes).textContent = fmt(t * yMax / 10, 0);
  }

  // ---- curves --------------------------------------------------------------
  // Each curve is Q = intercept + slope * P. A shock adds its own delta to the
  // intercept of whichever curve it names, which is what "shift the curve" means.
  var nodes = {};
  curves.forEach(function (curve) {
    var g = svg('g', { 'data-series': curve.id }, scene);
    var line = svg('line', { stroke: colour(curve.colour), 'stroke-width': 3 }, g);
    // A wide transparent stroke underneath, so a 3px curve is still easy to grab.
    var hit = svg('line', { stroke: 'transparent', 'stroke-width': 30,
                            'pointer-events': 'stroke', class: 'grab' }, g);
    var label = svg('text', { class: 'lbl', fill: colour(curve.colour) }, g);
    label.textContent = curve.label || curve.id;
    nodes[curve.id] = { curve: curve, line: line, hit: hit, label: label };
  });

  var gEq = svg('g', { 'data-series': 'equilibrium' }, scene);
  var eqDot = svg('circle', { r: 6, fill: COLOURS.c, stroke: '#fff', 'stroke-width': 2 }, gEq);
  var eqP = svg('line', { stroke: COLOURS.c, 'stroke-width': 1.2, 'stroke-dasharray': '4 4' }, gEq);
  var eqQ = svg('line', { stroke: COLOURS.c, 'stroke-width': 1.2, 'stroke-dasharray': '4 4' }, gEq);
  var eqLabel = svg('text', { class: 'lbl', fill: COLOURS.c }, gEq);
  eqLabel.textContent = 'Equilibrium';

  // ---- model ---------------------------------------------------------------
  function currentShock() { return shocks[state.index] || null; }

  function interceptOf(id) {
    var node = nodes[id];
    if (!node) return 0;
    var shock = currentShock();
    var extra = (shock && shock.shift === id) ? state.delta : 0;
    return (+node.curve.intercept || 0) + extra;
  }

  // Where two Q = a + bP lines cross. Undefined when they are parallel, which is
  // reported rather than drawn as a nonsense intersection at infinity.
  function equilibrium() {
    var ids = Object.keys(nodes);
    if (ids.length < 2) return null;
    var A = nodes[ids[0]].curve, B = nodes[ids[1]].curve;
    var a0 = interceptOf(ids[0]), a1 = interceptOf(ids[1]);
    var b0 = +A.slope || 0, b1 = +B.slope || 0;
    if (Math.abs(b1 - b0) < 1e-9) return null;
    var p = (a0 - a1) / (b1 - b0);
    return { p: p, q: a0 + b0 * p };
  }

  function draw() {
    var shock = currentShock();
    Object.keys(nodes).forEach(function (id) {
      var node = nodes[id];
      var intercept = interceptOf(id);
      var slope = +node.curve.slope || 0;
      // Clamp the drawn segment to the plot box: a curve leaving the view is
      // normal, a curve drawn outside it looks like a rendering fault.
      var pAt0 = 0, pAtMax = yMax;
      var qAt0 = intercept + slope * pAt0, qAtMax = intercept + slope * pAtMax;
      node.line.setAttribute('x1', toX(qAt0)); node.line.setAttribute('y1', toY(pAt0));
      node.line.setAttribute('x2', toX(qAtMax)); node.line.setAttribute('y2', toY(pAtMax));
      node.hit.setAttribute('x1', toX(qAt0)); node.hit.setAttribute('y1', toY(pAt0));
      node.hit.setAttribute('x2', toX(qAtMax)); node.hit.setAttribute('y2', toY(pAtMax));
      var anchorAtTop = qAtMax >= qAt0;
      node.label.setAttribute('x', anchorAtTop ? toX(qAtMax) - 4 : toX(qAtMax) + 6);
      node.label.setAttribute('y', toY(pAtMax) + 14);
      node.label.setAttribute('text-anchor', anchorAtTop ? 'end' : 'start');
      var draggable = !!(shock && shock.shift === id && !state.solved);
      node.hit.style.pointerEvents = draggable ? 'stroke' : 'none';
      node.hit.style.cursor = draggable ? 'ew-resize' : 'default';
      node.line.setAttribute('opacity', draggable ? 1 : 0.85);
    });

    var eq = equilibrium();
    if (!eq) {
      eqDot.setAttribute('opacity', 0); eqLabel.setAttribute('opacity', 0);
      eqP.setAttribute('opacity', 0); eqQ.setAttribute('opacity', 0);
      price.set('parallel'); quantity.set('parallel');
      return;
    }
    eqDot.setAttribute('opacity', 1); eqLabel.setAttribute('opacity', 1);
    eqP.setAttribute('opacity', 0.85); eqQ.setAttribute('opacity', 0.85);
    var cx = clamp(toX(eq.q), X0, X1), cy = clamp(toY(eq.p), Y1, Y0);
    eqDot.setAttribute('cx', cx); eqDot.setAttribute('cy', cy);
    eqP.setAttribute('x1', X0); eqP.setAttribute('y1', cy);
    eqP.setAttribute('x2', cx); eqP.setAttribute('y2', cy);
    eqQ.setAttribute('x1', cx); eqQ.setAttribute('y1', cy);
    eqQ.setAttribute('x2', cx); eqQ.setAttribute('y2', Y0);
    eqLabel.setAttribute('x', cx + 12); eqLabel.setAttribute('y', cy - 9);
    price.set(fmt(eq.p, 2));
    quantity.set(fmt(eq.q, 2));
    shiftChip.set((state.delta >= 0 ? '+' : '') + fmt(state.delta, 1));
    // Live state for the workbench's own display. Never stored.
    BRIDGE.readout({ price: +eq.p.toFixed(3), quantity: +eq.q.toFixed(3),
                     shift: +state.delta.toFixed(2),
                     shock: currentShock() ? currentShock().id : null });
  }

  function prompt() {
    var shock = currentShock();
    var node = shock ? nodes[shock.shift] : null;
    document.getElementById('shock').textContent = shock
      ? 'Shock: ' + shock.text + (node ? '  -  drag ' + (node.curve.label || node.curve.id) + '.' : '')
      : 'Every shock answered.';
  }

  // ---- drag ----------------------------------------------------------------
  // Only the curve the current shock names is draggable, and only until the
  // learner commits. Letting them drag everything would turn the exercise into
  // "wiggle until the marker looks right", which is the failure mode this game
  // is built to avoid.
  Object.keys(nodes).forEach(function (id) {
    drag(nodes[id].hit, {
      start: function (pt) {
        var shock = currentShock();
        if (!shock || shock.shift !== id || state.solved) return false;
        return { startX: pt.x, startDelta: state.delta };
      },
      move: function (pt, held) {
        var perPixel = xMax / (X1 - X0);
        state.delta = clamp(held.startDelta + (pt.x - held.startX) * perPixel, -xMax, xMax);
        draw();
      }
    });
  });

  // ---- check ---------------------------------------------------------------
  function check() {
    var shock = currentShock();
    if (!shock || state.solved) return;
    var wanted = shock.direction === 'left' ? -1 : 1;
    var moved = Math.abs(state.delta) > 0.25;
    var got = state.delta > 0 ? 1 : -1;
    if (!moved) {
      UI.feedback('Drag the curve the shock affects before checking. A shock that '
                  + 'moves nothing is not a shift.', false);
      return;
    }
    if (got === wanted) {
      state.solved = true;
      document.getElementById('check').disabled = true;
      var eq = equilibrium();
      UI.feedback('Correct. ' + shock.text + ' shifts '
                  + (nodes[shock.shift] ? (nodes[shock.shift].curve.label || shock.shift) : shock.shift)
                  + ' to the ' + shock.direction + ', so price goes ' + shock.price
                  + ' and quantity goes ' + shock.quantity + '. ' + (shock.why || ''),
                  true);
      document.getElementById('next').classList.remove('hidden');
      document.getElementById('reset').disabled = true;
      BRIDGE.outcome({
        correct: true, shock: shock.id, tries: state.tries + 1,
        direction: shock.direction, delta: +state.delta.toFixed(2),
        price: eq ? +eq.p.toFixed(3) : null, quantity: eq ? +eq.q.toFixed(3) : null,
        detail: { answer_price: shock.price, answer_quantity: shock.quantity,
                  shift: shock.shift, why: shock.why || '' }
      });
    } else {
      state.tries += 1;
      if (state.tries >= __MAX_TRIES__) {
        state.solved = true;
        document.getElementById('check').disabled = true;
        UI.feedback('Not quite, and this is the third try, so here is the answer: '
                    + shock.text + ' shifts the curve to the ' + shock.direction
                    + ', so price goes ' + shock.price + ' and quantity goes '
                    + shock.quantity + '. ' + (shock.why || ''), false);
        document.getElementById('next').classList.remove('hidden');
        BRIDGE.outcome({ correct: false, shock: shock.id, tries: state.tries,
                     direction: shock.direction, delta: +state.delta.toFixed(2),
                     detail: { answer_price: shock.price, answer_quantity: shock.quantity,
                               shift: shock.shift, gave_up: true } });
      } else {
        UI.feedback('That shifts it the wrong way. Ask what happens to the quantity '
                    + 'traded at the *old* price, then try again.', false);
      }
    }
  }

  // ---- controls ------------------------------------------------------------
  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    state.delta = 0; draw(); UI.feedback('');
  });
  document.getElementById('next').addEventListener('click', function () {
    state.index = Math.min(state.index + 1, shocks.length - 1);
    state.delta = 0; state.tries = 0; state.solved = false;
    document.getElementById('check').disabled = false;
    document.getElementById('reset').disabled = false;
    document.getElementById('next').classList.add('hidden');
    UI.feedback('');
    prompt(); draw();
  });

  prompt();
  draw();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


CURVE_SHIFT = Archetype(
    id='curve_shift',
    title='Shift the curve',
    blurb='Read a shock, drag the curve it affects, and watch the equilibrium move.',
    interaction='drag a curve; the intersection animates live',
    subjects=('economics', 'science', 'mathematics'),
    tags=('graphs', 'markets', 'equilibrium', 'cause-and-effect'),
    reference='Shifting Markets / Production Possibilities, reviewecon.com games & activities',
    telemetry='One outcome per shock: whether the shift direction was right, the shock id, '
              'the tries taken, and the resulting price and quantity.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('x_label', 'text', 'Horizontal axis label.', required=False),
        Field('y_label', 'text', 'Vertical axis label.', required=False),
        Field('x_max', 'float', 'Horizontal axis maximum.', minimum=1, maximum=100),
        Field('y_max', 'float', 'Vertical axis maximum.', minimum=1, maximum=100),
        Field('curves', 'table',
              'Two straight curves, each Q = intercept + slope x P. Exactly one should '
              'carry shifts=true: that is the one the learner drags.',
              minimum_items=2, maximum_items=2,
              item_fields=(
                  Field('id', 'text', 'Stable identifier, e.g. "demand".'),
                  Field('label', 'text', 'Legend text, e.g. "Demand D".'),
                  Field('colour', 'text', 'Palette name.', choices=('a', 'b', 'c', 'd', 'e')),
                  Field('intercept', 'float', 'Quantity when price is zero.'),
                  Field('slope', 'float', 'Change in quantity per unit of price; '
                                          'negative for demand, positive for supply.'),
                  Field('shifts', 'bool', 'True on the curve the shock moves.'),
              )),
        Field('shocks', 'table',
              'One row per scenario. Each names the curve it moves, the direction the '
              'learner must drag it, and what happens to price and quantity.',
              minimum_items=1, maximum_items=12,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this shock.'),
                  Field('text', 'text', 'The shock, in one sentence.'),
                  Field('shift', 'text', 'id of the curve this shock moves.'),
                  Field('direction', 'text', 'Which way the curve must move.',
                        choices=('left', 'right')),
                  Field('price', 'text', 'What happens to the equilibrium price.',
                        choices=('up', 'down', 'indeterminate')),
                  Field('quantity', 'text', 'What happens to the equilibrium quantity.',
                        choices=('up', 'down', 'indeterminate')),
                  Field('why', 'text', 'The reasoning revealed after the answer.',
                        required=False),
              )),
    ),
    body=_body,
    engine=lambda spec: _ENGINE,
)
