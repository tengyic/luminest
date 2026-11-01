/* Real-browser verification of the rendered playground games.
 *
 * Every other checker in this directory drives a HAND-WRITTEN DOM stub. The stub fakes
 * `getBoundingClientRect`, event dispatch, layout, and animation frames. If the stub is
 * wrong in a way that matters, every "failed: 0" verdict it produces is wrong together,
 * and nothing else we run would notice. This file exists to catch exactly that: it loads
 * each rendered game in a real Chromium, inside an iframe, and reports where the real
 * browser DISAGREES with the stub.
 *
 * A pass count is not the deliverable here. The disagreements are.
 *
 * Why an iframe: the runtime posts with `window.parent.postMessage(payload, '*')`
 * (runtime.py:197). Loading a game top-level would make `window.parent === window`, so
 * the message would arrive but the bridge being exercised would not be the real one.
 *
 * Why the driver instruments `addEventListener` instead of sweeping blindly: a blind
 * coordinate sweep committed 7 of 45 games, which says nothing about the games and
 * everything about the driver. The stub commits 37 because it drives the handlers the
 * page registered. A real browser can do the same honestly - patch `addEventListener`
 * before the page's own script runs, tag every element that registered a `pointerdown`
 * or `click`, and then drive those exact elements with real mouse events. Anything less
 * is not a comparison, it is a weaker driver losing.
 *
 * Usage: node playground_browser_check.mjs <games_dir> [out.json]
 *   <games_dir> holds one `<slug>.html` per game, written by playground_dump_pages.py.
 * Prints one JSON result per game, then a `SUMMARY {json}` line.
 */
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';

// Playwright lives in the isolated workspace, not next to this script, and NODE_PATH
// does not apply to ESM resolution. createRequire rooted at the workspace is the one
// spelling that finds it without installing anything globally.
const require = createRequire('/Users/tengyi/.workbuddy-ai/binaries/node/workspace/');
const { chromium } = require('playwright');

const GAMES_DIR = path.resolve(process.argv[2] || '');
const OUT_JSON = process.argv[3] || null;
//: Optional. `pages.json` from `playground_render_pages.py`, used only to read each page's
//: `commits_on`. Without it the driver cannot tell a commit-on-completion page (which is
//: *supposed* to post an outcome as soon as the board is finished) from a commit-on-check
//: one (which must post nothing until Check is pressed), so it reports the raw count
//: instead of a verdict.
const PAGES_JSON = process.argv[4] || null;

let COMMITS_ON = {};
if (PAGES_JSON && fs.existsSync(PAGES_JSON)) {
  try {
    for (const p of JSON.parse(fs.readFileSync(PAGES_JSON, 'utf8'))) {
      COMMITS_ON[p.slug] = p.commits_on || 'check';
    }
  } catch (err) { COMMITS_ON = {}; }
}

//: Controls a learner presses to commit. Mirrors the stub's list so the two drivers are
//: answering the same question; if they diverge, a difference in results would be the
//: driver's fault rather than the page's.
const COMMIT = /check|submit|verify|answer|confirm|lock|score/i;

//: Controls that throw work away. The stub learned this the expensive way: pressing
//: `reset` after dragging wipes the board before Check, so a fully driven game reports
//: no outcome and looks broken. They are excluded from the interaction phases and never
//: pressed at all.
const DESTRUCTIVE = /reset|clear|undo|start over|restart/i;

//: Bounds. The pairwise tap sweep is O(n^2) and a real browser is ~100x slower than the
//: stub, so both phases need a ceiling or one pathological page stalls the run.
const DRAG_BUDGET = 260;
//: Attempts per draggable piece. See the cap in the drag loop: an already-placed piece
//: ignores drags, so an uncapped handle spends the whole grid on nothing.
const DRAG_TARGETS_PER_HANDLE = 6;
const TAP_LIMIT = 24;
const TAP_BUDGET = 420;
//: Above this many controls, the tap sweep stops trying same-kind pairs. A large board
//: of one kind is a sort/place game whose destinations are the other kind, so same-kind
//: pairs are pure re-selection there; a matching game is small by construction.
const SAME_KIND_LIMIT = 8;

