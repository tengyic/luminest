"""Mathematics archetypes, set A: the linear-functions and equation family.

Four reusable interactions, all variations on the ``curve_shift`` pattern in
:mod:`app.harness.playground.archetypes_core`:

``plot_points``
    Place points on a coordinate grid so they satisfy a stated rule ``y = mx + c``.
    This is the Amplify Desmos linear-functions activity in archetype form: the
    learner drags points, commits with Check, and the line is drawn only once the
    commitment is right (or after three tries).

``function_machine``
    An input -> output machine. Feed it inputs, watch the table build, then commit
    to the rule - chosen from offered candidates or entered as slope and intercept.

``number_line``
    Place a value (fraction, decimal, integer or inequality boundary) on a number
    line, snapping to tick subdivisions; also compare two values and mark the
    direction of an inequality.

``balance_scale``
    Solve ``ax + b = c`` by keeping a two-pan balance level. Every move must be made
    to both pans; the scale tilts the moment one side is changed alone, which is the
    misconception the game is built to expose.

Every archetype obeys the runtime's evidence rule: dragging is exploration and only
produces ``luminfest:readout``; pressing Check is the commitment and produces exactly one
``luminfest:outcome`` per task. Feedback names what is wrong and what the rule requires,
and each task reveals its answer after three tries rather than letting a learner grind.
"""

from __future__ import annotations

from typing import Any, Mapping

from .archetypes import Archetype, Field

#: Three tries, then the game shows the answer. Same policy as ``curve_shift``.
_MAX_TRIES = 3


# ===================================================================== plot_points


def _plot_points_body(spec: Mapping[str, Any]) -> str:
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        'aria-label="A coordinate grid on which to plot points that satisfy a rule" '
        'data-series="plot-points"></svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="rule"></span>'
        '<span class="spacer"></span>'
        '<button id="clear">Clear points</button>'
        '<button class="primary" id="check">Check</button>'
        '</div>'
        '</div>')


