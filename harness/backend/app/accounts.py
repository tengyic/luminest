"""Account lifecycle, demand capture and metering for a hosted Beta.

Everything here is deliberately small and dependency-free. The Beta needs four things
that a single-user local app never did: a queue for demand, a way to admit people, a way
to prove an email address is real, and a way to see what the model calls are costing.
None of them justify a framework, and each is written so the same code path works on
SQLite in development and PostgreSQL in production.

The mailer is the one piece that must not lie. In development it writes the message to
the log and returns it, so a flow can be exercised end to end without an SMTP account. In
production it refuses to pretend: if no transport is configured, sending raises rather
than silently dropping a verification link a learner is waiting for.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .db import (BetaInvite, Cohort, Feedback, InviteRedemption, QuotaCounter, QuotaPolicy,
                 UsageLedger, UserPreference, WaitlistSignup, now_ts, uid)

log = logging.getLogger('luminfest.accounts')

EMAIL_RE = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')


def normalize_email(value: str) -> str:
    return (value or '').strip().casefold()


def valid_email(value: str) -> bool:
    value = normalize_email(value)
    return bool(EMAIL_RE.fullmatch(value)) and len(value) <= 254


# --------------------------------------------------------------------- mailer

class Mailer:
    """Transport-agnostic outbound mail.

    ``offline`` (the default) logs the message and keeps it in memory for tests and for
    the local Beta server. ``smtp`` is configured entirely from the environment so no
    credential ever lives in the repository.
    """

    def __init__(self, transport: str = 'offline', *, sender: str = 'Luminfest <no-reply@luminfest.local>',
                 base_url: str = 'http://127.0.0.1:8765'):
        self.transport = transport
        self.sender = sender
        self.base_url = base_url.rstrip('/')
        self.outbox: list[dict] = []

    @classmethod
    def from_env(cls, settings):
        transport = os.getenv('HARNESS_MAIL_TRANSPORT', 'offline')
        if transport not in {'offline', 'smtp'}:
            raise ValueError('HARNESS_MAIL_TRANSPORT must be offline or smtp')
        sender = os.getenv('HARNESS_MAIL_FROM', 'Luminfest <no-reply@luminfest.local>')
        base = os.getenv('HARNESS_PUBLIC_BASE_URL', 'http://127.0.0.1:8765')
        return cls(transport, sender=sender, base_url=base)

    def link(self, path: str, token: str) -> str:
        return f'{self.base_url}{path}?token={token}'

    def send(self, to: str, subject: str, body: str, *, purpose: str = 'transactional') -> dict:
        message = {'to': to, 'from': self.sender, 'subject': subject, 'body': body,
                   'purpose': purpose, 'queued_at': now_ts()}
        if self.transport == 'offline':
            self.outbox.append(message)
            log.info('mail(offline) to=%s subject=%r', to, subject)
            return message
        return self._send_smtp(message)

    def _send_smtp(self, message: dict):
        import smtplib
        from email.message import EmailMessage
        host = os.getenv('HARNESS_SMTP_HOST')
        if not host:
            # Never silently drop a verification link. A learner is waiting for it.
            raise RuntimeError('SMTP transport selected but HARNESS_SMTP_HOST is not configured')
        port = int(os.getenv('HARNESS_SMTP_PORT', '587'))
        user = os.getenv('HARNESS_SMTP_USER')
        password = os.getenv('HARNESS_SMTP_PASSWORD')
        msg = EmailMessage()
        msg['From'], msg['To'], msg['Subject'] = message['from'], message['to'], message['subject']
        msg.set_content(message['body'])
        with smtplib.SMTP(host, port, timeout=15) as client:
            client.starttls()
            if user:
                client.login(user, password)
            client.send_message(msg)
        return message


# --------------------------------------------------------------------- waitlist

def waitlist_position(db, row) -> int:
    """Queue position: earlier signups, higher priority first, then by time."""
    ahead = db.scalar(select(func.count()).select_from(WaitlistSignup).where(
        WaitlistSignup.id != row.id,
        (WaitlistSignup.priority > row.priority) |
        ((WaitlistSignup.priority == row.priority) & (WaitlistSignup.created_at < row.created_at)),
    ))
    return int(ahead or 0) + 1


def waitlist_json(db, row) -> dict:
    return {'email': row.email, 'status': row.status, 'source': row.source,
            'position': waitlist_position(db, row), 'confirmed': row.confirmed_at is not None,
            'priority': row.priority, 'created_at': row.created_at}


def join_waitlist(db, email: str, *, name=None, source='landing', referrer_code=None,
                  consent_marketing=False, ip=None, user_agent=None):
    """Idempotent: a repeat signup returns the existing row and re-issues confirmation.

    Re-signing up must never move a person backwards in the queue or create a duplicate.
    """
    from .security import digest, new_secret
    normalized = normalize_email(email)
    row = db.scalar(select(WaitlistSignup).where(WaitlistSignup.normalized_email == normalized))
    raw, token_digest = new_secret()
    if row is None:
        row = WaitlistSignup(email=email.strip(), normalized_email=normalized, name=(name or None),
                             source=source,
                             referrer_code=(referrer_code[:16] if referrer_code else None),
                             consent_marketing=bool(consent_marketing),
                             ip_hash=digest(ip)[:64] if ip else None,
                             user_agent_hash=digest(user_agent)[:64] if user_agent else None,
                             confirm_digest=token_digest)
        db.add(row)
        db.flush()
        row.position = waitlist_position(db, row)
    else:
        if row.status in {'declined', 'unsubscribed'}:
            row.status = 'pending'
        row.confirm_digest = token_digest
    return row, raw


def confirm_waitlist(db, raw_token: str):
    from .security import digest
    row = db.scalar(select(WaitlistSignup).where(WaitlistSignup.confirm_digest == digest(raw_token)))
    if not row:
        return None
    row.confirmed_at = row.confirmed_at or now_ts()
    row.confirm_digest = None
    return row


# --------------------------------------------------------------------- invites

def find_invite(db, code: str):
    return db.scalar(select(BetaInvite).where(BetaInvite.code == (code or '').strip().upper()))


def invite_is_redeemable(invite, email: str) -> tuple[bool, str]:
    if not invite or invite.status != 'active':
        return False, 'This invite code is not active.'
    if invite.expires_at is not None and invite.expires_at <= now_ts():
        return False, 'This invite code has expired.'
    if invite.uses >= invite.max_uses:
        return False, 'This invite code has already been fully redeemed.'
    if invite.normalized_email and invite.normalized_email != normalize_email(email):
        return False, 'This invite code was issued to a different email address.'
    return True, ''


def redeem_invite(db, invite, user, *, ip=None):
    from .security import digest
    invite.uses += 1
    if invite.uses >= invite.max_uses:
        invite.status = 'exhausted'
    db.add(InviteRedemption(invite_id=invite.id, user_id=user.id,
                            ip_hash=digest(ip)[:64] if ip else None))
    if invite.normalized_email:
        signup = db.scalar(select(WaitlistSignup).where(
            WaitlistSignup.normalized_email == invite.normalized_email))
        if signup:
            signup.status = 'converted'
            signup.converted_user_id = user.id
            signup.converted_at = now_ts()
    return invite


def new_invite_code() -> str:
    import secrets
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no I/O/0/1: unambiguous when read aloud
    return 'LUMINFEST-' + ''.join(secrets.choice(alphabet) for _ in range(8))


# --------------------------------------------------------------------- usage

def period_start(period: str, now: float | None = None) -> float:
    now = now if now is not None else now_ts()
    moment = datetime.fromtimestamp(now, timezone.utc)
    if period == 'day':
        return datetime(moment.year, moment.month, moment.day, tzinfo=timezone.utc).timestamp()
    if period == 'month':
        return datetime(moment.year, moment.month, 1, tzinfo=timezone.utc).timestamp()
    return 0.0  # lifetime


def effective_policies(db, user) -> list[QuotaPolicy]:
    """Every active policy that applies to this user, most specific first.

    Returns a *list*, not one policy, because a cohort may legitimately declare two
    different windows at the same time - a monthly token budget and a daily request
    ceiling. v6 collapsed those into a single ``period='month'`` policy, which measured the
    daily request ceiling against a monthly counter and so silently multiplied it by up to
    31. A cohort that means "50 requests a day" was enforced as "50 requests a month".
    """
    candidates = db.scalars(select(QuotaPolicy).where(QuotaPolicy.is_active.is_(True))).all()
    by_scope = {(p.scope, p.scope_id): p for p in candidates}
    found: list[QuotaPolicy] = []
    if ('user', user.id) in by_scope:
        found.append(by_scope[('user', user.id)])
    cohort_id = getattr(user, 'cohort_id', None)
    if cohort_id and ('cohort', cohort_id) in by_scope:
        found.append(by_scope[('cohort', cohort_id)])
    if ('global', None) in by_scope:
        found.append(by_scope[('global', None)])
    # Fall back to the cohort's own default allowance, if it declares one. One window per
    # limit, so each is measured against the counter that actually corresponds to it.
    if cohort_id:
        cohort = db.get(Cohort, cohort_id)
        if cohort and cohort.token_quota_monthly:
            found.append(QuotaPolicy(scope='cohort', scope_id=cohort_id, period='month',
                                     token_limit=cohort.token_quota_monthly,
                                     enforcement='observe'))
        if cohort and cohort.request_quota_daily:
            found.append(QuotaPolicy(scope='cohort', scope_id=cohort_id, period='day',
                                     request_limit=cohort.request_quota_daily,
                                     enforcement='observe'))
    return found


def effective_policy(db, user) -> QuotaPolicy | None:
    """The single most specific active policy, for callers that only need one."""
    policies = effective_policies(db, user)
    return policies[0] if policies else None


def _window_totals(db, user_id, period) -> tuple[float, dict]:
    """The running counter for one period window, and that window's start."""
    start = period_start(period)
    counters = db.scalar(select(QuotaCounter).where(
        QuotaCounter.user_id == user_id, QuotaCounter.period == period,
        QuotaCounter.period_start == start))
    return start, {'requests': int(counters.requests) if counters else 0,
                   'total_tokens': int(counters.total_tokens) if counters else 0,
                   'cost_micros': int(counters.cost_micros) if counters else 0}


