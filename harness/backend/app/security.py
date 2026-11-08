import hashlib
import hmac
import json
import logging
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import AuthToken, RateBucket, RefreshToken, Secret, Token, User, now_ts
from .user_scope import unscoped

log = logging.getLogger('luminfest.security')

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


# --------------------------------------------------------------------- account resolution
#
# One resolver, called by every route module. Twelve modules used to carry their own copy
# of the bearer parsing, each documented as "line-for-line identical to
# main.authenticated"; they had forked, and none of them asked the erasure ledger, so a
# deleted account's still-valid token kept returning its flashcards, decks and courses from
# whichever module had the copy. A second copy is not a style problem here - it is an
# authorisation bypass - so ``tests/test_account_auth_single_source.py`` fails if one
# reappears outside this file.


#: Query parameter names a client might carry a credential in. The HTTP boundary treats
#: any of them as a credential, because a credential that does not arrive in the header is
#: otherwise invisible to it (verification mounted a `?t=` route and got the card body).
CREDENTIAL_QUERY_KEYS = ('t', 'token', 'access_token')


def _bearer_value(request) -> str | None:
    """The credential from the ``Authorization`` header, or ``None``.

    The scheme is compared case-insensitively: RFC 7235 defines it as case-insensitive, so
    ``bearer <tok>`` is a valid request from a compliant client. Comparing with
    ``startswith('Bearer ')`` rejected those clients *and* - the reason this matters - made
    the boundary skip its check for them, because the boundary used the same comparison.
    """
    header = request.headers.get('authorization', '')
    if not header or len(header) > 200:
        return None
    scheme, _, value = header.partition(' ')
    if scheme.lower() != 'bearer':
        return None
    value = value.strip()
    return value or None


def bearer_raw(request) -> str:
    """The raw bearer credential, or 401. The only place the header is parsed."""
    value = _bearer_value(request)
    if value is None:
        raise HTTPException(401, 'Valid bearer token required',
                            headers={'WWW-Authenticate': 'Bearer'})
    return value


def has_bearer(request) -> bool:
    """Whether the request carries a credential in the header at all."""
    return _bearer_value(request) is not None


def credential_present(request) -> bool:
    """Whether the request carries a credential anywhere the app might read it.

    The HTTP boundary uses this to decide whether a 2xx response needed a resolved
    principal. It covers the ``Authorization`` header **and** the query-string names a
    client could pass a token in; a route that reads ``?token=`` and answers without the
    resolver is otherwise invisible to the boundary, which is exactly the hole verification
    found.
    """
    if _bearer_value(request) is not None:
        return True
    return any(request.query_params.get(key) for key in CREDENTIAL_QUERY_KEYS)


def refuse_if_erased(db, user, settings) -> bool:
    """Whether the erasure ledger condemns this account; finishes the delete when it does.

    The token path and the credential path ask the same question, so they ask it here:
    ``resolve_account`` for a bearer token, and the login / refresh / reset routes for a
    password or a refresh token, which mint a session before any token is checked.

    An unreadable ledger is not "no erasures": it is a 503 that refuses the credential.
    """
    from . import account_erasure

    if user is None or settings is None:
        return False
    try:
        condemned = account_erasure.is_erased(settings, str(user.id))
    except account_erasure.ErasureLedgerUnreadable as exc:
        log.error('erasure ledger unreadable; refusing credentials: %s', exc)
        raise HTTPException(
            503, 'Account deletion records cannot be read; sign-in is refused') from exc
    if not condemned:
        return False
    account_erasure.purge_stale(db, settings, str(user.id))
    return True


def _live_user(db, user_id: str, settings):
    """The account, or 401. An erased account is purged and refused, never returned.

    The erasure ledger lives outside the database (``app/account_erasure.py``), so a
    restored snapshot can put the row back. This is the one place every route asks, which
    is why the check cannot be forgotten by a new module.
    """
    user = db.get(User, user_id)
    if refuse_if_erased(db, user, settings):
        raise HTTPException(401, 'Account unavailable')
    if not user or getattr(user, 'status', 'active') != 'active':
        raise HTTPException(401, 'Account unavailable')
    return user


