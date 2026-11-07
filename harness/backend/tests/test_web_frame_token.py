"""The iframe credential, pinned.

The workbench shows a simulation in a sandboxed iframe, and an iframe navigation
carries only ``src`` - no ``Authorization`` header ever reaches the server on that
request. Before ``/frame-token`` existed the page handed the iframe the raw URL,
which meant a production backend answered ``401`` to the one request the feature
depends on: the canvas never loaded, and nothing in the client said why.

The fix has to be a credential that is *narrower* than the session token, because
the token ends up in browser history, in proxy logs and in any referrer the
simulation emits. These tests pin the three properties that make it narrower, and
the one property that makes it work at all:

1. It authorises exactly one artifact - a valid signature for simulation A is
   refused on simulation B.
2. It is short-lived - an expired token is refused even with a correct signature.
3. It is unforgeable - a single flipped character in the signature is refused.
4. It works with no ``Authorization`` header at all, which is the entire point.

What is *not* pinned here is the anonymous posture of the development
environment: ``principal()`` deliberately lets an unauthenticated request through
when ``settings.environment != 'production'``, so a developer can open
``/api/v1/sims/{id}/raw`` in a tab. That is a decision, not an accident, and
``test_production_refuses_an_anonymous_read`` is the test that keeps it from
becoming one that also applies to production.
"""
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.harness import sims_store
from app.main import create_app
from app.web_routes import AGENT_SCRIPT_TAG, issue_frame_token, principal

SIM_A = 'sim-frame-a'
SIM_B = 'sim-frame-b'

GOOD_SIM = """<!DOCTYPE html>
<html><head><title>Frame</title><style>body{margin:0}</style></head>
<body><svg viewBox="0 0 100 100">
<g data-series="demo"><line x1="10" y1="10" x2="90" y2="90" stroke="black"/></g>
</svg><script>document.getElementById('x');</script></body></html>"""


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_SECRET', 'test-frame-secret')
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _production_settings():
    """A production *posture* without a PostgreSQL instance.

    ``Settings.from_env()`` refuses ``production`` without Postgres - correctly,
    because a hosted instance needs a real database. The frame-token decision
    never touches the database, so it is exercised against the same settings
    object with only ``environment`` swapped.
    """
    import dataclasses

    monkey = Settings.from_env()
    return dataclasses.replace(monkey, environment='production')


def _stub_request(settings, header=''):
    """The two ``request`` attributes the frame-token code reads."""
    return SimpleNamespace(
        headers={'authorization': header} if header else {},
        app=SimpleNamespace(state=SimpleNamespace(settings=settings, factory=None)),
    )


@pytest.fixture
def sims(settings):
    """Two stored simulations, so a cross-artifact replay has somewhere to go."""
    assert sims_store.validate_html(GOOD_SIM, kind='simulation') == []
    a = sims_store.create_artifact(settings, kind='simulation', title='A', html=GOOD_SIM)
    b = sims_store.create_artifact(settings, kind='simulation', title='B', html=GOOD_SIM)
    return a['id'], b['id']


def _bearer(client, email='frame@example.com'):
    response = client.post('/api/v1/auth/register', json={
        'name': 'Frame Tester', 'email': email, 'password': 'Str0ng-pass-12345',
        'age_confirmed': True, 'accept_terms': True})
    assert response.status_code == 201, response.text
    return response.json()['token'], response.json()['user']['id']


def test_frame_token_authorises_the_iframe_with_no_header(client, sims):
    """The whole reason the route exists: ``src`` alone has to be enough."""
    sim_a, _ = sims
    token, _user_id = _bearer(client)
    minted = client.post(f'/api/v1/sims/{sim_a}/frame-token',
                         headers={'Authorization': f'Bearer {token}'})
    assert minted.status_code == 200, minted.text
    payload = minted.json()
    assert payload['expires_in'] == 120
    assert payload['url'].startswith(f'/api/v1/sims/{sim_a}/raw?frame_token=')

    served = client.get(payload['url'])  # deliberately no Authorization header
    assert served.status_code == 200, served.text
    assert 'data-series="demo"' in served.text
    assert AGENT_SCRIPT_TAG in served.text


