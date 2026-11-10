"""Contract for the dedicated scratch-board drawing agent.

These tests are deliberately offline: ``description`` requests go through an injected
stub resolver, so no model key, network or tutor session is involved. The assertions
that matter most are the isolation ones - the agent must never import the teacher tool
chain, never address a ``board-``/``wb-`` lesson canvas, and never leave the lesson
canvas modified - plus the fail-close ones: an unavailable or unfaithful resolver
produces UNRESOLVED and writes nothing.
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.harness import board, visual_specs, whiteboard_agent as wa

ROOT = Path(__file__).resolve().parents[3] / 'harness'
AGENT_SOURCE = ROOT / 'backend' / 'app' / 'harness' / 'whiteboard_agent.py'
PACKAGE_SCRIPT = ROOT / 'scripts' / 'package.py'

#: A real, renderable TikZ flowchart answering the request in the product brief:
#: "Draw boxes labeled Context and Tool, with an arrow from Context to Tool."
TIKZ_SOURCE = (
    r'\begin{tikzpicture}[node distance=3cm, >=stealth]'
    r'\node[draw, rounded corners] (context) {Context};'
    r'\node[draw, rounded corners, right of=context] (tool) {Tool};'
    r'\draw[->] (context) -- (tool);'
    r'\end{tikzpicture}'
)

EXAMPLE = {
    'id': 'context_tool_demo',
    'region': 'scratch',
    'content': {
        'type': 'tikz',
        'mode': 'description',
        'description': 'Draw boxes labeled Context and Tool, with an arrow from Context to Tool.',
        'w': 640,
        'h': 420,
    },
}


_UNSET = object()


class StubResolver:
    """Deterministic stand-in for the model role. Records every call."""

    def __init__(self, reply=_UNSET, *, raise_error=False, available=True):
        # ``None`` is a meaningful reply: it means "cannot resolve". A plain
        # ``reply or default`` would silently turn that into a valid diagram.
        self.reply = ({'title': 'Context to Tool', 'spec': {'source': TIKZ_SOURCE}}
                      if reply is _UNSET else reply)
        self.raise_error = raise_error
        self._available = available
        self.calls: list[dict] = []

    def available(self) -> bool:
        return self._available

    def __call__(self, *, vtype, description, width, height):
        self.calls.append({'vtype': vtype, 'description': description,
                           'width': width, 'height': height})
        if self.raise_error:
            raise RuntimeError('provider exploded')
        return self.reply


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(data_dir=str(tmp_path / 'data'))


def agent(settings, resolver=None, **kwargs):
    return wa.WhiteboardDrawAgent(
        settings, owner_id='learner-1',
        resolver=resolver if resolver is not None else StubResolver(), **kwargs)


def nodes(settings, board_id):
    doc = board.load(settings, board_id)
    return [] if doc is None else doc.get('nodes', [])


# ---------------------------------------------------------------- protocol parse

def test_example_request_parses_and_maps_to_internal_fields():
    parsed, refusal = wa.parse_request(EXAMPLE)
    assert refusal is None
    assert parsed['id'] == 'context_tool_demo'
    assert parsed['region'] == 'scratch'
    assert parsed['type'] == 'tikz'
    assert parsed['mode'] == 'description'
    assert (parsed['w'], parsed['h']) == (640.0, 420.0)
    assert len(parsed['fingerprint']) == 8
    # id/region/content are wire-only: the internal visual node is {type,title,spec}
    # plus geometry, derived by the agent, never taken from an envelope.
    assert 'id' not in visual_specs.clean_visual_payload(
        {'type': 'tikz', 'title': 'x', 'spec': {'source': TIKZ_SOURCE}})


def test_tikz_arrow_syntax_now_passes_the_validator():
    """The brief's diagram has an arrow; [^<>]* used to refuse every '->'."""
    cleaned = visual_specs.clean_visual_payload(
        {'type': 'tikz', 'title': 'Context to Tool', 'spec': {'source': TIKZ_SOURCE}})
    assert cleaned is not None
    assert '\\draw[->]' in cleaned['spec']['source']
    for unsafe in ('<script>alert(1)</script>', '<img src=x>',
                   '<!-- hi -->', r'\write18{rm -rf /}', r'\input{/etc/passwd}'):
        assert visual_specs.clean_visual_payload(
            {'type': 'tikz', 'title': 'x', 'spec': {'source': unsafe}}) is None


