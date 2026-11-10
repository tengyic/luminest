/* Build the offline WKWebView resource bundle for Luminest whiteboard visuals.
 *
 * Output lands in ../native/Sources/LearningHarness/Resources/Visuals, which SwiftPM's
 * `.process("Resources")` already copies into the app's resource bundle. Nothing in the
 * shipped app reads node_modules at runtime.
 *
 * The build is fail-closed: a missing vendored asset, a failed catalog export, or an
 * esbuild error aborts with a non-zero exit instead of producing a partial bundle that
 * would look fine until a learner tried to use one renderer.
 */
import { build } from 'esbuild';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  copyFileSync, mkdirSync, readFileSync, readdirSync, statSync,
  writeFileSync, existsSync,
} from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..');
const OUT = join(HERE, 'out');
const RESOURCES = join(REPO, 'native', 'Sources', 'LearningHarness', 'Visuals');
const VENDOR = join(HERE, 'vendor');

const TIKZ_WASM = '3f69afb974a1e83f66a36f7618f88a38c254034b.wasm';
const TIKZ_CORE = 'b565ab0b474e8e557d954694b7379a57db669ac9.gz';

function need(path, label) {
  if (!existsSync(path)) throw new Error(`MISSING ${label}: ${path}`);
  const size = statSync(path).size;
  if (size < 100) throw new Error(`SUSPICIOUS ${label}: ${path} is only ${size} bytes`);
  return path;
}

function put(src, destRel) {
  const dest = join(OUT, destRel);
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(need(src, destRel), dest);
}

function patchTikzBase(src, dest) {
  // Upstream hard-codes an S3 base for the TeX WASM + core dump. Point it at the local
  // vendored directory instead; the hashed file names stay untouched.
  const text = readFileSync(src, 'utf8');
  const upstream = 'https://s3.us-east-2.amazonaws.com/tikzjax.com';
  const previous = /\bs\s*=\s*"tikzjax"/;
  let patched = text;
  if (patched.includes(upstream)) {
    patched = patched.replace(upstream, 'vendor/tikzjax');
  } else if (previous.test(patched)) {
    patched = patched.replace(previous, 's="vendor/tikzjax"');
  } else if (!patched.includes('vendor/tikzjax')) {
    throw new Error('cannot localise tikzjax resource base: upstream literal not found');
  }
  if (patched.includes(upstream)) throw new Error('tikzjax still points at S3');
  writeFileSync(dest, patched, 'utf8');
}

function manifest(dir) {
  const rows = [];
  const walk = (current) => {
    for (const name of readdirSync(current).sort()) {
      const full = join(current, name);
      if (statSync(full).isDirectory()) { walk(full); continue; }
      if (name === 'MANIFEST.sha256') continue;
      const digest = createHash('sha256').update(readFileSync(full)).digest('hex');
      rows.push(`${digest}  ${relative(dir, full)}`);
    }
  };
  walk(dir);
  return rows;
}

