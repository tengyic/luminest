"""Mathematics and computer-science archetypes: area models, probability, patterns,
and stepping through an algorithm.

Four interactions live here, each a variation on the pattern set out in
:mod:`app.harness.playground.archetypes_core`:

``area_model``
    A rectangle of unit squares, subdivided so the partial products are visible.
    In *multiply* mode the sides are fixed and the learner drags the dividers and
    adds the sub-rectangles; in *factor* mode the area is fixed and the learner
    builds the sides. The distributive property is shown rather than asserted.

``probability_lab``
    Run 1 / 10 / 100 / 1000 trials and watch the empirical distribution settle on
    the theoretical one, then commit to a prediction about a *separate*, seeded
    run. Randomness comes from ``rand(seed)``, so the same spec always plays the
    same way.

``pattern_sequence``
    Extend an arithmetic pattern by one term, then state the rule ``a + (n-1)d``.
    Two committed tasks, two outcomes.

``step_algorithm``
    Step forward and back through insertion or bubble sort on a bar chart, with
    comparison and move counters that are exact for the algorithm implemented,
    then predict the comparison count or the array's state after *k* steps.

Two rules from the runtime are honoured throughout, and one is worth restating
because it is easy to get wrong: the drag, the trial run and the single step are
*exploration* and post ``BRIDGE.readout`` only; the Check button is *commitment*
and posts ``BRIDGE.outcome`` exactly once per committed task.
"""

from __future__ import annotations

from typing import Any, Mapping

from .archetypes import Archetype, Field

#: Tries before the game hands over the answer. Grinding teaches a learner that
#: the activity is a guessing game; being told teaches them the thing they missed.
_MAX_TRIES = 3


# =============================================================== area_model

def _body_area(spec: Mapping[str, Any]) -> str:
    factor = str(spec.get('mode') or '') == 'factor'
    ans_cls = 'fld hidden' if factor else 'fld'
    side_dis = '' if factor else ' disabled'
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        'aria-label="A rectangle of unit squares, split into sub-rectangles so the '
        'partial products are visible"></svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="task"></span>'
        '<span class="spacer"></span>'
        '<label class="fld">Width <input type="number" id="w" min="1" max="24" '
        'step="1" style="width:62px"' + side_dis + '></label>'
        '<label class="fld">Height <input type="number" id="h" min="1" max="24" '
        'step="1" style="width:62px"' + side_dis + '></label>'
        '<label class="' + ans_cls + '" id="answrap">Area '
        '<input type="number" id="answer" step="any" style="width:84px"></label>'
        '<button id="reset">Reset</button>'
        '<button class="primary" id="check">Check</button>'
        '</div>'
        '</div>')