//: Runs in every frame before any page script. Records which elements the page bound a
//: pointer or click handler to, so the driver can drive the real controls rather than
//: guess coordinates. Wrapped in try/catch because a page must not be able to break the
//: instrument, and the instrument must never change what the page observes.
const INSTRUMENT = () => {
  try {
    const bound = { pointerdown: [], click: [], input: [], change: [] };
    window.__bound = bound;
    const original = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function (type, fn, opts) {
      try {
        if (bound[type] && this && this.nodeType === 1 && bound[type].indexOf(this) === -1) {
          bound[type].push(this);
        }
      } catch (err) { /* never let instrumentation throw into the page */ }
      return original.call(this, type, fn, opts);
    };
  } catch (err) { /* if this fails the driver falls back to a coarse sweep */ }
};

function wrapperHtml(slug) {
  return `<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0">
<iframe id="f" src="/game/${encodeURIComponent(slug)}.html"
        style="width:1000px;height:700px;border:0"></iframe>
<script>
window.__msgs = [];
window.__errs = [];
window.addEventListener('message', function (e) {
  var d = e.data;
  window.__msgs.push({ type: d && d.type, data: d, t: Math.round(performance.now()) });
});
window.addEventListener('error', function (e) {
  window.__errs.push(String(e && e.message ? e.message : e));
});
</script>
</body></html>`;
}

function startServer() {
  const root = GAMES_DIR;
  const server = http.createServer((req, res) => {
    let url;
    try {
      url = new URL(req.url, 'http://127.0.0.1');
    } catch (err) {
      res.writeHead(400); res.end('bad url'); return;
    }
    if (url.pathname === '/frame') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(wrapperHtml(url.searchParams.get('slug') || ''));
      return;
    }
    if (url.pathname.startsWith('/game/')) {
      const name = decodeURIComponent(url.pathname.slice('/game/'.length));
      const file = path.resolve(root, name);
      // Refuse anything that escapes the games directory, so a crafted slug cannot turn
      // this checker into a file server.
      if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) {
        res.writeHead(404); res.end('not found'); return;
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(fs.readFileSync(file));
      return;
    }
    res.writeHead(404); res.end('not found');
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }));
  });
}

const SNAPSHOT = () => {
  const msgs = window.__msgs || [];
  const outcomes = msgs.filter((m) => m.type === 'luminfest:outcome');
  const readouts = msgs.filter((m) => m.type === 'luminfest:readout');
  let frameTextLength = -1;
  let frameControls = -1;
  try {
    const doc = document.getElementById('f').contentDocument;
    frameTextLength = doc.body ? doc.body.innerText.trim().length : -1;
    frameControls = doc.querySelectorAll('button, input, select, [role=button]').length;
  } catch (err) { /* not ready: reported as -1 */ }
  return {
    outcomes: outcomes.length,
    readouts: readouts.length,
    //: The most recent readout, as a string. A changed readout between two interactions
    //: is proof an event reached a handler, which is the only honest progress signal a
    //: driver has - the page posts nothing else until it commits.
    lastReadout: readouts.length ? JSON.stringify(readouts[readouts.length - 1].data) : '',
    windowErrors: (window.__errs || []).length,
    frameTextLength,
    frameControls,
    outcomePayloads: outcomes.map((m) => m.data),
  };
};

//: A coarse identity for each tagged control, so the tap sweep can tell a source from a
//: destination. Deliberately built from the page's own markup - tag name, first class,
//: and the `data-series` stem - rather than from anything the driver assigns, because it
//: has to survive a rebuild of the board.
const KINDS = () => {
  return [...document.querySelectorAll('[data-wb-tap]')].map((el) => {
    const cls = (el.getAttribute('class') || '').trim().split(/\s+/)[0] || '';
    const series = (el.getAttribute('data-series') || '').replace(/-[^-]*$/, '');
    return el.tagName + '|' + cls + '|' + series;
  });
};

