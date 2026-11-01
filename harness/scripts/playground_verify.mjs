/* A behavioural verifier for rendered playground games.
 *
 * The sibling `playground_dom_smoke.mjs` answers "does it crash?". This one answers the
 * harder question the crash check cannot: "does it behave like a scored game?" Those are
 * behavioural contracts, not rendering ones, and they are the ones that decide whether
 * playground play may be recorded as evidence:
 *
 *   - loading a page posts no outcome (interaction is what commits, not existing);
 *   - exploring - dragging, sliding, typing, clicking a choice - posts no outcome either;
 *     where the page has a Check button, only pressing it commits. An archetype whose
 *     commit is a drop rather than a press (a sort that completes when the last tile
 *     lands) is making a different, deliberate choice; the driver records that as a note
 *     rather than failing it, because it cannot tell that choice from a bug;
 *   - a committed answer posts exactly one outcome;
 *   - a wrong outcome is a give-up: it carries `correct: false` and `detail.gave_up`;
 *   - an unscored sandbox posts no outcome at all.
 *
 * It is deliberately archetype-agnostic. It knows nothing about any geometry: it drives
 * whatever handlers the page registered. That makes it broad and shallow - it cannot know
 * the *right* answer, so it cannot check that a game is correct, only that it commits
 * honestly. Correctness is asserted by each builder's own driver and by the content tests.
 *
 * Where an archetype cannot be driven generically the result is reported as `undriven`,
 * never as a pass and never as a failure. A contract that could not be tested is
 * reported as untested; claiming otherwise would be worse than the gap.
 *
 * Usage: node playground_verify.mjs <pages.json>
 *   <pages.json> is [{slug, archetype, scored, html}, ...] - rendered by a throwaway
 *   script that imports the playground, so this file never hard-codes the work.
 * Prints one JSON result per entry, then a `SUMMARY {json}` line. Exits non-zero if any
 * entry failed. Output is deterministic: two runs over the same bundle are byte-identical,
 * so a diff in CI means a real change.
 *
 * Every assertion above can be seen to fire: `outputs/.packaging/synth_pages.py` writes a
 * negative-control bundle in which each page breaks exactly one contract. Running this
 * driver over it must report exactly those failures - a verifier whose assertions never
 * fire is indistinguishable from one with none.
 */
import fs from 'node:fs';
import vm from 'node:vm';

const MAX_ROUNDS = 8;

// --------------------------------------------------------------------- stub DOM

function classList(initial) {
  const set = new Set(initial || []);
  return {
    add: (...c) => c.forEach((x) => set.add(x)),
    remove: (...c) => c.forEach((x) => set.delete(x)),
    contains: (c) => set.has(c),
    toggle: (c, force) => {
      const want = force === undefined ? !set.has(c) : !!force;
      if (want) set.add(c); else set.delete(c);
      return want;
    },
    _set: set,
  };
}

//: The id registry for the run currently in flight. `setAttribute('id', ...)` has to
//: register the element, because archetypes routinely build an input, then read it back
//: with getElementById - and a stub that hands back a different empty element for the
//: same id would make every such archetype look like it ignored its own controls.
let CURRENT_IDS = null;

