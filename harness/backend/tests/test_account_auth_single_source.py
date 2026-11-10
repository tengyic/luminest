"""One auth resolver, enforced by the route graph and by the HTTP boundary.

The first version of this file was a lint: it matched four literals across eleven hardcoded
module names. Verification defeated it with a dependency written in different spelling -
``request.headers.get('Authorization')``, ``.lower().startswith('bearer ')``, then
``db.get(Token, digest(raw))`` - and the lint reported nothing. A textual guard cannot hold
an invariant about *behaviour*.

Three layers now, in increasing strength:

1. **Route graph** (:func:`test_every_route_that_needs_a_principal_has_the_resolver`).
   Every ``APIRoute`` the app serves must have a resolver in its FastAPI dependency tree,
   unless it is in ``security.PUBLIC_ROUTES``. The check enumerates the app, not a list of
   filenames, so a newly added ``routes_*.py`` is covered the moment it is mounted.
2. **HTTP boundary** (the second test here). Any 2xx response to a request that carried a
   credential, from a route whose principal was never resolved, is replaced with 401 before
   it leaves the app. This does not care how the alternative dependency spells the header.
3. **Per-family behaviour** (the last test). A deleted account's token gets 401 from one
   endpoint of every route family, after a real snapshot restore, and the row is re-erased.
"""
import sqlite3
from pathlib import Path

import pytest
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.database_backup import create_sqlite_backup, restore_sqlite_backup, sqlite_path_from_engine
from app.db import Flashcard, Token
from app.main import create_app
from app.security import (PUBLIC_ROUTES, digest, require_principal,
                          routes_without_principal)

PASSWORD = 'long-secret-password'


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


def account(client, label='one'):
    response = client.post('/api/v1/auth/register', json={
        'name': label, 'email': f'{label}@example.test', 'password': PASSWORD})
    assert response.status_code == 201, response.text
    value = response.json()
    return {'Authorization': 'Bearer ' + value['token']}, value


def db_path(settings) -> Path:
    return Path(settings.data_dir) / 'harness.sqlite3'


def user_rows(settings, user_id: str) -> int:
    with sqlite3.connect(str(db_path(settings))) as connection:
        return connection.execute('SELECT count(*) FROM users WHERE id = ?', (user_id,)).fetchone()[0]


# ---------------------------------------------------------------- 1. the route graph


def test_every_route_that_needs_a_principal_has_the_resolver(app):
    """The app's own route table is the list; there is no hardcoded module list.

    A route whose dependency tree lacks ``security.require_principal`` (or any other
    callable marked ``_resolves_principal``) fails here, whether it lives in an existing
    module, a new ``routes_*.py``, or a router mounted by a feature flag.
    """
    unresolved = routes_without_principal(app, PUBLIC_ROUTES)
    assert unresolved == [], (
        'these routes can answer without the resolver having run; add '
        'Depends(security.require_principal(...)) to the router or to the route:\n  '
        + '\n  '.join(unresolved))


def test_public_routes_are_an_exact_and_reviewed_list(app):
    """Any route without a resolver must be declared public — no accidental expansion.

    The equality is the point: a new anonymous route appears on the left and fails the
    test until somebody adds it to ``PUBLIC_ROUTES`` deliberately. Combined with the test
    above, the public surface can only grow by an explicit edit.
    """
    without = set(routes_without_principal(app, set()))
    declared = {f'{method} {path}' for method, path in PUBLIC_ROUTES}
    assert without == declared, {
        'undeclared_public': sorted(without - declared),
        'declared_but_has_a_resolver': sorted(declared - without),
    }


# --------------------------------------------------------------- 2. the boundary


def _alt_router() -> APIRouter:
    """The alternative dependency verification wrote: right behaviour, different spelling.

    It reads ``Authorization`` with a capital A, lower-cases before comparing, splits the
    header itself, and looks the token up without going through ``resolve_account``. A
    textual guard cannot see it; the route graph can (no resolver in the chain) and the
    boundary can (the response never had a resolved principal).
    """
    router = APIRouter()

    @router.get('/api/v1/v3-alt')
    def alt_cards(request: Request):
        header = request.headers.get('Authorization', '')
        if not header.lower().startswith('bearer '):
            raise HTTPException(401, 'token required')
        raw = header.split(' ', 1)[1]
        with request.app.state.factory() as db:
            token = db.get(Token, digest(raw))
            if not token:
                raise HTTPException(401, 'bad token')
            rows = db.scalars(select(Flashcard).where(Flashcard.user_id == token.user_id)).all()
            return {'cards': [{'front': row.front} for row in rows]}

    return router