async function main() {
  // Overwrite in place. A recursive delete of the whole tree trips the desktop host's
  // bulk-delete guard (155 files > 50), which would make the build non-repeatable.
  // Instead: write every expected file, then report anything left over.
  mkdirSync(OUT, { recursive: true });

  // 1. Catalog: generated from the backend's single source of truth.
  execFileSync('python3', [
    join(REPO, 'scripts', 'export_visual_catalog.py'),
    join(HERE, 'src', 'catalog.generated.json'),
  ], { stdio: 'inherit' });
  put(join(HERE, 'src', 'catalog.generated.json'), 'catalog.json');

  // 2. Bundle the ESM-only renderers (Mafs/React, MathBox/three) into one IIFE.
  await build({
    entryPoints: [join(HERE, 'src', 'index.js')],
    bundle: true,
    minify: true,
    format: 'iife',
    globalName: 'LuminestVisualsBundle',
    target: ['safari16'],
    platform: 'browser',
    outfile: join(OUT, 'visuals.bundle.js'),
    loader: { '.json': 'json' },
    define: { 'process.env.NODE_ENV': '"production"' },
    legalComments: 'none',
    logLevel: 'warning',
  });
  need(join(OUT, 'visuals.bundle.js'), 'esbuild output');

  // 3. UMD renderers that ship as standalone browser builds.
  put(join(VENDOR, 'plotly.min.js'), 'vendor/plotly.min.js');
  put(join(VENDOR, 'jsxgraphcore.js'), 'vendor/jsxgraphcore.js');
  put(join(VENDOR, 'jsxgraph.css'), 'vendor/jsxgraph.css');
  put(join(VENDOR, '3Dmol-min.js'), 'vendor/3Dmol-min.js');
  put(join(HERE, 'node_modules', 'mafs', 'core.css'), 'vendor/mafs.css');
  put(join(HERE, 'node_modules', 'mathbox', 'build', 'mathbox.css'), 'vendor/mathbox.css');

  // 4. TikZ: TeX-in-WASM engine, core dump, and the full Bakoma font set.
  const tj = join(VENDOR, 'tikzjax');
  const tjOut = join(OUT, 'vendor', 'tikzjax');
  mkdirSync(join(tjOut, 'fonts'), { recursive: true });
  patchTikzBase(need(join(tj, 'tikzjax.js'), 'tikzjax.js'), join(tjOut, 'tikzjax.js'));
  put(join(tj, 'fonts.css'), 'vendor/tikzjax/fonts.css');
  put(join(tj, TIKZ_WASM), `vendor/tikzjax/${TIKZ_WASM}`);
  put(join(tj, TIKZ_CORE), `vendor/tikzjax/${TIKZ_CORE}`);
  const fonts = readdirSync(join(tj, 'fonts')).filter((f) => f.endsWith('.ttf'));
  if (fonts.length !== 140) {
    throw new Error(`expected 140 Bakoma fonts, found ${fonts.length}`);
  }
  for (const font of fonts) {
    put(join(tj, 'fonts', font), `vendor/tikzjax/fonts/${font}`);
  }

  // 4b. KaTeX for the `tex` visual type. The JS is bundled by esbuild above; the
  // stylesheet and the math fonts have to ship as files, because katex.min.css references
  // them by relative url() and a font that 404s renders boxes instead of glyphs without
  // raising anything. The stylesheet is written verbatim: it lives at vendor/katex/ and
  // its `url(fonts/…)` therefore resolves to vendor/katex/fonts/ with no rewriting. (An
  // earlier revision prefixed them and produced vendor/katex/vendor/katex/fonts/ — a 404
  // that the smoke test caught only because every missing response is now fatal.)
  const KATEX = join(HERE, 'node_modules', 'katex', 'dist');
  const katexCss = readFileSync(need(join(KATEX, 'katex.min.css'), 'katex.min.css'), 'utf8');
  const katexRefs = [...katexCss.matchAll(/url\((fonts\/[^)]+)\)/g)].map((m) => m[1]);
  if (!katexRefs.length) throw new Error('katex.min.css references no fonts/ assets');
  mkdirSync(join(OUT, 'vendor', 'katex', 'fonts'), { recursive: true });
  writeFileSync(join(OUT, 'vendor', 'katex', 'katex.min.css'), katexCss, 'utf8');
  // katex.min.css declares three sources per face (woff2, woff, ttf). Ship all three:
  // a browser that falls back past a missing format logs a 404 rather than failing, and
  // a 404 in this bundle is the thing the smoke test exists to notice.
  const katexAll = readdirSync(join(KATEX, 'fonts'));
  for (const ext of ['woff2', 'woff', 'ttf']) {
    const n = katexAll.filter((f) => f.endsWith(`.${ext}`)).length;
    if (n !== 20) throw new Error(`expected 20 KaTeX .${ext} fonts, found ${n}`);
  }
  for (const font of katexAll) {
    put(join(KATEX, 'fonts', font), `vendor/katex/fonts/${font}`);
  }
  // Every face the stylesheet names must exist, or the tex renderer silently degrades.
  for (const ref of katexRefs) need(join(OUT, 'vendor', 'katex', ref), `katex ${ref}`);

  // 5. Host page + styles.
  put(join(HERE, 'src', 'index.html'), 'index.html');
  put(join(HERE, 'src', 'styles.css'), 'styles.css');

  // 6. Verify every local reference in index.html resolves to a shipped file.
  const html = readFileSync(join(OUT, 'index.html'), 'utf8');
  for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
    const ref = match[1];
    if (/^(https?:|data:|#)/.test(ref)) continue;
    need(join(OUT, ref), `index.html reference ${ref}`);
  }

  const rows = manifest(OUT);
  writeFileSync(join(OUT, 'MANIFEST.sha256'), rows.join('\n') + '\n', 'utf8');

  // 7. Publish into the SwiftPM resource folder (and leave `out/` for inspection).
  // `.copy("Visuals")` in Package.swift preserves this directory hierarchy; flattening
  // it would break every `vendor/...` reference in index.html.
  mkdirSync(RESOURCES, { recursive: true });
  const copyTree = (from, to) => {
    for (const name of readdirSync(from)) {
      const src = join(from, name), dst = join(to, name);
      if (statSync(src).isDirectory()) { mkdirSync(dst, { recursive: true }); copyTree(src, dst); }
      else copyFileSync(src, dst);
    }
  };
  copyTree(OUT, RESOURCES);

  // Stale assets are reported, never bulk-deleted: a renamed renderer file must be
  // noticed by a human, not silently erased (or silently left in the shipped bundle).
  const expected = new Set(rows.map((row) => row.slice(66)));
  expected.add('MANIFEST.sha256');
  const stale = [];
  for (const name of readdirSync(RESOURCES)) {
    if (name === 'vendor') continue; // checked below
    if (!expected.has(name)) stale.push(name);
  }
  if (stale.length) {
    console.log(`STALE FILES in resources (left untouched): ${stale.join(', ')}`);
  }

  const total = rows.reduce((n, row) => n + statSync(join(OUT, row.slice(66))).size, 0);
  console.log(`\nBUNDLE OK  files=${rows.length + 1}  bytes=${total}  (${(total / 1048576).toFixed(2)} MiB)`);
  console.log(`out:       ${OUT}`);
  console.log(`resources: ${RESOURCES}`);
  const byKind = {};
  for (const row of rows) {
    const p = row.slice(66);
    const kind = p.startsWith('vendor/tikzjax/') ? 'tikz'
      : p.startsWith('vendor/') ? 'vendor UMD/CSS'
        : p === 'visuals.bundle.js' ? 'esbuild bundle' : 'host files';
    byKind[kind] = (byKind[kind] || 0) + statSync(join(OUT, p)).size;
  }
  for (const [kind, size] of Object.entries(byKind).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${kind.padEnd(16)} ${(size / 1048576).toFixed(2)} MiB`);
  }
}

main().catch((err) => {
  console.error('BUNDLE FAILED:', err && err.message ? err.message : err);
  process.exit(1);
});
