from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, Float, ForeignKey, Index,
                        Integer, JSON, SmallInteger, String, Text, UniqueConstraint, create_engine,
                        desc, event, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

#: ``bigserial`` on PostgreSQL, plain autoincrementing integer on SQLite. Append-only
#: ledgers (usage, audit, feedback history) use this so the hot insert path keeps index
#: locality instead of paying for a random 36-character UUID primary key.
BigIntPK = BigInteger().with_variant(Integer, 'sqlite')

#: ``jsonb`` on PostgreSQL, ``json`` elsewhere. The v4 columns are jsonb so they can be
#: indexed with ``jsonb_path_ops`` (feedback context) and queried by key without a rewrite.
#: The v1-v3 columns keep plain ``JSON`` - changing them would be a destructive migration.
JSONBType = JSON().with_variant(JSONB, 'postgresql')


def now_ts():
    return datetime.now(timezone.utc).timestamp()


def uid():
    return str(uuid4())


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(String(500), default='Build real understanding')
    daily_minutes: Mapped[int] = mapped_column(Integer, default=20)
    # -- v5: the course a learner is enrolled in -------------------------------
    #: Registry id from :mod:`app.courses`. Every course-scoped view reads this, so
    #: a learner in Physics never sees the mathematics map.
    course_id: Mapped[str] = mapped_column(String(40), default='integrated_math_1',
                                           server_default='integrated_math_1', index=True)
    telemetry_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    training_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    last_heartbeat: Mapped[float | None] = mapped_column(Float, nullable=True)
    # -- v4: account lifecycle for a hosted, multi-user Beta -------------------
    role: Mapped[str] = mapped_column(String(20), default='learner', server_default='learner')
    status: Mapped[str] = mapped_column(String(20), default='active', server_default='active')
    cohort_id: Mapped[str | None] = mapped_column(ForeignKey('cohorts.id', ondelete='SET NULL'), nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locale: Mapped[str] = mapped_column(String(16), default='en', server_default='en')
    timezone: Mapped[str] = mapped_column(String(64), default='UTC', server_default='UTC')
    email_verified_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    onboarding_completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    referral_code: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True)
    referred_by: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    deleted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    # -- v6: launch gate. A hosted Beta must be 13+ and must record acceptance of the
    # current Terms and Privacy Policy *version*, because both change over time and a
    # single boolean would not say which text the learner actually agreed to.
    age_confirmed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    terms_accepted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    terms_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


SCHEMA_VERSION = 11


class SchemaVersion(Base):
    __tablename__ = 'schema_version'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)


