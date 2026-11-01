// Prove that the runtime's pointer -> viewBox mapping agrees with the browser's own
// SVG transform. `getScreenCTM()` is the ground truth: it maps user space to screen
// space including letterboxing, any transform on the scene, and the element's rect.
// The runtime's `point()` is its inverse, written by hand, and it was wrong for the
// whole first draft of the runtime - it assumed the viewBox filled the element, so
// every drag handle sat slightly away from the pointer on any page whose aspect ratio
// differed. This checks the inverse against the truth instead of against itself.
//
//   node scripts/playground_point_check.mjs <page.html> [page.html ...]

import { chromium } from 'playwright';
import path from 'path';

const files = process.argv.slice(2);
if (!files.length) {
  console.error('usage: node playground_point_check.mjs <page.html> ...');
  process.exit(2);
}

// Deliberately awkward viewports: neither matches the 860x460 canvas, so both force
// letterboxing in one direction or the other.
const VIEWPORTS = [
  { width: 1200, height: 700 },
  { width: 760, height: 900 },
  { width: 1100, height: 560 },
];

const browser = await chromium.launch();
let worst = 0;
let checked = 0;

for (const vp of VIEWPORTS) {
  const page = await browser.newPage({ viewport: vp });
  for (const f of files) {
    await page.goto('file://' + path.resolve(f));
    await page.waitForTimeout(160);
    const result = await page.evaluate(() => {
      const scene = document.querySelector('#scene') || document.querySelector('.stage svg') || document.querySelector('svg');
      if (!scene || typeof window.point !== 'function') return { error: 'no scene or no point()' };
      const ctm = scene.getScreenCTM();
      if (!ctm) return { error: 'no screen CTM' };
      const raw = (scene.getAttribute('viewBox') || '').trim().split(/[\s,]+/).map(Number);
      const vb = raw.length === 4 ? raw : [0, 0, 860, 460];
      // Sample the corners and centre of the viewBox: the corners are where a scale
      // error shows up largest, and the centre is where an origin offset hides.
      const pts = [
        [vb[0] + vb[2] * 0.5, vb[1] + vb[3] * 0.5],
        [vb[0] + vb[2] * 0.1, vb[1] + vb[3] * 0.1],
        [vb[0] + vb[2] * 0.9, vb[1] + vb[3] * 0.9],
        [vb[0] + vb[2] * 0.2, vb[1] + vb[3] * 0.8],
      ];
      const out = [];
      for (const [vx, vy] of pts) {
        const p = new DOMPoint(vx, vy).matrixTransform(ctm);   // truth: user -> screen
        const back = window.point({ clientX: p.x, clientY: p.y }, scene);  // runtime: screen -> user
        out.push({ vx, vy, sx: p.x, sy: p.y, bx: back.x, by: back.y,
                   dx: Math.abs(back.x - vx), dy: Math.abs(back.y - vy) });
      }
      return { points: out };
    });
    if (result.error) {
      console.log(`ERR  ${path.basename(f)} @${vp.width}x${vp.height}: ${result.error}`);
      continue;
    }
    const err = Math.max(...result.points.map((p) => Math.max(p.dx, p.dy)));
    worst = Math.max(worst, err);
    checked += 1;
    const tag = err < 1.0 ? ' ok ' : 'FAIL';
    console.log(`${tag} ${path.basename(f).padEnd(38)} @${String(vp.width).padStart(4)}x${vp.height}  max error ${err.toFixed(2)} px(user)`);
  }
  await page.close();
}
await browser.close();
console.log(`\n${checked} page/viewport combinations | worst round-trip error ${worst.toFixed(2)} user units`);
process.exit(worst < 1.0 ? 0 : 1);