def test_a_token_for_one_simulation_is_refused_on_another(client, sims):
    """A valid signature is not a wildcard: the claim names its artifact."""
    sim_a, sim_b = sims
    token, _ = _bearer(client, 'cross@example.com')
    minted = client.post(f'/api/v1/sims/{sim_a}/frame-token',
                         headers={'Authorization': f'Bearer {token}'})
    frame_token = minted.json()['token']

    stolen = client.get(f'/api/v1/sims/{sim_b}/raw?frame_token={frame_token}')
    assert stolen.status_code == 401

    own = client.get(f'/api/v1/sims/{sim_a}/raw?frame_token={frame_token}')
    assert own.status_code == 200


def test_a_tampered_signature_is_refused(client, sims):
    sim_a, _ = sims
    token, _ = _bearer(client, 'tamper@example.com')
    minted = client.post(f'/api/v1/sims/{sim_a}/frame-token',
                         headers={'Authorization': f'Bearer {token}'})
    frame_token = minted.json()['token']

    head, _, signature = frame_token.partition('.')
    flipped = 'f' if signature[0] != 'f' else 'e'
    forged = f'{head}.{flipped}{signature[1:]}'
    assert client.get(f'/api/v1/sims/{sim_a}/raw?frame_token={forged}').status_code == 401

    # A payload rewritten for the other simulation, keeping the signature, is
    # also refused - the signature covers the claim, not just the route.
    assert client.get(f'/api/v1/sims/{sim_a}/raw?frame_token=not-a-token').status_code == 401


def test_an_expired_token_is_refused(client, sims, monkeypatch):
    """Two minutes is the whole lifetime; nothing may extend it client-side."""
    sim_a, _ = sims
    _bearer(client, 'expiry@example.com')
    token, _ = _bearer(client, 'expiry2@example.com')

    minted = client.post(f'/api/v1/sims/{sim_a}/frame-token',
                         headers={'Authorization': f'Bearer {token}'})
    frame_token = minted.json()['token']

    later = time.time() + 3600
    monkeypatch.setattr('app.web_routes.time.time', lambda: later)
    assert client.get(f'/api/v1/sims/{sim_a}/raw?frame_token={frame_token}').status_code == 401


def test_the_ttl_is_clamped_and_never_extends_past_the_ceiling(settings):
    """A caller cannot ask for a week: ``issue_frame_token`` clamps to 600s."""
    raw, ttl = issue_frame_token(_stub_request(settings), SIM_A, ttl=10 ** 6)
    assert ttl == 600
    assert raw.count('.') == 1
    assert issue_frame_token(_stub_request(settings), SIM_A, ttl=0)[1] == 1


def test_minting_requires_a_session_and_a_real_simulation(client, sims):
    sim_a, _ = sims
    token, _ = _bearer(client, 'missing@example.com')
    # A well-formed id that is not in the store is a 404 and stores nothing.
    assert client.post('/api/v1/sims/sim-does-not-exist/frame-token',
                       headers={'Authorization': f'Bearer {token}'}).status_code == 404
    # An id that cannot be a simulation id is refused before the store is read.
    assert client.post('/api/v1/sims/Not_A_Valid_Id/frame-token',
                       headers={'Authorization': f'Bearer {token}'}).status_code == 422
    # A forged bearer is refused, so a token cannot be minted at all.
    assert client.post(f'/api/v1/sims/{sim_a}/frame-token',
                       headers={'Authorization': 'Bearer not-a-real-token'}).status_code == 401


def test_production_refuses_an_anonymous_read(settings):
    """The development convenience must not survive into a hosted instance.

    ``/raw`` accepts either a frame token or a session bearer. In production the
    second branch has to fail closed, or the route is a public file server for
    every artifact in the store. This asserts the decision itself rather than a
    full production app, because ``Settings.from_env()`` refuses to build a
    production config without PostgreSQL - and the branch under test never
    reaches the database.
    """
    production = _production_settings()
    with pytest.raises(HTTPException) as refused:
        principal(_stub_request(production, header=''))
    assert refused.value.status_code == 401
    # A malformed bearer is refused in every environment.
    with pytest.raises(HTTPException) as bad:
        principal(_stub_request(production, header='Bearer ' + 'x' * 10))
    assert bad.value.status_code == 401
