"""Cross-unit contract tests for the web layer (regressions from adversarial verification).

Pins the four behaviours that previously failed:

1. A tool-created artifact (written through ``sims_store`` directly, no LLM) is
   served by the web layer, with ``?version=`` history intact.
2. ``POST /api/v1/sims`` runs the store's HTML validator -- an artifact that
   loads an outside script is refused with the validator's problems and stored
   nowhere.
3. The change-request role comes from the authenticated account, not the
   payload: a student declaring ``role: 'teacher'`` is still a student, and a
   create attempt is refused with a reason naming the four student categories.
4. Path traversal on the static asset route never escapes the web root.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.harness import sims_store
from app.main import create_app
from app.web_routes import AGENT_SCRIPT_TAG, WEB_DIR, inject_agent_script


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


GOOD_SIM = """<!DOCTYPE html>
<html><head><title>T</title><style>body{margin:0}</style></head>
<body><svg viewBox="0 0 100 100">
<g data-series="demo"><line x1="10" y1="10" x2="90" y2="90" stroke="black"/></g>
</svg><script>document.getElementById('x');</script></body></html>"""

EDITED_SIM = GOOD_SIM.replace('x2="90" y2="90"', 'x2="90" y2="50"')

EXTERNAL_SCRIPT_SIM = GOOD_SIM.replace('<style>', '<script src="https://cdn.example.com/x.js"></script><style>')


def test_tool_created_artifact_served_with_version_history(settings, client):
    """The store is the single storage path: what the creation tools write, the
    web layer serves -- latest by default, any version by query param."""
    assert sims_store.validate_html(GOOD_SIM, kind='simulation') == []
    entry = sims_store.create_artifact(settings, kind='simulation',
                                       title='Tool made', html=GOOD_SIM)
    artifact_id = entry['id']
    sims_store.save_version(settings, artifact_id, EDITED_SIM, note='bug fix')

    latest = client.get(f'/api/v1/sims/{artifact_id}/raw')
    assert latest.status_code == 200
    assert latest.headers['content-type'].startswith('text/html')
    assert latest.text == inject_agent_script(EDITED_SIM)  # bridge injected on the way out

    original = client.get(f'/api/v1/sims/{artifact_id}/raw?version=1')
    assert original.status_code == 200
    assert original.text == inject_agent_script(GOOD_SIM)  # pre-edit bytes, plus bridge

    # Store bytes stay canonical: the version history is untouched by serving.
    assert sims_store.read_version(settings, artifact_id) == EDITED_SIM
    assert sims_store.read_version(settings, artifact_id, 1) == GOOD_SIM

    meta = client.get(f'/api/v1/sims/{artifact_id}')
    assert meta.status_code == 200
    assert meta.json()['latest_version'] == 2

    missing_version = client.get(f'/api/v1/sims/{artifact_id}/raw?version=99')
    assert missing_version.status_code == 404


def test_post_sims_refused_by_validator_and_stores_nothing(settings, client):
    before = len(sims_store.list_artifacts(settings))
    response = client.post('/api/v1/sims', json={'title': 'Evil', 'html': EXTERNAL_SCRIPT_SIM})
    assert response.status_code == 422
    body = response.json()
    problems = ' '.join(body['detail']['problems'])
    assert 'outside host' in problems
    assert len(sims_store.list_artifacts(settings)) == before  # nothing stored


def test_student_cannot_declare_teacher_role_on_change_requests(settings, client):
    """The gate decides from the account, not the payload: a learner account
    that declares ``role: 'teacher'`` is still a student, and a create attempt
    is refused with the four categories it could have filed."""
    registered = client.post('/api/v1/auth/register', json={
        'name': 'Learner One', 'email': 'learner-one@example.test',
        'password': 'long-secret-password'})
    assert registered.status_code == 201, registered.text
    headers = {'Authorization': 'Bearer ' + registered.json()['token']}

    entry = sims_store.create_artifact(settings, kind='simulation',
                                       title='S', html=GOOD_SIM)
    artifact_id = entry['id']

    attack = client.post(f'/api/v1/sims/{artifact_id}/requests', headers=headers, json={
        'category': 'create', 'note': 'build me a brand-new simulation',
        'role': 'teacher'})
    assert attack.status_code == 403, attack.text
    reason = attack.json()['detail']
    for category in ('bug', 'wrong_info', 'ugly', 'ux'):
        assert category in reason, f'reason must name the alternative {category}'

    # A legitimate student category still goes through, recorded as a student
    # despite the declaration.
    honest = client.post(f'/api/v1/sims/{artifact_id}/requests', headers=headers, json={
        'category': 'bug', 'note': 'the curve does not move', 'role': 'teacher'})
    assert honest.status_code == 201, honest.text
    record = honest.json()
    assert record['role'] == 'student'
    assert record['declared_role'] == 'teacher'  # kept for the audit trail only


def test_static_asset_route_never_escapes_the_web_root(client):
    for path in ('/web/../app/main.py',
                 '/web/%2e%2e/app/main.py',
                 '/web/..%2f..%2fapp%2fmain.py',
                 '/web/....//app/main.py',
                 '/web/%2e%2e%2f%2e%2e%2fetc%2fpasswd'):
        response = client.get(path)
        assert response.status_code in (400, 404), f'{path}: {response.status_code}'
        assert 'SCHEMA_VERSION' not in response.text  # never the file's contents


def test_sandbox_never_grants_same_origin_and_bridge_is_serve_time_only(settings, client):
    """The orch-verify-2 escape (allow-scripts + allow-same-origin -> parent
    sessionStorage) must stay structurally impossible: the iframe is
    allow-scripts only, and the sim's outbound channel is the injected agent
    bridge, added at serve time so store bytes stay canonical."""
    index = (WEB_DIR / 'index.html').read_text(encoding='utf-8')
    assert 'sandbox="allow-scripts"' in index
    assert 'allow-same-origin' not in index

    entry = sims_store.create_artifact(settings, kind='simulation',
                                       title='S', html=GOOD_SIM)
    served = client.get(f'/api/v1/sims/{entry["id"]}/raw')
    assert '/web/luminfest-agent.js' in served.text
    assert sims_store.read_version(settings, entry['id']) == GOOD_SIM  # not stored into

    already_bridged = GOOD_SIM.replace('</body>', '<script src="/web/luminfest-agent.js"></script></body>')
    assert inject_agent_script(already_bridged) == already_bridged  # idempotent


def test_luminfest_ready_handshake_exists_in_served_artifacts(settings, client):
    """The sim -> parent handshake is pinned at the artifact level, end to end.

    ``inject_agent_script`` embeds an *external* tag (``AGENT_SCRIPT_TAG``),
    not an inline copy, so the bridge's content ships as its own artifact at
    ``/web/luminfest-agent.js``. The pin therefore checks both served artifacts:
    the sim HTML must carry the injected bridge tag, and the served bridge
    script must announce ``luminfest:ready`` to the parent -- otherwise the
    workbench's "bridge not ready" path silently becomes the only path.
    """
    entry = sims_store.create_artifact(settings, kind='simulation',
                                       title='Handshake', html=GOOD_SIM)
    served = client.get(f'/api/v1/sims/{entry["id"]}/raw')
    assert served.status_code == 200
    assert AGENT_SCRIPT_TAG in served.text, 'served sim must carry the injected bridge script'

    bridge = client.get('/web/luminfest-agent.js')
    assert bridge.status_code == 200
    assert re.search(r"send\(\{\s*type:\s*'luminfest:ready'\s*\}\)", bridge.text), \
        'bridge script must announce luminfest:ready to the parent'


def test_parent_checks_event_source_before_handling_luminfest_ready(client):
    """The parent side of the handshake: web/app.js must validate
    ``event.source === iframe.contentWindow`` before dispatching any luminfest:
    message. A regression that drops the source check (trusting any window's
    postMessage) fails the suite even though the browser still "works"."""
    app_js = client.get('/web/app.js')
    assert app_js.status_code == 200
    text = app_js.text

    guard = text.find('event.source !== els.frame.contentWindow')
    assert guard != -1, 'parent must check event.source against the sim frame'

    ready = text.find("data.type === 'luminfest:ready'")
    assert ready != -1, 'parent must dispatch luminfest:ready'
    assert guard < ready, 'the event.source guard must run before any luminfest: dispatch'
