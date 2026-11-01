// Measure how well each playground page uses its canvas.
//
//   node scripts/playground_layout_audit.mjs <html-dir> [out.json] [--verbose]
//
// The design system (docs/playground-design.md, section 6) states four rules that can
// be measured from the rendered page rather than argued about:
//
//   L1 fill      the drawn content covers >= 55% of the declared viewBox
//   L1 overflow  no mark falls outside the viewBox
//   L2 dup       #instruction and #prompt do not say the same sentence
//   L3 collide   no two <text> nodes overlap, and no text crosses the canvas edge
//
// Everything is read from a real headless Chromium with the real CSS applied, because
// every one of these quantities depends on font metrics and layout. Reading the source
// would tell us what the author intended; this tells us what a learner sees.
//
// Exit code is 0 when every page is clean, 1 otherwise, so this can gate a build.

import { chromium } from 'playwright';
import { readdirSync, writeFileSync } from 'fs';
import path from 'path';

const FILL_FLOOR = 0.55;

const dir = process.argv[2];
if (!dir) {
  console.error('usage: node playground_layout_audit.mjs <html-dir> [out.json] [--verbose]');
  process.exit(2);
}
const outPath = process.argv[3] && !process.argv[3].startsWith('--') ? process.argv[3] : null;
const verbose = process.argv.includes('--verbose');

const PROBE = () => {
  // Constants live inside the probe: page.evaluate serialises this function, so a
  // closure variable would be `undefined` in the page context. (It was, the first time.)
  // Text glyph boxes are generous; a couple of pixels of kerning overlap is not a
  // collision, a label sitting on top of another label is.
  const COLLIDE_MIN_AREA = 24;
  const COLLIDE_MIN_SIDE = 3;

  const scene = document.querySelector('#scene') || document.querySelector('.stage svg') || document.querySelector('svg');
  if (!scene) return { error: 'no scene element' };

  const raw = (scene.getAttribute('viewBox') || '').trim().split(/[\s,]+/).map(Number);
  const vb = raw.length === 4 && raw.every(Number.isFinite) ? raw : [0, 0, 860, 460];
  const [vx, vy, vw, vh] = vb;

  // ---- union of everything actually painted (L1 fill) --------------------
  // Measuring every element in the scene is wrong twice over. Pages carry a
  // full-canvas transparent <rect> as a pointer target, which alone reports 100%
  // fill; and a draggable marker parked off-canvas at rest reports content where
  // the learner sees nothing. Both inflated the first version of this audit until
  // the emptiest page in the catalogue scored 119%. So: leaves only, painted only,
  // and anything outside the viewBox is reported separately rather than counted.
  const PAINTED = new Set(['rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'path', 'text', 'image', 'use']);
  const transparent = (v) => !v || v === 'none' || v === 'transparent' || /rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)/.test(v);
  const isPainted = (node, cs, tag) => {
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    if (tag === 'text' || tag === 'image' || tag === 'use') return true;
    const fillEmpty = transparent(cs.fill);
    const strokeEmpty = transparent(cs.stroke) || parseFloat(cs.strokeWidth) === 0;
    return !(fillEmpty && strokeEmpty);
  };

  // Measure each mark in *viewBox* coordinates, through its real transform chain.
  //
  // `getBBox()` returns the box in the element's own user space - it ignores the
  // element's own `transform` and every ancestor's. A board laid out as
  // `<g transform="translate(470,300)"><rect x=0 y=0 w=340 h=42>` therefore reports a
  // box at the origin, and the first version of this audit scored exactly that page at
  // 4% when it occupies half the canvas. Screen rects passed back through the scene's
  // inverse CTM are transform-aware and are what the learner actually sees.
  const sceneCTM = scene.getScreenCTM();
  const inv = sceneCTM ? sceneCTM.inverse() : null;
  const userRect = (node) => {
    if (!inv) return null;
    const r = node.getBoundingClientRect();
    if (!r || (r.width === 0 && r.height === 0)) return null;
    const corners = [[r.left, r.top], [r.right, r.top], [r.left, r.bottom], [r.right, r.bottom]]
      .map(([x, y]) => new DOMPoint(x, y).matrixTransform(inv));
    const xs = corners.map((p) => p.x), ys = corners.map((p) => p.y);
    const x = Math.min(...xs), y = Math.min(...ys);
    return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y };
  };

  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  let drawn = 0, invisible = 0;
  for (const node of scene.querySelectorAll('*')) {
    const tag = node.tagName.toLowerCase();
    if (!PAINTED.has(tag)) continue;
    if (node.getClientRects().length === 0) continue;
    let b;
    try { b = userRect(node); } catch { continue; }
    if (!b) continue;
    if (!isPainted(node, getComputedStyle(node), tag)) continue;
    drawn += 1;
    // Content wholly outside the viewBox is clipped away by the SVG viewport, so it
    // is not part of what the learner sees. Count it, but do not let it set the box.
    const outsideView = (b.x + b.width <= vx) || (b.y + b.height <= vy) ||
                        (b.x >= vx + vw) || (b.y >= vy + vh);
    if (outsideView) { invisible += 1; continue; }
    x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
    x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height);
  }
  const hasBox = Number.isFinite(x0) && x1 > x0;
  const box = hasBox ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : null;
  const fill = box ? (box.w * box.h) / (vw * vh) : 0;

  // Fill measured against the *rendered* scene rather than the declared viewBox.
  // `fill` alone can be satisfied by shrinking the canvas: declare 860x120 and a thin
  // number line suddenly "fills" its viewBox while still floating in the middle of a
  // 500px-tall card. This second number is what the learner's eye actually sees, so it
  // is the one that cannot be gamed by moving the goalposts.
  const sr0 = scene.getBoundingClientRect();
  const k0 = Math.min(sr0.width / vw, sr0.height / vh) || 1;
  const visualFill = box && sr0.width && sr0.height
    ? ((box.w * k0) * (box.h * k0)) / (sr0.width * sr0.height)
    : 0;

  // ---- invisible content (L1) ---------------------------------------------
  // The union is built only from content inside the viewBox, so there is no
  // "overflow" left to measure. What matters instead is *how much* is drawn where
  // the SVG viewport will clip it. A drag handle parked off-stage at rest is the
  // common case, and it is a genuine defect - the learner cannot see the thing they
  // are meant to grab, which is exactly how the number-line games shipped.

  // ---- text collisions (L3) ----------------------------------------------
  const texts = [];
  for (const node of scene.querySelectorAll('text')) {
    if (node.getClientRects().length === 0) continue;
    const s = (node.textContent || '').trim();
    if (!s) continue;
    const r = node.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    texts.push({ s, r });
  }
  const collisions = [];
  for (let i = 0; i < texts.length; i++) {
    for (let j = i + 1; j < texts.length; j++) {
      const a = texts[i].r, b = texts[j].r;
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ox > COLLIDE_MIN_SIDE && oy > COLLIDE_MIN_SIDE && ox * oy > COLLIDE_MIN_AREA) {
        collisions.push({ a: texts[i].s, b: texts[j].s, area: Math.round(ox * oy) });
      }
    }
  }
  // Text crossing the canvas edge. Convert the client rect back to user units using
  // the same uniform scale the renderer applies, then compare to the viewBox.
  const sr = scene.getBoundingClientRect();
  const k = Math.min(sr.width / vw, sr.height / vh) || 1;
  const ox2 = (sr.width - vw * k) / 2, oy2 = (sr.height - vh * k) / 2;
  const outside = [];
  for (const t of texts) {
    const tx0 = vx + (t.r.left - sr.left - ox2) / k;
    const tx1 = vx + (t.r.right - sr.left - ox2) / k;
    const ty0 = vy + (t.r.top - sr.top - oy2) / k;
    const ty1 = vy + (t.r.bottom - sr.top - oy2) / k;
    if (tx0 < vx - 2 || ty0 < vy - 2 || tx1 > vx + vw + 2 || ty1 > vy + vh + 2) {
      outside.push(t.s);
    }
  }

  // ---- duplicate instruction (L2) ----------------------------------------
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const instruction = norm((document.querySelector('#instruction') || {}).textContent);
  const prompts = ['#prompt', '#task', '#taskline', '#tasklabel']
    .map((sel) => document.querySelector(sel))
    .filter(Boolean)
    .map((n) => norm(n.textContent))
    .filter((s) => s.length > 0);
  let duplicate = null;
  for (const p of prompts) {
    if (!p || !instruction) continue;
    if (p === instruction) { duplicate = p; break; }
    if (p.length > 30 && instruction.length > 30 && (instruction.includes(p) || p.includes(instruction))) {
      duplicate = p; break;
    }
  }

  return {
    viewBox: vb, box, fill: +fill.toFixed(3), visualFill: +visualFill.toFixed(3),
    drawn, invisible,
    collisions: collisions.slice(0, 6), collisionCount: collisions.length,
    outside: outside.slice(0, 6),
    duplicate,
    textCount: texts.length,
  };
};