//: Each tagged control's id and visible text, so the driver can skip the ones that throw
//: work away. The pairwise sweep needs this as much as `clickAll` does: pressing `reset`
//: as a *source* mid-sweep wipes every placement made so far, so the board is destroyed
//: and rebuilt over and over and the page can never reach its terminal state.
const LABELS = () => {
  return [...document.querySelectorAll('[data-wb-tap]')].map((el) => {
    let text = '';
    try { text = (el.textContent || '').trim().slice(0, 30); } catch (e) { text = ''; }
    return { id: el.getAttribute('id') || '', text };
  });
};

//: Tag the elements the page actually bound handlers to, so they can be addressed from
//: the driver by attribute rather than by a guessed selector.
//:
//: Re-run after any interaction that may rebuild the DOM. A page that re-renders its
//: board (most do, on every placement) replaces its controls with fresh elements, and
//: the earlier tags go with them - so a single tag at load leaves the drag phase with
//: nothing to address and it reports "0 drags" for a page full of draggable pieces.
//: `window.__bound` accumulates the handlers of every build, so the stale entries have
//: to be filtered out; `isConnected` is what makes the re-tag a refresh rather than a
//: pile of detached nodes.
const TAG_CONTROLS = () => {
  const b = window.__bound || { pointerdown: [], click: [] };
  b.pointerdown.forEach((el, i) => {
    try { if (el.isConnected) el.setAttribute('data-wb-drag', String(i)); } catch (e) {}
  });
  b.click.forEach((el, i) => {
    try { if (el.isConnected) el.setAttribute('data-wb-tap', String(i)); } catch (e) {}
  });
  return {
    drag: b.pointerdown.filter((el) => { try { return el.isConnected; } catch (e) { return false; } }).length,
    tap: b.click.filter((el) => { try { return el.isConnected; } catch (e) { return false; } }).length,
  };
};

//: Install a viewBox -> frame-client mapper, and report the scene's viewBox.
//:
//: This is not a convenience. The first version of this driver aimed at fractions of the
//: IFRAME, and every drag missed: in `sort_columns` the bins occupy viewBox y 50..268,
//: which lands at frame y ~227..375, while the frame-relative grid was aiming at y ~140 -
//: above the bins, in the header. Every game drew its targets somewhere the driver was not
//: looking, so "0 committed" measured the driver, not the games. Deriving the mapping from
//: the scene's own `viewBox` and rect is the only way to aim where the page actually drew.
const MAP_HELPER = () => {
  const read = () => {
    const svg = document.getElementById('scene');
    if (!svg) return null;
    const raw = (svg.getAttribute('viewBox') || '0 0 900 500').trim().split(/[\s,]+/).map(Number);
    if (raw.length !== 4 || raw.some((n) => !isFinite(n))) return [0, 0, 900, 500];
    return raw;
  };
  window.__viewBox = read();
  window.__mapPoint = function (vx, vy) {
    const svg = document.getElementById('scene');
    const vb = window.__viewBox;
    if (!svg || !vb) return null;
    const r = svg.getBoundingClientRect();
    // The archetypes letterbox: they scale by the smaller axis and centre the result, so
    // a naive `r.width / vb[2]` would drift on any page whose aspect ratio differs.
    const s = Math.min(r.width / vb[2], r.height / vb[3]) || 1;
    const ox = (r.width - vb[2] * s) / 2;
    const oy = (r.height - vb[3] * s) / 2;
    return { x: r.left + ox + (vx - vb[0]) * s, y: r.top + oy + (vy - vb[1]) * s };
  };
  return window.__viewBox;
};

