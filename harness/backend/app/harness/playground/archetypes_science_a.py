"""``archetypes_science_a`` - physics and chemistry simulators for the playground.

Four archetypes, all modelled on :mod:`app.harness.playground.archetypes_core` and
all written to be *first-party* replacements for the standard PhET / Gizmos
activities - the same interaction a learner would meet there, except that the
committed answer is reported back to the harness as evidence. PhET and Gizmos are
embedded read-only and can never be evidence (see :mod:`app.simulation_map`); these
can.

``particle_sandbox``
    A gas-law sandbox. A container of particles whose speed scales with the
    temperature, sliders for temperature, volume and amount, and a pressure
    computed from the ideal gas law ``P = nRT/V``. The learner then commits to a
    *factor* prediction ("double T at constant V - what happens to P?") which is
    what is scored. The physical claim being taught is the proportionality itself,
    so the collision model has to be honest: elastic wall bounces, and speeds that
    track ``sqrt(T)`` (the rms speed), not ``T``.

``circuit_builder``
    Ohm's law in a series circuit. A real schematic - battery, resistor zigzags,
    ammeter - with the supply voltage on a slider. The current readout is
    ``I = V/R_total`` and the ammeter shows it. The learner commits to a predicted
    current, a predicted total resistance, or which resistor takes the largest
    share of the supply voltage. The individual voltage drops stay hidden until
    the commitment, so "which resistor drops the most" is a real prediction rather
    than a lookup.

``balance_equation``
    Balance a chemical equation with coefficient steppers. The atom counts are
    parsed from the formula text - including nested groups such as ``Ca(OH)2`` -
    and never hardcoded, so the numbers on screen are exactly the numbers the
    formula implies. The equation is balanced when every element matches on both
    sides; the lowest whole-number coefficients are what is rewarded.

``titration_curve``
    A strong acid / strong base titration. Add titrant in increments or drag the
    playhead, and the pH curve grows behind you: a slow rise, a near-vertical jump
    at the equivalence point, then a plateau. The model is the standard
    strong/strong one, and its one simplification (water autoionisation is
    neglected) is stated in the spec's ``note`` and shown to the learner.

Every archetype separates the two bridge messages the runtime defines: live state
goes out as ``BRIDGE.readout``, and exactly one ``BRIDGE.outcome`` is posted when
the learner commits with Check.
"""

from __future__ import annotations

from typing import Any, Mapping

from .archetypes import Archetype, Field

#: Tries allowed on one task before the answer is revealed. Revealing it is better
#: than letting a learner grind: a stuck learner learns only that the game is
#: frustrating.
_MAX_TRIES = 3


# =========================================================== particle_sandbox

_PARTICLE_BODY = (
    '<div class="stagecol">'
    '<div class="scene-wrap">'
    '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
    'aria-label="A container of gas particles, with sliders for temperature, '
    'volume and amount"></svg>'
    '</div>'
    '<div class="panel">'
    '<label class="fld" for="t">Temperature '
    '<input type="range" id="t" min="100" max="1000" step="10">'
    '<span class="verdict" id="tval"></span></label>'
    '<label class="fld" for="v">Volume '
    '<input type="range" id="v" min="5" max="50" step="0.5">'
    '<span class="verdict" id="vval"></span></label>'
    '<label class="fld" for="n">Particles '
    '<input type="range" id="n" min="0.5" max="3" step="0.1">'
    '<span class="verdict" id="nval"></span></label>'
    '</div>'
    '<div class="controls">'
    '<span class="verdict" id="task"></span>'
    '<span id="opts"></span>'
    '<span class="spacer"></span>'
    '<button id="reset">Reset sliders</button>'
    '<button class="primary" id="check">Check</button>'
    '<button id="next" class="hidden">Next prediction</button>'
    '</div>'
    '</div>'
)