_ENGINE_AREA = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var MAX_TRIES = __MAX_TRIES__;
  var mode = (spec.mode === 'factor') ? 'factor' : 'multiply';
  var MAXS = 24;
  // Two columns: the model on the left, the arithmetic on the right. The grid is
  // re-fitted to its column on every draw, so the diagram always fills the card
  // whatever the sides are. The first draft scaled every rectangle to a fixed
  // 24 x 24 budget, which drew a 13 x 24 model as a postage stamp on a blank page.
  var GX0 = 88, GX1 = 500, GY0 = 392, GY1 = 40;
  var GW = GX1 - GX0, GH = GY0 - GY1;
  var DIVX = 516, PX = 540, PV = 812;
  var U = 1, RX = GX0;

  function clampInt(v) { v = Math.round(+v); if (!isFinite(v)) v = 1; return clamp(v, 1, MAXS); }
  function clampDiv(v, n) { v = Math.round(+v); if (!isFinite(v)) v = 0; return clamp(v, 0, Math.max(0, n - 1)); }
  // Split at the largest whole ten below the side, so the sub-rectangles are the
  // place-value parts a learner is taught to compute in their head.
  function tensSplit(n) {
    var m = Math.floor(n / 10) * 10;
    if (m >= 1 && m < n) return m;
    return Math.floor(n / 2);
  }

  var declaredW = clampInt(spec.width === undefined || spec.width === null ? 12 : spec.width);
  var declaredH = clampInt(spec.height === undefined || spec.height === null ? 12 : spec.height);
  var targetArea = Math.round(+(spec.area || (declaredW * declaredH)));
  var tol = Math.max(0, +(spec.tolerance || 0));

  var w = declaredW, h = declaredH;
  var splitW = tensSplit(w), splitH = tensSplit(h);
  var tries = 0, solved = false;

  var wIn = document.getElementById('w');
  var hIn = document.getElementById('h');
  var ansIn = document.getElementById('answer');
  var checkBtn = document.getElementById('check');
  var resetBtn = document.getElementById('reset');
  var taskEl = document.getElementById('task');

  var chipW = UI.chip('w', 'Width', 'a');
  var chipH = UI.chip('h', 'Height', 'a');
  var chipArea = (mode === 'factor') ? UI.chip('area', 'Area', 'c') : null;
  var chipTarget = (mode === 'factor') ? UI.chip('target', 'Target area', 'd') : null;
  var chipParts = (mode === 'multiply') ? UI.chip('parts', 'Sub-rectangles', 'b') : null;

  var gGrid = svg('g', { 'data-series': 'unit-grid' }, scene);
  var gRect = svg('g', { 'data-series': 'rectangle' }, scene);
  var gParts = svg('g', { 'data-series': 'partial-products' }, scene);
  var gPanel = svg('g', { 'data-series': 'workings' }, scene);
  var gHandles = svg('g', { 'data-series': 'handles' }, scene);

  // The column rule between the model and its arithmetic, drawn once.
  var gAxis = svg('g', { 'data-series': 'axis' }, scene);
  svg('line', { x1: DIVX, x2: DIVX, y1: GY1, y2: GY0, stroke: colour('edge'),
                'stroke-width': 1 }, gAxis);

  // The visible mark is 22px across with a white ring, and a transparent 52px
  // disc behind it gives it a touch target worth grabbing. Both are positioned by
  // cx/cy rather than by a transform on a parent group: getBBox() ignores ancestor
  // transforms, so a transformed handle measures as if it sat at the origin.
  function mkHandle() {
    var hit = svg('circle', { r: 26, fill: 'rgba(0,0,0,0)', 'pointer-events': 'all' }, gHandles);
    var dot = svg('circle', { r: 11, fill: COLOURS.card, stroke: colour('a'),
                              'stroke-width': 2.5, 'pointer-events': 'none' }, gHandles);
    return { hit: hit, dot: dot };
  }
  var hRight = mkHandle(), hTop = mkHandle(), hDivV = mkHandle(), hDivH = mkHandle();

  function place(h, x, y) {
    h.hit.setAttribute('cx', x); h.hit.setAttribute('cy', y);
    h.dot.setAttribute('cx', x); h.dot.setAttribute('cy', y);
  }

  function partsNow() {
    var sw = clampDiv(splitW, w), sh = clampDiv(splitH, h);
    var pw1 = sw, pw2 = w - sw, ph1 = sh, ph2 = h - sh;
    return { sw: sw, sh: sh, a: pw1 * ph1, b: pw2 * ph1, c: pw1 * ph2, d: pw2 * ph2,
             pw1: pw1, pw2: pw2, ph1: ph1, ph2: ph2 };
  }

  function partsPhrase() {
    var p = partsNow();
    return p.pw1 + ' x ' + p.ph1 + ' = ' + p.a + ', ' + p.pw2 + ' x ' + p.ph1 + ' = ' + p.b
      + ', ' + p.pw1 + ' x ' + p.ph2 + ' = ' + p.c + ' and ' + p.pw2 + ' x ' + p.ph2
      + ' = ' + p.d;
  }

  function factorPairs() {
    var out = [];
    for (var a = 1; a <= MAXS; a++) {
      if (targetArea % a === 0) {
        var b = targetArea / a;
        if (b <= MAXS && a <= b) out.push(a + ' x ' + b);
      }
    }
    return out;
  }

  function factorPair() {
    var pairs = factorPairs();
    if (!pairs.length) return String(targetArea);
    // Prefer the pair closest to a square: it is the easiest to draw and check.
    var best = pairs[0];
    var bestGap = Infinity;
    pairs.forEach(function (s) {
      var bits = s.split(' x ');
      var gap = Math.abs((+bits[0]) - (+bits[1]));
      if (gap < bestGap) { bestGap = gap; best = s; }
    });
    return best;
  }

  // The four sub-rectangles as a vertical addition, so the distributive property
  // is written down next to the picture rather than only implied by it.
  function drawPanel() {
    var p = partsNow();
    var rows = [
      { l: p.pw1 + ' \u00d7 ' + p.ph1, v: p.a },
      { l: p.pw2 + ' \u00d7 ' + p.ph1, v: p.b },
      { l: p.pw1 + ' \u00d7 ' + p.ph2, v: p.c },
      { l: p.pw2 + ' \u00d7 ' + p.ph2, v: p.d }
    ];
    svg('text', { x: PX, y: 92, class: 'note' }, gPanel).textContent =
      (mode === 'multiply') ? 'PARTIAL PRODUCTS' : 'YOUR RECTANGLE';
    rows.forEach(function (r, i) {
      var y = 132 + i * 30;
      svg('rect', { x: PX, y: y - 9, width: 9, height: 9, rx: 2.5,
                    fill: colour('a-soft'), stroke: colour('a'), 'stroke-width': 1.2 }, gPanel);
      svg('text', { x: PX + 20, y: y, class: 'lbl' }, gPanel).textContent = r.l;
      svg('text', { x: PV, y: y, class: 'lbl', 'text-anchor': 'end' }, gPanel)
        .textContent = String(r.v);
    });
    svg('line', { x1: PX, x2: PV, y1: 246, y2: 246, stroke: colour('edge'),
                  'stroke-width': 1.4 }, gPanel);
    if (mode === 'multiply') {
      // The total is the answer, so the panel states the question and leaves it out.
      svg('text', { x: PX, y: 282, class: 'lbl' }, gPanel).textContent = 'Total';
      svg('text', { x: PV, y: 282, 'text-anchor': 'end', class: 'lbl',
                    style: 'font-size:17px' }, gPanel).textContent = '?';
    } else {
      svg('text', { x: PX, y: 278, class: 'lbl' }, gPanel).textContent = 'Area';
      svg('text', { x: PV, y: 278, 'text-anchor': 'end', class: 'lbl',
                    style: 'font-size:17px' }, gPanel).textContent = String(w * h);
      svg('text', { x: PX, y: 310, class: 'lbl' }, gPanel).textContent = 'Target';
      svg('text', { x: PV, y: 310, 'text-anchor': 'end', class: 'lbl',
                    style: 'font-size:17px' }, gPanel).textContent = String(targetArea);
      var d = w * h - targetArea;
      svg('text', { x: PX, y: 342, class: 'note', style: 'fill:var(--ink-2)' }, gPanel)
        .textContent = (d === 0) ? 'Target met'
          : (Math.abs(d) + (d > 0 ? ' over the target' : ' short of the target'));
    }
  }

  function draw() {
    U = Math.min(GW / w, GH / h);
    RX = GX0 + (GW - w * U) / 2;
    var ry = GY0 - h * U, rw = w * U, rh = h * U;
    var p = partsNow();
    clear(gGrid); clear(gRect); clear(gParts); clear(gPanel);

    // A soft wash under the unit grid, so the model reads as one object on the card.
    svg('rect', { x: RX, y: ry, width: rw, height: rh, rx: 2,
                  fill: colour('a-soft'), opacity: 0.45 }, gGrid);
    var i, j;
    for (i = 1; i < w; i++) {
      svg('line', { x1: RX + i * U, x2: RX + i * U, y1: ry, y2: GY0, class: 'gridline',
                    style: 'stroke:rgba(36,49,42,.13)' }, gGrid);
    }
    for (j = 1; j < h; j++) {
      svg('line', { x1: RX, x2: RX + rw, y1: ry + j * U, y2: ry + j * U, class: 'gridline',
                    style: 'stroke:rgba(36,49,42,.13)' }, gGrid);
    }
    svg('rect', { x: RX, y: ry, width: rw, height: rh, rx: 2, fill: 'none',
                  stroke: colour('a'), 'stroke-width': 2.4 }, gRect);

    // A divider only where there is something on both sides of it.
    if (p.sw > 0 && p.sw < w) {
      svg('line', { x1: RX + p.sw * U, x2: RX + p.sw * U, y1: ry, y2: GY0,
                    stroke: colour('d'), 'stroke-width': 2.2,
                    'stroke-dasharray': '6 5' }, gRect);
    }
    if (p.sh > 0 && p.sh < h) {
      svg('line', { x1: RX, x2: RX + rw, y1: GY0 - p.sh * U, y2: GY0 - p.sh * U,
                    stroke: colour('d'), 'stroke-width': 2.2,
                    'stroke-dasharray': '6 5' }, gRect);
    }

    // Both labels sit clear of the handle travel along the edge: a divider handle
    // can rest anywhere on the bottom or left side of the model. The axis titles
    // live in the gutter outside the grid, so they never collide with a side label.
    svg('text', { x: RX + rw / 2, y: GY0 + 30, 'text-anchor': 'middle', class: 'lbl' },
        gRect).textContent = String(w);
    svg('text', { x: RX + rw / 2, y: GY0 + 52, 'text-anchor': 'middle', class: 'note' },
        gRect).textContent = 'width';
    svg('text', { x: RX - 18, y: ry + rh / 2 + 5, 'text-anchor': 'end', class: 'lbl' },
        gRect).textContent = String(h);
    svg('text', { x: RX - 52, y: ry + rh / 2, 'text-anchor': 'middle', class: 'note',
                  transform: 'rotate(-90 ' + (RX - 52) + ' ' + (ry + rh / 2) + ')' },
        gRect).textContent = 'height';

    var cells = [
      { x: RX,             y: GY0 - p.sh * U, w: p.pw1 * U, h: p.ph1 * U, v: p.a },
      { x: RX + p.pw1 * U, y: GY0 - p.sh * U, w: p.pw2 * U, h: p.ph1 * U, v: p.b },
      { x: RX,             y: ry,            w: p.pw1 * U, h: p.ph2 * U, v: p.c },
      { x: RX + p.pw1 * U, y: ry,            w: p.pw2 * U, h: p.ph2 * U, v: p.d }
    ];
    cells.forEach(function (c) {
      if (c.w < 32 || c.h < 20) return;
      svg('text', { x: c.x + c.w / 2, y: c.y + c.h / 2 + 5, 'text-anchor': 'middle',
                    class: 'lbl' }, gParts).textContent = String(c.v);
    });

    place(hRight, RX + rw, GY0);
    place(hTop, RX, ry);
    place(hDivV, RX + p.sw * U, GY0);
    place(hDivH, RX, GY0 - p.sh * U);

    var sidesLive = (mode === 'factor' && !solved);
    [hRight, hTop].forEach(function (h) {
      [h.hit, h.dot].forEach(function (node) {
        node.setAttribute('opacity', sidesLive ? 1 : 0);
      });
      h.hit.style.pointerEvents = sidesLive ? 'all' : 'none';
    });

    drawPanel();
    chipW.set(String(w));
    chipH.set(String(h));
    if (chipArea) { chipArea.set(String(w * h)); chipTarget.set(String(targetArea)); }
    if (chipParts) { chipParts.set([p.a, p.b, p.c, p.d].join(' + ')); }
    UI.progress(solved ? 1 : 0, 1);

    // Live state for the workbench. Never stored, and deliberately not the answer.
    BRIDGE.readout({ width: w, height: h, area: w * h, split_w: p.sw, split_h: p.sh,
                     parts: [p.a, p.b, p.c, p.d] });
  }

  // ---- drag ----------------------------------------------------------------
  // The drawing re-fits itself to the card on every move, so the pointer mapping
  // is frozen at the moment the drag starts: computing the side from a scale that
  // the side itself changes is a feedback loop, and it runs away to the maximum.
  var dragRef = null;
  function grabRef() { dragRef = { U: U, RX: RX, Y0: GY0 }; return {}; }

  drag(hRight.hit, {
    start: function () { return (mode === 'factor' && !solved) ? grabRef() : false; },
    move: function (pt) {
      w = clampInt((pt.x - dragRef.RX) / dragRef.U); splitW = tensSplit(w);
      if (wIn) wIn.value = String(w);
      draw();
    }
  });
  drag(hTop.hit, {
    start: function () { return (mode === 'factor' && !solved) ? grabRef() : false; },
    move: function (pt) {
      h = clampInt((dragRef.Y0 - pt.y) / dragRef.U); splitH = tensSplit(h);
      if (hIn) hIn.value = String(h);
      draw();
    }
  });
  // The dividers move the split, never the sides: the total area is invariant
  // under the split, which is the whole point of the distributive property.
  drag(hDivV.hit, {
    start: function () { return solved ? false : grabRef(); },
    move: function (pt) { splitW = clampDiv((pt.x - dragRef.RX) / dragRef.U, w); draw(); }
  });
  drag(hDivH.hit, {
    start: function () { return solved ? false : grabRef(); },
    move: function (pt) { splitH = clampDiv((dragRef.Y0 - pt.y) / dragRef.U, h); draw(); }
  });

  function onSide() {
    if (mode !== 'factor' || solved) return;
    w = clampInt(wIn.value); h = clampInt(hIn.value);
    splitW = tensSplit(w); splitH = tensSplit(h);
    draw();
  }
  if (wIn) wIn.addEventListener('change', onSide);
  if (hIn) hIn.addEventListener('change', onSide);

  // ---- commit --------------------------------------------------------------
  function check() {
    if (solved) return;
    if (mode === 'multiply') {
      var raw = ansIn ? ansIn.value.trim() : '';
      if (!raw) {
        UI.feedback('Enter the area of the whole rectangle before checking.', false);
        return;
      }
      var val = parseFloat(raw);
      if (!isFinite(val)) {
        UI.feedback('That is not a number. Enter the total area, in square units.', false);
        return;
      }
      var want = declaredW * declaredH;
      if (Math.abs(val - want) <= tol) {
        solved = true; checkBtn.disabled = true;
        UI.feedback('Correct. ' + declaredW + ' x ' + declaredH + ' = ' + want
          + '. The dividers split the rectangle into ' + partsPhrase() + '. Those four '
          + 'areas add to ' + want + ' - the same total however you place the dividers. '
          + 'That is the distributive property: ' + declaredW + ' x ' + declaredH + ' = '
          + declaredW + ' x 10 + ' + declaredW + ' x ' + (declaredH - 10) + ' and so on.',
          true);
        BRIDGE.outcome({ correct: true, task: 'area', tries: tries + 1,
                         width: declaredW, height: declaredH, answer: want,
                         detail: { mode: 'multiply', answer: want } });
      } else {
        wrong('multiply');
      }
    } else {
      var cur = w * h;
      if (Math.abs(cur - targetArea) <= tol) {
        solved = true; checkBtn.disabled = true;
        var pairs = factorPairs();
        UI.feedback('Correct. ' + w + ' x ' + h + ' = ' + targetArea + '. '
          + (pairs.length > 1
              ? 'Other factor pairs of ' + targetArea + ' are ' + pairs.join(', ') + '.'
              : 'It has no other factor pair within the grid.'),
          true);
        BRIDGE.outcome({ correct: true, task: 'factor', tries: tries + 1,
                         width: w, height: h, area: cur,
                         detail: { mode: 'factor', target: targetArea, sides: [w, h] } });
      } else {
        wrong('factor');
      }
    }
  }

  function wrong(kind) {
    tries += 1;
    if (tries >= MAX_TRIES) {
      solved = true; checkBtn.disabled = true;
      if (kind === 'multiply') {
        var answer = declaredW * declaredH;
        UI.feedback('This is the third try, so here is the answer: ' + declaredW + ' x '
          + declaredH + ' = ' + answer + '. Add the sub-rectangles: ' + partsPhrase()
          + ', which is ' + answer + '.', false);
        BRIDGE.outcome({ correct: false, task: 'area', tries: tries,
                         detail: { mode: 'multiply', answer: answer, gave_up: true } });
      } else {
        UI.feedback('This is the third try, so here is the answer: ' + targetArea
          + ' = ' + factorPair() + '.', false);
        BRIDGE.outcome({ correct: false, task: 'factor', tries: tries,
                         detail: { mode: 'factor', target: targetArea, gave_up: true } });
      }
      return;
    }
    if (kind === 'multiply') {
      UI.feedback('Not yet. Add the four numbers shown inside the rectangle - one per '
        + 'sub-rectangle. Check you have not dropped one, and check the place values.',
        false);
    } else {
      UI.feedback('Your rectangle has area ' + (w * h) + ', but the target is '
        + targetArea + '. Make one side longer and the other shorter and try again.',
        false);
    }
  }

  // ---- controls ------------------------------------------------------------
  checkBtn.addEventListener('click', check);
  resetBtn.addEventListener('click', function () {
    if (solved) return;
    w = declaredW; h = declaredH; splitW = tensSplit(w); splitH = tensSplit(h);
    if (wIn) wIn.value = String(w);
    if (hIn) hIn.value = String(h);
    if (ansIn) ansIn.value = '';
    UI.feedback('');
    draw();
  });

  if (mode === 'multiply') {
    if (wIn) wIn.disabled = true;
    if (hIn) hIn.disabled = true;
    // The prompt names this task; the how-to already lives in the instruction, and
    // saying it twice is what L2 forbids.
    taskEl.textContent = 'Model ' + declaredW + ' \u00d7 ' + declaredH + ' \u2014 total area?';
  } else {
    taskEl.textContent = 'Target: ' + targetArea + ' square units.';
    if (wIn) wIn.value = String(w);
    if (hIn) hIn.value = String(h);
  }

  draw();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


