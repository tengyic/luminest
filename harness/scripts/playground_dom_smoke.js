/* A generic DOM smoke driver for rendered playground games.
 *
 * The builders wrote per-archetype drivers that hand-trace a drag through the geometry
 * of one specific game. Those are excellent evidence for the games they cover and they
 * do not generalise: driving "place three points on y = 2x - 1" requires knowing where
 * the grid is. This driver does the opposite. It knows nothing about any archetype, and
 * instead exercises every handler the page registered, which is enough to catch the
 * whole class of bug that matters at this layer:
 *
 *   - a page whose build() throws on load, which the byte-level checks cannot see;
 *   - a page that calls a runtime helper which does not exist (an earlier revision of
 *     the reference archetype called `UI.outcome`, which was never defined - it
 *     rendered perfectly and threw the moment a learner pressed Check);
 *   - a handler that throws on a plain click or a plain drag.
 *
 * It is deliberately not a substitute for the per-archetype drivers. It proves a game
 * does not crash; it cannot prove a game is *right*. Correctness is asserted by the
 * content tests and by the builders' own drivers.
 *
 * Usage: node playground_dom_smoke.js <file.html> [<file.html> ...]
 * Prints one JSON object per file, then a JSON summary line prefixed with `SUMMARY `.
 */
'use strict';
const fs = require('fs');
const vm = require('vm');

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
  };
}

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
    // `class` and `classList` are two views of one thing in a real DOM. Keeping them
    // apart made `classList.contains('hidden')` lie about an element whose markup said
    // class="hidden", which is exactly the element the archetypes toggle.
    if (k === 'class') this.classList = classList(String(v).split(/\s+/).filter(Boolean));
  }
  getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) {
    delete this.attrs[k];
    if (k === 'class') this.classList = classList();
  }
  appendChild(c) { this.children.push(c); c.parentNode = this; return c; }
  insertBefore(c, ref) {
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(c); else this.children.splice(i, 0, c);
    c.parentNode = this; return c;
  }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; }
  replaceChildren() { this.children = []; }
  /* The standard node surface. `childNodes` is not an alias of `children` in the spec,
   * but for the element trees these pages build it holds the same nodes - and every
   * archetype that iterates a group does so through childNodes. Leaving it out made a
   * working archetype throw `Cannot read properties of undefined (reading 'length')`,
   * which is the stub lying about the DOM, not a product bug. */
  get childNodes() { return this.children; }
  get parentElement() { return this.parentNode; }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  get firstElementChild() { return this.children[0] || null; }
  get lastElementChild() { return this.children[this.children.length - 1] || null; }
  get nodeType() { return this.tagName === '#text' ? 3 : 1; }
  get nodeName() { return this.tagName === '#text' ? '#text' : this.tagName.toUpperCase(); }
  get ownerDocument() { return null; }
  addEventListener(t, h) { (this.listeners[t] = this.listeners[t] || []).push(h); }
  removeEventListener(t, h) {
    const list = this.listeners[t];
    if (list) { const i = list.indexOf(h); if (i >= 0) list.splice(i, 1); }
  }
  setPointerCapture() {}
  releasePointerCapture() {}
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
  /* Element-level querying. Archetypes use it on the groups they just built - a science
   * engine recolours its parts with `g.querySelector('rect')` - and the driver had no
   * such method on elements at all. */
  matches(sel) {
    const s = String(sel);
    if (s.startsWith('.')) return this.classList.contains(s.slice(1));
    if (s.startsWith('#')) return this.attrs.id === s.slice(1);
    return this.tagName === s.toLowerCase();
  }
  querySelector(sel) { return this.descendants().find((e) => e.matches(sel)) || null; }
  querySelectorAll(sel) { return this.descendants().filter((e) => e.matches(sel)); }
  getElementsByTagName(tag) {
    return this.descendants().filter((e) => e.tagName === String(tag).toLowerCase());
  }
  getElementsByClassName(cls) {
    return this.descendants().filter((e) => e.classList.contains(String(cls)));
  }
  contains(node) { return node === this || this.descendants().includes(node); }
  closest(sel) {
    let node = this;
    while (node) { if (node.matches && node.matches(sel)) return node; node = node.parentNode; }
    return null;
  }
}

/* Recreate every element the HTML declares, so the page's script finds the ids it
 * expects and so we can click the buttons it rendered. A page whose markup names an id
 * the script then looks up is the normal case; without this the script would silently
 * build into elements nothing ever displays. */
function seedFromMarkup(html, ids) {
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  let match;
  while ((match = tagRe.exec(html)) !== null) {
    const tag = match[1].toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'meta' || tag === 'title') continue;
    const idMatch = /\bid\s*=\s*["']([^"']+)["']/.exec(match[2]);
    if (!idMatch) continue;
    const node = new El(tag);
    const attrRe = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"/g;
    let attr;
    while ((attr = attrRe.exec(match[2])) !== null) node.setAttribute(attr[1], attr[2]);
    ids[idMatch[1]] = node;
  }
}