class El {
  constructor(tag) {
    this.tagName = String(tag || 'div').toLowerCase();
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.listeners = {};
    this.style = {};
    this.dataset = {};
    this.classList = classList();
    this.disabled = false;
    this.value = '';
    this.checked = false;
    this._text = '';
  }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k === 'class') this.classList = classList(String(v).split(/\s+/).filter(Boolean));
    if (k === 'id' && CURRENT_IDS) CURRENT_IDS[String(v)] = this;
  }
  getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(c) { this.children.push(c); c.parentNode = this; return c; }
  insertBefore(c, ref) {
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(c); else this.children.splice(i, 0, c);
    c.parentNode = this; return c;
  }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; }
  replaceChildren() { this.children = []; }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  // childNodes and the element-only variants are what a real DOM exposes; archetypes use
  // them for recolouring and iteration, so a stub without them makes a working archetype
  // look like it throws.
  get childNodes() { return this.children; }
  get parentElement() { return this.parentNode; }
  get firstElementChild() { return this.children[0] || null; }
  get lastElementChild() { return this.children[this.children.length - 1] || null; }
  getElementsByTagName(tag) {
    return this.descendants().filter((e) => e.tagName === String(tag).toLowerCase());
  }
  getElementsByClassName(cls) {
    return this.descendants().filter((e) => e.classList.contains(String(cls)));
  }
  contains(node) { return node === this || this.descendants().includes(node); }
  matches(sel) {
    const s = String(sel);
    if (s.startsWith('.')) return this.classList.contains(s.slice(1));
    if (s.startsWith('#')) return this.attrs.id === s.slice(1);
    return this.tagName === s.toLowerCase();
  }
  querySelector(sel) { return this.descendants().find((e) => e.matches(sel)) || null; }
  querySelectorAll(sel) { return this.descendants().filter((e) => e.matches(sel)); }
  addEventListener(t, h) { (this.listeners[t] = this.listeners[t] || []).push(h); }
  removeEventListener(t, h) {
    const list = this.listeners[t];
    if (list) { const i = list.indexOf(h); if (i >= 0) list.splice(i, 1); }
  }
  setPointerCapture() {} releasePointerCapture() {}
  focus() {} blur() {} select() {}
  getBoundingClientRect() { return { left: 0, top: 0, width: 860, height: 460, right: 860, bottom: 460 }; }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); }
  get innerHTML() { return this._text; }
  set innerHTML(v) { this._text = String(v); }
  click() { this.dispatch('click', { preventDefault() {} }); }
  dispatch(type, ev) {
    const handlers = (this.listeners[type] || []).slice();
    for (const handler of handlers) handler(ev || {});
    return handlers.length;
  }
  descendants() {
    const out = [];
    const walk = (n) => { for (const c of n.children) { out.push(c); walk(c); } };
    walk(this);
    return out;
  }
  closest(sel) {
    let node = this;
    const match = (n) => (sel.startsWith('.') ? n.classList.contains(sel.slice(1))
                             : n.tagName === sel.toLowerCase());
    while (node) { if (match(node)) return node; node = node.parentNode; }
    return null;
  }
  get hidden() { return this.classList.contains('hidden') || this.style.display === 'none'; }
}

/* Recreate every element the HTML declares, so the page's script finds the ids it looks
 * up and so the class attributes (notably `hidden`) are real. They are attached to the
 * body so the whole page is one live tree, which is what discovery walks. */
function seedFromMarkup(html, ids, body) {
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  let match;
  while ((match = tagRe.exec(html)) !== null) {
    const tag = match[1].toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'meta' || tag === 'title') continue;
    const node = new El(tag);
    const attrRe = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"/g;
    let attr;
    while ((attr = attrRe.exec(match[2])) !== null) node.setAttribute(attr[1], attr[2]);
    body.appendChild(node);
    const idMatch = /\bid\s*=\s*["']([^"']+)["']/.exec(match[2]);
    if (idMatch) ids[idMatch[1]] = node;
  }
}

// ------------------------------------------------------------------- one game