def usage_summary(db, user) -> dict:
    """What this account has used and what it is allowed. Read-only; never blocks."""
    policies = effective_policies(db, user)
    policy = policies[0] if policies else None
    period = policy.period if policy else 'month'
    start, used = _window_totals(db, user.id, period)
    recent = db.scalars(select(UsageLedger).where(UsageLedger.user_id == user.id)
                        .order_by(UsageLedger.created_at.desc()).limit(20)).all()
    windows = []
    for candidate in policies:
        window_start, window_used = _window_totals(db, user.id, candidate.period)
        windows.append({'scope': candidate.scope, 'period': candidate.period,
                        'period_start': window_start, 'enforcement': candidate.enforcement,
                        'used': window_used,
                        'limit': {'requests': candidate.request_limit,
                                  'total_tokens': candidate.token_limit,
                                  'cost_micros': candidate.cost_limit_micros}})
    return {
        'period': period,
        'period_start': start,
        'used': used,
        'limits': None if not policy else {
            'requests': policy.request_limit, 'total_tokens': policy.token_limit,
            'cost_micros': policy.cost_limit_micros, 'enforcement': policy.enforcement},
        # One entry per applicable window, each measured against its own counter. A learner
        # whose cohort sets a monthly token budget *and* a daily request ceiling sees both
        # here, instead of one number that silently belonged to the wrong period.
        'windows': windows,
        'recent': [{'feature': r.feature, 'provider': r.provider, 'model': r.model,
                    'total_tokens': r.total_tokens, 'outcome': r.outcome,
                    'latency_ms': r.latency_ms, 'created_at': r.created_at} for r in recent],
        'note': 'Metering is observational during the Beta: it records usage and reports it '
                'without blocking a learner mid-session.',
    }