AREA_MODEL = Archetype(
    id='area_model',
    title='Area model',
    blurb='Build or split a rectangle of unit squares and read the area off the parts.',
    interaction='drag the sides or the dividers; the area and partial products update live',
    subjects=('mathematics',),
    tags=('area', 'multiplication', 'factoring', 'distributive-property', 'number-sense'),
    reference='Area model of multiplication and factoring, as used in NRICH and Mathigon '
              'Polypad activities',
    telemetry='One outcome per committed task: in multiply mode the total area the learner '
              'entered; in factor mode the side lengths they built; plus the tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('mode', 'text', 'multiply: the sides are fixed and the learner finds the area. '
                              'factor: the area is fixed and the learner builds the sides.',
              choices=('multiply', 'factor')),
        Field('width', 'int', 'Width in units. In multiply mode this is the width factor; '
                              'in factor mode it is where the learner starts.',
              required=False, minimum=1, maximum=24),
        Field('height', 'int', 'Height in units. Same meaning as width.',
              required=False, minimum=1, maximum=24),
        Field('area', 'int', 'The target area in factor mode.',
              required=False, minimum=1, maximum=576),
        Field('tolerance', 'float', 'How far the learner may be off and still be correct.',
              required=False, minimum=0, maximum=50),
        Field('seed', 'int', 'Seeds any variation between games.', minimum=0, maximum=1000000000),
    ),
    body=_body_area,
    engine=lambda spec: _ENGINE_AREA,
)


