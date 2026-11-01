"""Physics, biology and earth-science archetypes for the simulator playground.

Four first-party simulators, each a variation on the ``curve_shift`` pattern in
:mod:`app.harness.playground.archetypes_core`:

``wave_lab``
    Two waves on one shared axis, and their sum computed point by point. The
    learner predicts constructive, destructive or partial interference, or sets a
    phase to cancel a wave. The physics being taught is the phase condition.

``projectile``
    Kinematics with a stated ``g`` and stated units. The trajectory is the real
    parabola ``R = v^2 sin(2 theta) / g``, with apex, range and time of flight
    marked, and a velocity vector that resolves into components.

``punnett``
    A Punnett square derived from the two parents' genotypes, with the phenotype
    ratio derived from the square. Dominant/recessive and incomplete dominance.

``orbit_gravity``
    A satellite around a central mass, integrated with a semi-implicit Euler step.
    Below the escape speed you get a closed orbit; above it, escape; too slow and
    it hits the body. That threshold is the physics.

Why these are archetypes and not pages
--------------------------------------
Each is the standard simulator from PhET or ExploreLearning Gizmos, reimplemented
first-party so it runs offline and - unlike PhET - can report the learner's
outcome back to the harness. Content arrives as a spec; the interaction is here.
"""

from __future__ import annotations

from typing import Any, Mapping

from .archetypes import Archetype, Field

#: Tries before the answer is revealed. Same rule as the reference archetype:
#: offering the answer beats letting a learner grind.
_MAX_TRIES = 3

#: The shared page shell: one stage, a slider/select panel, an answer panel, and a
#: control strip. Every archetype in this module uses it so the geometry matches.
_PANELS = '<div class="panel" id="panel"></div><div class="panel" id="answer"></div>'


def _shell(aria: str, extra: str = _PANELS) -> str:
    return (
        '<div class="stagecol">'
        '<div class="scene-wrap">'
        f'<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
        f'aria-label="{aria}"></svg>'
        '</div>'
        f'{extra}'
        '<div class="controls">'
        '<span class="verdict" id="prompt"></span>'
        '<span class="spacer"></span>'
        '<span id="choices"></span>'
        '<button id="reset">Reset</button>'
        '<button class="primary" id="check">Check</button>'
        '<button id="next" class="hidden">Next</button>'
        '</div>'
        '</div>')


# ============================================================ 1. wave_lab

def _body_wave(spec: Mapping[str, Any]) -> str:
    return _shell('Two waves drawn on one axis, with their sum underneath.')


_ENGINE_WAVE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var panel = document.getElementById('panel');
  // The plot leaves a gutter on every side: 44px on the left for a rotated axis
  // title and its ticks, 38px below for the tick row and the axis title. Labels
  // live in those gutters, never on the curve.
  var X0 = 92, X1 = 820, Y0 = 372, Y1 = 64;
  var xMax = +spec.x_max || 20;
  var yMax = +spec.y_max || 4.5;
  var N = 241;
  var TWO_PI = Math.PI * 2;
  var toX = scale([0, xMax], [X0, X1]);
  var toY = scale([-yMax, yMax], [Y0, Y1]);

  var chipD = UI.chip('dphi', 'Phase difference', 'e');
  var chipP = UI.chip('peak', 'Peak |A+B|', 'c');
  var chipK = UI.chip('kind', 'Interference', 'a');

  var state = { a1: 1, l1: 4, p1: 0, a2: 1, l2: 4, p2: 0,
                index: 0, tries: 0, choice: null, committed: false };

  function wrapPi(rad) {
    var d = rad % TWO_PI;
    if (d < 0) d += TWO_PI;
    if (d > Math.PI) d = TWO_PI - d;
    return d;
  }
  function dphiDeg() { return wrapPi((state.p2 - state.p1) * Math.PI / 180) * 180 / Math.PI; }
  function category() {
    if (Math.abs(state.l1 - state.l2) > 1e-6) return 'partial';
    var d = wrapPi((state.p2 - state.p1) * Math.PI / 180);
    if (d < Math.PI / 6) return 'constructive';
    if (d > 5 * Math.PI / 6) return 'destructive';
    return 'partial';
  }
  function sumAt(x) {
    return state.a1 * Math.sin(TWO_PI * x / state.l1 + state.p1 * Math.PI / 180)
         + state.a2 * Math.sin(TWO_PI * x / state.l2 + state.p2 * Math.PI / 180);
  }
  function pathOf(fn) {
    var d = '';
    for (var i = 0; i < N; i++) {
      var x = xMax * i / (N - 1);
      d += (i ? 'L' : 'M') + fmt(toX(x), 2) + ' ' + fmt(toY(fn(x)), 2) + ' ';
    }
    return d;
  }
  function waveFn(amp, lam, phase) {
    return function (x) { return amp * Math.sin(TWO_PI * x / lam + phase * Math.PI / 180); };
  }

  // ---- static chrome -------------------------------------------------------
  var gGrid = svg('g', { 'data-series': 'grid' }, scene);
  for (var i = 0; i <= 10; i++) {
    svg('line', { x1: toX(i * xMax / 10), x2: toX(i * xMax / 10), y1: Y1, y2: Y0,
                  class: 'gridline' }, gGrid);
  }
  for (var j = -2; j <= 2; j++) {
    svg('line', { x1: X0, x2: X1, y1: toY(j * yMax / 2), y2: toY(j * yMax / 2),
                  class: 'gridline' }, gGrid);
  }
  svg('line', { x1: X0, x2: X1, y1: Y0, y2: Y0, class: 'gridline' }, gGrid);

  var gAxes = svg('g', { 'data-series': 'axes' }, scene);
  svg('line', { x1: X0, x2: X1, y1: toY(0), y2: toY(0), class: 'axis' }, gAxes);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, gAxes);

  // Ticks sit in the gutter under the plot. On the zero line they collided with
  // the curves and with the axis title, which is exactly what the audit caught.
  for (var t = 0; t <= 10; t += 2) {
    svg('text', { x: toX(t * xMax / 10), y: Y0 + 18, 'text-anchor': 'middle',
                  class: 'tick' }, gAxes).textContent = fmt(t * xMax / 10, 0);
  }
  svg('text', { x: (X0 + X1) / 2, y: Y0 + 38, 'text-anchor': 'middle', class: 'tick' },
      gAxes).textContent = spec.x_label || 'Distance (m)';

  for (var k = -1; k <= 1; k++) {
    svg('text', { x: X0 - 10, y: toY(k * yMax) + 3.5, 'text-anchor': 'end',
                  class: 'tick' }, gAxes).textContent = k === 0 ? '0' : fmt(k * yMax, 1);
  }
  var cyP = (Y0 + Y1) / 2;
  svg('text', { x: X0 - 44, y: cyP, 'text-anchor': 'middle', class: 'tick',
                transform: 'rotate(-90 ' + (X0 - 44) + ' ' + cyP + ')' },
      gAxes).textContent = spec.y_label || 'Displacement';

  // The legend sits above the plot rather than over the curves it names.
  var legend = svg('g', { 'data-series': 'legend' }, scene);
  [['a', 'Wave A'], ['b', 'Wave B'], ['c', 'Sum A+B']].forEach(function (it, k2) {
    var x = X0 + k2 * 128;
    svg('line', { x1: x, x2: x + 18, y1: Y1 - 26, y2: Y1 - 26, stroke: colour(it[0]),
                  'stroke-width': 3 }, legend);
    svg('text', { x: x + 24, y: Y1 - 22, class: 'note' }, legend).textContent = it[1];
  });

  // B is drawn first and A over it, so that when the two waves coincide exactly -
  // which is the whole point of a "will they add or cancel" task - A can be dashed
  // and the learner still sees that there are two curves, not one.
  var gB = svg('g', { 'data-series': 'wave-b' }, scene);
  var pathB = svg('path', { fill: 'none', stroke: colour('b'), 'stroke-width': 2.4 }, gB);
  var gA = svg('g', { 'data-series': 'wave-a' }, scene);
  var pathA = svg('path', { fill: 'none', stroke: colour('a'), 'stroke-width': 2.4 }, gA);
  var gS = svg('g', { 'data-series': 'wave-sum' }, scene);
  var pathS = svg('path', { fill: 'none', stroke: colour('c'), 'stroke-width': 2.8 }, gS);

  // ---- panel ---------------------------------------------------------------
  var rows = {};
  function mk(key, label, min, max, step, unit) {
    var lab = el('label', { class: 'fld' }, panel);
    lab.appendChild(document.createTextNode(label));
    var inp = el('input', { type: 'range', min: min, max: max, step: step,
                            value: state[key], 'aria-label': label }, lab);
    var out = el('b', null, lab);
    rows[key] = { inp: inp, out: out, unit: unit, step: step };
    inp.addEventListener('input', function () {
      state[key] = +inp.value;
      out.textContent = fmt(+inp.value, step < 1 ? 1 : 0) + unit;
      draw();
    });
  }
  mk('a1', 'Amp 1', 0, 2, 0.1, '');
  mk('l1', 'Wavelength 1', 1, 10, 0.1, '');
  mk('p1', 'Phase 1', 0, 360, 5, '\u00b0');
  mk('a2', 'Amp 2', 0, 2, 0.1, '');
  mk('l2', 'Wavelength 2', 1, 10, 0.1, '');
  mk('p2', 'Phase 2', 0, 360, 5, '\u00b0');

  var KEYS = ['a1', 'l1', 'p1', 'a2', 'l2', 'p2'];
  function sync() {
    KEYS.forEach(function (k) {
      rows[k].inp.value = state[k];
      rows[k].out.textContent = fmt(state[k], rows[k].step < 1 ? 1 : 0) + rows[k].unit;
    });
  }
  function lockAll(on) { KEYS.forEach(function (k) { rows[k].inp.disabled = on; }); }

  function setChoices(opts) {
    var box = document.getElementById('choices');
    clear(box);
    opts.forEach(function (o) {
      var b = el('button', { type: 'button', 'data-value': o.value }, box);
      b.textContent = o.label;
      b.addEventListener('click', function () {
        state.choice = o.value;
        Array.prototype.forEach.call(box.children, function (c) {
          c.style.borderColor = ''; c.style.background = '';
        });
        b.style.borderColor = COLOURS.a; b.style.background = '#eef2f8';
      });
    });
  }

  // ---- challenge -----------------------------------------------------------
  function ch() { return (spec.challenges || [])[state.index] || null; }

  function explain(actual) {
    var base = 'The phase difference is ' + fmt(dphiDeg(), 0) + '\u00b0. ';
    if (actual === 'constructive') {
      return base + 'It is a whole number of cycles, so crest meets crest and the '
        + 'amplitudes add: peak ' + fmt(state.a1 + state.a2, 2) + '.';
    }
    if (actual === 'destructive') {
      return base + 'It is half a cycle out, so crest meets trough and they cancel, '
        + 'leaving a peak of ' + fmt(Math.abs(state.a1 - state.a2), 2) + '.';
    }
    if (Math.abs(state.l1 - state.l2) > 1e-6) {
      return base + 'The wavelengths differ, so the waves drift in and out of step '
        + 'along the axis: they beat rather than adding or cancelling everywhere.';
    }
    return base + 'It is neither in step nor exactly out of step, so the waves '
      + 'partially reinforce and partially cancel.';
  }

  function load() {
    var c = ch();
    state.tries = 0; state.choice = null; state.committed = false;
    clear(document.getElementById('choices'));
    var check = document.getElementById('check');
    var next = document.getElementById('next');
    check.disabled = false;
    next.classList.add('hidden');
    document.getElementById('prompt').textContent = '';
    UI.feedback('');
    UI.progress(state.index, (spec.challenges || []).length);
    if (!c) {
      UI.say('Every task is complete.');
      lockAll(true); draw(); return;
    }
    state.a1 = +c.a1; state.l1 = +c.l1; state.p1 = +c.p1;
    state.a2 = +c.a2; state.l2 = +c.l2;
    state.p2 = (c.kind === 'set_phase') ? (+c.p2_start || 0) : +c.p2;
    if (c.kind === 'classify') {
      lockAll(true);
      setChoices([{ value: 'constructive', label: 'Constructive' },
                  { value: 'destructive', label: 'Destructive' },
                  { value: 'partial', label: 'Partial' }]);
      UI.say(c.text);
    } else if (c.kind === 'set_phase') {
      lockAll(true); rows.p2.inp.disabled = false;
      UI.say(c.text);
      document.getElementById('prompt').textContent =
        'Target: ' + (c.target === 'destructive' ? 'destructive' : 'constructive')
        + ' interference. Move Phase 2.';
    } else {
      lockAll(false);
      check.disabled = true;
      next.classList.remove('hidden');
      UI.say(c.text);
    }
    sync(); draw();
  }

  function draw() {
    pathA.setAttribute('d', pathOf(waveFn(state.a1, state.l1, state.p1)));
    pathB.setAttribute('d', pathOf(waveFn(state.a2, state.l2, state.p2)));
    var dph = ((state.p2 - state.p1) % 360 + 360) % 360;
    var same = Math.abs(state.a1 - state.a2) < 1e-6
            && Math.abs(state.l1 - state.l2) < 1e-6
            && (dph < 1e-6 || dph > 360 - 1e-6);
    if (same) pathA.setAttribute('stroke-dasharray', '7 5');
    else pathA.removeAttribute('stroke-dasharray');
    var c = ch();
    var hideSum = !!(c && c.kind === 'classify' && !state.committed);
    if (hideSum) {
      pathS.setAttribute('d', '');
      pathS.setAttribute('opacity', 0);
      chipD.set('--'); chipP.set('--'); chipK.set('--');
      return;
    }
    pathS.setAttribute('opacity', 1);
    pathS.setAttribute('d', pathOf(sumAt));
    var peak = 0;
    for (var i = 0; i < N; i++) {
      peak = Math.max(peak, Math.abs(sumAt(xMax * i / (N - 1))));
    }
    chipD.set(fmt(dphiDeg(), 0) + '\u00b0');
    chipP.set(fmt(peak, 2));
    chipK.set(category());
    BRIDGE.readout({ a1: state.a1, l1: state.l1, p1: state.p1,
                     a2: state.a2, l2: state.l2, p2: state.p2,
                     dphi_deg: +dphiDeg().toFixed(1), peak: +peak.toFixed(3),
                     interference: category() });
  }

  function finish(correct, detail) {
    state.committed = true;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    draw();
    BRIDGE.outcome({ correct: correct, task: ch().id, kind: ch().kind,
                     tries: state.tries + (correct ? 1 : 0),
                     answer: detail.answer, detail: detail });
  }

  function check() {
    var c = ch();
    if (!c || state.committed || c.kind === 'sandbox') return;
    if (c.kind === 'classify') {
      if (!state.choice) {
        UI.feedback('Pick constructive, destructive or partial before checking.', false);
        return;
      }
      var actual = category();
      if (state.choice === actual) {
        UI.feedback('Correct. ' + explain(actual), true);
        finish(true, { answer: actual, dphi_deg: +dphiDeg().toFixed(1), why: c.why || '' });
      } else {
        state.tries += 1;
        if (state.tries >= __MAX_TRIES__) {
          UI.feedback('Here is the answer: the waves are ' + actual + '. '
                      + explain(actual) + ' ' + (c.why || ''), false);
          finish(false, { answer: actual, dphi_deg: +dphiDeg().toFixed(1),
                          gave_up: true, why: c.why || '' });
        } else {
          UI.feedback('Not quite. Compare the two phases: they differ by '
                      + fmt(dphiDeg(), 0) + '\u00b0. In step means 0\u00b0 apart, '
                      + 'out of step means 180\u00b0 apart. Try again.', false);
        }
      }
      return;
    }
    // set_phase
    var target = c.target === 'destructive' ? Math.PI : 0;
    var d = wrapPi((state.p2 - state.p1) * Math.PI / 180);
    var ok = Math.abs(d - target) <= 0.35;
    var actual2 = category();
    if (ok) {
      UI.feedback('Correct. ' + explain(actual2) + ' ' + (c.why || ''), true);
      finish(true, { answer: c.target, dphi_deg: +dphiDeg().toFixed(1), why: c.why || '' });
    } else {
      state.tries += 1;
      if (state.tries >= __MAX_TRIES__) {
        UI.feedback('Third try, so here it is: ' + (c.target === 'destructive'
          ? 'set the phase difference to 180\u00b0 so a crest meets a trough.'
          : 'set the phase difference to 0\u00b0 so the crests line up.') + ' '
          + explain(actual2), false);
        finish(false, { answer: c.target, dphi_deg: +dphiDeg().toFixed(1),
                        gave_up: true, why: c.why || '' });
      } else {
        UI.feedback('Not yet. The waves now differ in phase by ' + fmt(dphiDeg(), 0)
                    + '\u00b0. ' + (c.target === 'destructive'
                      ? 'To cancel, you need 180\u00b0.' : 'To add up, you need 0\u00b0.'),
                    false);
      }
    }
  }

  // ---- controls ------------------------------------------------------------
  document.getElementById('check').addEventListener('click', check);
  document.getElementById('next').addEventListener('click', function () {
    state.index += 1; load();
  });
  document.getElementById('reset').addEventListener('click', function () {
    var c = ch();
    if (c && c.kind === 'set_phase') { state.p2 = +c.p2_start || 0; sync(); draw(); }
    UI.feedback('');
  });

  load();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