const files = readdirSync(dir).filter((f) => f.endsWith('.html')).sort();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1100, height: 820 } });
const results = [];

for (const f of files) {
  const slug = f.replace(/\.html$/, '');
  await page.goto('file://' + path.join(dir, f));
  await page.waitForTimeout(140);
  let probe;
  try {
    probe = await page.evaluate(PROBE);
  } catch (err) {
    probe = { error: String(err && err.message ? err.message : err) };
  }
  const problems = [];
  if (probe.error) problems.push(probe.error);
  else {
    if (probe.fill < FILL_FLOOR) problems.push('low fill');
    if (probe.invisible > 0) problems.push(`${probe.invisible} mark${probe.invisible > 1 ? 's' : ''} clipped off-canvas`);
    if (probe.collisionCount) problems.push(`${probe.collisionCount} text collision${probe.collisionCount > 1 ? 's' : ''}`);
    if (probe.outside && probe.outside.length) problems.push('text off-canvas');
    if (probe.duplicate) problems.push('duplicate instruction');
  }
  results.push({ slug, ...probe, problems });
}
await browser.close();

const bad = results.filter((r) => r.problems.length);
results.sort((a, b) => (a.fill || 0) - (b.fill || 0));

for (const r of results) {
  if (!verbose && !r.problems.length) continue;
  const flag = r.problems.length ? 'FAIL' : ' ok ';
  const seen = Math.round((r.visualFill ?? r.fill ?? 0) * 100);
  console.log(`${flag} ${r.slug.padEnd(46)} sees ${String(seen).padStart(3)}%  ${r.problems.join(', ')}`);
  if (verbose && r.collisions && r.collisions.length) {
    for (const c of r.collisions) console.log(`       collision: "${c.a}" x "${c.b}"`);
  }
}

console.log(`\n${files.length} pages | ${bad.length} with findings | ${files.length - bad.length} clean`);
if (bad.length) {
  const mean = (key) => results.reduce((s, r) => s + (r[key] || 0), 0) / results.length;
  console.log(`mean: ${(mean('visualFill') * 100).toFixed(0)}% of the visible card, ` +
              `${(mean('fill') * 100).toFixed(0)}% of the declared viewBox (floor ${FILL_FLOOR * 100}%)`);
}
if (outPath) writeFileSync(outPath, JSON.stringify(results, null, 2));
process.exit(bad.length ? 1 : 0);
