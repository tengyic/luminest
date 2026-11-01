/* A correctness oracle for rendered playground games.
 *
 * The sibling `playground_verify.mjs` answers "does it commit honestly?" - it drives
 * whatever handlers a page registered and checks that only Check commits, that a
 * give-up is never marked correct, and so on. It deliberately knows nothing about any
 * geometry, so it can never know the *right* answer.
 *
 * This one closes that gap. It is handed, for each case, a rendered page plus a list of
 * concrete actions that a learner would take to commit a *specific, spec-derived*
 * answer - either the right one or a wrong one - and it asserts:
 *
 *   1. a spec-derived correct answer must never come back `correct: false`
 *      (no inverted scoring);
 *   2. a spec-derived wrong answer must never come back `correct: true`;
 *   3. one commit posts at most one outcome;
 *   4. a give-up outcome (`detail.gave_up`) is never marked `correct: true`, and the
 *      case that deliberately burns three tries does carry `gave_up`.
 *
 * Nothing about the answer lives here: the cases file is produced by
 * `playground_correctness_cases.py`, which derives each answer from the *spec* (and,
 * where the spec alone is not enough, from an independent re-derivation of the subject
 * matter - a stoichiometry solver, a sorting trace, the gas law). This file only drives
 * the DOM and reads what the page posted back, exactly as `playground_verify.mjs` does.
 *
 * The stub DOM below is copied from `playground_verify.mjs` on purpose: both harnesses
 * must drive a page identically, or a difference between their verdicts would be a
 * difference in the harness rather than in the game.
 *
 * Usage: node playground_correctness.mjs <cases.json>
 *   <cases.json> is [{slug, archetype, label, html, actions, expect_correct,
 *                     expect_gave_up?}, ...]
 * Prints one JSON result per case, then a `SUMMARY {json}` line. Exits non-zero if any
 * case failed.
 */
import fs from 'node:fs';
import vm from 'node:vm';

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

//: The id registry for the run in flight. `setAttribute('id', ...)` must register the
//: element, because archetypes build a control and then read it back with
//: getElementById - a stub that handed back a different empty element for the same id
//: would make every such archetype look like it ignored its own controls.
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
  /* The scene must report the box its own `viewBox` declares, not a fixed 860x460.
   * `point()` maps a pointer through `min(rect.w/vb.w, rect.h/vb.h)` and re-centres,
   * so a stub that lies about the aspect ratio silently rescales every dispatched
   * drag - and a drag that misses its target looks exactly like a broken game. Four
   * archetypes declare a taller canvas (number_line and plot_points are 860x600), and
   * they were the four that failed this oracle for that reason alone. */
  getBoundingClientRect() {
    const box = this.viewBox();
    if (box) return { left: 0, top: 0, width: box[2], height: box[3], right: box[2], bottom: box[3] };
    return { left: 0, top: 0, width: 860, height: 460, right: 860, bottom: 460 };
  }
  viewBox() {
    const raw = this.attrs && this.attrs.viewBox;
    if (!raw) return null;
    const n = String(raw).trim().split(/[\s,]+/).map(Number);
    if (n.length !== 4 || !n.every((v) => isFinite(v))) return null;
    if (!(n[2] > 0 && n[3] > 0)) return null;
    return n;
  }
  // Faithful for nodes built at runtime; the markup seeder flattens nesting, so for
  // parsed nodes this falls back to `#scene` exactly as before.
  get ownerSVGElement() {
    let node = this.parentNode;
    while (node) {
      if (node.tagName === 'svg') return node;
      node = node.parentNode;
    }
    return null;
  }
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

/* Recreate every element the HTML declares, so the page's script finds the ids it
 * looks up and the class attributes (notably `hidden`) are real. */
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

// --------------------------------------------------------------------- one case

const CONTROL_IDS = ['check', 'next', 'reset', 'clear', 'undo', 'back', 'fwd'];

