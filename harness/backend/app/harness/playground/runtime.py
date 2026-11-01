"""The shared runtime every playground game is built on.

One page shell, one CSS token set, one JavaScript helper surface. An *archetype*
supplies only two things - the markup that goes inside the stage and the script
that wires it up - and inherits everything else from here. That is what makes the
playground a system rather than twenty-four hand-written pages.

Why a shared runtime at all
---------------------------
The games this replaces were each written end to end, so every one of them
re-invented its own palette, its own pointer handling and its own way of telling
the harness what happened. Three consequences followed, all of them bad: the
games looked like they came from different products, a fix to drag handling had
to be made twenty-four times, and - the one that actually matters - *none of them
reported anything back*, so the harness could not tell whether a learner had
learned anything. A simulation the harness cannot observe is a resource, not an
experiment; that is the rule :mod:`app.simulation_map` already enforces for PhET
and Gizmos.

A first-party simulation is different, and this runtime is where the difference
is cashed in. The page runs inside the workbench's own sandboxed web view, so it
can post its outcome up to the harness. Two messages are defined:

``luminfest:readout``
    Continuous state, for the workbench's live display. High frequency, never
    stored. "Price 4.20, quantity 5.80" as the learner drags a curve.

``luminfest:outcome``
    A completed, scored task. Low frequency, and the only message the harness
    records. It carries whether the learner was right, which task within the
    game it was, how many tries it took, and a free-form detail object.

The distinction is deliberate. A readout is the simulation talking to the
screen; an outcome is the learner having committed to something checkable. Only
the second is evidence, and collapsing the two would let time spent dragging a
slider masquerade as mastery - the exact fabrication the rest of this system
exists to prevent.

The visual system
-----------------
The first draft of this file carried the palette of the hand-authored seed
simulation: an off-white page, hairline grey borders, a dusty blue accent and
nothing else. Every game rendered as a worksheet. It was consistent, which was
the goal at the time, but it was consistent *with a document* rather than with
the product - the native app had meanwhile settled on a Morandi palette anchored
on forest green, with soft tint / deep ink accent pairs, generous radii and
layered shadows. The games sat inside that app looking like a print-out stapled
into a notebook.

This file now carries the product's own design language. Three rules govern it:

**Colour carries meaning, and nothing else does.** Five *series* hues (``a`` to
``e``) identify data - a demand curve, a second series, a highlighted marker -
and each ships as a deep tone for strokes and text plus a soft tint for fills.
They never mean "right" or "wrong". Correctness is carried only by the three
*semantic* tokens (``ok`` / ``no`` / ``hint``), so a game cannot imply a verdict
through decoration. The ``a``-to-``e`` names are load-bearing: roughly a hundred
call sites across the archetypes pass them to :func:`colour`, so the names are
fixed and only the values moved.

**The chrome recedes, the content is the interface.** The stage is a raised white
card on a warm paper page. Controls are the only things with a resting shadow.
Nothing decorative competes with the drawing.

**Every state is designed.** A drag handle lifts on hover, a drop zone lights on
drag-over, an empty chart says what to do, a verdict arrives as a tinted banner
with a mark and a reason rather than a line of grey text. A learner should never
have to guess whether something is interactive.

The runtime also enforces the house conventions so no archetype can forget them:
the stage carries a ``data-series`` attribute (the workbench's hover-to-inspect
convention), and the page is self-contained - no external script, stylesheet,
font or fetch - because :func:`app.harness.sims_store.validate_html` refuses
anything that would phone home from a lesson.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

#: The design tokens. Kept in one place so a generated game and a hand-written one
#: are indistinguishable in the product.
#:
#: Colour is two ladders plus two groups. The ladders are *surface* (page -> card ->
#: well) and *ink* (primary -> secondary -> tertiary), and they are what gives the
#: interface depth without a single hard black or pure grey. The groups are the five
#: *series* hues and the three *semantic* tones, and the split between them is a rule
#: rather than a preference: series hues identify data, semantic tones judge it.
TOKENS_CSS = """
:root {
  /* ---- surface ladder: warm paper, raised card, sunken well ---- */
  --bg: #F7F5EF; --surface: #FFFFFF; --surface-2: #F6F4ED; --surface-3: #EFEDE3;
  --line: #E5E7DB; --line-strong: #D3D7C7;

  /* ---- ink ladder: never pure black, never pure grey ---- */
  --ink: #24312A; --ink-2: #5C6A60; --ink-3: #8D9A90;

  /* ---- series: five data hues, deep stroke + soft fill ---- */
  --a: #47519C; --a-soft: #CCD2F0;
  --b: #3E7A55; --b-soft: #C4E6C9;
  --c: #B35C2E; --c-soft: #FBD0B4;
  --d: #8F6A1F; --d-soft: #F7DFA8;
  --e: #7A3E8C; --e-soft: #E0C7EA;

  /* ---- semantic: the only tokens allowed to mean right or wrong ---- */
  --ok: #2C5C3E; --ok-soft: #E7F2E9; --ok-line: #BCD9C2;
  --no: #A8422F; --no-soft: #FCEAE4; --no-line: #EFC7BB;
  --hint: #47519C; --hint-soft: #EDEFF9; --hint-line: #D2D8EE;

  /* ---- aliases: the names archetypes already pass to colour() ---- */
  --dim: var(--ink-2); --faint: var(--ink-3);
  --card: var(--surface); --grid: var(--line); --edge: var(--line-strong);
  --good: var(--ok); --bad: var(--no);

  /* ---- radius ---- */
  --r-sm: 8px; --r-md: 11px; --r-lg: 16px; --r-xl: 22px; --r-pill: 999px;

  /* ---- elevation: three levels, all warm-tinted rather than neutral black ---- */
  --e1: 0 1px 2px rgba(36,49,42,.06), 0 1px 1px rgba(36,49,42,.04);
  --e2: 0 4px 12px rgba(36,49,42,.07), 0 1px 3px rgba(36,49,42,.05);
  --e3: 0 12px 28px rgba(36,49,42,.14), 0 3px 8px rgba(36,49,42,.08);

  /* ---- motion: one easing, three durations ---- */
  --fast: 120ms; --dur: 200ms; --slow: 340ms;
  --ease: cubic-bezier(.22,.61,.36,1);
  --spring: cubic-bezier(.34,1.4,.64,1);
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  color: var(--ink); background: var(--bg); display: flex; flex-direction: column;
  overflow: hidden; -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
}
.frame {
  flex: 1 1 auto; min-height: 0; width: 100%; max-width: 940px; margin: 0 auto;
  display: flex; flex-direction: column; gap: 10px; padding: 16px 20px 14px;
}