# =========================================================== probability_lab

def _body_prob(spec: Mapping[str, Any]) -> str:
    slider_cls = 'fld' if spec.get('learner_sets') else 'fld hidden'
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        'aria-label="A bar chart of observed frequencies against the theoretical '
        'probabilities"></svg>'
        '</div>'
        '<div class="controls">'
        '<button id="r1">Run 1</button>'
        '<button id="r10">Run 10</button>'
        '<button id="r100">Run 100</button>'
        '<button id="r1000">Run 1000</button>'
        '<button id="reset">Reset</button>'
        '<span class="spacer"></span>'
        '<label class="' + slider_cls + '">Bias '
        '<input type="range" id="p" min="5" max="95" step="5" value="50"></label>'
        '<label class="fld">Predicted proportion '
        '<input type="number" id="answer" min="0" max="1" step="0.01" style="width:84px">'
        '</label>'
        '<button class="primary" id="check">Check</button>'
        '</div>'
        '</div>')


_ENGINE_PROB = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var MAX_TRIES = __MAX_TRIES__;
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 44;

  var rows = spec.outcomes || [];
  if (!rows.length) rows = [{ label: 'Heads', p: 0.5 }, { label: 'Tails', p: 0.5 }];
  rows = rows.slice(0, 6);
  if (rows.length < 2) rows = [{ label: 'Heads', p: 0.5 }, { label: 'Tails', p: 0.5 }];
  var labels = rows.map(function (o, i) { return String(o.label || ('Outcome ' + (i + 1))); });
  var raw = rows.map(function (o) { return Math.max(0, +(o.p || 0)); });
  var ssum = raw.reduce(function (a, b) { return a + b; }, 0) || 1;
  var p = raw.map(function (v) { return v / ssum; });

  var learnerSets = !!spec.learner_sets && p.length === 2;
  var predictTrials = Math.max(1, Math.round(+(spec.predict_trials || 1000)));
  var tol = Math.max(0.001, +(spec.tolerance || 0.05));
  var seed = Math.round(+(spec.seed || 1));

  var counts = p.map(function () { return 0; });
  var total = 0;
  var rng = rand(seed);
  // A second stream, seeded apart from the exploration stream, so running the
  // trials on screen cannot hand the learner the prediction's answer.
  var predictRng = rand(seed + 999983);
  var tries = 0, solved = false, lastObserved = null;

  var toY = scale([0, 1], [Y0, Y1]);
  var n = p.length;
  var slot = (X1 - X0) / n;
  var barW = Math.min(96, slot * 0.6);

  var chipTrials = UI.chip('trials', 'Trials', 'a');
  var chipObs = UI.chip('obs', labels[0], 'a');
  var chipTheo = UI.chip('theo', 'Theoretical', 'c');

  var gAxis = svg('g', { 'data-series': 'axis' }, scene);
  svg('line', { x1: X0, x2: X1, y1: Y0, y2: Y0, class: 'axis' }, gAxis);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, gAxis);
  for (var t = 0; t <= 4; t++) {
    var gy = Y0 - (Y0 - Y1) * t / 4;
    svg('line', { x1: X0, x2: X1, y1: gy, y2: gy, class: 'gridline' }, gAxis);
    svg('text', { x: X0 - 6, y: gy + 3.5, 'text-anchor': 'end', class: 'tick' },
        gAxis).textContent = fmt(t / 4, 2);
  }

  var bars = [], theory = [], vals = [], predMark = null;
  for (var i = 0; i < n; i++) {
    var cx = X0 + slot * (i + 0.5);
    var g = svg('g', { 'data-series': 'outcome-' + i }, scene);
    // Observed frequency is series a; the theoretical line is series c. The bar is
    // not a drop zone, so it is painted as a bar rather than as a lit .bin well.
    bars.push(svg('rect', { x: cx - barW / 2, y: Y0, width: barW, height: 0,
                            fill: colour('a-soft'), stroke: colour('a'),
                            'stroke-width': 1.4 }, g));
    theory.push(svg('line', { x1: cx - barW / 2 - 5, x2: cx + barW / 2 + 5,
                              y1: toY(p[i]), y2: toY(p[i]), stroke: colour('c'),
                              'stroke-width': 2, 'stroke-dasharray': '5 4' }, g));
    // A white halo keeps the number legible where it lands on the dashed line.
    vals.push(svg('text', { x: cx, y: Y0 - 6, 'text-anchor': 'middle', class: 'tick',
                            style: 'paint-order:stroke;stroke:#fff;stroke-width:3px;'
                                   + 'stroke-linejoin:round' }, g));
    svg('text', { x: cx, y: Y0 + 15, 'text-anchor': 'middle', class: 'tick' },
        g).textContent = labels[i];
    svg('text', { x: cx, y: Y0 + 28, 'text-anchor': 'middle', class: 'note' },
        g).textContent = 'p = ' + fmt(p[i], 2);
  }
  // The marker for the separate prediction run, drawn on the first outcome only.
  predMark = svg('line', { x1: X0 + slot * 0.5 - barW / 2 - 6,
                           x2: X0 + slot * 0.5 + barW / 2 + 6,
                           y1: toY(0.5), y2: toY(0.5), stroke: colour('e'),
                           'stroke-width': 2, opacity: 0 }, scene);
  var emptyNote = svg('text', { x: (X0 + X1) / 2, y: (Y0 + Y1) / 2, 'text-anchor': 'middle',
                                class: 'note', style: 'font-size:13px' }, scene);

  function drawTrials(count) {
    for (var t = 0; t < count; t++) {
      var r = rng(), acc = 0, pick = p.length - 1;
      for (var i = 0; i < p.length; i++) { acc += p[i]; if (r < acc) { pick = i; break; } }
      counts[pick] += 1; total += 1;
    }
  }

  function draw() {
    for (var i = 0; i < n; i++) {
      var f = total ? counts[i] / total : 0;
      var y = toY(f);
      bars[i].setAttribute('y', y);
      bars[i].setAttribute('height', Math.max(0, Y0 - y));
      theory[i].setAttribute('y1', toY(p[i]));
      theory[i].setAttribute('y2', toY(p[i]));
      // An empty <text> still reports a degenerate box at the origin, which reads
      // as a mark drawn off-canvas, so the empty state hides it rather than blanks it.
      if (total) {
        vals[i].removeAttribute('display');
        vals[i].textContent = f.toFixed(3);
        vals[i].setAttribute('y', Math.max(Y1 + 12, y - 6));
      } else {
        vals[i].setAttribute('display', 'none');
      }
    }
    // L4: before the first run the chart invites an action instead of printing a
    // row of zero-height bars reading 0.000. The axes, grid and theoretical lines
    // stay, so the scaffolding is visible from the start.
    if (total) emptyNote.setAttribute('display', 'none');
    else {
      emptyNote.removeAttribute('display');
      emptyNote.textContent = 'Press Run 1 to start';
    }
    if (predMark) {
      predMark.setAttribute('opacity', lastObserved === null ? 0 : 1);
      if (lastObserved !== null) {
        predMark.setAttribute('y1', toY(lastObserved));
        predMark.setAttribute('y2', toY(lastObserved));
      }
    }
    chipTrials.set(String(total));
    chipObs.set(total ? (counts[0] / total).toFixed(3) : '--');
    chipTheo.set(fmt(p[0], 3));
    UI.progress(solved ? 1 : 0, 1);
    BRIDGE.readout({ trials: total, counts: counts.slice(),
                     proportions: counts.map(function (c) {
                       return total ? +(c / total).toFixed(4) : 0;
                     }),
                     theoretical: p.map(function (v) { return +v.toFixed(4); }) });
  }

  function resetRun() {
    counts = p.map(function () { return 0; });
    total = 0;
    rng = rand(seed);
    lastObserved = null;
    draw();
  }

  // ---- commit --------------------------------------------------------------
  function check() {
    if (solved) return;
    var ansIn = document.getElementById('answer');
    var rawv = ansIn ? ansIn.value.trim() : '';
    var pred = parseFloat(rawv);
    if (!isFinite(pred) || pred < 0 || pred > 1) {
      UI.feedback('Enter a proportion between 0 and 1 - the share of trials you expect '
        + labels[0] + ' to take.', false);
      return;
    }
    // The prediction run is fresh and independent of what the learner has watched.
    var hit = 0;
    for (var t = 0; t < predictTrials; t++) {
      var r = predictRng(), acc = 0, pick = p.length - 1;
      for (var i = 0; i < p.length; i++) { acc += p[i]; if (r < acc) { pick = i; break; } }
      if (pick === 0) hit += 1;
    }
    var q = hit / predictTrials;
    lastObserved = q;
    var se = Math.sqrt(Math.max(1e-9, p[0] * (1 - p[0]) / predictTrials));
    if (Math.abs(pred - q) <= tol) {
      solved = true;
      document.getElementById('check').disabled = true;
      UI.feedback('You predicted ' + pred + '. In a fresh run of ' + predictTrials
        + ' trials, ' + labels[0] + ' came up ' + hit + ' times - a proportion of '
        + q.toFixed(3) + '. The theoretical probability is ' + p[0].toFixed(3)
        + ', and with ' + predictTrials + ' trials the observed proportion typically '
        + 'lands within about ' + (2 * se).toFixed(3) + ' of it. Your prediction was '
        + 'within ' + tol + ', so it is consistent with the model.', true);
      BRIDGE.outcome({ correct: true, task: 'predict', tries: tries + 1,
                       prediction: pred, observed: +q.toFixed(4),
                       theoretical: +p[0].toFixed(4), trials: predictTrials,
                       detail: { prediction: pred, observed: +q.toFixed(4),
                                 theoretical: +p[0].toFixed(4), trials: predictTrials,
                                 tolerance: tol } });
    } else {
      tries += 1;
      if (tries >= MAX_TRIES) {
        solved = true;
        document.getElementById('check').disabled = true;
        UI.feedback('This is the third try, so here is the answer: in a fresh run of '
          + predictTrials + ' trials, ' + labels[0] + ' came up ' + hit + ' times - a '
          + 'proportion of ' + q.toFixed(3) + '. The theoretical probability is '
          + p[0].toFixed(3) + ', so a prediction near ' + p[0].toFixed(3)
          + ' would have been within ' + tol + '.', false);
        BRIDGE.outcome({ correct: false, task: 'predict', tries: tries,
                        prediction: pred, observed: +q.toFixed(4),
                        theoretical: +p[0].toFixed(4), trials: predictTrials,
                        detail: { prediction: pred, observed: +q.toFixed(4),
                                  theoretical: +p[0].toFixed(4), trials: predictTrials,
                                  tolerance: tol, gave_up: true } });
      } else {
        UI.feedback('Your prediction ' + pred + ' is more than ' + tol + ' from the '
          + 'observed proportion, which was ' + q.toFixed(3) + '. The theoretical value '
          + 'is ' + p[0].toFixed(3) + ': the observed proportion settles around it, and '
          + 'the gap shrinks roughly like 1/sqrt(trials). Predict something near the '
          + 'theoretical value and check again.', false);
      }
    }
    draw();
  }

  // ---- controls ------------------------------------------------------------
  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    if (solved) return;
    resetRun();
    UI.feedback('');
  });
  [['r1', 1], ['r10', 10], ['r100', 100], ['r1000', 1000]].forEach(function (pair) {
    document.getElementById(pair[0]).addEventListener('click', function () {
      drawTrials(pair[1]);
      draw();
    });
  });

  var slider = document.getElementById('p');
  if (learnerSets && slider) {
    slider.value = String(Math.round(p[0] * 100));
    slider.addEventListener('input', function () {
      var v = clamp(+slider.value / 100, 0.05, 0.95);
      p[0] = v; p[1] = 1 - v;
      resetRun();
      UI.feedback('');
    });
  }

  UI.say('Run trials, watch the bars settle on the dashed theoretical lines, then predict '
    + 'the proportion of ' + labels[0] + ' in a fresh run of ' + predictTrials + ' trials.');
  draw();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