_PLOT_POINTS_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 44;
  var xmin = +spec.x_min, xmax = +spec.x_max;
  var ymin = +spec.y_min, ymax = +spec.y_max;
  var step = +spec.step || 1;
  var need = clamp(Math.round(+spec.required_points || 3), 2, 6);
  var m = +spec.m, c = +spec.c;
  var mode = spec.mode || 'line';
  var rule = spec.rule_label || 'the rule';
  var TOL = 1e-6;
  var toX = scale([xmin, xmax], [X0, X1]);
  var toY = scale([ymin, ymax], [Y0, Y1]);
  var state = { tries: 0, solved: false };

  document.getElementById('rule').textContent = 'Rule: ' + rule;

  var defs = svg('defs', null, scene);
  var cp = svg('clipPath', { id: 'plotclip' }, defs);
  svg('rect', { x: X0, y: Y1, width: X1 - X0, height: Y0 - Y1 }, cp);

  var gGrid = svg('g', null, scene);
  (function () {
    var x = Math.ceil(xmin / step) * step, guard = 0;
    while (x <= xmax + 1e-9 && guard < 240) {
      svg('line', { x1: toX(x), x2: toX(x), y1: Y0, y2: Y1, class: 'gridline' }, gGrid);
      x += step; guard += 1;
    }
    var y = Math.ceil(ymin / step) * step; guard = 0;
    while (y <= ymax + 1e-9 && guard < 240) {
      svg('line', { x1: X0, x2: X1, y1: toY(y), y2: toY(y), class: 'gridline' }, gGrid);
      y += step; guard += 1;
    }
  })();

  var axX = clamp(toX(0), X0, X1), axY = clamp(toY(0), Y1, Y0);
  var gAxes = svg('g', null, scene);
  svg('line', { x1: X0, x2: X1, y1: axY, y2: axY, class: 'axis' }, gAxes);
  svg('line', { x1: axX, x2: axX, y1: Y0, y2: Y1, class: 'axis' }, gAxes);
  for (var lx = Math.ceil(xmin); lx <= xmax; lx += 1) {
    if (lx === 0 && xmin <= 0 && xmax >= 0) continue;
    svg('text', { x: toX(lx), y: axY + 15, 'text-anchor': 'middle', class: 'tick' },
        gAxes).textContent = lx;
  }
  for (var ly = Math.ceil(ymin); ly <= ymax; ly += 1) {
    if (ly === 0 && ymin <= 0 && ymax >= 0) continue;
    svg('text', { x: axX - 7, y: toY(ly) + 3.5, 'text-anchor': 'end', class: 'tick' },
        gAxes).textContent = ly;
  }
  // Axis names in the gutters, so the numbers have something to belong to.
  svg('text', { x: X1 + 12, y: axY + 4, 'text-anchor': 'start', class: 'note' },
      gAxes).textContent = 'x';
  svg('text', { x: axX - 26, y: Y1 - 8, 'text-anchor': 'middle', class: 'note' },
      gAxes).textContent = 'y';

  var gLine = svg('g', null, scene);
  gLine.setAttribute('clip-path', 'url(#plotclip)');
  var ruleLine = svg('line', { stroke: colour('c'), 'stroke-width': 2.6,
                               'stroke-dasharray': '7 5', opacity: 0 }, gLine);

  var gHandles = svg('g', { 'data-series': 'points' }, scene);
  var trayY = 424, trayX0 = 300, trayGap = 46;
  // The tray is a shelf, not a void: the handles sit on it at rest, so it is obvious
  // that they are pieces you pick up rather than dots drawn on the page.
  var shelfX0 = trayX0 - 26, shelfX1 = trayX0 + (need - 1) * trayGap + 26;
  var shelf = svg('rect', { x: shelfX0, y: trayY - 24, width: shelfX1 - shelfX0,
                            height: 48, rx: 24,
                            fill: colour('surface2'), stroke: colour('line'),
                            'stroke-width': 1.2 }, gHandles);
  var handles = [];
  for (var i = 0; i < need; i += 1) {
    var hg = svg('g', { 'pointer-events': 'none' }, gHandles);
    var hsh = svg('circle', { cx: 0, cy: 2.5, r: 15.5, fill: 'rgba(36,49,42,.15)' }, hg);
    var hring = svg('circle', { cx: 0, cy: 0, r: 15, fill: colour('card') }, hg);
    var hc = svg('circle', { r: 12, fill: colour('a-soft'), stroke: colour('a'),
                             'stroke-width': 1.8 }, hg);
    var hl = svg('text', { 'text-anchor': 'middle', 'pointer-events': 'none',
                           fill: colour('a'),
                           style: 'font-size:12.5px;font-weight:700' }, hg);
    hl.textContent = String.fromCharCode(65 + i);
    hl.setAttribute('y', '4.5');
    handles.push({ x: 0, y: 0, placed: false, dragging: false, g: hg, circ: hc,
                   letter: hl, coord: null, trayX: trayX0 + i * trayGap, trayY: trayY });
  }
  svg('text', { x: X0, y: trayY + 4, class: 'note', 'text-anchor': 'start' },
      gHandles).textContent = 'Drag each point onto the grid.';

  var layer = svg('rect', { x: 0, y: 0, width: 860, height: 460, fill: 'transparent',
                            'pointer-events': 'all', class: 'grab' }, scene);

  function snap(v) { return Math.round(v / step) * step; }
  function placedList() {
    return handles.filter(function (h) { return h.placed; });
  }
  function pts(list) {
    return list.map(function (h) { return [+h.x.toFixed(3), +h.y.toFixed(3)]; });
  }

  // A readout of what is on the grid. The coordinate labels follow the points, but
  // they are small and can crowd each other near an axis; this line is where the
  // learner checks how many they have committed without hunting for the labels.
  var placedText = svg('text', { x: 812, y: 30, 'text-anchor': 'end',
      fill: colour('dim'),
      style: 'font-size:11.5px;font-weight:550;font-variant-numeric:tabular-nums' },
      scene);
  placedText.textContent = '0 of ' + need + ' points placed';

  function draw() {
    var inTray = 0;
    handles.forEach(function (h, i) {
      var px, py;
      if (h.placed || h.dragging) { px = toX(h.x); py = toY(h.y); }
      else { px = h.trayX; py = h.trayY; inTray += 1; }
      h.g.setAttribute('transform', 'translate(' + px + ',' + py + ')');
      var letter = String.fromCharCode(65 + i);
      if (h.placed || h.dragging) {
        if (!h.coord) {
          h.coord = svg('text', { 'text-anchor': 'middle', 'pointer-events': 'none',
              fill: colour('ink'),
              style: 'font-size:11.5px;font-weight:650;font-variant-numeric:tabular-nums' },
              h.g);
        }
        h.coord.textContent = '(' + fmt(h.x, 0) + ', ' + fmt(h.y, 0) + ')';
        h.coord.setAttribute('x', 0);
        h.coord.setAttribute('y', -21);
        h.circ.setAttribute('fill', colour('a'));
        h.circ.setAttribute('stroke', '#fff');
        h.circ.setAttribute('stroke-width', 2.4);
        h.letter.setAttribute('fill', '#fff');
      } else {
        if (h.coord) { h.g.removeChild(h.coord); h.coord = null; }
        h.circ.setAttribute('fill', colour('a-soft'));
        h.circ.setAttribute('stroke', colour('a'));
        h.circ.setAttribute('stroke-width', 1.8);
        h.letter.setAttribute('fill', colour('a'));
      }
    });
    var placed = placedList();
    // An empty shelf is a leftover, not an affordance: show it only while there is
    // something on it to pick up.
    shelf.setAttribute('display', inTray ? 'inline' : 'none');
    placedText.textContent = placed.length + ' of ' + need + ' points placed';
    BRIDGE.readout({ placed: placed.length, need: need, points: pts(placed) });
  }

  var held = null;
  drag(layer, {
    start: function (pt) {
      if (state.solved) return false;
      var best = -1, bestD = 28 * 28;
      handles.forEach(function (h, idx) {
        var px = (h.placed || h.dragging) ? toX(h.x) : h.trayX;
        var py = (h.placed || h.dragging) ? toY(h.y) : h.trayY;
        var dx = pt.x - px, dy = pt.y - py, d = dx * dx + dy * dy;
        if (d < bestD) { bestD = d; best = idx; }
      });
      if (best < 0) return false;
      held = best;
      return { i: best };
    },
    move: function (pt) {
      if (held === null) return;
      var h = handles[held];
      h.dragging = true;
      h.placed = true;
      h.x = snap(toX.invert(clamp(pt.x, X0, X1)));
      h.y = snap(toY.invert(clamp(pt.y, Y1, Y0)));
      draw();
    },
    end: function () {
      if (held === null) return;
      handles[held].dragging = false;
      held = null;
      draw();
    }
  });

  function subst(x) {
    var ms;
    if (m === 1) ms = 'x';
    else if (m === -1) ms = '−x';
    else ms = fmt(m, 0) + 'x';
    ms = ms.replace('x', '(' + fmt(x, 0) + ')');
    var cs = c < 0 ? ' − ' + fmt(Math.abs(c), 0) : (c > 0 ? ' + ' + fmt(c, 0) : '');
    return ms + cs;
  }

  function showLine() {
    ruleLine.setAttribute('x1', toX(xmin));
    ruleLine.setAttribute('y1', toY(m * xmin + c));
    ruleLine.setAttribute('x2', toX(xmax));
    ruleLine.setAttribute('y2', toY(m * xmax + c));
    ruleLine.setAttribute('opacity', 0.95);
  }
  function lock() {
    document.getElementById('check').disabled = true;
    document.getElementById('clear').disabled = true;
  }

  function succeed(placed) {
    state.solved = true;
    showLine();
    var s0 = placed[0];
    UI.feedback('Correct. Every point lies on ' + rule + ' — at x = ' + fmt(s0.x, 0)
      + ', ' + subst(s0.x) + ' = ' + fmt(m * s0.x + c, 0)
      + ', which is exactly where your point sits. The line through them is drawn.', true);
    BRIDGE.outcome({ correct: true, mode: mode, tries: state.tries + 1,
                     points: pts(placed),
                     detail: { rule: rule, m: m, c: c } });
    lock();
  }

  function reveal() {
    state.solved = true;
    showLine();
    var xs = [];
    if (mode === 'intercept_and_point') {
      xs = [0, 1];
    } else {
      for (var xi = Math.ceil(xmin); xi <= xmax && xs.length < need; xi += 1) {
        var yy = m * xi + c;
        if (yy >= ymin && yy <= ymax) xs.push(xi);
      }
      if (!xs.length) xs = [0];
    }
    handles.forEach(function (h, idx) {
      h.placed = true;
      h.dragging = false;
      h.x = xs[Math.min(idx, xs.length - 1)];
      h.y = m * h.x + c;
    });
    draw();
    UI.feedback('That is three tries, so here is the line: ' + rule + '. At x = 0 it gives y = '
      + fmt(c, 0) + ', and each step of 1 to the right changes y by ' + fmt(m, 0)
      + '. Points are placed on it for you.', false);
    BRIDGE.outcome({ correct: false, mode: mode, tries: state.tries,
                     detail: { rule: rule, m: m, c: c, gave_up: true } });
    lock();
  }

  function check() {
    if (state.solved) return;
    var placed = placedList();
    if (placed.length < need) {
      UI.feedback('Place all ' + need + ' points on the grid first — ' + placed.length
        + ' of ' + need + ' so far.', false);
      return;
    }
    var wrong = null;
    for (var i = 0; i < placed.length; i += 1) {
      var h = placed[i], want = m * h.x + c;
      if (Math.abs(h.y - want) > TOL) { wrong = { h: h, want: want }; break; }
    }
    var hasIntercept = placed.some(function (h) { return Math.abs(h.x) < TOL; });
    var modeOk = (mode !== 'intercept_and_point') || hasIntercept;
    if (!wrong && modeOk) { succeed(placed); return; }
    state.tries += 1;
    if (state.tries >= __MAX_TRIES__) { reveal(); return; }
    if (wrong) {
      UI.feedback('Not yet. At x = ' + fmt(wrong.h.x, 0) + ', ' + rule + ' gives y = '
        + fmt(wrong.want, 0) + ' because ' + subst(wrong.h.x) + ' = ' + fmt(wrong.want, 0)
        + ', but your point sits at y = ' + fmt(wrong.h.y, 0) + '. Move point '
        + String.fromCharCode(65 + handles.indexOf(wrong.h)) + ' '
        + (wrong.h.y < wrong.want ? 'up' : 'down') + ' until it is on the line.', false);
    } else {
      UI.feedback('Every point is on the line, but this task also asks for the y-intercept: '
        + 'place one point at x = 0, where the line crosses the y-axis.', false);
    }
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('clear').addEventListener('click', function () {
    if (state.solved) return;
    handles.forEach(function (h) { h.placed = false; h.dragging = false; });
    draw();
    UI.feedback('');
  });

  draw();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


PLOT_POINTS = Archetype(
    id='plot_points',
    title='Plot the points',
    blurb='Drag points onto a coordinate grid so that they all satisfy one rule.',
    interaction='drag points onto a grid and commit to a line',
    subjects=('mathematics',),
    tags=('coordinate-grid', 'linear-functions', 'plotting', 'slope', 'graphs'),
    reference='Amplify Desmos linear-functions activity set; Math Playground graphing games',
    telemetry='One outcome per committed rule: whether every placed point satisfied y = mx + c, '
              'the mode, the point coordinates, and the tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('rule_label', 'text', 'How the rule is written for the learner, e.g. "y = 2x − 1".'),
        Field('m', 'float', 'The slope of the rule y = mx + c.', minimum=-20, maximum=20),
        Field('c', 'float', 'The y-intercept of the rule y = mx + c.', minimum=-50, maximum=50),
        Field('x_min', 'float', 'Left edge of the grid.', minimum=-50, maximum=50),
        Field('x_max', 'float', 'Right edge of the grid.', minimum=-50, maximum=50),
        Field('y_min', 'float', 'Bottom edge of the grid.', minimum=-50, maximum=50),
        Field('y_max', 'float', 'Top edge of the grid.', minimum=-50, maximum=50),
        Field('step', 'float', 'Grid spacing the points snap to.', minimum=0.25, maximum=5),
        Field('required_points', 'int', 'How many points must be placed.',
              minimum=2, maximum=6),
        Field('mode', 'text', 'What the task asks for.',
              choices=('line', 'intercept_and_point')),
    ),
    body=_plot_points_body,
    engine=lambda spec: _PLOT_POINTS_ENGINE,
    # 860x460 is what the correctness oracle's grid arithmetic assumes; the drawing
    # uses the whole box rather than shrinking the grid to fit a shorter one.
    height=460,
)


# ================================================================ function_machine


def _function_machine_body(spec: Mapping[str, Any]) -> str:
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 515" role="img" '
        'aria-label="An input-output machine that turns each input into an output" '
        'data-series="function-machine"></svg>'
        '</div>'
        '<div class="controls" id="feedbar"></div>'
        '<div class="controls" id="answerbar"></div>'
        '<div class="controls">'
        '<span class="spacer"></span>'
        '<button id="reset">Reset</button>'
        '<button class="primary" id="check">Check</button>'
        '</div>'
        '</div>')


