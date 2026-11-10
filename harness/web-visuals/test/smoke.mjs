/* Headless-browser acceptance smoke test for the visual host bundle.
 * Runs the REAL index.html (with the same CSP) in Chrome, drives the eight renderers
 * through the native bridge, and reports per-type outcome. Not shipped in the app.
 */
import puppeteer from 'puppeteer-core';
import { createServer } from 'node:http';
import { readFileSync, statSync } from 'node:fs';
import { join, extname, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

// fileURLToPath, not URL.pathname: the repo path contains a space and .pathname
// percent-encodes it, which makes every static request a 404.
const ROOT = fileURLToPath(new URL('../out/', import.meta.url));
const TEST_ROOT = fileURLToPath(new URL('./', import.meta.url));
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.wasm': 'application/wasm',
  '.gz': 'application/gzip', '.ttf': 'font/ttf', '.woff2': 'font/woff2',
};

// Test the REAL host page with the REAL CSP: only inject the dev harness script tag.
const HOST_HTML = readFileSync(join(ROOT, 'index.html'), 'utf8').replace(
  '<script src="visuals.bundle.js"></script>',
  '<script src="visuals.bundle.js"></script>\n<script src="/selftest.js" defer></script>',
);

const server = createServer((req, res) => {
  const rel = normalize(decodeURIComponent(req.url.split('?')[0])).replace(/^(\.\.[/\\])+/, '');
  if (rel === '/' || rel === '/selftest.html') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(HOST_HTML);
    return;
  }
  if (rel === '/selftest.js') {
    res.writeHead(200, { 'Content-Type': 'text/javascript' });
    res.end(readFileSync(join(TEST_ROOT, 'selftest.js')));
    return;
  }
  // Chrome asks for /favicon.ico on every page load. Serving an empty 204 keeps the
  // console clean so a future real 404 (a lost font/WASM/vendor file) is not buried.
  if (rel === '/favicon.ico') { res.writeHead(204).end(); return; }
  const path = join(ROOT, rel);
  if (!path.startsWith(ROOT)) { res.writeHead(403).end(); return; }
  try {
    if (!statSync(path).isFile()) throw new Error('not a file');
    const body = readFileSync(path);
    res.writeHead(200, { 'Content-Type': MIME[extname(path)] || 'application/octet-stream' });
    res.end(body);
  } catch (_) { res.writeHead(404).end('not found'); }
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port;
const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: [
    '--no-sandbox', '--disable-dev-shm-usage',
    '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader',
    '--allow-file-access-from-files',
  ],
});
const page = await browser.newPage();
await page.setViewport({ width: 640, height: 420 });
const consoleErrors = [];
const notFound = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 240)); });
page.on('pageerror', (e) => consoleErrors.push('PAGEERROR ' + String(e.message).slice(0, 240)));
// A bare "404 (Not Found)" console line hides which asset went missing. Name it, so a
// renderer that silently lost a font or WASM cannot hide behind a passing status table.
page.on('response', (r) => { if (r.status() === 404) notFound.push(r.url()); });

let results = null;
let timedOut = false;
try {
  await page.goto(`http://127.0.0.1:${port}/selftest.html`, { waitUntil: 'load', timeout: 60000 });
  await page.waitForFunction(
    () => document.title === 'SELFTEST_DONE' || !!document.body.dataset.results,
    { timeout: 120000 },
  );
  results = JSON.parse(await page.evaluate(() => document.body.dataset.results));
} catch (e) {
  timedOut = true;
  console.error('WAIT FAILED:', e.message);
}
console.log('=== RENDERER RESULTS ===');
// Desmos is an explicitly external provider. With no API key, the *correct* outcome is
// a stable refusal code, not a drawing. Assert that code instead of calling it a bug.
const EXPECTED_REFUSAL = { desmos: 'EXTERNAL_PROVIDER_UNAVAILABLE' };
let failures = 0;
for (const r of results || []) {
  const expected = EXPECTED_REFUSAL[r.type];
  let pass = r.ok || (expected && r.code === expected);
  // `ok` is not enough for tex: it is only typeset if katex.min.css and the woff2 fonts
  // landed in the bundle. A missing stylesheet still renders, at the wrong size and in a
  // fallback font, and would otherwise be reported as a success.
  if (pass && r.type === 'tex') {
    const d = r.dom || {};
    if (!d.katex || !/KaTeX/i.test(d.fontFamily || '') || !(d.width > 0)) {
      pass = false;
      r.detail = `DOM check failed: ${JSON.stringify(d)}`;
    }
  }
  if (!pass) failures += 1;
  const status = pass ? 'PASS' : 'FAIL';
  const note = (!r.ok && expected) ? ' [expected refusal: no API key]' : '';
  console.log(`${status.padEnd(5)} ${r.type.padEnd(10)} ${r.code}${r.detail ? ' :: ' + r.detail : ''}${note}`);
}
console.log('\n=== 404 RESPONSES ===');
for (const url of notFound.slice(0, 20)) console.log(' ', url);
// A missing asset is a failure, not a note. A lost font or WASM does not raise: the
// renderer draws with a fallback and the table above still says PASS, which is exactly
// how a visibly broken visual ships with a green smoke test.
const missing = notFound.length;
console.log('\n=== CONSOLE ERRORS (first 12) ===');
for (const e of consoleErrors.slice(0, 12)) console.log(' ', e);
console.log(`\ntimedOut=${timedOut} results=${results ? results.length : 0} failures=${failures} missing_assets=${missing}`);
await browser.close();
server.close();
if (timedOut || !results || failures || missing) process.exit(1);