PROBABILITY_LAB = Archetype(
    id='probability_lab',
    title='Probability lab',
    blurb='Run trials, watch the empirical distribution settle on the theoretical one, '
          'then predict.',
    interaction='run 1/10/100/1000 trials and watch the bar chart converge',
    subjects=('mathematics',),
    tags=('probability', 'simulation', 'law-of-large-numbers', 'experiment', 'statistics'),
    reference='Experimental probability and the law of large numbers; simulation and '
              'probability models',
    telemetry='One outcome per committed prediction: the predicted proportion, the observed '
              'proportion from a separate seeded run, the theoretical probability, and the '
              'tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('outcomes', 'table',
              'Two to six outcomes with their theoretical probabilities. The values are '
              'normalised, so they need not sum to exactly 1.',
              minimum_items=2, maximum_items=6,
              item_fields=(
                  Field('label', 'text', 'The outcome, e.g. "Heads".'),
                  Field('p', 'float', 'Theoretical probability of this outcome.',
                        minimum=0, maximum=1),
              )),
        Field('learner_sets', 'bool',
              'True to let the learner set the bias of a two-outcome model with a slider.',
              required=False),
        Field('predict_trials', 'int', 'How many trials the prediction run uses.',
              minimum=1, maximum=100000),
        Field('tolerance', 'float', 'How close the prediction must be to the observed '
                                    'proportion.', minimum=0.001, maximum=1),
        Field('seed', 'int', 'Seeds the trial stream, so the same spec always plays the '
                             'same way.', minimum=0, maximum=1000000000),
    ),
    body=_body_prob,
    engine=lambda spec: _ENGINE_PROB,
)


# ========================================================== pattern_sequence

def _body_pattern(spec: Mapping[str, Any]) -> str:
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        'aria-label="A growing arithmetic pattern, one row of tiles per term"></svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="task"></span>'
        '<span class="spacer"></span>'
        '<label class="fld" id="termwrap">Next term '
        '<input type="number" id="nextterm" step="1" style="width:70px"></label>'
        '<label class="fld hidden" id="awrap">First term a '
        '<input type="number" id="aval" step="1" style="width:64px"></label>'
        '<label class="fld hidden" id="dwrap">Common difference d '
        '<input type="number" id="dval" step="1" style="width:64px"></label>'
        '<button class="primary" id="check">Check</button>'
        '</div>'
        '</div>')