_FUNCTION_MACHINE_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var m = +spec.m, c = +spec.c;
  var inputs = (spec.inputs || []).map(function (v) { return +v; });
  var mode = spec.answer_mode || 'choices';
  var state = { fed: [], tries: 0, solved: false, pick: null };

  function f(x) { return m * x + c; }
  function ruleText(mm, cc) {
    if (mm === 0) return 'y = ' + fmt(cc, 0);
    var s = 'y = ';
    if (mm === 1) s += 'x';
    else if (mm === -1) s += '−x';
    else s += fmt(mm, 0) + 'x';
    if (cc > 0) s += ' + ' + fmt(cc, 0);
    else if (cc < 0) s += ' − ' + fmt(Math.abs(cc), 0);
    return s;
  }

  var gMachine = svg('g', { 'data-series': 'machine' }, scene);
  svg('rect', { x: 170, y: 30, width: 520, height: 214, rx: 22,
                fill: colour('surface2'), stroke: colour('line'),
                'stroke-width': 1.5 }, gMachine);
  svg('text', { x: 198, y: 58, fill: colour('faint'),
                style: 'font-size:10px;font-weight:700;letter-spacing:.15em' },
      gMachine).textContent = 'FUNCTION MACHINE';
  // The machine's plate: the rule the learner is trying to name. It starts as
  // "y = ?" - the shape of the answer - and becomes the rule when they commit.
  var midText = svg('text', { x: 430, y: 106, 'text-anchor': 'middle',
      fill: colour('ink'), style: 'font-size:18px;font-weight:650' }, gMachine);
  midText.textContent = 'y = ?';

  svg('line', { x1: 296, x2: 556, y1: 172, y2: 172, stroke: colour('faint'),
                'stroke-width': 2.4, 'stroke-linecap': 'round' }, gMachine);
  svg('path', { d: 'M552 164 L566 172 L552 180 Z', fill: colour('faint') }, gMachine);

  svg('circle', { cx: 250, cy: 174, r: 42, fill: 'rgba(36,49,42,.10)' }, gMachine);
  svg('circle', { cx: 610, cy: 174, r: 42, fill: 'rgba(36,49,42,.10)' }, gMachine);
  svg('circle', { cx: 250, cy: 172, r: 42, fill: colour('a') }, gMachine);
  svg('circle', { cx: 610, cy: 172, r: 42, fill: colour('c') }, gMachine);
  var inPort = svg('text', { x: 250, y: 180, 'text-anchor': 'middle', fill: '#fff',
      style: 'font-size:20px;font-weight:700;font-variant-numeric:tabular-nums' }, gMachine);
  var outPort = svg('text', { x: 610, y: 180, 'text-anchor': 'middle', fill: '#fff',
      style: 'font-size:20px;font-weight:700;font-variant-numeric:tabular-nums' }, gMachine);
  inPort.textContent = 'x';
  outPort.textContent = '?';
  svg('text', { x: 250, y: 234, 'text-anchor': 'middle', fill: colour('dim'),
                style: 'font-size:11.5px' }, gMachine).textContent = 'input';
  svg('text', { x: 610, y: 234, 'text-anchor': 'middle', fill: colour('dim'),
                style: 'font-size:11.5px' }, gMachine).textContent = 'output';

  // The table is one column per offered input, so it grows sideways and never
  // runs out of room however many inputs the spec offers.
  var gTable = svg('g', { 'data-series': 'table' }, scene);
  svg('rect', { x: 60, y: 264, width: 740, height: 222, rx: 18,
                fill: colour('surface2'), stroke: colour('line'),
                'stroke-width': 1.2 }, gTable);
  svg('text', { x: 88, y: 292, fill: colour('faint'),
                style: 'font-size:10px;font-weight:700;letter-spacing:.15em' },
      gTable).textContent = 'OUTPUT TABLE';
  svg('text', { x: 88, y: 358, fill: colour('dim'),
                style: 'font-size:15px;font-weight:650' }, gTable).textContent = 'x';
  svg('text', { x: 88, y: 416, fill: colour('dim'),
                style: 'font-size:15px;font-weight:650' }, gTable).textContent = 'f(x)';
  svg('line', { x1: 150, x2: 150, y1: 310, y2: 432, stroke: colour('line'),
                'stroke-width': 1.2 }, gTable);
  svg('text', { x: 88, y: 460, fill: colour('dim'), style: 'font-size:11.5px' },
      gTable).textContent =
    'The slope m is the change in f(x) per step of 1 in x; the intercept c is f(0).';

  var cells = [];
  (function () {
    var n = Math.max(1, inputs.length);
    var gap = n > 1 ? (770 - 186) / (n - 1) : 0;
    for (var i = 0; i < n; i += 1) {
      var cx = 186 + i * gap;
      svg('text', { x: cx, y: 358, 'text-anchor': 'middle', fill: colour('ink'),
          style: 'font-size:20px;font-weight:650;font-variant-numeric:tabular-nums' },
          gTable).textContent = fmt(inputs[i], 0);
      var out = svg('text', { x: cx, y: 416, 'text-anchor': 'middle',
          fill: colour('faint'),
          style: 'font-size:20px;font-weight:700;font-variant-numeric:tabular-nums' },
          gTable);
      out.textContent = '\u2013';
      cells.push(out);
    }
  })();

  var answerbar = document.getElementById('answerbar');
  var feedbar = document.getElementById('feedbar');
  var choiceButtons = [];

  function enableAnswer() {
    if (state.solved || state.fed.length < 2) return;
    choiceButtons.forEach(function (b) { b.disabled = false; });
    document.getElementById('check').disabled = false;
  }

  function addRow(x) {
    var i = inputs.indexOf(x);
    if (i < 0 || !cells[i]) return;
    cells[i].textContent = fmt(f(x), 0);
    cells[i].setAttribute('fill', colour('c'));
  }

  function feed(x) {
    if (state.solved) return;
    if (state.fed.indexOf(x) >= 0) {
      UI.feedback('You already fed x = ' + fmt(x, 0) + '. Try a different input.', false);
      return;
    }
    state.fed.push(x);
    addRow(x);
    inPort.textContent = fmt(x, 0);
    outPort.textContent = fmt(f(x), 0);
    UI.feedback('Fed x = ' + fmt(x, 0) + ' \u2192 f(x) = ' + fmt(f(x), 0)
      + '. Feed at least two inputs, then commit to the rule.', true);
    enableAnswer();
    BRIDGE.readout({ fed: state.fed.length, last_input: x, last_output: f(x) });
  }

  function verifyLine() {
    if (!state.fed.length) return '';
    var x0 = state.fed[0];
    return 'For x = ' + fmt(x0, 0) + ', f(x) = ' + fmt(f(x0), 0)
      + ', which is exactly what the machine produced.';
  }
  function testLine(gm, gc) {
    if (!state.fed.length) return '';
    var x0 = state.fed[0];
    return 'Your rule gives f(' + fmt(x0, 0) + ') = ' + fmt(gm * x0 + gc, 0)
      + ', but the machine gave ' + fmt(f(x0), 0) + '.';
  }

  function succeed() {
    state.solved = true;
    document.getElementById('check').disabled = true;
    midText.textContent = ruleText(m, c);
    midText.setAttribute('fill', colour('good'));
    UI.feedback('Correct — the rule is ' + ruleText(m, c) + '. ' + verifyLine()
      + ' In slope-intercept form y = mx + c, the slope m = ' + fmt(m, 0)
      + ' is the change in f(x) each time x rises by 1, and c = ' + fmt(c, 0)
      + ' is f(0).', true);
    BRIDGE.outcome({ correct: true, tries: state.tries + 1, m: m, c: c,
                     detail: { rule: ruleText(m, c), answer_mode: mode } });
  }
  function reveal() {
    state.solved = true;
    document.getElementById('check').disabled = true;
    midText.textContent = ruleText(m, c);
    midText.setAttribute('fill', colour('good'));
    UI.feedback('That is three tries, so here is the rule: ' + ruleText(m, c) + '. '
      + verifyLine() + ' In y = mx + c, m = ' + fmt(m, 0) + ' is the change in f(x) per unit '
      + 'of x, and c = ' + fmt(c, 0) + ' is the output when the input is 0.', false);
    BRIDGE.outcome({ correct: false, tries: state.tries,
                     detail: { rule: ruleText(m, c), answer_mode: mode, gave_up: true } });
  }

  function check() {
    if (state.solved) return;
    if (state.fed.length < 2) {
      UI.feedback('Feed the machine at least two different inputs first, so you have '
        + 'something to reason from.', false);
      return;
    }
    var gm, gc;
    if (mode === 'slope_intercept') {
      var em = document.getElementById('in_m').value;
      var ec = document.getElementById('in_c').value;
      if (em === '' || ec === '') {
        UI.feedback('Enter both the slope m and the y-intercept c.', false);
        return;
      }
      gm = +em; gc = +ec;
    } else {
      if (!state.pick) {
        UI.feedback('Choose one of the rules first.', false);
        return;
      }
      gm = state.pick.m; gc = state.pick.c;
    }
    if (Math.abs(gm - m) < 1e-6 && Math.abs(gc - c) < 1e-6) { succeed(); return; }
    state.tries += 1;
    if (state.tries >= __MAX_TRIES__) { reveal(); return; }
    UI.feedback('Not that rule. ' + testLine(gm, gc) + ' Look again at how f(x) changes each '
      + 'time x goes up by 1 — that change is the slope.', false);
  }

  function buildAnswer() {
    if (mode === 'slope_intercept') {
      var lm = el('label', { class: 'fld' }, answerbar);
      lm.appendChild(document.createTextNode('slope m'));
      el('input', { type: 'number', id: 'in_m', step: 'any', 'aria-label': 'slope m' }, lm);
      var lc = el('label', { class: 'fld' }, answerbar);
      lc.appendChild(document.createTextNode('y-intercept c'));
      el('input', { type: 'number', id: 'in_c', step: 'any', 'aria-label': 'y-intercept c' }, lc);
      return;
    }
    var cands = [[m, c], [c, m], [m, -c], [-m, c], [m + 1, c], [m, c + 1]];
    var correctKey = ruleText(m, c);
    var seen = {}, pool = [];
    cands.forEach(function (p) {
      var key = ruleText(p[0], p[1]);
      if (key !== correctKey && !seen[key]) { seen[key] = 1; pool.push({ m: p[0], c: p[1], label: key }); }
    });
    var seed = Math.abs(Math.round(m * 97 + c * 13)) + 11;
    pool = shuffle(pool, seed);
    var four = [{ m: m, c: c, label: correctKey }].concat(pool.slice(0, 3));
    four = shuffle(four, seed + 3);
    four.forEach(function (o) {
      var b = el('button', { type: 'button', class: 'choice' }, answerbar);
      b.textContent = o.label;
      b.addEventListener('click', function () {
        if (state.solved) return;
        state.pick = o;
        choiceButtons.forEach(function (bb) { bb.classList.remove('primary'); });
        b.classList.add('primary');
      });
      choiceButtons.push(b);
    });
  }

  inputs.forEach(function (x) {
    var b = el('button', { type: 'button' }, feedbar);
    b.textContent = 'Feed x = ' + fmt(x, 0);
    b.addEventListener('click', function () { feed(x); });
  });

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    if (state.solved) return;
    state.fed = [];
    state.tries = 0;
    state.pick = null;
    cells.forEach(function (t) {
      t.textContent = '\u2013';
      t.setAttribute('fill', colour('faint'));
    });
    inPort.textContent = 'x';
    outPort.textContent = '?';
    midText.textContent = 'y = ?';
    midText.setAttribute('fill', colour('ink'));
    choiceButtons.forEach(function (b) { b.classList.remove('primary'); b.disabled = true; });
    document.getElementById('check').disabled = true;
    UI.feedback('');
  });

  buildAnswer();
  choiceButtons.forEach(function (b) { b.disabled = true; });
  document.getElementById('check').disabled = true;
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


