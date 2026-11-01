"""Tests for the hosted-Beta account lifecycle.

Covers the four things a single-user local app never needed and a hosted Beta cannot ship
without: a waitlist that cannot be spammed or forged, invite codes that admit exactly the
people they were issued to, a session that can be refreshed and revoked per device, and an
email/password recovery flow that does not leak which addresses exist.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db import AuthToken, BetaInvite, Cohort, Feedback, RefreshToken, Token, User, now_ts
from app.main import create_app

PASSWORD = 'a-long-enough-password'


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def register(client, email=None, invite=None, **extra):
    payload = {'name': 'Learner', 'email': email or f'{uuid4().hex[:8]}@example.test',
               'password': PASSWORD, **extra}
    if invite:
        payload['invite_code'] = invite
    return client.post('/api/v1/auth/register', json=payload)


def auth(client, email=None):
    response = register(client, email)
    assert response.status_code == 201, response.text
    body = response.json()
    return {'Authorization': 'Bearer ' + body['token']}, body


def make_admin(client, email='admin@example.test'):
    headers, body = auth(client, email)
    with client.app.state.factory() as db:
        user = db.get(User, body['user']['id'])
        user.role = 'admin'
        db.commit()
    return headers


# ------------------------------------------------------------------ waitlist

def test_waitlist_is_idempotent_and_holds_position(client):
    first = client.post('/api/v1/waitlist', json={'email': 'Queue@Example.test', 'name': 'Q'})
    assert first.status_code == 201, first.text
    position = first.json()['position']
    assert first.json()['confirmed'] is False

    # Signing up again must not create a second row or move the person backwards.
    again = client.post('/api/v1/waitlist', json={'email': 'queue@example.test'})
    assert again.status_code == 201
    assert again.json()['position'] == position
    with client.app.state.factory() as db:
        assert len(db.scalars(select(User).where(User.email == 'queue@example.test')).all()) == 0


def test_waitlist_confirmation_requires_the_emailed_token(client):
    client.post('/api/v1/waitlist', json={'email': 'confirm@example.test'})
    assert client.post('/api/v1/waitlist/confirm', json={'token': 'not-a-real-token-value'}).status_code == 400
    # The mailer is offline in tests, so the real link is in its outbox.
    sent = client.app.state.mailer.outbox[-1]
    token = sent['body'].split('token=')[1].split()[0]
    confirmed = client.post('/api/v1/waitlist/confirm', json={'token': token})
    assert confirmed.status_code == 200 and confirmed.json()['confirmed'] is True
    # Single use.
    assert client.post('/api/v1/waitlist/confirm', json={'token': token}).status_code == 400


# ------------------------------------------------------------------ invites

def test_invite_gate_admits_only_the_addressed_email(client, monkeypatch):
    admin = make_admin(client)
    created = client.post('/api/v1/admin/invites', headers=admin,
                          json={'email': 'invited@example.test', 'max_uses': 1})
    assert created.status_code == 201, created.text
    code = created.json()['invites'][0]['code']

    # A different address is refused, even holding a valid code.
    assert register(client, 'someone-else@example.test', invite=code).status_code == 403
    # The addressed address is admitted.
    ok = register(client, 'invited@example.test', invite=code)
    assert ok.status_code == 201, ok.text
    # And the code is now exhausted.
    assert register(client, 'late@example.test', invite=code).status_code == 403


def test_invite_required_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_REQUIRE_INVITE', '1')
    with TestClient(create_app(Settings.from_env())) as gated:
        assert register(gated, 'nobody@example.test').status_code == 403


def test_invite_carries_a_cohort(client):
    admin = make_admin(client)
    cohort = client.post('/api/v1/admin/cohorts', headers=admin,
                         json={'name': 'Wave 1', 'rollout_stage': 'closed_beta'})
    assert cohort.status_code == 201, cohort.text
    cohort_id = cohort.json()['id']
    created = client.post('/api/v1/admin/invites', headers=admin,
                          json={'cohort_id': cohort_id, 'max_uses': 5})
    code = created.json()['invites'][0]['code']
    joined = register(client, 'cohort-member@example.test', invite=code)
    assert joined.status_code == 201
    assert joined.json()['user']['cohort_id'] == cohort_id


def test_admin_surface_rejects_a_learner(client):
    headers, _ = auth(client)
    assert client.get('/api/v1/admin/waitlist', headers=headers).status_code == 403
    assert client.post('/api/v1/admin/invites', headers=headers, json={}).status_code == 403


# ------------------------------------------------------------------ sessions

def test_refresh_rotates_and_reuse_is_treated_as_theft(client):
    _, body = auth(client)
    refreshed = client.post('/api/v1/auth/refresh', json={'refresh_token': body['refresh_token']})
    assert refreshed.status_code == 200, refreshed.text
    new_access = refreshed.json()['token']
    assert refreshed.json()['refresh_token'] != body['refresh_token']

    # The new access token works.
    assert client.get('/api/v1/me', headers={'Authorization': 'Bearer ' + new_access}).status_code == 200
    # Replaying the *old* refresh token is refused and kills the session it belonged to.
    assert client.post('/api/v1/auth/refresh', json={'refresh_token': body['refresh_token']}).status_code == 401


def test_sessions_can_be_listed_and_revoked_per_device(client):
    headers, body = auth(client)
    sessions = client.get('/api/v1/auth/sessions', headers=headers)
    assert sessions.status_code == 200
    assert len(sessions.json()['sessions']) == 1
    assert sessions.json()['sessions'][0]['current'] is True

    # A second device.
    login = client.post('/api/v1/auth/login', json={'email': body['user']['email'], 'password': PASSWORD})
    second = {'Authorization': 'Bearer ' + login.json()['token']}
    assert len(client.get('/api/v1/auth/sessions', headers=headers).json()['sessions']) == 2

    other = [s for s in client.get('/api/v1/auth/sessions', headers=headers).json()['sessions']
             if not s['current']][0]
    assert client.delete(f"/api/v1/auth/sessions/{other['id']}", headers=headers).status_code == 204
    assert client.get('/api/v1/me', headers=second).status_code == 401

    assert client.post('/api/v1/auth/logout-all', headers=headers).json()['revoked'] is True
    assert client.get('/api/v1/me', headers=headers).status_code == 401


def test_a_revoked_access_token_stops_working_immediately(client):
    headers, _ = auth(client)
    assert client.get('/api/v1/me', headers=headers).status_code == 200
    assert client.post('/api/v1/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/v1/me', headers=headers).status_code == 401


# ------------------------------------------------------------------ email & password

def test_email_verification_flow(client):
    headers, body = auth(client)
    assert body['user']['email_verified'] is False
    resent = client.post('/api/v1/auth/resend-verification', headers=headers)
    assert resent.status_code == 200, resent.text
    assert resent.json()['sent'] is True
    token = client.app.state.mailer.outbox[-1]['body'].split('token=')[1].split()[0]
    verified = client.post('/api/v1/auth/verify-email', headers=headers, json={'token': token})
    assert verified.status_code == 200 and verified.json()['email_verified'] is True
    assert client.post('/api/v1/auth/verify-email', headers=headers, json={'token': token}).status_code == 400


def test_password_reset_is_single_use_and_ends_other_sessions(client):
    headers, body = auth(client, 'reset@example.test')
    assert client.post('/api/v1/auth/forgot-password', json={'email': 'reset@example.test'}).json()['sent'] is True
    token = client.app.state.mailer.outbox[-1]['body'].split('token=')[1].split()[0]

    reset = client.post('/api/v1/auth/reset-password', json={'token': token, 'password': 'brand-new-password'})
    assert reset.status_code == 200, reset.text
    # The old session is gone; the reset response carries a working one.
    assert client.get('/api/v1/me', headers=headers).status_code == 401
    assert client.get('/api/v1/me',
                      headers={'Authorization': 'Bearer ' + reset.json()['token']}).status_code == 200
    # The old password no longer works, the new one does.
    assert client.post('/api/v1/auth/login', json={'email': 'reset@example.test', 'password': PASSWORD}).status_code == 401
    assert client.post('/api/v1/auth/login', json={'email': 'reset@example.test', 'password': 'brand-new-password'}).status_code == 200
    # A reset link is single use.
    assert client.post('/api/v1/auth/reset-password', json={'token': token, 'password': 'another-password'}).status_code == 400


def test_forgot_password_does_not_reveal_whether_an_account_exists(client):
    known = client.post('/api/v1/auth/forgot-password', json={'email': 'ghost@example.test'})
    assert known.status_code == 200 and known.json()['sent'] is True
    # Nothing was actually sent for an address with no account.
    assert client.app.state.mailer.outbox == []


# ------------------------------------------------------------------ usage, preferences, feedback

def test_usage_reports_observation_not_enforcement(client):
    headers, _ = auth(client)
    body = client.get('/api/v1/usage', headers=headers).json()
    assert body['used']['requests'] == 0
    assert body['limits'] is None  # no policy configured for a fresh account
    assert 'without blocking' in body['note']


def test_preferences_round_trip(client):
    headers, _ = auth(client)
    assert client.get('/api/v1/preferences', headers=headers).json()['theme'] == 'system'
    patched = client.patch('/api/v1/preferences', headers=headers, json={'theme': 'dark'})
    assert patched.status_code == 200 and patched.json()['theme'] == 'dark'
    assert client.patch('/api/v1/preferences', headers=headers, json={'theme': 'chartreuse'}).status_code == 422


def test_feedback_works_signed_out_and_is_idempotent_when_signed_in(client):
    anon = client.post('/api/v1/feedback', json={'kind': 'bug', 'message': 'The map did not load.'})
    assert anon.status_code == 201, anon.text

    headers, _ = auth(client)
    event = str(uuid4())
    first = client.post('/api/v1/feedback', headers=headers,
                        json={'kind': 'idea', 'message': 'Add keyboard-only mode.', 'client_event_id': event})
    second = client.post('/api/v1/feedback', headers=headers,
                         json={'kind': 'idea', 'message': 'Add keyboard-only mode.', 'client_event_id': event})
    assert first.status_code == 201 and first.json()['id'] == second.json()['id']
    assert len(client.get('/api/v1/feedback', headers=headers).json()['feedback']) == 1


# ------------------------------------------------------------------ legal

def test_legal_documents_are_served(client):
    index = client.get('/api/v1/legal').json()
    slugs = {doc['slug'] for doc in index['documents']}
    assert {'terms', 'privacy', 'ai', 'accessibility'} <= slugs
    for slug in slugs:
        assert client.get(f'/api/v1/legal/{slug}').status_code == 200
    assert client.get('/api/v1/legal/not-a-document').status_code == 404