def _query_router() -> APIRouter:
    """A route that reads the token from ``?t=`` - no header, so a header-only boundary is blind."""
    router = APIRouter()

    @router.get('/api/v1/v3-query')
    def query_cards(request: Request, t: str = ''):
        with request.app.state.factory() as db:
            token = db.get(Token, digest(t))
            if not token:
                raise HTTPException(401, 'bad token')
            rows = db.scalars(select(Flashcard).where(Flashcard.user_id == token.user_id)).all()
            return {'cards': [{'front': row.front} for row in rows]}

    return router


def _good_router() -> APIRouter:
    """The same handler, wired the one supported way.

    The dependency goes on the router *before* the route is added: FastAPI copies the
    router's dependencies into each route at ``add_api_route`` time, which is why appending
    to ``router.dependencies`` afterwards would silently do nothing.
    """
    router = APIRouter(dependencies=[Depends(require_principal('api', 180))])

    @router.get('/api/v1/v3-good')
    def good_cards(request: Request):
        with request.app.state.factory() as db:
            rows = db.scalars(select(Flashcard).where(Flashcard.user_id == request.state.principal.id)).all()
            return {'cards': [{'front': row.front} for row in rows]}

    return router


def test_hand_rolled_dependency_is_refused_by_the_boundary(app, client, settings):
    """The bypass is reproduced, then refused - and the same handler wired correctly works.

    Assertions, in order: the route graph flags the alternative; a live account's token gets
    401 from it (so the route is inert, not merely unlucky about a deleted account); the
    card body is absent from the 401; and the identical handler behind the resolver returns
    the card, which is what proves the account and the fixture are real.
    """
    headers, value = account(client)
    with app.state.factory() as db:
        db.add(Flashcard(user_id=value['user']['id'], concept_id='fractions',
                         front='SECRET CARD', back='0.5', front_key='k1'))
        db.commit()

    # Mount the alternative *after* create_app, exactly as a new module would be mounted.
    app.include_router(_alt_router())
    app.include_router(_good_router())

    flagged = routes_without_principal(app, PUBLIC_ROUTES)
    assert 'GET /api/v1/v3-alt' in flagged, (
        'the route graph did not notice a hand-rolled dependency: ' + repr(flagged))
    assert 'GET /api/v1/v3-good' not in flagged

    refused = client.get('/api/v1/v3-alt', headers=headers)
    assert refused.status_code == 401, refused.text
    # The wording pins the *source* of the refusal: it came from the boundary, not from a
    # coincidence inside the hand-rolled route.
    assert refused.json()['detail'] == 'Account could not be verified', refused.text
    assert 'SECRET CARD' not in refused.text

    allowed = client.get('/api/v1/v3-good', headers=headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()['cards'][0]['front'] == 'SECRET CARD'


def test_lowercase_bearer_scheme_is_still_a_credential(app, client):
    """G1: HTTP auth schemes are case-insensitive, so ``bearer`` must be caught too.

    The hand-rolled route in this file lowercases before comparing, so it authenticates a
    lowercase request and would return the card. The boundary must recognise the credential
    regardless of case and refuse the response. A boundary that used
    ``startswith('Bearer ')`` would let exactly this through.
    """
    headers, value = account(client)
    with app.state.factory() as db:
        db.add(Flashcard(user_id=value['user']['id'], concept_id='fractions',
                         front='SECRET CARD', back='0.5', front_key='k1'))
        db.commit()
    app.include_router(_alt_router())

    lower = {'Authorization': 'bearer ' + headers['Authorization'].split(' ', 1)[1]}
    refused = client.get('/api/v1/v3-alt', headers=lower)
    assert refused.status_code == 401, refused.text
    assert refused.json()['detail'] == 'Account could not be verified'
    assert 'SECRET CARD' not in refused.text

    # The supported path accepts the same lowercase request: this is a case-insensitivity
    # fix, not a second auth scheme.
    assert client.get('/api/v1/me', headers=lower).status_code == 200


def test_query_credential_is_not_invisible_to_the_boundary(app, client):
    """G2: a token in ``?t=`` reaches a handler with no header, so the boundary must count it.

    The route graph flags this route (it runs only in CI); the boundary is what refuses the
    response in production, and it has to look at the query string to do that.
    """
    headers, value = account(client)
    token = headers['Authorization'].split(' ', 1)[1]
    with app.state.factory() as db:
        db.add(Flashcard(user_id=value['user']['id'], concept_id='fractions',
                         front='SECRET CARD', back='0.5', front_key='k1'))
        db.commit()
    app.include_router(_query_router())

    assert 'GET /api/v1/v3-query' in routes_without_principal(app, PUBLIC_ROUTES)

    refused = client.get('/api/v1/v3-query', params={'t': token})
    assert refused.status_code == 401, refused.text
    assert refused.json()['detail'] == 'Account could not be verified'
    assert 'SECRET CARD' not in refused.text


def test_websocket_route_is_enumerated_by_the_graph_guard(app):
    """G3: ``WebSocketRoute`` is not an ``APIRoute``, so only this walk can see it.

    The HTTP boundary never sees a WebSocket handshake, so for a WebSocket route the graph
    guard is the only layer that exists. There are no WebSocket routes today; this proves
    the first one added is reported rather than silently inheriting the gap.
    """
    from fastapi import WebSocket

    @app.websocket('/api/v1/ws-alt')
    async def ws_alt(websocket: WebSocket):  # pragma: no cover - never connected in tests
        await websocket.accept()
        await websocket.close()

    flagged = routes_without_principal(app, PUBLIC_ROUTES)
    assert 'WS /api/v1/ws-alt' in flagged, flagged


def test_public_path_with_trailing_slash_is_not_refused_for_credentialed_probes(client):
    """G4: ``GET /health/`` with a token must not become a 401 for a monitoring probe."""
    headers, _ = account(client)
    for path in ('/health', '/health/'):
        response = client.get(path, headers=headers)
        assert response.status_code < 400, (path, response.status_code, response.text)


# --------------------------------------------- 3. one endpoint per family, after a restore

FAMILIES = [
    ('flashcards', 'GET', '/api/v1/flashcards', None),
    ('courses', 'GET', '/api/v1/my-courses', None),
    ('decks', 'GET', '/api/v1/deck', None),
    ('media-library', 'GET', '/api/v1/images/library', None),
    ('playground', 'GET', '/api/v1/playground', None),
    ('procedure', 'GET', '/api/v1/procedure', None),
    ('authoring', 'GET', '/api/v1/author/courses', None),
    ('supervision', 'GET', '/api/v1/supervision', None),
    ('capabilities', 'GET', '/api/v1/capabilities', None),
    ('web-sims', 'GET', '/api/v1/sims', None),
    ('optional-user', 'POST', '/api/v1/feedback',
     {'kind': 'bug', 'message': 'erased account should not reach this route'}),
]


def test_erased_account_is_refused_by_every_route_family(app, client, settings):
    """Each family gets its own snapshot+restore, because one 401 reaps the row for all."""
    headers, value = account(client)
    user_id = value['user']['id']
    snapshot = create_sqlite_backup(sqlite_path_from_engine(app.state.engine),
                                    backup_dir=Path(settings.data_dir) / 'backups',
                                    kind='manual')
    assert client.request('DELETE', '/api/v1/me', headers=headers,
                          json={'confirmation': 'DELETE MY ACCOUNT'}).status_code == 204

    failures = []
    for name, method, path, body in FAMILIES:
        app.state.engine.dispose()
        restore_sqlite_backup(snapshot['path'], db_path(settings),
                              backup_dir=Path(settings.data_dir) / 'backups',
                              lock_path=Path(settings.data_dir) / f'.restore-{name}.lock')
        assert user_rows(settings, user_id) == 1, f'{name}: the restore did not bring the row back'
        response = client.request(method, path, headers=headers, json=body)
        if response.status_code != 401:
            failures.append(f'{name} {method} {path} -> {response.status_code}')
        if user_rows(settings, user_id) != 0:
            failures.append(f'{name}: the row was not re-erased')

    assert failures == [], 'a restored, deleted account still reached these routes:\n  ' + \
        '\n  '.join(failures)