WAVE_LAB = Archetype(
    id='wave_lab',
    title='Wave interference lab',
    blurb='Draw two waves on one axis and watch their sum add up or cancel.',
    interaction='slide amplitude, wavelength and phase; predict how the waves combine',
    subjects=('science', 'physics', 'mathematics'),
    tags=('waves', 'superposition', 'interference', 'graphs', 'phase'),
    reference='PhET Wave Interference / Fourier: Making Waves; ExploreLearning Gizmos '
              'Wave Superposition',
    telemetry='One outcome per task: whether the predicted interference (constructive, '
              'destructive or partial) was right, or whether the set phase met the target, '
              'the phase difference in degrees, and the tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('x_label', 'text', 'Horizontal axis label.', required=False),
        Field('y_label', 'text', 'Vertical axis label.', required=False),
        Field('x_max', 'float', 'Horizontal axis maximum, in metres.', required=False,
              minimum=1, maximum=100),
        Field('y_max', 'float', 'Vertical half-range of the displacement axis.',
              required=False, minimum=1, maximum=50),
        Field('challenges', 'table',
              'One row per task. kind="classify" hides the sum and asks the learner to '
              'predict how the waves combine; kind="set_phase" lets the learner move '
              'Phase 2 to hit a target; kind="sandbox" is free play with no score.',
              minimum_items=1, maximum_items=12,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this task.'),
                  Field('kind', 'text', 'What the task asks for.',
                        choices=('classify', 'set_phase', 'sandbox')),
                  Field('text', 'text', 'The question, in one sentence.'),
                  Field('a1', 'float', 'Amplitude of wave A.', minimum=0, maximum=5),
                  Field('l1', 'float', 'Wavelength of wave A, in metres.',
                        minimum=0.5, maximum=20),
                  Field('p1', 'float', 'Phase of wave A, in degrees.',
                        minimum=0, maximum=360),
                  Field('a2', 'float', 'Amplitude of wave B.', minimum=0, maximum=5),
                  Field('l2', 'float', 'Wavelength of wave B, in metres.',
                        minimum=0.5, maximum=20),
                  Field('p2', 'float', 'Phase of wave B, in degrees.',
                        minimum=0, maximum=360),
                  Field('p2_start', 'float', 'Starting phase of wave B for a set_phase '
                        'task, in degrees.', required=False, minimum=0, maximum=360),
                  Field('target', 'text', 'For a set_phase task: the interference the '
                        'learner must produce.', required=False,
                        choices=('constructive', 'destructive')),
                  Field('why', 'text', 'The reasoning revealed after the answer.',
                        required=False),
              )),
    ),
    body=_body_wave,
    engine=lambda spec: _ENGINE_WAVE,
)


# ============================================================ 2. projectile

def _body_projectile(spec: Mapping[str, Any]) -> str:
    return _shell('A projectile trajectory parabola with apex, range and time marked.')