class TrainingConsent(Base):
    __tablename__ = 'training_consent_ledger'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
    policy_version: Mapped[str] = mapped_column(String(32), default='training-v1')
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class Token(Base):
    __tablename__ = 'tokens'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[float] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    # -- v4: session metadata so an account can list, label and revoke devices --
    label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revoked_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotated_from: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RefreshToken(Base):
    """A long-lived credential that buys a new access token.

    Access tokens are deliberately short-lived, so a leaked one is worth little. The
    refresh token is the long-lived half, and it is single-use: redeeming it revokes the
    old row and issues a new one (``rotated_from`` records the chain). Reuse of an
    already-rotated token is treated as theft and revokes the whole session.
    """

    __tablename__ = 'refresh_tokens'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    session_digest: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[float] = mapped_column(Float)
    revoked_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotated_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuthToken(Base):
    """A single-use, expiring token for email verification or password reset.

    Only the digest is stored, so a database read cannot be replayed as a link. ``kind``
    separates the two flows because a reset token must never be accepted where a
    verification token is expected.
    """

    __tablename__ = 'auth_tokens'
    __table_args__ = (
        CheckConstraint("kind IN ('verify_email','reset_password')", name='auth_tokens_kind_ck'),
        Index('auth_tokens_user_kind_idx', 'user_id', 'kind'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[float] = mapped_column(Float)
    used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class RateBucket(Base):
    __tablename__ = 'rate_buckets'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    start: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer)


class Secret(Base):
    __tablename__ = 'server_secrets'
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class State(Base):
    __tablename__ = 'learning_states'
    __table_args__ = (UniqueConstraint('user_id', 'concept_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    concept_id: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Assessment(Base):
    __tablename__ = 'assessments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    # -- v8: delayed transfer tests ------------------------------------------
    #: For ``mode='transfer'``: how many days after the learner's last practice
    #: activity this test was taken (7 or 28). ``None`` for every other mode, so
    #: existing rows and tests are untouched. Karpicke & Roediger (2008): the
    #: learning benefit is measured at a *delay*, so the delay is data, not detail.
    delay_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int] = mapped_column(Integer)
    answered: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    expires_at: Mapped[float] = mapped_column(Float)


class Receipt(Base):
    __tablename__ = 'receipts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(20))
    assessment_id: Mapped[str | None] = mapped_column(ForeignKey('assessments.id', ondelete='CASCADE'), nullable=True)
    issued_at: Mapped[float] = mapped_column(Float, default=now_ts)
    expires_at: Mapped[float] = mapped_column(Float)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Attempt(Base):
    __tablename__ = 'attempts'
    __table_args__ = (UniqueConstraint('user_id', 'client_event_id'), UniqueConstraint('receipt_id'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    receipt_id: Mapped[str] = mapped_column(ForeignKey('receipts.id', ondelete='CASCADE'))
    client_event_id: Mapped[str] = mapped_column(String(100))
    question_id: Mapped[str] = mapped_column(String(64))
    concept_id: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(20))
    correct: Mapped[bool] = mapped_column(Boolean)
    elapsed_seconds: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    concept_id: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class Project(Base):
    __tablename__ = 'projects'
    __table_args__ = (UniqueConstraint('user_id', 'concept_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    concept_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default='not_started')
    submission: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_disclosure: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)


class TelemetryEvent(Base):
    __tablename__ = 'telemetry_events'
    __table_args__ = (UniqueConstraint('user_id', 'client_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    client_id: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    occurred_at: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[float] = mapped_column(Float, default=now_ts)
    active_seconds: Mapped[float] = mapped_column(Float, default=0)


class MemoryNote(Base):
    """One durable thing the harness knows about a learner.

    ``kind`` separates three genuinely different things, because collapsing them is how
    a system ends up telling a student it has diagnosed them:

    ``episodic``    what happened (a session, an attempt sequence, a project submitted);
    ``semantic``    a belief about understanding, always tied to the evidence that
                    produced it and always revisable;
    ``procedural``  what worked for this learner (which move actually moved mastery).

    Every note carries its ``evidence`` and a ``confidence`` that decays with time and
    is reinforced when the same thing is observed again, so memory is a running
    estimate rather than a permanent verdict.
    """

    __tablename__ = 'memory_notes'
    __table_args__ = (UniqueConstraint('user_id', 'kind', 'concept_id', 'text'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    concept_id: Mapped[str] = mapped_column(String(64), default='')
    text: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.4)
    reinforcements: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    last_seen: Mapped[float] = mapped_column(Float, default=now_ts)


class HarnessRun(Base):
    """A recorded decision by the agentic loop, and what it led to.

    Storing the decision *and* its outcome is what makes the loop improvable: the
    harness can later ask which moves actually preceded progress, instead of assuming
    its policy is correct.
    """

    __tablename__ = 'harness_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    concept_id: Mapped[str] = mapped_column(String(64), default='')
    move: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    chosen: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class Flashcard(Base):
    """One persisted card in a learner's deck.

    Until v9 flashcards existed only as a transient ``harness.generate`` artifact: a
    list of ``{front, back}`` dicts returned by one call and never stored. That meant a
    card could be generated and read, but never *reviewed* -- and a review is the only
    event the FSRS-6 memory model can learn from. This table is what lets a card carry a
    DSR state (``stability`` / ``difficulty`` / ``due_at``) and feed the same memory curve
    the concept-level practice already feeds.

    ``source`` is mandatory provenance: the curriculum block or question id the card was
    built from. A card with no provenance cannot be graded honestly -- there is no way to
    tell whether it still matches the material -- so the domain layer refuses to create
    one. ``front_key`` is the normalised-front digest used to deduplicate, with the
    UNIQUE constraint on ``(user_id, concept_id, front_key)`` making generation idempotent
    at the database level, not merely by convention.
    """

    __tablename__ = 'flashcards'
    __table_args__ = (
        CheckConstraint("kind IN ('basic','cloze','definition','formula','misconception')",
                        name='flashcards_kind_ck'),
        CheckConstraint("state IN ('new','learning','review','relearning')",
                        name='flashcards_state_ck'),
        UniqueConstraint('user_id', 'concept_id', 'front_key'),
        Index('flashcards_user_due_idx', 'user_id', 'due_at'),
        Index('flashcards_user_concept_idx', 'user_id', 'concept_id'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    concept_id: Mapped[str] = mapped_column(String(64))
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    #: Provenance: ``{'kind': 'block'|'question'|'concept', 'concept_id': ..., ...}``.
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    kind: Mapped[str] = mapped_column(String(20), default='basic', server_default='basic')
    #: SHA-256 of the normalised front text; the dedupe key (see the class docstring).
    front_key: Mapped[str] = mapped_column(String(64))
    # -- FSRS-6 state. ``due_at`` is the scheduled next review, in epoch seconds ------
    due_at: Mapped[float] = mapped_column(Float, default=now_ts)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    reps: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    lapses: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    last_review_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_grade: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: New / learning / review / relearning -- a display summary of the DSR state, not a
    #: second scheduler. The schedule itself is ``due_at``, computed by the FSRS-6 model.
    state: Mapped[str] = mapped_column(String(20), default='new', server_default='new')
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)


class Cohort(Base):
    """A staged Beta rollout group. Carries the default quota a member inherits."""

    __tablename__ = 'cohorts'
    __table_args__ = (CheckConstraint("rollout_stage IN ('internal','closed_beta','open_beta','general')", name='cohorts_rollout_stage_ck'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollout_stage: Mapped[str] = mapped_column(String(20), default='closed_beta', server_default='closed_beta')
    token_quota_monthly: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_quota_daily: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class WaitlistSignup(Base):
    """Pre-launch demand. ``normalized_email`` is the dedupe key, ``position`` the queue."""

    __tablename__ = 'waitlist_signups'
    __table_args__ = (
        CheckConstraint("source IN ('landing','referral','teacher','partner','event','import')", name='waitlist_source_ck'),
        CheckConstraint("status IN ('pending','invited','converted','declined','unsubscribed')", name='waitlist_status_ck'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254))
    normalized_email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default='landing', server_default='landing')
    referrer_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    status: Mapped[str] = mapped_column(String(20), default='pending', server_default='pending')
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    invited_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    converted_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    converted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    # -- v6: double opt-in. A signup is not confirmed until the emailed link is opened,
    # which proves the address is real and keeps the queue free of typo'd addresses.
    confirm_digest: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    confirmed_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class BetaInvite(Base):
    """A redeemable access code. Cohort-scoped, optionally addressed to one email."""

    __tablename__ = 'beta_invites'
    __table_args__ = (
        CheckConstraint("status IN ('active','revoked','exhausted','expired')", name='beta_invites_status_ck'),
        CheckConstraint('uses >= 0 AND max_uses >= 1', name='beta_invites_uses_ck'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    cohort_id: Mapped[str | None] = mapped_column(ForeignKey('cohorts.id', ondelete='SET NULL'), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    uses: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    status: Mapped[str] = mapped_column(String(20), default='active', server_default='active')
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class InviteRedemption(Base):
    __tablename__ = 'invite_redemptions'
    __table_args__ = (UniqueConstraint('invite_id', 'user_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    invite_id: Mapped[str] = mapped_column(ForeignKey('beta_invites.id', ondelete='CASCADE'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    redeemed_at: Mapped[float] = mapped_column(Float, default=now_ts)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Feedback(Base):
    """One piece of in-product feedback: a bug, an idea, an NPS or CSAT score, a survey.

    ``user_id`` is nullable so an unauthenticated visitor on the waitlist page can still
    report a problem. ``client_event_id`` makes submission idempotent, exactly like
    ``attempts``.
    """

    __tablename__ = 'feedback'
    __table_args__ = (
        CheckConstraint("kind IN ('bug','idea','praise','question','nps','csat','survey','accessibility','content_error')", name='feedback_kind_ck'),
        CheckConstraint("status IN ('new','triaged','in_progress','resolved','wontfix','duplicate')", name='feedback_status_ck'),
        CheckConstraint("severity IS NULL OR severity IN ('low','medium','high','critical')", name='feedback_severity_ck'),
        CheckConstraint('rating IS NULL OR (rating BETWEEN 0 AND 10)', name='feedback_rating_ck'),
        Index('feedback_idempotency_key', 'user_id', 'client_event_id', unique=True,
              postgresql_where=text('client_event_id IS NOT NULL'),
              sqlite_where=text('client_event_id IS NOT NULL')),
        Index('feedback_context_idx', 'context', postgresql_using='gin',
              postgresql_ops={'context': 'jsonb_path_ops'}),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSONBType, default=dict)
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='new', server_default='new')
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class FeedbackEvent(Base):
    __tablename__ = 'feedback_events'
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id', ondelete='CASCADE'))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class Experiment(Base):
    __tablename__ = 'experiments'
    __table_args__ = (CheckConstraint("status IN ('draft','running','paused','completed')", name='experiments_status_ck'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    variants: Mapped[list] = mapped_column(JSONBType, default=list)
    status: Mapped[str] = mapped_column(String(20), default='draft', server_default='draft')
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class ExperimentAssignment(Base):
    __tablename__ = 'experiment_assignments'
    __table_args__ = (UniqueConstraint('experiment_id', 'user_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    experiment_id: Mapped[str] = mapped_column(ForeignKey('experiments.id', ondelete='CASCADE'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    variant: Mapped[str] = mapped_column(String(40))
    assigned_at: Mapped[float] = mapped_column(Float, default=now_ts)


class ExperimentExposure(Base):
    """One logged presentation of an experiment to a user on one surface.

    Assignment says which arm a learner is in; exposure says whether they ever
    actually *saw* it. An analysis that counts assigned-but-never-exposed users as
    participants inflates N with people who never met the treatment, so exposure is
    its own record. Idempotent per (experiment, user, surface): repeated renders of
    the same surface log once, because the unit of analysis is "was ever shown",
    not "was shown n times".
    """

    __tablename__ = 'experiment_exposures'
    __table_args__ = (
        UniqueConstraint('experiment_id', 'user_id', 'surface'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    experiment_id: Mapped[str] = mapped_column(ForeignKey('experiments.id', ondelete='CASCADE'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    surface: Mapped[str] = mapped_column(String(40))
    exposed_at: Mapped[float] = mapped_column(Float, default=now_ts)


class UsageLedger(Base):
    """One metered model call. The source of truth for Beta token/cost accounting.

    Append-only: a row is written for every provider call, including the ones that fell
    back to the offline tutor or errored, because an unmetered call is the one that
    breaks the budget.
    """

    __tablename__ = 'usage_ledger'
    __table_args__ = (
        CheckConstraint("feature IN ('tutor_chat','harness_generate','harness_plan','teacher_analyze','ingest','other')", name='usage_feature_ck'),
        CheckConstraint("outcome IN ('ok','fallback','error','refused')", name='usage_outcome_ck'),
        Index('usage_ledger_user_time_idx', 'user_id', 'created_at'),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    feature: Mapped[str] = mapped_column(String(30))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(12), default='ok', server_default='ok')
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class UsageDailyRollup(Base):
    """Nightly aggregate of ``usage_ledger`` for dashboards and quota windows."""

    __tablename__ = 'usage_daily_rollup'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    day: Mapped[object] = mapped_column(Date, primary_key=True)
    feature: Mapped[str] = mapped_column(String(30), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    model: Mapped[str] = mapped_column(String(80), primary_key=True, default='', server_default='')
    requests: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')


class QuotaPolicy(Base):
    """A limit attached to a user, a cohort, or globally. ``enforcement`` decides whether
    exceeding it blocks the call (``hard``), merely warns (``soft``) or is measured only
    (``observe``) - the last is how a Beta should start.
    """

    __tablename__ = 'quota_policies'
    __table_args__ = (
        CheckConstraint("scope IN ('user','cohort','global')", name='quota_scope_ck'),
        CheckConstraint("period IN ('day','month','lifetime')", name='quota_period_ck'),
        CheckConstraint("enforcement IN ('hard','soft','observe')", name='quota_enforcement_ck'),
        Index('quota_policies_unique_active', 'scope', 'scope_id', 'period', unique=True,
              postgresql_where=text('is_active'), sqlite_where=text('is_active = 1')),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scope: Mapped[str] = mapped_column(String(10))
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    period: Mapped[str] = mapped_column(String(10))
    token_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_limit_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enforcement: Mapped[str] = mapped_column(String(10), default='soft', server_default='soft')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)


class QuotaCounter(Base):
    """Running total for one user in one period window.

    Deliberately mirrors ``rate_buckets``: a single row read ``FOR UPDATE``, incremented
    and committed. Enforcement stays O(1) and needs no scan of ``usage_ledger``.
    """

    __tablename__ = 'quota_counters'
    __table_args__ = (UniqueConstraint('user_id', 'period', 'period_start'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    period: Mapped[str] = mapped_column(String(10))
    period_start: Mapped[float] = mapped_column(Float)
    requests: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)


class UserPreference(Base):
    """Durable UI/UX personalisation. Accessibility lives here so it survives reinstall."""

    __tablename__ = 'user_preferences'
    __table_args__ = (CheckConstraint("theme IN ('system','light','dark','high_contrast')", name='user_preferences_theme_ck'),)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    theme: Mapped[str] = mapped_column(String(20), default='system', server_default='system')
    default_modality: Mapped[str] = mapped_column(String(20), default='reading', server_default='reading')
    accessibility: Mapped[dict] = mapped_column(JSONBType, default=dict)
    notifications: Mapped[dict] = mapped_column(JSONBType, default=dict)
    ui: Mapped[dict] = mapped_column(JSONBType, default=dict)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)


class TeacherStyleProfile(Base):
    """A saved style profile. Until v4 this existed only for the duration of one request."""

    __tablename__ = 'teacher_style_profiles'
    __table_args__ = (
        UniqueConstraint('user_id', 'name'),
        CheckConstraint("source IN ('self','transcript_analysis')", name='tsp_source_ck'),
        Index('tsp_one_default', 'user_id', unique=True,
              postgresql_where=text('is_default'), sqlite_where=text('is_default = 1')),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(20), default='self', server_default='self')
    methodology: Mapped[list] = mapped_column(JSONBType, default=list)
    teaching_style: Mapped[list] = mapped_column(JSONBType, default=list)
    content_procedure: Mapped[list] = mapped_column(JSONBType, default=list)
    interaction_prompts: Mapped[list] = mapped_column(JSONBType, default=list)
    tone: Mapped[list] = mapped_column(JSONBType, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)


class ConsentLedger(Base):
    """Generalised consent trail. ``training_consent_ledger`` is kept for back-compat."""

    __tablename__ = 'consent_ledger'
    __table_args__ = (CheckConstraint("kind IN ('telemetry','training','marketing','research','terms','privacy')", name='consent_kind_ck'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean)
    policy_version: Mapped[str] = mapped_column(String(32), default='v1')
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class AdminAuditLog(Base):
    __tablename__ = 'admin_audit_log'
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSONBType, default=dict)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class PlaygroundRun(Base):
    """One completed, scored task inside a first-party playground game.

    Deliberately **not** an ``Attempt``. An attempt answers an authored question from
    the curriculum bank: it is issued under a receipt, it consumes that receipt, and
    it is graded against the question's own recorded answer key. A playground run is
    something different in kind - a learner committing to an answer *inside a
    simulation we wrote*, where the answer key belongs to the game. Recording the two
    in one table would let a game borrow the authority of the question bank, and a
    reviewer reading the attempts table could no longer tell which observations came
    from vetted items.

    What the two *do* share is the effect. A run that the learner committed to is a
    real right/wrong observation about a concept, so it feeds the same mastery state
    the questions feed (see ``harness.playground.evidence``), and this row records
    the before/after so that effect is auditable rather than assumed.

    ``detail`` holds the game's own telemetry: which task, how many tries, and the
    archetype-specific fields the game chose to report. It is free-form by design, and
    it must never contain anything the learner typed as free text.
    """

    __tablename__ = 'playground_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    #: The stored artifact this was played from, so a run can be traced to exact bytes.
    artifact_id: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(80), index=True)
    archetype: Mapped[str] = mapped_column(String(40))
    concept_id: Mapped[str] = mapped_column(String(64), index=True)
    #: Which task within the game, when the game has more than one.
    task_id: Mapped[str] = mapped_column(String(64), default='')
    correct: Mapped[bool] = mapped_column(Boolean)
    tries: Mapped[int] = mapped_column(Integer, default=1)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: The learner's mastery of this concept before and after the run. Recorded so the
    #: claim "playground play counts" can be checked against the database, not trusted.
    mastery_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    mastery_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)


class ProcedureRun(Base):
    """One compiled lesson procedure, and how far the learner got through it.

    Deliberately **not** an ``Attempt`` and not a ``PlaygroundRun``. Those record an
    observation; this records a *plan* and its progress. Advancing a block says the
    learner did the activity, not that they did it well - mastery still moves only
    through the question route and the playground's own outcome route. Keeping the plan
    out of the evidence tables is what stops "opened the deck" from ever being read as
    "learned the concept".

    ``blocks`` is the compiled plan exactly as the compiler produced it, including the
    bound artifacts and the reasons activities were refused. It is stored rather than
    recompiled on read for one reason: a lesson that changes shape underneath a learner
    mid-session is not a lesson. A genuinely new plan gets a new ``procedure_hash`` and a
    new row, and the old one is marked abandoned rather than edited.

    ``completed`` is an append-only list of ``{order, kind, outcome, at, seconds,
    note}``. It is JSON rather than a second table because it is read and written as a
    whole, is bounded by the number of blocks (at most nine), and has no query surface
    beyond "how far did this run get".
    """

    __tablename__ = 'procedure_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'),
                                         index=True)
    concept_id: Mapped[str] = mapped_column(String(64), index=True)
    course_id: Mapped[str] = mapped_column(String(40), default='')
    #: The plan's fingerprint. A recompile whose evidence has not changed produces the
    #: same hash and resumes; one whose evidence moved is a different lesson.
    procedure_hash: Mapped[str] = mapped_column(String(64), index=True)
    profile_name: Mapped[str] = mapped_column(String(40), default='default')
    budget_minutes: Mapped[int] = mapped_column(Integer, default=0)
    total_minutes: Mapped[int] = mapped_column(Integer, default=0)
    blocks: Mapped[list] = mapped_column(JSON, default=list)
    completed: Mapped[list] = mapped_column(JSON, default=list)
    #: Activities the compiler refused, with the reason. Stored with the plan because the
    #: prompt must be able to say "no video, and here is why" for the *running* lesson,
    #: not only for a freshly compiled one.
    skipped: Mapped[list] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(String(1000), default='')
    #: active | completed | abandoned
    status: Mapped[str] = mapped_column(String(20), default='active', index=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)

    __table_args__ = (
        UniqueConstraint('user_id', 'concept_id', 'procedure_hash',
                         name='procedure_runs_user_concept_hash_uq'),
    )


# --------------------------------------------------------------------- index parity
#: ``Base.metadata`` is what ``scripts/init_db.py`` builds. So a *fresh* database - which is
#: every development database, and any production database created by ``init_db.py`` - has
#: exactly the indexes declared on these tables and nothing else. The PostgreSQL reference
#: DDL in ``migrations/004..006`` declares these same indexes for databases that were
#: upgraded in place instead of created fresh.
#:
#: Until v7 those two sets disagreed. The SQL declared roughly twenty indexes that the ORM
#: never declared anywhere, so the two build paths produced different schemas. The
#: consequence was not a wrong answer, it was that a fresh Beta database served
#: ``POST /api/v1/waitlist`` (whose position is an unindexed ``COUNT(*)`` over
#: ``waitlist_signups``) and the cost dashboards (an unindexed scan of the append-only
#: ``usage_ledger``) with no supporting index at all, while a migrated database did not.
#:
#: ``tests/test_schema_equivalence.py`` cannot see this: its snapshot compares table and
#: column names only, and every index here is on a column that exists either way. The
#: guard is ``scripts/schema_parity.py``, which diffs the ORM against the reference DDL.
#:
#: Two deliberate non-additions, both documented rather than copied blindly:
#:
#: * ``quota_counters_lookup_idx`` - 004 declares it on ``(user_id, period, period_start)``,
#:   which is already the table's UNIQUE constraint. A second identical index only costs
#:   writes, so it is not reproduced here.
#: * ``ix_feedback_user_id`` / ``ix_tokens_user_id`` become strict prefixes of the composite
#:   indexes added below. They are left in place because dropping a column's ``index=True``
#:   would change freshly created databases without touching already-migrated ones - the
#:   same class of divergence this block exists to remove. Consolidating them is a
#:   follow-up, and ``schema_parity.py`` reports them as redundant rather than missing.
BETA_INDEXES: tuple = (
    # -- account administration ------------------------------------------------
    Index('users_status_idx', User.__table__.c.status),
    # -- waitlist: position is a COUNT over exactly these two columns ----------
    Index('waitlist_status_idx', WaitlistSignup.__table__.c.status),
    Index('waitlist_created_idx', WaitlistSignup.__table__.c.created_at),
    Index('waitlist_priority_idx', desc(WaitlistSignup.__table__.c.priority),
          WaitlistSignup.__table__.c.created_at),
    # -- invites --------------------------------------------------------------
    Index('beta_invites_status_idx', BetaInvite.__table__.c.status),
    # -- feedback: the triage queue, the kind filter, and "my feedback" ---------
    Index('feedback_status_idx', Feedback.__table__.c.status,
          desc(Feedback.__table__.c.created_at)),
    Index('feedback_kind_idx', Feedback.__table__.c.kind,
          desc(Feedback.__table__.c.created_at)),
    Index('feedback_user_idx', Feedback.__table__.c.user_id,
          desc(Feedback.__table__.c.created_at)),
    Index('feedback_events_feedback_idx', FeedbackEvent.__table__.c.feedback_id,
          FeedbackEvent.__table__.c.created_at),
    # -- sessions: sweep expired credentials without scanning the table --------
    Index('tokens_user_expiry_idx', Token.__table__.c.user_id, Token.__table__.c.expires_at),
    Index('tokens_expiry_idx', Token.__table__.c.expires_at),
    # -- cost accounting: every dashboard window opens with created_at ---------
    Index('usage_ledger_time_idx', desc(UsageLedger.__table__.c.created_at)),
    Index('usage_rollup_day_idx', UsageDailyRollup.__table__.c.day),
    # -- consent and operator accountability ----------------------------------
    Index('consent_ledger_user_idx', ConsentLedger.__table__.c.user_id,
          ConsentLedger.__table__.c.kind, desc(ConsentLedger.__table__.c.created_at)),
    Index('admin_audit_actor_idx', AdminAuditLog.__table__.c.actor_user_id,
          desc(AdminAuditLog.__table__.c.created_at)),
    Index('admin_audit_target_idx', AdminAuditLog.__table__.c.target_type,
          AdminAuditLog.__table__.c.target_id),
    # -- lesson procedures: "this learner's active lesson on this concept" -----
    Index('procedure_runs_active_idx', ProcedureRun.__table__.c.user_id,
          ProcedureRun.__table__.c.concept_id, ProcedureRun.__table__.c.status),
    # -- quota_policies: see the note on the unique index below ----------------
    Index('quota_policies_global_unique', QuotaPolicy.__table__.c.period, unique=True,
          postgresql_where=text("is_active AND scope = 'global'"),
          sqlite_where=text("is_active = 1 AND scope = 'global'")),
)

#: ``role`` and ``status`` are gates, not labels: ``main.require_admin`` reads ``role`` and
#: every "is this account allowed to act" decision reads ``status``. 004 constrains both, but
#: only in SQL, so a freshly created database accepted any string in either column.
#:
#: ``staff`` is included because ``require_admin`` already admits it
#: (``{'admin', 'staff'}``). 004's CHECK allowed only ``learner``/``teacher``/``admin``, so
#: the role the code accepts was the one role the database refused to store - an operator
#: account could not be created on a migrated database at all. ``migrations/007`` widens the
#: shipped constraint to match.
USER_CHECKS: tuple = (
    CheckConstraint("role IN ('learner','teacher','staff','admin')", name='users_role_ck'),
    CheckConstraint("status IN ('waitlist','invited','active','suspended','deleted')",
                    name='users_status_ck'),
)
for _check in USER_CHECKS:
    User.__table__.append_constraint(_check)


def make_database(settings):
    # The user-scope guard installs on the ORM Session class, so every session this
    # process ever opens runs under the same multi-tenant read rule. See
    # :mod:`app.user_scope` for what is guarded, what is allowed, and why.
    from . import user_scope
    user_scope.install()
    sqlite = settings.database_url.startswith('sqlite:')
    if sqlite:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = create_engine(settings.database_url, pool_pre_ping=True,
                               connect_args={'check_same_thread': False, 'timeout': 30})
        @event.listens_for(engine, 'connect')
        def pragmas(connection, _):
            cursor = connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.execute('PRAGMA journal_mode=WAL')
            cursor.execute('PRAGMA busy_timeout=30000')
            cursor.close()
    else:
        # Hosted Beta: every request may open a connection, so the pool is sized for
        # concurrency rather than the single local user. ``pool_recycle`` keeps connections
        # under any pooler's idle timeout and ``statement_timeout`` bounds a runaway query
        # instead of letting it hold a connection until the client gives up.
        engine = create_engine(
            settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20,
            pool_recycle=1800, pool_timeout=30,
            connect_args={'options': '-c statement_timeout=15000 -c idle_in_transaction_session_timeout=30000'},
        )
    return engine, sessionmaker(engine, expire_on_commit=False)