/* ---- top bar: title and instruction left, progress right ------------------ */
.topbar { display: flex; align-items: flex-start; gap: 18px; flex: 0 0 auto; }
.topbar-main { flex: 1 1 auto; min-width: 0; }
.eyebrow {
  font-size: 10px; font-weight: 700; letter-spacing: .15em; text-transform: uppercase;
  color: var(--ink-3); margin-bottom: 5px;
}
.topbar h1 { margin: 0; font-size: 19px; font-weight: 650; letter-spacing: -.018em; line-height: 1.25; }
.instruction { margin: 5px 0 0; font-size: 13px; line-height: 1.5; color: var(--ink-2); max-width: 66ch; }
.progress { flex: 0 0 auto; display: flex; flex-direction: column; gap: 6px; align-items: flex-end; padding-top: 3px; }
.progress[hidden] { display: none; }
.progress-label {
  font-size: 11px; font-weight: 650; color: var(--ink-2); letter-spacing: .02em;
  font-variant-numeric: tabular-nums;
}
.progress-rail { width: 132px; height: 6px; border-radius: var(--r-pill); background: var(--surface-3); overflow: hidden; }
.progress-fill {
  height: 100%; width: 0; border-radius: inherit;
  background: linear-gradient(90deg, var(--b), #5FA173);
  transition: width var(--slow) var(--ease);
}

/* ---- the stage: one raised card, and the only place content lives -------- */
.stage {
  position: relative; flex: 1 1 auto; min-height: 0; width: 100%;
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg);
  box-shadow: var(--e2); padding: 12px;
}
svg.scene { width: 100%; height: 100%; display: block; touch-action: none; }
/* Standard stage layout: a flexible drawing area above a fixed control strip.
   Archetypes use these classes rather than their own inline styles so every game
   in the playground has identical geometry. */
