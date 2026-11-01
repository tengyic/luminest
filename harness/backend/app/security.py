import hashlib
import hmac
import json
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import AuthToken, RateBucket, RefreshToken, Secret, Token, now_ts
from .user_scope import unscoped

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))

#: Access tokens are short by design; the refresh token carries the long session.
ACCESS_TTL_SECONDS = 3600
REFRESH_TTL_SECONDS = 60 * 60 * 24 * 60  # 60 days
VERIFY_TTL_SECONDS = 60 * 60 * 24 * 3     # 3 days
RESET_TTL_SECONDS = 60 * 60               # 1 hour


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def password_ok(password, encoded):
    try:
        return HASHER.verify(encoded or DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False


def issue_token(db, user, ttl):
    raw = secrets.token_urlsafe(40)
    db.add(Token(digest=digest(raw), user_id=user.id, expires_at=now_ts() + ttl))
    return raw


def new_secret(prefix=''):
    """A fresh credential and its stored digest. The raw value is returned once only."""
    raw = prefix + secrets.token_urlsafe(32)
    return raw, digest(raw)


def issue_session(db, user, *, access_ttl=ACCESS_TTL_SECONDS, refresh_ttl=REFRESH_TTL_SECONDS,
                  label=None, user_agent=None, ip=None):
    """Open a session: a short access token plus a long, single-use refresh token.

    Both rows share ``session_digest`` so the account can list and revoke one device
    without touching the others.
    """
    access_raw = secrets.token_urlsafe(40)
    session_digest = digest(access_raw)
    refresh_raw = secrets.token_urlsafe(48)
    now = now_ts()
    db.add(Token(digest=session_digest, user_id=user.id, expires_at=now + access_ttl,
                 # created_at is stamped from the same `now` as expires_at: the column default
                 # fires its own clock read at flush time, and a second independent read makes
                 # the exact invariant (expires_at == created_at + ttl) flaky at sub-ms scale.
                 created_at=now,
                 label=(label or '')[:60] or None,
                 user_agent_hash=digest(user_agent)[:64] if user_agent else None,
                 ip_hash=digest(ip)[:64] if ip else None, last_used_at=now))
    db.add(RefreshToken(digest=digest(refresh_raw), user_id=user.id,
                        session_digest=session_digest, expires_at=now + refresh_ttl))
    return access_raw, refresh_raw, session_digest


def rotate_refresh(db, raw_refresh, *, access_ttl=ACCESS_TTL_SECONDS, refresh_ttl=REFRESH_TTL_SECONDS):
    """Exchange a refresh token for a new access+refresh pair.

    Returns ``(access_raw, refresh_raw, session_digest, user_id)`` or ``None``. Reusing a
    token that was already rotated is treated as compromise: the whole session is revoked.
    """
    row = db.get(RefreshToken, digest(raw_refresh))
    if not row:
        return None
    if row.revoked_at is not None or row.expires_at <= now_ts():
        # A revoked token being presented again means someone kept a copy. Kill the session.
        _revoke_session(db, row.session_digest)
        return None
    access_raw = secrets.token_urlsafe(40)
    refresh_raw = secrets.token_urlsafe(48)
    now = now_ts()
    row.revoked_at = now
    row.last_used_at = now
    db.add(Token(digest=digest(access_raw), user_id=row.user_id, expires_at=now + access_ttl,
                 last_used_at=now))
    db.add(RefreshToken(digest=digest(refresh_raw), user_id=row.user_id,
                        session_digest=row.session_digest, expires_at=now + refresh_ttl,
                        rotated_from=row.digest))
    return access_raw, refresh_raw, row.session_digest, row.user_id


def _revoke_session(db, session_digest):
    # Keyed by session_digest, not user_id: this runs before (and independent of) any
    # user identity, and Token.digest *is* the session key. The AuthToken-style digest
    # lookups and this one are exactly what the audited user_scope.unscoped() hatch
    # exists for -- credential lookups by an unguessable digest.
    with unscoped('credential lookup by session digest'):
        for token in db.query(Token).filter(Token.digest == session_digest).all():
            token.revoked_at = now_ts()
        for refresh in db.query(RefreshToken).filter(RefreshToken.session_digest == session_digest).all():
            refresh.revoked_at = refresh.revoked_at or now_ts()


def revoke_session(db, session_digest):
    _revoke_session(db, session_digest)


def revoke_all_sessions(db, user_id):
    now = now_ts()
    db.query(Token).filter(Token.user_id == user_id, Token.revoked_at.is_(None)).update(
        {'revoked_at': now}, synchronize_session=False)
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).update(
        {'revoked_at': now}, synchronize_session=False)


def issue_auth_token(db, user, kind, ttl):
    """Mint a single-use email-verification or password-reset token. Supersedes prior ones."""
    db.query(AuthToken).filter(AuthToken.user_id == user.id, AuthToken.kind == kind,
                               AuthToken.used_at.is_(None)).update({'used_at': now_ts()},
                                                                   synchronize_session=False)
    raw, token_digest = new_secret()
    db.add(AuthToken(user_id=user.id, kind=kind, digest=token_digest, expires_at=now_ts() + ttl))
    return raw


def consume_auth_token(db, raw, kind):
    """Validate and burn a single-use token. Returns the row, or ``None``.

    Looked up by ``digest``, not by primary key: the row's id is a random uuid and the
    digest is a separate column, so a ``db.get`` on the digest would silently never match
    and every verification and reset link would be reported as invalid.
    """
    with unscoped('single-use credential lookup by digest'):
        row = db.scalar(select(AuthToken).where(AuthToken.digest == digest(raw)))
    if not row or row.kind != kind or row.used_at is not None or row.expires_at <= now_ts():
        return None
    row.used_at = now_ts()
    return row

def signing_secret(db, configured):
    if configured:
        return configured
    stmt = sqlite_insert(Secret) if db.bind.dialect.name == 'sqlite' else pg_insert(Secret)
    db.execute(stmt.values(name='receipt', value=secrets.token_urlsafe(48)).on_conflict_do_nothing(index_elements=['name']))
    db.commit()
    return db.get(Secret, 'receipt').value


def sign_receipt(receipt, key):
    value = json.dumps([receipt.id, receipt.user_id, receipt.question_id, receipt.mode,
                        receipt.assessment_id, receipt.issued_at, receipt.expires_at], separators=(',', ':'))
    signature = hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()
    return receipt.id + '.' + signature


def verify_receipt(raw, receipt, key):
    return hmac.compare_digest(raw, sign_receipt(receipt, key))


def rate_limit(factory, key, maximum=60, period=60):
    timestamp = int(time.time())
    start = timestamp // period * period
    hashed = digest(key)
    with factory() as db:
        insert = sqlite_insert(RateBucket) if db.bind.dialect.name == 'sqlite' else pg_insert(RateBucket)
        db.execute(insert.values(key=hashed, start=start, count=0).on_conflict_do_nothing(index_elements=['key']))
        row = db.scalar(select(RateBucket).where(RateBucket.key == hashed).with_for_update())
        if row.start != start:
            row.start, row.count = start, 0
        row.count += 1
        limited = row.count > maximum
        db.commit()
    if limited:
        raise HTTPException(429, 'Rate limit exceeded', headers={'Retry-After': str(period - timestamp % period)})