@pytest.mark.parametrize('mutation', [
    lambda r: r.pop('id'),
    lambda r: r.update({'id': 'bad id with spaces'}),
    lambda r: r.update({'extra': 1}),
    lambda r: r['content'].update({'colour': 'red'}),
    lambda r: r['content'].update({'type': 'not_a_renderer'}),
    lambda r: r['content'].update({'mode': 'guess'}),
    lambda r: r['content'].update({'w': 0}),
    lambda r: r['content'].update({'h': 999999}),
    lambda r: r['content'].update({'description': ''}),
    lambda r: r['content'].update({'spec': 'not-an-object'}),
])
def test_invalid_request_shapes_are_refused_not_repaired(mutation):
    raw = copy.deepcopy(EXAMPLE)
    mutation(raw)
    parsed, refusal = wa.parse_request(raw)
    assert parsed is None
    assert refusal['status'] == wa.CODE_REFUSED
    assert refusal['blocking']


@pytest.mark.parametrize('region', ['lesson', 'main', 'board-econ', 'wb-econ', '', None])
def test_only_scratch_region_is_defined(region):
    raw = copy.deepcopy(EXAMPLE)
    raw['region'] = region
    _parsed, refusal = wa.parse_request(raw)
    assert refusal['code'] == wa.CODE_UNSUPPORTED_REGION


# ------------------------------------------------------------------- happy path

def test_description_request_is_drawn_into_the_scratch_board(settings):
    stub = StubResolver()
    result = agent(settings, stub).draw(EXAMPLE)
    assert result['status'] == wa.CODE_DRAWN
    assert result['code'] == wa.CODE_DRAWN
    assert result['board_id'].startswith('agent-scratch-')
    assert result['node_id'].startswith('n-')
    assert result['payload']['type'] == 'tikz'
    assert result['payload']['status'] == visual_specs.CATALOG['tikz']['status']
    assert result['payload']['spec']['source'] == TIKZ_SOURCE
    assert stub.calls == [{'vtype': 'tikz',
                           'description': EXAMPLE['content']['description'],
                           'width': 640.0, 'height': 420.0}]
    doc_nodes = nodes(settings, result['board_id'])
    assert len(doc_nodes) == 1
    assert doc_nodes[0]['kind'] == 'visual'
    assert (doc_nodes[0]['w'], doc_nodes[0]['h']) == (640.0, 420.0)
    assert doc_nodes[0]['author'].startswith(wa.ACTOR_PREFIX + 'context_tool_demo:')
    assert result['provenance']['validator'] == 'app.harness.visual_specs.clean_visual_payload'


def test_agent_never_touches_the_teacher_lesson_canvas(settings):
    lesson_id = 'board-supply-demand'
    board.create(settings, owner_id='learner-1', board_id=lesson_id, title='Lesson')
    board.apply_mutations(
        settings, lesson_id, owner_id='learner-1', base_version=1,
        mutations=[{'action': 'add', 'node': {
            'kind': 'text', 'x': 10, 'y': 10, 'payload': {'text': 'teacher note'}}}],
        actor='teacher')
    before = json.dumps(board.load(settings, lesson_id), sort_keys=True)

    result = agent(settings).draw(EXAMPLE)
    assert result['status'] == wa.CODE_DRAWN
    assert not result['board_id'].startswith(('board-', 'wb-'))
    assert json.dumps(board.load(settings, lesson_id), sort_keys=True) == before


def test_agent_module_does_not_import_the_teacher_tool_chain():
    """Check real import statements, not the docstring that names them as forbidden."""
    tree = ast.parse(AGENT_SOURCE.read_text(encoding='utf-8'))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or '')
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    for forbidden in ('tools_whiteboard', 'agent_loop', 'toolbox'):
        assert forbidden not in imported, (
            f'agent must stay off the tutor tool chain: imported {forbidden}')
    assert 'board' in imported and 'visual_specs' in imported and 'provider' in imported


def test_mode_spec_is_the_deterministic_offline_path(settings):
    raw = copy.deepcopy(EXAMPLE)
    raw['content'] = {'type': 'tikz', 'mode': 'spec', 'spec': {'source': TIKZ_SOURCE},
                      'title': 'Explicit spec', 'w': 520, 'h': 380}
    stub = StubResolver()
    result = agent(settings, stub).draw(raw)
    assert result['status'] == wa.CODE_DRAWN
    assert stub.calls == []          # no model call at all
    assert result['payload']['title'] == 'Explicit spec'
    assert result['provenance']['resolver'] == 'none (mode=spec)'


# ------------------------------------------------------------------- idempotency

def test_identical_repeat_returns_already_drawn_without_a_second_node(settings):
    first = agent(settings).draw(EXAMPLE)
    second = agent(settings).draw(copy.deepcopy(EXAMPLE))
    assert second['status'] == wa.CODE_ALREADY_DRAWN
    assert second['node_id'] == first['node_id']
    assert second['provenance']['writes'] == 0
    assert len(nodes(settings, first['board_id'])) == 1
    assert board.load(settings, first['board_id'])['version'] == 2  # one create-level + one add


