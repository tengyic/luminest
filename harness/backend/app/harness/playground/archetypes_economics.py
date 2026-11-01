"""Economics archetypes for the simulator playground.

Four reusable interactions, each a variation on the ``curve_shift`` pattern in
:mod:`app.harness.playground.archetypes_core`:

``ppf_frontier``     draw a concave production possibilities frontier; move the
                     point of production along it (opportunity cost made visible)
                     or drag the frontier outward after a growth shock.
``sort_columns``     drag tiles into labelled columns; a wrong drop bounces the
                     tile straight back to the tray (the heart of the mechanic).
``calc_choice``      compute an opportunity cost from two sets of intercepts, then
                     choose who should specialise - the comparative-advantage game.
``elasticity_probe`` compute an elasticity coefficient by the point or mid-point
                     method, classify it, and read its sign.

Every archetype obeys the runtime's central rule: ``BRIDGE.readout`` while the
learner explores, and exactly one ``BRIDGE.outcome`` when they commit a checkable
answer. The outcome is the only thing the harness records as evidence, so no
archetype here posts one on a mere drag.

A note on the bridge API: the shared runtime exposes ``BRIDGE.outcome(obj)`` and
``UI.score(correct, text, detail)``. ``UI.outcome`` does **not** exist, so these
archetypes call ``BRIDGE.outcome`` directly after ``UI.feedback`` when they need
to carry more than a ``detail`` object upward.
"""

from __future__ import annotations

from typing import Any, Mapping

from .archetypes import Archetype, Field

#: How many tries on one task before the answer is revealed. The alternative is a
#: learner grinding against a mechanic, which teaches only frustration.
_MAX_TRIES = 3


# ---------------------------------------------------------------------------
# ppf_frontier
# ---------------------------------------------------------------------------

_PPF_BODY = (
    '<div class="stagecol">'
    '<div id="task" style="flex:0 0 auto;padding:2px 4px 10px;'
    'font-size:13.5px;font-weight:600;line-height:1.45;color:var(--ink)"></div>'
    '<div class="scene-wrap">'
    '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
    'aria-label="A production possibilities frontier with the point of production on '
    'the curve"></svg>'
    '</div>'
    '<div class="controls">'
    '<label class="fld hidden" id="costwrap">Opportunity cost'
    '<input type="number" id="cost" step="any" aria-label="Opportunity cost of the '
    'move, in units of the vertical-axis good">'
    '<span id="costunit" style="font-size:11.5px;color:var(--ink-3)"></span></label>'
    '<span class="spacer"></span>'
    '<button id="reset">Reset</button>'
    '<button class="primary" id="check">Check</button>'
    '<button id="next" class="hidden">Next</button>'
    '</div>'
    '</div>')