def resolve_account(request, db, *, rate_key: str = 'api', limit: int = 180) -> User:
    """Resolve the signed-in account for a request, or raise the same 401 everywhere.

    Every route module calls this instead of parsing the header itself. It performs the
    one bearer check, the rate limit under the caller's key, the token lookup, the status
    check and - the part the twelve forked copies were missing - the erasure check. The
    resolved token is left on ``request.state`` for the caller that needs its digest
    (``main.authenticated`` writes the session heartbeat through it).

    ``rate_key`` and ``limit`` exist because the route families had set their own ceilings
    (180 for the API, 900 for the playground, 120 for media). They are the only thing that
    legitimately differed between the copies.

    Every call marks ``request.state.principal_resolved``; the HTTP boundary refuses any
    2xx response to a request that carried a credential and never reached this function.
    That is what makes the resolver structural rather than a convention: an alternative
    dependency written with different spelling still produces a response, and the boundary
    throws it away.
    """
    request.state.principal_resolved = True
    cached = getattr(request.state, 'principal', _UNSET)
    if cached is not _UNSET:
        if cached is None:
            # An optional resolver already established that this request is anonymous;
            # a route that demands a principal must not accept that answer.
            raise HTTPException(401, 'Valid bearer token required',
                                headers={'WWW-Authenticate': 'Bearer'})
        return cached
    factory = getattr(request.app.state, 'factory', None)
    settings = getattr(request.app.state, 'settings', None)
    raw = bearer_raw(request)
    if factory is not None:
        rate_limit(factory, f'{rate_key}:' + digest(raw), limit)
    token = db.get(Token, digest(raw))
    if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
        raise HTTPException(401, 'Invalid or expired token')
    user = _live_user(db, token.user_id, settings)
    request.state.token = token
    request.state.token_digest = token.digest
    request.state.session_digest = token.digest
    request.state.principal = user
    return user


def resolve_optional_account(request, db, *, rate_key: str = 'api', limit: int = 180):
    """The account when a usable token is present, ``None`` for no token at all.

    For endpoints that must serve a signed-out visitor (waitlist, feedback). Two cases are
    deliberately *not* folded into anonymous:

    * a token that exists but has expired or been revoked is still allowed to fall through
      to anonymous, which is the behaviour those routes shipped with;
    * a token that resolves to an **erased** account is a 401, because a deleted account is
      not "someone who has not signed in" - its credential must stop working everywhere.
    """
    raw = _bearer_value(request)
    if raw is None:
        request.state.principal = None
        return None
    request.state.principal_resolved = True
    cached = getattr(request.state, 'principal', _UNSET)
    if cached is not _UNSET:
        return cached
    factory = getattr(request.app.state, 'factory', None)
    settings = getattr(request.app.state, 'settings', None)
    if factory is not None:
        rate_limit(factory, f'{rate_key}:' + digest(raw), limit)
    token = db.get(Token, digest(raw))
    if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
        request.state.principal = None
        return None
    user = db.get(User, token.user_id)
    if refuse_if_erased(db, user, settings):
        raise HTTPException(401, 'Account unavailable')
    request.state.principal = user
    return user


# --------------------------------------------------------------------- route-level wiring
#
# ``resolve_account`` inside a handler is a function call, and a FastAPI dependency graph
# cannot see it. So each authenticated router declares a dependency that runs the resolver
# before the handler: every route on that router then has it in ``route.dependant``, and a
# route mounted without it is visible to ``routes_without_principal``. The resolver caches
# on ``request.state.principal``, so the handler's own call is a lookup, not a second
# rate-limit or a second token read.

_UNSET = object()

#: Attribute carried by every callable that resolves the principal. The route-graph guard
#: (``routes_without_principal``) looks for it in each route's dependency tree.
RESOLVES_PRINCIPAL = '_resolves_principal'