FUNCTION_MACHINE = Archetype(
    id='function_machine',
    title='Guess the rule',
    blurb='Feed inputs into the machine, watch the outputs, then work out the rule.',
    interaction='feed inputs and guess the rule behind the outputs',
    subjects=('mathematics',),
    tags=('functions', 'input-output', 'slope', 'tables', 'patterns'),
    reference='Math Playground function machine; Desmos function-machine activities',
    telemetry='One outcome per committed guess: whether the guessed rule matched y = mx + c, '
              'how many inputs were fed, and the tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('m', 'float', 'The slope of the hidden rule y = mx + c.', minimum=-20, maximum=20),
        Field('c', 'float', 'The y-intercept of the hidden rule y = mx + c.',
              minimum=-50, maximum=50),
        Field('inputs', 'list', 'The input values offered to feed the machine.',
              minimum_items=3, maximum_items=8),
        Field('answer_mode', 'text', 'How the learner commits to a rule.',
              choices=('choices', 'slope_intercept')),
    ),
    body=_function_machine_body,
    engine=lambda spec: _FUNCTION_MACHINE_ENGINE,
    # The machine, the table and the hint all stack above two rows of HTML controls,
    # so the stage's drawing area is shorter than a full-height game's; 860x515 is
    # that box's aspect, which keeps the drawing from letterboxing inside it.
    height=515,
)


# =================================================================== number_line


def _number_line_body(spec: Mapping[str, Any]) -> str:
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 600" role="img" '
        'aria-label="A number line on which to place a value" data-series="number-line">'
        '</svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="tasklabel"></span>'
        '<span class="spacer"></span>'
        '<button id="left">◀ shade left</button>'
        '<button id="right">shade right ▶</button>'
        '<button id="cmpA">A is larger</button>'
        '<button id="cmpB">B is larger</button>'
        '<button id="reset">Reset</button>'
        '<button class="primary" id="check">Check</button>'
        '<button id="next" class="hidden">Next task</button>'
        '</div>'
        '</div>')