_PPF_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var tasks = spec.tasks || [];
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 44;
  var xMax = +spec.x_max || 10, yMax = +spec.y_max || 10;
  var xInt = +spec.x_intercept || xMax, yInt = +spec.y_intercept || yMax;
  var bow = +spec.bow || 2;
  var MAX_TRIES = 3;
  var xLab = spec.x_label || 'Good X', yLab = spec.y_label || 'Good Y';
  var toX = scale([0, xMax], [X0, X1]);
  var toY = scale([0, yMax], [Y0, Y1]);

  // A growth task asks for a frontier larger than the declared axis (130% of a
  // 10-unit intercept is 13, against an x_max of 12), so the top of the range is
  // set just above the largest scale any task asks for and the drawing is clipped
  // to the plot. The drag mapping stays on the declared domain.
  var wantScale = 1;
  for (var q = 0; q < tasks.length; q++) {
    if ((tasks[q].kind || '') === 'grow') {
      wantScale = Math.max(wantScale, +tasks[q].target_scale || 1);
    }
  }
  var GROW_MAX = Math.min(2.4, Math.max(1.15, wantScale + 0.12));

  // Ticks land on round numbers. Stepping by max/5 put 2.4 on the axis and printed
  // it as "2", so the labels read 0, 2, 5, 7, 10 - unevenly spaced and not adding
  // up. A 1/2/3/5/10 ladder cannot do that.
  function niceStep(max) {
    var raw = max / 5, mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var n = raw / mag, step;
    if (n <= 1) step = 1; else if (n <= 2) step = 2; else if (n <= 3) step = 3;
    else if (n <= 5) step = 5; else step = 10;
    return step * mag;
  }
  function placesFor(step) { return step >= 1 ? 0 : (step >= 0.1 ? 1 : 2); }

  // True viewBox coordinates for a pointer event. The runtime's point() is relative
  // to the grabbed node's own bounding box, which is wrong for a node that moves;
  // the scene's box plus preserveAspectRatio letterboxing is what we actually need.
  function sp(event) {
    var r = scene.getBoundingClientRect();
    var s = Math.min(r.width / W, r.height / H) || 1;
    var ox = (r.width - W * s) / 2, oy = (r.height - H * s) / 2;
    return { x: (event.clientX - r.left - ox) / s, y: (event.clientY - r.top - oy) / s };
  }

  var chipX = UI.chip('xg', xLab, 'a');
  var chipY = UI.chip('yg', yLab, 'b');
  var chipCost = UI.chip('oc', 'Opportunity cost', 'c');
  var chipScale = UI.chip('sc', 'Capacity', 'd');

  var state = { index: 0, u: 0, scaleF: 1, tries: 0, solved: false };

  // ---- chrome --------------------------------------------------------------
  // Every label is given its own gutter: ticks under the x axis, the x title on a
  // second line below them, the y title rotated into the left margin. The previous
  // draft put both axis titles at the plot corner, which is exactly where the last
  // tick and the top tick already sat.
  var gGrid = svg('g', null, scene);
  var gAxes = svg('g', null, scene);
  var xStep = niceStep(xMax), yStep = niceStep(yMax);
  var xp = placesFor(xStep), yp = placesFor(yStep);
  var i, v;
  for (i = 0; i * xStep <= xMax + 1e-9; i++) {
    v = i * xStep;
    svg('line', { x1: toX(v), x2: toX(v), y1: Y0, y2: Y1, class: 'gridline' }, gGrid);
    svg('text', { x: toX(v), y: Y0 + 16, 'text-anchor': 'middle', class: 'tick' }, gAxes)
      .textContent = fmt(v, xp);
  }
  for (i = 0; i * yStep <= yMax + 1e-9; i++) {
    v = i * yStep;
    svg('line', { x1: X0, x2: X1, y1: toY(v), y2: toY(v), class: 'gridline' }, gGrid);
    svg('text', { x: X0 - 10, y: toY(v) + 3.5, 'text-anchor': 'end', class: 'tick' }, gAxes)
      .textContent = fmt(v, yp);
  }
  svg('line', { x1: X0, x2: X1, y1: Y0, y2: Y0, class: 'axis' }, gAxes);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, gAxes);
  svg('text', { x: (X0 + X1) / 2, y: Y0 + 38, 'text-anchor': 'middle',
                'font-size': 11.5, 'font-weight': 600, fill: COLOURS.dim }, gAxes)
    .textContent = xLab;
  svg('text', { x: 22, y: (Y0 + Y1) / 2, 'text-anchor': 'middle',
                'font-size': 11.5, 'font-weight': 600, fill: COLOURS.dim,
                transform: 'rotate(-90 22 ' + fmt((Y0 + Y1) / 2, 0) + ')' }, gAxes)
    .textContent = yLab;

  var clip = svg('clipPath', { id: 'ppf-plot' }, svg('defs', null, scene));
  svg('rect', { x: X0, y: Y1, width: X1 - X0, height: Y0 - Y1 }, clip);

  // ---- frontier ------------------------------------------------------------
  // A bowed-out curve through (x_int, 0) and (0, y_int): the generalised ellipse
  // (x/a)^bow + (y/b)^bow = 1. bow = 2 gives the classic quarter-ellipse PPF;
  // larger bow bows it further outward, which is what "increasing opportunity
  // cost along the frontier" looks like on the page. The wash under the curve is
  // the feasible set, so the chart reads as an area rather than a wire.
  var gFront = svg('g', { 'data-series': 'frontier', 'clip-path': 'url(#ppf-plot)' }, scene);
  var area = svg('path', { fill: colour('a-soft'), opacity: 0.5, stroke: 'none' }, gFront);
  var ghost = svg('path', { fill: 'none', stroke: COLOURS.faint, 'stroke-width': 1.8,
                            'stroke-dasharray': '5 5' }, gFront);
  var path = svg('path', { fill: 'none', stroke: colour('a'), 'stroke-width': 3,
                           'stroke-linejoin': 'round' }, gFront);
  var hitPath = svg('path', { fill: 'none', stroke: 'transparent', 'stroke-width': 28,
                              'pointer-events': 'stroke', class: 'grab' }, gFront);

  var gMark = svg('g', { 'data-series': 'production' }, scene);
  var guideV = svg('line', { stroke: COLOURS.edge, 'stroke-width': 1,
                             'stroke-dasharray': '3 4' }, gMark);
  var guideH = svg('line', { stroke: COLOURS.edge, 'stroke-width': 1,
                             'stroke-dasharray': '3 4' }, gMark);
  var dot = svg('circle', { r: 7, fill: COLOURS.c, stroke: '#fff', 'stroke-width': 2 }, gMark);
  var dotLbl = svg('text', { class: 'lbl', fill: COLOURS.c }, gMark);
  dotLbl.textContent = 'Production';
  var handle = svg('circle', { r: 8, fill: COLOURS.d, stroke: '#fff', 'stroke-width': 2,
                               class: 'grab' }, gMark);
  var handleLbl = svg('text', { class: 'lbl', fill: COLOURS.d }, gMark);
  handleLbl.textContent = 'Drag outward to grow';

  function ptAt(u, sf) {
    var uu = clamp(u, 0, 1), a = xInt * sf, b = yInt * sf;
    return { x: a * uu, y: b * Math.pow(1 - Math.pow(uu, bow), 1 / bow) };
  }
  function frontierPath(sf) {
    var d = '', N = 80;
    for (var n = 0; n <= N; n++) {
      var p = ptAt(n / N, sf);
      d += (n ? 'L' : 'M') + fmt(toX(p.x), 1) + ' ' + fmt(toY(p.y), 1) + ' ';
    }
    return d;
  }
  function areaPath(sf) {
    var d = 'M' + fmt(toX(0), 1) + ' ' + fmt(toY(0), 1) + ' ', N = 80;
    for (var n = 0; n <= N; n++) {
      var p = ptAt(n / N, sf);
      d += 'L' + fmt(toX(p.x), 1) + ' ' + fmt(toY(p.y), 1) + ' ';
    }
    return d + 'Z';
  }
  function currentTask() { return tasks[state.index] || null; }
  function kindOf(t) { return t && t.kind ? t.kind : 'move_along'; }
  function uFrom(t) { return clamp((+t.from_x || 0) / xInt, 0, 1); }
  function targetU(t) { return clamp((+t.target_x || 0) / xInt, 0, 1); }
  function costTol(t) { return t.cost_tolerance != null ? +t.cost_tolerance : 0.3; }

  function showCostInput() {
    var t = currentTask();
    var want = kindOf(t) === 'move_along' && !!(t && t.ask_cost);
    document.getElementById('costwrap').classList.toggle('hidden', !want);
    if (want) document.getElementById('costunit').textContent = 'in ' + yLab;
  }

  function draw() {
    var t = currentTask(), kind = kindOf(t);
    var sf = kind === 'grow' ? state.scaleF : 1;
    path.setAttribute('d', frontierPath(sf));
    // The hit target needs the same geometry as the visible curve. Without this the
    // path has no `d` at all, so the curve looks draggable and is not.
    hitPath.setAttribute('d', frontierPath(1));
    area.setAttribute('d', areaPath(sf));
    ghost.setAttribute('d', frontierPath(1));
    ghost.setAttribute('opacity', kind === 'grow' ? 0.9 : 0);
    hitPath.style.pointerEvents = (kind === 'move_along' && !state.solved) ? 'stroke' : 'none';

    var cost = 0, px = 0, py = 0;
    if (kind === 'move_along') {
      var p = ptAt(state.u, 1); px = p.x; py = p.y;
      cost = ptAt(t ? uFrom(t) : 0, 1).y - p.y;
      var cx = toX(p.x), cy = toY(p.y);
      dot.setAttribute('opacity', 1); dotLbl.setAttribute('opacity', 1);
      guideV.setAttribute('opacity', 1); guideH.setAttribute('opacity', 1);
      dot.setAttribute('cx', cx); dot.setAttribute('cy', cy);
      guideH.setAttribute('x1', X0); guideH.setAttribute('x2', cx);
      guideH.setAttribute('y1', cy); guideH.setAttribute('y2', cy);
      guideV.setAttribute('x1', cx); guideV.setAttribute('x2', cx);
      guideV.setAttribute('y1', Y0); guideV.setAttribute('y2', cy);
      // The point starts at the top-left corner of the plot, where a label placed
      // above it would sit in the axis gutter and collide with the top tick.
      dotLbl.setAttribute('x', clamp(cx + 12, X0 + 6, X1 - 88));
      dotLbl.setAttribute('y', cy < Y1 + 30 ? cy + 22 : cy - 10);
      dotLbl.setAttribute('text-anchor', 'start');
      handle.setAttribute('opacity', 0); handleLbl.setAttribute('opacity', 0);
      // Parked, not removed: the label keeps a position inside the frame so it never
      // sits off-canvas while it is invisible.
      handleLbl.setAttribute('x', X1 - 14);
      handleLbl.setAttribute('y', Y1 + 26);
      handleLbl.setAttribute('text-anchor', 'end');
    } else {
      dot.setAttribute('opacity', 0); dotLbl.setAttribute('opacity', 0);
      guideV.setAttribute('opacity', 0); guideH.setAttribute('opacity', 0);
      dotLbl.setAttribute('x', X0 + 12);
      dotLbl.setAttribute('y', Y0 - 18);
      dotLbl.setAttribute('text-anchor', 'start');
      handle.setAttribute('opacity', 1); handleLbl.setAttribute('opacity', 1);
      var axis = (t && t.grow_axis) || 'both';
      var hp = axis === 'x' ? { x: xInt * state.scaleF, y: 0 }
             : axis === 'y' ? { x: 0, y: yInt * state.scaleF }
             : { x: xInt * state.scaleF, y: yInt * state.scaleF };
      // Beyond about 120% the intercepts leave the declared axis; park the handle on
      // the plot edge rather than letting it ride off the canvas.
      var hx = clamp(toX(hp.x), X0 + 12, X1 - 12);
      var hy = clamp(toY(hp.y), Y1 + 12, Y0 - 12);
      handle.setAttribute('cx', hx); handle.setAttribute('cy', hy);
      var flip = hx > X1 - 170;
      handleLbl.setAttribute('x', flip ? hx - 14 : hx + 14);
      handleLbl.setAttribute('y', clamp(hy + 22, Y1 + 16, Y0 - 8));
      handleLbl.setAttribute('text-anchor', flip ? 'end' : 'start');
      px = xInt * state.scaleF; py = yInt * state.scaleF;
    }
    chipX.set(fmt(px, 2)); chipY.set(fmt(py, 2));
    chipCost.set(kind === 'move_along' ? fmt(Math.max(0, cost), 2) + ' ' + yLab : '--');
    chipScale.set(fmt(state.scaleF * 100, 0) + '%');
    BRIDGE.readout({ task: t ? t.id : null, kind: kind, x: +px.toFixed(3), y: +py.toFixed(3),
                     opportunity_cost: +Math.max(0, cost).toFixed(3),
                     scale: +state.scaleF.toFixed(3) });
  }

  function prompt() {
    var t = currentTask();
    document.getElementById('task').textContent = t ? t.text : 'Every scenario answered.';
    showCostInput();
    UI.progress(state.solved ? state.index + 1 : state.index, tasks.length);
  }

  // ---- drag ----------------------------------------------------------------
  drag(hitPath, {
    start: function () {
      if (kindOf(currentTask()) !== 'move_along' || state.solved) return false;
      return {};
    },
    move: function (pt, held, event) {
      state.u = clamp(toX.invert(sp(event).x) / xInt, 0, 1);
      draw();
    }
  });
  drag(handle, {
    start: function () {
      if (kindOf(currentTask()) !== 'grow' || state.solved) return false;
      return {};
    },
    move: function (pt, held, event) {
      var t = currentTask(), axis = (t && t.grow_axis) || 'both';
      var q = sp(event), xd = toX.invert(q.x), yd = toY.invert(q.y), s;
      if (axis === 'x') s = xd / xInt;
      else if (axis === 'y') s = yd / yInt;
      else s = Math.sqrt(xd * xd + yd * yd) / Math.sqrt(xInt * xInt + yInt * yInt);
      state.scaleF = clamp(s, 1, GROW_MAX);
      draw();
    }
  });

  // ---- check ---------------------------------------------------------------
  function resetTask(to) {
    var t = currentTask();
    state.u = kindOf(t) === 'move_along' ? uFrom(t) : 0;
    state.scaleF = 1; state.tries = 0; state.solved = false;
    document.getElementById('cost').value = '';
    document.getElementById('check').disabled = false;
    document.getElementById('reset').disabled = false;
    document.getElementById('next').classList.add('hidden');
    if (to !== false) { prompt(); draw(); }
  }

  function finish(t, kind, detail, gaveUp) {
    state.solved = true;
    document.getElementById('check').disabled = true;
    document.getElementById('reset').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    detail.gave_up = !!gaveUp;
    UI.progress(state.index + 1, tasks.length);
    BRIDGE.outcome({ correct: !gaveUp, task: t.id, kind: kind, tries: state.tries, detail: detail });
  }

  function check() {
    var t = currentTask();
    if (!t || state.solved) return;
    var kind = kindOf(t);
    if (kind === 'move_along') {
      var tol = t.tolerance != null ? +t.tolerance : 0.4;
      var p = ptAt(state.u, 1), tp = ptAt(targetU(t), 1);
      if (Math.abs(p.x - tp.x) > tol) {
        state.tries += 1;
        if (state.tries >= MAX_TRIES) {
          state.u = targetU(t); draw();
          UI.feedback('Three tries, so here is the answer: move the point to '
                      + fmt(tp.x, 2) + ' units of ' + xLab
                      + ', which leaves ' + fmt(tp.y, 2) + ' of '
                      + yLab + '. ' + (t.why || ''), false);
          finish(t, kind, { placed_x: +tp.x.toFixed(3), placed_y: +tp.y.toFixed(3),
                            opportunity_cost: +(ptAt(uFrom(t), 1).y - tp.y).toFixed(3),
                            target_x: +t.target_x }, true);
        } else {
          UI.feedback('Not at the required output yet. Drag the point along the frontier '
                      + 'to ' + fmt(+t.target_x, 2) + ' units of ' + xLab
                      + '. Remember the frontier is a constraint: more of one good means '
                      + 'less of the other.', false);
        }
        return;
      }
      var oc = ptAt(uFrom(t), 1).y - tp.y;
      if (t.ask_cost) {
        var raw = document.getElementById('cost').value, val = parseFloat(raw);
        if (raw === '' || isNaN(val) || Math.abs(val - oc) > costTol(t)) {
          state.tries += 1;
          if (state.tries >= MAX_TRIES) {
            state.u = targetU(t); draw();
            UI.feedback('The point is placed right; the opportunity cost is '
                        + fmt(oc, 2) + ' units of ' + yLab
                        + ' (that is ' + fmt(ptAt(uFrom(t), 1).y, 2) + ' - '
                        + fmt(tp.y, 2) + '). ' + (t.why || ''), false);
            finish(t, kind, { placed_x: +tp.x.toFixed(3), placed_y: +tp.y.toFixed(3),
                              opportunity_cost: +oc.toFixed(3), answer_cost: +oc.toFixed(3),
                              entered_cost: raw }, true);
          } else {
            UI.feedback('The point is in the right place, but the opportunity cost is not. '
                        + 'It is the units of ' + yLab
                        + ' given up, i.e. the height you lose on the vertical axis.', false);
          }
          return;
        }
      }
      UI.feedback('Correct. Moving to ' + fmt(tp.x, 2) + ' units of '
                  + xLab + ' costs ' + fmt(oc, 2) + ' units of '
                  + yLab + ' - that is the opportunity cost of the '
                  + 'move, read straight off the frontier. ' + (t.why || ''), true);
      finish(t, kind, { placed_x: +tp.x.toFixed(3), placed_y: +tp.y.toFixed(3),
                        opportunity_cost: +oc.toFixed(3), target_x: +t.target_x }, false);
    } else {
      var tolS = t.tolerance != null ? +t.tolerance : 0.06;
      var want = +t.target_scale || 1;
      if (Math.abs(state.scaleF - want) > tolS) {
        state.tries += 1;
        if (state.tries >= MAX_TRIES) {
          state.scaleF = clamp(want, 1, GROW_MAX); draw();
          UI.feedback('Three tries, so here is the answer: drag the frontier out to '
                      + fmt(want * 100, 0) + '% of its original capacity. '
                      + (t.why || ''), false);
          finish(t, kind, { scale: +state.scaleF.toFixed(3), target_scale: want }, true);
        } else {
          UI.feedback('Not the right amount of growth yet. Drag the handle further outward '
                      + 'until capacity reads about ' + fmt(want * 100, 0) + '%.', false);
        }
        return;
      }
      UI.feedback('Correct. The frontier has shifted outward: the economy can now produce '
                  + 'more of both goods, so the whole curve moves out rather than a single '
                  + 'point moving along it. ' + (t.why || ''), true);
      finish(t, kind, { scale: +state.scaleF.toFixed(3), target_scale: want }, false);
    }
  }

  // ---- controls ------------------------------------------------------------
  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    resetTask(true); UI.feedback('');
  });
  document.getElementById('next').addEventListener('click', function () {
    state.index = Math.min(state.index + 1, tasks.length - 1);
    resetTask(true); UI.feedback('');
  });

  resetTask(true);
}
"""

PPF_FRONTIER = Archetype(
    id='ppf_frontier',
    title='Production possibilities frontier',
    blurb='Move the point of production along a bowed-out frontier, or drag the frontier '
          'outward after a growth shock, and read the opportunity cost as you go.',
    interaction='drag the point along the frontier, or drag the frontier outward',
    subjects=('economics',),
    tags=('graphs', 'opportunity-cost', 'scarcity', 'growth', 'trade-offs'),
    reference='Production Possibilities, reviewecon.com games & activities',
    telemetry='One outcome per scenario: whether the point was moved (or the frontier grown) '
              'the right way, the placed outputs, the opportunity cost of the move, and the '
              'tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('x_label', 'text', 'Horizontal axis label (the first good).', required=False),
        Field('y_label', 'text', 'Vertical axis label (the second good).', required=False),
        Field('x_max', 'float', 'Horizontal axis maximum.', minimum=1, maximum=100),
        Field('y_max', 'float', 'Vertical axis maximum.', minimum=1, maximum=100),
        Field('x_intercept', 'float', 'Most of the horizontal good the economy can make.',
              minimum=1, maximum=100),
        Field('y_intercept', 'float', 'Most of the vertical good the economy can make.',
              minimum=1, maximum=100),
        Field('bow', 'float', 'How far the frontier bows outward. 2 is a quarter-ellipse; '
              'larger values bow further out, so opportunity cost rises faster.',
              required=False, minimum=1.2, maximum=6),
        Field('tasks', 'table',
              'One row per scenario. A move_along task drags the point to target_x; a grow '
              'task drags the frontier outward to target_scale.',
              minimum_items=1, maximum_items=10,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this scenario.'),
                  Field('text', 'text', 'The scenario, in one sentence.'),
                  Field('kind', 'text', 'move_along, or grow after a growth shock.',
                        choices=('move_along', 'grow')),
                  Field('from_x', 'float', 'Starting output of the horizontal good; the '
                        'baseline the opportunity cost is measured from.', required=False),
                  Field('target_x', 'float', 'For move_along: the output of the horizontal '
                        'good the learner must reach.', required=False),
                  Field('grow_axis', 'text', 'For grow: which intercept moves outward.',
                        required=False, choices=('x', 'y', 'both')),
                  Field('target_scale', 'float', 'For grow: the capacity multiplier the '
                        'learner must reach (1.3 = 130%).', required=False, minimum=1,
                        maximum=2.4),
                  Field('ask_cost', 'bool', 'For move_along: also require the learner to '
                        'type the opportunity cost of the move.', required=False),
                  Field('cost_tolerance', 'float', 'Accepted error in the typed opportunity '
                        'cost.', required=False, minimum=0, maximum=5),
                  Field('tolerance', 'float', 'Accepted error in the placement (units of the '
                        'horizontal good) or in the growth multiplier.', required=False,
                        minimum=0, maximum=5),
                  Field('why', 'text', 'The reasoning revealed after the answer.',
                        required=False),
              )),
    ),
    body=lambda spec: _PPF_BODY,
    engine=lambda spec: _PPF_ENGINE,
)

# ---------------------------------------------------------------------------
# sort_columns
# ---------------------------------------------------------------------------

_SORT_BODY = (
    '<div class="stagecol">'
    '<div class="scene-wrap">'
    '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
    'aria-label="Two labelled columns above a tray of tiles to sort"></svg>'
    '</div>'
    '<div class="controls">'
    '<span class="spacer"></span>'
    '<button id="reset">Reset</button>'
    '</div>'
    '</div>')

_SORT_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var columns = spec.columns || [];
  var rawTiles = spec.tiles || [];
  var MAX_TRIES = 3;
  // Two bands: a drop-zone band with a real header, and a tray below it. The tray
  // label used to sit eight pixels above the first tile row and was struck through
  // by the bottom edge of the bins, so it read as hidden behind the grid.
  var BX0 = 30, BX1 = 830, BY0 = 24, BY1 = 268;
  var TX0 = 30, TX1 = 830, TY0 = 298;
  var binGap = 16, trayGap = 10, tileH = 30, rowGap = 6;
  var trayCols = rawTiles.length >= 9 ? 4 : rawTiles.length >= 5 ? 3
               : rawTiles.length >= 2 ? 2 : 1;
  var binW = (BX1 - BX0 - (columns.length - 1) * binGap) / columns.length;
  var tileW = (TX1 - TX0 - (trayCols - 1) * trayGap) / trayCols;

  // How many tiles each column has to hold decides how tall a placed tile can be,
  // so a 14-tile sort does not overflow the well it is dropped into.
  var perBin = {}, maxPerBin = 1, b, t;
  for (b = 0; b < columns.length; b++) perBin[columns[b].id] = 0;
  for (t = 0; t < rawTiles.length; t++) {
    if (perBin[rawTiles[t].column] !== undefined) perBin[rawTiles[t].column] += 1;
  }
  for (b = 0; b < columns.length; b++) maxPerBin = Math.max(maxPerBin, perBin[columns[b].id]);
  var BIN_TILE_TOP = BY0 + 54, binTileGap = 3;
  var BIN_ROOM = BY1 - 8 - BIN_TILE_TOP;
  var binTileH = Math.min(22, (BIN_ROOM - (maxPerBin - 1) * binTileGap) / maxPerBin);

  var chipPlaced = UI.chip('pl', 'Placed', 'a');
  var chipCorrect = UI.chip('cd', 'Correct drops', 'b');
  var chipAttempts = UI.chip('at', 'Attempts', 'c');

  var state = { attempts: 0, correctDrops: 0, wrongDrops: 0, done: false };
  var tiles = [], views = [], counts = {}, selected = null;
  var binRects = [], countNodes = [], emptyNodes = [];

  function sp(event) {
    var r = scene.getBoundingClientRect();
    var s = Math.min(r.width / W, r.height / H) || 1;
    var ox = (r.width - W * s) / 2, oy = (r.height - H * s) / 2;
    return { x: (event.clientX - r.left - ox) / s, y: (event.clientY - r.top - oy) / s };
  }
  function colLabel(id) {
    for (var i = 0; i < columns.length; i++) if (columns[i].id === id) return columns[i].label;
    return id;
  }
  function binX(i) { return BX0 + i * (binW + binGap); }
  function binIndexAt(x, y) {
    if (y < BY0 || y > BY1) return -1;
    for (var i = 0; i < columns.length; i++) {
      if (x >= binX(i) && x <= binX(i) + binW) return i;
    }
    return -1;
  }

  // Positioned with x/y on the shapes rather than a transform on the group. A
  // translated group still reports its children's *local* box to getBBox(), which is
  // what the layout audit measures, so a transformed tray reads as content stacked
  // at the origin. Absolute geometry keeps what the audit sees equal to what the
  // learner sees.
  function apply(v) {
    v.rect.setAttribute('x', fmt(v.x, 1));
    v.rect.setAttribute('y', fmt(v.y, 1));
    v.rect.setAttribute('width', fmt(v.w, 1));
    v.rect.setAttribute('height', fmt(v.h, 1));
    v.text.setAttribute('x', fmt(v.x + v.w / 2, 1));
    v.text.setAttribute('y', fmt(v.y + v.h / 2 + 4, 1));
  }
  function move(v, ms) {
    var t = ms ? 'x ' + ms + 'ms ease-out, y ' + ms + 'ms ease-out' : 'none';
    v.rect.style.transition = t;
    v.text.style.transition = t;
  }

  // Selection is a *brand* outline, not a verdict: a tile the learner has picked up
  // is not a wrong tile, and the semantic tones are reserved for right and wrong.
  function mark(v, kind) {
    v.rect.style.stroke = '';
    v.rect.style.strokeWidth = '';
    v.rect.setAttribute('data-state', kind || '');
  }

  function refreshBins() {
    var placed = 0;
    for (var i = 0; i < tiles.length; i++) if (tiles[i].placed) placed += 1;
    for (var k = 0; k < columns.length; k++) {
      var n = counts[columns[k].id] || 0;
      countNodes[k].textContent = n === 1 ? '1 placed' : n + ' placed';
      emptyNodes[k].setAttribute('opacity', n ? 0 : 1);
    }
    return placed;
  }

  // Remaining tiles close the gap a placed one leaves behind, so the tray never
  // shows a hole where a tile used to be. Each row is centred, which also keeps a
  // half-full last row looking deliberate.
  function layoutTray(animate) {
    var live = [], i;
    for (i = 0; i < views.length; i++) if (!views[i].tile.placed) live.push(views[i]);
    var rows = Math.ceil(live.length / trayCols);
    for (var r = 0; r < rows; r++) {
      var inRow = Math.min(trayCols, live.length - r * trayCols);
      var rowW = inRow * tileW + (inRow - 1) * trayGap;
      var startX = TX0 + (TX1 - TX0 - rowW) / 2;
      for (var c = 0; c < inRow; c++) {
        var v = live[r * trayCols + c];
        v.homeX = startX + c * (tileW + trayGap);
        v.homeY = TY0 + r * (tileH + rowGap);
        if (!animate) { v.x = v.homeX; v.y = v.homeY; apply(v); }
        else if (Math.abs(v.x - v.homeX) > 0.5 || Math.abs(v.y - v.homeY) > 0.5) {
          v.x = v.homeX; v.y = v.homeY; move(v, 220); apply(v);
        }
      }
    }
  }

  function place(v, binId, revealed) {
    v.tile.placed = true; v.tile.revealed = !!revealed;
    var i = 0; for (var k = 0; k < columns.length; k++) if (columns[k].id === binId) i = k;
    v.w = binW - 36; v.h = binTileH;
    v.x = binX(i) + 18;
    v.y = BIN_TILE_TOP + counts[binId] * (binTileH + binTileGap);
    counts[binId] += 1;
    v.text.setAttribute('font-size', binTileH >= 21 ? 11 : 10);
    move(v, 200);
    v.rect.setAttribute('rx', 6);
    mark(v, 'correct');
    if (revealed) v.g.setAttribute('opacity', 0.72);
    apply(v);
    layoutTray(true);
    refreshBins();
  }

  function bounce(v) {
    v.x = v.homeX; v.y = v.homeY;
    move(v, 220);
    apply(v);
  }

  function flash(v, kind) {
    mark(v, kind);
    setTimeout(function () { if (!v.tile.placed) mark(v, ''); }, 600);
  }

  function updateChips() {
    var placed = refreshBins();
    chipPlaced.set(placed + ' / ' + tiles.length);
    chipCorrect.set(String(state.correctDrops));
    chipAttempts.set(String(state.attempts));
    // Live tally for the workbench's own display. Never stored.
    BRIDGE.readout({ placed: placed, tiles: tiles.length, attempts: state.attempts,
                     correct_drops: state.correctDrops, wrong_drops: state.wrongDrops });
  }

  function finish() {
    state.done = true;
    var revealed = 0;
    for (var i = 0; i < tiles.length; i++) if (tiles[i].revealed) revealed += 1;
    var ok = revealed === 0;
    UI.feedback(ok
      ? 'All sorted, no wrong drops left unrecovered. Every non-price determinant either '
        + 'shifts demand (what buyers want at each price) or supply (what sellers offer at '
        + 'each price).'
      : 'Sorted - but ' + revealed + ' tile(s) had to be revealed after three tries. The '
        + 'distinction to rehearse: demand shifters change what buyers want at every price; '
        + 'supply shifters change what sellers can offer at every price.', ok);
    BRIDGE.outcome({
      correct: ok, tiles: tiles.length, attempts: state.attempts,
      correct_drops: state.correctDrops, wrong_drops: state.wrongDrops,
      // Top level, not only inside `detail`. `playground_routes.py` stores the attempt
      // count by reading `payload.tries` into `PlaygroundRun.tries`; `detail` is a
      // free-form blob nothing reads for scoring. A count that lived only in `detail`
      // would leave the column at its default of 1, which is precisely what makes a
      // three-try give-up indistinguishable from a one-try one in the record.
      tries: state.attempts,
      detail: { gave_up: !ok, revealed: revealed, tries: state.attempts }
    });
  }

  function checkDone() {
    for (var i = 0; i < tiles.length; i++) if (!tiles[i].placed) return;
    finish();
  }

  function reveal(v) {
    place(v, v.tile.column, true);
    UI.feedback('After three tries, "' + v.tile.text + '" is shown in '
                + colLabel(v.tile.column) + '. ' + (spec.reveal_note || ''), false);
    updateChips();
  }

  function attemptPlace(v, binId) {
    if (v.tile.placed || state.done) return;
    state.attempts += 1;
    if (binId === v.tile.column) {
      state.correctDrops += 1;
      if (selected === v) selected = null;
      place(v, binId, false);
      UI.feedback('Correct: "' + v.tile.text + '" belongs in ' + colLabel(binId) + '.', true);
    } else {
      state.wrongDrops += 1;
      v.tile.wrong += 1;
      flash(v, 'wrong');
      bounce(v);
      if (v.tile.wrong >= MAX_TRIES) reveal(v);
      else UI.feedback('Not that column - the tile bounces straight back to the tray. '
                       + 'Re-read the column headings: a determinant belongs with the curve '
                       + 'whose behaviour at each price it changes.', false);
    }
    updateChips();
    checkDone();
  }

  function selectTile(v) {
    if (v.tile.placed || state.done) return;
    if (selected) mark(selected, '');
    selected = v;
    v.rect.style.stroke = colour('a');
    v.rect.style.strokeWidth = 2.2;
    UI.feedback('Tile "' + v.tile.text + '" selected. Now click a column (or focus one and '
                + 'press Enter) to place it.', undefined);
  }

  function setOver(index) {
    for (var i = 0; i < binRects.length; i++) {
      binRects[i].setAttribute('data-over', i === index ? '1' : '0');
    }
  }

  function buildAll() {
    clear(scene);
    tiles = []; views = []; counts = {}; selected = null;
    binRects = []; countNodes = []; emptyNodes = [];
    state = { attempts: 0, correctDrops: 0, wrongDrops: 0, done: false };
    var i, k;
    for (k = 0; k < columns.length; k++) counts[columns[k].id] = 0;

    var gBins = svg('g', { 'data-series': 'columns' }, scene);
    for (i = 0; i < columns.length; i++) {
      var col = columns[i], bx = binX(i);
      var rect = svg('rect', { x: bx, y: BY0, width: binW, height: BY1 - BY0,
                               rx: 12, ry: 12, class: 'bin', tabindex: 0, role: 'button',
                               'aria-label': 'Place the selected tile in ' + col.label }, gBins);
      rect.style.cursor = 'pointer';
      binRects.push(rect);
      svg('text', { x: bx + 18, y: BY0 + 24, class: 'lbl' }, gBins).textContent = col.label;
      countNodes.push(svg('text', { x: bx + binW - 18, y: BY0 + 24, 'text-anchor': 'end',
                                    'font-size': 11, fill: COLOURS.dim }, gBins));
      if (col.hint) {
        svg('text', { x: bx + 18, y: BY0 + 42, 'font-size': 11, fill: COLOURS.dim }, gBins)
          .textContent = col.hint;
      }
      svg('line', { x1: bx + 16, x2: bx + binW - 16, y1: BY0 + 52, y2: BY0 + 52,
                    stroke: COLOURS.line, 'stroke-width': 1 }, gBins);
      // A resting invitation, so an empty well is a place to put something rather
      // than a large blank rectangle with a caption in the corner.
      emptyNodes.push(svg('text', { x: bx + binW / 2, y: (BIN_TILE_TOP + BY1) / 2 + 2,
                                    'text-anchor': 'middle', 'font-size': 11.5,
                                    fill: COLOURS.faint }, gBins));
      emptyNodes[i].textContent = 'Drop a tile here';
      (function (colId, rectNode) {
        function put() { if (selected) attemptPlace(selected, colId); }
        rectNode.addEventListener('click', put);
        rectNode.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); put(); }
        });
      })(col.id, rect);
    }

    svg('text', { x: TX0, y: TY0 - 12, class: 'note' }, scene).textContent =
      spec.tray_label || 'Tiles to sort';
    svg('text', { x: TX1, y: TY0 - 12, 'text-anchor': 'end', 'font-size': 11,
                  fill: COLOURS.faint }, scene).textContent =
      rawTiles.length + ' to place';

    var order = shuffle(rawTiles, (spec.seed === undefined ? 7 : spec.seed));
    for (i = 0; i < order.length; i++) {
      var tile = order[i];
      tile.placed = false; tile.revealed = false; tile.wrong = 0;
      var homeX = TX0, homeY = TY0;
      var g = svg('g', { 'data-series': 'tile-' + tile.id, tabindex: 0, role: 'button',
                         'aria-label': 'Tile: ' + tile.text }, scene);
      var rect2 = svg('rect', { rx: 8, ry: 8, class: 'tile' }, g);
      var text = svg('text', { 'text-anchor': 'middle', 'font-size': 11.5 }, g);
      text.textContent = tile.text;
      var v = { tile: tile, g: g, rect: rect2, text: text, w: tileW, h: tileH,
                x: homeX, y: homeY, homeX: homeX, homeY: homeY };
      apply(v);
      tiles.push(tile); views.push(v);
      (function (vv) {
        var moved = false;
        drag(vv.g, {
          start: function (pt, event) {
            if (vv.tile.placed || state.done) return false;
            moved = false;
            move(vv, 0);
            var q = sp(event);
            return { dx: vv.x - q.x, dy: vv.y - q.y };
          },
          move: function (pt, held, event) {
            var q = sp(event);
            vv.x = q.x + held.dx; vv.y = q.y + held.dy; moved = true; apply(vv);
            setOver(binIndexAt(q.x, q.y));
          },
          end: function (pt, held, event) {
            var q = sp(event), bi = binIndexAt(q.x, q.y);
            setOver(-1);
            if (bi >= 0) attemptPlace(vv, columns[bi].id);
            else { bounce(vv); }
          }
        });
        vv.g.addEventListener('click', function () { if (!moved) selectTile(vv); moved = false; });
        vv.g.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectTile(vv); }
        });
      })(v);
    }
    layoutTray(false);
    updateChips();
    UI.feedback('');
  }

  document.getElementById('reset').addEventListener('click', function () {
    state.done = false;
    buildAll();
  });
  buildAll();
}
"""

