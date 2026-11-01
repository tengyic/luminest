// Screenshot rendered playground pages, so a layout change can be looked at rather
// than inferred from a number.
//
//   node scripts/playground_shots.mjs <html-dir> <out-dir> [slug-substring,...]
//
// The audit in playground_layout_audit.mjs measures four things well and cannot see
// the rest - whether a diagram reads, whether the composition is balanced, whether a
// control looks like a control. Those need eyes on the page, which is what this is for.

import { chromium } from 'playwright';
import { readdirSync, mkdirSync } from 'fs';
import path from 'path';

const [dir, out] = process.argv.slice(2);
if (!dir || !out) {
  console.error('usage: node playground_shots.mjs <html-dir> <out-dir> [slug-substring,...]');
  process.exit(2);
}
mkdirSync(out, { recursive: true });
const only = process.argv[4] ? process.argv[4].split(',') : null;

const files = readdirSync(dir).filter((f) => f.endsWith('.html')).sort()
  .filter((f) => !only || only.some((o) => f.includes(o)));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1100, height: 760 }, deviceScaleFactor: 2 });
let shot = 0;
for (const f of files) {
  await page.goto('file://' + path.resolve(dir, f));
  await page.waitForTimeout(260);
  await page.screenshot({ path: path.join(out, f.replace('.html', '.png')) });
  shot += 1;
}
await browser.close();
console.log(`shot ${shot} page(s) -> ${out}`);