_ENGINE_PROJECTILE = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var panel = document.getElementById('panel');
  var answer = document.getElementById('answer');
  // Gutters, not overlays: 44px left for the rotated height title and its ticks,
  // 38px below for the tick row and the axis title.
  var X0 = 92, X1 = 820, Y0 = 372, Y1 = 56;
  var xMax = +spec.x_max || 110;
  var yMax = +spec.y_max || 50;
  var g = +spec.g || 9.81;
  var toX = scale([0, xMax], [X0, X1]);
  var toY = scale([0, yMax], [Y0, Y1]);

  var chipR = UI.chip('range', 'Range', 'c');
  var chipH = UI.chip('apex', 'Apex height', 'b');
  var chipT = UI.chip('tof', 'Time of flight', 'e');
  var chipV = UI.chip('speed', 'Speed', 'a');

  var state = { angle: 45, speed: 20, pos: 35, index: 0, tries: 0,
                choice: null, committed: false, given: null };

  function traj(angle, speed) {
    var th = angle * Math.PI / 180;
    var vx = speed * Math.cos(th), vy = speed * Math.sin(th);
    var T = 2 * vy / g;
    var R = vx * T;
    var H = vy * vy / (2 * g);
    var pts = [], n = 140;
    for (var i = 0; i <= n; i++) {
      var t = T * i / n;
      pts.push([vx * t, vy * t - 0.5 * g * t * t, t]);
    }
    return { vx: vx, vy: vy, T: T, R: R, H: H, pts: pts };
  }

  // ---- static chrome -------------------------------------------------------
  var gGrid = svg('g', { 'data-series': 'grid' }, scene);
  for (var i = 0; i <= 10; i++) {
    svg('line', { x1: toX(i * xMax / 10), x2: toX(i * xMax / 10), y1: Y1, y2: Y0,
                  class: 'gridline' }, gGrid);
  }
  for (var j = 0; j <= 5; j++) {
    svg('line', { x1: X0, x2: X1, y1: toY(j * yMax / 5), y2: toY(j * yMax / 5),
                  class: 'gridline' }, gGrid);
  }
  var gAxes = svg('g', { 'data-series': 'axes' }, scene);
  svg('line', { x1: X0, x2: X1, y1: toY(0), y2: toY(0), class: 'axis' }, gAxes);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, gAxes);

  for (var t = 0; t <= 10; t += 2) {
    svg('text', { x: toX(t * xMax / 10), y: Y0 + 18, 'text-anchor': 'middle',
                  class: 'tick' }, gAxes).textContent = fmt(t * xMax / 10, 0);
  }
  svg('text', { x: X0, y: Y0 + 40, 'text-anchor': 'start', class: 'tick' },
      gAxes).textContent = spec.x_label || 'Horizontal distance (m)';

  for (var h = 0; h <= 5; h++) {
    svg('text', { x: X0 - 10, y: toY(h * yMax / 5) + 3.5, 'text-anchor': 'end',
                  class: 'tick' }, gAxes).textContent = fmt(h * yMax / 5, 0);
  }
  var cyP = (Y0 + Y1) / 2;
  svg('text', { x: X0 - 44, y: cyP, 'text-anchor': 'middle', class: 'tick',
                transform: 'rotate(-90 ' + (X0 - 44) + ' ' + cyP + ')' },
      gAxes).textContent = spec.y_label || 'Height (m)';

  // The landing point gets its own label in the bottom gutter, where it cannot
  // collide with the velocity vectors or with the tick row.
  var gFoot = svg('g', { 'data-series': 'annotation' }, scene);
  var rangeTxt = svg('text', { x: X1, y: Y0 + 40, 'text-anchor': 'middle', class: 'lbl' },
                     gFoot);

  var gPath = svg('g', { 'data-series': 'trajectory' }, scene);
  var pathMain = svg('path', { fill: 'none', stroke: colour('a'), 'stroke-width': 2.8 }, gPath);
  var pathGhost = svg('path', { fill: 'none', stroke: colour('e'), 'stroke-width': 2.2,
                                'stroke-dasharray': '6 5' }, gPath);
  var gMark = svg('g', { 'data-series': 'markers' }, scene);
  var apexDot = svg('circle', { r: 4.5, fill: colour('b') }, gMark);
  var rangeDot = svg('circle', { r: 4.5, fill: colour('c') }, gMark);
  var apexTxt = svg('text', { class: 'note' }, gMark);
  var ghostTxt = svg('text', { class: 'note', style: 'fill:' + colour('e') }, gMark);

  // The velocity components live in a fixed callout in the empty top-right corner,
  // keyed to the arrows drawn at the marker. Two labels chasing the marker put
  // themselves on top of the range label and the tick row at the landing point.
  var gV = svg('g', { 'data-series': 'velocity' }, scene);
  var arrowVx = svg('line', { stroke: colour('b'), 'stroke-width': 2 }, gV);
  var arrowVy = svg('line', { stroke: colour('d'), 'stroke-width': 2 }, gV);
  var arrowV = svg('line', { stroke: colour('c'), 'stroke-width': 2.4 }, gV);
  var dot = svg('circle', { r: 5, fill: colour('c'), stroke: '#fff', 'stroke-width': 1.6 }, gV);

  // Hidden until there is a trajectory to read, so it never sits empty on a task
  // that asks the learner to predict before the arc is revealed.
  var gBox = svg('g', { class: 'hidden' }, gV);
  var BX = X1 - 152, BY = Y1 + 8, BW = 140, BH = 60;
  svg('rect', { x: BX, y: BY, width: BW, height: BH, rx: 10,
                fill: colour('surface2'), stroke: colour('line'),
                'stroke-width': 1 }, gBox);
  svg('line', { x1: BX + 12, x2: BX + 30, y1: BY + 24, y2: BY + 24,
                stroke: colour('b'), 'stroke-width': 2.4 }, gBox);
  svg('line', { x1: BX + 12, x2: BX + 30, y1: BY + 44, y2: BY + 44,
                stroke: colour('d'), 'stroke-width': 2.4 }, gBox);
  var lblVx = svg('text', { x: BX + 38, y: BY + 28, class: 'note',
                            style: 'fill:' + colour('dim') }, gBox);
  var lblVy = svg('text', { x: BX + 38, y: BY + 48, class: 'note',
                            style: 'fill:' + colour('dim') }, gBox);

  // ---- panel ---------------------------------------------------------------
  var rows = {};
  function mk(key, label, min, max, step, unit) {
    var lab = el('label', { class: 'fld' }, panel);
    lab.appendChild(document.createTextNode(label));
    var inp = el('input', { type: 'range', min: min, max: max, step: step,
                            value: state[key], 'aria-label': label }, lab);
    var out = el('b', null, lab);
    rows[key] = { inp: inp, out: out, unit: unit, step: step };
    inp.addEventListener('input', function () {
      state[key] = +inp.value;
      out.textContent = fmt(+inp.value, step < 1 ? 1 : 0) + unit;
      launch(false);
    });
  }
  mk('angle', 'Launch angle', +spec.angle_min || 5, +spec.angle_max || 85, 1, '\u00b0');
  mk('speed', 'Launch speed', +spec.speed_min || 5, +spec.speed_max || 30, 0.5, ' m/s');
  mk('pos', 'Marker position', 0, 100, 1, '%');

  function setChoices(opts) {
    var box = document.getElementById('choices');
    clear(box);
    opts.forEach(function (o) {
      var b = el('button', { type: 'button', 'data-value': String(o) }, box);
      b.textContent = fmt(o, 0) + '\u00b0';
      b.addEventListener('click', function () {
        state.choice = +o;
        Array.prototype.forEach.call(box.children, function (c) {
          c.style.borderColor = ''; c.style.background = '';
        });
        b.style.borderColor = COLOURS.a; b.style.background = '#eef2f8';
      });
    });
  }

  function ch() { return (spec.challenges || [])[state.index] || null; }
  function hideAll() {
    pathMain.setAttribute('d', '');
    pathGhost.setAttribute('d', '');
    [apexDot, rangeDot, dot].forEach(function (n) { n.setAttribute('opacity', 0); });
    [apexTxt, rangeTxt, ghostTxt, lblVx, lblVy].forEach(function (n) {
      n.textContent = '';
    });
    arrowVx.setAttribute('opacity', 0); arrowVy.setAttribute('opacity', 0);
    arrowV.setAttribute('opacity', 0);
    gBox.classList.add('hidden');
    chipR.set('--'); chipH.set('--'); chipT.set('--'); chipV.set('--');
  }

  function pathFrom(tr, upto) {
    var d = '';
    var maxX = upto === undefined ? Infinity : upto;
    for (var i = 0; i < tr.pts.length; i++) {
      var p = tr.pts[i];
      if (p[0] > xMax || p[1] > yMax) { break; }
      d += (i ? 'L' : 'M') + fmt(toX(p[0]), 2) + ' ' + fmt(toY(Math.max(0, p[1])), 2) + ' ';
    }
    return d;
  }

  function annotate(tr) {
    var n = tr.pts.length;
    var k = Math.round(state.pos / 100 * (n - 1));
    var p = tr.pts[k];
    var x = clamp(toX(p[0]), X0, X1), y = clamp(toY(p[1]), Y1, Y0);
    dot.setAttribute('cx', x); dot.setAttribute('cy', y); dot.setAttribute('opacity', 1);
    var vy = tr.vy - g * p[2];
    var scalePx = 55 / Math.max(1, tr.vx + Math.abs(tr.vy));
    // The vectors are clamped to the plot: below the axis they used to run into
    // the tick row, which is where the "vy" label collided with a tick number.
    var tx = clamp(x + tr.vx * scalePx, X0, X1);
    var ty = clamp(y - vy * scalePx, Y1, Y0);
    arrowVx.setAttribute('x1', x); arrowVx.setAttribute('y1', y);
    arrowVx.setAttribute('x2', tx); arrowVx.setAttribute('y2', y);
    arrowVx.setAttribute('opacity', 1);
    arrowVy.setAttribute('x1', x); arrowVy.setAttribute('y1', y);
    arrowVy.setAttribute('x2', x); arrowVy.setAttribute('y2', ty);
    arrowVy.setAttribute('opacity', 1);
    arrowV.setAttribute('x1', x); arrowV.setAttribute('y1', y);
    arrowV.setAttribute('x2', tx); arrowV.setAttribute('y2', ty);
    arrowV.setAttribute('opacity', 0.9);
    lblVx.textContent = 'vx ' + fmt(tr.vx, 1) + ' m/s';
    lblVy.textContent = 'vy ' + fmt(vy, 1) + ' m/s';
    gBox.classList.remove('hidden');
    chipV.set(fmt(Math.sqrt(tr.vx * tr.vx + vy * vy), 1) + ' m/s');
  }

  function placeMarks(tr) {
    if (tr.R > xMax) {
      apexDot.setAttribute('opacity', 0); rangeDot.setAttribute('opacity', 0);
      apexTxt.textContent = ''; rangeTxt.textContent = '';
      return;
    }
    apexDot.setAttribute('cx', toX(tr.R / 2));
    apexDot.setAttribute('cy', toY(tr.H));
    apexDot.setAttribute('opacity', 1);
    rangeDot.setAttribute('cx', toX(tr.R));
    rangeDot.setAttribute('cy', toY(0));
    rangeDot.setAttribute('opacity', 1);
    apexTxt.setAttribute('x', clamp(toX(tr.R / 2) + 6, X0, X1 - 76));
    apexTxt.setAttribute('y', Math.max(Y1 + 14, toY(tr.H) - 6));
    apexTxt.textContent = 'apex ' + fmt(tr.H, 1) + ' m';
    // In the footer, centred on the landing point and never under the axis title.
    rangeTxt.setAttribute('x', clamp(toX(tr.R), X0 + 230, X1 - 60));
    rangeTxt.textContent = 'range ' + fmt(tr.R, 1) + ' m';
  }

  function launch(animate) {
    var tr = traj(state.angle, state.speed);
    pathMain.setAttribute('d', pathFrom(tr));
    placeMarks(tr);
    annotate(tr);
    chipR.set(fmt(tr.R, 1) + ' m');
    chipH.set(fmt(tr.H, 1) + ' m');
    chipT.set(fmt(tr.T, 2) + ' s');
    BRIDGE.readout({ angle_deg: state.angle, speed: state.speed,
                     range_m: +tr.R.toFixed(2), apex_m: +tr.H.toFixed(2),
                     tof_s: +tr.T.toFixed(3), g: g });
  }

  function load() {
    var c = ch();
    state.tries = 0; state.choice = null; state.committed = false; state.given = null;
    clear(document.getElementById('choices'));
    clear(answer);
    var check = document.getElementById('check');
    var next = document.getElementById('next');
    check.disabled = false; next.classList.add('hidden');
    document.getElementById('prompt').textContent = '';
    UI.feedback('');
    UI.progress(state.index, (spec.challenges || []).length);
    if (!c) { UI.say('Every task is complete.'); hideAll(); return; }
    if (c.kind === 'sandbox') {
      state.angle = +c.angle; state.speed = +c.speed;
      rows.angle.inp.disabled = false; rows.speed.inp.disabled = false;
      check.disabled = true; next.classList.remove('hidden');
      UI.say(c.text); sync(); launch(true); return;
    }
    state.angle = +c.angle; state.speed = +c.speed;
    rows.angle.inp.disabled = true; rows.speed.inp.disabled = true;
    hideAll(); sync();
    if (c.kind === 'predict_range') {
      var lab = el('label', { class: 'fld' }, answer);
      lab.appendChild(document.createTextNode('Your predicted range (m)'));
      el('input', { type: 'number', id: 'rangeInput', min: 0, step: '0.1',
                    'aria-label': 'Predicted range in metres', style: 'width:110px' }, lab);
      UI.say(c.text);
      document.getElementById('prompt').textContent =
        'Predict first, then Check reveals the arc. g = ' + fmt(g, 2) + ' m/s\u00b2.';
    } else if (c.kind === 'same_range') {
      setChoices(c.options || []);
      UI.say(c.text);
      document.getElementById('prompt').textContent =
        'Which other angle gives the same range?';
    }
  }

  function revealAnswer(tr) {
    pathMain.setAttribute('d', pathFrom(tr));
    placeMarks(tr);
    annotate(tr);
    chipR.set(fmt(tr.R, 1) + ' m'); chipH.set(fmt(tr.H, 1) + ' m');
    chipT.set(fmt(tr.T, 2) + ' s');
  }

  function finish(correct, detail) {
    state.committed = true;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    BRIDGE.outcome({ correct: correct, task: ch().id, kind: ch().kind,
                     tries: state.tries + (correct ? 1 : 0),
                     answer: detail.answer, detail: detail });
  }

  function check() {
    var c = ch();
    if (!c || state.committed || c.kind === 'sandbox') return;
    if (c.kind === 'predict_range') {
      var inp = document.getElementById('rangeInput');
      var val = inp ? parseFloat(inp.value) : NaN;
      if (!isFinite(val)) {
        UI.feedback('Enter your predicted range as a number of metres.', false);
        return;
      }
      var tr = traj(state.angle, state.speed);
      var tol = (+c.tol || 0.06) * tr.R;
      revealAnswer(tr);
      if (Math.abs(val - tr.R) <= tol) {
        UI.feedback('Correct: ' + fmt(tr.R, 1) + ' m. With v = ' + fmt(state.speed, 1)
          + ' m/s at ' + fmt(state.angle, 0) + '\u00b0, R = v\u00b2 sin(2\u03b8)/g = '
          + fmt(state.speed * state.speed, 1) + ' \u00d7 sin(' + fmt(2 * state.angle, 0)
          + '\u00b0)/' + fmt(g, 2) + ' = ' + fmt(tr.R, 1) + ' m. ' + (c.why || ''), true);
        finish(true, { answer: +tr.R.toFixed(2), guess: +val.toFixed(2),
                       angle: state.angle, speed: state.speed, why: c.why || '' });
      } else {
        state.tries += 1;
        if (state.tries >= __MAX_TRIES__) {
          UI.feedback('Third try, so here it is: ' + fmt(tr.R, 1) + ' m. '
            + 'Use R = v\u00b2 sin(2\u03b8)/g with v = ' + fmt(state.speed, 1)
            + ' m/s, \u03b8 = ' + fmt(state.angle, 0) + '\u00b0, g = ' + fmt(g, 2)
            + ' m/s\u00b2. ' + (c.why || ''), false);
          finish(false, { answer: +tr.R.toFixed(2), guess: +val.toFixed(2),
                          gave_up: true, angle: state.angle, speed: state.speed,
                          why: c.why || '' });
        } else {
          UI.feedback('Not that. Recompute sin(2\u03b8): at ' + fmt(state.angle, 0)
            + '\u00b0 the doubled angle is ' + fmt(2 * state.angle, 0)
            + '\u00b0. Check your arithmetic and try again.', false);
        }
      }
      return;
    }
    // same_range
    if (!state.choice && state.choice !== 0) {
      UI.feedback('Choose one of the offered angles first.', false);
      return;
    }
    var base = traj(state.angle, state.speed);
    var alt = traj(state.choice, state.speed);
    var tol2 = 0.03 * base.R;
    var correct = Math.abs(alt.R - base.R) <= tol2;
    pathMain.setAttribute('d', pathFrom(base));
    pathGhost.setAttribute('d', pathFrom(alt));
    placeMarks(base);
    annotate(base);
    ghostTxt.setAttribute('x', clamp(toX(alt.R / 2) + 6, X0, X1 - 96));
    ghostTxt.setAttribute('y', Math.max(Y1 + 14, toY(alt.H) - 6));
    ghostTxt.textContent = fmt(state.choice, 0) + '\u00b0 launch';
    chipR.set(fmt(base.R, 1) + ' m');
    chipH.set(fmt(base.H, 1) + ' m');
    chipT.set(fmt(base.T, 2) + ' s');
    if (correct) {
      UI.feedback('Correct. ' + fmt(state.angle, 0) + '\u00b0 and ' + fmt(state.choice, 0)
        + '\u00b0 are complementary (they add to 90\u00b0), so sin(2\u03b8) is the same '
        + 'and both give ' + fmt(base.R, 1) + ' m. ' + (c.why || ''), true);
      finish(true, { answer: state.choice, angle: state.angle, speed: state.speed,
                     range_m: +base.R.toFixed(2), why: c.why || '' });
    } else {
      state.tries += 1;
      if (state.tries >= __MAX_TRIES__) {
        UI.feedback('Here is the answer: ' + fmt(90 - state.angle, 0) + '\u00b0. It is '
          + 'the complement of ' + fmt(state.angle, 0) + '\u00b0 (they sum to 90\u00b0), '
          + 'so sin(2\u03b8) matches and the range is ' + fmt(base.R, 1) + ' m.', false);
        finish(false, { answer: 90 - state.angle, angle: state.angle, speed: state.speed,
                        gave_up: true, why: c.why || '' });
      } else {
        UI.feedback('That angle gives ' + fmt(alt.R, 1) + ' m, not ' + fmt(base.R, 1)
          + ' m. Look for the angle whose doubled sine matches. Try again.', false);
      }
    }
  }

  function sync() {
    ['angle', 'speed', 'pos'].forEach(function (k) {
      rows[k].inp.value = state[k];
      rows[k].out.textContent = fmt(state[k], rows[k].step < 1 ? 1 : 0) + rows[k].unit;
    });
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('next').addEventListener('click', function () {
    state.index += 1; load();
  });
  document.getElementById('reset').addEventListener('click', function () {
    var c = ch();
    if (c && (c.kind === 'predict_range' || c.kind === 'same_range')) {
      state.choice = null; load();
    } else { load(); }
  });

  sync();
  load();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


PROJECTILE = Archetype(
    id='projectile',
    title='Projectile motion',
    blurb='Set the launch angle and speed, then predict the range before you see the arc.',
    interaction='set angle and speed; predict the range, or find the angle with the same range',
    subjects=('science', 'physics', 'mathematics'),
    tags=('kinematics', 'projectiles', 'parabola', 'vectors', 'graphs'),
    reference='PhET Projectile Motion; ExploreLearning Gizmos Feed the Monkey / '
              'Projectile Motion',
    telemetry='One outcome per task: whether the predicted range was within tolerance, or '
              'whether the complementary angle was identified, with the true range, the '
              'angle and speed, and the tries taken.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('x_label', 'text', 'Horizontal axis label.', required=False),
        Field('y_label', 'text', 'Vertical axis label.', required=False),
        Field('x_max', 'float', 'Horizontal axis maximum, in metres.',
              minimum=10, maximum=2000),
        Field('y_max', 'float', 'Vertical axis maximum, in metres.',
              minimum=5, maximum=1000),
        Field('g', 'float', 'Gravitational field strength, in m/s squared.',
              minimum=0.1, maximum=30),
        Field('angle_min', 'float', 'Smallest launch angle, in degrees.',
              minimum=1, maximum=89),
        Field('angle_max', 'float', 'Largest launch angle, in degrees.',
              minimum=1, maximum=89),
        Field('speed_min', 'float', 'Smallest launch speed, in m/s.',
              minimum=1, maximum=100),
        Field('speed_max', 'float', 'Largest launch speed, in m/s.',
              minimum=1, maximum=100),
        Field('challenges', 'table',
              'One row per task. kind="sandbox" is free play; kind="predict_range" hides '
              'the arc and asks for a numeric range; kind="same_range" asks which of the '
              'offered angles gives the same range.',
              minimum_items=1, maximum_items=12,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this task.'),
                  Field('kind', 'text', 'What the task asks for.',
                        choices=('sandbox', 'predict_range', 'same_range')),
                  Field('text', 'text', 'The question, in one sentence.'),
                  Field('angle', 'float', 'Launch angle for this task, in degrees.',
                        required=False, minimum=1, maximum=89),
                  Field('speed', 'float', 'Launch speed for this task, in m/s.',
                        required=False, minimum=1, maximum=100),
                  Field('tol', 'float', 'Relative tolerance for a numeric prediction '
                        '(0.06 is six per cent).', required=False, minimum=0.001,
                        maximum=0.5),
                  Field('options', 'list', 'Offered angles, in degrees, for a '
                        'same_range task.', required=False,
                        minimum_items=2, maximum_items=6),
                  Field('why', 'text', 'The reasoning revealed after the answer.',
                        required=False),
              )),
    ),
    body=_body_projectile,
    engine=lambda spec: _ENGINE_PROJECTILE,
)


