/* Renderer adapters for the eight Luminest whiteboard visual types.
 *
 * Each adapter receives a *validated* spec, a host element, and a config object, and
 * returns { dispose }. It never reads the network except the one explicitly external
 * provider (desmos), and it never executes spec strings as code: expressions go through
 * safeexpr.js, which compiles a tiny closed grammar into an AST.
 *
 * Error codes are part of the native contract. A renderer that cannot run must throw a
 * VisualError with a precise code; it must NEVER fall back to drawing something else and
 * report success. That is the whole point of the BLOCKED / external provider states.
 */
import * as React from 'react';
import { createRoot } from 'react-dom/client';
import { Mafs, Coordinates, Plot, Point, Polyline, Line, Vector, Text, Polygon } from 'mafs';
import { mathBox } from 'mathbox';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import katex from 'katex';
import { compileExpression, sample } from './safeexpr.js';

export class VisualError extends Error {
  constructor(code, detail = '') {
    super(detail || code);
    this.name = 'VisualError';
    this.code = code;
    this.detail = detail;
  }
}

const HEX = /^#[0-9a-fA-F]{6}$/;
const colour = (v, fallback) => (HEX.test(v || '') ? v : fallback);

function compiled(expr, vars, label) {
  if (!expr) return null;
  const c = compileExpression(String(expr), vars);
  if (!c.ok) throw new VisualError('INVALID_EXPRESSION', `${label}: ${c.error}`);
  return c;
}

function viewportOf(spec) {
  const v = spec.viewport || {};
  return {
    x: Array.isArray(v.x) && v.x.length === 2 ? v.x : [-10, 10],
    y: Array.isArray(v.y) && v.y.length === 2 ? v.y : [-6, 6],
  };
}

function emptyHost(host) {
  while (host.firstChild) host.removeChild(host.firstChild);
}

/* ------------------------------------------------------------------ 1. Mafs */
function renderMafs(spec, host) {
  const vp = viewportOf(spec);
  const children = [React.createElement(Coordinates.Cartesian, { key: 'axes' })];

  (spec.curves || []).forEach((curve, i) => {
    const c = colour(curve.color, '#3b6fd4');
    if (curve.expr) {
      const fn = compiled(curve.expr, ['x'], `curves[${i}].expr`);
      const domain = Array.isArray(curve.domain) && curve.domain.length === 2
        ? curve.domain : [vp.x[0], vp.x[1]];
      children.push(React.createElement(Plot.OfX, {
        key: `c${i}`, y: (x) => fn.evaluate({ x }), domain, color: c, weight: 2,
      }));
    } else if (Array.isArray(curve.points) && curve.points.length > 1) {
      children.push(React.createElement(Polyline, {
        key: `p${i}`, points: curve.points.map((p) => [Number(p[0]), Number(p[1])]), color: c,
      }));
    }
  });

  (spec.points || []).forEach((p, i) => {
    children.push(React.createElement(Point, {
      key: `pt${i}`, x: Number(p.x), y: Number(p.y), color: colour(p.color, '#c0392b'),
    }));
    if (p.label) {
      children.push(React.createElement(Text, {
        key: `lbl${i}`, x: Number(p.x), y: Number(p.y), attach: 'ne',
        children: String(p.label),
      }));
    }
  });

  (spec.segments || []).forEach((s, i) => {
    if (!s.from || !s.to) return;
    children.push(React.createElement(Line.Segment, {
      key: `seg${i}`,
      point1: [Number(s.from[0]), Number(s.from[1])],
      point2: [Number(s.to[0]), Number(s.to[1])],
      color: colour(s.color, '#333333'),
    }));
  });

  (spec.vectors || []).forEach((v, i) => {
    children.push(React.createElement(Vector, {
      key: `vec${i}`,
      tail: [Number(v.from[0]), Number(v.from[1])],
      tip: [Number(v.to[0]), Number(v.to[1])],
      color: colour(v.color, '#27865b'),
    }));
  });

  const root = createRoot(host);
  root.render(React.createElement(Mafs, {
    viewBox: { x: vp.x, y: vp.y, padding: 0.4 },
    pan: true,
    zoom: { min: 0.2, max: 12 },
    preserveAspectRatio: false,
  }, children));
  return { dispose: () => root.unmount() };
}