async function runOne(browser, base, slug) {
  const page = await browser.newPage({ viewport: { width: 1100, height: 820 } });
  const pageErrors = [];
  const consoleErrors = [];
  const failedRequests = [];
  page.on('pageerror', (e) => pageErrors.push(String((e && e.message) || e)));
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('requestfailed', (r) => {
    failedRequests.push(r.url() + ' :: ' + ((r.failure() && r.failure().errorText) || '?'));
  });
  // Must precede goto: the instrument has to be in place before the game's own script
  // registers its handlers, or it records nothing.
  await page.addInitScript(INSTRUMENT);

  const res = {
    slug, ok: true, load_error: null,
    pageErrors: [], consoleErrors: [], failedRequests: [],
    outcomesBefore: 0, outcomesAfter: 0, readoutsBefore: 0, readoutsAfter: 0,
    frameTextLength: -1, frameControls: -1, drags: 0, taps: 0, committed: false, notes: [],
  };

  try {
    await page.goto(`${base}/frame?slug=${encodeURIComponent(slug)}`, { waitUntil: 'load' });
    await page.waitForTimeout(400);

    const before = await page.evaluate(SNAPSHOT);
    res.outcomesBefore = before.outcomes;
    res.readoutsBefore = before.readouts;
    res.frameTextLength = before.frameTextLength;
    res.frameControls = before.frameControls;
    if (before.outcomes > 0) res.notes.push('posted an outcome on load, before any interaction');
    if (before.frameTextLength === 0) res.notes.push('frame rendered empty');

    const frame = page.frames().find((f) => f !== page.mainFrame());
    if (!frame) throw new Error('the game frame never appeared');

    const tagged = await frame.evaluate(TAG_CONTROLS);
    //: Counts of events actually delivered, not of controls discovered. A control that
    //: was found but never successfully clicked would otherwise be reported as driven.
    const activity = { drags: 0, taps: 0, dragHandles: tagged.drag, tapHandles: tagged.tap };

    const clickAll = async (selector) => {
      const nodes = await frame.$$(selector);
      for (const node of nodes) {
        let id = '';
        let text = '';
        try { id = (await node.getAttribute('id')) || ''; } catch (err) { id = ''; }
        try { text = (await node.innerText()) || ''; } catch (err) { text = ''; }
        if (COMMIT.test(id) || (COMMIT.test(text) && text.length < 30)) continue; // commit later
        if (DESTRUCTIVE.test(id) || DESTRUCTIVE.test(text)) continue; // would wipe the work
        try { await node.click({ timeout: 900 }); activity.taps += 1; } catch (err) { /* covered or gone */ }
      }
    };

    const outcomesNow = async () => (await page.evaluate(SNAPSHOT)).outcomes;

    //: The outcome count captured immediately before the FIRST press of any commit
    //: control, wherever that happens. This is the real test of the central rule: for a
    //: commit-on-check archetype nothing may have been posted by exploring alone. It
    //: cannot be measured "just before step 5", because the tap sweep legitimately
    //: presses Check to advance a staged game - counting from step 5 would attribute the
    //: driver's own press to the page and report a violation on 15 perfectly correct
    //: games.
    let outcomesBeforeFirstCommit = null;
    const noteCommitPress = async () => {
      if (outcomesBeforeFirstCommit === null) outcomesBeforeFirstCommit = await outcomesNow();
    };
    const isCommit = (label) => !!label && (COMMIT.test(label.id)
      || (COMMIT.test(label.text) && label.text.length < 30));

    // 1. Progress any choice-driven stage first, so a multi-stage game is not still
    //    sitting on stage one when the drags happen.
    await clickAll('[data-wb-tap]');

    // 2. Pairwise tap sweep. Tap-based games place a piece by selecting a source and then
    //    pressing a destination; neither click alone does anything, so clicking every
    //    control once (step 1) cannot complete one. Defined here and called after the
    //    drags: a drag phase that runs on a clean board places pieces in one attempt each,
    //    whereas a tap sweep that runs first leaves the board mid-animation and the drags
    //    then measure moving targets. The sweep's job is the mop-up.
    const tapSweep = async () => {
      if (await outcomesNow() > 0) return;
      outer:
      for (let i = 0; i < TAP_LIMIT; i++) {
        // Re-resolve for every source. A placement rebuilds the board, and a Playwright
        // handle to a replaced element is detached forever - clicking it throws for the
        // rest of the run. Holding one list for the whole sweep is what made an
        // 18-control page stop after 24 of its 306 pairs and report the rest as "not
        // driven", when the real cause was that every later handle was dead.
        await frame.evaluate(TAG_CONTROLS);
        let srcs = [];
        try { srcs = await frame.$$('[data-wb-tap]'); } catch (err) { break outer; }
        if (i >= srcs.length) break outer;
        let kinds = [];
        try { kinds = await frame.evaluate(KINDS); } catch (err) { break outer; }
        if (i >= kinds.length) break outer;
        let labels = [];
        try { labels = await frame.evaluate(LABELS); } catch (err) { break outer; }
        // A destructive control is never a source: `reset` clears the board, so sweeping
        // from it destroys every placement the sweep has made.
        if (labels[i] && (DESTRUCTIVE.test(labels[i].id) || DESTRUCTIVE.test(labels[i].text))) continue;

        // Order destinations: a different KIND of control first, then the same kind.
        // In a select-then-place game the sources are one kind of thing (tiles) and the
        // destinations are another (bins), so pairing across kinds finds the mechanic
        // immediately; pairing same-kind only re-selects and burns the budget before the
        // sweep reaches the controls that matter. Same-kind pairs are still tried - some
        // games genuinely match like against like (`matching_pairs`) - but only on a
        // small board, because on a 14-tile one they are 13 wasted re-selections per tile
        // and they exhaust the budget before the drag phase gets a turn.
        const ok = (j) => {
          if (j === i) return false;
          const l = labels[j];
          if (l && (DESTRUCTIVE.test(l.id) || DESTRUCTIVE.test(l.text))) return false;
          return true;
        };
        const order = [];
        for (let j = 0; j < srcs.length; j++) if (ok(j) && kinds[j] !== kinds[i]) order.push(j);
        if (srcs.length <= SAME_KIND_LIMIT) {
          for (let j = 0; j < srcs.length; j++) if (ok(j) && kinds[j] === kinds[i]) order.push(j);
        }

        for (const j of order) {
          let dsts = [];
          // Re-tag before re-resolving. The attribute is set by the driver, not by the
          // page, so a rebuilt element carries none of it: without this the selector
          // matches nothing after the first placement and the sweep silently stops.
          try { await frame.evaluate(TAG_CONTROLS); } catch (err) { break outer; }
          try { dsts = await frame.$$('[data-wb-tap]'); } catch (err) { break outer; }
          if (j >= dsts.length) continue;
          if (isCommit(labels[i]) || isCommit(labels[j])) await noteCommitPress();
          let clicked = false;
          try { await srcs[i].click({ timeout: 600, force: true }); clicked = true; } catch (err) { clicked = false; }
          try { await dsts[j].click({ timeout: 600, force: true }); clicked = true; } catch (err) { clicked = false; }
          if (clicked) activity.taps += 2;
          if (await outcomesNow() > 0) break outer;
          if (activity.taps > TAP_BUDGET) break outer;
        }
      }
    };

    // 3. Drag every control the page bound a pointer handler to, onto a grid of real
    //    targets laid out in the SCENE's own coordinate space. Real mouse events, real
    //    layout - see MAP_HELPER for why the targets cannot be iframe-relative.
    //
    //    Every handle is dragged, not the first few. A completion-committing archetype
    //    (`sort_columns`) only posts its outcome once every tile is placed, so capping
    //    the handle list makes completion impossible and reports "0 committed" for a
    //    page that is working perfectly - which is what the first version of this file
    //    did with `.slice(0, 8)`.
    const dragPhase = async () => {
      // Re-tag first: the tap sweep and every placement rebuild the board, so the
      // attributes set at load are stale by the time this runs.
      await frame.evaluate(TAG_CONTROLS);
      const box = await page.locator('#f').boundingBox();
      if (!box) return;
      const viewBox = await frame.evaluate(MAP_HELPER);
      const dragHandles = await frame.$$('[data-wb-drag]');
      let targets = [];
      if (viewBox) {
        const local = await frame.evaluate(([vx, vy, vw, vh]) => {
          const out = [];
          // The column order alternates sides on purpose. A left-to-right sweep gives a
          // piece whose home is the RIGHT-hand drop zone three consecutive attempts at
          // the left-hand one - which exhausts the three-try budget and reveals the
          // answer before the correct target is ever tried, so the game can never be
          // completed and reports "0 committed" while working perfectly. Alternating
          // means the first two targets for any piece are on opposite sides, which for a
          // two-zone layout is one attempt per zone.
          for (const cy of [0.14, 0.4, 0.68, 0.92]) {
            for (const cx of [0.25, 0.75, 0.08, 0.4, 0.6, 0.92]) {
              const p = window.__mapPoint(vx + vw * cx, vy + vh * cy);
              if (p) out.push([p.x, p.y]);
            }
          }
          return out;
        }, viewBox);
        // `__mapPoint` returns frame-client coordinates; `page.mouse` speaks page
        // coordinates, so the iframe's own offset has to be added back.
        targets = local.map(([x, y]) => [box.x + x, box.y + y]);
      }
      if (!targets.length) return;
      for (const handle of dragHandles) {
        let hb;
        try { hb = await handle.boundingBox(); } catch (err) { hb = null; }
        if (!hb) continue;
        const homeX = hb.x + hb.width / 2;
        const homeY = hb.y + hb.height / 2;
        let tried = 0;
        for (const [tx, ty] of targets) {
          // Cap the attempts per piece. A piece that has already been placed ignores the
          // drag entirely, so it never moves and the `moved` test below never fires - the
          // handle then burns the whole 24-target grid doing nothing, which is enough for
          // two or three inert pieces to exhaust the entire drag budget. The alternating
          // column order means the first two targets already cover both drop zones, so a
          // handful of attempts is all a live piece can need.
          if (tried >= DRAG_TARGETS_PER_HANDLE) break;
          tried += 1;
          try {
            await page.mouse.move(homeX, homeY);
            await page.mouse.down();
            await page.mouse.move(tx, ty, { steps: 3 });
            await page.mouse.up();
            activity.drags += 1;
          } catch (err) { /* a drag that lands nowhere is not an error */ }
          if (await outcomesNow() > 0) return;
          // Did the piece STAY where it was dropped, or bounce back to its tray slot?
          // This is the one signal that separates "accepted" from "rejected" without
          // knowing anything about the archetype: a placed piece is redrawn at the drop
          // site, so its box moves; a rejected one is animated home, so its box does not.
          // Without it the driver cannot tell a solved tile from a bounced one and
          // abandons every tile whose first target happened to be the wrong column -
          // which is why `sort_columns` reported "0 committed" while a manual drag of the
          // same tile into the same bin scored `correct_drops: 1`.
          let moved = true;
          try {
            // A rejected piece is animated home, so measuring immediately reads it at the
            // drop site and every tile looks accepted. Wait for the transition to settle
            // before deciding, or the test measures the animation rather than the result.
            await page.waitForTimeout(220);
            const hb2 = await handle.boundingBox();
            moved = !hb2 || Math.abs(hb2.x + hb2.width / 2 - homeX) > 8
                         || Math.abs(hb2.y + hb2.height / 2 - homeY) > 8;
          } catch (err) { moved = true; }
          if (moved) break; // accepted: this handle is done, move to the next piece
          if (activity.drags > DRAG_BUDGET) return;
        }
      }
    };
    await dragPhase();
    // The exploration measurement. Taken HERE - after the non-commit taps and one drag
    // pass, but before the tap sweep, which is allowed to press Check to advance a staged
    // game. Measured any later it is trivially zero for every page, because the sweep
    // reaches a commit control within its first few pairs and the count is captured after
    // that press: all 45 pages read 0, which looked like a clean result and was actually
    // a measurement taken too late to mean anything.
    res.outcomesAfterExplore = await outcomesNow();
    res.commits_on = COMMITS_ON[slug] || null;
    // Mop up with the reliable path, then give the drags one more turn: a page whose
    // board was rebuilt by a placement has fresh geometry, and pieces the tap sweep could
    // not reach (because they only respond to a drag) get a second chance here.
    await tapSweep();
    await dragPhase();

    // 4. Advance a staged game, then give the drag and tap phases one more pass: many
    //    archetypes reveal stage two only after stage one is committed.
    const nextBtns = await frame.$$('button');
    for (const b of nextBtns) {
      let id = '';
      try { id = (await b.getAttribute('id')) || ''; } catch (err) { id = ''; }
      if (/^next$/i.test(id) || /next|continue/i.test(id)) {
        if (await outcomesNow() > 0) break;
        try { await b.click({ timeout: 800 }); } catch (err) { /* covered */ }
        await page.waitForTimeout(120);
        await dragPhase();
        break;
      }
    }

    // 5. Commit.
    //    The count before the FIRST commit press anywhere in this run is what tests the
    //    central rule; see `noteCommitPress`.
    await noteCommitPress();
    const buttons = await frame.$$('button, [role=button]');
    for (const b of buttons) {
      let id = '';
      try { id = (await b.getAttribute('id')) || ''; } catch (err) { id = ''; }
      if (COMMIT.test(id)) {
        try { await b.click({ timeout: 1200 }); } catch (err) { /* covered */ }
      }
    }

    await page.waitForTimeout(300);
    const after = await page.evaluate(SNAPSHOT);
    res.outcomesAfter = after.outcomes;
    res.readoutsAfter = after.readouts;
    res.frameTextLength = after.frameTextLength;
    res.frameControls = after.frameControls;
    res.committed = after.outcomes > 0;
    res.drags = activity.drags;
    res.taps = activity.taps;
    res.dragHandles = activity.dragHandles;
    res.tapHandles = activity.tapHandles;
    res.outcomesBeforeFirstCommit = outcomesBeforeFirstCommit;
    res.outcomePayloads = after.outcomePayloads.map((p) => ({
      correct: p && p.correct, tries: p && p.tries, has_detail: !!(p && p.detail),
    }));
    res.pageErrors = pageErrors;
    res.consoleErrors = consoleErrors;
    res.failedRequests = failedRequests;
    if (pageErrors.length) { res.ok = false; res.notes.push('uncaught exception in a real browser'); }
    if (failedRequests.length) { res.ok = false; res.notes.push('a request failed; pages must be self-contained'); }
  } catch (err) {
    res.ok = false;
    res.load_error = 'driver: ' + String((err && err.message) || err);
    res.pageErrors = pageErrors;
    res.consoleErrors = consoleErrors;
    res.failedRequests = failedRequests;
  } finally {
    await page.close().catch(() => {});
  }
  return res;
}