.stagecol { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.scene-wrap { flex: 1 1 auto; min-height: 0; position: relative; }
.controls {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  justify-content: center; padding: 12px 4px 2px; flex: 0 0 auto;
}
.controls .spacer { flex: 1 1 auto; }
.verdict { font-size: 12px; font-weight: 550; color: var(--ink-2); }
.panel { display: flex; flex-wrap: wrap; gap: 10px; padding: 10px 4px 2px; justify-content: center; flex: 0 0 auto; }

/* ---- readout chips: the live numbers, each tinted to its series ---------- */
.readout { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; flex: 0 0 auto; }
.readout:empty { display: none; }
.chip {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-pill);
  padding: 6px 13px; font-size: 11.5px; font-weight: 550; color: var(--ink-2);
  box-shadow: var(--e1); white-space: nowrap;
}
.chip::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%;
  background: var(--ink-3); flex: 0 0 auto;
}
.chip[data-tone="a"]::before { background: var(--a); } .chip[data-tone="b"]::before { background: var(--b); }
.chip[data-tone="c"]::before { background: var(--c); } .chip[data-tone="d"]::before { background: var(--d); }
.chip[data-tone="e"]::before { background: var(--e); } .chip[data-tone=""]::before { display: none; }
.chip b { color: var(--ink); font-variant-numeric: tabular-nums; font-weight: 700; }