function runEntry(entry) {
  const res = {
    slug: entry.slug, archetype: entry.archetype, scored: entry.scored !== false,
    // Declared by the archetype, not inferred from the markup: it is the authoritative
    // answer to "when may an outcome appear?" and the only thing that separates honest
    // exploration from a game that scores a stray drag.
    commits_on: entry.commits_on || null,
    ok: true, load_error: null, handler_errors: [], rounds: 0,
    outcomes: 0, correct: 0, wrong: 0, gave_up: 0,
    premature: [], double_posts: 0, undriven: false, notes: [],
  };
  const fail = (why) => { res.ok = false; res.notes.push(why); };

  // A page that never ran has not passed - it has not been tested. Reporting it as `ok`
  // would let a bundle of broken pages exit 0 and look verified, which is the worst
  // possible failure mode for a verifier.
  if (entry.render_error) {
    res.load_error = 'render: ' + entry.render_error;
    fail('the page could not be rendered');
    return res;
  }
  const scriptMatch = String(entry.html || '').match(/<script>([\s\S]*?)<\/script>/);
  if (!scriptMatch) {
    res.load_error = entry.html ? 'no <script> block' : 'no html';
    fail('the page has no script, so nothing could be driven');
    return res;
  }

  const ids = {};
  CURRENT_IDS = ids;
  const body = new El('body');
  seedFromMarkup(entry.html, ids, body);
  // Discovery walks the live tree, never an accumulating list: a redrawing engine
  // detaches and recreates hundreds of nodes per frame, and retaining them all would
  // exhaust the heap on a long sweep.
  const live = () => body.descendants();
  const messages = [];
  const document = {
    readyState: 'complete',
    createElement: (t) => new El(t),
    createElementNS: (ns, t) => new El(t),
    createTextNode: (t) => { const e = new El('#text'); e._text = String(t); return e; },
    getElementById: (id) => {
      if (!ids[id]) {
        const e = new El('div');
        e.setAttribute('id', id);
        body.appendChild(e);
        ids[id] = e;
      }
      return ids[id];
    },
    querySelector: (sel) => {
      const s = String(sel);
      if (s.startsWith('#')) return ids[s.slice(1)] || null;
      return live().find((e) => e.matches(s)) || null;
    },
    querySelectorAll: (sel) => {
      const s = String(sel);
      if (s.startsWith('#')) return [ids[s.slice(1)]].filter(Boolean);
      return live().filter((e) => e.matches(s));
    },
    getElementsByTagName: (tag) => live().filter((e) => e.tagName === String(tag).toLowerCase()),
    addEventListener: () => {},
    documentElement: new El('html'),
    body,
  };
  let rafBudget = 6;
  const timers = {
    setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
    requestAnimationFrame: (fn) => {
      if (rafBudget-- > 0) { try { fn(Date.now()); } catch (e) { /* reported below */ } }
      return 1;
    },
    cancelAnimationFrame: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    innerWidth: 860, innerHeight: 460,
  };
  const sandbox = {
    document,
    window: Object.assign({
      parent: { postMessage: (p) => messages.push(p) },
      addEventListener: () => {}, removeEventListener: () => {},
    }, timers),
    console: { log() {}, warn() {}, error() {}, info() {}, debug() {} },
    performance: { now: () => Date.now() },
    getComputedStyle: timers.getComputedStyle,
    innerWidth: 860, innerHeight: 460,
  };
  Object.assign(sandbox, timers);
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;

  try {
    vm.createContext(sandbox);
    vm.runInContext(scriptMatch[1], sandbox, { filename: entry.slug + '.js', timeout: 5000 });
  } catch (err) {
    res.load_error = 'load: ' + (err && err.message ? err.message : String(err));
    fail('the page threw while loading');
    return res;
  }

  /* The runtime's own mount() catches a build failure and turns it into feedback rather
   * than a throw, precisely so a learner sees a sentence instead of a blank stage. The
   * consequence for a verifier is that a page whose build() exploded looks exactly like a
   * page with no controls - and would otherwise be waved through as `undriven`. */
  const bootFeedback = ids['feedback'] ? String(ids['feedback'].textContent || '') : '';
  if (/could not start/i.test(bootFeedback)) {
    res.load_error = 'build: ' + bootFeedback;
    fail('the page failed to build its stage');
    return res;
  }

  const outcomes = () => messages.filter((m) => m && m.type === 'luminfest:outcome');
  const count = () => outcomes().length;
  /* Every driven handler is measured. The contract is "one commit posts exactly one
   * outcome", and the only honest way to test it is to count the outcomes a single
   * handler produces - counting per round would fire on any archetype that advances two
   * stages in one round, which is not a bug. */
  const safe = (label, fn) => {
    const b = count();
    try { fn(); } catch (e) { res.handler_errors.push(label + ': ' + (e && e.message ? e.message : e)); }
    if (count() - b > 1) res.double_posts += 1;
  };

  // Contract: merely loading a page commits nothing.
  if (count() > 0) fail('posted an outcome on load, before any interaction');

  const buttons = () => live().filter((e) => e.tagName === 'button' && !e.disabled && !e.hidden);
  const draggables = () => live().filter((e) => (e.listeners['pointerdown'] || []).length);
  const inputs = () => live().filter((e) => e.tagName === 'input' && !e.disabled);
  const selects = () => live().filter((e) => e.tagName === 'select' && !e.disabled);

  /* A drag has to start on the thing being dragged, and an archetype's draggable is
   * usually one full-stage layer that hit-tests the press against its own handles. A
   * single blind drag therefore proves nothing. Two things make the sweep actually reach
   * a commit: the start points cover the whole stage, and the drop point is *derived from
   * the start* rather than fixed - the dominant gesture is a horizontal "carry it out of
   * the tray on the left and drop it on the target on the right", which two fixed drop
   * points miss entirely (they land back in the tray). It is still a shotgun, and it is
   * labelled as one: when it cannot reach a commit the result is reported as undriven. */
  // The X values are the stage's left/centre/right thirds plus the six x-positions a
  // bottom tray commonly parks its handles at (300 + 46k): a handle is grabbed within
  // ~28px of its centre, so a grid that misses those columns can never pick one up.
  const SWEEP_X = [110, 190, 270, 300, 346, 392, 438, 484, 530, 620, 710, 780];
  // Eight rows, spanning the grid (y 44-388) *and* the bottom tray (y 424): a handle
  // parked in a tray at the bottom of the stage is only reachable from the last row or
  // two, so a grid that stops at the grid lines can never pick one up.
  const SWEEP_Y = [60, 110, 160, 210, 260, 310, 360, 410];
  // (dx, dy) added to each start point: long and short rightward carries, a downward
  // carry, and one diagonal, which between them cover tray-to-slot, tray-to-hotspot and
  // handle-to-track layouts. The upward carries matter just as much: a handle parked in a
  // *bottom* tray is placed by dragging it up onto the grid, and a driver that only ever
  // moves right and down never leaves the tray.
  const DROP_OFFSETS = [[300, 0], [430, 0], [0, 180], [300, 120], [300, -240], [0, -300]];
  const DRAG_PAIRS = [];
  for (const sy of SWEEP_Y) {
    for (const sx of SWEEP_X) {
      for (const [dx, dy] of DROP_OFFSETS) {
        const ex = Math.max(0, Math.min(860, sx + dx));
        const ey = Math.max(0, Math.min(460, sy + dy));
        if (ex === sx && ey === sy) continue;
        DRAG_PAIRS.push([sx, sy, ex, ey]);
      }
    }
  }
  // The budget is the whole pair list, deliberately. Slicing it looks harmless but is
  // not: the pairs are grouped by row, so a budget that stops two thirds of the way
  // through silently drops the bottom third of the stage - exactly where a tray lives.
  const DRAG_BUDGET = DRAG_PAIRS.length;

  const dragLayer = (node, sx, sy, ex, ey) => {
    const base = { pointerId: 1, preventDefault() {}, target: node };
    node.dispatch('pointerdown', Object.assign({ clientX: sx, clientY: sy }, base));
    node.dispatch('pointermove', Object.assign({ clientX: (sx + ex) / 2, clientY: (sy + ey) / 2 }, base));
    node.dispatch('pointermove', Object.assign({ clientX: ex, clientY: ey }, base));
    node.dispatch('pointerup', Object.assign({ clientX: ex, clientY: ey }, base));
  };
  const dragAll = (budget) => {
    const layers = draggables();
    if (!layers.length) return;
    const cap = budget === undefined ? DRAG_BUDGET : budget;
    const per = Math.min(DRAG_PAIRS.length, Math.max(4, Math.floor(cap / layers.length)));
    for (const node of layers) {
      const id = node.attrs.id || node.attrs['data-series'] || node.tagName;
      for (let i = 0; i < per; i++) {
        const p = DRAG_PAIRS[i];
        safe('drag ' + id, () => dragLayer(node, p[0], p[1], p[2], p[3]));
      }
    }
  };

  /* The sweep alone is not enough for a tray-to-target task. It is unordered, so the last
   * pair it happens to try decides the final state, and that pair is as likely to carry a
   * tile *back* into the tray as into a slot. What actually completes the task is the
   * gesture a learner makes: take the item at the top of the tray and carry it to the next
   * target slot, then take the new top item to the slot after that, and so on. Two details
   * matter and both are easy to get wrong: the grab point stays at the top of the tray
   * (the tray closes up behind each item), while the *drop* point walks down the target
   * column - dropping into the same slot twice simply swaps the previous tile back out.
   * The loop re-reads the game's own readout after every carry and stops the moment it
   * stops changing, so a game that ignores drags costs one short pass, not eight. */
  const readoutSig = () => {
    const rs = messages.filter((m) => m && m.type === 'luminfest:readout');
    if (!rs.length) return '';
    const d = Object.assign({}, rs[rs.length - 1]);
    delete d.at_ms;                       // the clock ticks even when nothing moves
    return JSON.stringify(d);
  };
  const dragCarry = () => {
    const layer = draggables()[0];
    if (!layer) return;
    let prev = readoutSig();
    for (let pass = 0; pass < 4; pass++) {
      let changed = false;
      for (const ey of SWEEP_Y) {           // the slot to fill, top to bottom
        for (const sx of [110, 190, 270]) { // grab the top of the tray
          for (const ex of [410, 490, 570]) {
            safe('drag carry', () => dragLayer(layer, sx, 60, ex, ey));
            const now = readoutSig();
            if (now !== prev) { prev = now; changed = true; }
          }
        }
      }
      if (!changed) break;
    }
  };

  /* A two-column matching board needs a gesture neither of the above makes: a *cross-row*
   * join, left row i onto right row j with i !== j. The carry pass only ever tries a row
   * against the same row, so it matches whichever items happen to line up and leaves the
   * rest - which reads as "undrivable" when it is really "under-driven". Most such boards
   * reveal an item after three failed attempts on it, so a systematic cross sweep also
   * walks a stuck board to completion rather than grinding one item forever. */
  const dragCross = () => {
    const layer = draggables()[0];
    if (!layer) return;
    let prev = readoutSig();
    for (let pass = 0; pass < 3; pass++) {
      let changed = false;
      for (const sy of SWEEP_Y) {            // left row
        for (const ey of SWEEP_Y) {          // right row
          if (sy === ey) continue;           // the carry pass already covers this
          for (const sx of [150, 230]) {
            for (const ex of [490, 570]) {
              safe('drag cross', () => dragLayer(layer, sx, sy, ex, ey));
              const now = readoutSig();
              if (now !== prev) { prev = now; changed = true; }
            }
          }
        }
      }
      if (!changed) break;
    }
  };

  /* Not every drag-and-drop archetype drags. Several place a point or a label with a
   * *tap* on the stage, and a tap never reaches a drag handler - so without this the
   * driver reports them undriven while the game is in fact perfectly drivable. */
  const tapAll = (budget) => {
    const layers = draggables();
    if (!layers.length) return;
    const cap = budget === undefined ? 120 : budget;
    const per = Math.min(SWEEP_X.length * SWEEP_Y.length,
                         Math.max(4, Math.floor(cap / layers.length)));
    for (const node of layers) {
      for (let i = 0; i < per; i++) {
        const x = SWEEP_X[i % SWEEP_X.length];
        const y = SWEEP_Y[Math.floor(i / SWEEP_X.length) % SWEEP_Y.length];
        safe('tap', () => node.dispatch('click', { clientX: x, clientY: y, preventDefault() {}, target: node }));
      }
    }
  };
  const clickButtons = (excludeIds) => {
    for (const node of buttons()) {
      const id = node.attrs.id;
      if (id === 'check' || id === 'next') continue;
      // Reset/Clear/Undo discard the learner's work. Pressing them between driving the
      // answer and pressing Check would wipe the very state being tested - the driver
      // would be sabotaging itself - so they are excluded while committing.
      if (excludeIds && excludeIds.includes(id)) continue;
      safe('click ' + (id || '(unnamed)'), () => node.dispatch('click', { preventDefault() {} }));
    }
  };
  /* `afterEach` is what makes a text/number input testable. Setting the value five times
   * and then pressing Check once leaves only the *last* value in the box when Check runs,
   * so a numeric answer is never actually submitted. Committing after every candidate is
   * the difference between driving an input and merely typing into it. */
  const driveInputs = (afterEach) => {
    for (const node of inputs()) {
      const type = (node.attrs.type || 'text').toLowerCase();
      const label = node.attrs.id || node.attrs['aria-label'] || type;
      const lo = parseFloat(node.attrs.min), hi = parseFloat(node.attrs.max);
      let values;
      if (type === 'range') {
        values = isFinite(lo) && isFinite(hi) ? [lo, (lo + hi) / 2, hi] : [1, 5, 9];
      } else if (type === 'number') {
        // A proportion wants 0.5, a count wants 5, an elasticity wants -0.75. Cover all
        // three, and honour any bounds the archetype declared.
        values = [0, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 12, -1];
        if (isFinite(lo)) values.push(lo);
        if (isFinite(hi)) values.push(hi);
        if (isFinite(lo) && isFinite(hi)) values.push((lo + hi) / 2);
      } else if (type === 'checkbox') {
        values = null;
      } else {
        // A text input may still be asking for a number ("how many comparisons?"), so
        // sweep small integers before falling back to a letter.
        values = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '12', '15', 'A'];
      }
      if (values === null) {
        safe('change ' + label, () => { node.checked = !node.checked; node.dispatch('change', {}); });
        if (afterEach) afterEach();
        continue;
      }
      for (const v of values) {
        safe('input ' + label, () => {
          node.value = String(v);
          node.dispatch('input', {});
          node.dispatch('change', {});
        });
        if (afterEach) afterEach();
      }
    }
  };
  const driveSelects = (afterEach) => {
    for (const node of selects()) {
      const label = node.attrs.id || node.attrs['aria-label'] || 'select';
      const opts = node.children.filter((c) => c.tagName === 'option');
      for (const o of opts) {
        safe('select ' + label, () => {
          node.value = o.attrs.value !== undefined ? o.attrs.value : o._text;
          node.dispatch('change', {});
        });
        if (afterEach) afterEach();
      }
    }
  };
  const clickCheck = () => {
    const node = ids['check'];
    if (node && !node.disabled && !node.hidden) safe('click check', () => node.dispatch('click', { preventDefault() {} }));
  };
  const clickNext = () => {
    const node = ids['next'];
    if (node && !node.disabled && !node.hidden) safe('click next', () => node.dispatch('click', { preventDefault() {} }));
  };

  // A button that only resets, clears, steps or checks is not something a learner can
  // *answer* with, so it does not make an archetype drivable on its own.
  const CONTROL_IDS = ['check', 'next', 'reset', 'clear', 'undo', 'back', 'fwd'];
  const answerButtons = buttons().filter((b) => !CONTROL_IDS.includes(b.attrs.id));
  // Can this archetype be driven at all? If there is nothing to press and nothing to
  // move, a zero-outcome result is honest but uninformative, and must not be a failure -
  // that is a gap in this driver, not a defect in the game.
  const drivable = !!(ids['check'] || inputs().length || selects().length
                      || draggables().length || answerButtons.length);
  // An archetype whose only controls are a Check/Reset button and a draggable layer is
  // geometry-bound: reaching a commit depends on pressing the right pixel, which this
  // driver cannot know. Its zero-outcome result is reported as untested, not as a bug.
  const geometryOnly = draggables().length > 0 && inputs().length === 0
                       && selects().length === 0 && answerButtons.length === 0;

  let stale = 0;
  for (let r = 0; r < MAX_ROUNDS; r++) {
    res.rounds += 1;
    const before = count();
    const marks = [];
    // The explore pass only has to prove that *something* the learner can do fails to
    // commit, so it samples the sweep rather than spending all of it; the full grid is
    // reserved for the commit pass, which is the one that has to actually finish a task.
    dragAll(200); tapAll(); dragCarry(); marks.push(['drag', count()]);
    clickButtons(); marks.push(['click', count()]);
    driveInputs(); marks.push(['input', count()]);
    driveSelects(); marks.push(['select', count()]);
    for (let i = 0; i < marks.length; i++) {
      if (marks[i][1] > before) {
        res.premature.push({ round: r, phase: marks[i][0] });
        break;
      }
    }

    const c0 = count();
    // Re-drive the controls before every Check. A multi-stage archetype (type a number,
    // then classify it, then read its sign) advances its stage on a correct answer, and
    // the next stage's control only exists after that - so driving once per round would
    // never reach the last stage. Each candidate value is committed as it is entered,
    // because a value only submitted while it is still in the box is a value actually
    // tested.
    for (let t = 0; t < 3; t++) {
      // Drag first, and drag again here rather than only in the explore phase: exploring
      // presses Reset, which discards a placed marker, and a geometry-bound task cannot be
      // committed without it. The full grid is spent here, not a slice of it, because the
      // last drag before Check is the one that decides whether the answer is complete.
      // Reset/Clear/Undo stay excluded below, so this state survives all three tries and
      // the geometry only has to be set up once per round.
      if (t === 0) { dragAll(DRAG_BUDGET); tapAll(); dragCarry(); dragCross(); }
      clickButtons(['reset', 'clear', 'undo']);
      driveInputs(clickCheck);
      driveSelects(clickCheck);
      clickCheck();
    }
    const gained = count() - c0;
    clickNext();
    if (gained === 0) {
      stale += 1;
      // A multi-stage archetype advances one stage per round of three tries, so a couple
      // of quiet rounds mean nothing. Only stop when the game has nothing left to press -
      // Check gone or disabled - and two rounds have passed without a commit.
      const checkNode = ids['check'];
      const exhausted = !checkNode || checkNode.disabled;
      if (stale >= 2 && exhausted) break;
    } else { stale = 0; }
  }

  res.feedback = ids['feedback'] ? String(ids['feedback'].textContent || '') : '';
  res.prompt = ids['prompt'] ? String(ids['prompt'].textContent || '') : '';
  // The last live readout is the game's own account of its state when the driver gave
  // up. Without it a "no outcome" verdict is unactionable; with it the owner can see
  // whether the driver never moved anything or moved the wrong thing. The timestamp is
  // dropped so that two runs of the same bundle produce byte-identical output and a CI
  // diff means a real change.
  const readouts = messages.filter((m) => m && m.type === 'luminfest:readout');
  if (readouts.length) {
    const last = Object.assign({}, readouts[readouts.length - 1]);
    delete last.at_ms;
    res.last_readout = last;
  } else {
    res.last_readout = null;
  }
  res.controls = {
    buttons: buttons().map((b) => b.attrs.id || '(unnamed)'),
    inputs: inputs().map((i) => (i.attrs.id || i.attrs['aria-label'] || '?') + ':'
      + (i.attrs.type || 'text') + '=' + i.value),
    selects: selects().map((s) => (s.attrs.id || '?') + '[' + s.children.length + ']='
      + (s.value || '')),
  };

  const final = outcomes();
  res.outcomes = final.length;
  let bare_wrong = 0;
  for (const o of final) {
    if (o.correct) res.correct += 1;
    else {
      res.wrong += 1;
      if (o.detail && o.detail.gave_up) res.gave_up += 1;
      else bare_wrong += 1;
    }
  }
  // A wrong outcome is a give-up, so it should say so; but a game that posts many of
  // them must not bury the report under one note per occurrence.
  if (bare_wrong) {
    res.notes.push(bare_wrong + ' wrong outcome(s) did not carry detail.gave_up');
  }
  if (res.premature.length) {
    /* `commits_on` is the archetype's own declaration of when an outcome is allowed, so
     * it decides this - not the presence of a Check button. A `completion` archetype has
     * a terminal state that *is* the answer (sorting every tile into a column), so an
     * outcome appearing mid-interaction is the design, not a leak. Falling back to the
     * markup only when the renderer withheld the field keeps old bundles usable, and the
     * fallback is deliberately the strict reading. */
    const commitsOn = res.commits_on || (ids['check'] ? 'check' : 'completion');
    if (commitsOn === 'check') {
      fail('posted an outcome before Check was pressed (' +
        res.premature.map((p) => p.phase).join(', ') + ')');
    } else {
      res.notes.push('committed during ' + res.premature[0].phase +
        ' with commits_on="completion" (declared commit-on-completion archetype)');
    }
  }
  if (res.double_posts) fail('a single commit posted more than one outcome');
  if (res.handler_errors.length) fail('a handler threw');
  if (final.some((o) => o.detail && o.detail.gave_up && o.correct)) {
    fail('a give-up outcome was marked correct');
  }
  if (!res.scored) {
    if (res.outcomes > 0) fail('an unscored sandbox posted an outcome');
  } else if (res.outcomes === 0) {
    if (!drivable || geometryOnly) {
      res.undriven = true;
      res.notes.push(geometryOnly
        ? 'geometry-bound: only a Check button and a draggable layer, so a commit was not reachable generically'
        : 'no controls could be found to drive this archetype');
    } else {
      fail('a scored game posted no outcome even though its controls were exercised');
    }
  }
  return res;
}