async function main() {
  if (!GAMES_DIR || !fs.existsSync(GAMES_DIR)) {
    console.error('usage: node playground_browser_check.mjs <games_dir> [out.json]');
    process.exit(2);
  }
  const slugs = fs.readdirSync(GAMES_DIR).filter((f) => f.endsWith('.html'))
    .map((f) => f.slice(0, -5)).sort();
  const { server, port } = await startServer();
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();
  const results = [];
  let failed = 0;
  try {
    for (const slug of slugs) {
      const res = await runOne(browser, base, slug);
      if (!res.ok) failed += 1;
      results.push(res);
      console.log(JSON.stringify(res));
    }
  } finally {
    await browser.close().catch(() => {});
    server.close();
  }
  const summary = {
    files: slugs.length,
    failed,
    committed: results.filter((r) => r.committed).length,
    threw: results.filter((r) => (r.pageErrors || []).length).length,
    requestFailures: results.filter((r) => (r.failedRequests || []).length).length,
    outcomeOnLoad: results.filter((r) => r.outcomesBefore > 0).length,
    readoutOnLoad: results.filter((r) => r.readoutsBefore > 0).length,
    emptyFrames: results.filter((r) => r.frameTextLength === 0).length,
    //: A page that posted an outcome while being explored. Judged only where the page's
    //: own `commits_on` says exploring must be silent: for `'check'` any outcome before
    //: Check is a contract violation, while for `'completion'` the finished board *is*
    //: the answer and posting is correct. Without `pages.json` this cannot be judged, and
    //: the raw count is reported instead of a verdict.
    prematureOutcome: results.filter((r) => r.commits_on === 'check'
      && (r.outcomesAfterExplore || 0) > 0).length,
    //: Pages where `commits_on` was not available, so the rule above could not be applied.
    commitsOnUnknown: results.filter((r) => !r.commits_on).length,
    undriven: results.filter((r) => !r.committed).length,
  };
  if (OUT_JSON) fs.writeFileSync(OUT_JSON, JSON.stringify(results, null, 2));
  console.log('SUMMARY ' + JSON.stringify(summary));
  process.exit(failed ? 1 : 0);
}

main();