_ENGINE_PATTERN = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var MAX_TRIES = __MAX_TRIES__;
  var first = Math.round(+(spec.first === undefined ? 3 : spec.first));
  var step = Math.round(+(spec.step === undefined ? 2 : spec.step));
  if (step === 0) step = 1;
  var shown = clamp(Math.round(+(spec.shown || 4)), 2, 6);

  var terms = [];
  for (var k = 1; k <= shown; k++) terms.push(first + (k - 1) * step);
  var nextVal = first + shown * step;

  var stage = 1, tries = 0, solved = false;

  // One row per term, sized to the widest term so the growth is legible: the tile
  // size is derived from the largest value, not from a fixed budget. The first
  // draft capped the tiles at 16px and the row height at 46px, which left a strip
  // of confetti in the top-left corner of an otherwise empty card.
  var X0 = 150, X1 = 700, Y1 = 44, Y0 = 424;
  var LABX = 128, VALX = 800, HDRY = 30;
  var rows = shown + 1;
  var rowH = (Y0 - Y1) / rows;
  var maxVal = Math.max.apply(null, terms.concat([nextVal]));
  var cell = (X1 - X0) / Math.max(1, maxVal);
  var gap = Math.min(6, Math.max(1.5, cell * 0.18));
  var sq = Math.max(3, Math.min(34, cell - gap));

  var chipTerms = UI.chip('terms', 'Terms', 'a');
  var chipStage = UI.chip('stage', 'Stage', 'c');

  var taskEl = document.getElementById('task');
  var checkBtn = document.getElementById('check');

  function midOf(index) { return Y1 + rowH * (index + 0.5); }

  function rowLabel(index, mid) {
    svg('text', { x: LABX, y: mid + 4, 'text-anchor': 'end', class: 'lbl' }, scene)
      .textContent = 'Term ' + (index + 1);
  }

  function drawTerm(index, value, revealed) {
    var mid = midOf(index);
    rowLabel(index, mid);
    for (var i = 0; i < value; i++) {
      svg('rect', { x: X0 + i * (sq + gap), y: mid - sq / 2, width: sq, height: sq,
                    rx: 2,
                    fill: revealed ? colour('a-soft') : colour('a'),
                    stroke: revealed ? colour('a') : 'none',
                    'stroke-width': revealed ? 1.4 : 0,
                    opacity: revealed ? 1 : 0.85 }, scene);
    }
    svg('text', { x: VALX, y: mid + 5, 'text-anchor': 'end', class: 'lbl' }, scene)
      .textContent = String(value);
  }

  function drawBlank(index) {
    var mid = midOf(index);
    rowLabel(index, mid);
    // A full-width well: "the next row goes here", without hinting at its length.
    svg('rect', { x: X0, y: mid - sq / 2 - 5, width: X1 - X0, height: sq + 10, rx: 8,
                  class: 'bin' }, scene);
    svg('text', { x: (X0 + X1) / 2, y: mid + 5, 'text-anchor': 'middle', class: 'lbl',
                  style: 'fill:var(--ink-3)' }, scene).textContent = '?';
    svg('text', { x: VALX, y: mid + 5, 'text-anchor': 'end', class: 'lbl',
                  style: 'fill:var(--ink-3)' }, scene).textContent = '?';
  }

  function draw() {
    clear(scene);
    svg('text', { x: LABX, y: HDRY, 'text-anchor': 'end', class: 'note' }, scene)
      .textContent = 'TERM';
    svg('text', { x: VALX, y: HDRY, 'text-anchor': 'end', class: 'note' }, scene)
      .textContent = 'TILES';
    // The count column is a column, not a caption floating at the edge of the card.
    svg('line', { x1: 736, x2: 736, y1: 16, y2: 432, stroke: colour('line'),
                  'stroke-width': 1 }, scene);
    for (var i = 0; i < terms.length; i++) drawTerm(i, terms[i], false);
    if (stage === 1) drawBlank(terms.length);
    else drawTerm(terms.length, nextVal, true);
    if (stage === 2) {
      svg('text', { x: (X0 + X1) / 2, y: 446, 'text-anchor': 'middle', class: 'lbl' },
          scene).textContent = 't(n) = ' + first + ' + (n \u2212 1) \u00d7 ' + step;
    }
    chipTerms.set(terms.join(', '));
    chipStage.set(stage === 1 ? 'extend' : 'rule');
    UI.progress(solved ? 2 : (stage === 2 ? 1 : 0), 2);
    BRIDGE.readout({ shown_terms: terms.slice(), stage: stage,
                     differences: terms.slice(1).map(function (v, i) { return v - terms[i]; }) });
  }

  function nextValue() { return nextVal; }

  function check() {
    if (solved) return;
    if (stage === 1) {
      var el1 = document.getElementById('nextterm');
      var raw = el1 ? el1.value.trim() : '';
      var val = parseInt(raw, 10);
      if (!isFinite(val)) {
        UI.feedback('Enter the next term as a whole number.', false);
        return;
      }
      if (val === nextValue()) {
        tries = 0;
        stage = 2;
        document.getElementById('termwrap').classList.add('hidden');
        document.getElementById('awrap').classList.remove('hidden');
        document.getElementById('dwrap').classList.remove('hidden');
        taskEl.textContent = 'Now state the rule: t(n) = a + (n \u2212 1)d.';
        UI.feedback('Correct - the next term is ' + nextValue() + '. Each term is '
          + step + ' more than the one before: ' + terms.join(', ') + ', ' + nextValue()
          + '. Now give the rule.', true);
        BRIDGE.outcome({ correct: true, task: 'next_term', tries: 1,
                         answer: nextValue(),
                         detail: { terms: terms.slice(), next_term: nextValue() } });
        draw();
      } else {
        tries += 1;
        if (tries >= MAX_TRIES) {
          UI.feedback('This is the third try, so here is the answer: the next term is '
            + nextValue() + '. Each term adds ' + step + ' to the one before it.', false);
          BRIDGE.outcome({ correct: false, task: 'next_term', tries: tries,
                           answer: nextValue(),
                           detail: { terms: terms.slice(), next_term: nextValue(),
                                     gave_up: true } });
          solved = true;
          checkBtn.disabled = true;
        } else {
          UI.feedback('Not quite. Look at the jump from one term to the next - the '
            + 'difference is the same every time. Add that difference once more.', false);
        }
      }
      return;
    }
    var aEl = document.getElementById('aval');
    var dEl = document.getElementById('dval');
    var a = parseInt(aEl ? aEl.value.trim() : '', 10);
    var d = parseInt(dEl ? dEl.value.trim() : '', 10);
    if (!isFinite(a) || !isFinite(d)) {
      UI.feedback('Enter both the first term and the common difference.', false);
      return;
    }
    if (a === first && d === step) {
      solved = true;
      checkBtn.disabled = true;
      UI.feedback('Correct. The rule is t(n) = ' + first + ' + (n - 1) x ' + step
        + ': first term ' + first + ', common difference ' + step + '. Check it: t('
        + (shown + 1) + ') = ' + first + ' + ' + shown + ' x ' + step + ' = '
        + nextValue() + ', which is the term you found.', true);
      BRIDGE.outcome({ correct: true, task: 'rule', tries: tries + 1,
                       first_term: first, common_difference: step,
                       detail: { terms: terms.slice(), first_term: first,
                                 common_difference: step } });
    } else {
      tries += 1;
      if (tries >= MAX_TRIES) {
        solved = true;
        checkBtn.disabled = true;
        UI.feedback('This is the third try, so here is the answer: the first term is '
          + first + ' and the common difference is ' + step + ', so t(n) = ' + first
          + ' + (n - 1) x ' + step + '.', false);
        BRIDGE.outcome({ correct: false, task: 'rule', tries: tries,
                         first_term: first, common_difference: step,
                         detail: { terms: terms.slice(), first_term: first,
                                   common_difference: step, gave_up: true } });
      } else {
        var which = [];
        if (a !== first) which.push('the first term (the value of t(1))');
        if (d !== step) which.push('the common difference (how much each term grows by)');
        UI.feedback('Not quite - check ' + which.join(' and ') + '. Read them straight '
          + 'off the first two rows of the pattern.', false);
      }
    }
    // The reveal row and the rule strip only exist in stage 2, so a committed
    // answer has to redraw before the progress rail can move.
    draw();
  }

  checkBtn.addEventListener('click', check);
  taskEl.textContent = 'Term ' + (terms.length + 1) + ' is missing \u2014 how many tiles?';
  draw();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


PATTERN_SEQUENCE = Archetype(
    id='pattern_sequence',
    title='Pattern sequence',
    blurb='Extend a growing pattern by one term, then state its rule as a + (n-1)d.',
    interaction='place the next term, then enter the first term and common difference',
    subjects=('mathematics',),
    tags=('sequences', 'patterns', 'arithmetic', 'nth-term', 'algebra'),
    reference='Arithmetic sequences as linear functions; a + (n-1)d',
    telemetry='Two outcomes: whether the next term was right, and whether the first term '
              'and common difference were right, each with the tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('first', 'int', 'The first term of the sequence.', minimum=0, maximum=20),
        Field('step', 'int', 'The common difference; the sequence grows by this much each '
                             'term.', minimum=1, maximum=12),
        Field('shown', 'int', 'How many terms to show before the blank.', minimum=2, maximum=6),
        Field('seed', 'int', 'Seeds any variation between games.', minimum=0, maximum=1000000000),
    ),
    body=_body_pattern,
    engine=lambda spec: _ENGINE_PATTERN,
)


