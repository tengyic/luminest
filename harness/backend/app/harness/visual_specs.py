"""Single source of truth for Luminest structured whiteboard visual objects.

A ``visual`` board node carries one structured content object::

    {"kind": "visual", "x": ..., "y": ..., "w": ..., "h": ...,
     "payload": {"type": "mafs", "title": "Parabola", "spec": {...}}}

``type`` is one of the renderer families (mafs, plotly, jsxgraph, mathbox, molecule,
desmos, tikz, tex); ``spec`` is type-specific. This module
owns BOTH the catalog that clients render their tool palette from, and the fail-close
validator that decides what the board is allowed to store. Nothing here executes a spec:
strings are data, expressions go through a closed grammar, and unknown keys are refused
rather than ignored.

Two deliberate boundaries
-------------------------
* **The client never supplies its own status or provider.** ``clean_visual_payload``
  overwrites those from the catalog, so a caller cannot mark a BLOCKED renderer as
  available or smuggle extra envelope fields onto a node.
* **External / asset-gated renderers are still first-class types.** ``desmos`` needs an
  API key, ``tikz`` needs the vendored TeX-WASM assets. They are validated and catalogued
  exactly like the offline ones; at render time a missing prerequisite produces a stable
  error code, never a substitute drawing.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

VISUAL_TYPES: tuple[str, ...] = (
    'mafs', 'plotly', 'jsxgraph', 'mathbox', 'molecule', 'desmos', 'tikz', 'tex',
)

# These are statements about the JavaScript bundle that actually ships, not intent.
# ``web-visuals/package.json`` is the authority: MathBox 2 still imports WebGL1Renderer,
# which three >= 0.163 removed, so three had to be pinned back to 0.162.0 after the
# build broke. ``test_visual_specs.py`` refuses a catalog that disagrees with that
# manifest, so a dependency bump can no longer leave the gallery naming the old version.
MAFS_VERSION = '0.21.0'
MATHBOX_VERSION = '2.3.2-rc1'
THREE_VERSION = '0.162.0'

# ``status`` is a capability statement; ``provider`` says where the code comes from;
# ``requires`` names the runtime prerequisite the native host must satisfy.
CATALOG: dict[str, dict[str, Any]] = {
    'mafs': {
        'status': 'available', 'provider': 'bundled', 'requires': '',
        'label': '2D mathematics',
        'purpose': 'two-dimensional mathematical visuals',
        'renderer': f'Mafs {MAFS_VERSION}',
        'defaultSize': [560, 360],
        'specKeys': ['viewport', 'curves', 'points', 'segments', 'vectors'],
    },
    'plotly': {
        'status': 'available', 'provider': 'bundled', 'requires': '',
        'label': 'Data charts & 3D plots',
        'purpose': 'data charts and three-dimensional plots',
        'renderer': 'Plotly.js 2.35.2',
        'defaultSize': [600, 400],
        'specKeys': ['traces', 'layout'],
    },
    'jsxgraph': {
        'status': 'available', 'provider': 'bundled', 'requires': '',
        'label': 'Coordinate geometry',
        'purpose': 'coordinate graphs and interactive geometry',
        'renderer': 'JSXGraph 1.10.1',
        'defaultSize': [560, 380],
        'specKeys': ['viewport', 'functions', 'points', 'segments', 'polygons'],
    },
    'mathbox': {
        'status': 'available', 'provider': 'bundled', 'requires': '',
        'label': '3D mathematics',
        'purpose': 'three-dimensional mathematical scenes',
        'renderer': f'MathBox {MATHBOX_VERSION} / three {THREE_VERSION}',
        'defaultSize': [600, 420],
        'specKeys': ['range', 'surfaces', 'curves3d'],
    },
    'molecule': {
        'status': 'available', 'provider': 'bundled', 'requires': '',
        'label': 'Molecular viewer',
        'purpose': 'chemical structures and molecular shapes',
        'renderer': '3Dmol.js 2.4.2',
        'defaultSize': [480, 420],
        'specKeys': ['format', 'data', 'style', 'spin'],
    },
    'desmos': {
        'status': 'available', 'provider': 'external', 'requires': 'desmosApiKey',
        'label': 'Interactive equations',
        'purpose': 'interactive equations and function graphs in the calculator tools',
        'renderer': 'Desmos API v1.11 (loaded from www.desmos.com)',
        'defaultSize': [600, 400],
        'specKeys': ['expressions', 'viewport'],
        'requirement': ('Official Desmos API key + network access; the loader cannot be '
                        'vendored offline. Without a key the host reports '
                        'EXTERNAL_PROVIDER_UNAVAILABLE.'),
    },
    'tikz': {
        'status': 'available', 'provider': 'bundled', 'requires': 'tikzAssets',
        'label': 'TikZ diagrams',
        'purpose': 'illustrations, flowcharts, schematic diagrams',
        'renderer': 'TikZJax (TeX-in-WASM), vendored GPL-3.0/LPPL-1.3c assets',
        'defaultSize': [520, 380],
        'specKeys': ['source'],
        'requirement': ('Requires the vendored tex.wasm, core dump and 140 Bakoma fonts. '
                        'If packaging omits them the host reports '
                        'RENDERER_ASSETS_NOT_INSTALLED.'),
    },
    'tex': {
        'status': 'available', 'provider': 'bundled', 'requires': '',
        'label': 'Equation (LaTeX)',
        'purpose': 'a single LaTeX equation or formula, rendered by the client LaTeX engine',
        'renderer': 'KaTeX (client-side)',
        'defaultSize': [360, 120],
        'specKeys': ['latex', 'display'],
        'requirement': ('Rendered from one LaTeX expression by the client LaTeX engine '
                        '(KaTeX on the web host). The native host needs a LaTeX renderer '
                        'wired into the visual pipeline before it can paint this node.'),
    },
}

CATALOG_VERSION = 1
MAX_SPEC_BYTES = 65536
MAX_TITLE_CHARS = 160
MAX_EXPR_CHARS = 256
MAX_ARRAY_ITEMS = 2000
MAX_TRACE_COUNT = 12
MAX_ELEMENT_COUNT = 64
MAX_MOLECULE_CHARS = 200_000
MAX_TIKZ_CHARS = 20_000
MAX_TEX_CHARS = 600

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
_EXPR_CHARS = re.compile(r'^[0-9A-Za-z_+\-*/^().,\s]+$')
_EXPR_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_EXPR_FUNCS = frozenset({
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sqrt', 'abs', 'exp',
    'ln', 'log10', 'log2', 'floor', 'ceil', 'round', 'sign',
    'sinh', 'cosh', 'tanh', 'min', 'max', 'pow', 'atan2',
})
_EXPR_CONSTS = frozenset({'pi', 'e'})
_IMPLICIT_MUL = re.compile(r'[0-9)]\s*[A-Za-z_(]')
# TikZJax receives the source inside a <script type="text/tikz"> element, so the only
# escape from that raw-text context is a literal HTML tag opener - not '<' or '>' on
# their own. A blanket [^<>]* rule also refused standard TikZ arrows ('->', '<->'),
# which silently rejected the most common flowchart request the board supports.
_HTML_TAG_OPEN = re.compile(r'<\s*/?\s*[A-Za-z!]')
_LATEX_SAFE = re.compile(r"^[A-Za-z0-9\\{}_^+\-*/=.,()\[\]\s|:<>']*$")
_STRUCTURE_SAFE = re.compile(r"^[A-Za-z0-9\s.\-+_,;:()\[\]{}'\"=#@/\\]*$")

PLOTLY_TRACE_TYPES = frozenset({'scatter', 'bar', 'scatter3d', 'surface', 'histogram'})
MOLECULE_FORMATS = frozenset({'pdb', 'sdf', 'mol', 'xyz'})
MOLECULE_STYLES = frozenset({'stick', 'sphere', 'cartoon', 'line', 'cross'})


def catalog_document() -> dict[str, Any]:
    """The wire shape served by /api/v1/visuals/catalog and embedded into the JS host."""
    return {
        'version': CATALOG_VERSION,
        'types': {key: dict(value) for key, value in CATALOG.items()},
        'order': list(VISUAL_TYPES),
    }


def _text(value: Any, cap: int) -> str:
    return ' '.join(str(value or '').split())[:cap]


def _finite(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and abs(float(value)) <= 1_000_000)


def _number(value: Any) -> float | None:
    return round(float(value), 6) if _finite(value) else None


def _pair(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    a, b = _number(value[0]), _number(value[1])
    return [a, b] if a is not None and b is not None and a <= b else None


def _point_list(value: Any, cap: int = MAX_ARRAY_ITEMS) -> list[list[float]] | None:
    if not isinstance(value, list) or not (1 <= len(value) <= cap):
        return None
    out = []
    for item in value:
        pair = _pair_any(item)
        if pair is None:
            return None
        out.append(pair)
    return out


def _pair_any(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    a, b = _number(value[0]), _number(value[1])
    return [a, b] if a is not None and b is not None else None


def _numeric_list(value: Any, cap: int = MAX_ARRAY_ITEMS) -> list[float] | None:
    if not isinstance(value, list) or len(value) > cap:
        return None
    out = []
    for item in value:
        n = _number(item)
        if n is None:
            return None
        out.append(n)
    return out


def _colour(value: Any, fallback: str = '') -> str:
    s = str(value or '')
    return s if _HEX.match(s) else fallback


def _expr(value: Any, variables: tuple[str, ...]) -> str | None:
    """Validate a mathematical expression against the same closed grammar as safeexpr.js."""
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_EXPR_CHARS:
        return None
    if not _EXPR_CHARS.match(value) or _IMPLICIT_MUL.search(value):
        return None
    # Balance parentheses here too: safeexpr.js would reject an unbalanced string at
    # render time, and a spec that can only ever fail should never be stored.
    depth = 0
    for char in value:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                return None
    if depth != 0:
        return None
    allowed = _EXPR_FUNCS | _EXPR_CONSTS | frozenset(variables)
    if any(name not in allowed for name in _EXPR_IDENT.findall(value)):
        return None
    return ' '.join(value.split())


def _only_keys(spec: dict, allowed: tuple[str, ...]) -> bool:
    return not (set(spec) - set(allowed))


def _viewport(spec: dict) -> dict:
    out: dict[str, Any] = {}
    if 'viewport' in spec:
        v = spec['viewport']
        if not isinstance(v, dict) or not _only_keys(v, ('x', 'y', 'boundingbox')):
            return {}
        for axis in ('x', 'y'):
            if axis in v:
                pair = _pair(v[axis])
                if pair is None:
                    return {}
                out[axis] = pair
        if 'boundingbox' in v:
            bb = v['boundingbox']
            if not isinstance(bb, list) or len(bb) != 4:
                return {}
            nums = [_number(n) for n in bb]
            if any(n is None for n in nums):
                return {}
            out['boundingbox'] = nums
    return out


def _clean_mafs(spec: dict) -> dict | None:
    if not _only_keys(spec, ('viewport', 'curves', 'points', 'segments', 'vectors')):
        return None
    out: dict[str, Any] = {}
    if 'viewport' in spec:
        out['viewport'] = _viewport(spec)
        if not out['viewport']:
            return None
    if 'curves' in spec:
        raw = spec['curves']
        if not isinstance(raw, list) or len(raw) > MAX_TRACE_COUNT:
            return None
        curves = []
        for item in raw:
            if not isinstance(item, dict) or not _only_keys(item, ('expr', 'points', 'domain', 'color')):
                return None
            if ('expr' in item) == ('points' in item):
                return None
            row: dict[str, Any] = {}
            if 'expr' in item:
                expr = _expr(item['expr'], ('x',))
                if expr is None:
                    return None
                row['expr'] = expr
            else:
                pts = _point_list(item['points'])
                if pts is None or len(pts) < 2:
                    return None
                row['points'] = pts
            if 'domain' in item:
                pair = _pair(item['domain'])
                if pair is None:
                    return None
                row['domain'] = pair
            if 'color' in item:
                row['color'] = _colour(item['color'], '#3b6fd4')
            curves.append(row)
        out['curves'] = curves
    for key in ('points', 'segments', 'vectors'):
        if key not in spec:
            continue
        raw = spec[key]
        if not isinstance(raw, list) or len(raw) > MAX_ELEMENT_COUNT:
            return None
        rows = []
        for item in raw:
            if not isinstance(item, dict):
                return None
            if key == 'points':
                if not _only_keys(item, ('x', 'y', 'label', 'color')):
                    return None
                x, y = _number(item.get('x')), _number(item.get('y'))
                if x is None or y is None:
                    return None
                row = {'x': x, 'y': y}
                if 'label' in item:
                    row['label'] = _text(item['label'], 60)
            else:
                if not _only_keys(item, ('from', 'to', 'color')):
                    return None
                a, b = _pair_any(item.get('from')), _pair_any(item.get('to'))
                if a is None or b is None:
                    return None
                row = {'from': a, 'to': b}
            if 'color' in item:
                row['color'] = _colour(item['color'], '#333333')
            rows.append(row)
        out[key] = rows
    return out


def _clean_plotly(spec: dict) -> dict | None:
    if not _only_keys(spec, ('traces', 'layout')):
        return None
    raw = spec.get('traces')
    if not isinstance(raw, list) or not (1 <= len(raw) <= MAX_TRACE_COUNT):
        return None
    traces = []
    for item in raw:
        if not isinstance(item, dict) or not _only_keys(item, ('type', 'x', 'y', 'z', 'mode', 'name')):
            return None
        if item.get('type') not in PLOTLY_TRACE_TYPES:
            return None
        row: dict[str, Any] = {'type': item['type']}
        for key in ('x', 'y', 'z'):
            if key in item:
                values = item[key]
                if isinstance(values, list) and values and isinstance(values[0], list):
                    grid = [_numeric_list(row_) for row_ in values[:64]]
                    if any(g is None for g in grid):
                        return None
                    row[key] = grid
                else:
                    nums = _numeric_list(values)
                    if nums is None:
                        return None
                    row[key] = nums
        if 'mode' in item and item['mode'] in ('lines', 'markers', 'lines+markers'):
            row['mode'] = item['mode']
        if 'name' in item:
            row['name'] = _text(item['name'], 80)
        traces.append(row)
    out: dict[str, Any] = {'traces': traces}
    if 'layout' in spec:
        l = spec['layout']
        if not isinstance(l, dict) or not _only_keys(l, ('title', 'xTitle', 'yTitle')):
            return None
        out['layout'] = {k: _text(l[k], 120) for k in l}
    return out


def _clean_jsxgraph(spec: dict) -> dict | None:
    if not _only_keys(spec, ('viewport', 'functions', 'points', 'segments', 'polygons')):
        return None
    out: dict[str, Any] = {}
    if 'viewport' in spec:
        out['viewport'] = _viewport(spec)
        if not out['viewport']:
            return None
    if 'functions' in spec:
        raw = spec['functions']
        if not isinstance(raw, list) or len(raw) > MAX_TRACE_COUNT:
            return None
        rows = []
        for item in raw:
            if not isinstance(item, dict) or not _only_keys(item, ('expr', 'domain', 'color')):
                return None
            expr = _expr(item.get('expr'), ('x',))
            if expr is None:
                return None
            row = {'expr': expr}
            if 'domain' in item:
                pair = _pair(item['domain'])
                if pair is None:
                    return None
                row['domain'] = pair
            if 'color' in item:
                row['color'] = _colour(item['color'], '#3b6fd4')
            rows.append(row)
        out['functions'] = rows
    if 'points' in spec:
        raw = spec['points']
        if not isinstance(raw, list) or len(raw) > MAX_ELEMENT_COUNT:
            return None
        rows = []
        for item in raw:
            if not isinstance(item, dict) or not _only_keys(item, ('x', 'y', 'label', 'color')):
                return None
            x, y = _number(item.get('x')), _number(item.get('y'))
            if x is None or y is None:
                return None
            row = {'x': x, 'y': y}
            if 'label' in item:
                row['label'] = _text(item['label'], 60)
            if 'color' in item:
                row['color'] = _colour(item['color'], '#c0392b')
            rows.append(row)
        out['points'] = rows
    if 'segments' in spec:
        raw = spec['segments']
        if not isinstance(raw, list) or len(raw) > MAX_ELEMENT_COUNT:
            return None
        rows = []
        for item in raw:
            if not isinstance(item, dict) or not _only_keys(item, ('from', 'to', 'color')):
                return None
            a, b = _pair_any(item.get('from')), _pair_any(item.get('to'))
            if a is None or b is None:
                return None
            rows.append({'from': a, 'to': b, 'color': _colour(item.get('color'), '#333333')})
        out['segments'] = rows
    if 'polygons' in spec:
        raw = spec['polygons']
        if not isinstance(raw, list) or len(raw) > MAX_ELEMENT_COUNT:
            return None
        rows = []
        for item in raw:
            if not isinstance(item, dict) or not _only_keys(item, ('vertices', 'color')):
                return None
            vertices = _point_list(item.get('vertices'), 64)
            if vertices is None or len(vertices) < 3:
                return None
            rows.append({'vertices': vertices, 'color': _colour(item.get('color'), '#3b6fd4')})
        out['polygons'] = rows
    return out


def _clean_mathbox(spec: dict) -> dict | None:
    if not _only_keys(spec, ('range', 'surfaces', 'curves3d')):
        return None
    out: dict[str, Any] = {}
    if 'range' in spec:
        r = spec['range']
        if not isinstance(r, list) or len(r) != 3:
            return None
        pairs = [_pair(p) for p in r]
        if any(p is None for p in pairs):
            return None
        out['range'] = pairs
    if 'surfaces' in spec:
        raw = spec['surfaces']
        if not isinstance(raw, list) or len(raw) > 4:
            return None
        rows = []
        for item in raw:
            if not isinstance(item, dict) or not _only_keys(
                    item, ('expr', 'xRange', 'yRange', 'grid', 'color')):
                return None
            expr = _expr(item.get('expr'), ('x', 'y'))
            if expr is None:
                return None
            row: dict[str, Any] = {'expr': expr}
            for key in ('xRange', 'yRange'):
                if key in item:
                    pair = _pair(item[key])
                    if pair is None:
                        return None
                    row[key] = pair
            if 'grid' in item:
                n = item['grid']
                if not isinstance(n, int) or isinstance(n, bool) or not (4 <= n <= 64):
                    return None
                row['grid'] = n
            if 'color' in item:
                row['color'] = _colour(item['color'], '#3b6fd4')
            rows.append(row)
        out['surfaces'] = rows
    if 'curves3d' in spec:
        raw = spec['curves3d']
        if not isinstance(raw, list) or len(raw) > 8:
            return None
        rows = []
        for item in raw:
            if not isinstance(item, dict) or not _only_keys(item, ('expr', 'tRange', 'color')):
                return None
            expr = _expr(item.get('expr'), ('t',))
            if expr is None:
                return None
            row: dict[str, Any] = {'expr': expr}
            if 'tRange' in item:
                pair = _pair(item['tRange'])
                if pair is None:
                    return None
                row['tRange'] = pair
            if 'color' in item:
                row['color'] = _colour(item['color'], '#c0392b')
            rows.append(row)
        out['curves3d'] = rows
    return out


def _clean_molecule(spec: dict) -> dict | None:
    if not _only_keys(spec, ('format', 'data', 'style', 'spin')):
        return None
    fmt = spec.get('format')
    if fmt not in MOLECULE_FORMATS:
        return None
    data = spec.get('data')
    if not isinstance(data, str) or not data.strip() or len(data) > MAX_MOLECULE_CHARS:
        return None
    if not _STRUCTURE_SAFE.match(data):
        return None
    out: dict[str, Any] = {'format': fmt, 'data': data}
    style = spec.get('style', 'stick')
    out['style'] = style if style in MOLECULE_STYLES else 'stick'
    out['spin'] = bool(spec.get('spin', False))
    return out


def _clean_desmos(spec: dict) -> dict | None:
    if not _only_keys(spec, ('expressions', 'viewport')):
        return None
    raw = spec.get('expressions')
    if not isinstance(raw, list) or not (1 <= len(raw) <= 24):
        return None
    rows = []
    for item in raw:
        if not isinstance(item, dict) or not _only_keys(item, ('latex', 'color')):
            return None
        latex = item.get('latex')
        if not isinstance(latex, str) or not latex.strip() or len(latex) > 512:
            return None
        if '<' in latex or '>' in latex or not _LATEX_SAFE.match(latex):
            return None
        row: dict[str, Any] = {'latex': latex}
        if 'color' in item:
            row['color'] = _colour(item['color'], '#3b6fd4')
        rows.append(row)
    out: dict[str, Any] = {'expressions': rows}
    if 'viewport' in spec:
        v = spec['viewport']
        if not isinstance(v, dict) or not _only_keys(v, ('bounds',)):
            return None
        b = v.get('bounds')
        if not isinstance(b, dict) or not _only_keys(b, ('left', 'right', 'bottom', 'top')):
            return None
        nums = {k: _number(b.get(k)) for k in ('left', 'right', 'bottom', 'top')}
        if any(n is None for n in nums.values()):
            return None
        out['viewport'] = {'bounds': nums}
    return out


def _clean_tikz(spec: dict) -> dict | None:
    if not _only_keys(spec, ('source',)):
        return None
    source = spec.get('source')
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_TIKZ_CHARS:
        return None
    # The source is injected into an srcdoc frame as a raw-text <script type="text/tikz">
    # element. Refuse a tag opener (the one way out of raw-text), TeX shell-escape and
    # arbitrary file inclusion regardless of the sandbox. Plain '>' / '<->' arrow syntax
    # stays legal: it cannot terminate a script element.
    if (_HTML_TAG_OPEN.search(source) or '\\write18' in source
            or '\\input{' in source):
        return None
    return {'source': source}


def _clean_tex(spec: dict) -> dict | None:
    if not _only_keys(spec, ('latex', 'display')):
        return None
    latex = spec.get('latex')
    if not isinstance(latex, str) or not latex.strip() or len(latex) > MAX_TEX_CHARS:
        return None
    # Same closed LaTeX character set the problem card and desmos expressions use: refuse
    # angle brackets (a markup escape in a WebView context) and TeX shell-escape / file
    # inclusion. A bare '<' / '>' is not valid math here, so it is refused outright rather
    # than relying on KaTeX never emitting it.
    if '<' in latex or '>' in latex or not _LATEX_SAFE.match(latex):
        return None
    if '\\write18' in latex or '\\input{' in latex or '\\include{' in latex:
        return None
    return {'latex': latex, 'display': bool(spec.get('display', True))}


_CLEANERS = {
    'mafs': _clean_mafs,
    'plotly': _clean_plotly,
    'jsxgraph': _clean_jsxgraph,
    'mathbox': _clean_mathbox,
    'molecule': _clean_molecule,
    'desmos': _clean_desmos,
    'tikz': _clean_tikz,
    'tex': _clean_tex,
}


def clean_visual_payload(payload: Any) -> dict | None:
    """Validate one ``visual`` node payload, or return None so the board drops it.

    The catalog fields are re-derived here. A client that sends ``status``, ``provider``,
    ``schema`` or any other envelope key is refused rather than repaired - the board must
    never persist a lie about a renderer's availability.
    """
    if not isinstance(payload, dict):
        return None
    if set(payload) - {'type', 'title', 'spec'}:
        return None
    vtype = payload.get('type')
    if vtype not in VISUAL_TYPES:
        return None
    spec = payload.get('spec')
    if not isinstance(spec, dict):
        return None
    try:
        if len(json.dumps(spec, separators=(',', ':'), ensure_ascii=False)) > MAX_SPEC_BYTES:
            return None
    except (TypeError, ValueError):
        return None
    cleaned = _CLEANERS[vtype](spec)
    if cleaned is None:
        return None
    entry = CATALOG[vtype]
    out: dict[str, Any] = {
        'type': vtype,
        'title': _text(payload.get('title'), MAX_TITLE_CHARS),
        'spec': cleaned,
        'status': entry['status'],
        'provider': entry['provider'],
        'schema': CATALOG_VERSION,
    }
    return out


__all__ = [
    'CATALOG', 'CATALOG_VERSION', 'VISUAL_TYPES', 'MAX_TEX_CHARS', 'catalog_document',
    'clean_visual_payload',
]