/* ---------------------------------------------------------------- 2. Plotly */
function renderPlotly(spec, host) {
  const Plotly = window.Plotly;
  if (!Plotly || typeof Plotly.newPlot !== 'function') {
    throw new VisualError('RENDERER_ASSETS_NOT_INSTALLED', 'Plotly bundle is missing');
  }
  const traces = (spec.traces || []).map((t) => {
    const out = { type: t.type, x: t.x || [], y: t.y || [], name: t.name || '' };
    if (t.z) out.z = t.z;
    if (t.mode) out.mode = t.mode;
    if (t.type === 'surface' && Array.isArray(t.z)) out.z = t.z;
    return out;
  });
  const l = spec.layout || {};
  const layout = {
    autosize: true,
    margin: { l: 44, r: 16, t: l.title ? 38 : 12, b: 40 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: '-apple-system, sans-serif', size: 11 },
    showlegend: traces.length > 1,
    title: l.title ? { text: l.title, font: { size: 13 } } : undefined,
    xaxis: { title: l.xTitle || '' },
    yaxis: { title: l.yTitle || '' },
  };
  return Plotly.newPlot(host, traces, layout, {
    responsive: true, displayModeBar: false, displaylogo: false,
  }).then(() => ({ dispose: () => Plotly.purge(host) }));
}

/* -------------------------------------------------------------- 3. JSXGraph */
function renderJSXGraph(spec, host) {
  const JXG = window.JXG;
  if (!JXG || !JXG.JSXGraph) {
    throw new VisualError('RENDERER_ASSETS_NOT_INSTALLED', 'JSXGraph bundle is missing');
  }
  host.id = host.id || `jsxgraph-${Math.random().toString(36).slice(2)}`;
  const bb = (spec.viewport && spec.viewport.boundingbox) || [-10, 10, 10, -10];
  const board = JXG.JSXGraph.initBoard(host.id, {
    boundingbox: bb, axis: true, showCopyright: false, showNavigation: false,
    keepaspectratio: false,
  });
  (spec.functions || []).forEach((f, i) => {
    const fn = compiled(f.expr, ['x'], `functions[${i}].expr`);
    const domain = Array.isArray(f.domain) && f.domain.length === 2 ? f.domain : [bb[0], bb[2]];
    board.create('functiongraph', [(x) => fn.evaluate({ x }), domain[0], domain[1]], {
      strokeColor: colour(f.color, '#3b6fd4'), strokeWidth: 2,
    });
  });
  (spec.points || []).forEach((p) => {
    board.create('point', [Number(p.x), Number(p.y)], {
      name: p.label || '', size: 3, color: colour(p.color, '#c0392b'),
    });
  });
  (spec.segments || []).forEach((s) => {
    if (!s.from || !s.to) return;
    board.create('segment', [
      [Number(s.from[0]), Number(s.from[1])],
      [Number(s.to[0]), Number(s.to[1])],
    ], { strokeColor: colour(s.color, '#333333'), strokeWidth: 2 });
  });
  (spec.polygons || []).forEach((p) => {
    if (!Array.isArray(p.vertices) || p.vertices.length < 3) return;
    board.create('polygon', p.vertices.map((v) => [Number(v[0]), Number(v[1])]), {
      fillColor: colour(p.color, '#3b6fd4'), fillOpacity: 0.15,
      borders: { strokeColor: colour(p.color, '#3b6fd4') },
    });
  });
  return { dispose: () => { try { JXG.JSXGraph.freeBoard(board); } catch (_) { /* already gone */ } } };
}