# ============================================================ 3. punnett

def _body_punnett(spec: Mapping[str, Any]) -> str:
    return _shell('A Punnett square showing the offspring of two parents.')


_ENGINE_PUNNETT = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var panel = document.getElementById('panel');
  var traits = spec.traits || [];
  var T = traits.length;
  // The square is the whole point of the page, so it takes the left two-thirds of
  // the canvas at its natural size and the derived ratio gets a card beside it.
  // Both live inside the card's gutters: the parent labels sit outside the grid.
  var TOP = 66, SQ = 336;
  var LFT = 96, RGT = LFT + SQ;          // 96 .. 432
  var PX = 468, PW = 366, PY = TOP, PH = SQ;  // the ratio card: 468 .. 834

  var chipG1 = UI.chip('gam1', 'Gametes parent 1', 'a');
  var chipG2 = UI.chip('gam2', 'Gametes parent 2', 'b');
  var chipRatio = UI.chip('ratio', 'Phenotype ratio', 'c');
  var chipOff = UI.chip('off', 'Offspring', 'e');

  var state = { p1: '', p2: '', index: 0, tries: 0, choice: null, committed: false };

  function pairOrder(a, b) {
    if (a === b) return a + b;
    var ua = a === a.toUpperCase(), ub = b === b.toUpperCase();
    if (ua !== ub) return ua ? a + b : b + a;
    return a < b ? a + b : b + a;
  }
  function alleles(g, t) { return [g.charAt(2 * t), g.charAt(2 * t + 1)]; }
  function gametes(g) {
    var out = [''];
    for (var t = 0; t < T; t++) {
      var al = alleles(g, t), next = [];
      for (var i = 0; i < out.length; i++) {
        next.push(out[i] + al[0]);
        next.push(out[i] + al[1]);
      }
      out = next;
    }
    return out;
  }
  function combine(a, b) {
    var s = '';
    for (var t = 0; t < T; t++) s += pairOrder(a.charAt(t), b.charAt(t));
    return s;
  }
  // A full genotype string -> the canonical form used as the square's cell text.
  function canonGeno(g) {
    var s = '';
    for (var t = 0; t < T; t++) {
      var al = alleles(g, t);
      s += pairOrder(al[0], al[1]);
    }
    return s;
  }
  function rank(tr, a, b) {
    var D = tr.dominant_letter, R = tr.recessive_letter;
    if (tr.mode === 'incomplete') {
      if (a === D && b === D) return 0;
      if (a === R && b === R) return 2;
      return 1;
    }
    return (a === R && b === R) ? 2 : 0;
  }
  function phenoKey(g) {
    var k = '';
    for (var t = 0; t < T; t++) {
      var al = alleles(g, t);
      k += String(rank(traits[t], al[0], al[1]));
    }
    return k;
  }
  function phenoLabel(key) {
    var parts = [];
    for (var t = 0; t < T; t++) {
      var r = +key.charAt(t);
      parts.push(r === 0 ? traits[t].dominant_label
              : (r === 2 ? traits[t].recessive_label
                         : (traits[t].hetero_label || traits[t].dominant_label)));
    }
    return parts.join(' / ');
  }
  function gcd(a, b) { a = Math.abs(a); b = Math.abs(b); while (b) { var t = b; b = a % b; a = t; } return a || 1; }
  function reduce(counts) {
    var g = counts.reduce(function (a, b) { return gcd(a, b); });
    return counts.map(function (c) { return c / g; });
  }
  function ratioString(map) {
    var keys = Object.keys(map).sort();
    var counts = keys.map(function (k) { return map[k]; });
    var r = reduce(counts);
    return { keys: keys, counts: counts, text: r.join(':') };
  }
  function cross(p1, p2) {
    var g1 = gametes(p1), g2 = gametes(p2);
    var cells = [], pheno = {}, geno = {};
    for (var i = 0; i < g1.length; i++) {
      var row = [];
      for (var j = 0; j < g2.length; j++) {
        var cell = combine(g1[i], g2[j]);
        row.push(cell);
        var pk = phenoKey(cell);
        pheno[pk] = (pheno[pk] || 0) + 1;
        geno[cell] = (geno[cell] || 0) + 1;
      }
      cells.push(row);
    }
    return { g1: g1, g2: g2, cells: cells, pheno: pheno, geno: geno,
             total: g1.length * g2.length };
  }

  // ---- panel ---------------------------------------------------------------
  function genoOptions() {
    var out = [''];
    traits.forEach(function (tr) {
      var D = tr.dominant_letter, R = tr.recessive_letter;
      var pairs = [D + D, pairOrder(D, R), R + R], next = [];
      out.forEach(function (pre) { pairs.forEach(function (p) { next.push(pre + p); }); });
      out = next;
    });
    return out;
  }
  function mkSelect(label, onChange) {
    var lab = el('label', { class: 'fld' }, panel);
    lab.appendChild(document.createTextNode(label));
    var sel = el('select', { 'aria-label': label }, lab);
    genoOptions().forEach(function (o) {
      var opt = el('option', { value: o }, sel);
      opt.textContent = o;
    });
    sel.addEventListener('change', function () { onChange(sel.value); });
    return sel;
  }
  var sel1 = mkSelect('Parent 1 genotype', function (v) { state.p1 = v; draw(); });
  var sel2 = mkSelect('Parent 2 genotype', function (v) { state.p2 = v; draw(); });
  if (!state.p1) { state.p1 = genoOptions()[1]; }
  if (!state.p2) { state.p2 = genoOptions()[1]; }

  function setChoices(opts) {
    var box = document.getElementById('choices');
    clear(box);
    opts.forEach(function (o) {
      var b = el('button', { type: 'button', 'data-value': String(o) }, box);
      b.textContent = String(o);
      b.addEventListener('click', function () {
        state.choice = String(o);
        Array.prototype.forEach.call(box.children, function (c) {
          c.style.borderColor = ''; c.style.background = '';
        });
        b.style.borderColor = COLOURS.a; b.style.background = '#eef2f8';
      });
    });
  }

  // ---- square --------------------------------------------------------------
  // The square fills the left two-thirds of the card: a header row and column for
  // the gametes, then one cell per offspring tinted by phenotype, so the square
  // and the ratio card beside it are visibly the same groups. Parent genotypes sit
  // in the gutters outside the grid, never on it.
  var PALETTE = ['a', 'b', 'c', 'd', 'e'];

  function draw() {
    clear(scene);
    var p1 = state.p1, p2 = state.p2;
    if (!p1 || !p2) return;
    var c = cross(p1, p2);
    var n = c.g1.length;
    var cell = SQ / (n + 1);
    var hidden = !!state.hidden;
    var rs = ratioString(c.pheno);
    var keys = rs.keys;
    var tone = {};
    keys.forEach(function (k, i) { tone[k] = PALETTE[i % PALETTE.length]; });
    var fs = Math.min(19, cell * 0.3);

    var gGrid = svg('g', { 'data-series': 'square' }, scene);
    for (var r = 0; r <= n; r++) {
      for (var q = 0; q <= n; q++) {
        var x = LFT + q * cell, y = TOP + r * cell;
        var head = (r === 0 || q === 0);
        var body = (r > 0 && q > 0);
        if (body && hidden) continue;   // one waiting well instead of a wall of "?"
        var key = body ? phenoKey(c.cells[r - 1][q - 1]) : '';
        var fill = !body ? colour('surface2') : colour(tone[key] + '-soft');
        svg('rect', { x: x, y: y, width: cell, height: cell, fill: fill,
                      stroke: colour('line'), 'stroke-width': 1 }, gGrid);
        if (body) {
          var t = svg('text', { x: x + cell / 2, y: y + cell / 2 + fs * 0.35,
                                'text-anchor': 'middle', class: 'lbl',
                                style: 'font-size:' + fs + 'px' }, gGrid);
          t.textContent = c.cells[r - 1][q - 1];
        } else if (!(r === 0 && q === 0)) {
          var gtxt = svg('text', { x: x + cell / 2, y: y + cell / 2 + fs * 0.28,
                                   'text-anchor': 'middle', class: 'lbl',
                                   style: 'font-size:' + (fs * 0.86) + 'px;fill:'
                                          + colour('dim') }, gGrid);
          gtxt.textContent = (r === 0) ? c.g2[q - 1] : c.g1[r - 1];
        }
      }
    }
    if (hidden) {
      // The offspring are the unknown: one dashed well with a single mark reads as
      // "this is where the cross goes" rather than sixteen identical question marks.
      var bx = LFT + cell, by = TOP + cell, bw = SQ - cell, bh = SQ - cell;
      svg('rect', { x: bx, y: by, width: bw, height: bh, fill: colour('surface2'),
                    stroke: colour('edge'), 'stroke-width': 1.6,
                    'stroke-dasharray': '8 7' }, gGrid);
      svg('text', { x: bx + bw / 2, y: by + bh / 2 + 2, 'text-anchor': 'middle',
                    class: 'lbl',
                    style: 'font-size:40px;fill:' + colour('faint') }, gGrid)
        .textContent = '?';
      svg('text', { x: bx + bw / 2, y: by + bh / 2 + 34, 'text-anchor': 'middle',
                    class: 'note' }, gGrid).textContent = 'offspring genotypes';
    }
    svg('rect', { x: LFT, y: TOP, width: SQ, height: SQ, rx: 10, fill: 'none',
                  stroke: colour('edge'), 'stroke-width': 1.6 }, gGrid);

    var p1x = LFT - 34, p1y = TOP + SQ / 2;
    svg('text', { x: p1x, y: p1y, 'text-anchor': 'middle', class: 'note',
                  transform: 'rotate(-90 ' + p1x + ' ' + p1y + ')' }, gGrid)
      .textContent = 'Parent 1 \u00b7 ' + p1;
    svg('text', { x: LFT + SQ / 2, y: TOP - 18, 'text-anchor': 'middle',
                  class: 'note' }, gGrid).textContent = 'Parent 2 \u00b7 ' + p2;

    // ---- the derived ratio, as a card beside the square ---------------------
    var gPanel = svg('g', { 'data-series': 'ratio' }, scene);
    svg('rect', { x: PX, y: PY, width: PW, height: PH, rx: 14,
                  fill: colour('surface2'), stroke: colour('line'),
                  'stroke-width': 1 }, gPanel);
    svg('text', { x: PX + 22, y: PY + 34, class: 'note',
                  style: 'font-size:10px;font-weight:700;letter-spacing:.13em;fill:'
                         + colour('faint') }, gPanel).textContent = 'PHENOTYPE RATIO';
    svg('text', { x: PX + 22, y: PY + 82, class: 'lbl',
                  style: 'font-size:32px;font-weight:700;letter-spacing:-.01em' },
        gPanel).textContent = hidden ? '?' : rs.text;
    svg('line', { x1: PX + 22, x2: PX + PW - 22, y1: PY + 102, y2: PY + 102,
                  stroke: colour('line'), 'stroke-width': 1 }, gPanel);

    var barY = PY + PH - 72, barX = PX + 22, barW = PW - 44, barH = 12;
    var rowsTop = PY + 138, rowsBot = barY - 28;
    var step = keys.length > 1 ? Math.min(48, (rowsBot - rowsTop) / (keys.length - 1)) : 0;
    keys.forEach(function (k, i) {
      var y = rowsTop + i * step;
      svg('circle', { cx: PX + 28, cy: y - 4, r: 5,
                      fill: hidden ? colour('edge') : colour(tone[k]) }, gPanel);
      svg('text', { x: PX + 42, y: y, class: 'lbl' }, gPanel).textContent = phenoLabel(k);
      svg('text', { x: PX + PW - 22, y: y, 'text-anchor': 'end', class: 'note',
                    style: 'fill:' + colour('dim') }, gPanel)
        .textContent = hidden ? '\u2014' : rs.counts[i] + ' / ' + c.total;
    });

    // One bar, split in proportion, is the ratio itself rather than a restatement.
    svg('rect', { x: barX, y: barY, width: barW, height: barH, rx: 6,
                  fill: colour('surface3') }, gPanel);
    if (!hidden) {
      var defs = svg('defs', {}, scene);
      var clip = svg('clipPath', { id: 'ratio-clip' }, defs);
      svg('rect', { x: barX, y: barY, width: barW, height: barH, rx: 6 }, clip);
      var gBar = svg('g', { 'clip-path': 'url(#ratio-clip)' }, gPanel);
      var acc = 0;
      keys.forEach(function (k, i) {
        var w = barW * rs.counts[i] / c.total;
        svg('rect', { x: barX + acc, y: barY, width: w, height: barH,
                      fill: colour(tone[k]) }, gBar);
        acc += w;
      });
    }
    svg('text', { x: PX + 22, y: barY + barH + 20, class: 'note' }, gPanel)
      .textContent = c.total + ' offspring, ' + keys.length + ' phenotypes';

    chipG1.set(c.g1.join(', '));
    chipG2.set(c.g2.join(', '));
    chipOff.set(String(c.total));
    var bits = [];
    keys.forEach(function (k, i) {
      bits.push(phenoLabel(k) + ' ' + rs.counts[i]);
    });
    if (hidden) { chipRatio.set('--'); }
    else {
      chipRatio.set(rs.text);
      BRIDGE.readout({ parent1: p1, parent2: p2, gametes1: c.g1, gametes2: c.g2,
                       ratio: rs.text, offspring: c.total,
                       phenotypes: bits });
    }
  }

  function ch() { return (spec.challenges || [])[state.index] || null; }

  function load() {
    var c = ch();
    state.tries = 0; state.choice = null; state.committed = false;
    clear(document.getElementById('choices'));
    var check = document.getElementById('check');
    var next = document.getElementById('next');
    check.disabled = false; next.classList.add('hidden');
    document.getElementById('prompt').textContent = '';
    UI.feedback('');
    UI.progress(state.index, (spec.challenges || []).length);
    if (!c) { UI.say('Every task is complete.'); return; }
    state.hidden = c.kind !== 'sandbox';
    if (c.kind === 'build') {
      sel1.disabled = false; sel2.disabled = false;
      if (c.parent1) { state.p1 = c.parent1; }
      if (c.parent2) { state.p2 = c.parent2; }
      UI.say(c.text);
      document.getElementById('prompt').textContent =
        'Target ratio: ' + (c.target || '') + '. Choose both parents, then Check.';
    } else {
      state.p1 = c.parent1; state.p2 = c.parent2;
      sel1.value = state.p1; sel2.value = state.p2;
      sel1.disabled = true; sel2.disabled = true;
      if (c.kind === 'ratio') {
        setChoices(c.options || []);
        UI.say(c.text);
        document.getElementById('prompt').textContent =
          'Predict the ratio, then Check.';
      } else {
        setChoices(c.options || []);
        UI.say(c.text);
        document.getElementById('prompt').textContent =
          'Predict the probability, then Check.';
      }
    }
    sel1.value = state.p1; sel2.value = state.p2;
    draw();
  }

  function frac(n, d) {
    var g = gcd(n, d);
    n = n / g; d = d / g;
    return d === 1 ? String(n) : n + '/' + d;
  }

  function finish(correct, detail) {
    state.committed = true;
    state.hidden = false;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    draw();
    BRIDGE.outcome({ correct: correct, task: ch().id, kind: ch().kind,
                     tries: state.tries + (correct ? 1 : 0),
                     answer: detail.answer, detail: detail });
  }

  function check() {
    var c = ch();
    if (!c || state.committed || c.kind === 'sandbox') return;
    var cr = cross(state.p1, state.p2);
    var rs = ratioString(cr.pheno);
    if (c.kind === 'build') {
      if (rs.text === (c.target || '')) {
        UI.feedback('Correct. ' + state.p1 + ' \u00d7 ' + state.p2 + ' gives a '
          + rs.text + ' phenotype ratio. ' + (c.why || ''), true);
        finish(true, { answer: c.target, ratio: rs.text, parent1: state.p1,
                       parent2: state.p2, why: c.why || '' });
      } else {
        state.tries += 1;
        if (state.tries >= __MAX_TRIES__) {
          UI.feedback('Third try, so here is the answer: ' + (c.why || 'see the revealed '
            + 'square') + ' This cross gives ' + rs.text + '.', false);
          finish(false, { answer: c.target, ratio: rs.text, gave_up: true,
                          parent1: state.p1, parent2: state.p2, why: c.why || '' });
        } else {
          UI.feedback('This cross gives ' + rs.text + ', not ' + (c.target || '')
            + '. Think about how many gamete types each parent makes. Try again.', false);
        }
      }
      return;
    }
    if (!state.choice) {
      UI.feedback('Choose one of the offered answers first.', false);
      return;
    }
    if (c.kind === 'ratio') {
      if (state.choice === rs.text) {
        UI.feedback('Correct: ' + rs.text + '. ' + state.p1 + ' \u00d7 ' + state.p2
          + ' makes ' + cr.g1.length + ' \u00d7 ' + cr.g2.length + ' = ' + cr.total
          + ' equally likely offspring. ' + (c.why || ''), true);
        finish(true, { answer: rs.text, ratio: rs.text, parent1: state.p1,
                       parent2: state.p2, why: c.why || '' });
      } else {
        state.tries += 1;
        if (state.tries >= __MAX_TRIES__) {
          UI.feedback('Here is the answer: ' + rs.text + '. ' + (c.why || ''), false);
          finish(false, { answer: rs.text, ratio: rs.text, gave_up: true,
                          parent1: state.p1, parent2: state.p2, why: c.why || '' });
        } else {
          UI.feedback('Not that. Count how many offspring show each phenotype out of '
            + cr.total + ', then reduce. Try again.', false);
        }
      }
      return;
    }
    // probability
    var ask = c.ask || '';
    var canonical = canonGeno(ask);
    var hits = cr.geno[canonical] || 0;
    var correct = frac(hits, cr.total);
    if (state.choice === correct) {
      UI.feedback('Correct: ' + correct + '. ' + hits + ' of the ' + cr.total
        + ' equally likely offspring are ' + canonical + '. ' + (c.why || ''), true);
      finish(true, { answer: correct, genotype: canonical, parent1: state.p1,
                     parent2: state.p2, why: c.why || '' });
    } else {
      state.tries += 1;
      if (state.tries >= __MAX_TRIES__) {
        UI.feedback('Here is the answer: ' + correct + ' (' + hits + ' of ' + cr.total
          + ' offspring are ' + canonical + '). ' + (c.why || ''), false);
        finish(false, { answer: correct, genotype: canonical, gave_up: true,
                        parent1: state.p1, parent2: state.p2, why: c.why || '' });
      } else {
        UI.feedback('Not that. Count the squares showing ' + canonical + ' out of all '
          + cr.total + ' and write it as a fraction. Try again.', false);
      }
    }
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('next').addEventListener('click', function () {
    state.index += 1; load();
  });
  document.getElementById('reset').addEventListener('click', function () { load(); });

  load();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


PUNNETT = Archetype(
    id='punnett',
    title='Punnett square',
    blurb='Cross two parents and read the offspring genotypes and phenotype ratio.',
    interaction='choose the parents; the square and ratio are derived from them',
    subjects=('science', 'biology'),
    tags=('genetics', 'inheritance', 'probability', 'punnett-square', 'dominance'),
    reference='ExploreLearning Gizmos Mouse Genetics / Chicken Genetics; standard '
              'Punnett-square genetics',
    telemetry='One outcome per task: whether the phenotype ratio or genotype probability '
              'was right, or whether the chosen parents met the target ratio, with the '
              'parents used and the computed ratio.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('traits', 'table',
              'One or two traits. Letters are the alleles; for dominant/recessive use an '
              'uppercase dominant letter and its lowercase recessive (A/a); for incomplete '
              'dominance use two distinct uppercase letters (R/W) and give the heterozygote '
              'its own label.',
              minimum_items=1, maximum_items=2,
              item_fields=(
                  Field('gene', 'text', 'Short name for the trait, e.g. "Flower colour".'),
                  Field('mode', 'text', 'How the heterozygote is expressed.',
                        choices=('dominant', 'incomplete')),
                  Field('dominant_letter', 'text', 'The dominant (or first) allele letter.'),
                  Field('recessive_letter', 'text', 'The recessive (or second) allele letter.'),
                  Field('dominant_label', 'text', 'Phenotype of the homozygous dominant.'),
                  Field('recessive_label', 'text', 'Phenotype of the homozygous recessive.'),
                  Field('hetero_label', 'text', 'Phenotype of the heterozygote, for '
                        'incomplete dominance.', required=False),
              )),
        Field('challenges', 'table',
              'One row per task. kind="ratio" asks for the phenotype ratio from offered '
              'options; kind="probability" asks for the chance of a named genotype; '
              'kind="build" asks the learner to choose parents that give a target ratio.',
              minimum_items=1, maximum_items=12,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this task.'),
                  Field('kind', 'text', 'What the task asks for.',
                        choices=('ratio', 'probability', 'build')),
                  Field('text', 'text', 'The question, in one sentence.'),
                  Field('parent1', 'text', 'Parent 1 genotype, e.g. "AaBb".',
                        required=False),
                  Field('parent2', 'text', 'Parent 2 genotype, e.g. "AaBb".',
                        required=False),
                  Field('options', 'list', 'Offered answers.', required=False,
                        minimum_items=2, maximum_items=8),
                  Field('target', 'text', 'For a build task: the ratio the parents must '
                        'produce, e.g. "3:1".', required=False),
                  Field('ask', 'text', 'For a probability task: the genotype asked about, '
                        'e.g. "Aabb".', required=False),
                  Field('why', 'text', 'The reasoning revealed after the answer.',
                        required=False),
              )),
    ),
    body=_body_punnett,
    engine=lambda spec: _ENGINE_PUNNETT,
)