#: Routes that answer without a principal, as ``(METHOD, path template)``.
#:
#: This is a decision list, not a pattern: every entry is a route that must work for a
#: signed-out visitor. It is used twice - by ``routes_without_principal`` (a route that is
#: not here and has no resolver fails the guard) and by the HTTP boundary (a credentialed
#: request is only exempt from the principal requirement when it hits one of these). A new
#: public route must be added here deliberately, and a route that is here by mistake shows
#: up as a test failure rather than as a silent hole.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ('GET', '/health'),
    ('GET', '/api/v1/health'),
    ('GET', '/api/v1/legal'),
    ('GET', '/api/v1/legal/{slug}'),
    ('GET', '/api/v1/share/{token}'),
    ('GET', '/playground'),
    ('POST', '/api/v1/auth/register'),
    ('POST', '/api/v1/auth/login'),
    ('POST', '/api/v1/auth/refresh'),
    ('POST', '/api/v1/auth/forgot-password'),
    ('POST', '/api/v1/auth/reset-password'),
    ('POST', '/api/v1/feedback'),
    ('POST', '/api/v1/waitlist'),
    ('POST', '/api/v1/waitlist/confirm'),
})


def require_principal(rate_key: str = 'api', limit: int = 180):
    """A FastAPI dependency that resolves the account or raises the resolver's own 401.

    Returned as a closure because each route family keeps its own rate-limit ceiling. The
    marker is set on the closure, which is the object FastAPI stores in the dependency
    graph.
    """
    def dependency(request: Request):
        factory = getattr(request.app.state, 'factory', None)
        with factory() as db:
            return resolve_account(request, db, rate_key=rate_key, limit=limit)

    setattr(dependency, RESOLVES_PRINCIPAL, True)
    return dependency


def require_optional_principal(rate_key: str = 'api', limit: int = 180):
    """The anonymous-or-signed-in variant, for routers with public reads."""
    def dependency(request: Request):
        factory = getattr(request.app.state, 'factory', None)
        with factory() as db:
            return resolve_optional_account(request, db, rate_key=rate_key, limit=limit)

    setattr(dependency, RESOLVES_PRINCIPAL, True)
    return dependency


def _dependant_resolves(dependant) -> bool:
    if getattr(getattr(dependant, 'call', None), RESOLVES_PRINCIPAL, False):
        return True
    return any(_dependant_resolves(child) for child in dependant.dependencies)


def routes_without_principal(app, public) -> list[str]:
    """Routes that can answer without the resolver having run.

    ``public`` is a set of ``(METHOD, path)`` pairs a reviewer has decided need no
    principal. Everything else must have a resolver in its dependency tree - not an import
    of the resolver, not a similar-looking check: the dependency graph is what FastAPI
    actually executes, so it is the only claim worth testing.

    Routes are enumerated from the app, including routers mounted by FastAPI's
    ``_IncludedRouter`` wrapper, so a new ``routes_*.py`` cannot be born outside the check.
    The second half of the guarantee is at runtime: the HTTP boundary refuses any 2xx
    response to a request that carried a credential when ``principal_resolved`` is unset,
    which catches a hand-rolled dependency even if this graph walk is fooled.
    """
    # FastAPI 0.143 names it ``APIWebSocketRoute``; Starlette's base class is what
    # ``isinstance`` needs if a raw Starlette route is ever mounted.
    from fastapi.routing import APIRoute, APIWebSocketRoute
    from starlette.routing import WebSocketRoute as StarletteWebSocketRoute

    missing: list[str] = []

    def visit(routes):
        for route in routes:
            children = getattr(getattr(route, 'original_router', None), 'routes', None)
            if children:
                visit(children)
                continue
            if isinstance(route, (APIWebSocketRoute, StarletteWebSocketRoute)):
                # Not an APIRoute, so this walk is the *only* layer that can see it: the
                # HTTP boundary never sees a WebSocket handshake or frame. There are no
                # WebSocket routes today; the first one added inherits the check instead of
                # the gap.
                methods, path = {'WS'}, route.path
            elif isinstance(route, APIRoute):
                methods = {str(m).upper() for m in (route.methods or ())}
                path = route.path
            else:
                continue
            if methods and all((method, path) in public for method in methods):
                continue
            if not _dependant_resolves(route.dependant):
                missing.append(f'{",".join(sorted(methods))} {path}')

    visit(app.routes)
    return missing



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