def test_same_id_with_different_content_is_superseded_not_overwritten(settings):
    first = agent(settings).draw(EXAMPLE)
    changed = copy.deepcopy(EXAMPLE)
    changed['content']['description'] = 'Draw a completely different diagram.'
    second = agent(settings).draw(changed)
    assert second['status'] == wa.CODE_SUPERSEDED
    assert second['node_id'] == first['node_id']
    assert second['provenance']['writes'] == 0
    assert len(nodes(settings, first['board_id'])) == 1
    assert nodes(settings, first['board_id'])[0]['payload']['spec']['source'] == TIKZ_SOURCE


def test_scratch_board_is_per_owner(settings):
    a = agent(settings).draw(EXAMPLE)
    b = wa.WhiteboardDrawAgent(settings, owner_id='learner-2',
                               resolver=StubResolver()).draw(copy.deepcopy(EXAMPLE))
    assert a['board_id'] != b['board_id']
    assert len(nodes(settings, a['board_id'])) == len(nodes(settings, b['board_id'])) == 1


def test_concurrent_identical_requests_draw_exactly_one_node(settings):
    shared = agent(settings)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: shared.draw(copy.deepcopy(EXAMPLE)), range(6)))
    assert sum(r['status'] == wa.CODE_DRAWN for r in results) == 1
    assert sum(r['status'] == wa.CODE_ALREADY_DRAWN for r in results) == 5
    board_id = results[0]['board_id']
    assert len(nodes(settings, board_id)) == 1


# --------------------------------------------------------------------- fail close

def test_unavailable_resolver_is_unresolved_and_writes_nothing(settings):
    stub = StubResolver(available=False)
    result = agent(settings, stub).draw(EXAMPLE)
    assert result['status'] == wa.CODE_UNRESOLVED
    assert result['code'] == wa.CODE_EXTERNAL_PROVIDER_UNAVAILABLE
    assert result['blocking']
    assert stub.calls == []
    assert nodes(settings, wa.scratch_board_id('learner-1')) == []


def test_default_llm_resolver_with_offline_settings_is_unresolved(settings):
    offline = SimpleNamespace(data_dir=str(settings.data_dir), provider='offline',
                              provider_url='')
    result = wa.WhiteboardDrawAgent(offline, owner_id='learner-1').draw(EXAMPLE)
    assert result['status'] == wa.CODE_UNRESOLVED
    assert 'mode=spec' in ' '.join(result['blocking'])
    assert nodes(settings, wa.scratch_board_id('learner-1')) == []


@pytest.mark.parametrize('reply', [
    None,
    {'title': 'x', 'spec': {'source': '<script>alert(1)</script>'}},
    {'title': 'x', 'spec': {'source': r'\write18{rm -rf /}'}},
    {'title': 'x', 'spec': {'unexpected': 'key'}},
    {'title': '', 'spec': None},
    'not an object',
])
def test_unfaithful_or_unsafe_resolver_output_never_reaches_the_board(settings, reply):
    stub = StubResolver(reply=reply)
    result = agent(settings, stub).draw(EXAMPLE)
    assert result['status'] == wa.CODE_UNRESOLVED
    assert result['code'] in (wa.CODE_UNRESOLVED, wa.CODE_RENDER_FAILED)
    assert result['blocking']
    assert nodes(settings, wa.scratch_board_id('learner-1')) == []


def test_resolver_exception_is_not_swallowed_into_a_fabricated_diagram(settings):
    result = agent(settings, StubResolver(raise_error=True)).draw(EXAMPLE)
    assert result['status'] == wa.CODE_UNRESOLVED
    assert any('resolver failed' in b for b in result['blocking'])
    assert nodes(settings, wa.scratch_board_id('learner-1')) == []


def test_spec_with_forged_envelope_fields_is_refused(settings):
    raw = copy.deepcopy(EXAMPLE)
    raw['content'] = {'type': 'tikz', 'mode': 'spec',
                      'spec': {'source': TIKZ_SOURCE, 'status': 'available',
                               'provider': 'bundled', 'schema': 1}}
    result = agent(settings).draw(raw)
    assert result['status'] == wa.CODE_UNRESOLVED
    assert nodes(settings, wa.scratch_board_id('learner-1')) == []


# ---------------------------------------------------------------------- catalog

def test_catalog_document_declares_the_protocol_and_isolation():
    doc = wa.catalog_document()
    assert doc['agent'] == wa.AGENT_ID
    assert doc['request']['regions'] == ['scratch']
    assert sorted(doc['request']['modes']) == ['description', 'spec']
    assert doc['rendererTypes'] == list(visual_specs.VISUAL_TYPES)
    assert doc['isolation']['teacherToolChainImported'] is False
    assert doc['isolation']['lessonCanvasPrefixes'] == ['board-', 'wb-']
    assert wa.CODE_UNRESOLVED in doc['codes']