SORT_COLUMNS = Archetype(
    id='sort_columns',
    title='Sort into columns',
    blurb='Drag each tile into the column it belongs to. A wrong drop bounces straight back '
          'to the tray, so you have to commit to a reason before it counts.',
    interaction='drag tiles into labelled columns; wrong drops bounce back',
    subjects=('economics', 'science', 'mathematics', 'computer_science'),
    tags=('classification', 'drag-and-drop', 'vocabulary', 'cause-and-effect'),
    reference='Determinants of Supply and Demand, reviewecon.com games & activities',
    # There is no Check button: the commit is the completed board. A wrong drop bounces
    # back to the tray, so a tile can only be *placed* when it is placed correctly and
    # the board can only be completed by getting every tile right. `checkDone()` fires
    # `finish()` - the single BRIDGE.outcome - only once every tile is placed, and
    # `finish()` sets `state.done`, which makes every later `attemptPlace` and drag a
    # no-op. Declared rather than inferred, because a verifier cannot guess this from
    # the markup and guessing wrong would either wave through a stray-drag commit or
    # condemn a game behaving exactly as designed.
    commits_on='completion',
    telemetry='One outcome per completed sort: whether every tile was placed without a '
              'reveal, the tile count, the number of correct and wrong drops, and the '
              'running attempt tally.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('tray_label', 'text', 'Caption above the tile tray.', required=False),
        Field('seed', 'int', 'Seed for the deterministic shuffle of the tray.',
              required=False, minimum=0, maximum=100000),
        Field('reveal_note', 'text', 'Extra sentence shown when a tile is revealed after '
              'three wrong drops.', required=False),
        Field('columns', 'table',
              'Two or three labelled columns. The hint under each heading is always visible '
              'and doubles as the teaching text on a wrong drop.',
              minimum_items=2, maximum_items=3,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this column.'),
                  Field('label', 'text', 'Column heading.'),
                  Field('hint', 'text', 'One-line description of what belongs here.',
                        required=False),
              )),
        Field('tiles', 'table',
              'The tiles to sort. Each names the column it belongs in.',
              minimum_items=3, maximum_items=18,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this tile.'),
                  Field('text', 'text', 'Tile text.'),
                  Field('column', 'text', 'id of the column this tile belongs in.'),
              )),
    ),
    body=lambda spec: _SORT_BODY,
    engine=lambda spec: _SORT_ENGINE,
)