_NUMBER_LINE_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  // The value -> pixel mapping is fixed at 78..812: the correctness oracle derives its
  // drop point from these bounds, so the drawing may move but the scale may not.
  var X0 = 78, X1 = 812, TOP = 300, BOT = 326, KNOB = 313;
  var vmin = +spec.min, vmax = +spec.max;
  var sub = clamp(Math.round(+spec.subdivisions || 1), 1, 10);
  var tolTicks = +spec.tol_ticks || 0.4;
  var tasks = spec.tasks || [];
  var toX = scale([vmin, vmax], [X0, X1]);
  var pxPerTick = (X1 - X0) / (vmax - vmin) / sub;
  var state = { index: 0, tries: 0, solved: false, posA: null, posB: null,
                dir: null, cmp: null };

  scene.setAttribute('aria-label',
    'A number line from ' + vmin + ' to ' + vmax + ' in steps of 1/' + sub);

  // ---- number formatting ---------------------------------------------------
  // Every number on this page is read while dragging, so every number is tabular
  // and every minus is a true minus sign rather than a hyphen.
  function gcd(a, b) {
    a = Math.abs(a); b = Math.abs(b);
    while (b) { var t = a % b; a = b; b = t; }
    return a || 1;
  }
  function dec(v) {
    var s = (+v).toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
    if (s === '' || s === '-0') s = '0';
    return s.replace('-', '\u2212');
  }
  function frac(v) {
    var n = Math.round(v * sub), d = sub, g = gcd(n, d);
    n /= g; d /= g;
    if (d === 1) return (n < 0 ? '\u2212' : '') + Math.abs(n);
    return (n < 0 ? '\u2212' : '') + Math.abs(n) + '/' + d;
  }
  // "as a fraction: 11/8" when there is a fraction to show; a whole number needs
  // no restating, so it gets a plain note instead.
  function fracNote(v) {
    var f = frac(v);
    return f.indexOf('/') >= 0 ? 'as a fraction: ' + f : 'a whole number';
  }
  // The same number as a mixed number, so 7/4 also reads as "1 and 3/4".
  function mixed(v) {
    var neg = v < 0, a = Math.abs(v);
    var w = Math.floor(a + 1e-9), rem = a - w;
    if (rem < 1e-9) return dec(v);
    var n = Math.round(rem * sub), d = sub, g = gcd(n, d);
    n /= g; d /= g;
    return (neg ? '\u2212' : '') + (w ? w + ' and ' : '') + n + '/' + d;
  }

  var UNIT_WORD = { 2: 'halves', 3: 'thirds', 4: 'quarters', 5: 'fifths',
                    8: 'eighths', 10: 'tenths' };
  var unitWord = UNIT_WORD[sub] || 'ticks';

  // ---- the target card -----------------------------------------------------
  // What the task asks for, in three equivalent forms, plus a key that says how
  // the line is divided. Neither of those tells the learner where to drop the
  // marker - the conversion from 7/4 to a position is the exercise.
  var gCard = svg('g', { 'data-series': 'target' }, scene);
  svg('rect', { x: 40, y: 16, width: 780, height: 150, rx: 18,
                fill: colour('surface2'), stroke: colour('line'),
                'stroke-width': 1.2 }, gCard);
  svg('text', { x: 64, y: 46, fill: colour('faint'),
                style: 'font-size:10px;font-weight:700;letter-spacing:.15em' },
      gCard).textContent = 'TARGET VALUE';
  var targetBig = svg('text', { x: 64, y: 104, fill: colour('ink'),
      style: 'font-size:40px;font-weight:700;font-variant-numeric:tabular-nums' },
      gCard);
  var targetSub = svg('text', { x: 64, y: 140, fill: colour('dim'),
      style: 'font-size:12px' }, gCard);

  var LX0 = 520, LX1 = 796, LY0 = 58, LH = 28;
  svg('text', { x: LX1, y: 46, 'text-anchor': 'end', fill: colour('faint'),
                style: 'font-size:10px;font-weight:700;letter-spacing:.15em' },
      gCard).textContent = 'TICK SCALE';
  var cellW = (LX1 - LX0) / sub;
  for (var ci = 0; ci < sub; ci += 1) {
    svg('rect', { x: LX0 + ci * cellW, y: LY0, width: cellW, height: LH,
                  fill: colour('card'), stroke: colour('edge'),
                  'stroke-width': 1 }, gCard);
  }
  svg('text', { x: LX1, y: 116, 'text-anchor': 'end', fill: colour('dim'),
                style: 'font-size:11px' }, gCard).textContent =
    '1 unit = ' + sub + ' ' + unitWord;

  // ---- the track -----------------------------------------------------------
  // A real band rather than a hairline: the line is a thing the marker sits on.
  var gTrack = svg('g', null, scene);
  svg('rect', { x: X0 - 2, y: TOP, width: X1 - X0 + 4, height: BOT - TOP,
                rx: 9, fill: colour('surface3'), stroke: colour('line'),
                'stroke-width': 1 }, gTrack);
  var gShade = svg('g', { 'data-series': 'shade' }, scene);

  var gTicks = svg('g', null, scene);
  var totalTicks = Math.round((vmax - vmin) * sub);
  for (var i = 0; i <= totalTicks; i += 1) {
    var v = vmin + i / sub;
    var isInt = Math.abs(v - Math.round(v)) < 1e-9;
    svg('line', { x1: toX(v), x2: toX(v), y1: isInt ? TOP : TOP + 7, y2: BOT,
                  stroke: isInt ? colour('ink') : colour('faint'),
                  'stroke-width': isInt ? 2 : 1.2,
                  'stroke-linecap': 'round' }, gTicks);
    if (isInt) {
      svg('text', { x: toX(v), y: 352, 'text-anchor': 'middle',
                    fill: colour('ink'),
                    style: 'font-size:13px;font-weight:650;font-variant-numeric:tabular-nums' },
          gTicks).textContent = String(Math.round(v)).replace('-', '\u2212');
    }
  }

  // ---- the handles ---------------------------------------------------------
  // Visible at rest, on the track, 15px white ring over a soft shadow: the thing
  // you are meant to grab is the first thing you see.
  var gMark = svg('g', { 'data-series': 'marker' }, scene);
  function mkPin(col, letter, bubbleY) {
    var g = svg('g', { 'pointer-events': 'none' }, gMark);
    svg('rect', { x: -1.2, y: bubbleY + 34, width: 2.4, height: TOP + 2 - bubbleY - 34,
                  rx: 1.2, fill: col, opacity: 0.45 }, g);
    svg('circle', { cx: 0, cy: KNOB + 3, r: 16, fill: 'rgba(36,49,42,.16)' }, g);
    svg('circle', { cx: 0, cy: KNOB, r: 15.5, fill: colour('card') }, g);
    var head = svg('circle', { cx: 0, cy: KNOB, r: 12, fill: col }, g);
    if (letter) {
      svg('text', { x: 0, y: KNOB + 4.5, 'text-anchor': 'middle', fill: '#fff',
                    style: 'font-size:12.5px;font-weight:700' }, g).textContent = letter;
    }
    var bub = svg('g', null, g);
    svg('rect', { x: -40, y: bubbleY, width: 80, height: 34, rx: 17,
                  fill: col }, bub);
    var btxt = svg('text', { x: 0, y: bubbleY + 22, 'text-anchor': 'middle',
        fill: '#fff',
        style: 'font-size:14px;font-weight:700;font-variant-numeric:tabular-nums' },
        bub);
    btxt.textContent = '0';
    return { g: g, head: head, bub: bub, btxt: btxt };
  }
  var pinA = mkPin(colour('a'), 'A', 186);
  var pinB = mkPin(colour('b'), 'B', 230);

  var layer = svg('rect', { x: 26, y: 170, width: 808, height: 220,
                            fill: 'transparent', 'pointer-events': 'all',
                            class: 'grab' }, scene);

  function snapVal(v) {
    return clamp(vmin + Math.round((v - vmin) * sub) / sub, vmin, vmax);
  }
  function near(val, target) {
    return Math.abs(toX(val) - toX(target)) <= tolTicks * pxPerTick;
  }
  function place(pin, val) {
    if (val === null) { pin.g.setAttribute('display', 'none'); return; }
    pin.g.removeAttribute('display');
    pin.g.setAttribute('transform', 'translate(' + toX(val) + ',0)');
    pin.btxt.textContent = dec(val);
  }
  // A strict inequality is drawn as an open endpoint, which is what the feedback
  // text describes, so the picture and the words cannot disagree.
  function styleHead(pin, col, open) {
    pin.head.setAttribute('fill', open ? colour('card') : col);
    pin.head.setAttribute('stroke', open ? col : 'none');
    pin.head.setAttribute('stroke-width', open ? 3 : 0);
  }
  // ---- the readout band ----------------------------------------------------
  // The number the learner is steering, in tabular figures, next to the number the
  // task asks for. Two columns, divided, so the comparison is a glance.
  var gBand = svg('g', { 'data-series': 'readout' }, scene);
  svg('rect', { x: 40, y: 416, width: 780, height: 136, rx: 18,
                fill: colour('surface2'), stroke: colour('line'),
                'stroke-width': 1.2 }, gBand);
  svg('line', { x1: 430, x2: 430, y1: 436, y2: 532,
                stroke: colour('line'), 'stroke-width': 1.2 }, gBand);
  function bandText(x, y, anchor) {
    return svg('text', { x: x, y: y, 'text-anchor': anchor, fill: colour('ink'),
                         style: 'font-size:10px;font-weight:700;letter-spacing:.15em' },
               gBand);
  }
  function bandValue(x, y, anchor) {
    return svg('text', { x: x, y: y, 'text-anchor': anchor, fill: colour('ink'),
        style: 'font-size:32px;font-weight:700;font-variant-numeric:tabular-nums' },
        gBand);
  }
  function bandNote(x, y, anchor) {
    return svg('text', { x: x, y: y, 'text-anchor': anchor, fill: colour('dim'),
        style: 'font-size:11.5px' }, gBand);
  }
  var bandL1 = bandText(64, 446, 'start');
  var bandL2 = bandValue(64, 492, 'start');
  var bandL3 = bandNote(64, 522, 'start');
  var bandR1 = bandText(796, 446, 'end');
  var bandR2 = bandValue(796, 492, 'end');
  var bandR3 = bandNote(796, 522, 'end');

  function drawShade(task) {
    clear(gShade);
    if (!task || task.kind !== 'inequality' || state.posA === null || !state.dir) return;
    var bx = toX(state.posA);
    var x2 = state.dir === 'right' ? X1 : X0;
    svg('rect', { x: Math.min(bx, x2), y: TOP + 1.5, width: Math.abs(x2 - bx),
                  height: BOT - TOP - 3, fill: colour('c'), opacity: 0.26 }, gShade);
    var ay = (TOP + BOT) / 2;
    var ax = state.dir === 'right' ? X1 - 7 : X0 + 7;
    var sgn = state.dir === 'right' ? -1 : 1;
    svg('path', { d: 'M' + (ax + sgn * 15) + ' ' + (ay - 8) + ' L' + ax + ' ' + ay
                    + ' L' + (ax + sgn * 15) + ' ' + (ay + 8) + ' Z',
                  fill: colour('c') }, gShade);
  }

  function syncBand(task) {
    var kind = task ? task.kind : 'point';
    if (kind === 'compare') {
      bandL1.textContent = 'MARKER A';
      bandL2.textContent = dec(state.posA);
      bandL3.textContent = fracNote(state.posA);
      bandR1.textContent = 'MARKER B';
      bandR2.textContent = dec(state.posB);
      bandR3.textContent = fracNote(state.posB);
      return;
    }
    if (kind === 'inequality') {
      bandL1.textContent = 'BOUNDARY';
      bandL2.textContent = dec(state.posA);
      bandL3.textContent = fracNote(state.posA);
      bandR1.textContent = 'SHADE';
      bandR2.textContent = state.dir
        ? (state.dir === 'right' ? 'to the right' : 'to the left') : 'not chosen';
      bandR3.textContent = task.strict ? 'open endpoint' : 'closed endpoint';
      return;
    }
    bandL1.textContent = 'MARKER';
    bandL2.textContent = dec(state.posA);
    bandL3.textContent = fracNote(state.posA);
    bandR1.textContent = 'TARGET';
    bandR2.textContent = dec(+task.value);
    bandR3.textContent = fracNote(+task.value);
  }

  // ---- what this task asks for --------------------------------------------
  function syncTask() {
    var task = tasks[state.index];
    if (!task) return;
    var kind = task.kind;
    if (kind === 'compare') {
      targetBig.textContent = 'A ' + frac(+task.value) + '   B ' + frac(+task.value_b);
      targetSub.textContent = 'Place both markers, then say which value is larger.';
    } else if (kind === 'inequality') {
      var op = task.direction === 'right'
        ? (task.strict ? '>' : '\u2265') : (task.strict ? '<' : '\u2264');
      targetBig.textContent = 'x ' + op + ' ' + dec(+task.value);
      targetSub.textContent = 'Boundary at ' + dec(+task.value) + ' \u00b7 '
        + (task.strict ? 'open circle' : 'closed circle');
    } else {
      targetBig.textContent = frac(+task.value);
      targetSub.textContent = '= ' + dec(+task.value) + ' \u00b7 ' + mixed(+task.value);
    }
    syncProgress();
  }

  function syncProgress() {
    UI.progress(state.index + (state.solved ? 1 : 0), tasks.length);
  }

  function draw() {
    var task = tasks[state.index];
    var kind = task ? task.kind : 'point';
    place(pinA, state.posA);
    place(pinB, kind === 'compare' ? state.posB : null);
    styleHead(pinA, colour('a'), kind === 'inequality' && !!task.strict);
    drawShade(task);
    syncBand(task);
    BRIDGE.readout({ task: state.index, kind: task ? task.kind : null,
                     a: state.posA === null ? null : +state.posA.toFixed(3),
                     b: state.posB === null ? null : +state.posB.toFixed(3),
                     direction: state.dir, compare: state.cmp });
  }

  var held = null;
  drag(layer, {
    start: function (pt) {
      if (state.solved) return false;
      var task = tasks[state.index];
      if (!task) return false;
      if (task.kind === 'compare') {
        var da = state.posA === null ? 1e9 : Math.abs(toX(state.posA) - pt.x);
        var db = state.posB === null ? 1e9 : Math.abs(toX(state.posB) - pt.x);
        held = da <= db ? 'A' : 'B';
      } else {
        held = 'A';
        // Pressing anywhere on the line moves the single marker there; there is
        // nothing else on the line to hit.
        state.posA = snapVal(toX.invert(clamp(pt.x, X0, X1)));
        draw();
      }
      return { which: held };
    },
    move: function (pt) {
      if (!held) return;
      var v = snapVal(toX.invert(clamp(pt.x, X0, X1)));
      if (held === 'A') state.posA = v; else state.posB = v;
      draw();
    },
    end: function () { held = null; draw(); }
  });

  function toggle(id, show) {
    var b = document.getElementById(id);
    if (show) b.classList.remove('hidden'); else b.classList.add('hidden');
  }
  function syncControls() {
    var task = tasks[state.index];
    var kind = task ? task.kind : 'point';
    toggle('left', kind === 'inequality');
    toggle('right', kind === 'inequality');
    toggle('cmpA', kind === 'compare');
    toggle('cmpB', kind === 'compare');
    document.getElementById('tasklabel').textContent = task ? task.prompt : '';
    syncTask();
  }
  function setDir(d) {
    if (state.solved) return;
    state.dir = d;
    document.getElementById('left').classList.toggle('primary', d === 'left');
    document.getElementById('right').classList.toggle('primary', d === 'right');
    draw();
  }
  function setCmp(v) {
    if (state.solved) return;
    state.cmp = v;
    document.getElementById('cmpA').classList.toggle('primary', v === 'A');
    document.getElementById('cmpB').classList.toggle('primary', v === 'B');
    draw();
  }

  function finish(correct, extra) {
    var task = tasks[state.index];
    document.getElementById('check').disabled = true;
    document.getElementById('reset').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    syncProgress();
    BRIDGE.outcome({ correct: correct, task: task.id, kind: task.kind,
                     tries: state.tries + (correct ? 1 : 0),
                     detail: extra });
  }
  function succeed() {
    state.solved = true;
    var task = tasks[state.index];
    var lead = task.kind === 'point'
      ? fmt(+task.value, 2) + ' sits exactly on the line. ' : '';
    UI.feedback('Correct. ' + lead + (task.why || ''), true);
    finish(true, { value: +task.value,
                   placed: state.posA === null ? null : +state.posA.toFixed(3),
                   direction: task.direction || null, why: task.why || '' });
  }
  function reveal() {
    state.solved = true;
    var task = tasks[state.index];
    state.posA = +task.value;
    if (task.kind === 'compare') {
      state.posB = +task.value_b;
      state.cmp = (+task.value > +task.value_b) ? 'A' : 'B';
    }
    if (task.kind === 'inequality') state.dir = task.direction;
    draw();
    UI.feedback('That is three tries, so here is the answer: ' + (task.prompt || '') + ' '
      + (task.why || ''), false);
    finish(false, { value: +task.value, direction: task.direction || null,
                    gave_up: true, why: task.why || '' });
  }

  function miss(task, val) {
    state.tries += 1;
    if (state.tries >= __MAX_TRIES__) { reveal(); return; }
    var target = +task.value;
    var dticks = (val - target) * sub;
    var away = Math.round(Math.abs(dticks));
    var dstr = Math.abs(dticks) < 1e-6 ? 'right on the mark'
      : (Math.abs(Math.abs(dticks) - away) < 0.05
         ? away + ' tick(s) too far ' + (dticks > 0 ? 'right' : 'left')
         : fmt(Math.abs(dticks), 1) + ' tick(s) too far ' + (dticks > 0 ? 'right' : 'left'));
    UI.feedback('Not quite. ' + (task.prompt || '') + ' sits at ' + fmt(target, 2)
      + '; your marker is at ' + fmt(val, 2) + ', ' + dstr + '. ' + (task.why || ''), false);
  }

  function check() {
    if (state.solved) return;
    var task = tasks[state.index];
    if (!task) return;
    if (task.kind === 'point') {
      if (state.posA === null) {
        UI.feedback('Drag the marker onto the number line first.', false);
        return;
      }
      if (near(state.posA, +task.value)) { succeed(); return; }
      miss(task, state.posA);
      return;
    }
    if (task.kind === 'compare') {
      if (state.posA === null || state.posB === null || !state.cmp) {
        UI.feedback('Place both markers and choose which value is larger.', false);
        return;
      }
      var want = (+task.value > +task.value_b) ? 'A' : 'B';
      var placedOk = near(state.posA, +task.value) && near(state.posB, +task.value_b);
      if (placedOk && state.cmp === want) { succeed(); return; }
      state.tries += 1;
      if (state.tries >= __MAX_TRIES__) { reveal(); return; }
      if (!placedOk) {
        UI.feedback('Check the positions first: A belongs at ' + fmt(+task.value, 2)
          + ' and B at ' + fmt(+task.value_b, 2) + '. ' + (task.why || ''), false);
      } else {
        UI.feedback(fmt(+task.value, 2) + ' is '
          + (want === 'A' ? 'greater' : 'less') + ' than ' + fmt(+task.value_b, 2)
          + ', so ' + want + ' is the larger value. ' + (task.why || ''), false);
      }
      return;
    }
    if (state.posA === null || !state.dir) {
      UI.feedback('Place the boundary marker and choose a shading direction.', false);
      return;
    }
    if (near(state.posA, +task.value) && state.dir === task.direction) { succeed(); return; }
    state.tries += 1;
    if (state.tries >= __MAX_TRIES__) { reveal(); return; }
    if (!near(state.posA, +task.value)) {
      UI.feedback('The boundary belongs at ' + fmt(+task.value, 2) + '. ' + (task.why || ''), false);
    } else {
      UI.feedback('The boundary is right, but the shading runs the wrong way: '
        + (task.direction === 'right'
           ? 'the solution is greater than the boundary, so shade to the right.'
           : 'the solution is less than the boundary, so shade to the left.')
        + ' ' + (task.why || ''), false);
    }
  }

  function resetTask() {
    var task = tasks[state.index];
    state.tries = 0;
    state.solved = false;
    // The handles start on the line, at the left end (and, for a comparison, a
    // second one further along). A handle parked outside the canvas is not a
    // handle - the learner cannot see the thing they are meant to grab.
    state.posA = vmin;
    state.posB = (task && task.kind === 'compare')
      ? snapVal(vmin + (vmax - vmin) * 0.4) : null;
    state.dir = null;
    state.cmp = null;
    document.getElementById('check').disabled = false;
    document.getElementById('reset').disabled = false;
    document.getElementById('next').classList.add('hidden');
    document.getElementById('left').classList.remove('primary');
    document.getElementById('right').classList.remove('primary');
    document.getElementById('cmpA').classList.remove('primary');
    document.getElementById('cmpB').classList.remove('primary');
    UI.feedback('');
    syncControls();
    draw();
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    if (!state.solved) resetTask();
  });
  document.getElementById('next').addEventListener('click', function () {
    state.index = Math.min(state.index + 1, tasks.length - 1);
    resetTask();
  });
  document.getElementById('left').addEventListener('click', function () { setDir('left'); });
  document.getElementById('right').addEventListener('click', function () { setDir('right'); });
  document.getElementById('cmpA').addEventListener('click', function () { setCmp('A'); });
  document.getElementById('cmpB').addEventListener('click', function () { setCmp('B'); });

  resetTask();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