# ============================================================ step_algorithm

def _body_step(spec: Mapping[str, Any]) -> str:
    after_k = str(spec.get('predict') or '') == 'state_after_k'
    hint = 'e.g. 5, 2, 4, 1' if after_k else 'a whole number'
    # A comparison count is a whole number, so the control is a number input: it gives the
    # numeric keypad a student actually has on a tablet, and lets the browser reject junk
    # before Check ever sees it. The state-after-k mode needs free text ("5, 2, 4, 1"),
    # which a number input would refuse, so it keeps type="text".
    answer_attrs = 'type="text"' if after_k else 'type="number" step="1"'
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        'aria-label="A bar chart of the array being sorted, one bar per element"></svg>'
        '</div>'
        '<div class="controls">'
        # The prompt takes a row of its own: seven controls plus a sentence do not
        # fit on one line, and a wrapped Check button reads as a second action.
        '<span class="verdict" id="task" style="flex:1 0 100%;text-align:left"></span>'
        '<button id="back">Step back</button>'
        '<button id="fwd">Step forward</button>'
        '<button id="reset">Reset</button>'
        '<label class="fld" id="answrap"><span id="anslabel">Answer</span> '
        '<input ' + answer_attrs + ' id="answer" placeholder="' + hint + '" '
        'style="width:150px">'
        '</label>'
        '<button class="primary" id="check">Check</button>'
        '</div>'
        '</div>')