function runCase(entry) {
  const res = {
    slug: entry.slug, archetype: entry.archetype, label: entry.label || '',
    ok: true, load_error: null, failures: [], handler_errors: [],
    actions: 0, max_outcomes_per_action: 0, on_load_outcomes: 0,
    outcomes: [], expect_correct: [], expect_gave_up: [],
  };
  const fail = (kind, why) => { res.ok = false; res.failures.push({ kind, why }); };

  const expectCorrect = Array.isArray(entry.expect_correct)
    ? entry.expect_correct.slice() : [entry.expect_correct];
  const expectGaveUp = entry.expect_gave_up === undefined
    ? expectCorrect.map(() => null)
    : (Array.isArray(entry.expect_gave_up) ? entry.expect_gave_up.slice() : [entry.expect_gave_up]);
  res.expect_correct = expectCorrect;
  res.expect_gave_up = expectGaveUp;

  const scriptMatch = String(entry.html || '').match(/<script>([\s\S]*?)<\/script>/);
  if (!scriptMatch) { res.load_error = 'no <script> block'; res.ok = false; return res; }

  const ids = {};
  CURRENT_IDS = ids;
  const body = new El('body');
  seedFromMarkup(entry.html, ids, body);
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
    res.ok = false;
    return res;
  }

  const outcomes = () => messages.filter((m) => m && m.type === 'luminfest:outcome');
  const safe = (label, fn) => {
    try { fn(); } catch (e) { res.handler_errors.push(label + ': ' + (e && e.message ? e.message : e)); }
  };

  // Contract: merely loading a page commits nothing.
  res.on_load_outcomes = outcomes().length;
  if (res.on_load_outcomes > 0) fail('premature-outcome', 'posted an outcome on load, before any action');

  // ---- the declared controls this case may press ---------------------------
  const buttons = () => live().filter((e) => e.tagName === 'button' && !e.disabled && !e.hidden);
  const inputs = () => live().filter((e) => e.tagName === 'input' && !e.disabled && !e.hidden);
  const selects = () => live().filter((e) => e.tagName === 'select' && !e.disabled && !e.hidden);

  const byId = (id) => ids[id] || null;
  const byText = (text, cls) => buttons().find((b) => String(b.textContent) === String(text)
    && (!cls || b.classList.contains(cls)) && !CONTROL_IDS.includes(b.attrs.id)) || null;
  const byTextNot = (text, cls) => buttons().find((b) => String(b.textContent) !== String(text)
    && (!cls || b.classList.contains(cls)) && !CONTROL_IDS.includes(b.attrs.id)) || null;
  const byValue = (value) => live().find((e) => e.attrs['data-value'] === String(value)
    && !e.disabled && !e.hidden) || null;
  const byAria = (label) => live().find((e) => e.attrs['aria-label'] === String(label)
    && !e.disabled) || null;

  const fire = (node, type) => node.dispatch(type, { preventDefault() {}, target: node });
  const setValue = (node, value) => {
    node.value = String(value);
    fire(node, 'input');
    fire(node, 'change');
  };

  // ---- one action ----------------------------------------------------------
  function apply(a) {
    switch (a.type) {
      case 'click': {
        const node = byId(a.id);
        if (!node) return 'no element #' + a.id;
        if (node.disabled) return '#' + a.id + ' is disabled';
        safe('click #' + a.id, () => fire(node, 'click'));
        return null;
      }
      case 'click_text': {
        const node = byText(a.text, a.cls);
        if (!node) return 'no button reading "' + a.text + '"';
        safe('click_text ' + a.text, () => fire(node, 'click'));
        return null;
      }
      case 'click_not_text': {
        const node = byTextNot(a.text, a.cls);
        if (!node) return 'no button other than "' + a.text + '"';
        safe('click_not_text ' + a.text, () => fire(node, 'click'));
        return null;
      }
      case 'click_value': {
        const node = byValue(a.value);
        if (!node) return 'no control with data-value "' + a.value + '"';
        safe('click_value ' + a.value, () => fire(node, 'click'));
        return null;
      }
      case 'click_aria': {
        const node = byAria(a.label);
        if (!node) return 'no control labelled "' + a.label + '"';
        safe('click_aria ' + a.label, () => fire(node, 'click'));
        return null;
      }
      case 'key': {
        const node = byAria(a.aria);
        if (!node) return 'no control labelled "' + a.aria + '"';
        safe('key ' + a.aria, () => node.dispatch('keydown',
          { key: 'Enter', preventDefault() {}, target: node }));
        return null;
      }
      case 'set': {
        const node = byId(a.id);
        if (!node) return 'no element #' + a.id;
        safe('set #' + a.id, () => setValue(node, a.value));
        return null;
      }
      case 'set_aria': {
        const node = byAria(a.aria);
        if (!node) return 'no control labelled "' + a.aria + '"';
        safe('set_aria ' + a.aria, () => setValue(node, a.value));
        return null;
      }
      case 'select': {
        const node = byId(a.id);
        if (!node) return 'no element #' + a.id;
        safe('select #' + a.id, () => { node.value = String(a.value); fire(node, 'change'); });
        return null;
      }
      case 'drag': {
        // A page may wire more than one draggable layer (ppf_frontier: the point along
        // the frontier, and the handle that grows it). `on: 'last'` reaches the second.
        const layers = live().filter((e) => (e.listeners['pointerdown'] || []).length);
        const layer = a.on === 'last' ? layers[layers.length - 1] : layers[0];
        if (!layer) return 'no draggable layer';
        const base = { pointerId: 1, preventDefault() {}, target: layer };
        const [sx, sy] = a.from, [ex, ey] = a.to;
        safe('drag', () => {
          layer.dispatch('pointerdown', Object.assign({ clientX: sx, clientY: sy }, base));
          layer.dispatch('pointermove', Object.assign({ clientX: (sx + ex) / 2, clientY: (sy + ey) / 2 }, base));
          layer.dispatch('pointermove', Object.assign({ clientX: ex, clientY: ey }, base));
          layer.dispatch('pointerup', Object.assign({ clientX: ex, clientY: ey }, base));
        });
        return null;
      }
      default:
        return 'unknown action type ' + a.type;
    }
  }

  // ---- drive ---------------------------------------------------------------
  for (const a of entry.actions || []) {
    res.actions += 1;
    const before = outcomes().length;
    const problem = apply(a);
    if (problem) fail('unreachable-control', 'action ' + res.actions + ' (' + a.type + '): ' + problem);
    const delta = outcomes().length - before;
    if (delta > res.max_outcomes_per_action) res.max_outcomes_per_action = delta;
    if (delta > 1) {
      fail('multi-commit', 'action ' + res.actions + ' (' + a.type + ') posted ' + delta
        + ' outcomes; a single commit must post at most one');
    }
  }

  if (res.handler_errors.length) fail('handler-threw', 'a handler threw');

  const got = outcomes().map((o) => ({
    correct: !!o.correct,
    gave_up: !!(o.detail && o.detail.gave_up),
    task: o.task === undefined ? null : o.task,
    kind: o.kind === undefined ? null : o.kind,
    detail: o.detail || {},
  }));
  res.outcomes = got;

  if (got.length !== expectCorrect.length) {
    fail('outcome-count', 'expected ' + expectCorrect.length + ' outcome(s), got '
      + got.length + ' (' + JSON.stringify(got.map((o) => o.correct)) + ')');
  }

  for (let i = 0; i < got.length; i++) {
    const o = got[i];
    if (i < expectCorrect.length) {
      if (expectCorrect[i] === true && o.correct === false) {
        fail('correct-scored-wrong', 'outcome ' + i + ' should have been correct but came '
          + 'back correct:false - ' + JSON.stringify(o));
      }
      if (expectCorrect[i] === false && o.correct === true) {
        fail('wrong-scored-correct', 'outcome ' + i + ' should have been wrong but came '
          + 'back correct:true - ' + JSON.stringify(o));
      }
    }
    const wantGaveUp = i < expectGaveUp.length ? expectGaveUp[i] : null;
    if (wantGaveUp !== null && o.gave_up !== !!wantGaveUp) {
      fail('gave-up-mismatch', 'outcome ' + i + ' gave_up=' + o.gave_up + ', expected '
        + !!wantGaveUp + ' - ' + JSON.stringify(o));
    }
    if (o.gave_up && o.correct) {
      fail('give-up-marked-correct', 'outcome ' + i + ' is a give-up but was marked '
        + 'correct:true - ' + JSON.stringify(o));
    }
  }

  return res;
}