_PARTICLE_ENGINE = r"""
function build(root, spec) {
  var MAXTRIES = __MAXTRIES__;
  var R_GAS = 8.314;                      // J mol^-1 K^-1
  var scene = document.getElementById('scene');
  var tasks = spec.tasks || [];
  var tMin = +spec.t_min, tMax = +spec.t_max, tStart = +spec.t_start;
  var vMin = +spec.v_min, vMax = +spec.v_max, vStart = +spec.v_start;
  var nMin = +spec.n_min, nMax = +spec.n_max, nStart = +spec.n_start;
  var gaugeMax = +spec.p_max || 400;
  var rng = rand(+spec.seed || 1);

  var state = { T: tStart, V: vStart, n: nStart, index: 0, attempts: 0,
                choice: null, solved: false };

  var cT = UI.chip('T', 'Temperature', 'c');
  var cV = UI.chip('V', 'Volume', 'a');
  var cN = UI.chip('n', 'Amount', 'b');
  var cP = UI.chip('P', 'Pressure', 'd');
  var cB = UI.chip('base', 'Baseline P', 'e');

  // ---- static chrome -------------------------------------------------------
  // The container and the gauge run nearly the full height of the card: a gas
  // vessel that stops two-thirds of the way down reads as a floating box.
  var boxLeft = 70, boxTop = 56, boxH = 344;
  function boxW(V) { return 90 + (V - vMin) / ((vMax - vMin) || 1) * 400; }

  var gBox = svg('g', { 'data-series': 'container' }, scene);
  // Solid walls, not the dashed `.bin` well: nothing is dropped in here, and a
  // dashed edge would advertise a drag target that does not exist.
  var box = svg('rect', { x: boxLeft, y: boxTop, width: 490, height: boxH, rx: 6,
                          fill: COLOURS.surface2, stroke: COLOURS.edge,
                          'stroke-width': 1.8 }, gBox);
  var boxLabel = svg('text', { class: 'lbl', x: boxLeft, y: boxTop - 12 }, gBox);
  boxLabel.textContent = 'Container';
  var gPart = svg('g', { 'data-series': 'particles' }, scene);

  var gGauge = svg('g', { 'data-series': 'gauge' }, scene);
  var gx = 640, gw = 60, gy0 = 400, gy1 = 56;
  svg('rect', { x: gx, y: gy1, width: gw, height: gy0 - gy1, fill: 'none',
                stroke: COLOURS.edge, 'stroke-width': 1.2, rx: 4 }, gGauge);
  // A scale turns the tube into an instrument: without ticks the bar is a shape,
  // not a reading.
  for (var gt = 0; gt <= 4; gt++) {
    var gyv = gy1 + (gy0 - gy1) * gt / 4;
    svg('line', { x1: gx - 6, y1: gyv, x2: gx, y2: gyv, stroke: COLOURS.edge,
                  'stroke-width': 1 }, gGauge);
    var gTick = svg('text', { class: 'tick', x: gx - 10, y: gyv + 3.5,
                              'text-anchor': 'end' }, gGauge);
    gTick.textContent = fmt(gaugeMax * (1 - gt / 4), 0);
  }
  var gBar = svg('rect', { x: gx + 3, y: gy0 - 3, width: gw - 6, height: 0,
                           fill: COLOURS.d, opacity: 0.8 }, gGauge);
  var gTitle = svg('text', { class: 'lbl', x: gx + gw / 2, y: gy1 - 12,
                             'text-anchor': 'middle' }, gGauge);
  gTitle.textContent = 'Pressure';
  var gVal = svg('text', { class: 'tick', x: gx + gw / 2, y: gy0 + 17,
                           'text-anchor': 'middle' }, gGauge);

  var noteTxt = svg('text', { class: 'note', x: 78, y: 26 }, scene);
  noteTxt.textContent = spec.unit_note || '';

  // ---- model ---------------------------------------------------------------
  function P() { return state.n * R_GAS * state.T / state.V; }   // kPa
  function baseline() { return nStart * R_GAS * tStart / vStart; }
  // rms speed is proportional to sqrt(T); drawing v proportional to T would
  // teach the wrong relation, so the visual carries the correct one.
  function speed() { return 1.15 * Math.sqrt(state.T / 300); }
  function count() { return Math.round(clamp(state.n * 30, 12, 110)); }
  function fillFor() {
    var f = (state.T - tMin) / ((tMax - tMin) || 1);
    return f < 0.34 ? COLOURS.a : (f < 0.67 ? COLOURS.d : COLOURS.c);
  }

  var parts = [];

  function addOne() {
    var w = boxW(state.V), r = 5;
    parts.push({ x: boxLeft + r + rng() * Math.max(1, w - 2 * r),
                 y: boxTop + r + rng() * (boxH - 2 * r),
                 th: rng() * Math.PI * 2 });
    svg('circle', { r: 4, fill: fillFor(), opacity: 0.8 }, gPart);
  }

  function sync() {
    var want = count();
    while (parts.length > want) { parts.pop(); gPart.removeChild(gPart.lastChild); }
    while (parts.length < want) addOne();
  }

  function step() {
    var w = boxW(state.V), sp = speed(), r = 5;
    var lo = boxLeft + r, hi = boxLeft + w - r;
    var top = boxTop + r, bot = boxTop + boxH - r;
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      p.x += Math.cos(p.th) * sp;
      p.y += Math.sin(p.th) * sp;
      // Elastic bounce off a wall: reflect the normal component of the velocity.
      if (p.x < lo) { p.x = lo + (lo - p.x); p.th = Math.PI - p.th; }
      else if (p.x > hi) { p.x = hi - (p.x - hi); p.th = Math.PI - p.th; }
      if (p.y < top) { p.y = top + (top - p.y); p.th = -p.th; }
      else if (p.y > bot) { p.y = bot - (p.y - bot); p.th = -p.th; }
    }
  }

  function paint() {
    for (var i = 0; i < parts.length; i++) {
      var node = gPart.childNodes[i];
      node.setAttribute('cx', parts[i].x);
      node.setAttribute('cy', parts[i].y);
    }
  }

  function frame() { step(); paint(); requestAnimationFrame(frame); }

  function recolour() {
    var f = fillFor();
    for (var i = 0; i < gPart.childNodes.length; i++) {
      gPart.childNodes[i].setAttribute('fill', f);
    }
  }

  function update() {
    sync(); recolour();
    var p = P(), p0 = baseline();
    cT.set(fmt(state.T, 0) + ' K');
    cV.set(fmt(state.V, 1) + ' L');
    cN.set(fmt(state.n, 2) + ' mol');
    cP.set(fmt(p, 1) + ' kPa');
    cB.set(fmt(p0, 1) + ' kPa');
    document.getElementById('tval').textContent = fmt(state.T, 0) + ' K';
    document.getElementById('vval').textContent = fmt(state.V, 1) + ' L';
    document.getElementById('nval').textContent = fmt(state.n, 2) + ' mol';
    gVal.textContent = fmt(p, 1) + ' kPa';
    var h = clamp(p / gaugeMax, 0, 1) * (gy0 - gy1 - 8);
    gBar.setAttribute('height', h);
    gBar.setAttribute('y', gy0 - 3 - h);
    box.setAttribute('width', boxW(state.V));
    BRIDGE.readout({ temperature: +state.T.toFixed(1), volume: +state.V.toFixed(2),
                     amount: +state.n.toFixed(3), pressure: +p.toFixed(2) });
  }

  // ---- sliders -------------------------------------------------------------
  var tEl = document.getElementById('t');
  var vEl = document.getElementById('v');
  var nEl = document.getElementById('n');
  tEl.min = tMin; tEl.max = tMax; tEl.step = 10; tEl.value = state.T;
  vEl.min = vMin; vEl.max = vMax; vEl.step = 0.5; vEl.value = state.V;
  nEl.min = nMin; nEl.max = nMax; nEl.step = 0.1; nEl.value = state.n;
  tEl.addEventListener('input', function () { state.T = +tEl.value; update(); });
  vEl.addEventListener('input', function () { state.V = +vEl.value; update(); });
  nEl.addEventListener('input', function () { state.n = +nEl.value; update(); });

  // ---- the committed prediction -------------------------------------------
  function factorLabel(v) {
    if (Math.abs(v - 1) < 1e-9) return 'no change (x1)';
    if (v > 1) return 'x ' + (Math.round(v) === v ? Math.round(v) : fmt(v, 2));
    var inv = 1 / v;
    return '/ ' + (Math.round(inv) === inv ? Math.round(inv) : fmt(inv, 2));
  }

  function prompt() {
    var t = tasks[state.index];
    var taskEl = document.getElementById('task');
    var opts = document.getElementById('opts');
    clear(opts);
    state.choice = null;
    UI.progress(state.index, tasks.length);
    if (!t) {
      taskEl.textContent = 'Every prediction is answered.';
      UI.say(spec.instruction || '');
      return;
    }
    taskEl.textContent = t.question;
    UI.say((t.setup ? t.setup + '  ' : '') + (spec.instruction || ''));
    (t.options || []).forEach(function (value) {
      var b = el('button', { type: 'button' }, opts);
      b.textContent = factorLabel(value);
      b.addEventListener('click', function () {
        if (state.solved) return;
        state.choice = value;
        for (var i = 0; i < opts.children.length; i++) opts.children[i].className = '';
        b.className = 'primary';
        UI.feedback('');
      });
    });
  }

  function finish(ok, message) {
    var t = tasks[state.index];
    state.solved = true;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    UI.feedback(message, ok);
    BRIDGE.outcome({
      correct: ok, task: t.id, kind: 'pressure_factor', answer: t.answer,
      choice: state.choice, tries: state.attempts,
      detail: { gave_up: !ok, temperature: +state.T.toFixed(1),
                volume: +state.V.toFixed(2), amount: +state.n.toFixed(3),
                pressure: +P().toFixed(2), baseline_pressure: +baseline().toFixed(2) }
    });
  }

  function check() {
    var t = tasks[state.index];
    if (!t || state.solved) return;
    if (state.choice === null) {
      UI.feedback('Choose what happens to the pressure before checking. A prediction '
                  + 'you did not make is not evidence.', false);
      return;
    }
    state.attempts += 1;
    if (Math.abs(state.choice - (+t.answer)) < 1e-6) {
      finish(true, 'Correct. ' + (t.why || ''));
    } else if (state.attempts >= MAXTRIES) {
      finish(false, 'Not quite, and this is the third try, so here is the answer: '
                    + factorLabel(+t.answer) + '. ' + (t.why || ''));
    } else {
      UI.feedback('That is not it. ' + (t.hint
                  || 'Work out what the ideal gas law does when only that quantity '
                     + 'changes.'), false);
    }
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    state.T = tStart; state.V = vStart; state.n = nStart;
    tEl.value = tStart; vEl.value = vStart; nEl.value = nStart;
    update(); UI.feedback('');
  });
  document.getElementById('next').addEventListener('click', function () {
    state.index = Math.min(state.index + 1, tasks.length);
    state.attempts = 0; state.solved = false; state.choice = null;
    document.getElementById('check').disabled = false;
    document.getElementById('next').classList.add('hidden');
    UI.feedback('');
    prompt(); update();
  });

  prompt();
  update();
  requestAnimationFrame(frame);
}
""".replace('__MAXTRIES__', str(_MAX_TRIES))


PARTICLE_SANDBOX = Archetype(
    id='particle_sandbox',
    title='Particle sandbox',
    blurb='Move the sliders on a box of gas and watch the pressure respond, then '
          'commit to what the ideal gas law says will happen.',
    interaction='slide temperature, volume and amount; commit to a pressure factor',
    subjects=('science',),
    tags=('gas-laws', 'kinetic-theory', 'proportionality', 'simulation', 'prediction'),
    reference='PhET Gas Properties; ExploreLearning Gizmos "Ideal Gas Law"',
    telemetry='One outcome per prediction: the pressure factor the learner chose, the '
              'correct factor, whether it was right, and how many tries it took.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('unit_note', 'text', 'The unit system, shown on the stage. State the '
              'units of P, V, T and n and the value of R.', required=False),
        Field('t_min', 'float', 'Lowest temperature on the slider (K).', minimum=1),
        Field('t_max', 'float', 'Highest temperature on the slider (K).', minimum=2),
        Field('t_start', 'float', 'Starting temperature (K).', minimum=1),
        Field('v_min', 'float', 'Smallest container volume (L).', minimum=0.1),
        Field('v_max', 'float', 'Largest container volume (L).', minimum=0.2),
        Field('v_start', 'float', 'Starting volume (L).', minimum=0.1),
        Field('n_min', 'float', 'Fewest moles of gas.', minimum=0.01),
        Field('n_max', 'float', 'Most moles of gas.', minimum=0.02),
        Field('n_start', 'float', 'Starting amount of gas (mol).', minimum=0.01),
        Field('p_max', 'float', 'Full-scale reading of the pressure gauge (kPa).',
              required=False, minimum=1),
        Field('seed', 'int', 'Seed for the deterministic particle layout.',
              required=False, minimum=0),
        Field('tasks', 'table',
              'One row per prediction. The learner picks a factor and commits.',
              minimum_items=1, maximum_items=8,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this prediction.'),
                  Field('question', 'text', 'The prediction, phrased as a question.'),
                  Field('setup', 'text', 'What to set the sliders to before deciding.',
                        required=False),
                  Field('options', 'list', 'The factor buttons offered, as numbers '
                        '(1 means unchanged).', minimum_items=2, maximum_items=6),
                  Field('answer', 'float', 'The correct factor.'),
                  Field('hint', 'text', 'A nudge shown after a wrong answer.',
                        required=False),
                  Field('why', 'text', 'The reasoning revealed once the answer is in.',
                        required=False),
              )),
    ),
    body=lambda spec: _PARTICLE_BODY,
    engine=lambda spec: _PARTICLE_ENGINE,
)