_ENGINE_STEP = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var MAX_TRIES = __MAX_TRIES__;
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 92;

  var arr0 = (spec.array || []).map(function (v) { return Math.round(+v) || 0; });
  if (arr0.length < 2) arr0 = [5, 2, 4, 1];
  var n = arr0.length;
  var algo = (spec.algorithm === 'bubble') ? 'bubble' : 'insertion';
  var algoName = (algo === 'bubble') ? 'bubble sort' : 'insertion sort';
  var predict = (spec.predict === 'state_after_k') ? 'state_after_k' : 'comparisons';
  var k = Math.max(0, Math.round(+(spec.k || 0)));

  function mkSorted(count, upto) {
    var out = [];
    for (var q = 0; q < count; q++) out.push(q < upto);
    return out;
  }
  // In bubble sort the tail settles one element per completed pass: after pass i,
  // indices i' >= m - i are final.
  function sortedTail(count, pass) {
    var out = [];
    for (var q = 0; q < count; q++) out.push(q >= count - pass);
    return out;
  }

  // Each frame is one *comparison*: the array after the comparison, the two
  // indices compared, and the running counters. Precomputing the whole trace is
  // what makes Step back exact and the counters honest - they are read from the
  // simulation, never incremented by the UI.
  function bubbleFrames(src) {
    var a = src.slice(), frames = [], cmp = 0, moves = 0, m = a.length, i, j;
    frames.push({ arr: a.slice(), a: -1, b: -1, cmp: cmp, moves: moves,
                  sorted: mkSorted(m, 0), desc: 'Start: unsorted' });
    for (i = 0; i < m - 1; i++) {
      for (j = 0; j < m - 1 - i; j++) {
        cmp += 1;
        var swapped = a[j] > a[j + 1];
        var d;
        if (swapped) {
          var t = a[j]; a[j] = a[j + 1]; a[j + 1] = t; moves += 1;
          d = 'a[' + j + '] > a[' + (j + 1) + ']: swap';
        } else {
          d = 'a[' + j + '] <= a[' + (j + 1) + ']: leave as is';
        }
        frames.push({ arr: a.slice(), a: j, b: j + 1, cmp: cmp, moves: moves,
                      sorted: sortedTail(m, i), desc: d });
      }
    }
    frames.push({ arr: a.slice(), a: -1, b: -1, cmp: cmp, moves: moves,
                  sorted: mkSorted(m, m), desc: 'Sorted after ' + cmp + ' comparisons' });
    return frames;
  }

  function insertionFrames(src) {
    var a = src.slice(), frames = [], cmp = 0, moves = 0, m = a.length, i;
    frames.push({ arr: a.slice(), a: -1, b: -1, cmp: cmp, moves: moves,
                  sorted: mkSorted(m, 0), desc: 'Start: the first element is a sorted prefix' });
    for (i = 1; i < m; i++) {
      var key = a[i], j = i - 1;
      frames.push({ arr: a.slice(), a: i, b: -1, cmp: cmp, moves: moves,
                    sorted: mkSorted(m, i),
                    desc: 'Take a[' + i + '] = ' + key + ' as the key to insert' });
      while (j >= 0) {
        cmp += 1;
        if (a[j] > key) {
          a[j + 1] = a[j]; moves += 1;
          frames.push({ arr: a.slice(), a: j, b: j + 1, cmp: cmp, moves: moves,
                        sorted: mkSorted(m, i),
                        desc: 'a[' + j + '] = ' + a[j] + ' > ' + key + ': shift it right' });
          j -= 1;
        } else {
          frames.push({ arr: a.slice(), a: j, b: i, cmp: cmp, moves: moves,
                        sorted: mkSorted(m, i),
                        desc: 'a[' + j + '] = ' + a[j] + ' <= ' + key + ': stop shifting' });
          break;
        }
      }
      a[j + 1] = key;
      frames.push({ arr: a.slice(), a: j + 1, b: -1, cmp: cmp, moves: moves,
                    sorted: mkSorted(m, i + 1),
                    desc: 'Place ' + key + ' at index ' + (j + 1) });
    }
    return frames;
  }

  var frames = (algo === 'bubble') ? bubbleFrames(arr0) : insertionFrames(arr0);
  var lastFrame = frames[frames.length - 1];
  var answerCount = lastFrame.cmp;
  var kIndex = Math.min(k, frames.length - 1);
  var answerState = frames[kIndex].arr.slice();

  var cur = 0, tries = 0, solved = false;

  var maxV = Math.max.apply(null, arr0) || 1;
  var slot = (X1 - X0) / n;
  var barW = Math.min(72, slot * 0.62);

  var chipCmp = UI.chip('cmp', 'Comparisons', 'a');
  var chipMoves = UI.chip('moves', algo === 'bubble' ? 'Swaps' : 'Moves', 'c');
  var chipStep = UI.chip('step', 'Step', 'b');

  var taskEl = document.getElementById('task');
  var ansIn = document.getElementById('answer');
  var checkBtn = document.getElementById('check');

  // A caption band above the plot: the step's description used to float at the top
  // of the plot area, where the tallest bar's value label ran into it.
  svg('rect', { x: 48, y: 18, width: 764, height: 42, rx: 10,
                fill: colour('surface2'), stroke: colour('line'),
                'stroke-width': 1 }, scene);
  var gAxis = svg('g', { 'data-series': 'axis' }, scene);
  svg('line', { x1: X0, x2: X1, y1: Y0, y2: Y0, class: 'axis' }, gAxis);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, gAxis);
  for (var t = 0; t <= 4; t++) {
    var gy = Y0 - (Y0 - Y1) * t / 4;
    svg('line', { x1: X0, x2: X1, y1: gy, y2: gy, class: 'gridline' }, gAxis);
    svg('text', { x: X0 - 6, y: gy + 3.5, 'text-anchor': 'end', class: 'tick' },
        gAxis).textContent = fmt(maxV * t / 4, 0);
  }
  var gBars = svg('g', { 'data-series': 'array' }, scene);
  var gNote = svg('g', { 'data-series': 'step-description' }, scene);

  function draw() {
    var f = frames[cur];
    clear(gBars);
    for (var i = 0; i < n; i++) {
      var cx = X0 + slot * (i + 0.5);
      var val = f.arr[i];
      var hgt = maxV ? (val / maxV) * (Y0 - Y1) : 0;
      var y = Y0 - hgt;
      var hi = (i === f.a || i === f.b);
      svg('rect', { x: cx - barW / 2, y: y, width: barW, height: Math.max(0, hgt), rx: 3,
                    fill: f.sorted[i] ? colour('b') : colour('a'),
                    opacity: f.sorted[i] ? 0.55 : 0.9,
                    stroke: hi ? colour('c') : colour('edge'),
                    'stroke-width': hi ? 3 : 1 }, gBars);
      svg('text', { x: cx, y: y - 7, 'text-anchor': 'middle',
                    class: 'lbl' }, gBars).textContent = String(val);
      svg('text', { x: cx, y: Y0 + 15, 'text-anchor': 'middle', class: 'tick' },
          gBars).textContent = String(i);
    }
    clear(gNote);
    svg('text', { x: 64, y: 45, class: 'note', style: 'font-size:12px;fill:var(--ink-2)' },
        gNote).textContent = f.desc;
    svg('text', { x: 796, y: 45, 'text-anchor': 'end', class: 'note' }, gNote)
      .textContent = 'Step ' + cur + ' of ' + (frames.length - 1);
    chipCmp.set(String(f.cmp));
    chipMoves.set(String(f.moves));
    chipStep.set(cur + ' / ' + (frames.length - 1));
    UI.progress(solved ? 1 : 0, 1);
    BRIDGE.readout({ step: cur, comparisons: f.cmp, moves: f.moves, array: f.arr.slice() });
  }

  function setStep(next) {
    if (solved) return;
    cur = clamp(next, 0, frames.length - 1);
    draw();
  }

  function check() {
    if (solved) return;
    var raw = ansIn ? ansIn.value.trim() : '';
    if (!raw) {
      UI.feedback(predict === 'comparisons'
        ? 'Enter the number of comparisons you predict.'
        : 'Enter the array you predict, as comma-separated values.', false);
      return;
    }
    if (predict === 'comparisons') {
      // A comparison count is a whole number. Refusing a blank or non-whole entry here -
      // before `tries` is touched - is what stops a stray keystroke being scored as a
      // wrong answer and counting towards the give-up. parseFloat rather than parseInt so
      // that "2.5" is rejected rather than silently truncated to 2.
      var num = parseFloat(raw);
      if (!isFinite(num) || Math.floor(num) !== num) {
        UI.feedback('Enter a whole number of comparisons.', false);
        return;
      }
      var val = num;
      if (val === answerCount) {
        solved = true; checkBtn.disabled = true;
        UI.feedback('Correct - ' + algoName + ' makes ' + answerCount + ' comparisons on ['
          + arr0.join(', ') + ']. '
          + (algo === 'bubble'
              ? 'Bubble sort compares every adjacent pair once per pass, and the passes '
                + 'shrink by one each time, so it is n(n - 1)/2 = ' + n + ' x ' + (n - 1)
                + ' / 2 = ' + answerCount + ' comparisons whatever the data.'
              : 'Insertion sort compares the key against each element of the sorted prefix '
                + 'until it finds one no larger than the key, or runs out of prefix. The '
                + 'count therefore depends on the data - step through to see where each '
                + 'comparison falls.'),
          true);
        BRIDGE.outcome({ correct: true, task: 'comparisons', algorithm: algo,
                         answer: answerCount, tries: tries + 1,
                         detail: { comparisons: answerCount, moves: lastFrame.moves,
                                   array: arr0.slice() } });
      } else {
        wrong('comparisons', String(answerCount));
      }
      return;
    }
    var nums = raw.split(/[\s,]+/).filter(function (s) { return s.length > 0; })
      .map(function (s) { return parseInt(s, 10); });
    var ok = (nums.length === n);
    if (ok) {
      for (var i = 0; i < n; i++) { if (nums[i] !== answerState[i]) { ok = false; break; } }
    }
    if (ok) {
      solved = true; checkBtn.disabled = true;
      UI.feedback('Correct - after ' + kIndex + ' steps the array is ['
        + answerState.join(', ') + ']. Each step is one comparison; the highlighted bars '
        + 'are the pair being compared, and a swap moves them.', true);
      BRIDGE.outcome({ correct: true, task: 'state_after_k', algorithm: algo,
                       steps: kIndex, answer: answerState.slice(), tries: tries + 1,
                       detail: { steps: kIndex, state: answerState.slice() } });
    } else {
      wrong('state_after_k', '[' + answerState.join(', ') + ']');
    }
  }

  function wrong(kind, answerText) {
    tries += 1;
    if (tries >= MAX_TRIES) {
      solved = true; checkBtn.disabled = true;
      UI.feedback('This is the third try, so here is the answer: ' + answerText + '.', false);
      BRIDGE.outcome({ correct: false, task: kind, algorithm: algo, tries: tries,
                       detail: { answer: answerText, gave_up: true } });
      return;
    }
    if (kind === 'comparisons') {
      UI.feedback('Not yet. Step through with the buttons and watch the Comparisons chip: '
        + 'it counts every pair the algorithm looks at, including the comparison that '
        + 'fails and ends a pass.', false);
    } else {
      UI.feedback('Not yet. Step forward to step ' + kIndex + ' and read the bar heights '
        + 'off the chart - the numbers above the bars are the array at that moment.',
        false);
    }
  }

  document.getElementById('fwd').addEventListener('click', function () { setStep(cur + 1); });
  document.getElementById('back').addEventListener('click', function () { setStep(cur - 1); });
  document.getElementById('reset').addEventListener('click', function () {
    if (solved) return;
    cur = 0; UI.feedback(''); draw();
  });
  checkBtn.addEventListener('click', check);

  if (predict === 'comparisons') {
    document.getElementById('anslabel').textContent = 'Comparisons';
    taskEl.textContent = 'Predict the comparison count for [' + arr0.join(', ') + '].';
  } else {
    document.getElementById('anslabel').textContent = 'Array after ' + kIndex + ' steps';
    taskEl.textContent = 'State the array after ' + kIndex + ' steps.';
  }
  draw();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


STEP_ALGORITHM = Archetype(
    id='step_algorithm',
    title='Step the algorithm',
    blurb='Step through a sorting algorithm one comparison at a time, then predict its '
          'behaviour.',
    interaction='step forward and back through a sort, then commit to a prediction',
    subjects=('mathematics',),
    tags=('algorithms', 'sorting', 'computational-thinking', 'big-o', 'trace'),
    reference='Comparison sorting algorithms; algorithm efficiency and Big-O',
    telemetry='One outcome per committed prediction: the comparison count or the array '
              'state the learner entered, the algorithm, and the tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('array', 'list', 'The array to sort, as whole numbers. Two to ten values.',
              minimum_items=2, maximum_items=10),
        Field('algorithm', 'text', 'Which sorting algorithm to step through.',
              choices=('insertion', 'bubble')),
        Field('predict', 'text',
              'comparisons: predict the total comparison count. state_after_k: predict the '
              'array after k steps.', choices=('comparisons', 'state_after_k')),
        Field('k', 'int', 'How many steps ahead to predict, for state_after_k.',
              required=False, minimum=0, maximum=200),
        Field('seed', 'int', 'Seeds any variation between games.', minimum=0, maximum=1000000000),
    ),
    body=_body_step,
    engine=lambda spec: _ENGINE_STEP,
)


#: Every archetype in this module, in declaration order.
MATH_B_ARCHETYPES = (AREA_MODEL, PROBABILITY_LAB, PATTERN_SEQUENCE, STEP_ALGORITHM)