def test_feature_router_and_frozen_probe_are_in_sync():
    from app.feature_routers import FEATURE_ROUTERS
    spec = importlib.util.spec_from_file_location('luminest_package_wa', PACKAGE_SCRIPT)
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    probes = dict(package.FEATURE_ROUTE_PROBES)
    assert 'routes_whiteboard_agent' in FEATURE_ROUTERS
    assert set(probes) == set(FEATURE_ROUTERS)
    assert probes['routes_whiteboard_agent'] == '/whiteboard-agent/catalog'


# ------------------------------------------------------- real HTTP, mounted app

@pytest.fixture
def client(tmp_path, monkeypatch):
    """The shipped offline configuration, through create_app's real router mounting."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    monkeypatch.setenv('HARNESS_ACCESS_TOKEN_TTL_SECONDS', '7200')
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    with TestClient(create_app(Settings.from_env())) as test_client:
        yield test_client


def _headers(client):
    response = client.post('/api/v1/auth/register', json={
        'name': 'wa', 'email': 'wa@example.test',
        'password': 'long-secret-password', 'age_confirmed': True})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_catalog_endpoint_is_mounted_and_declares_isolation(client):
    response = client.get('/api/v1/whiteboard-agent/catalog')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['agent'] == wa.AGENT_ID
    assert body['request']['regions'] == ['scratch']
    assert body['isolation']['teacherToolChainImported'] is False


def test_catalog_is_a_reviewed_public_route_even_with_a_credential(client):
    """A public read must be declared, not merely left without a dependency.

    Anonymous access is the easy half. The HTTP boundary also refuses any 2xx from a
    route that carried a credential without resolving a principal, unless the route is
    in ``PUBLIC_ROUTES`` - so a signed-in probe of the catalog used to answer 401. Pin
    both halves here.

    The graph assertion is scoped to *this router*: the app-wide "every route has a
    resolver" equality belongs to ``test_account_auth_single_source.py``. Asserting it
    here would make this feature's tests fail whenever another router is mid-wiring.
    """
    from app.security import PUBLIC_ROUTES, routes_without_principal

    catalog = '/api/v1/whiteboard-agent/catalog'
    assert ('GET', catalog) in PUBLIC_ROUTES
    without = set(routes_without_principal(client.app, set()))
    agent_routes = {route for route in without if '/whiteboard-agent/' in route}
    assert agent_routes == {f'GET {catalog}'}, agent_routes
    headers = _headers(client)
    response = client.get(catalog, headers=headers)
    assert response.status_code == 200, response.text


def test_draw_endpoint_without_auth_is_refused(client):
    response = client.post('/api/v1/whiteboard-agent/draw', json=EXAMPLE)
    assert response.status_code in (401, 403), response.text


def test_offline_description_request_is_honestly_unresolved(client):
    """No model configured: the endpoint says UNRESOLVED, never a fake diagram."""
    headers = _headers(client)
    response = client.post('/api/v1/whiteboard-agent/draw', json=EXAMPLE, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == wa.CODE_UNRESOLVED
    assert body['code'] == wa.CODE_EXTERNAL_PROVIDER_UNAVAILABLE
    assert any('mode=spec' in b for b in body['blocking'])


def test_spec_request_writes_a_real_board_node_over_http(client):
    headers = _headers(client)
    request = {'id': 'http_spec_demo', 'region': 'scratch',
               'content': {'type': 'tikz', 'mode': 'spec',
                           'spec': {'source': TIKZ_SOURCE}, 'w': 640, 'h': 420}}
    response = client.post('/api/v1/whiteboard-agent/draw', json=request, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == wa.CODE_DRAWN, body
    assert body['board_id'].startswith('agent-scratch-')
    # Scratch boards live in their own namespace, so they must NOT appear in the
    # teacher's lesson-canvas listing - that separation is the point of the request.
    teacher_boards = client.get('/api/v1/boards', headers=headers)
    assert teacher_boards.status_code == 200
    assert body['board_id'] not in {b['id'] for b in teacher_boards.json()['boards']}
    # They ARE visible through the agent's own listing route.
    listed = client.get('/api/v1/whiteboard-agent/boards', headers=headers)
    assert listed.status_code == 200
    assert body['board_id'] in {b['id'] for b in listed.json()['boards']}
    repeat = client.post('/api/v1/whiteboard-agent/draw', json=request, headers=headers)
    assert repeat.json()['status'] == wa.CODE_ALREADY_DRAWN