function run(file) {
  const html = fs.readFileSync(file, 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!script) return { file, ok: false, error: 'no <script> block' };
  const ids = {};
  seedFromMarkup(html, ids);
  const messages = [];
  const errors = [];
  // Every element the page creates, whether or not it has an id. Most archetypes build
  // their interactive layer in JavaScript - the draggable curve, the plot grid - and
  // those elements never appear in the markup, so iterating only `ids` finds no pointer
  // handlers at all and silently reports that every game has nothing to drag.
  const created = [];
  const document = {
    readyState: 'complete',
    createElement: (t) => { const e = new El(t); created.push(e); return e; },
    createElementNS: (ns, t) => { const e = new El(t); created.push(e); return e; },
    createTextNode: (t) => { const e = new El('#text'); e._text = String(t); return e; },
    getElementById: (id) => {
      if (!ids[id]) { const e = new El('div'); created.push(e); ids[id] = e; }
      return ids[id];
    },
    querySelector: (sel) => {
      const s = String(sel);
      if (s.startsWith('#')) return ids[s.slice(1)] || null;
      return Object.values(ids).concat(created).find((e) => e && e.matches(s)) || null;
    },
    querySelectorAll: (sel) => {
      const s = String(sel);
      if (s.startsWith('#')) return [ids[s.slice(1)]].filter(Boolean);
      return Object.values(ids).concat(created).filter((e) => e && e.matches(s));
    },
    addEventListener: () => {},
    documentElement: new El('html'),
    body: new El('body'),
  };
  /* The browser surface the pages reach for. `requestAnimationFrame` is asynchronous and
   * browser-scheduled in reality; invoking it synchronously with no bound turns a page's
   * self-re-arming frame loop - `function frame() { step(); paint(); raf(frame); }` -
   * into unbounded recursion, which surfaced as a bogus `Maximum call stack size
   * exceeded` on pages that are perfectly fine in a browser. A small budget still runs
   * the loop body without pretending the scheduler is synchronous.
   *
   * `setTimeout` returns an increasing id, never 0, because that is what browsers do and
   * archetypes branch on it (`if (flashTimer) window.clearTimeout(flashTimer)`). */
  let rafBudget = 6;
  let timerId = 0;
  const timers = {
    setTimeout: () => { timerId += 1; return timerId; },
    clearTimeout: () => {},
    setInterval: () => { timerId += 1; return timerId; },
    clearInterval: () => {},
    requestAnimationFrame: (fn) => {
      if (rafBudget-- > 0) {
        try { fn(Date.now()); } catch (e) { errors.push('raf: ' + (e && e.message ? e.message : e)); }
      }
      return 1;
    },
    cancelAnimationFrame: () => {},
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  const sandbox = {
    document,
    window: Object.assign({ parent: { postMessage: (p) => messages.push(p) } }, timers),
    console,
    performance: { now: () => Date.now() },
    getComputedStyle: timers.getComputedStyle,
    innerWidth: 860, innerHeight: 460, devicePixelRatio: 1,
    MutationObserver: class { observe() {} disconnect() {} },
    ResizeObserver: class { observe() {} disconnect() {} },
    IntersectionObserver: class { observe() {} disconnect() {} },
    Math, JSON, Date, isFinite, isNaN, Number, String, Boolean, Object, Array, Set, Map,
    parseFloat, parseInt,
  };
  Object.assign(sandbox, timers);
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;

  let loadError = null;
  try {
    vm.createContext(sandbox);
    vm.runInContext(script[1], sandbox, { filename: file, timeout: 5000 });
  } catch (err) {
    loadError = 'load: ' + (err && err.message ? err.message : String(err));
  }

  // Exercise the page until it commits, or until the search is exhausted.
  //
  // A single blind drag is not enough, and the reason is structural rather than
  // incidental: an archetype only scores a *valid* interaction - points actually on the
  // line, a tile actually on a target, coefficients that actually balance - so a sweep
  // through the middle of the stage produces a state the game correctly refuses to
  // score. Reporting "no outcome" from that would be reporting this driver's limitation
  // as a game defect.
  //
  // So the driver searches: bounded rounds of gestures across the stage, pressing the
  // commit control after each, stopping the moment the game reports. That is what a
  // persistent learner does, and it reaches the outcome contract on games whose geometry
  // this driver does not know.
  //
  // The sweep walks *every* element the page created, not only those the markup named:
  // an archetype's draggable layer is almost always built in JavaScript, and missing it
  // would make this driver report a clean run over games it never touched.
  const candidates = [];
  const seen = new Set();
  for (const node of Object.values(ids).concat(created)) {
    if (node && !seen.has(node)) { seen.add(node); candidates.push(node); }
  }
  const draggable = candidates.filter((n) => (n.listeners['pointerdown'] || []).length);
  const buttons = candidates.filter((n) => n.tagName === 'button' && n.getAttribute('id'));
  const fields = candidates.filter((n) => ['input', 'select', 'textarea'].includes(n.tagName));

  const countOutcomes = () => messages.filter((m) => m && m.type === 'luminfest:outcome').length;
  let drags = 0;
  const handlerErrors = [];
  function gesture(node, x, y) {
    try {
      const base = { pointerId: 1, preventDefault() {}, target: node };
      node.dispatch('pointerdown', { ...base, clientX: 430, clientY: 230 });
      node.dispatch('pointermove', { ...base, clientX: (430 + x) / 2, clientY: (230 + y) / 2 });
      node.dispatch('pointermove', { ...base, clientX: x, clientY: y });
      node.dispatch('pointerup', { ...base, clientX: x, clientY: y });
      drags += 1;
    } catch (err) {
      handlerErrors.push(`drag on ${describe(node)}: ${err && err.message ? err.message : err}`);
    }
  }
  function press(node) {
    try {
      node.dispatch('click', { preventDefault() {} });
    } catch (err) {
      handlerErrors.push(`click on #${node.getAttribute('id')}: ${err && err.message ? err.message : err}`);
      return false;
    }
    return true;
  }

  // The control a learner presses to commit, tried before Reset/Next so the search does
  // not immediately undo its own gesture.
  const COMMIT = /check|submit|verify|answer|confirm|lock|score/i;
  const commitButtons = buttons.filter((b) => COMMIT.test(b.getAttribute('id')));
  const otherButtons = buttons.filter((b) => !COMMIT.test(b.getAttribute('id')));
  const pressed = new Set();

  // Round zero: fill every field with a plausible value, in case the game scores a typed
  // answer rather than a dragged one. Guarded per field: an `input`/`change` handler that
  // throws is a finding about that handler, not a reason to abandon the whole run. This
  // is the exact path the childNodes defect escaped through.
  const FIELD_VALUES = ['1', '2', '5', '10', '0.5', '50'];
  fields.forEach((field, index) => {
    try {
      field.value = FIELD_VALUES[index % FIELD_VALUES.length];
      field.dispatch('input', { target: field });
      field.dispatch('change', { target: field });
    } catch (err) {
      handlerErrors.push(`field #${field.getAttribute('id')}: ${err && err.message ? err.message : err}`);
    }
  });

  const ROUNDS = 12;
  let round = 0;
  for (; round < ROUNDS; round += 1) {
    const x = 78 + ((round % 6) / 5) * (812 - 78);
    const y = 44 + ((Math.floor(round / 6) % 3) / 2) * (388 - 44);
    try {
      for (const node of draggable) gesture(node, x, y);
      if (round === 0) {
        for (const node of otherButtons) if (!pressed.has(node)) { pressed.add(node); press(node); }
      }
      for (const node of commitButtons) {
        if (countOutcomes() > 0) break;
        if (!press(node)) break;
      }
    } catch (err) {
      handlerErrors.push(`round ${round}: ${err && err.message ? err.message : err}`);
      break;
    }
    if (countOutcomes() > 0) break;
  }
  // Then every remaining control once, so Reset and Next are exercised too.
  for (const node of otherButtons) {
    if (pressed.has(node)) continue;
    pressed.add(node);
    if (!press(node)) break;
  }

  const allErrors = errors.concat(handlerErrors);
  const outcomes = messages.filter((m) => m && m.type === 'luminfest:outcome');
  return {
    file: file.split('/').pop(),
    ok: !loadError && allErrors.length === 0,
    load_error: loadError,
    handler_errors: allErrors.slice(0, 8),
    drags,
    draggable: draggable.length,
    buttons: buttons.map((b) => b.getAttribute('id')),
    fields: fields.length,
    rounds: round,
    readouts: messages.filter((m) => m && m.type === 'luminfest:readout').length,
    outcomes: outcomes.length,
    outcome_correct: outcomes.map((o) => !!o.correct),
  };
}

function describe(node) {
  const id = node.getAttribute && node.getAttribute('id');
  const series = node.getAttribute && node.getAttribute('data-series');
  return [node.tagName, id && '#' + id, series && `[${series}]`].filter(Boolean).join(' ');
}

/* One page must never take the run with it.
 *
 * This is not hypothetical: a handler that threw during field seeding escaped `run()`,
 * killed the process, and printed 27 results and no SUMMARY line - which reads as "the
 * driver found nothing" when in fact 18 files were never checked at all. A crash in file
 * 3 must be reported as a failing entry for file 3 and the loop must carry on to file 45.
 */
const files = process.argv.slice(2);
let failed = 0;
for (const file of files) {
  let result;
  try {
    result = run(file);
  } catch (err) {
    result = {
      file: file.split('/').pop(),
      ok: false,
      load_error: null,
      crash: err && err.stack
        ? String(err.stack).split('\n').slice(0, 3).join(' | ')
        : String(err),
      handler_errors: [],
      drags: 0,
      outcomes: 0,
    };
  }
  if (!result.ok) failed += 1;
  console.log(JSON.stringify(result));
}
console.log('SUMMARY ' + JSON.stringify({ files: files.length, failed }));
process.exit(failed ? 1 : 0);
