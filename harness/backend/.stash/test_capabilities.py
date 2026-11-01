"""The capability matrix and its pay-to-enable surface.

Five things are proven here, in the order the brief names them: the fail-closed
default for an anonymous caller; tier resolution; that a granted capability is
visible and an ungranted one is refused with a reason; that a capability whose
provider is unconfigured degrades to its fallback instead of erroring; and the HTTP
surface, including the store-agnostic grant path and the adoption seam other routes
will use.
"""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import capabilities
from app.config import Settings
from app.db import QuotaPolicy, Token, User, UserPreference, make_database, now_ts
from app.main import create_app
from app.security import HASHER, issue_token
from sqlalchemy import select

#: The capabilities the matrix pays for, and the ones it does not. Pinned so a new
#: matrix row fails a test rather than silently changing what is sold.
PLUS_IDS = {'images', 'video', 'audio_tts', 'web_search', 'browser_snapshot',
            'course_creation', 'vision_understanding'}
FREE_IDS = {'simulations', 'whiteboard_rich', 'flashcards_auto', 'pptx_export'}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    monkeypatch.delenv('HARNESS_ENTITLEMENTS', raising=False)
    return Settings.from_env()


@pytest.fixture
def client(settings):
    # A context manager, not a bare constructor: the lifespan is what creates the
    # tables and seeds app.state.signing_secret, and without it every request here
    # would 500 on a missing table instead of testing anything.
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def media_off_client(tmp_path, monkeypatch):
    """An instance where the operator has switched network media off."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '0')
    with TestClient(create_app(Settings.from_env())) as client:
        yield client


def account(client, label='one'):
    response = client.post('/api/v1/auth/register',
                           json={'name': label, 'email': f'{label}@example.test',
                                 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def rows(payload):
    return {row['id']: row for row in payload['capabilities']}


# ----------------------------------------------------- fail closed and the tiers

def test_anonymous_caller_fails_closed_to_the_free_tier(settings):
    resolved = capabilities.resolve(None, settings)
    assert resolved['principal'] == {'authenticated': False, 'user_id': None,
                                     'tier': 'free'}
    matrix = rows(resolved)
    # Every paid row is withheld *with a reason*, for every unknown principal. The
    # reason is what the UI shows instead of silently downgrading. (vision_*
    # excluded: it is withheld for not existing, which the shape test pins.)
    for cap_id in PLUS_IDS - {'vision_understanding'}:
        entry = matrix[cap_id]
        assert entry['state'] == capabilities.STATE_WITHHELD
        assert entry['granted'] is False
        assert 'Sign in' in entry['reason']
    # Free rows are offered, not refused: offline and unauthenticated still works.
    for cap_id in FREE_IDS:
        assert matrix[cap_id]['state'] in {capabilities.STATE_ENABLED,
                                            capabilities.STATE_DEGRADED}


def test_matrix_shape_is_stable(settings):
    """The declared set of capabilities is part of the contract: a new row or a
    removed one is a product decision, so it fails here until someone makes it."""
    matrix = rows(capabilities.resolve(None, settings))
    assert set(matrix) == PLUS_IDS | FREE_IDS
    # Two tiers only. A tier the quota machinery cannot enforce would be a lie.
    assert capabilities.TIERS == ('free', 'plus')
    # The one gap is labelled missing, not dressed up as stubbed or implemented.
    assert matrix['vision_understanding']['status'] == capabilities.STATUS_MISSING
    for cap_id in (PLUS_IDS | FREE_IDS) - {'vision_understanding'}:
        assert matrix[cap_id]['status'] == capabilities.STATUS_IMPLEMENTED


def test_tier_resolution_for_a_signed_in_learner(client):
    headers = account(client)
    matrix = rows(client.get('/api/v1/capabilities', headers=headers).json())
    assert matrix['images']['state'] == capabilities.STATE_WITHHELD
    assert matrix['images']['reason'] == (
        'This capability is part of Luminfest Plus. Pay to enable it, or ask the '
        'operator to comp this account.')
    # ...and the paid plan is stated, so the client can show the metered ceiling.
    plan = client.get('/api/v1/capabilities', headers=headers).json()['paid_plan']
    assert plan == {'period': 'month', 'requests': 2000, 'total_tokens': 2_000_000,
                    'enforcement': 'soft', 'meter': plan['meter'], 'note': plan['note']}


def test_expired_entitlement_stops_resolving(settings, tmp_path, monkeypatch):
    """A lapsed subscription stops resolving immediately -- not at the next cron."""
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    engine, factory = make_database(settings)
    from app.db import Base
    Base.metadata.create_all(engine)
    with factory() as db:
        user = User(name='lapsed', email='lapsed@example.test',
                    password_hash=HASHER.hash('long-secret-password'))
        db.add(user)
        db.commit()
        ok, reason, record = capabilities.grant(
            db, user, 'images', settings=settings, key='test-key',
            receipt=capabilities.mint_receipt('images', key='test-key', ttl_days=1))
        assert ok, reason
        db.commit()
        # Resolve a day after expiry: same rows, now withheld, and the reason says so.
        resolved = capabilities.resolve(user, settings, db=db, now=now_ts() + 2 * 86400)
        entry = rows(resolved)['images']
        assert entry['state'] == capabilities.STATE_WITHHELD
        assert 'expired' in entry['reason']


# ----------------------------------------------------- granted, refused, revoked

def test_granted_capability_is_visible_and_writes_real_rows(client):
    headers = account(client)
    key = client.app.state.signing_secret
    receipt = capabilities.mint_receipt('images', key=key)

    granted = client.post('/api/v1/capabilities/images/grant', headers=headers,
                          json={'receipt': receipt})
    assert granted.status_code == 200, granted.text
    body = granted.json()
    assert body['capability'] == 'images' and body['granted'] is True
    # A real entitlement row and a real metered ceiling, not an in-memory flag.
    assert body['entitlement']['source'] == 'receipt'
    assert body['entitlement']['expires_at'] > now_ts()
    assert body['quota']['period'] == 'month' and body['quota']['enforcement'] == 'soft'

    entry = rows(client.get('/api/v1/capabilities', headers=headers).json())['images']
    assert entry['state'] == capabilities.STATE_ENABLED
    assert entry['granted'] is True


def test_grant_persists_the_entitlement_row(client):
    headers = account(client)
    key = client.app.state.signing_secret
    client.post('/api/v1/capabilities/video/grant', headers=headers,
                json={'receipt': capabilities.mint_receipt('video', key=key)})
    with client.app.state.factory() as db:
        user = db.scalar(select(User))
        prefs = db.get(UserPreference, user.id)
        stored = prefs.ui['capabilities']['video']
        assert stored['source'] == 'receipt'
        assert stored['expires_at'] > now_ts()
        # One paid ceiling, written once through the quota machinery.
        policies = db.scalars(select(QuotaPolicy).where(QuotaPolicy.scope == 'user',
                                                        QuotaPolicy.scope_id == user.id)).all()
        assert len(policies) == 1
        assert policies[0].request_limit == 2000


def test_ungranted_capability_is_refused_with_a_reason(client):
    headers = account(client)
    refused = client.post('/api/v1/capabilities/video/grant', headers=headers, json={})
    assert refused.status_code == 402
    body = refused.json()['detail']
    assert 'receipt' in body['reason']
    # The 402 names the seam instead of pretending a store exists.
    assert body['seam']['runbook'] == 'docs/pay-to-enable.md'
    assert 'mint_receipt' in body['seam']['app_store']
    # Nothing was written.
    assert rows(client.get('/api/v1/capabilities', headers=headers).json())['video']['granted'] is False


def test_receipt_cannot_be_replayed_across_capabilities(client):
    headers = account(client)
    key = client.app.state.signing_secret
    video_receipt = capabilities.mint_receipt('video', key=key)
    refused = client.post('/api/v1/capabilities/images/grant', headers=headers,
                          json={'receipt': video_receipt})
    assert refused.status_code == 402
    assert 'different capability' in refused.json()['detail']['reason']


def test_tampered_and_expired_receipts_are_refused(client):
    headers = account(client)
    key = client.app.state.signing_secret
    good = capabilities.mint_receipt('web_search', key=key)
    tampered = good[:-1] + ('0' if good[-1] != '0' else '1')
    refused = client.post('/api/v1/capabilities/web_search/grant', headers=headers,
                          json={'receipt': tampered})
    assert refused.status_code == 402
    assert 'signature does not verify' in refused.json()['detail']['reason']

    expired = capabilities.mint_receipt('web_search', key=key, ttl_days=-1)
    refused = client.post('/api/v1/capabilities/web_search/grant', headers=headers,
                          json={'receipt': expired})
    assert refused.status_code == 402
    assert 'expired' in refused.json()['detail']['reason']


def test_operator_comp_grants_without_any_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    monkeypatch.setenv('HARNESS_ENTITLEMENTS', '*:images,staff@example.test:video')
    with TestClient(create_app(Settings.from_env())) as client:
        headers = account(client, 'comped')
        granted = client.post('/api/v1/capabilities/images/grant', headers=headers,
                              json={})
        assert granted.status_code == 200, granted.text
        assert granted.json()['entitlement']['source'] == 'operator'
        # A comp is not a subscription: it does not silently lapse in a month.
        assert granted.json()['entitlement']['expires_at'] > now_ts() + 300 * 86400
        # Not comped for this one, though the wildcard covered images.
        assert client.post('/api/v1/capabilities/video/grant', headers=headers,
                           json={}).status_code == 402


def test_revoke_removes_the_entitlement(client):
    headers = account(client)
    key = client.app.state.signing_secret
    client.post('/api/v1/capabilities/audio_tts/grant', headers=headers,
                json={'receipt': capabilities.mint_receipt('audio_tts', key=key)})
    assert rows(client.get('/api/v1/capabilities', headers=headers).json())['audio_tts']['granted']
    revoked = client.delete('/api/v1/capabilities/audio_tts/grant', headers=headers)
    assert revoked.status_code == 200 and revoked.json()['revoked'] is True
    entry = rows(client.get('/api/v1/capabilities', headers=headers).json())['audio_tts']
    assert entry['granted'] is False and entry['state'] == capabilities.STATE_WITHHELD


# ----------------------------------------------------- degraded, never an error

def test_ungranted_beats_degraded_in_the_reason(client):
    """Precedence matters for the UI: a learner who has not paid is told to pay, not
    told the provider is off -- the two are different actions. audio_tts is the
    honest probe case: its package is absent in this environment, and an anonymous
    caller must still see the payment reason, not the package reason."""
    matrix = rows(client.get('/api/v1/capabilities').json())
    entry = matrix['audio_tts']
    assert entry['provider_ready'] is False
    assert entry['state'] == capabilities.STATE_WITHHELD
    assert 'Sign in' in entry['reason']


def test_entitled_capability_degrades_when_the_provider_is_off(media_off_client):
    """The operator switch is off, so the paid capability must fall back with a
    reason -- not error, and not pretend."""
    headers = account(media_off_client)
    key = media_off_client.app.state.signing_secret
    granted = media_off_client.post(
        '/api/v1/capabilities/images/grant', headers=headers,
        json={'receipt': capabilities.mint_receipt('images', key=key)})
    assert granted.status_code == 200, granted.text

    detail = media_off_client.get('/api/v1/capabilities/images', headers=headers).json()
    entry = detail['capability']
    assert entry['granted'] is True
    assert entry['state'] == capabilities.STATE_DEGRADED
    assert entry['provider_ready'] is False
    assert 'HARNESS_MEDIA_ENABLED' in entry['reason']
    assert entry['fallback'] in entry['reason']


def test_absent_package_degrades_the_speech_capability(client):
    """edge-tts is not installed in this environment, so an entitled audio_tts must
    report degraded -- the tool refuses honestly rather than synthesising audio."""
    headers = account(client)
    key = client.app.state.signing_secret
    client.post('/api/v1/capabilities/audio_tts/grant', headers=headers,
                json={'receipt': capabilities.mint_receipt('audio_tts', key=key)})
    entry = rows(client.get('/api/v1/capabilities', headers=headers).json())['audio_tts']
    assert entry['state'] == capabilities.STATE_DEGRADED
    assert 'edge-tts' in entry['provider_note']
    assert entry['fallback'] in entry['reason']


def test_local_capabilities_never_degrade(settings):
    """A capability with no external provider is enabled even with everything off."""
    resolved = capabilities.resolve(None, settings)
    matrix = rows(resolved)
    for cap_id in FREE_IDS - {'pptx_export'}:  # pptx depends on a local package only
        entry = matrix[cap_id]
        assert entry['state'] == capabilities.STATE_ENABLED
        assert entry['provider_ready'] is True


def test_resolver_never_raises_on_a_probe_failure(settings):
    """A probe bug must not take the API down: the whole request degrades instead."""
    def exploding(settings):
        raise RuntimeError('probe exploded')
    original = capabilities.PROBES['media_network']
    capabilities.PROBES['media_network'] = exploding
    try:
        resolved = capabilities.resolve(None, settings)
    finally:
        capabilities.PROBES['media_network'] = original
    entry = rows(resolved)['images']
    assert entry['state'] == capabilities.STATE_WITHHELD  # anonymous outranks the probe
    assert entry['provider_ready'] is False


# ----------------------------------------------------- the HTTP surface

def test_http_surface_shape(client):
    anonymous = client.get('/api/v1/capabilities')
    assert anonymous.status_code == 200
    payload = anonymous.json()
    assert set(payload) == {'tiers', 'principal', 'paid_plan', 'capabilities', 'note'}
    assert len(payload['capabilities']) == len(PLUS_IDS | FREE_IDS)
    # Every row carries what a storefront needs, before any tap.
    for entry in payload['capabilities']:
        assert set(entry) >= {'id', 'title', 'tier', 'provider', 'knob', 'fallback',
                              'status', 'state', 'reason', 'granted', 'provider_ready',
                              'price'}

    detail = client.get('/api/v1/capabilities/images')
    assert detail.status_code == 200
    assert detail.json()['capability']['id'] == 'images'
    assert detail.json()['receipt_ttl_days'] == capabilities.RECEIPT_TTL_DAYS

    assert client.get('/api/v1/capabilities/no_such_thing').status_code == 404


def test_grant_requires_authentication(client):
    assert client.post('/api/v1/capabilities/images/grant', json={}).status_code == 401
    assert client.delete('/api/v1/capabilities/images/grant').status_code == 401
    # A read is anonymous by design, so the storefront renders before signup.
    assert client.get('/api/v1/capabilities').status_code == 200


def test_broken_token_on_a_read_is_not_silently_anonymous(client):
    headers = account(client)
    with client.app.state.factory() as db:
        # A predicate, not a bare select: the user_scope guard rejects an unscoped
        # read of the tokens table, and this test is about auth, not the guard.
        tokens = db.scalars(select(Token).where(Token.user_id == db.scalar(select(User.id))))
        for token in tokens:
            token.revoked_at = now_ts()
        db.commit()
    assert client.get('/api/v1/capabilities', headers=headers).status_code == 401


def test_free_capability_grant_is_an_idempotent_noop(client):
    headers = account(client)
    granted = client.post('/api/v1/capabilities/simulations/grant', headers=headers,
                          json={})
    assert granted.status_code == 200
    assert granted.json()['granted'] is True
    # Nothing was written: a free capability has no entitlement row to write, so the
    # preferences row is either absent or carries no capabilities key at all.
    with client.app.state.factory() as db:
        prefs = db.get(UserPreference, db.scalar(select(User.id)))
        assert prefs is None or not (prefs.ui or {}).get('capabilities')


def test_missing_capability_cannot_be_granted(client):
    headers = account(client)
    refused = client.post('/api/v1/capabilities/vision_understanding/grant',
                          headers=headers, json={})
    assert refused.status_code == 409
    assert 'not implemented' in refused.json()['detail']


def test_the_adoption_seam_other_routes_will_use(settings, tmp_path):
    """``require_capability`` is the one-line adoption path for the existing routes.
    Proven here on a minimal app so the seam is shown to work, not merely described.
    """
    from app.db import Base
    engine, factory = make_database(settings)
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.settings, app.state.factory = settings, factory

    @app.get('/gated')
    def gated(capability=Depends(capabilities.require_capability('images'))):
        return {'ok': True, 'capability': capability['id']}

    with factory() as db:
        user = User(name='gated', email='gated@example.test',
                    password_hash=HASHER.hash('long-secret-password'))
        db.add(user)
        db.commit()
        raw = issue_token(db, user, 3600)
        db.commit()  # the token row must exist before the request reads it back
    headers = {'Authorization': 'Bearer ' + raw}

    with TestClient(app) as client:
        # Not entitled: 402 carrying the matrix's own reason.
        refused = client.get('/gated', headers=headers)
        assert refused.status_code == 402
        assert 'Luminfest Plus' in refused.json()['detail']
        assert client.get('/gated').status_code == 401  # anonymous is not a downgrade

        with factory() as db:
            ok, reason, _ = capabilities.grant(
                db, db.get(User, user.id), 'images', settings=settings,
                key='test-key',
                receipt=capabilities.mint_receipt('images', key='test-key'))
            assert ok, reason
            db.commit()
        assert client.get('/gated', headers=headers).json() == {'ok': True,
                                                                'capability': 'images'}


def test_require_capability_refuses_a_degraded_provider(tmp_path, monkeypatch):
    """Entitled but the operator switch is off: 503, because the fallback lives on a
    different route and this one genuinely cannot serve.

    ``Settings`` is a frozen dataclass, so the switch is flipped through the
    environment and a fresh ``Settings.from_env()`` rather than by patching the
    instance the app already holds.
    """
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '0')
    settings = Settings.from_env()
    from app.db import Base
    engine, factory = make_database(settings)
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.settings, app.state.factory = settings, factory

    @app.get('/gated')
    def gated(capability=Depends(capabilities.require_capability('images'))):
        return {'ok': True}

    with factory() as db:
        user = User(name='degraded', email='degraded@example.test',
                    password_hash=HASHER.hash('long-secret-password'))
        db.add(user)
        db.commit()
        ok, reason, _ = capabilities.grant(
            db, user, 'images', settings=settings, key='test-key',
            receipt=capabilities.mint_receipt('images', key='test-key'))
        assert ok, reason
        db.commit()
        raw = issue_token(db, user, 3600)
        db.commit()  # the token row must exist before the request reads it back
    headers = {'Authorization': 'Bearer ' + raw}

    with TestClient(app) as client:
        refused = client.get('/gated', headers=headers)
        assert refused.status_code == 503
        assert 'HARNESS_MEDIA_ENABLED' in refused.json()['detail']