# =========================================================== circuit_builder

_CIRCUIT_BODY = (
    '<div class="stagecol">'
    '<div class="scene-wrap">'
    '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
    'aria-label="A series circuit with a battery, resistors and an ammeter"></svg>'
    '</div>'
    '<div class="panel">'
    '<label class="fld" for="vs">Supply voltage '
    '<input type="range" id="vs" min="0" max="12" step="0.1">'
    '<span class="verdict" id="vsval"></span></label>'
    '</div>'
    '<div class="controls">'
    '<span class="verdict" id="task"></span>'
    '<span id="answer"></span>'
    '<span class="spacer"></span>'
    '<button id="reset">Reset supply</button>'
    '<button class="primary" id="check">Check</button>'
    '<button id="next" class="hidden">Next task</button>'
    '</div>'
    '</div>'
)

_CIRCUIT_ENGINE = r"""
function build(root, spec) {
  var MAXTRIES = __MAXTRIES__;
  var scene = document.getElementById('scene');
  var res = spec.resistors || [];
  var tasks = spec.tasks || [];
  var vMin = +spec.v_min, vMax = +spec.v_max, vStart = +spec.v_start;
  var state = { V: vStart, index: 0, attempts: 0, solved: false, got: null,
                reveal: false };

  // The loop is sized to the card: a wide, tall rectangle with a reserved label
  // gutter above the top run and to the left of the cell.
  var LX = 128, RX = 744, TY = 116, BY = 400, MID = (TY + BY) / 2;
  var HALF = 44;                        // half the width of a resistor symbol

  var cV = UI.chip('V', 'Supply', 'a');
  var cR = UI.chip('R', 'Total resistance', 'b');
  var cI = UI.chip('I', 'Current', 'c');

  var gWire = svg('g', { 'data-series': 'wires' }, scene);
  // Charge dots sit above the wires but beneath the components, so a dot passing a
  // resistor or the ammeter is hidden by it instead of speckling the symbol.
  var gDots = svg('g', { 'data-series': 'charge-flow' }, scene);
  var gComp = svg('g', { 'data-series': 'components' }, scene);
  var gDrop = svg('g', { 'data-series': 'voltage-drops' }, scene);

  var note = svg('text', { class: 'note', x: 78, y: 26 }, scene);
  note.textContent = spec.note || '';

  function wire(x1, y1, x2, y2) {
    svg('line', { x1: x1, y1: y1, x2: x2, y2: y2, stroke: COLOURS.ink,
                  'stroke-width': 3, 'stroke-linecap': 'round' }, gWire);
  }

  // Resistor centres, spread evenly along the top run so the loop reads as one
  // continuous circuit rather than a row of parts bunched near the left corner.
  function positions(n) {
    var out = [];
    for (var i = 0; i < n; i++) out.push(LX + (RX - LX) * (i + 1) / (n + 1));
    return out;
  }
  var xs = positions(res.length);

  function zigzag(cx, cy) {
    var w = HALF * 2, a = 13, l = cx - HALF;
    var pts = [[l, cy], [l + 8, cy], [l + 18, cy - a], [l + 34, cy + a],
               [l + 50, cy - a], [l + 66, cy + a], [l + 80, cy], [l + w, cy]];
    return pts.map(function (p) { return p[0] + ',' + p[1]; }).join(' ');
  }

  function textWidth(node, fallback) {
    try { var w = node.getComputedTextLength(); if (w > 0) return w; } catch (e) {}
    return fallback;
  }

  // A value label sits on its own plate above its symbol and is joined to it by a
  // leader, so the number and the component it belongs to read as one object
  // rather than a caption floating somewhere over the wire.
  function labelPlate(cx, baseline, text, col) {
    var t = svg('text', { class: 'lbl', x: cx, y: baseline, 'text-anchor': 'middle',
                          fill: col }, gComp);
    t.setAttribute('font-size', '13');
    t.setAttribute('font-weight', '700');
    t.textContent = text;
    var w = textWidth(t, text.length * 7.2);
    var plate = svg('rect', { x: cx - w / 2 - 10, y: baseline - 16,
                              width: w + 20, height: 24, rx: 7,
                              fill: COLOURS.surface2, stroke: COLOURS.line,
                              'stroke-width': 1 });
    var leader = svg('line', { x1: cx, y1: baseline + 8, x2: cx, y2: baseline + 22,
                               stroke: col, 'stroke-width': 1.4, opacity: 0.5 });
    gComp.insertBefore(plate, t);
    gComp.insertBefore(leader, t);
    return t;
  }

  // ---- wires ---------------------------------------------------------------
  wire(LX, TY, xs[0] - HALF, TY);
  for (var k = 0; k + 1 < xs.length; k++) {
    wire(xs[k] + HALF, TY, xs[k + 1] - HALF, TY);
  }
  wire(xs[xs.length - 1] + HALF, TY, RX, TY);
  wire(RX, TY, RX, MID - 21);          // right side, above the ammeter
  wire(RX, MID + 21, RX, BY);          // right side, below the ammeter
  wire(RX, BY, LX, BY);                // bottom
  wire(LX, BY, LX, MID + 14);          // left side, below the cell
  wire(LX, MID - 14, LX, TY);          // left side, above the cell

  // ---- battery (a single cell: one long plate, one short plate) -------------
  svg('line', { x1: LX - 27, y1: MID - 14, x2: LX + 27, y2: MID - 14,
                stroke: COLOURS.ink, 'stroke-width': 3.6,
                'stroke-linecap': 'round' }, gComp);
  svg('line', { x1: LX - 14, y1: MID + 14, x2: LX + 14, y2: MID + 14,
                stroke: COLOURS.ink, 'stroke-width': 3.6,
                'stroke-linecap': 'round' }, gComp);
  var plusTxt = svg('text', { class: 'lbl', x: LX + 36, y: MID - 10,
                              'text-anchor': 'start' }, gComp);
  plusTxt.textContent = '+';
  var minusTxt = svg('text', { class: 'lbl', x: LX + 36, y: MID + 18,
                               'text-anchor': 'start' }, gComp);
  minusTxt.textContent = '\u2212';
  var capSupply = svg('text', { class: 'note', x: LX - 38, y: MID - 2,
                                'text-anchor': 'end' }, gComp);
  capSupply.textContent = 'supply';
  var battLabel = svg('text', { class: 'lbl', x: LX - 38, y: MID + 17,
                                'text-anchor': 'end' }, gComp);
  battLabel.setAttribute('font-size', '14');
  battLabel.setAttribute('font-variant-numeric', 'tabular-nums');
  battLabel.textContent = '--';

  // ---- ammeter -------------------------------------------------------------
  svg('circle', { cx: RX, cy: MID, r: 21, fill: COLOURS.card, stroke: COLOURS.ink,
                  'stroke-width': 2.6 }, gComp);
  var ammLetter = svg('text', { class: 'lbl', x: RX, y: MID + 5,
                                'text-anchor': 'middle' }, gComp);
  ammLetter.setAttribute('font-size', '13.5');
  ammLetter.textContent = 'A';
  var ammLabel = svg('text', { class: 'lbl', x: RX + 31, y: MID + 5,
                               'text-anchor': 'start', fill: COLOURS.c }, gComp);
  ammLabel.setAttribute('font-size', '14');
  ammLabel.setAttribute('font-variant-numeric', 'tabular-nums');
  ammLabel.textContent = '--';

  // ---- resistors -----------------------------------------------------------
  var resNodes = [];
  res.forEach(function (r, i) {
    var col = colour(r.colour || 'a');
    var poly = svg('polyline', { points: zigzag(xs[i], TY), fill: 'none',
                                 stroke: col, 'stroke-width': 3.6,
                                 'stroke-linejoin': 'round',
                                 'stroke-linecap': 'round' }, gComp);
    var lab = labelPlate(xs[i], TY - 40,
                         (r.label || ('R' + (i + 1))) + ' = ' + fmt(+r.ohms, 0)
                         + ' \u03a9', col);
    resNodes.push({ r: r, poly: poly, lab: lab, col: col });
  });

  function highlight(id) {
    resNodes.forEach(function (node) {
      node.poly.setAttribute('stroke-width', node.r.id === id ? 6 : 3.6);
    });
  }

  // ---- model ---------------------------------------------------------------
  function totalR() {
    var sum = 0;
    res.forEach(function (r) { sum += +r.ohms; });
    return sum || 1;
  }
  function current() { return state.V / totalR(); }

  function drawDrops() {
    clear(gDrop);
    if (!state.reveal) return;
    var I = current();
    res.forEach(function (r, i) {
      // A bracket under the symbol ties the drop to that resistor, so three
      // revealed numbers cannot be read against the wrong component.
      svg('path', { d: 'M' + (xs[i] - 26) + ',' + (TY + 26) + ' v-6 H' + (xs[i] + 26)
                       + ' v6', fill: 'none', stroke: COLOURS.e, 'stroke-width': 1.2,
                    opacity: 0.6 }, gDrop);
      var t = svg('text', { class: 'lbl', x: xs[i], y: TY + 44,
                            'text-anchor': 'middle', fill: COLOURS.e }, gDrop);
      t.setAttribute('font-size', '12.5');
      t.setAttribute('font-variant-numeric', 'tabular-nums');
      t.textContent = fmt(I * (+r.ohms), 2) + ' V';
    });
    var tot = svg('text', { class: 'note', x: (LX + RX) / 2, y: BY - 18,
                            'text-anchor': 'middle', fill: COLOURS.e }, gDrop);
    tot.textContent = 'the drops sum to the supply: ' + fmt(state.V, 1) + ' V';
  }

  function update() {
    var R = totalR(), I = current();
    cV.set(fmt(state.V, 1) + ' V');
    cR.set(fmt(R, 0) + ' \u03a9');
    cI.set(fmt(I, 3) + ' A');
    document.getElementById('vsval').textContent = fmt(state.V, 1) + ' V';
    battLabel.textContent = fmt(state.V, 1) + ' V';
    ammLabel.textContent = fmt(I, 3) + ' A';
    drawDrops();
    BRIDGE.readout({ voltage: +state.V.toFixed(2), resistance: R,
                     current: +I.toFixed(4) });
  }

  var vsEl = document.getElementById('vs');
  vsEl.min = vMin; vsEl.max = vMax; vsEl.step = 0.1; vsEl.value = state.V;
  vsEl.addEventListener('input', function () { state.V = +vsEl.value; update(); });

  // ---- the committed task --------------------------------------------------
  function prompt() {
    var t = tasks[state.index];
    var box = document.getElementById('answer');
    clear(box);
    state.got = null;
    highlight('');
    UI.progress(state.index, tasks.length);
    if (!t) {
      document.getElementById('task').textContent = 'Every task is done.';
      return;
    }
    document.getElementById('task').textContent = t.question;
    if (t.kind === 'voltage_drop') {
      res.forEach(function (r) {
        var b = el('button', { type: 'button' }, box);
        b.textContent = r.label || r.id;
        b.addEventListener('click', function () {
          if (state.solved) return;
          state.got = r.id;
          for (var i = 0; i < box.children.length; i++) box.children[i].className = '';
          b.className = 'primary';
          highlight(r.id);
          UI.feedback('');
        });
      });
    } else {
      var lab = el('label', { class: 'fld' }, box);
      var cap = el('span', null, lab);
      cap.textContent = t.kind === 'resistance'
        ? 'Total resistance (\u03a9)' : 'Current (A)';
      el('input', { type: 'number', id: 'ans', step: '0.01',
                    inputmode: 'decimal' }, lab);
    }
  }

  function answerText(t) {
    if (t.kind === 'voltage_drop') {
      var found = null;
      res.forEach(function (r) { if (r.id === t.answer_resistor) found = r; });
      return found ? (found.label || found.id) + ', because V = IR and it has the '
                      + 'largest resistance' : String(t.answer_resistor);
    }
    return fmt(+t.answer, t.kind === 'resistance' ? 0 : 2)
           + (t.kind === 'resistance' ? ' \u03a9' : ' A');
  }

  function observe(t) {
    state.reveal = true;
    state.V = +t.voltage;
    vsEl.value = state.V;
    if (t.kind === 'voltage_drop') highlight(t.answer_resistor);
    update();
  }

  function finish(ok, message) {
    var t = tasks[state.index];
    state.solved = true;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    UI.feedback(message, ok);
    BRIDGE.outcome({
      correct: ok, task: t.id, kind: t.kind, answer: t.answer,
      answer_resistor: t.answer_resistor, got: state.got, tries: state.attempts,
      detail: { gave_up: !ok, voltage: +state.V.toFixed(2),
                resistance: totalR(), current: +current().toFixed(4) }
    });
  }

  function check() {
    var t = tasks[state.index];
    if (!t || state.solved) return;
    if (t.kind === 'voltage_drop') {
      if (!state.got) { UI.feedback('Choose a resistor before checking.', false); return; }
    } else {
      var inp = document.getElementById('ans');
      var value = inp ? parseFloat(inp.value) : NaN;
      if (!isFinite(value)) {
        UI.feedback('Enter a number before checking.', false);
        return;
      }
      state.got = value;
    }
    state.attempts += 1;
    var ok = t.kind === 'voltage_drop'
      ? state.got === t.answer_resistor
      : Math.abs(state.got - (+t.answer))
        <= (+t.tolerance || Math.max(0.02, Math.abs(+t.answer) * 0.05));
    if (ok) {
      observe(t);
      finish(true, 'Correct. ' + (t.why || ''));
    } else if (state.attempts >= MAXTRIES) {
      observe(t);
      finish(false, 'Not quite, and this is the third try, so here is the answer: '
                    + answerText(t) + '. ' + (t.why || ''));
    } else {
      UI.feedback('Not yet. ' + (t.hint
                  || 'Add the series resistances first, then use I = V / R.'), false);
    }
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    state.V = vStart; vsEl.value = vStart; update(); UI.feedback('');
  });
  document.getElementById('next').addEventListener('click', function () {
    state.index = Math.min(state.index + 1, tasks.length);
    state.attempts = 0; state.solved = false; state.got = null; state.reveal = false;
    document.getElementById('check').disabled = false;
    document.getElementById('next').classList.add('hidden');
    UI.feedback('');
    prompt(); update();
  });

  // ---- charge flow ---------------------------------------------------------
  var path = [[LX, TY], [RX, TY], [RX, BY], [LX, BY]];
  var segs = [], total = 0;
  for (var s = 0; s < path.length; s++) {
    var a = path[s], b = path[(s + 1) % path.length];
    var len = Math.abs(b[0] - a[0]) + Math.abs(b[1] - a[1]);
    segs.push({ a: a, b: b, len: len, start: total });
    total += len;
  }
  function atLength(distance) {
    var d = ((distance % total) + total) % total;
    for (var i = 0; i < segs.length; i++) {
      var sg = segs[i];
      if (d <= sg.start + sg.len) {
        var f = (d - sg.start) / sg.len;
        return [sg.a[0] + (sg.b[0] - sg.a[0]) * f,
                sg.a[1] + (sg.b[1] - sg.a[1]) * f];
      }
    }
    return [path[0][0], path[0][1]];
  }
  var NDOT = 14, dots = [], phase = 0;
  for (var d = 0; d < NDOT; d++) {
    dots.push(svg('circle', { r: 3.4, fill: COLOURS.c, opacity: 0.85 }, gDots));
  }
  // The dots travel along the straight wire, which the zigzag leaves by up to the
  // amplitude; a dot inside a resistor's span would therefore sit beside the symbol
  // rather than on it. Hide it for that stretch - the charge is inside the component.
  function insideResistor(p) {
    if (Math.abs(p[1] - TY) > 1) return false;
    for (var i = 0; i < xs.length; i++) {
      if (Math.abs(p[0] - xs[i]) <= HALF + 2) return true;
    }
    return false;
  }
  function frame() {
    // Conventional current leaves the + plate and runs round the loop. Drift
    // speed is drawn proportional to the current, so a bigger I visibly moves.
    var sp = clamp(6 + current() * 26, 6, 46);
    phase += sp;
    for (var i = 0; i < NDOT; i++) {
      var p = atLength(phase + i * total / NDOT);
      dots[i].setAttribute('cx', p[0]);
      dots[i].setAttribute('cy', p[1]);
      dots[i].setAttribute('opacity', insideResistor(p) ? 0 : 0.85);
    }
    requestAnimationFrame(frame);
  }

  prompt();
  update();
  requestAnimationFrame(frame);
}
""".replace('__MAXTRIES__', str(_MAX_TRIES))