NUMBER_LINE = Archetype(
    id='number_line',
    title='Place it on the line',
    blurb='Drag a marker to a value on a number line, compare two values, or shade an inequality.',
    interaction='drag a marker along a number line and commit to a position',
    subjects=('mathematics',),
    tags=('number-line', 'fractions', 'inequality', 'comparison', 'place-value'),
    reference='Math Playground number-line games; NRICH number-line tasks',
    telemetry='One outcome per committed task: whether the marker landed within the tick '
              'tolerance, the value placed, the direction chosen for an inequality, and the tries.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('min', 'float', 'Left end of the number line.', minimum=-100, maximum=100),
        Field('max', 'float', 'Right end of the number line.', minimum=-100, maximum=100),
        Field('subdivisions', 'int', 'Tick marks per unit (4 for quarters, 8 for eighths).',
              minimum=1, maximum=10),
        Field('tol_ticks', 'float', 'How close, in ticks, a placement must be to count.',
              minimum=0.05, maximum=1.5),
        Field('tasks', 'table',
              'One row per task. kind "point" places one value; "compare" places two and asks '
              'which is larger; "inequality" places a boundary and marks the direction.',
              minimum_items=1, maximum_items=6,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this task.'),
                  Field('kind', 'text', 'What the task asks for.',
                        choices=('point', 'compare', 'inequality')),
                  Field('prompt', 'text', 'The task, in one sentence.'),
                  Field('value', 'float', 'The value to place (or the inequality boundary).'),
                  Field('value_b', 'float', 'The second value, for a compare task.',
                        required=False),
                  Field('direction', 'text', 'Which way the solution set runs, for an '
                        'inequality task.', choices=('right', 'left'), required=False),
                  Field('strict', 'bool', 'True for a strict inequality (open endpoint).',
                        required=False),
                  Field('why', 'text', 'The reasoning revealed after the answer.',
                        required=False),
              )),
    ),
    body=_number_line_body,
    engine=lambda spec: _NUMBER_LINE_ENGINE,
    # 860x600 is the aspect of the stage's drawing area, so the target card, the
    # line and the readout band fill the card instead of letterboxing inside it.
    # The value scale stays 78..812 and the marker's grab layer still covers y=250,
    # which is the drop point the correctness oracle derives.
    height=600,
)