// ----------------------------------------------------------------------- driver

function main() {
  const input = process.argv[2];
  if (!input) { console.error('usage: playground_correctness.mjs <cases.json>'); process.exit(2); }
  const entries = JSON.parse(fs.readFileSync(input, 'utf8'));
  const byArchetype = {};
  const byKind = {};
  let failed = 0;

  for (const entry of entries) {
    let result;
    try {
      result = runCase(entry);
    } catch (err) {
      result = { slug: entry.slug, archetype: entry.archetype, label: entry.label || '',
                 ok: false, load_error: 'driver: ' + (err && err.message ? err.message : err),
                 failures: [{ kind: 'driver', why: String(err && err.stack || err) }],
                 handler_errors: [], actions: 0, max_outcomes_per_action: 0,
                 on_load_outcomes: 0, outcomes: [],
                 expect_correct: [], expect_gave_up: [] };
    }
    if (!result.ok) failed += 1;
    const bucket = byArchetype[result.archetype]
      || (byArchetype[result.archetype] = { cases: 0, failed: 0 });
    bucket.cases += 1;
    if (!result.ok) bucket.failed += 1;
    for (const f of result.failures) byKind[f.kind] = (byKind[f.kind] || 0) + 1;
    console.log(JSON.stringify(result));
  }

  console.log('SUMMARY ' + JSON.stringify({
    cases: entries.length,
    failed,
    passed: entries.length - failed,
    archetypes_covered: Object.keys(byArchetype).sort(),
    failure_kinds: byKind,
    by_archetype: byArchetype,
  }));
  process.exit(failed ? 1 : 0);
}

main();