# ============================================================ 4. orbit_gravity

def _body_orbit(spec: Mapping[str, Any]) -> str:
    return _shell('A satellite orbiting a central mass, with the escape speed marked.')


_ENGINE_ORBIT = r"""
function build(root, spec) {
  var scene = document.getElementById('scene');
  var panel = document.getElementById('panel');
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 44;
  var cx = (X0 + X1) / 2, cy = (Y0 + Y1) / 2;
  var G = 6.674e-11;
  var r0 = +spec.orbit_radius || 7.0e6;
  var Rbody = +spec.body_radius || 6.371e6;
  var viewR = +spec.view_radius || 2.1e7;
  var S = Math.min((X1 - X0) / 2, (Y0 - Y1) / 2) / viewR;

  var chipV = UI.chip('speed', 'Satellite speed', 'a');
  var chipEsc = UI.chip('esc', 'Escape speed', 'd');
  var chipS = UI.chip('status', 'Orbit', 'c');

  var state = { mass: 5.972, speed: 7.55, index: 0, tries: 0, choice: null, committed: false };

  function mu(mass) { return G * mass * 1e24; }
  function vcirc(mass) { return Math.sqrt(mu(mass) / r0); }
  function vesc(mass) { return Math.sqrt(2 * mu(mass) / r0); }
  function classify(mass, v0) {
    var m = mu(mass);
    var eps = v0 * v0 / 2 - m / r0;
    var h = r0 * v0;
    if (eps >= 0) return 'escape';
    var a = -m / (2 * eps);
    var e = Math.sqrt(Math.max(0, 1 + 2 * eps * h * h / (m * m)));
    var rp = a * (1 - e);
    if (rp < Rbody) return 'crash';
    return 'closed';
  }
  function simulate(mass, v0) {
    var m = mu(mass);
    var r = [r0, 0], v = [0, v0];
    var T = 2 * Math.PI * Math.sqrt(r0 * r0 * r0 / m);
    var dt = T / 700, maxSteps = 2200;
    var pts = [];
    for (var i = 0; i < maxSteps; i++) {
      var d2 = r[0] * r[0] + r[1] * r[1];
      var d = Math.sqrt(d2);
      if (d < Rbody) { pts.push([r[0], r[1]]); return { pts: pts, hit: 'crash', d: d }; }
      if (d > viewR * 1.7) { pts.push([r[0], r[1]]); return { pts: pts, hit: 'escape', d: d }; }
      var acc = -m / (d2 * d);
      v[0] += acc * r[0] * dt; v[1] += acc * r[1] * dt;
      r[0] += v[0] * dt; r[1] += v[1] * dt;
      if (i % 3 === 0) pts.push([r[0], r[1]]);
    }
    return { pts: pts, hit: 'closed', d: Math.sqrt(r[0] * r[0] + r[1] * r[1]) };
  }
  function px(x) { return cx + x * S; }
  function py(y) { return cy - y * S; }

  // ---- static chrome -------------------------------------------------------
  var gGrid = svg('g', { 'data-series': 'grid' }, scene);
  for (var k = 1; k <= 3; k++) {
    svg('circle', { cx: cx, cy: cy, r: k * viewR / 3 * S, fill: 'none',
                    stroke: colour('grid'), 'stroke-width': 1 }, gGrid);
  }
  svg('line', { x1: X0, x2: X1, y1: cy, y2: cy, stroke: colour('grid'),
                'stroke-width': 1 }, gGrid);
  svg('line', { x1: cx, x2: cx, y1: Y1, y2: Y0, stroke: colour('grid'),
                'stroke-width': 1 }, gGrid);
  // The ring scale, in the empty top-right corner rather than across the axis
  // where it used to read as an axis label.
  svg('text', { x: X1 - 6, y: Y1 + 16, 'text-anchor': 'end', class: 'note' }, gGrid)
    .textContent = 'Rings every ' + fmt(viewR / 3 / 1e6, 0) + ' \u00d7 10\u2076 m';

  var gBody = svg('g', { 'data-series': 'central-body' }, scene);
  var bodyR = Math.max(4, Rbody * S);
  var body = svg('circle', { cx: cx, cy: cy, r: bodyR,
                             fill: colour('d'), stroke: colour('edge'),
                             'stroke-width': 1 }, gBody);
  // Inside the body, so it cannot sit on the orbit that hugs the surface.
  svg('text', { x: cx, y: cy + 4, 'text-anchor': 'middle', class: 'note',
                style: 'fill:#fff;font-size:10px' }, gBody).textContent = 'Central body';
  var gOrbit = svg('g', { 'data-series': 'orbit' }, scene);
  var path = svg('path', { fill: 'none', stroke: colour('a'), 'stroke-width': 2.2 }, gOrbit);
  var sat = svg('circle', { r: 5, fill: colour('c'), stroke: '#fff', 'stroke-width': 1.6 },
                gOrbit);
  var startDot = svg('circle', { r: 4, fill: 'none', stroke: colour('b'),
                                 'stroke-width': 2 }, gOrbit);

  // ---- panel ---------------------------------------------------------------
  var rows = {};
  function mk(key, label, min, max, step, unit) {
    var lab = el('label', { class: 'fld' }, panel);
    lab.appendChild(document.createTextNode(label));
    var inp = el('input', { type: 'range', min: min, max: max, step: step,
                            value: state[key], 'aria-label': label }, lab);
    var out = el('b', null, lab);
    rows[key] = { inp: inp, out: out, unit: unit, step: step };
    inp.addEventListener('input', function () {
      state[key] = +inp.value;
      out.textContent = fmt(+inp.value, step < 1 ? 2 : 1) + unit;
      draw();
    });
  }
  mk('mass', 'Central mass', +spec.mass_min || 1, +spec.mass_max || 20, 0.1, ' \u00d7 10\u00b2\u2074 kg');
  mk('speed', 'Launch speed', +spec.speed_min || 2, +spec.speed_max || 16, 0.05, ' km/s');

  function sync() {
    ['mass', 'speed'].forEach(function (key) {
      rows[key].inp.value = state[key];
      rows[key].out.textContent = fmt(state[key], rows[key].step < 1 ? 2 : 1) + rows[key].unit;
    });
  }

  function setChoices(opts) {
    var box = document.getElementById('choices');
    clear(box);
    opts.forEach(function (o) {
      var b = el('button', { type: 'button', 'data-value': o.value }, box);
      b.textContent = o.label;
      b.addEventListener('click', function () {
        state.choice = o.value;
        Array.prototype.forEach.call(box.children, function (c) {
          c.style.borderColor = ''; c.style.background = '';
        });
        b.style.borderColor = COLOURS.a; b.style.background = '#eef2f8';
      });
    });
  }

  function draw() {
    var v0 = state.speed * 1000;
    var sim = simulate(state.mass, v0);
    var d = '';
    for (var i = 0; i < sim.pts.length; i++) {
      d += (i ? 'L' : 'M') + fmt(px(sim.pts[i][0]), 2) + ' ' + fmt(py(sim.pts[i][1]), 2) + ' ';
    }
    path.setAttribute('d', d);
    var last = sim.pts[sim.pts.length - 1];
    sat.setAttribute('cx', px(last[0])); sat.setAttribute('cy', py(last[1]));
    startDot.setAttribute('cx', px(r0)); startDot.setAttribute('cy', py(0));
    var kind = classify(state.mass, v0);
    chipV.set(fmt(state.speed, 2) + ' km/s');
    chipEsc.set(fmt(vesc(state.mass) / 1000, 2) + ' km/s');
    chipS.set(kind);
    BRIDGE.readout({ central_mass_1e24kg: state.mass, speed_kms: state.speed,
                     escape_kms: +(vesc(state.mass) / 1000).toFixed(3),
                     circular_kms: +(vcirc(state.mass) / 1000).toFixed(3),
                     status: kind });
  }

  function hideAll() {
    path.setAttribute('d', '');
    sat.setAttribute('opacity', 0); startDot.setAttribute('opacity', 0);
    chipV.set('--'); chipEsc.set('--'); chipS.set('--');
  }

  function ch() { return (spec.challenges || [])[state.index] || null; }

  function load() {
    var c = ch();
    state.tries = 0; state.choice = null; state.committed = false;
    clear(document.getElementById('choices'));
    var check = document.getElementById('check');
    var next = document.getElementById('next');
    check.disabled = false; next.classList.add('hidden');
    document.getElementById('prompt').textContent = '';
    UI.feedback('');
    UI.progress(state.index, (spec.challenges || []).length);
    if (!c) { UI.say('Every task is complete.'); hideAll(); return; }
    state.mass = +c.mass; state.speed = +c.speed;
    if (c.kind === 'sandbox') {
      rows.mass.inp.disabled = false; rows.speed.inp.disabled = false;
      check.disabled = true; next.classList.remove('hidden');
      UI.say(c.text); sync(); draw(); return;
    }
    if (c.kind === 'classify') {
      rows.mass.inp.disabled = true; rows.speed.inp.disabled = true;
      hideAll(); sync();
      setChoices([{ value: 'closed', label: 'Closed orbit' },
                  { value: 'crash', label: 'Crash' },
                  { value: 'escape', label: 'Escape' }]);
      UI.say(c.text);
      document.getElementById('prompt').textContent =
        'Predict the fate of the satellite, then Check runs the orbit.';
    } else {
      rows.mass.inp.disabled = true; rows.speed.inp.disabled = false;
      sync(); draw();
      UI.say(c.text);
      document.getElementById('prompt').textContent = c.target === 'circular'
        ? 'Find the speed for a circular orbit (within '
          + fmt((+c.tol || 0.03) * 100, 0) + '%).'
        : (c.target === 'escape' ? 'Find a speed that escapes.'
                                 : 'Find a speed that crashes into the body.');
    }
  }

  function explain(kind) {
    if (kind === 'escape') {
      return 'The speed is at or above the escape speed, so the total energy is zero or '
        + 'positive and the satellite never returns.';
    }
    if (kind === 'crash') {
      return 'It is bound but the orbit dips inside the body: the periapsis is below the '
        + 'surface, so it hits.';
    }
    return 'It is bound and the whole orbit stays outside the body, so the satellite '
      + 'returns to where it started.';
  }

  function finish(correct, detail) {
    state.committed = true;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    draw();
    BRIDGE.outcome({ correct: correct, task: ch().id, kind: ch().kind,
                     tries: state.tries + (correct ? 1 : 0),
                     answer: detail.answer, detail: detail });
  }

  function check() {
    var c = ch();
    if (!c || state.committed || c.kind === 'sandbox') return;
    var v0 = state.speed * 1000;
    if (c.kind === 'classify') {
      if (!state.choice) { UI.feedback('Choose closed, crash or escape first.', false); return; }
      var kind = classify(state.mass, v0);
      if (state.choice === kind) {
        UI.feedback('Correct: ' + kind + '. ' + explain(kind) + ' Escape speed here is '
          + fmt(vesc(state.mass) / 1000, 2) + ' km/s and the circular speed is '
          + fmt(vcirc(state.mass) / 1000, 2) + ' km/s. ' + (c.why || ''), true);
        finish(true, { answer: kind, speed_kms: state.speed, mass: state.mass,
                       why: c.why || '' });
      } else {
        state.tries += 1;
        if (state.tries >= __MAX_TRIES__) {
          UI.feedback('Third try, so here it is: ' + kind + '. ' + explain(kind)
            + ' Escape speed is ' + fmt(vesc(state.mass) / 1000, 2) + ' km/s; you set '
            + fmt(state.speed, 2) + ' km/s. ' + (c.why || ''), false);
          finish(false, { answer: kind, speed_kms: state.speed, mass: state.mass,
                          gave_up: true, why: c.why || '' });
        } else {
          UI.feedback('Not that. Compare your speed with the escape speed '
            + fmt(vesc(state.mass) / 1000, 2) + ' km/s (twice the circular speed, '
            + fmt(vcirc(state.mass) / 1000, 2) + ' km/s). Try again.', false);
        }
      }
      return;
    }
    // set_speed
    var target = c.target, ok = false, msg = '';
    if (target === 'escape') {
      ok = v0 >= vesc(state.mass);
      msg = 'the escape speed is ' + fmt(vesc(state.mass) / 1000, 2) + ' km/s';
    } else if (target === 'crash') {
      ok = classify(state.mass, v0) === 'crash';
      msg = 'the circular speed is ' + fmt(vcirc(state.mass) / 1000, 2)
        + ' km/s and the orbit must dip below the surface';
    } else {
      ok = Math.abs(v0 - vcirc(state.mass)) / vcirc(state.mass) <= (+c.tol || 0.03);
      msg = 'the circular speed is ' + fmt(vcirc(state.mass) / 1000, 2) + ' km/s';
    }
    var kind2 = classify(state.mass, v0);
    if (ok) {
      UI.feedback('Correct: ' + explain(kind2) + ' ' + (c.why || ''), true);
      finish(true, { answer: target, speed_kms: state.speed, mass: state.mass,
                     status: kind2, why: c.why || '' });
    } else {
      state.tries += 1;
      if (state.tries >= __MAX_TRIES__) {
        UI.feedback('Third try, so here it is: ' + msg + '. ' + (c.why || ''), false);
        finish(false, { answer: target, speed_kms: state.speed, mass: state.mass,
                        gave_up: true, why: c.why || '' });
      } else {
        UI.feedback('Not yet: ' + msg + '. Adjust the speed and try again.', false);
      }
    }
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('next').addEventListener('click', function () {
    state.index += 1; load();
  });
  document.getElementById('reset').addEventListener('click', function () { load(); });

  sync();
  load();
}
""".replace('__MAX_TRIES__', str(_MAX_TRIES))