CIRCUIT_BUILDER = Archetype(
    id='circuit_builder',
    title='Circuit builder',
    blurb='Set the supply voltage on a series circuit, read the ammeter, and commit '
          'to what Ohm\u2019s law says.',
    interaction='set the supply and resistances; commit to a current, a resistance '
                'or a voltage drop',
    subjects=('science',),
    tags=('circuits', 'ohms-law', 'series', 'schematic', 'prediction'),
    reference='PhET Circuit Construction Kit; ExploreLearning Gizmos "Circuits"',
    telemetry='One outcome per task: the committed current, resistance or chosen '
              'resistor, whether it was right, and how many tries it took.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('note', 'text', 'A modelling note shown on the stage.', required=False),
        Field('v_min', 'float', 'Lowest supply voltage (V).', minimum=0),
        Field('v_max', 'float', 'Highest supply voltage (V).', minimum=1),
        Field('v_start', 'float', 'Starting supply voltage (V).', minimum=0),
        Field('resistors', 'table',
              'Two or three resistors, wired in series along the top of the loop.',
              minimum_items=2, maximum_items=3,
              item_fields=(
                  Field('id', 'text', 'Stable identifier, e.g. "r1".'),
                  Field('label', 'text', 'Label drawn on the schematic, e.g. "R1".'),
                  Field('ohms', 'float', 'Resistance in ohms.', minimum=0.1),
                  Field('colour', 'text', 'Palette name.', choices=('a', 'b', 'c', 'd', 'e')),
              )),
        Field('tasks', 'table',
              'One row per committed task. kind picks the question and the answer.',
              minimum_items=1, maximum_items=8,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this task.'),
                  Field('kind', 'text', 'What is being predicted.',
                        choices=('current', 'resistance', 'voltage_drop')),
                  Field('question', 'text', 'The question, including the supply voltage.'),
                  Field('voltage', 'float', 'The supply voltage the question is about. '
                        'The slider moves here when the answer is revealed.'),
                  Field('answer', 'float', 'Correct current (A) or resistance (ohm).',
                        required=False),
                  Field('tolerance', 'float', 'Absolute tolerance on a numeric answer.',
                        required=False, minimum=0),
                  Field('answer_resistor', 'text', 'id of the resistor with the largest '
                        'voltage drop.', required=False),
                  Field('hint', 'text', 'A nudge shown after a wrong answer.',
                        required=False),
                  Field('why', 'text', 'The reasoning revealed once the answer is in.',
                        required=False),
              )),
    ),
    body=lambda spec: _CIRCUIT_BODY,
    engine=lambda spec: _CIRCUIT_ENGINE,
)