// ---------------------------------------------------------------------- driver

function main() {
  const input = process.argv[2];
  if (!input) { console.error('usage: playground_verify.mjs <pages.json>'); process.exit(2); }
  const entries = JSON.parse(fs.readFileSync(input, 'utf8'));
  const byArchetype = {};
  let failed = 0;

  for (const entry of entries) {
    let result;
    try {
      result = runEntry(entry);
    } catch (err) {
      result = { slug: entry.slug, archetype: entry.archetype, scored: entry.scored !== false,
                 ok: false, load_error: 'driver: ' + (err && err.message ? err.message : err),
                 handler_errors: [], outcomes: 0, correct: 0, wrong: 0, gave_up: 0,
                 rounds: 0, premature: [], double_posts: 0, undriven: false, notes: [] };
    }
    if (!result.ok) failed += 1;
    const bucket = byArchetype[result.archetype] || (byArchetype[result.archetype] =
      { games: 0, failed: 0, committed: 0, undriven: 0, outcomes: 0, gave_up: 0 });
    bucket.games += 1;
    bucket.outcomes += result.outcomes;
    bucket.gave_up += result.gave_up || 0;
    if (!result.ok) bucket.failed += 1;
    if (result.outcomes > 0) bucket.committed += 1;
    if (result.undriven) bucket.undriven += 1;
    console.log(JSON.stringify(result));
  }

  console.log('SUMMARY ' + JSON.stringify({ files: entries.length, failed, archetypes: byArchetype }));
  process.exit(failed ? 1 : 0);
}

main();
