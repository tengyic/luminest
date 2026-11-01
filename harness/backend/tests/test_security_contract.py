"""Token lifetime contract (audit finding E-2).

The audit found the two access-token defaults disagreed: ``config.Settings`` shipped
604800 s (seven days) while ``security.ACCESS_TTL_SECONDS`` was 3600 s. A week-long
bearer token in a hosted Beta is exactly what the single-use refresh-token rotation
exists to avoid: the long-lived half of a session belongs in the refresh token,
which is stored hashed, rotated on every use, and revoked wholesale on reuse.

Policy: the access token lives **one hour** by default; both default sites must
agree, and a produced access token must actually expire at the configured TTL.
"""
import os

from sqlalchemy import select

from app.config import Settings
from app.db import Token, User, now_ts
from app.security import ACCESS_TTL_SECONDS, REFRESH_TTL_SECONDS, issue_session
from test_api import client, settings  # noqa: F401


def test_default_access_ttl_sites_agree():
    assert Settings.access_token_ttl == ACCESS_TTL_SECONDS, (
        'config.Settings and security.ACCESS_TTL_SECONDS are the two default sites for '
        'the access token lifetime; the audit (E-2) found them disagreeing (7 days vs 1 hour)')
    assert ACCESS_TTL_SECONDS == 3600
    assert Settings.refresh_token_ttl == 5184000  # 60 days


def test_from_env_default_matches_the_dataclass_default():
    for name in [key for key in os.environ if key.startswith('HARNESS_')]:
        os.environ.pop(name, None)
    assert Settings.from_env().access_token_ttl == ACCESS_TTL_SECONDS


def test_issued_access_token_expires_at_the_configured_ttl(client, settings):
    response = client.post('/api/v1/auth/register', json={
        'name': 'ttl', 'email': 'ttl@example.test', 'password': 'long-secret-password'})
    assert response.status_code == 201
    with client.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == 'ttl@example.test'))
        before = now_ts()
        access, refresh, session_digest = issue_session(
            db, user, access_ttl=settings.access_token_ttl,
            refresh_ttl=settings.refresh_token_ttl)
        db.commit()
        row = db.get(Token, session_digest)
        assert row is not None
        assert row.expires_at == row.created_at + settings.access_token_ttl
        assert row.expires_at - before <= settings.access_token_ttl + 1
        assert settings.refresh_token_ttl > settings.access_token_ttl


def test_refresh_token_is_the_long_half(settings):
    assert settings.refresh_token_ttl >= 60 * 86400
    assert REFRESH_TTL_SECONDS == 60 * 60 * 24 * 60
    assert settings.refresh_token_ttl > settings.access_token_ttl
