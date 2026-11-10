/* Native <-> Web bridge for the Luminest whiteboard visual host.
 *
 * Swift drives this page with `evaluateJavaScript`:
 *   LuminestVisuals.renderFromNative({ type, spec, config, requestId })
 * and receives events through `window.webkit.messageHandlers.luminest`:
 *   { event: 'ready' | 'rendered' | 'error' | 'interaction', ... }
 *
 * Nothing here is allowed to report success for a renderer that did not run. The catalog
 * gate runs before the adapter: an `external` type with no credential, or a `blocked`
 * type, fails with a stable code instead of silently drawing a substitute.
 */
import { renderVisual, RENDERER_TYPES } from './adapters.js';
import catalog from './catalog.generated.json';

const VERSION = '1.0.0';
const stage = () => document.getElementById('stage');
let active = null;
let serial = 0;

function emit(event, fields) {
  const bridge = window.webkit
    && window.webkit.messageHandlers
    && window.webkit.messageHandlers.luminest;
  const message = Object.assign({ event, version: VERSION }, fields || {});
  if (bridge && typeof bridge.postMessage === 'function') {
    bridge.postMessage(message);
  }
  // Also leave a machine-readable DOM trace for the packaging smoke test, which loads
  // this page in a headless WKWebView without a native message handler.
  document.documentElement.setAttribute('data-luminest-event', event);
  document.documentElement.setAttribute('data-luminest-payload', JSON.stringify(message));
}

function showState(code, detail) {
  const el = document.getElementById('state');
  if (!el) return;
  el.hidden = false;
  el.textContent = `${code}${detail ? ` — ${detail}` : ''}`;
  el.setAttribute('data-code', code);
}

function hideState() {
  const el = document.getElementById('state');
  if (el) { el.hidden = true; el.textContent = ''; el.removeAttribute('data-code'); }
}

function disposeActive() {
  if (!active) return;
  try { active.dispose && active.dispose(); } catch (_) { /* teardown is best effort */ }
  active = null;
}

const STATE_FAILURE = Object.freeze({
  external: 'EXTERNAL_PROVIDER_UNAVAILABLE',
  blocked: 'RENDERER_BLOCKED',
  missing: 'RENDERER_ASSETS_NOT_INSTALLED',
});

async function renderFromNative(payload) {
  const { type, spec, config, requestId } = payload || {};
  const ticket = ++serial;
  disposeActive();
  hideState();

  const entry = (catalog.types || {})[type];
  if (!entry) {
    const code = 'UNSUPPORTED_TYPE';
    showState(code, String(type));
    emit('error', { requestId: requestId || '', type, code, detail: String(type) });
    return { ok: false, code };
  }
  if (entry.status !== 'available') {
    const code = STATE_FAILURE[entry.status] || 'RENDERER_BLOCKED';
    const detail = entry.requirement || `renderer status is ${entry.status}`;
    showState(code, detail);
    emit('error', { requestId: requestId || '', type, code, detail });
    return { ok: false, code, detail };
  }
  // A first-class type can still need a runtime prerequisite. Refuse it explicitly:
  // never draw a substitute, never report success, always name what is missing.
  const cfg = config || {};
  if (entry.requires === 'desmosApiKey' && !cfg.desmosApiKey) {
    const code = 'EXTERNAL_PROVIDER_UNAVAILABLE';
    const detail = entry.requirement || 'Desmos API key is not configured';
    showState(code, detail);
    emit('error', { requestId: requestId || '', type, code, detail });
    return { ok: false, code, detail };
  }
  if (entry.requires === 'tikzAssets' && !cfg.tikzAssets) {
    const code = 'RENDERER_ASSETS_NOT_INSTALLED';
    const detail = entry.requirement || 'TikZ TeX-WASM assets are not installed';
    showState(code, detail);
    emit('error', { requestId: requestId || '', type, code, detail });
    return { ok: false, code, detail };
  }
  if (!RENDERER_TYPES.includes(type)) {
    const code = 'RENDERER_ASSETS_NOT_INSTALLED';
    const detail = `no adapter compiled for ${type}`;
    showState(code, detail);
    emit('error', { requestId: requestId || '', type, code, detail });
    return { ok: false, code, detail };
  }

  try {
    const result = await renderVisual(type, spec, stage(), config || {});
    if (ticket !== serial) { // a newer render arrived while this one was compiling
      try { result.dispose && result.dispose(); } catch (_) { /* superseded */ }
      return { ok: false, code: 'SUPERSEDED' };
    }
    active = result;
    emit('rendered', { requestId: requestId || '', type });
    return { ok: true, type };
  } catch (e) {
    const code = e && e.code ? e.code : 'RENDER_FAILED';
    const detail = e && e.detail ? e.detail : (e && e.message ? e.message : String(e));
    showState(code, detail);
    emit('error', { requestId: requestId || '', type, code, detail });
    return { ok: false, code, detail };
  }
}

window.LuminestVisuals = Object.freeze({
  version: VERSION,
  catalog,
  rendererTypes: RENDERER_TYPES,
  renderFromNative,
  dispose: () => { disposeActive(); hideState(); },
});

// Let the renderer observe a resize before native re-renders; the visual adapters with
// their own resize handling (Plotly, JSXGraph, 3Dmol) pick this up.
window.addEventListener('resize', () => {
  try {
    if (window.Plotly && window.Plotly.Plots) window.Plotly.Plots.resize(stage());
  } catch (_) { /* nothing to resize */ }
});

emit('ready', { rendererTypes: RENDERER_TYPES });