def record_usage(db, user_id, *, feature, provider, model=None, prompt_tokens=0,
                 completion_tokens=0, cost_micros=0, latency_ms=None, outcome='ok',
                 request_id=None):
    """Append one metered call and bump the running counter.

    An unmetered call is the one that breaks the budget, so this is called for every
    provider attempt, including fallbacks and errors.
    """
    total = int(prompt_tokens) + int(completion_tokens)
    db.add(UsageLedger(user_id=user_id, feature=feature, provider=provider, model=model,
                       prompt_tokens=int(prompt_tokens), completion_tokens=int(completion_tokens),
                       total_tokens=total, cost_micros=int(cost_micros), latency_ms=latency_ms,
                       outcome=outcome, request_id=request_id))
    if not user_id:
        return
    for period in ('day', 'month', 'lifetime'):
        _bump_counter(db, user_id, period, period_start(period), total, int(cost_micros))


def _bump_counter(db, user_id, period, start, total, cost_micros):
    """Add one metered call to a period window, creating the window when it is the first.

    ``SELECT ... FOR UPDATE`` locks a row that exists. It locks *nothing* when the row is
    absent, so on PostgreSQL two concurrent first calls for the same ``(user, period)``
    both read ``None``, both inserted, and one died on the ``(user_id, period,
    period_start)`` unique constraint - a 500 on the first metered call of every new day,
    which is the call a Beta makes most often. SQLite hid it completely because every write
    there opens with ``BEGIN IMMEDIATE`` (see ``main.start_write``), which takes the write
    lock before the read even happens, so the race cannot form in the test suite.

    The insert is therefore attempted inside a savepoint. If it loses the race the
    savepoint is rolled back, the surrounding transaction survives, and the winner's row is
    re-read under the lock and incremented.

    Totals are seeded explicitly: ``mapped_column(default=0)`` is a *flush-time* Python
    default, so a row that has only been constructed still reads ``None`` and an ``+= 1``
    against it raises ``TypeError``.
    """
    where = (QuotaCounter.user_id == user_id, QuotaCounter.period == period,
             QuotaCounter.period_start == start)
    counter = db.scalar(select(QuotaCounter).where(*where).with_for_update())
    if counter is None:
        try:
            with db.begin_nested():
                db.add(QuotaCounter(user_id=user_id, period=period, period_start=start,
                                    requests=1, total_tokens=total, cost_micros=cost_micros,
                                    updated_at=now_ts()))
            return
        except IntegrityError:
            counter = db.scalar(select(QuotaCounter).where(*where).with_for_update())
            if counter is None:  # pragma: no cover - the row was deleted mid-flight
                raise
    counter.requests += 1
    counter.total_tokens += total
    counter.cost_micros += cost_micros
    counter.updated_at = now_ts()


# --------------------------------------------------------------------- feedback

def feedback_json(row) -> dict:
    return {'id': row.id, 'kind': row.kind, 'rating': row.rating, 'message': row.message,
            'status': row.status, 'severity': row.severity, 'created_at': row.created_at,
            'updated_at': row.updated_at, 'resolution_note': row.resolution_note,
            'context': row.context or {}}


# --------------------------------------------------------------------- prefs

def preferences_for(db, user) -> UserPreference:
    row = db.get(UserPreference, user.id)
    if row is None:
        row = UserPreference(user_id=user.id)
        db.add(row)
        db.flush()
    return row


def preferences_json(row) -> dict:
    return {'theme': row.theme, 'default_modality': row.default_modality,
            'accessibility': row.accessibility or {}, 'notifications': row.notifications or {},
            'ui': row.ui or {}, 'updated_at': row.updated_at}
