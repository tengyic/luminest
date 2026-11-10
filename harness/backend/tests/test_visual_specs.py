"""Fail-close contract for structured whiteboard visual objects.

The board only stores a `visual` node after the catalog validator accepts it. These tests
cover the positive contract (one runnable example per renderer), the negative contract
(forgery, unknown keys, expression injection, oversize, unsafe TeX/LaTeX/molecule data),
and the boundary with board.py (kind whitelist, mandatory WebView frame).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.harness import board
from app.harness.visual_specs import (
    CATALOG, VISUAL_TYPES, catalog_document, clean_visual_payload,
)

BUNDLE_CATALOG = (
    Path(__file__).resolve().parents[2]
    / 'native' / 'Sources' / 'LearningHarness' / 'Visuals' / 'catalog.json'
)

VALID_SPECS: dict[str, dict] = {
    'mafs': {
        'viewport': {'x': [-5, 5], 'y': [-2, 8]},
        'curves': [{'expr': 'x^2'}],
        'points': [{'x': 1, 'y': 1, 'label': 'P'}],
    },
    'plotly': {
        'traces': [{'type': 'scatter', 'x': [1, 2, 3, 4],
                    'y': [1, 4, 9, 16], 'mode': 'lines+markers'}],
    },
    'jsxgraph': {
        'viewport': {'boundingbox': [-5, 5, 5, -5]},
        'functions': [{'expr': 'sin(x)'}],
    },
    'mathbox': {
        'range': [[-3, 3], [-3, 3], [-3, 3]],
        'surfaces': [{'expr': 'sin(x)*cos(y)', 'grid': 16}],
    },
    'molecule': {
        'format': 'pdb',
        'data': ('ATOM      1  C   MOL A   1       0.000   0.000   0.000  1.00  0.00           C\n'
                 'ATOM      2  O   MOL A   1       1.200   0.000   0.000  1.00  0.00           O\n'),
        'style': 'stick',
    },
    'desmos': {'expressions': [{'latex': 'x^2'}]},
    'tikz': {'source': r'\begin{tikzpicture}\draw (0,0) circle (1in);\end{tikzpicture}'},
}


def _payload(kind: str, spec: dict | None = None, **extra) -> dict:
    body = {'type': kind, 'title': 'Example', 'spec': VALID_SPECS[kind] if spec is None else spec}
    body.update(extra)
    return body


def test_catalog_is_a_single_source_of_truth():
    assert set(CATALOG) == set(VISUAL_TYPES)
    assert BUNDLE_CATALOG.is_file(), 'run harness/web-visuals/npm run build first'
    shipped = json.loads(BUNDLE_CATALOG.read_text(encoding='utf-8'))
    assert shipped == catalog_document(), 'JS host catalog has drifted from the backend'


def test_catalog_names_the_versions_that_actually_shipped():
    """The gallery is prose; package.json is what npm installed.

    three 0.187.0 was once named here while 0.162.0 was pinned (threestrap needs
    WebGL1Renderer). A string that only a human compares to package.json drifts, so the
    comparison is a test instead.
    """
    manifest = json.loads((
        Path(__file__).resolve().parents[2] / 'web-visuals' / 'package.json'
    ).read_text(encoding='utf-8'))
    deps = manifest['dependencies']
    assert CATALOG['mafs']['renderer'] == f"Mafs {deps['mafs']}"
    assert CATALOG['mathbox']['renderer'] == (
        f"MathBox {deps['mathbox']} / three {deps['three']}")


def test_catalog_states_are_explicit():
    assert CATALOG['desmos']['provider'] == 'external'
    assert CATALOG['desmos']['requires'] == 'desmosApiKey'
    assert CATALOG['tikz']['requires'] == 'tikzAssets'
    for kind in ('mafs', 'plotly', 'jsxgraph', 'mathbox', 'molecule'):
        assert CATALOG[kind]['provider'] == 'bundled'
        assert CATALOG[kind]['status'] == 'available'


def test_every_renderer_has_a_valid_example():
    assert set(VALID_SPECS) == set(VISUAL_TYPES)
    for kind, spec in VALID_SPECS.items():
        cleaned = clean_visual_payload(_payload(kind, spec))
        assert cleaned is not None, kind
        assert cleaned['type'] == kind
        assert cleaned['status'] == 'available'
        assert cleaned['provider'] == CATALOG[kind]['provider']
        assert cleaned['schema'] == catalog_document()['version']


@pytest.mark.parametrize('kind', VISUAL_TYPES)
def test_unknown_spec_keys_are_refused(kind):
    spec = dict(VALID_SPECS[kind])
    spec['__proto__'] = {'polluted': True}
    assert clean_visual_payload(_payload(kind, spec)) is None


@pytest.mark.parametrize('forged', [
    {'status': 'blocked'},
    {'provider': 'bundled'},
    {'schema': 99},
    {'region': 'scratch'},
    {'id': 'client-chosen'},
])
def test_client_cannot_forge_envelope_fields(forged):
    assert clean_visual_payload(_payload('mafs', **forged)) is None


def test_status_is_always_derived_from_the_catalog():
    cleaned = clean_visual_payload(_payload('desmos'))
    assert cleaned is not None
    assert cleaned['provider'] == 'external'  # not the bundled value a client might want
    assert cleaned['status'] == CATALOG['desmos']['status']


@pytest.mark.parametrize('expr', [
    'x; alert(1)',
    'x) + 1',
    '(x + 1',
    '2x',
    '2(x+1)',
    '__proto__',
    'constructor(x)',
    'window.alert(x)',
    'x' * 300,
    '',
])
def test_unsafe_expressions_are_refused(expr):
    payload = _payload('mafs', {'curves': [{'expr': expr}]})
    assert clean_visual_payload(payload) is None


def test_whitelisted_math_expression_survives():
    cleaned = clean_visual_payload(_payload('mafs', {'curves': [{'expr': 'sin(x)*x^2 + sqrt(abs(x))'}]}))
    assert cleaned is not None
    assert cleaned['spec']['curves'][0]['expr'] == 'sin(x)*x^2 + sqrt(abs(x))'


def test_non_finite_numbers_are_refused():
    assert clean_visual_payload(_payload('mafs', {
        'points': [{'x': float('nan'), 'y': 1}],
    })) is None


def test_oversized_spec_is_refused():
    assert clean_visual_payload(_payload('plotly', {
        'traces': [{'type': 'scatter', 'x': list(range(2001)), 'y': list(range(2001))}],
    })) is None


def test_tikz_refuses_html_and_shell_escape():
    for source in ('<script>alert(1)</script>', r'\write18{rm -rf /}', r'\input{/etc/passwd}'):
        assert clean_visual_payload(_payload('tikz', {'source': source})) is None


def test_desmos_refuses_html_in_latex():
    assert clean_visual_payload(_payload('desmos', {
        'expressions': [{'latex': '<img src=x onerror=alert(1)>'}],
    })) is None


def test_molecule_refuses_markup_and_unknown_format():
    assert clean_visual_payload(_payload('molecule', {
        'format': 'pdb', 'data': '<script>alert(1)</script>',
    })) is None
    assert clean_visual_payload(_payload('molecule', {
        'format': 'exe', 'data': 'ATOM 1 C',
    })) is None


def test_board_accepts_a_valid_visual_node():
    assert 'visual' in board.NODE_KINDS
    raw = {'kind': 'visual', 'x': 100, 'y': 120, 'w': 560, 'h': 360,
           'payload': _payload('mafs')}
    node = board._clean_node(raw)
    assert node is not None
    assert node['kind'] == 'visual'
    assert node['w'] == 560 and node['h'] == 360
    assert node['payload']['status'] == 'available'
    assert node['payload']['provider'] == 'bundled'


def test_board_refuses_zero_sized_visual_node():
    # A WKWebView with no frame is an invisible hole on the board.
    raw = {'kind': 'visual', 'x': 100, 'y': 120, 'payload': _payload('mafs')}
    assert board._clean_node(raw) is None
    raw['w'], raw['h'] = 560, 0
    assert board._clean_node(raw) is None


def test_board_refuses_invalid_visual_payload():
    raw = {'kind': 'visual', 'x': 100, 'y': 120, 'w': 560, 'h': 360,
           'payload': {'type': 'mafs', 'spec': {'curves': [{'expr': 'alert(1)'}]}}}
    assert board._clean_node(raw) is None


def test_unknown_type_is_refused():
    assert clean_visual_payload({'type': 'canvas', 'spec': {}}) is None
    assert board._clean_node({'kind': 'canvas', 'x': 0, 'y': 0, 'payload': {}}) is None


def test_existing_node_kinds_are_untouched():
    text = board._clean_node({'kind': 'text', 'x': 1, 'y': 2,
                              'payload': {'text': 'still works', 'size': 16}})
    assert text is not None and text['payload']['text'] == 'still works'