/* ---- feedback: the verdict, as a moment rather than a line of text ------- */
.feedback {
  flex: 0 0 auto; display: none; align-items: flex-start; gap: 9px;
  padding: 10px 14px; border-radius: var(--r-md); font-size: 12.5px; line-height: 1.5;
  border: 1px solid transparent; box-shadow: var(--e1);
}
.feedback[data-show="1"] { display: flex; animation: fb-in var(--dur) var(--ease); }
@keyframes fb-in { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
.feedback-icon {
  flex: 0 0 auto; width: 17px; height: 17px; border-radius: 50%;
  display: grid; place-items: center; font-size: 10px; font-weight: 800;
  color: #fff; margin-top: 1px;
}
.feedback-text { flex: 1 1 auto; min-width: 0; }
.feedback[data-ok="1"] { background: var(--ok-soft); border-color: var(--ok-line); color: var(--ok); }
.feedback[data-ok="1"] .feedback-icon { background: var(--ok); }
.feedback[data-ok="0"] { background: var(--no-soft); border-color: var(--no-line); color: var(--no); }
.feedback[data-ok="0"] .feedback-icon { background: var(--no); }
.feedback[data-ok="2"] { background: var(--hint-soft); border-color: var(--hint-line); color: var(--hint); }
.feedback[data-ok="2"] .feedback-icon { background: var(--hint); }

/* ---- controls ------------------------------------------------------------ */
button {
  font: inherit; font-size: 12.5px; font-weight: 600; letter-spacing: .005em;
  border-radius: var(--r-md); cursor: pointer; padding: 9px 17px;
  border: 1px solid var(--line-strong); background: var(--surface); color: var(--ink);
  box-shadow: var(--e1);
  transition: box-shadow var(--fast) var(--ease), transform var(--fast) var(--ease),
              border-color var(--fast) var(--ease);
}
button:hover { border-color: var(--b); box-shadow: var(--e2); transform: translateY(-1px); }
button:active { transform: translateY(0) scale(.985); box-shadow: var(--e1); }
button.primary {
  background: linear-gradient(135deg, var(--b), #4E8C66); border-color: transparent; color: #fff;
  box-shadow: 0 2px 6px rgba(62,122,85,.28), 0 1px 2px rgba(62,122,85,.20);
}
button.primary:hover { box-shadow: 0 6px 16px rgba(62,122,85,.32), 0 2px 4px rgba(62,122,85,.22); }
button:disabled { opacity: .42; cursor: default; box-shadow: none; transform: none; }
button.ghost { border-color: transparent; background: transparent; box-shadow: none; color: var(--ink-2); }
button.ghost:hover { background: var(--surface-2); box-shadow: none; transform: none; border-color: transparent; }
select, input[type="number"], input[type="text"] {
  font: inherit; font-size: 12.5px; padding: 8px 11px; border-radius: var(--r-md);
  border: 1px solid var(--line-strong); background: var(--surface); color: var(--ink);
  box-shadow: var(--e1);
  transition: border-color var(--fast) var(--ease), box-shadow var(--fast) var(--ease);
}
select:focus, input:focus { border-color: var(--b); box-shadow: 0 0 0 3px rgba(62,122,85,.14); outline: none; }
:focus-visible { outline: 2px solid var(--b); outline-offset: 2px; }
label.fld { font-size: 12px; font-weight: 550; color: var(--ink-2); display: inline-flex; align-items: center; gap: 7px; }

/* The native range input is the least designed control on the platform; every
   archetype that exposes a slider inherits this replacement instead. */
input[type="range"] {
  -webkit-appearance: none; appearance: none; background: transparent;
  height: 22px; margin: 0; padding: 0; border: none; box-shadow: none; cursor: pointer;
}
input[type="range"]::-webkit-slider-runnable-track {
  height: 5px; border-radius: var(--r-pill); background: var(--surface-3); border: 1px solid var(--line);
}
input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 17px; height: 17px; border-radius: 50%;
  background: var(--surface); border: 2.5px solid var(--b); margin-top: -7px;
  box-shadow: var(--e1);
  transition: transform var(--fast) var(--ease), box-shadow var(--fast) var(--ease);
}
input[type="range"]:hover::-webkit-slider-thumb { transform: scale(1.12); box-shadow: var(--e2); }
input[type="range"]:active::-webkit-slider-thumb { transform: scale(1.04); }

/* ---- in-scene primitives ------------------------------------------------- */
.grab { cursor: grab; } .grab:active { cursor: grabbing; }
.axis { stroke: var(--ink); stroke-width: 1.6; stroke-linecap: round; }
.gridline { stroke: var(--line); stroke-width: 1; }
.tick { font-size: 10.5px; fill: var(--ink-3); font-variant-numeric: tabular-nums; }
.lbl { font-size: 12px; font-weight: 650; fill: var(--ink); }
.note { font-size: 11px; fill: var(--ink-3); }
/* A drop zone reads as a dashed well at rest and as a lit target on drag-over,
   so "you can put something here" is visible before the learner tries. */
.bin {
  fill: var(--surface-2); stroke: var(--line-strong); stroke-width: 1.6; stroke-dasharray: 7 6;
  transition: fill var(--fast) var(--ease), stroke var(--fast) var(--ease);
}
.bin[data-over="1"] { fill: #EAF3EC; stroke: var(--b); stroke-width: 2.4; stroke-dasharray: none; }
.tile {
  fill: var(--surface); stroke: var(--line-strong); stroke-width: 1.3; cursor: grab;
  filter: drop-shadow(0 1.5px 2.5px rgba(36,49,42,.10));
  transition: filter var(--fast) var(--ease);
}
.tile:hover { filter: drop-shadow(0 4px 9px rgba(36,49,42,.17)); }
.tile text { font-size: 11.5px; font-weight: 550; fill: var(--ink); pointer-events: none; }
.tile[data-state="correct"] { stroke: var(--ok); stroke-width: 2.2; }
.tile[data-state="wrong"] { stroke: var(--no); stroke-width: 2.2; }
.hidden { display: none !important; }

/* The native app already honours Reduce Motion (see Design.swift); a web view inside
   it that keeps bouncing is a bug, not a flourish. Every transition and keyframe
   collapses to an instant state change rather than being removed, so nothing that
   depends on a transitionend ever fails to fire. */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
}
"""

#: The helper surface every archetype's script is written against. Kept small on
#: purpose: each name here is one the archetype authors do not have to re-invent,
#: and one whose behaviour is guaranteed identical across all twenty-four games.
RUNTIME_JS = r"""
var SPEC = __SPEC__;
var W = __W__, H = __H__;
var SVGNS = 'http://www.w3.org/2000/svg';

function el(tag, attrs, parent) {
  var node = document.createElement(tag);
  if (attrs) { for (var k in attrs) { if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, attrs[k]); } }
  if (parent) parent.appendChild(node);
  return node;
}
function svg(tag, attrs, parent) {
  var node = document.createElementNS(SVGNS, tag);
  if (attrs) { for (var k in attrs) { if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, attrs[k]); } }
  if (parent) parent.appendChild(node);
  return node;
}
function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); return node; }
function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
// Palette names, so a spec says "a" and every archetype paints the same indigo.
// The five series hues and the two verdict tones are deliberately different groups:
// a series hue never means "right", and a verdict tone never identifies data.
var COLOURS = {
  a: '#47519C', b: '#3E7A55', c: '#B35C2E', d: '#8F6A1F', e: '#7A3E8C',
  'a-soft': '#CCD2F0', 'b-soft': '#C4E6C9', 'c-soft': '#FBD0B4',
  'd-soft': '#F7DFA8', 'e-soft': '#E0C7EA',
  ink: '#24312A', dim: '#5C6A60', faint: '#8D9A90',
  grid: '#E5E7DB', edge: '#D3D7C7', card: '#FFFFFF',
  surface: '#FFFFFF', surface2: '#F6F4ED', surface3: '#EFEDE3', line: '#E5E7DB',
  good: '#2C5C3E', bad: '#A8422F', ok: '#2C5C3E', no: '#A8422F', hint: '#47519C'
};
function colour(name) { return COLOURS[name] || name || COLOURS.a; }
function fmt(v, places) {
  var p = places === undefined ? 2 : places;
  if (!isFinite(v)) return '--';
  return (Math.abs(v) < 1e-9 ? 0 : v).toFixed(p);
}
function scale(domain, range) {
  var d0 = domain[0], d1 = domain[1], r0 = range[0], r1 = range[1];
  var span = (d1 - d0) || 1;
  var fn = function (v) { return r0 + (r1 - r0) * (v - d0) / span; };
  fn.invert = function (px) { return d0 + (px - r0) / ((r1 - r0) || 1) * span; };
  return fn;
}
function rand(seed) {
  var s = (seed >>> 0) || 1;
  return function () {
    s = (s + 0x6D2B79F5) >>> 0;
    var t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function shuffle(list, seed) {
  var out = list.slice(), r = rand(seed === undefined ? 7 : seed);
  for (var i = out.length - 1; i > 0; i--) {
    var j = Math.floor(r() * (i + 1)), tmp = out[i]; out[i] = out[j]; out[j] = tmp;
  }
  return out;
}

// ---- the bridge to the harness -------------------------------------------
// The page is sandboxed, so the parent cannot read this DOM. Anything the
// workbench should show, or record, travels as a postMessage.
var BRIDGE = (function () {
  var seq = 0, started = Date.now();
  function post(payload) {
    try { window.parent.postMessage(payload, '*'); } catch (e) { /* no parent: fine */ }
  }
  return {
    // Continuous state. Never stored by the harness.
    readout: function (obj) {
      var payload = { type: 'luminfest:readout', archetype: __ARCH__, at_ms: Date.now() - started };
      for (var k in obj) payload[k] = obj[k];
      post(payload);
    },
    // A committed, checkable result. This is the only message that becomes
    // evidence, so it is the only one that carries correctness.
    outcome: function (obj) {
      seq += 1;
      var payload = {
        type: 'luminfest:outcome', archetype: __ARCH__, seq: seq,
        elapsed_ms: Date.now() - started, correct: !!obj.correct
      };
      for (var k in obj) if (k !== 'correct') payload[k] = obj[k];
      post(payload);
      return payload;
    }
  };
})();

// ---- presentation helpers -------------------------------------------------
var UI = (function () {
  var bar = document.getElementById('feedback');
  var barText = document.getElementById('feedback-text');
  var barIcon = document.getElementById('feedback-icon');
  var MARK = { '1': '\u2713', '0': '\u2715', '2': '\u25C6' };
  var chips = {};
  return {
    say: function (text) {
      var node = document.getElementById('instruction');
      if (node) node.textContent = text;
    },
    // Where the learner is in the game. A game that never calls this shows no
    // progress rail at all, which is the right default for a free-play sandbox.
    // `done` counts *finished* tasks, so a bar at 0% is honest rather than empty.
    progress: function (done, total) {
      var wrap = document.getElementById('progress');
      if (!wrap) return;
      var n = Math.max(0, Math.floor(total) || 0);
      var d = clamp(Math.floor(done) || 0, 0, n);
      if (!n) { wrap.hidden = true; return; }
      wrap.hidden = false;
      var label = document.getElementById('progress-label');
      if (label) label.textContent = d >= n ? 'All tasks complete' : 'Task ' + (d + 1) + ' of ' + n;
      var fill = document.getElementById('progress-fill');
      if (fill) fill.style.width = (d / n * 100) + '%';
    },
    chip: function (key, label, tone) {
      if (!chips[key]) {
        var node = el('span', { class: 'chip', 'data-tone': tone || '' }, document.getElementById('readout'));
        node.appendChild(document.createTextNode(label));
        var value = el('b', null, node);
        value.textContent = '--';
        chips[key] = value;
      }
      return { set: function (text) { chips[key].textContent = text; } };
    },
    feedback: function (text, ok) {
      if (!bar) return;
      var tone = ok === undefined ? '2' : (ok ? '1' : '0');
      if (barText) barText.textContent = text; else bar.textContent = text;
      if (barIcon) barIcon.textContent = MARK[tone] || '';
      bar.setAttribute('data-show', text ? '1' : '0');
      bar.setAttribute('data-ok', tone);
    },
    // Score a committed answer: shows the verdict and reports it upward.
    score: function (correct, text, detail) {
      this.feedback(text, correct);
      BRIDGE.outcome({ correct: correct, detail: detail || {} });
    }
  };
})();

// ---- pointer drag, in viewBox units ---------------------------------------
// The scene letterboxes inside its box - `preserveAspectRatio` defaults to
// `xMidYMid meet`, which scales by the *smaller* axis and centres the result - so
// a mapping of `(clientX - left) / width * W` is wrong by a constant offset and a
// constant scale factor on every page whose aspect ratio differs from the viewBox.
// It was, for the whole first draft of this file, which is why drag handles sat
// slightly away from the pointer. Reading the live viewBox and applying the same
// uniform scale the renderer applies is the only mapping that puts the handle
// exactly under the cursor.
function viewBoxOf(node) {
  var host = null;
  if (node) {
    if (node.ownerSVGElement) host = node.ownerSVGElement;
    else if (node.tagName && String(node.tagName).toLowerCase() === 'svg') host = node;
  }
  if (!host) host = document.getElementById('scene');
  if (!host || !host.getAttribute) return [0, 0, W, H];
  var raw = (host.getAttribute('viewBox') || ('0 0 ' + W + ' ' + H)).trim().split(/[\s,]+/).map(Number);
  if (raw.length !== 4 || raw.some(function (n) { return !isFinite(n); })) return [0, 0, W, H];
  return raw;
}
function point(event, node) {
  var host = null;
  if (node) {
    if (node.ownerSVGElement) host = node.ownerSVGElement;
    else if (node.tagName && String(node.tagName).toLowerCase() === 'svg') host = node;
  }
  if (!host) host = document.getElementById('scene');
  if (!host) return { x: 0, y: 0 };
  var vb = viewBoxOf(host);
  var rect = host.getBoundingClientRect();
  var s = Math.min(rect.width / vb[2], rect.height / vb[3]) || 1;
  var ox = (rect.width - vb[2] * s) / 2, oy = (rect.height - vb[3] * s) / 2;
  return {
    x: vb[0] + (event.clientX - rect.left - ox) / s,
    y: vb[1] + (event.clientY - rect.top - oy) / s
  };
}
// L.drag(node, {start, move, end}); every handler receives viewBox coords.
// Capture is taken on the grabbed node rather than the root, so the workbench's
// click handler still resolves event.target to the [data-series] ancestor.
function drag(node, handlers) {
  var state = null;
  node.addEventListener('pointerdown', function (event) {
    state = handlers.start ? handlers.start(point(event, node), event) : {};
    if (state === false) { state = null; return; }
    try { node.setPointerCapture(event.pointerId); } catch (e) { /* older engines */ }
    event.preventDefault();
  });
  node.addEventListener('pointermove', function (event) {
    if (state === null) return;
    if (handlers.move) handlers.move(point(event, node), state, event);
  });
  ['pointerup', 'pointercancel'].forEach(function (type) {
    node.addEventListener(type, function (event) {
      if (state === null) return;
      var held = state; state = null;
      if (handlers.end) handlers.end(point(event, node), held, event);
    });
  });
  return node;
}

// ---- mount ----------------------------------------------------------------
function mount() {
  var root = document.getElementById('stage');
  try { if (typeof build === 'function') build(root, SPEC); }
  catch (err) {
    UI.feedback('This activity could not start: ' + (err && err.message ? err.message : err), false);
  }
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
else mount();
"""

#: The page skeleton. ``__TOKEN__`` substitution rather than ``str.format`` so the
#: CSS and JavaScript can contain braces freely.
_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
__TOKENS__
</style>
</head>
<body>
<div class="frame">
  <header class="topbar">
    <div class="topbar-main">
      <div class="eyebrow">__EYEBROW__</div>
      <h1>__TITLE__</h1>
      <p class="instruction" id="instruction">__INSTRUCTION__</p>
    </div>
    <div class="progress" id="progress" hidden>
      <div class="progress-label" id="progress-label"></div>
      <div class="progress-rail"><div class="progress-fill" id="progress-fill"></div></div>
    </div>
  </header>
  <div class="stage" id="stage" data-series="__ARCH__">
__BODY__
  </div>
  <div class="readout" id="readout"></div>
  <div class="feedback" id="feedback" data-show="0" data-ok="2" role="status" aria-live="polite">
    <span class="feedback-icon" id="feedback-icon" aria-hidden="true"></span>
    <span class="feedback-text" id="feedback-text"></span>
  </div>
</div>
<script>
__SCRIPT__
</script>
</body>
</html>
"""


def _js_literal(value: Any) -> str:
    """Embed a Python value in a ``<script>`` block without breaking out of it.

    ``json.dumps`` is almost enough, but a spec containing the literal text
    ``</script>`` would close the block early and the rest of the game would
    render as visible text. Escaping every ``<`` as ``\\u003c`` is valid JSON, is
    parsed identically by JavaScript, and cannot terminate the element.
    """
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c')


def eyebrow_for(subject: str, archetype_title: str) -> str:
    """The small caps line above the title: which subject, which interaction.

    Naming the *interaction* rather than the game matters pedagogically. A learner
    who has met "drag a point along a number line" in maths should recognise it in
    science, and seeing the same label is what makes the transfer visible.

    Subject ids are identifiers (``computer_science``), not display strings, so the
    separators are turned into spaces here. The CSS uppercases the result.
    """
    def human(text: str) -> str:
        return str(text or '').replace('_', ' ').replace('-', ' ').strip()

    parts = [human(p) for p in (subject, archetype_title)]
    return ' \u00b7 '.join(p for p in parts if p)


def render_page(*, archetype_id: str, title: str, instruction: str, body_html: str,
                engine_js: str, spec: Mapping[str, Any], width: int = 860,
                height: int = 460, subject: str = '',
                archetype_title: str = '') -> str:
    """Assemble a complete, self-contained, offline-playable game page.

    The result is what :func:`app.harness.sims_store.validate_html` must accept and
    what the workbench opens in its sandboxed web view. Nothing is fetched, nothing
    is evaluated dynamically, and the whole thing is one file.
    """
    script = (RUNTIME_JS
              .replace('__SPEC__', _js_literal(dict(spec)))
              .replace('__ARCH__', _js_literal(archetype_id))
              .replace('__W__', str(int(width)))
              .replace('__H__', str(int(height)))
              + '\n' + engine_js)
    return (_PAGE
            .replace('__TOKENS__', TOKENS_CSS.strip())
            .replace('__EYEBROW__', _escape(eyebrow_for(subject, archetype_title)))
            .replace('__TITLE__', _escape(title))
            .replace('__INSTRUCTION__', _escape(instruction))
            .replace('__ARCH__', _escape(archetype_id))
            .replace('__BODY__', body_html)
            .replace('__SCRIPT__', script))


def _escape(text: str) -> str:
    return (str(text or '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