# =========================================================== balance_equation

_BALANCE_BODY = (
    '<div class="stagecol">'
    '<div class="scene-wrap">'
    '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
    'aria-label="Atom counts for each element on the reactant and product sides '
    'of the equation"></svg>'
    '</div>'
    '<div id="equation" style="display:flex;flex-wrap:wrap;gap:8px 12px;'
    'align-items:center;justify-content:center;padding:6px 14px 0;"></div>'
    '<div class="controls">'
    '<span class="verdict" id="status"></span>'
    '<span class="spacer"></span>'
    '<button id="reset">Reset coefficients</button>'
    '<button class="primary" id="check">Check</button>'
    '<button id="next" class="hidden">Next equation</button>'
    '</div>'
    '</div>'
)

_BALANCE_ENGINE = r"""
function build(root, spec) {
  var MAXTRIES = __MAXTRIES__;
  var scene = document.getElementById('scene');
  var eqs = spec.equations || [];
  var maxCoef = +spec.max_coefficient || 8;
  var state = { index: 0, coefs: [], attempts: 0, solved: false, parsed: null,
                minSolution: null };

  var gTable = svg('g', { 'data-series': 'atom-counts' }, scene);
  var head = svg('text', { class: 'lbl', x: 78, y: 34 }, scene);
  head.textContent = 'Atom counts, from the formula';
  var note = svg('text', { class: 'note', x: 78, y: 442 }, scene);
  note.textContent = spec.note || '';

  // ---- formula parser ------------------------------------------------------
  // Counts atoms straight from the formula text, so the numbers on screen are
  // the numbers the formula implies. Handles nested groups: Ca(OH)2 -> Ca1 O2 H2.
  function parseFormula(text) {
    var s = String(text).replace(/\s+/g, '');
    var i = 0;
    function number() {
      var start = i;
      while (i < s.length && s[i] >= '0' && s[i] <= '9') i++;
      return start === i ? 1 : parseInt(s.slice(start, i), 10);
    }
    function group() {
      var out = {};
      while (i < s.length) {
        var ch = s[i];
        if (ch === '(' || ch === '[') {
          i++;
          var inner = group();
          if (s[i] === ')' || s[i] === ']') i++;
          var mult = number();
          for (var key in inner) out[key] = (out[key] || 0) + inner[key] * mult;
        } else if (ch === ')' || ch === ']') {
          break;
        } else if (ch >= 'A' && ch <= 'Z') {
          var start = i; i++;
          while (i < s.length && s[i] >= 'a' && s[i] <= 'z') i++;
          var el = s.slice(start, i);
          out[el] = (out[el] || 0) + number();
        } else {
          i++;   // stray characters (a leading coefficient, a dot) are ignored
        }
      }
      return out;
    }
    return group();
  }

  function splitSide(text) {
    return String(text).split('+').map(function (x) { return x.trim(); })
                       .filter(function (x) { return x.length > 0; });
  }

  function parseEq(text) {
    var t = String(text).replace(/\u2192/g, '->').replace(/\u21cc/g, '->')
                        .replace(/=/g, '->');
    var parts = t.split('->');
    if (parts.length < 2) return null;
    var species = [];
    splitSide(parts[0]).forEach(function (f) {
      species.push({ formula: f, side: 0, atoms: parseFormula(f) });
    });
    var rightStart = species.length;
    splitSide(parts[1]).forEach(function (f) {
      species.push({ formula: f, side: 1, atoms: parseFormula(f) });
    });
    return { species: species, rightStart: rightStart };
  }

  function orderElements(list) {
    var hasC = list.indexOf('C') >= 0;
    return list.slice().sort(function (a, b) {
      if (hasC) {
        if (a === 'C') return -1;
        if (b === 'C') return 1;
        if (a === 'H') return -1;
        if (b === 'H') return 1;
      }
      return a < b ? -1 : (a > b ? 1 : 0);
    });
  }

  function elements() {
    var seen = {};
    state.parsed.species.forEach(function (sp) {
      for (var el in sp.atoms) seen[el] = true;
    });
    return orderElements(Object.keys(seen));
  }

  function counts() {
    var left = {}, right = {};
    state.parsed.species.forEach(function (sp, i) {
      var target = sp.side === 0 ? left : right;
      for (var el in sp.atoms) {
        target[el] = (target[el] || 0) + sp.atoms[el] * state.coefs[i];
      }
    });
    return { left: left, right: right };
  }

  function balanced() {
    var c = counts(), els = elements();
    for (var i = 0; i < els.length; i++) {
      if ((c.left[els[i]] || 0) !== (c.right[els[i]] || 0)) return false;
    }
    return els.length > 0;
  }

  function gcd(a, b) { while (b) { var t = a % b; a = b; b = t; } return a; }

  function gcdAll(list) {
    var g = 0;
    list.forEach(function (c) { g = gcd(g, c); });
    return g || 1;
  }

  // The minimal whole-number solution, found by enumeration. Small systems only,
  // which is all a balancing exercise ever is.
  function solve() {
    var n = state.parsed.species.length;
    var trial = new Array(n);
    var found = null;
    function rec(i) {
      if (found) return;
      if (i === n) {
        var saved = state.coefs;
        state.coefs = trial.slice();
        var ok = balanced() && gcdAll(trial) === 1;
        state.coefs = saved;
        if (ok) found = trial.slice();
        return;
      }
      for (var c = 1; c <= maxCoef; c++) {
        trial[i] = c;
        rec(i + 1);
        if (found) return;
      }
    }
    rec(0);
    return found;
  }

  // ---- rendering -----------------------------------------------------------
  function drawTable() {
    clear(gTable);
    if (!state.parsed) return;
    var c = counts(), els = elements();
    var colEl = 108, colL = 400, colEq = 540, colR = 700;
    var ruleL = 96, ruleR = 800;
    function txt(x, y, s, cls, fill, anchor) {
      var node = svg('text', { x: x, y: y, class: cls || 'tick',
                               'text-anchor': anchor || 'middle' }, gTable);
      if (fill) node.setAttribute('fill', fill);
      node.setAttribute('font-variant-numeric', 'tabular-nums');
      node.textContent = s;
      return node;
    }
    txt(colEl, 80, 'Element', 'tick', COLOURS.dim, 'start');
    txt(colL, 80, 'Reactants', 'tick', COLOURS.dim);
    txt(colR, 80, 'Products', 'tick', COLOURS.dim);
    svg('line', { x1: ruleL, x2: ruleR, y1: 92, y2: 92, stroke: COLOURS.edge,
                  'stroke-width': 1 }, gTable);
    // Rows are spread over the height of the card rather than stacked at the top,
    // so the table fills the stage and the eye has less distance to travel from an
    // element name to its two counts. A zebra band carries the eye across.
    var n = els.length;
    var top = 148, bottom = 372;
    var step = n > 1 ? Math.min(64, (bottom - top) / (n - 1)) : 0;
    var y0 = n > 1 ? top + ((bottom - top) - step * (n - 1)) / 2 : (top + bottom) / 2;
    els.forEach(function (el, i) {
      var y = y0 + i * step;
      if (i % 2 === 1) {
        svg('rect', { x: ruleL, y: y - 27, width: ruleR - ruleL, height: 42, rx: 7,
                      fill: COLOURS.surface2 }, gTable);
      }
      var l = c.left[el] || 0, r = c.right[el] || 0;
      var same = l === r;
      var tone = same ? COLOURS.good : COLOURS.bad;
      txt(colEl, y, el, 'lbl', COLOURS.ink, 'start')
        .setAttribute('font-size', '13.5');
      // The counts are the data of this game, so they get the largest type on the
      // stage; the comparison sign is a verdict and is sized to be seen from afar.
      txt(colL, y, l, 'lbl', tone).setAttribute('font-size', '14.5');
      var eqNode = txt(colEq, y, same ? '=' : '\u2260', 'lbl', tone);
      eqNode.setAttribute('font-size', '16');
      eqNode.setAttribute('font-weight', '700');
      txt(colR, y, r, 'lbl', tone).setAttribute('font-size', '14.5');
    });
  }

  function buildEquation() {
    var host = document.getElementById('equation');
    clear(host);
    if (!state.parsed) return;
    state.parsed.species.forEach(function (sp, i) {
      if (i === state.parsed.rightStart) {
        var arrow = el('span', { class: 'lbl' }, host);
        arrow.textContent = '\u2192';
        arrow.style.fontSize = '16px';
      } else if (i > 0) {
        var plus = el('span', { class: 'lbl' }, host);
        plus.textContent = '+';
        plus.style.fontSize = '15px';
      }
      var cell = el('span', null, host);
      cell.style.display = 'inline-flex';
      cell.style.alignItems = 'center';
      cell.style.gap = '5px';
      var minus = el('button', { type: 'button',
                                 'aria-label': 'decrease the coefficient of ' + sp.formula },
                     cell);
      minus.textContent = '\u2212';
      minus.style.padding = '2px 8px';
      minus.style.lineHeight = '1';
      var num = el('b', null, cell);
      num.textContent = state.coefs[i];
      num.style.minWidth = '16px';
      num.style.textAlign = 'center';
      num.style.fontVariantNumeric = 'tabular-nums';
      var plusB = el('button', { type: 'button',
                                 'aria-label': 'increase the coefficient of ' + sp.formula },
                     cell);
      plusB.textContent = '+';
      plusB.style.padding = '2px 8px';
      plusB.style.lineHeight = '1';
      var formula = el('span', null, cell);
      formula.textContent = sp.formula;
      formula.style.fontSize = '14px';
      minus.addEventListener('click', function () { bump(i, -1); });
      plusB.addEventListener('click', function () { bump(i, 1); });
    });
  }

  function publish() {
    if (!state.parsed) return;
    var c = counts();
    // Live state for the workbench's own display. Never stored.
    BRIDGE.readout({ equation: eqs[state.index] ? eqs[state.index].id : null,
                     coefficients: state.coefs.slice(), balanced: balanced(),
                     left: c.left, right: c.right });
  }

  function bump(index, delta) {
    if (state.solved) return;
    state.coefs[index] = clamp(state.coefs[index] + delta, 1, maxCoef);
    buildEquation();
    drawTable();
    publish();
    document.getElementById('status').textContent = '';
    UI.feedback('');
  }

  function render() { buildEquation(); drawTable(); publish(); }

  // ---- the committed answer ------------------------------------------------
  function finish(ok, message) {
    var eq = eqs[state.index];
    state.solved = true;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    UI.feedback(message, ok);
    BRIDGE.outcome({
      correct: ok, task: eq.id, tries: state.attempts,
      coefficients: state.coefs.slice(),
      detail: { gave_up: !ok, equation: eq.equation,
                simplest: state.minSolution ? state.minSolution.slice() : null }
    });
  }

  function check() {
    var eq = eqs[state.index];
    if (!eq || state.solved) return;
    state.attempts += 1;
    var c = counts(), els = elements();
    var bad = null;
    for (var i = 0; i < els.length; i++) {
      if ((c.left[els[i]] || 0) !== (c.right[els[i]] || 0)) { bad = els[i]; break; }
    }
    if (bad) {
      var l = c.left[bad] || 0, r = c.right[bad] || 0;
      var msg = 'Not balanced yet: ' + bad + ' has ' + l + ' on the left and ' + r
                + ' on the right. ' + (l > r
                  ? 'Raise a coefficient on the reactant side, or lower one on the '
                    + 'product side.'
                  : 'Raise a coefficient on the product side, or lower one on the '
                    + 'reactant side.');
      if (state.attempts >= MAXTRIES) {
        reveal();
        finish(false, msg + ' The lowest whole-number answer is '
                      + state.minSolution.join(' : ') + '. ' + (eq.why || ''));
      } else {
        UI.feedback(msg, false);
      }
      return;
    }
    var g = gcdAll(state.coefs);
    if (g > 1) {
      var msg2 = 'Every element matches, so the equation is balanced - but these are '
                 + 'not the lowest whole numbers. Divide every coefficient by ' + g + '.';
      if (state.attempts >= MAXTRIES) {
        reveal();
        finish(false, msg2 + ' The lowest answer is ' + state.minSolution.join(' : ')
                      + '. ' + (eq.why || ''));
      } else {
        UI.feedback(msg2, false);
      }
      return;
    }
    finish(true, 'Balanced, with the lowest whole-number coefficients. ' + (eq.why || ''));
  }

  function reveal() {
    state.coefs = state.minSolution.slice();
    render();
  }

  function load(index) {
    state.index = index;
    var eq = eqs[index];
    state.parsed = eq ? parseEq(eq.equation) : null;
    state.coefs = state.parsed ? state.parsed.species.map(function () { return 1; })
                               : [];
    state.minSolution = state.parsed ? solve() : null;
    state.attempts = 0;
    state.solved = false;
    UI.progress(index, eqs.length);
    document.getElementById('check').disabled = false;
    document.getElementById('next').classList.add('hidden');
    document.getElementById('status').textContent = '';
    UI.feedback('');
    render();
  }

  document.getElementById('check').addEventListener('click', check);
  document.getElementById('reset').addEventListener('click', function () {
    if (!state.parsed) return;
    state.coefs = state.parsed.species.map(function () { return 1; });
    render(); UI.feedback('');
  });
  document.getElementById('next').addEventListener('click', function () {
    var following = state.index + 1;
    if (following >= eqs.length) {
      document.getElementById('next').classList.add('hidden');
      document.getElementById('status').textContent = 'Every equation is done.';
      UI.feedback('');
      return;
    }
    state.index = following;
    load(state.index);
  });

  load(0);
  if (eqs.length <= 1) document.getElementById('next').classList.add('hidden');
}
""".replace('__MAXTRIES__', str(_MAX_TRIES))