/* --------------------------------------------------------------- 4. MathBox */
function renderMathBox(spec, host) {
  if (typeof mathBox !== 'function') {
    throw new VisualError('RENDERER_ASSETS_NOT_INSTALLED', 'MathBox bundle is missing');
  }
  const range = (spec.range && spec.range.length === 3) ? spec.range : [[-5, 5], [-5, 5], [-5, 5]];
  let root;
  try {
    // MathBox 2 installs its own "mathbox" + "splash" threestrap plugins inside
    // mathBox(). The `plugins: ['dataviz', ...]` option belongs to MathBox 1 and makes
    // Bootstrap.install fail with "'dataviz' is not registered".
    root = mathBox({
      element: host,
      controls: { klass: OrbitControls },
      camera: { fov: 45, position: [4, 3, 6] },
    });
  } catch (e) {
    throw new VisualError('RENDER_FAILED', `MathBox init: ${e && e.message ? e.message : e}`);
  }
  if (!root || !root.three) throw new VisualError('RENDER_FAILED', 'MathBox returned no WebGL context');

  const three = root.three;
  three.renderer.setClearColor(new THREE.Color(0xffffff), 1);
  const view = root.cartesian({ range, scale: [1, 1, 1] });
  view.axis({ axis: 1, color: 0x888888, width: 2 });
  view.axis({ axis: 2, color: 0x888888, width: 2 });
  view.axis({ axis: 3, color: 0x888888, width: 2 });
  view.grid({ axes: [1, 3], color: 0xdddddd, width: 1 });

  (spec.surfaces || []).forEach((s, i) => {
    const fn = compiled(s.expr, ['x', 'y'], `surfaces[${i}].expr`);
    const xr = (s.xRange && s.xRange.length === 2) ? s.xRange : range[0];
    const yr = (s.yRange && s.yRange.length === 2) ? s.yRange : range[2];
    const n = Math.max(4, Math.min(64, Number(s.grid) || 32));
    const colorHex = colour(s.color, '#3b6fd4');
    view.area({
      width: n, height: n, channels: 3,
      expr: (emit, u, v) => {
        const x = xr[0] + (xr[1] - xr[0]) * u;
        const y = yr[0] + (yr[1] - yr[0]) * v;
        let z = fn.evaluate({ x, y });
        if (!Number.isFinite(z)) z = 0;
        emit(x, z, y);
      },
    }).surface({ shaded: true, color: new THREE.Color(colorHex).getHex(), lineX: false, lineY: false });
  });

  (spec.curves3d || []).forEach((c, i) => {
    const fn = compiled(c.expr, ['t'], `curves3d[${i}].expr`);
    const tr = (c.tRange && c.tRange.length === 2) ? c.tRange : [-3, 3];
    const pts = sample(fn, tr[0], tr[1], 160, 't')
      .filter((p) => p[1] !== null)
      .map((p) => [p[0], p[1], 0]);
    if (pts.length < 2) return;
    view.array({ data: pts, channels: 3, items: pts.length })
      .line({ color: new THREE.Color(colour(c.color, '#c0392b')).getHex(), width: 3 });
  });

  return {
    dispose: () => {
      try { root.destroy ? root.destroy() : three.destroy(); } catch (_) { /* best effort */ }
      emptyHost(host);
    },
  };
}

/* --------------------------------------------------- 5. Molecular (3Dmol.js) */
function renderMolecule(spec, host) {
  const mol = window.$3Dmol;
  if (!mol || typeof mol.createViewer !== 'function') {
    throw new VisualError('RENDERER_ASSETS_NOT_INSTALLED', '3Dmol bundle is missing');
  }
  const viewer = mol.createViewer(host, { backgroundColor: 'white' });
  if (!viewer) throw new VisualError('RENDER_FAILED', '3Dmol could not create a viewer');
  viewer.addModel(String(spec.data || ''), String(spec.format || 'pdb'));
  const style = ['stick', 'sphere', 'cartoon', 'line', 'cross'].includes(spec.style) ? spec.style : 'stick';
  viewer.setStyle({}, { [style]: {} });
  viewer.zoomTo();
  viewer.render();
  if (spec.spin) viewer.spin(true);
  return { dispose: () => { try { viewer.clear(); } catch (_) { /* best effort */ } emptyHost(host); } };
}

/* ------------------------------------------ 6. Desmos (external provider) */
function loadDesmos(apiKey) {
  if (window.Desmos && window.Desmos.Calculator) return Promise.resolve(window.Desmos);
  if (!apiKey) {
    return Promise.reject(new VisualError(
      'EXTERNAL_PROVIDER_UNAVAILABLE',
      'Desmos requires an API key: set LUMINEST_DESMOS_API_KEY / pass desmosApiKey to renderFromNative()',
    ));
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `https://www.desmos.com/api/v1.11/calculator.js?apiKey=${encodeURIComponent(apiKey)}`;
    script.onload = () => (window.Desmos && window.Desmos.Calculator)
      ? resolve(window.Desmos)
      : reject(new VisualError('EXTERNAL_PROVIDER_UNAVAILABLE', 'Desmos loader did not register a Calculator'));
    script.onerror = () => reject(new VisualError(
      'EXTERNAL_PROVIDER_UNAVAILABLE', 'Desmos loader could not be reached (offline or blocked)',
    ));
    document.head.appendChild(script);
  });
}

async function renderDesmos(spec, host, config) {
  const Desmos = await loadDesmos(config.desmosApiKey || '');
  const calculator = Desmos.Calculator(host, {
    expressions: false, settingsMenu: false, zoomButtons: true,
    showGrid: true, expressionsCollapsed: true,
  });
  (spec.expressions || []).forEach((e, i) => {
    const state = { id: `expr-${i}`, latex: String(e.latex || '') };
    if (e.color) state.color = colour(e.color, '#3b6fd4');
    calculator.setExpression(state);
  });
  const vp = spec.viewport || {};
  if (vp.bounds) {
    calculator.setMathBounds({
      left: vp.bounds.left, right: vp.bounds.right,
      bottom: vp.bounds.bottom, top: vp.bounds.top,
    });
  }
  return { dispose: () => { try { calculator.destroy(); } catch (_) { /* best effort */ } emptyHost(host); } };
}