# ================================================================= balance_scale


def _balance_scale_body(spec: Mapping[str, Any]) -> str:
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        '<svg class="scene" id="scene" viewBox="0 0 860 565" role="img" '
        'aria-label="A balance scale holding x blocks and unit blocks" '
        'data-series="balance-scale"></svg>'
        '</div>'
        '<div class="controls">'
        '<span class="verdict" id="eq"></span>'
        '<span class="spacer"></span>'
        '<button id="l_minus">Left −1 unit</button>'
        '<button id="l_div">Left ÷ coeff</button>'
        '<button id="r_minus">Right −1 unit</button>'
        '<button id="r_div">Right ÷ coeff</button>'
        '<button id="undo">Undo</button>'
        '<button id="reset">Reset</button>'
        '<button class="primary" id="check">Check</button>'
        '</div>'
        '</div>')


_BALANCE_SCALE_ENGINE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var A = +spec.coefficient, B = +spec.constant_left, C = +spec.constant_right;
  var xsol = (C - B) / A;
  var pivotX = 430, beamY = 150, half = 280, baseY = 520;
  var state = { left: { x: A, units: B }, right: { x: 0, units: C },
                divided: { left: false, right: false },
                tries: 0, solved: false, stack: [] };

  function eqText(a, b, cc) {
    var s = '';
    if (a === 1) s += 'x'; else if (a === -1) s += '−x'; else s += fmt(a, 0) + 'x';
    if (b > 0) s += ' + ' + fmt(b, 0); else if (b < 0) s += ' − ' + fmt(Math.abs(b), 0);
    s += ' = ' + fmt(cc, 0);
    return s;
  }
  document.getElementById('eq').textContent = eqText(A, B, C);
  document.getElementById('l_div').textContent = 'Left ÷ ' + fmt(A, 0);
  document.getElementById('r_div').textContent = 'Right ÷ ' + fmt(A, 0);

  // The goal, stated once, large: the whole game is to make this line say a number.
  svg('text', { x: pivotX, y: 36, 'text-anchor': 'middle', fill: colour('faint'),
                style: 'font-size:10px;font-weight:700;letter-spacing:.15em' },
      scene).textContent = 'SOLVE FOR';
  var goalText = svg('text', { x: pivotX, y: 88, 'text-anchor': 'middle',
      fill: colour('ink'),
      style: 'font-size:44px;font-weight:700;font-variant-numeric:tabular-nums' }, scene);
  goalText.textContent = 'x = ?';

  var gStatic = svg('g', null, scene);
  svg('path', { d: 'M' + (pivotX - 16) + ' ' + baseY + ' L' + (pivotX - 7) + ' ' + beamY
    + ' L' + (pivotX + 7) + ' ' + beamY + ' L' + (pivotX + 16) + ' ' + baseY + ' Z',
    fill: colour('surface3'), stroke: colour('edge'), 'stroke-width': 1.4 }, gStatic);
  svg('rect', { x: pivotX - 62, y: baseY - 4, width: 124, height: 12, rx: 6,
                fill: colour('surface3'), stroke: colour('edge'),
                'stroke-width': 1.4 }, gStatic);
  svg('circle', { cx: pivotX, cy: beamY, r: 8, fill: colour('ink') }, gStatic);

  var gBeam = svg('g', { 'data-series': 'beam' }, scene);
  var beam = svg('line', { stroke: colour('ink'), 'stroke-width': 5,
                           'stroke-linecap': 'round' }, gBeam);
  var gLeft = svg('g', { 'data-series': 'left-pan' }, scene);
  var gRight = svg('g', { 'data-series': 'right-pan' }, scene);
  var tiltChip = UI.chip('level', 'Scale', 'b');

  function weight(side) { return side.x * xsol + side.units; }
  function snapshot() {
    return { left: { x: state.left.x, units: state.left.units },
             right: { x: state.right.x, units: state.right.units },
             divided: { left: state.divided.left, right: state.divided.right } };
  }
  function renderPan(g, ex, ey, side) {
    clear(g);
    var top = ey + 70;
    var pw = 250, ph = 130;
    // The pan hangs from its two rim corners on strings that meet at the beam end,
    // so a tilt reads as a pan swinging rather than a box sliding down the beam.
    svg('line', { x1: ex, y1: ey, x2: ex - 104, y2: top, stroke: colour('faint'),
                  'stroke-width': 1.4 }, g);
    svg('line', { x1: ex, y1: ey, x2: ex + 104, y2: top, stroke: colour('faint'),
                  'stroke-width': 1.4 }, g);
    svg('rect', { x: ex - pw / 2, y: top + 3, width: pw, height: ph, rx: 12,
                  fill: 'rgba(36,49,42,.10)' }, g);
    svg('rect', { x: ex - pw / 2, y: top, width: pw, height: ph, rx: 12,
                  fill: colour('card'), stroke: colour('edge'),
                  'stroke-width': 1.6 }, g);
    var left = ex - 115, w = 230, bx = left, by = top + 11, i;
    for (i = 0; i < side.x; i += 1) {
      svg('rect', { x: bx, y: by, width: 32, height: 32, rx: 7, fill: colour('a') }, g);
      svg('text', { x: bx + 16, y: by + 22, 'text-anchor': 'middle', fill: '#fff',
                    style: 'font-size:15px;font-weight:700' }, g).textContent = 'x';
      bx += 37;
    }
    var ux = left, uy = by + (side.x > 0 ? 42 : 0);
    for (i = 0; i < side.units; i += 1) {
      if (ux + 22 > left + w) { ux = left; uy += 26; }
      svg('rect', { x: ux, y: uy, width: 22, height: 22, rx: 4, fill: colour('d'),
                    stroke: colour('edge'), 'stroke-width': 1 }, g);
      ux += 26;
    }
    svg('text', { x: ex, y: top + ph + 28, 'text-anchor': 'middle', fill: colour('ink'),
                  style: 'font-size:15px;font-weight:650;font-variant-numeric:tabular-nums' },
        g).textContent = (side.x > 0 ? side.x + 'x + ' : '') + side.units;
  }
  function draw() {
    var lw = weight(state.left), rw = weight(state.right);
    var d = rw - lw;
    var theta = clamp(d * 0.09, -0.18, 0.18);
    var cs = Math.cos(theta), sn = Math.sin(theta);
    var lx = pivotX - half * cs, ly = beamY - half * sn;
    var rx = pivotX + half * cs, ry = beamY + half * sn;
    beam.setAttribute('x1', lx); beam.setAttribute('y1', ly);
    beam.setAttribute('x2', rx); beam.setAttribute('y2', ry);
    renderPan(gLeft, lx, ly, state.left);
    renderPan(gRight, rx, ry, state.right);
    tiltChip.set(Math.abs(d) < 1e-9 ? 'level' : 'tilted');
    BRIDGE.readout({ left: { x: state.left.x, units: state.left.units },
                     right: { x: state.right.x, units: state.right.units },
                     level: Math.abs(d) < 1e-9, tilt: +theta.toFixed(3) });
  }

  function op(side, kind) {
    if (state.solved) return;
    var s = state[side];
    if (kind === 'minus') {
      if (s.units <= 0) {
        UI.feedback('There are no unit blocks left on the ' + side + ' pan to remove.', false);
        return;
      }
      state.stack.push(snapshot());
      s.units -= 1;
      draw();
      return;
    }
    var d = A;
    if (d <= 1) {
      UI.feedback('x already stands alone — its coefficient is 1 — so there is nothing '
        + 'left to divide by.', false);
      return;
    }
    if (state.divided[side]) {
      UI.feedback('You have already divided the ' + side + ' pan by ' + fmt(d, 0)
        + '. Now do the same to the other pan.', false);
      return;
    }
    if (state.left.units % d !== 0 || state.right.units % d !== 0) {
      UI.feedback('Dividing by ' + fmt(d, 0) + ' would not give whole blocks yet: '
        + state.left.units + ' and ' + state.right.units + ' are not both multiples of '
        + fmt(d, 0) + '. Remove the constant from both pans first.', false);
      return;
    }
    state.stack.push(snapshot());
    state[side].x = state[side].x / d;
    state[side].units = state[side].units / d;
    state.divided[side] = true;
    draw();
  }

  function succeed() {
    state.solved = true;
    document.getElementById('check').disabled = true;
    goalText.textContent = 'x = ' + fmt(xsol, 0);
    goalText.setAttribute('fill', colour('good'));
    UI.feedback('Correct — the scale stayed level the whole way. x = ' + fmt(xsol, 0)
      + ': subtracting ' + fmt(B, 0) + ' from both sides leaves ' + fmt(A, 0) + 'x = '
      + fmt(C - B, 0) + ', and dividing both sides by ' + fmt(A, 0) + ' gives x = '
      + fmt(xsol, 0) + '.', true);
    BRIDGE.outcome({ correct: true, tries: state.tries + 1, solution: xsol,
                     detail: { equation: eqText(A, B, C), left: snapshot().left,
                               right: snapshot().right } });
  }
  function reveal() {
    state.solved = true;
    document.getElementById('check').disabled = true;
    state.left = { x: 1, units: 0 };
    state.right = { x: 0, units: xsol };
    goalText.textContent = 'x = ' + fmt(xsol, 0);
    goalText.setAttribute('fill', colour('good'));
    draw();
    UI.feedback('That is three tries, so here is the solution: subtract ' + fmt(B, 0)
      + ' from both sides, then divide both sides by ' + fmt(A, 0) + '. That isolates x = '
      + fmt(xsol, 0) + '.', false);
    BRIDGE.outcome({ correct: false, tries: state.tries, solution: xsol,
                     detail: { equation: eqText(A, B, C), gave_up: true } });
  }

  function check() {
    if (state.solved) return;
    var lw = weight(state.left), rw = weight(state.right);
    var level = Math.abs(rw - lw) < 1e-9;
    if (level && state.left.x === 1 && state.left.units === 0) { succeed(); return; }
    state.tries += 1;
    if (state.tries >= __MAX_TRIES__) { reveal(); return; }
    if (!level) {
      UI.feedback('The scale is not level: you changed one pan without changing the other. '
        + 'Whatever you do to one side you must do to the other — that is what keeps the '
        + 'equation true. Use Undo, or repeat the move on the other pan.', false);
    } else if (state.left.x !== 1) {
      UI.feedback('Still level, but x is not alone: the left pan still holds ' + state.left.x
        + ' x-blocks. Divide both sides by ' + fmt(state.left.x, 0) + '.', false);
    } else {
      UI.feedback('Still level, but there are ' + state.left.units + ' unit block(s) sitting '
        + 'with the x. Remove that constant from both pans before dividing.', false);
    }
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('undo').addEventListener('click', function () {
    if (state.solved || !state.stack.length) return;
    var s = state.stack.pop();
    state.left = s.left;
    state.right = s.right;
    state.divided = s.divided;
    draw();
  });
  document.getElementById('reset').addEventListener('click', function () {
    if (state.solved) return;
    state.left = { x: A, units: B };
    state.right = { x: 0, units: C };
    state.divided = { left: false, right: false };
    state.stack = [];
    goalText.textContent = 'x = ?';
    goalText.setAttribute('fill', colour('ink'));
    draw();
  });
  document.getElementById('l_minus').addEventListener('click', function () { op('left', 'minus'); });
  document.getElementById('l_div').addEventListener('click', function () { op('left', 'div'); });
  document.getElementById('r_minus').addEventListener('click', function () { op('right', 'minus'); });
  document.getElementById('r_div').addEventListener('click', function () { op('right', 'div'); });

  draw();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


BALANCE_SCALE = Archetype(
    id='balance_scale',
    title='Keep the balance',
    blurb='Isolate x by making the same move on both pans — the scale tilts if you do not.',
    interaction='add or remove blocks from both pans of a balance scale',
    subjects=('mathematics',),
    tags=('equations', 'balance', 'manipulatives', 'solving', 'algebra'),
    reference='Math Playground algebra balance scales; solving linear equations manipulatives',
    telemetry='One outcome per committed solve: whether x was isolated with the scale level, '
              'the integer solution reached, and the tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('coefficient', 'int', 'The coefficient a in ax + b = c.', minimum=1, maximum=6),
        Field('constant_left', 'int', 'The constant b on the x side.', minimum=0, maximum=12),
        Field('constant_right', 'int', 'The constant c on the other side.', minimum=1, maximum=24),
    ),
    body=_balance_scale_body,
    engine=lambda spec: _BALANCE_SCALE_ENGINE,
    # The beam, the two pans and the stand need the full height of the stage; 860x565
    # is that box's aspect, so the scale is drawn at the size the card can show.
    height=565,
)


#: Everything this module contributes, for the registry to pick up.
MATH_A_ARCHETYPES = (PLOT_POINTS, FUNCTION_MACHINE, NUMBER_LINE, BALANCE_SCALE)