BALANCE_EQUATION = Archetype(
    id='balance_equation',
    title='Balance the equation',
    blurb='Turn the coefficient steppers until every element has the same count on '
          'both sides, using the lowest whole numbers.',
    interaction='step stoichiometric coefficients and watch live atom counts',
    subjects=('science',),
    tags=('stoichiometry', 'equations', 'conservation', 'counting', 'chemistry'),
    reference='PhET Balancing Chemical Equations; ExploreLearning Gizmos "Balancing '
              'Chemical Equations"',
    telemetry='One outcome per equation: the coefficient vector the learner settled '
              'on, whether it was balanced at the lowest whole numbers, and the tries.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('note', 'text', 'A note shown on the stage, e.g. the conservation '
              'principle being used.', required=False),
        Field('max_coefficient', 'int', 'Highest value the steppers reach.',
              required=False, minimum=2, maximum=12),
        Field('equations', 'table',
              'One row per equation. Formulas may use nested groups such as Ca(OH)2.',
              minimum_items=1, maximum_items=4,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this equation.'),
                  Field('equation', 'text', 'The unbalanced equation, e.g. '
                        '"C3H8 + O2 -> CO2 + H2O". Use -> or the arrow character.'),
                  Field('why', 'text', 'The reasoning revealed once it is balanced.',
                        required=False),
              )),
    ),
    body=lambda spec: _BALANCE_BODY,
    engine=lambda spec: _BALANCE_ENGINE,
)