ORBIT_GRAVITY = Archetype(
    id='orbit_gravity',
    title='Gravity and orbits',
    blurb='Launch a satellite and see whether it orbits, crashes or escapes.',
    interaction='set the central mass and the launch speed; the orbit is integrated live',
    subjects=('science', 'physics', 'earth_science'),
    tags=('gravity', 'orbits', 'escape-velocity', 'energy', 'simulation'),
    reference='PhET Gravity and Orbits; ExploreLearning Gizmos Orbital Motion',
    telemetry='One outcome per task: whether the predicted fate (closed, crash or escape) '
              'was right, or whether the speed set met the circular/escape/crash target, '
              'with the mass and speed used.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('orbit_radius', 'float', 'Radius at which the satellite starts, in metres.',
              minimum=1e5, maximum=1e9),
        Field('body_radius', 'float', 'Radius of the central body, in metres.',
              minimum=1e4, maximum=1e9),
        Field('view_radius', 'float', 'Half-width of the view, in metres.',
              minimum=1e5, maximum=1e10),
        Field('mass_min', 'float', 'Smallest central mass, in 10^24 kg.',
              minimum=0.1, maximum=1000),
        Field('mass_max', 'float', 'Largest central mass, in 10^24 kg.',
              minimum=0.1, maximum=1000),
        Field('speed_min', 'float', 'Smallest launch speed, in km/s.',
              minimum=0.5, maximum=200),
        Field('speed_max', 'float', 'Largest launch speed, in km/s.',
              minimum=0.5, maximum=200),
        Field('challenges', 'table',
              'One row per task. kind="classify" hides the orbit and asks the learner to '
              'predict closed/crash/escape; kind="set_speed" asks the learner to find a '
              'speed for a target; kind="sandbox" is free play.',
              minimum_items=1, maximum_items=12,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this task.'),
                  Field('kind', 'text', 'What the task asks for.',
                        choices=('sandbox', 'classify', 'set_speed')),
                  Field('text', 'text', 'The question, in one sentence.'),
                  Field('mass', 'float', 'Central mass for this task, in 10^24 kg.',
                        required=False, minimum=0.1, maximum=1000),
                  Field('speed', 'float', 'Launch speed for this task, in km/s.',
                        required=False, minimum=0.5, maximum=200),
                  Field('target', 'text', 'For a set_speed task: what the speed must '
                        'achieve.', required=False,
                        choices=('circular', 'escape', 'crash')),
                  Field('tol', 'float', 'Relative tolerance for a circular-orbit target.',
                        required=False, minimum=0.001, maximum=0.5),
                  Field('why', 'text', 'The reasoning revealed after the answer.',
                        required=False),
              )),
    ),
    body=_body_orbit,
    engine=lambda spec: _ENGINE_ORBIT,
)


SCIENCE_B_ARCHETYPES = (WAVE_LAB, PROJECTILE, PUNNETT, ORBIT_GRAVITY)