/* ------------------------------------- 7. TikZ (vendored TeX-in-WASM bundle) */
function renderTikZ(spec, host, config) {
  if (!config.tikzAssets) {
    throw new VisualError(
      'RENDERER_ASSETS_NOT_INSTALLED',
      'TikZ TeX-WASM assets are not installed in this build',
    );
  }
  return new Promise((resolve, reject) => {
    const frame = document.createElement('iframe');
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
    frame.style.cssText = 'width:100%;height:100%;border:0;background:white';
    const source = String(spec.source || '').replace(/<\/script/gi, '<\\/script');
    const base = document.baseURI;
    // TikZJax scans <script type="text/tikz"> on window.onload and replaces each with an SVG.
    // A dedicated srcdoc frame gives each render its own load event without patching the
    // vendor bundle or touching the host document's lifecycle.
    frame.srcdoc = `<!doctype html><html><head><base href="${base}">`
      + '<link rel="stylesheet" href="vendor/tikzjax/fonts.css">'
      + '<script src="vendor/tikzjax/tikzjax.js"></script>'
      + '</head><body style="margin:0">'
      + `<script type="text/tikz">${source}<\/script>`
      + '</body></html>';
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new VisualError('RENDER_FAILED', 'TikZ compilation timed out'));
    }, 30000);
    frame.onload = () => {
      const poll = () => {
        if (settled) return;
        let svg = null;
        try { svg = frame.contentDocument && frame.contentDocument.querySelector('svg'); } catch (_) { /* cross-origin guard */ }
        if (svg) {
          settled = true;
          clearTimeout(timer);
          resolve({ dispose: () => { frame.remove(); } });
        } else {
          const elapsed = Date.now() - started;
          if (elapsed > 30000) {
            settled = true;
            clearTimeout(timer);
            reject(new VisualError('RENDER_FAILED', 'TikZ produced no SVG'));
          } else { setTimeout(poll, 120); }
        }
      };
      const started = Date.now();
      poll();
    };
    host.appendChild(frame);
  });
}

/* ------------------------------------------------------------------ 8. TeX */
// A `tex` spec is `{latex, display}` — one formula, no figure. It exists because the
// board mounts a problem's equation as a first-class node, and routing that through
// Mafs or TikZ would mean shipping a plot or a WASM compile to draw a single line of
// maths. KaTeX is vendored (JS into this bundle, CSS + 60 woff2 into vendor/katex/),
// so this adapter needs no network and no runtime prerequisite.
//
// `throwOnError` is deliberately true. With it false KaTeX renders the source in red
// and returns normally, which would make this adapter report `rendered` for a formula
// that is not typeset — the exact failure mode the rest of this file exists to prevent.
// `trust: false` refuses \href, \url, \htmlClass and \includegraphics, so a spec cannot
// turn a formula into a link or an asset fetch.
function renderTex(spec, host) {
  const latex = typeof spec.latex === 'string' ? spec.latex.trim() : '';
  if (!latex) throw new VisualError('INVALID_SPEC', 'tex: latex is empty');
  const block = document.createElement('div');
  block.className = 'luminest-tex';
  block.setAttribute('data-latex', latex);
  host.appendChild(block);
  try {
    katex.render(latex, block, {
      displayMode: spec.display !== false,
      throwOnError: true,
      trust: false,
      strict: 'ignore',
      maxSize: 30,
      maxExpand: 1000,
      output: 'html',
    });
  } catch (e) {
    if (block.parentNode) block.parentNode.removeChild(block);
    throw new VisualError('INVALID_EXPRESSION', `tex: ${e && e.message ? e.message : String(e)}`);
  }
  return { dispose: () => { if (block.parentNode) block.parentNode.removeChild(block); } };
}

const ADAPTERS = Object.freeze({
  mafs: renderMafs,
  plotly: renderPlotly,
  jsxgraph: renderJSXGraph,
  mathbox: renderMathBox,
  molecule: renderMolecule,
  desmos: renderDesmos,
  tikz: renderTikZ,
  tex: renderTex,
});

export const RENDERER_TYPES = Object.keys(ADAPTERS);

export async function renderVisual(type, spec, host, config) {
  const adapter = ADAPTERS[type];
  if (!adapter) throw new VisualError('UNSUPPORTED_TYPE', String(type));
  emptyHost(host);
  try {
    return await adapter(spec || {}, host, config || {});
  } catch (e) {
    if (e instanceof VisualError) throw e;
    throw new VisualError('RENDER_FAILED', e && e.message ? e.message : String(e));
  }
}