# =========================================================== titration_curve

_TITRATION_BODY = (
    '<div class="stagecol">'
    '<div class="scene-wrap">'
    '<svg class="scene" id="scene" viewBox="0 0 860 460" role="img" '
    'aria-label="A pH curve plotted against the volume of base added"></svg>'
    '</div>'
    '<div class="controls">'
    '<span class="verdict" id="task"></span>'
    '<span id="answer"></span>'
    '<span class="spacer"></span>'
    '<button id="a01">+0.1 mL</button>'
    '<button id="a1">+1 mL</button>'
    '<button id="a5">+5 mL</button>'
    '<button id="reset">Reset</button>'
    '<button class="primary" id="check">Check</button>'
    '<button id="next" class="hidden">Next task</button>'
    '</div>'
    '</div>'
)

_TITRATION_ENGINE = r"""
function build(root, spec) {
  var MAXTRIES = __MAXTRIES__;
  var scene = document.getElementById('scene');
  var X0 = 78, X1 = 812, Y0 = 388, Y1 = 44;
  var ca = +spec.acid_conc, va = +spec.acid_volume, cb = +spec.base_conc;
  var vMax = +spec.v_max || 50;
  var tasks = spec.tasks || [];
  var veq = ca * va / cb;                     // equivalence volume, mL
  var state = { added: 0, index: 0, attempts: 0, solved: false, got: null };

  var toX = scale([0, vMax], [X0, X1]);
  var toY = scale([0, 14], [Y0, Y1]);

  var cAdd = UI.chip('added', 'Titrant added', 'a');
  var cPh = UI.chip('ph', 'pH', 'c');
  var cEq = UI.chip('eq', 'Equivalence volume', 'e');

  function log10(x) { return Math.log(x) / Math.LN10; }

  // Strong acid / strong base model. Moles are in mmol (M x mL) and the total
  // volume in mL, so the ratio is already a concentration in mol/L. Water
  // autoionisation is neglected, which is the simplification the note states.
  function phAt(vb) {
    var na = ca * va, nb = cb * vb, total = va + vb;
    var d = na - nb;
    if (Math.abs(d) < 1e-9) return 7;
    if (d > 0) return -log10(d / total);
    return 14 + log10(-d / total);
  }

  // ---- chrome --------------------------------------------------------------
  var gGrid = svg('g', { 'data-series': 'grid' }, scene);
  for (var p = 0; p <= 7; p++) {
    svg('line', { x1: X0, x2: X1, y1: toY(p * 2), y2: toY(p * 2),
                  class: 'gridline' }, gGrid);
  }
  var vStep = vMax <= 20 ? 2 : (vMax <= 60 ? 5 : 10);
  for (var v = 0; v <= vMax + 1e-9; v += vStep) {
    svg('line', { x1: toX(v), x2: toX(v), y1: Y0, y2: Y1, class: 'gridline' }, gGrid);
  }
  svg('line', { x1: X0, x2: X1, y1: Y0, y2: Y0, class: 'axis' }, scene);
  svg('line', { x1: X0, x2: X0, y1: Y0, y2: Y1, class: 'axis' }, scene);
  for (var q = 0; q <= 7; q++) {
    var ty = svg('text', { x: X0 - 8, y: toY(q * 2) + 3.5, 'text-anchor': 'end',
                           class: 'tick' }, scene);
    ty.textContent = q * 2;
  }
  for (var w = 0; w <= vMax + 1e-9; w += vStep) {
    var tx = svg('text', { x: toX(w), y: Y0 + 15, 'text-anchor': 'middle',
                           class: 'tick' }, scene);
    tx.textContent = w;
  }
  var xlab = svg('text', { x: X1, y: Y0 + 33, 'text-anchor': 'end',
                           class: 'lbl' }, scene);
  xlab.textContent = 'Volume of ' + (spec.base_name || 'base') + ' added (mL)';
  var ylab = svg('text', { x: X0 - 8, y: Y1 - 16, 'text-anchor': 'end',
                           class: 'lbl' }, scene);
  ylab.textContent = 'pH';
  var note = svg('text', { class: 'note', x: X0, y: 26 }, scene);
  note.textContent = spec.note || '';

  var curve = svg('polyline', { fill: 'none', stroke: COLOURS.c, 'stroke-width': 2.6,
                                'stroke-linejoin': 'round',
                                'data-series': 'ph-curve' }, scene);
  var eqLine = svg('line', { stroke: COLOURS.e, 'stroke-width': 1.6,
                             'stroke-dasharray': '5 4', opacity: 0 }, scene);
  var eqLabel = svg('text', { class: 'lbl', fill: COLOURS.e, opacity: 0 }, scene);
  var dropLine = svg('line', { stroke: COLOURS.a, 'stroke-width': 1.2,
                               'stroke-dasharray': '4 4', opacity: 0 }, scene);
  // The playhead is the only handle on this page, so it is drawn as one: a ringed dot
  // with a stem above it, 18px across, not a 12px dot sitting on the axis where a
  // learner reads it as a data point and never tries to grab it.
  var marker = svg('circle', { r: 9, fill: COLOURS.a, stroke: '#ffffff',
                               'stroke-width': 2.5, class: 'grab',
                               'data-series': 'playhead-handle' }, scene);
  var grip = svg('rect', { width: 3, height: 13, rx: 1.5, fill: COLOURS.a,
                           opacity: 0.5, 'pointer-events': 'none' }, scene);
  // L4: an empty plot is not a state, it is an unfinished page. Until the learner adds
  // titrant the stage says what to do, and the sentence removes itself the moment it
  // stops being true. It is *not* a ghost of the whole curve: the tasks ask where the
  // curve turns, so drawing the answer would be a leak, not an affordance.
  var invite = svg('text', { 'text-anchor': 'middle', x: (X0 + X1) / 2,
                             y: (Y0 + Y1) / 2,
                             style: 'font-size:13px;font-weight:550;fill:'
                                    + colour('dim') }, scene);
  invite.textContent = 'Drag the playhead, or add titrant with the buttons below.';
  var hit = svg('rect', { x: X0, y: Y1, width: X1 - X0, height: Y0 - Y1,
                          fill: 'transparent', 'pointer-events': 'all',
                          class: 'grab', 'data-series': 'playhead' }, scene);

  // ---- drawing -------------------------------------------------------------
  // Uniform across the whole axis, plus a dense band around the equivalence
  // point, so the near-vertical jump is drawn as the corner it is.
  var SAMPLES = (function () {
    var out = [], i;
    for (i = 0; i <= 160; i++) out.push(i * vMax / 160);
    var lo = Math.max(0, veq - 1.5), hi = Math.min(vMax, veq + 1.5);
    for (i = 0; i <= 240; i++) out.push(lo + (hi - lo) * i / 240);
    out.sort(function (a, b) { return a - b; });
    return out;
  })();

  function drawCurve() {
    var pts = [];
    for (var i = 0; i < SAMPLES.length; i++) {
      var vv = SAMPLES[i];
      if (vv > state.added + 1e-9) break;
      pts.push(toX(vv).toFixed(1) + ',' + toY(clamp(phAt(vv), 0, 14)).toFixed(1));
    }
    var last = toX(state.added).toFixed(1) + ','
             + toY(clamp(phAt(state.added), 0, 14)).toFixed(1);
    if (!pts.length) pts.push(last);
    pts.push(last);
    curve.setAttribute('points', pts.join(' '));
  }

  function drawMarker() {
    var x = toX(state.added), y = toY(clamp(phAt(state.added), 0, 14));
    marker.setAttribute('cx', x);
    marker.setAttribute('cy', y);
    grip.setAttribute('x', x - 1.5);
    grip.setAttribute('y', y - 25);
    invite.setAttribute('opacity', state.added > 0 ? 0 : 1);
    dropLine.setAttribute('x1', x);
    dropLine.setAttribute('y1', Y0);
    dropLine.setAttribute('x2', x);
    dropLine.setAttribute('y2', y);
    dropLine.setAttribute('opacity', state.added > 0 ? 0.65 : 0);
  }

  function update() {
    var ph = phAt(state.added);
    cAdd.set(fmt(state.added, 1) + ' mL');
    cPh.set(fmt(clamp(ph, 0, 14), 2));
    drawCurve();
    drawMarker();
    BRIDGE.readout({ added_ml: +state.added.toFixed(2), ph: +ph.toFixed(3) });
  }

  function add(amount) {
    state.added = clamp(Math.round((state.added + amount) * 10) / 10, 0, vMax);
    update();
  }

  // Dragging uses the svg's own screen CTM, so the playhead lands where the
  // pointer is even when the viewBox is letterboxed inside the stage.
  function viewPt(ev) {
    if (scene.createSVGPoint && scene.getScreenCTM) {
      var pt = scene.createSVGPoint();
      pt.x = ev.clientX; pt.y = ev.clientY;
      var m = scene.getScreenCTM();
      if (m) {
        var q = pt.matrixTransform(m.inverse());
        return { x: q.x, y: q.y };
      }
    }
    return point(ev, scene);
  }

  drag(hit, {
    start: function (pt, ev) { return { ok: true }; },
    move: function (pt, held, ev) {
      var p = viewPt(ev);
      state.added = clamp(Math.round(toX.invert(p.x) * 10) / 10, 0, vMax);
      update();
    }
  });

  // ---- tasks ---------------------------------------------------------------
  function revealEq() {
    var x = toX(clamp(veq, 0, vMax));
    eqLine.setAttribute('x1', x);
    eqLine.setAttribute('x2', x);
    eqLine.setAttribute('y1', Y1);
    eqLine.setAttribute('y2', Y0);
    eqLine.setAttribute('opacity', 1);
    eqLabel.setAttribute('x', clamp(x + 6, X0, X1 - 120));
    eqLabel.setAttribute('y', Y1 + 14);
    eqLabel.setAttribute('opacity', 1);
    eqLabel.textContent = 'Equivalence at ' + fmt(veq, 1) + ' mL';
    cEq.set(fmt(veq, 1) + ' mL');
  }

  function prompt() {
    var t = tasks[state.index];
    var wrap = document.getElementById('answer');
    clear(wrap);
    state.got = null;
    UI.progress(state.index, tasks.length);
    if (!t) {
      document.getElementById('task').textContent = 'Every task is done.';
      return;
    }
    document.getElementById('task').textContent = t.question;
    var lab = el('label', { class: 'fld' }, wrap);
    var cap = el('span', null, lab);
    cap.textContent = t.kind === 'equivalence_volume' ? 'Volume (mL)' : 'pH';
    el('input', { type: 'number', id: 'ans', step: '0.01',
                  inputmode: 'decimal' }, lab);
  }

  function observe(t) {
    if (t.volume !== undefined && t.volume !== null) {
      state.added = clamp(+t.volume, 0, vMax);
      update();
    }
  }

  function finish(ok, message) {
    var t = tasks[state.index];
    state.solved = true;
    document.getElementById('check').disabled = true;
    document.getElementById('next').classList.remove('hidden');
    UI.feedback(message, ok);
    BRIDGE.outcome({
      correct: ok, task: t.id, kind: t.kind, answer: t.answer, got: state.got,
      tries: state.attempts,
      detail: { gave_up: !ok, equivalence_volume: +veq.toFixed(3),
                added_ml: +state.added.toFixed(2),
                ph: +phAt(state.added).toFixed(3) }
    });
  }

  function check() {
    var t = tasks[state.index];
    if (!t || state.solved) return;
    var inp = document.getElementById('ans');
    var value = inp ? parseFloat(inp.value) : NaN;
    if (!isFinite(value)) {
      UI.feedback('Enter a number before checking.', false);
      return;
    }
    state.got = value;
    state.attempts += 1;
    var tol = +t.tolerance || 0.2;
    if (Math.abs(value - (+t.answer)) <= tol) {
      observe(t);
      revealEq();
      finish(true, 'Correct. ' + (t.why || ''));
    } else if (state.attempts >= MAXTRIES) {
      observe(t);
      revealEq();
      finish(false, 'Not quite, and this is the third try, so here is the answer: '
                    + fmt(+t.answer, 2) + (t.unit ? ' ' + t.unit : '') + '. '
                    + (t.why || ''));
    } else {
      UI.feedback('Not yet. ' + (t.hint
                  || 'Find the point where the curve is steepest, or work out how '
                     + 'much acid is still unneutralised.'), false);
    }
  }

  document.getElementById('a01').addEventListener('click', function () { add(0.1); });
  document.getElementById('a1').addEventListener('click', function () { add(1); });
  document.getElementById('a5').addEventListener('click', function () { add(5); });
  document.getElementById('reset').addEventListener('click', function () {
    state.added = 0;
    eqLine.setAttribute('opacity', 0);
    eqLabel.setAttribute('opacity', 0);
    cEq.set('--');
    update();
    UI.feedback('');
  });
  document.getElementById('check').addEventListener('click', check);
  document.getElementById('next').addEventListener('click', function () {
    state.index = Math.min(state.index + 1, tasks.length);
    state.attempts = 0; state.solved = false; state.got = null;
    document.getElementById('check').disabled = false;
    document.getElementById('next').classList.add('hidden');
    UI.feedback('');
    prompt();
  });

  prompt();
  update();
}
""".replace('__MAXTRIES__', str(_MAX_TRIES))