# ---------------------------------------------------------------------------
# calc_choice
# ---------------------------------------------------------------------------

_CALC_BODY = (
    '<div class="stagecol">'
    '<div id="task" style="flex:0 0 auto;padding:2px 4px 10px;'
    'font-size:13.5px;font-weight:600;line-height:1.45;color:var(--ink)"></div>'
    '<div class="scene-wrap">'
    '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
    'aria-label="Two linear production possibility frontiers, one for each producer"></svg>'
    '</div>'
    '<div class="controls">'
    '<label class="fld" id="numwrap">Opportunity cost'
    '<input type="number" id="num" step="any" aria-label="Your numeric answer">'
    '<span id="unit" style="font-size:11.5px;color:var(--ink-3)"></span></label>'
    '<label class="fld hidden" id="choicewrap">Who specialises?'
    '<select id="choice" aria-label="Choose the party with the comparative advantage"></select>'
    '</label>'
    '<span class="spacer"></span>'
    '<button class="primary" id="check">Check</button>'
    '<button id="next" class="hidden">Next</button>'
    '</div>'
    '</div>')

_CALC_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var parties = spec.parties || [];
  var questions = spec.questions || [];
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 44;
  var xMax = +spec.x_max || 10, yMax = +spec.y_max || 10;
  var MAX_TRIES = 3;
  var xGood = spec.x_good || 'Good X', yGood = spec.y_good || 'Good Y';
  var toX = scale([0, xMax], [X0, X1]);
  var toY = scale([0, yMax], [Y0, Y1]);

  // Round ticks. max/5 turned 40 into steps of 8 and 12 into steps of 2.4, which
  // printed as 0, 2, 5, 7, 10 - numbers that are not evenly spaced.
  function niceStep(max) {
    var raw = max / 5, mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var n = raw / mag, step;
    if (n <= 1) step = 1; else if (n <= 2) step = 2; else if (n <= 3) step = 3;
    else if (n <= 5) step = 5; else step = 10;
    return step * mag;
  }
  function placesFor(step) { return step >= 1 ? 0 : (step >= 0.1 ? 1 : 2); }

  var chipGoods = UI.chip('goods', 'Goods', 'a');
  chipGoods.set(xGood + ' / ' + yGood);
  parties.forEach(function (p, i) {
    var chip = UI.chip('p' + i, p.name, i === 0 ? 'a' : 'b');
    chip.set(fmt(+p.x_intercept, 0) + ' ' + xGood + ' | ' + fmt(+p.y_intercept, 0) + ' ' + yGood);
  });

  var state = { index: 0, stage: 'num', tries: 0, solved: false, numCorrect: false, numericGaveUp: false };

  // ---- chart ---------------------------------------------------------------
  var gGrid = svg('g', null, scene);
  var gAxes = svg('g', null, scene);
  var xStep = niceStep(xMax), yStep = niceStep(yMax);
  var xp = placesFor(xStep), yp = placesFor(yStep);
  var i, v;
  for (i = 0; i * xStep <= xMax + 1e-9; i++) {
    v = i * xStep;
    svg('line', { x1: toX(v), x2: toX(v), y1: Y0, y2: Y1, class: 'gridline' }, gGrid);
    svg('text', { x: toX(v), y: Y0 + 16, 'text-anchor': 'middle', class: 'tick' }, gAxes)
      .textContent = fmt(v, xp);
  }
  for (i = 0; i * yStep <= yMax + 1e-9; i++) {
    v = i * yStep;
    svg('line', { x1: X0, x2: X1, y1: toY(v), y2: toY(v), class: 'gridline' }, gGrid);
    svg('text', { x: X0 - 10, y: toY(v) + 3.5, 'text-anchor': 'end', class: 'tick' }, gAxes)
      .textContent = fmt(v, yp);
  }
  svg('line', { x1: X0, x2: X1, y1: Y0, y2: Y0, class: 'axis' }, gAxes);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, gAxes);
  svg('text', { x: (X0 + X1) / 2, y: Y0 + 38, 'text-anchor': 'middle',
                'font-size': 11.5, 'font-weight': 600, fill: COLOURS.dim }, gAxes)
    .textContent = xGood;
  svg('text', { x: 22, y: (Y0 + Y1) / 2, 'text-anchor': 'middle',
                'font-size': 11.5, 'font-weight': 600, fill: COLOURS.dim,
                transform: 'rotate(-90 22 ' + fmt((Y0 + Y1) / 2, 0) + ')' }, gAxes)
    .textContent = yGood;

  var gLines = svg('g', { 'data-series': 'ppfs' }, scene);
  parties.forEach(function (p, idx) {
    var c = colour(p.colour || (idx === 0 ? 'a' : 'b'));
    var ax = +p.x_intercept || 0, ay = +p.y_intercept || 0;
    svg('line', { x1: toX(ax), y1: toY(0), x2: toX(0), y2: toY(ay), stroke: c,
                  'stroke-width': 3, 'stroke-linecap': 'round' }, gLines);
    // The intercepts are the numbers the task is about, so they get a mark.
    svg('circle', { cx: toX(ax), cy: toY(0), r: 4, fill: c, stroke: '#fff',
                    'stroke-width': 1.5 }, gLines);
    svg('circle', { cx: toX(0), cy: toY(ay), r: 4, fill: c, stroke: '#fff',
                    'stroke-width': 1.5 }, gLines);
  });

  // A legend rather than labels stuck to the line ends: at the y axis both lines
  // start within a few units of each other and of the top tick, which is where the
  // names used to collide with the axis label.
  var legend = svg('g', { 'data-series': 'legend' }, scene);
  parties.forEach(function (p, idx) {
    var c = colour(p.colour || (idx === 0 ? 'a' : 'b'));
    var ly = Y1 + 24 + idx * 20;
    svg('line', { x1: X1 - 104, x2: X1 - 84, y1: ly - 4, y2: ly - 4, stroke: c,
                  'stroke-width': 3, 'stroke-linecap': 'round' }, legend);
    svg('text', { x: X1 - 78, y: ly, 'font-size': 11.5, 'font-weight': 650, fill: c }, legend)
      .textContent = p.name;
  });

  // ---- model ---------------------------------------------------------------
  function currentQ() { return questions[state.index] || null; }
  function partyOf(q) {
    for (var i = 0; i < parties.length; i++) if (parties[i].id === q.party) return parties[i];
    return null;
  }
  function axOf(q) { var p = partyOf(q); return p ? +p.x_intercept : 0; }
  function ayOf(q) { var p = partyOf(q); return p ? +p.y_intercept : 0; }
  // Opportunity cost of one unit of the asked-about good, in units of the other.
  // Computed from the intercepts rather than trusted from the spec, so the game's
  // "correct" answer cannot be an authoring slip.
  function ocFor(q) {
    var ax = axOf(q), ay = ayOf(q);
    if (!ax || !ay) return NaN;
    return q.per_good === 'y' ? ax / ay : ay / ax;
  }
  function askedGood(q) { return q.per_good === 'y' ? yGood : xGood; }
  function otherGood(q) { return q.per_good === 'y' ? xGood : yGood; }

  function buildChoices(q) {
    var sel = document.getElementById('choice');
    clear(sel);
    el('option', { value: '' }, sel).textContent = 'Choose...';
    (q.choices || []).forEach(function (text) {
      el('option', { value: text }, sel).textContent = text;
    });
    sel.value = '';
  }

  function prompt() {
    var q = currentQ();
    if (!q) { document.getElementById('task').textContent = 'Every question answered.'; return; }
    document.getElementById('task').textContent = state.stage === 'num' ? q.text : q.choice_prompt;
    // The unit belongs to the field while it is being typed in; at the choice stage
    // it would run into the next label and read as one sentence.
    document.getElementById('unit').textContent = state.stage === 'num'
      ? 'in ' + otherGood(q) + ' per ' + askedGood(q) : '';
    document.getElementById('choicewrap').classList.toggle('hidden', state.stage !== 'choice');
    UI.progress(state.solved ? state.index + 1 : state.index, questions.length);
    BRIDGE.readout({ task: q.id, stage: state.stage, numeric_correct: state.numCorrect,
                     entered: document.getElementById('num').value || null });
  }

  function finish(correct, choiceCorrect, chose, gaveUp, tries) {
    state.solved = true;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    UI.progress(state.index + 1, questions.length);
    BRIDGE.outcome({
      correct: correct, task: currentQ().id, numeric_correct: state.numCorrect,
      // Top level so the stored `tries` column is the real attempt count, not its
      // default. See the note in `sort_columns` for why `detail` alone is not enough.
      tries: tries,
      detail: { numeric_correct: state.numCorrect, choice_correct: choiceCorrect,
                gave_up: gaveUp, answer: +ocFor(currentQ()).toFixed(4),
                correct_choice: currentQ().choice_answer, chose: chose, tries: tries }
    });
  }

  // ---- check ---------------------------------------------------------------
  function check() {
    var q = currentQ();
    if (!q || state.solved) return;
    var num = document.getElementById('num');
    if (state.stage === 'num') {
      var val = parseFloat(num.value), truth = ocFor(q), tol = +q.tolerance || 0.01;
      if (num.value === '' || isNaN(val)) {
        UI.feedback('Type a number first - the opportunity cost of one unit of '
                    + askedGood(q) + ' in units of ' + otherGood(q) + '.', false);
        return;
      }
      if (Math.abs(val - truth) <= tol) {
        state.numCorrect = true; state.stage = 'choice'; state.tries = 0;
        buildChoices(q); prompt();
        UI.feedback('Correct: ' + fmt(truth, 3) + ' ' + otherGood(q) + ' per 1 ' + askedGood(q)
                    + '. That is ' + fmt(ayOf(q), 0) + ' ' + yGood + ' forgone for '
                    + fmt(axOf(q), 0) + ' ' + xGood + '. Now decide who specialises.', true);
        return;
      }
      state.tries += 1;
      if (state.tries >= MAX_TRIES) {
        num.value = fmt(truth, 4);
        state.numericGaveUp = true; state.stage = 'choice'; state.tries = 0;
        buildChoices(q); prompt();
        UI.feedback('Three tries, so here is the value: ' + fmt(truth, 3) + ' ' + otherGood(q)
                    + ' per 1 ' + askedGood(q) + ' - the other good given up divided by the '
                    + 'good gained. Now choose who specialises.', false);
        return;
      }
      UI.feedback('Not that figure. The opportunity cost of 1 ' + askedGood(q) + ' is what the '
                  + 'party gives up: at full specialisation it forgoes ' + fmt(ayOf(q), 0) + ' '
                  + yGood + ' to make ' + fmt(axOf(q), 0) + ' ' + xGood + ', so divide the '
                  + 'forgone amount by the gained amount.', false);
      return;
    }
    var sel = document.getElementById('choice').value;
    if (!sel) { UI.feedback('Choose an option first.', false); return; }
    if (sel === q.choice_answer) {
      UI.feedback('Correct. ' + (q.why || ''), true);
      finish(state.numCorrect, true, sel, state.numericGaveUp, state.tries + 1);
      return;
    }
    state.tries += 1;
    if (state.tries >= MAX_TRIES) {
      UI.feedback('Three tries, so here is the answer: ' + q.choice_answer + '. ' + (q.why || ''), false);
      finish(false, false, sel, true, state.tries);
      return;
    }
    UI.feedback('Not that party. Whoever gives up less of the other good to make one unit of '
                + askedGood(q) + ' has the comparative advantage - compare the opportunity '
                + 'costs, not the raw output.', false);
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('next').addEventListener('click', function () {
    state.index = Math.min(state.index + 1, questions.length - 1);
    state.stage = 'num'; state.tries = 0; state.solved = false;
    state.numCorrect = false; state.numericGaveUp = false;
    document.getElementById('num').value = '';
    document.getElementById('check').disabled = false;
    document.getElementById('next').classList.add('hidden');
    document.getElementById('choicewrap').classList.add('hidden');
    UI.feedback('');
    prompt();
  });

  prompt();
}
"""

CALC_CHOICE = Archetype(
    id='calc_choice',
    title='Calculate, then choose',
    blurb='Work out an opportunity cost from two sets of intercepts, then decide who has the '
          'comparative advantage and should specialise.',
    interaction='type a computed opportunity cost, then commit a multiple-choice decision',
    subjects=('economics',),
    tags=('comparative-advantage', 'opportunity-cost', 'trade', 'calculation'),
    reference='Comparative Advantage, reviewecon.com games & activities',
    telemetry='One outcome per question: whether the numeric opportunity cost was right, '
              'whether the specialisation decision was right, the correct values, and the '
              'tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('x_good', 'text', 'Name of the horizontal-axis good.'),
        Field('y_good', 'text', 'Name of the vertical-axis good.'),
        Field('x_max', 'float', 'Horizontal axis maximum.', minimum=1, maximum=1000),
        Field('y_max', 'float', 'Vertical axis maximum.', minimum=1, maximum=1000),
        Field('parties', 'table',
              'The two (or more) producers, each with the intercepts of a linear frontier.',
              minimum_items=2, maximum_items=4,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this party.'),
                  Field('name', 'text', 'Display name.'),
                  Field('colour', 'text', 'Palette name.', required=False,
                        choices=('a', 'b', 'c', 'd', 'e')),
                  Field('x_intercept', 'float', 'Most of the horizontal good it can make.',
                        minimum=1, maximum=1000),
                  Field('y_intercept', 'float', 'Most of the vertical good it can make.',
                        minimum=1, maximum=1000),
              )),
        Field('questions', 'table',
              'One row per question: a numeric opportunity cost, then a decision. The engine '
              'recomputes the cost from the intercepts, so answer is documentation only.',
              minimum_items=1, maximum_items=8,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this question.'),
                  Field('text', 'text', 'The numeric question, e.g. "what is Alpha\'s '
                        'opportunity cost of 1 coffee?"'),
                  Field('party', 'text', 'id of the party the numeric part is about.'),
                  Field('per_good', 'text', 'Which good the opportunity cost is of.',
                        choices=('x', 'y')),
                  Field('answer', 'float', 'The opportunity cost the author expects.'),
                  Field('tolerance', 'float', 'Accepted error in the numeric answer.',
                        minimum=0, maximum=100),
                  Field('choice_prompt', 'text', 'The decision question.'),
                  Field('choices', 'list', 'The options offered for the decision.',
                        minimum_items=2, maximum_items=4),
                  Field('choice_answer', 'text', 'The option text that is correct.'),
                  Field('why', 'text', 'The reasoning revealed after the answer.',
                        required=False),
              )),
    ),
    body=lambda spec: _CALC_BODY,
    engine=lambda spec: _CALC_ENGINE,
)

# ---------------------------------------------------------------------------
# elasticity_probe
# ---------------------------------------------------------------------------

_ELAS_BODY = (
    '<div class="stagecol">'
    '<div id="task" style="flex:0 0 auto;padding:2px 4px 10px;'
    'font-size:13.5px;font-weight:600;line-height:1.45;color:var(--ink)"></div>'
    '<div class="scene-wrap">'
    '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
    'aria-label="A demand curve with two marked points"></svg>'
    '</div>'
    '<div class="controls">'
    '<label class="fld" id="numwrap">Coefficient'
    '<input type="number" id="num" step="any" aria-label="Your elasticity coefficient"></label>'
    '<label class="fld hidden" id="classwrap">Classification'
    '<select id="class" aria-label="Classify the elasticity"></select></label>'
    '<label class="fld hidden" id="signwrap">What the sign tells you'
    '<select id="sign" aria-label="What the sign of the coefficient tells you"></select></label>'
    '<span class="spacer"></span>'
    '<button class="primary" id="check">Check</button>'
    '</div>'
    '</div>')

_ELAS_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var pts = spec.points || [];
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 44;
  var xMax = +spec.x_max || 10, yMax = +spec.y_max || 10;
  var MAX_TRIES = 3;
  var xLab = spec.x_label || 'Quantity', yLab = spec.y_label || 'Price';
  var method = spec.method === 'midpoint' ? 'midpoint' : 'point';
  var toX = scale([0, xMax], [X0, X1]);
  var toY = scale([0, yMax], [Y0, Y1]);

  // Round ticks. max/5 turned 12 into steps of 2.4 and 6 into steps of 1.2, which
  // printed as 0, 2, 5, 7, 10, 12 - labels that are neither evenly spaced nor the
  // values the gridlines sit on.
  function niceStep(max) {
    var raw = max / 5, mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var n = raw / mag, step;
    if (n <= 1) step = 1; else if (n <= 2) step = 2; else if (n <= 3) step = 3;
    else if (n <= 5) step = 5; else step = 10;
    return step * mag;
  }
  function placesFor(step) { return step >= 1 ? 0 : (step >= 0.1 ? 1 : 2); }

  var P1 = +pts[0].price, Q1 = +pts[0].quantity;
  var P2 = +pts[1].price, Q2 = +pts[1].quantity;
  var dP = P2 - P1, dQ = Q2 - Q1;
  var slope = dP / (dQ || 1e-9);        // dP/dQ, for drawing only

  // (dQ/dP) * (P/Q) for the point method; (dQ/dP) * ((P1+P2)/(Q1+Q2)) for mid-point.
  var ratio = dQ / (dP || 1e-9);
  var ePoint = ratio * (P1 / Q1);
  var eMid = ratio * ((P1 + P2) / (Q1 + Q2));
  var e = method === 'midpoint' ? eMid : ePoint;
  var other = method === 'midpoint' ? ePoint : eMid;
  function truthClass(v) {
    var a = Math.abs(v);
    if (a > 1.0000001) return 'elastic';
    if (a < 0.9999999) return 'inelastic';
    return 'unit elastic';
  }

  var chipP1 = UI.chip('p1', (pts[0].label || 'Point 1'), 'a');
  var chipP2 = UI.chip('p2', (pts[1].label || 'Point 2'), 'b');
  chipP1.set('P ' + fmt(P1, 2) + ' | Q ' + fmt(Q1, 2));
  chipP2.set('P ' + fmt(P2, 2) + ' | Q ' + fmt(Q2, 2));
  var chipMethod = UI.chip('m', 'Method', 'd');
  chipMethod.set(method === 'midpoint' ? 'mid-point' : 'point');

  var state = { stage: 'num', tries: 0, done: false, numOK: false, classOK: false, signOK: false, sign: '', gaveUp: false };

  // ---- chart ---------------------------------------------------------------
  var gGrid = svg('g', null, scene);
  var gAxes = svg('g', null, scene);
  var xStep = niceStep(xMax), yStep = niceStep(yMax);
  var xp = placesFor(xStep), yp = placesFor(yStep);
  var i, v;
  for (i = 0; i * xStep <= xMax + 1e-9; i++) {
    v = i * xStep;
    svg('line', { x1: toX(v), x2: toX(v), y1: Y0, y2: Y1, class: 'gridline' }, gGrid);
    svg('text', { x: toX(v), y: Y0 + 16, 'text-anchor': 'middle', class: 'tick' }, gAxes)
      .textContent = fmt(v, xp);
  }
  for (i = 0; i * yStep <= yMax + 1e-9; i++) {
    v = i * yStep;
    svg('line', { x1: X0, x2: X1, y1: toY(v), y2: toY(v), class: 'gridline' }, gGrid);
    svg('text', { x: X0 - 10, y: toY(v) + 3.5, 'text-anchor': 'end', class: 'tick' }, gAxes)
      .textContent = fmt(v, yp);
  }
  svg('line', { x1: X0, x2: X1, y1: Y0, y2: Y0, class: 'axis' }, gAxes);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, gAxes);
  // The axis titles get their own gutters: the x title on a second line under the
  // ticks, the y title rotated into the left margin. Both used to be pinned to the
  // top-left corner, on top of the top tick.
  svg('text', { x: (X0 + X1) / 2, y: Y0 + 38, 'text-anchor': 'middle',
                'font-size': 11.5, 'font-weight': 600, fill: COLOURS.dim }, gAxes)
    .textContent = xLab;
  svg('text', { x: 22, y: (Y0 + Y1) / 2, 'text-anchor': 'middle',
                'font-size': 11.5, 'font-weight': 600, fill: COLOURS.dim,
                transform: 'rotate(-90 22 ' + fmt((Y0 + Y1) / 2, 0) + ')' }, gAxes)
    .textContent = yLab;

  var gCurve = svg('g', { 'data-series': 'demand' }, scene);
  function Pof(q) { return P1 + slope * (q - Q1); }
  var qa = 0, qb = xMax;
  if (Math.abs(slope) > 1e-9) {
    var pa = Pof(qa), pb = Pof(qb);
    if (pa < 0) qa = Q1 + (0 - P1) / slope; else if (pa > yMax) qa = Q1 + (yMax - P1) / slope;
    if (pb < 0) qb = Q1 + (0 - P1) / slope; else if (pb > yMax) qb = Q1 + (yMax - P1) / slope;
  }
  svg('line', { x1: toX(qa), y1: toY(clamp(Pof(qa), 0, yMax)),
                x2: toX(qb), y2: toY(clamp(Pof(qb), 0, yMax)),
                stroke: colour('a'), 'stroke-width': 3, 'stroke-linecap': 'round' }, gCurve);

  // Drop lines from each point to the two axes: the coefficient is a ratio of two
  // changes, so the two coordinates it is built from should be readable off the
  // chart rather than only in the label.
  var gGuides = svg('g', null, scene);
  pts.forEach(function (p) {
    var cx = toX(+p.quantity), cy = toY(+p.price);
    svg('line', { x1: cx, x2: cx, y1: cy, y2: Y0, stroke: COLOURS.edge,
                  'stroke-width': 1, 'stroke-dasharray': '2 6' }, gGuides);
    svg('line', { x1: X0, x2: cx, y1: cy, y2: cy, stroke: COLOURS.edge,
                  'stroke-width': 1, 'stroke-dasharray': '2 6' }, gGuides);
  });

  var gPts = svg('g', { 'data-series': 'points' }, scene);
  pts.forEach(function (p, idx) {
    var cx = toX(+p.quantity), cy = toY(+p.price);
    svg('circle', { cx: cx, cy: cy, r: 6, fill: colour(idx === 0 ? 'a' : 'b'),
                    stroke: '#fff', 'stroke-width': 2 }, gPts);
    var lbl = svg('text', { class: 'lbl', fill: colour(idx === 0 ? 'a' : 'b') }, gPts);
    lbl.textContent = (p.label || ('Point ' + (idx + 1)))
      + ' (' + fmt(+p.quantity, 1) + ', ' + fmt(+p.price, 1) + ')';
    var lx = cx + 12, anchor = 'start', flip = false;
    if (lx + 118 > X1) { lx = cx - 12; anchor = 'end'; flip = true; }
    // A label that flips to the left of a descending curve would otherwise be drawn
    // across the line, so it drops below the point instead of above it.
    var ly = flip ? cy + 22 : cy - 11;
    if (ly < Y1 + 20) ly = cy + 22;
    lbl.setAttribute('x', lx);
    lbl.setAttribute('y', ly);
    lbl.setAttribute('text-anchor', anchor);
  });

  // ---- model ---------------------------------------------------------------
  function buildClass() {
    var sel = document.getElementById('class');
    clear(sel);
    ['elastic', 'inelastic', 'unit elastic'].forEach(function (v) {
      el('option', { value: v }, sel).textContent = v;
    });
    sel.value = '';
  }
  function buildSign() {
    var sel = document.getElementById('sign');
    clear(sel);
    el('option', { value: '' }, sel).textContent = 'Choose...';
    (spec.sign_choices || []).forEach(function (v) {
      el('option', { value: v }, sel).textContent = v;
    });
    sel.value = '';
  }

  function prompt() {
    document.getElementById('task').textContent =
      state.stage === 'num' ? spec.coefficient_prompt
      : state.stage === 'class' ? 'Classify the demand: is it elastic, inelastic, or unit elastic?'
      : spec.sign_prompt;
    document.getElementById('numwrap').classList.toggle('hidden', state.stage !== 'num');
    document.getElementById('classwrap').classList.toggle('hidden', state.stage !== 'class');
    document.getElementById('signwrap').classList.toggle('hidden', state.stage !== 'sign');
    BRIDGE.readout({ stage: state.stage, method: method, coefficient: +e.toFixed(4),
                     entered: document.getElementById('num').value || null });
  }

  function formulaNote() {
    return method === 'midpoint'
      ? '(ΔQ/ΔP) × ((P1+P2)/(Q1+Q2)) = ' + fmt(ratio, 3) + ' × ' + fmt((P1 + P2) / (Q1 + Q2), 3)
      : '(ΔQ/ΔP) × (P1/Q1) = ' + fmt(ratio, 3) + ' × ' + fmt(P1 / Q1, 3);
  }

  function finish(gaveUp) {
    state.done = true;
    document.getElementById('check').disabled = true;
    // Every stage must be right: a correct coefficient and classification with a mis-read
    // sign has not demonstrated the concept, so the sign reading is part of the score.
    var correct = state.numOK && state.classOK && state.signOK;
    UI.feedback((correct ? 'Correct. ' : 'Here is the full answer. ')
      + 'The coefficient is ' + fmt(e, 3) + ' (' + formulaNote() + '), which makes demand '
      + truthClass(e) + ' because |e| is ' + (Math.abs(e) > 1 ? 'greater than' : Math.abs(e) < 1 ? 'less than' : 'equal to')
      + ' 1. ' + (spec.why || '')
      + ' By the other method the coefficient would be ' + fmt(other, 3) + '.', correct);
    BRIDGE.outcome({
      correct: correct, method: method,
      // Top level so the stored `tries` column is the real attempt count, not its
      // default. See the note in `sort_columns` for why `detail` alone is not enough.
      tries: state.tries,
      detail: {
        numeric_correct: state.numOK, class_correct: state.classOK, sign_correct: state.signOK,
        coefficient: +e.toFixed(4), point_value: +ePoint.toFixed(4), midpoint_value: +eMid.toFixed(4),
        classification: truthClass(e),
        // `sign` is the learner's own pick; the answer is kept under a separate key so the
        // record is auditable and a wrong reading cannot hide behind the correct string.
        sign: state.sign, sign_answer: spec.sign_answer,
        gave_up: gaveUp, tries: state.tries
      }
    });
  }

  function check() {
    if (state.done) return;
    if (state.stage === 'num') {
      var raw = document.getElementById('num').value, val = parseFloat(raw), tol = +spec.tolerance || 0.01;
      if (raw === '' || isNaN(val)) {
        UI.feedback('Type the coefficient first. Use the formula shown in the prompt for the '
                    + (method === 'midpoint' ? 'mid-point' : 'point') + ' method.', false);
        return;
      }
      if (Math.abs(val - e) <= tol) {
        state.numOK = true; state.stage = 'class'; state.tries = 0;
        prompt();
        UI.feedback('Correct: ' + fmt(e, 3) + ' (' + formulaNote() + '). Now classify it.', true);
        return;
      }
      state.tries += 1;
      if (state.tries >= MAX_TRIES) {
        document.getElementById('num').value = fmt(e, 4);
        state.gaveUp = true; state.stage = 'class'; state.tries = 0; prompt();
        UI.feedback('Three tries, so here is the value: ' + fmt(e, 3) + ' (' + formulaNote()
                    + '). Now classify it.', false);
        return;
      }
      UI.feedback('Not that figure. Substitute carefully: ' + formulaNote() + ' - the '
                  + (method === 'midpoint' ? 'mid-point method averages the two prices and the '
                     + 'two quantities; the point method uses just the first point.' : 'point '
                     + 'method uses the first point\'s own price and quantity.'), false);
      return;
    }
    if (state.stage === 'class') {
      var cls = document.getElementById('class').value;
      if (!cls) { UI.feedback('Choose a classification first.', false); return; }
      if (cls === truthClass(e)) {
        state.classOK = true; state.stage = 'sign'; state.tries = 0; prompt();
        UI.feedback('Correct - |' + fmt(e, 3) + '| is ' + (Math.abs(e) > 1 ? 'greater than' : Math.abs(e) < 1 ? 'less than' : 'equal to')
                    + ' 1, so demand is ' + truthClass(e) + '. Finally, read the sign.', true);
        return;
      }
      state.tries += 1;
      if (state.tries >= MAX_TRIES) {
        state.gaveUp = true; state.stage = 'sign'; state.tries = 0; prompt();
        UI.feedback('Three tries - |' + fmt(e, 3) + '| ' + (Math.abs(e) > 1 ? 'exceeds' : Math.abs(e) < 1 ? 'is below' : 'equals')
                    + ' 1, so demand is ' + truthClass(e) + '. Finally, read the sign.', false);
        return;
      }
      UI.feedback('Not quite. Classification is about the magnitude, not the sign: compare '
                  + '|e| = ' + fmt(Math.abs(e), 3) + ' with 1.', false);
      return;
    }
    var sign = document.getElementById('sign').value;
    if (!sign) { UI.feedback('Choose what the sign tells you first.', false); return; }
    state.sign = sign;
    if (sign === spec.sign_answer) {
      state.signOK = true;
      finish(false);
      return;
    }
    state.tries += 1;
    if (state.tries >= MAX_TRIES) { state.gaveUp = true; finish(true); return; }
    UI.feedback('Not that reading of the sign. The coefficient here is ' + fmt(e, 3)
                + ' - ask what the sign says about how price and quantity move together.', false);
  }

  document.getElementById('check').addEventListener('click', check);
  buildClass();
  buildSign();
  prompt();
}
"""

ELASTICITY_PROBE = Archetype(
    id='elasticity_probe',
    title='Elasticity probe',
    blurb='Given two points on a demand curve, work out the elasticity coefficient by the '
          'point or mid-point method, classify it, and read its sign.',
    interaction='type an elasticity coefficient, then classify it and read its sign',
    subjects=('economics',),
    tags=('elasticity', 'formula', 'calculation', 'classification'),
    reference='Elasticity Coefficients, reviewecon.com games & activities',
    telemetry='One outcome per task: whether the coefficient, the classification and the sign '
              'reading were right, the point-method and mid-point-method values, and the '
              'tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('coefficient_prompt', 'text', 'The prompt asking for the coefficient, naming the '
              'method in words.'),
        Field('x_label', 'text', 'Horizontal axis label.', required=False),
        Field('y_label', 'text', 'Vertical axis label.', required=False),
        Field('x_max', 'float', 'Horizontal axis maximum.', minimum=1, maximum=100000),
        Field('y_max', 'float', 'Vertical axis maximum.', minimum=1, maximum=100000),
        Field('method', 'text', 'Which formula the task asks for.',
              choices=('point', 'midpoint')),
        Field('tolerance', 'float', 'Accepted error in the coefficient.', minimum=0, maximum=5),
        Field('points', 'table', 'Exactly two points on the curve, in order.',
              minimum_items=2, maximum_items=2,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this point.'),
                  Field('label', 'text', 'Display label, e.g. "Point A".', required=False),
                  Field('price', 'float', 'Price at this point.', minimum=0, maximum=100000),
                  Field('quantity', 'float', 'Quantity at this point.', minimum=0, maximum=100000),
              )),
        Field('sign_prompt', 'text', 'The prompt asking what the sign tells you.'),
        Field('sign_choices', 'list', 'The readings of the sign offered as options.',
              minimum_items=2, maximum_items=4),
        Field('sign_answer', 'text', 'The option text that is correct.'),
        Field('why', 'text', 'The reasoning revealed after the answer.', required=False),
    ),
    body=lambda spec: _ELAS_BODY,
    engine=lambda spec: _ELAS_ENGINE,
)


#: Every archetype in this module, in the order the catalogue should present them.
ECONOMICS_ARCHETYPES = (PPF_FRONTIER, SORT_COLUMNS, CALC_CHOICE, ELASTICITY_PROBE)