TITRATION_CURVE = Archetype(
    id='titration_curve',
    title='Titration curve',
    blurb='Add base to an acid and watch the pH curve turn; read the equivalence '
          'point off the plot.',
    interaction='add titrant in increments or drag the playhead; commit to a volume '
                'or a pH',
    subjects=('science',),
    tags=('titration', 'acids-bases', 'pH', 'curves', 'equilibrium'),
    reference='ExploreLearning Gizmos "Titration"; PhET Acid-Base Solutions',
    telemetry='One outcome per task: the committed equivalence volume or pH, whether '
              'it was within tolerance, and how many tries it took.',
    spec_fields=(
        Field('title', 'text', 'Shown as the page heading.'),
        Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
        Field('note', 'text', 'The model and its simplification, shown on the stage. '
              'Say that water autoionisation is neglected for a strong/strong pair.',
              required=False),
        Field('acid_name', 'text', 'Formula of the strong acid, e.g. "HCl".'),
        Field('base_name', 'text', 'Formula of the strong base, e.g. "NaOH".'),
        Field('acid_conc', 'float', 'Concentration of the acid (mol/L).', minimum=0.0001),
        Field('acid_volume', 'float', 'Volume of acid in the flask (mL).', minimum=0.1),
        Field('base_conc', 'float', 'Concentration of the titrant (mol/L).',
              minimum=0.0001),
        Field('v_max', 'float', 'Right-hand end of the volume axis (mL).', minimum=1),
        Field('seed', 'int', 'Reserved for deterministic variation.',
              required=False, minimum=0),
        Field('tasks', 'table',
              'One row per committed task.',
              minimum_items=1, maximum_items=8,
              item_fields=(
                  Field('id', 'text', 'Stable identifier for this task.'),
                  Field('kind', 'text', 'What is being predicted.',
                        choices=('equivalence_volume', 'ph_at')),
                  Field('question', 'text', 'The question put to the learner.'),
                  Field('volume', 'float', 'The volume of titrant the question is '
                        'about, for kind "ph_at" (mL).', required=False, minimum=0),
                  Field('answer', 'float', 'Correct volume (mL) or pH.'),
                  Field('tolerance', 'float', 'Absolute tolerance on the answer.',
                        required=False, minimum=0),
                  Field('unit', 'text', 'Unit shown when the answer is revealed, '
                        'e.g. "mL".', required=False),
                  Field('hint', 'text', 'A nudge shown after a wrong answer.',
                        required=False),
                  Field('why', 'text', 'The reasoning revealed once the answer is in.',
                        required=False),
              )),
    ),
    body=lambda spec: _TITRATION_BODY,
    engine=lambda spec: _TITRATION_ENGINE,
)


#: Every archetype this module contributes. Imported and registered by
#: ``app.harness.playground.__init__``.
SCIENCE_A_ARCHETYPES = (PARTICLE_SANDBOX, CIRCUIT_BUILDER, BALANCE_EQUATION,
                        TITRATION_CURVE)
