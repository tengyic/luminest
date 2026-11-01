-- ============================================================================
--  Luminfest Learning Harness — schema v5 -> v6
--  Session and credential tokens.  PostgreSQL 15+.
--
--  Why this migration exists
--  -------------------------
--  Through v5 a session was one opaque bearer token row in `tokens`, valid for
--  its whole TTL. That cannot express three things a hosted Beta needs:
--
--    * a short access window with a long session. A leaked access token is only
--      worth its remaining minutes, so the long-lived half has to be separate.
--    * rotation with theft detection. A refresh token is single-use: redeeming
--      it revokes the old row and issues a new one. Reuse of an already-rotated
--      token means the credential leaked, and the whole session is revoked.
--    * single-use e-mail flows. Verification and password reset links must be
--      consumable exactly once and must not be interchangeable.
--
--  This migration also carries the second half of v6: the waitlist double
--  opt-in. `waitlist_signups` gained `confirm_digest` and `confirmed_at` so a
--  signup is not confirmed until the emailed link is opened, which proves the
--  address is real and keeps the queue free of typo'd addresses. Those columns
--  are read and written by `app/accounts.py` (join_waitlist / confirm_waitlist /
--  waitlist_json), so a database migrated without them fails at runtime with
--  "column waitlist_signups.confirm_digest does not exist" the first time a
--  learner clicks the confirmation link.
--
--  Design contract (identical to 004 and 005):
--    * ADDITIVE ONLY. Two new tables and two new columns. No existing row is
--      rewritten, no column is dropped, no type is narrowed.
--    * IDEMPOTENT. Every statement is guarded; running it twice is a no-op.
--    * NO BACK-FILL NEEDED. Existing `tokens` rows stay valid exactly as they
--      are; the v6 code keeps accepting them until they expire. Nothing has to
--      be rewritten, so there is no window in which a logged-in learner is
--      thrown out by this migration.
--
--  Column types match the SQLAlchemy model exactly (app/db.py: RefreshToken,
--  AuthToken) so a migrated database and a freshly created one are identical.
--  Epoch timestamps are double precision, matching every other time column.
--
--  Run:  psql "$HARNESS_DATABASE_URL" -v ON_ERROR_STOP=1 -f 006_session_tokens.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. refresh_tokens — the long-lived half of a session, single-use
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refresh_tokens (
    digest        varchar(64)  NOT NULL,
    user_id       varchar(36)  NOT NULL,
    session_digest varchar(64) NOT NULL,
    expires_at    double precision NOT NULL,
    revoked_at    double precision,
    rotated_from  varchar(64),
    created_at    double precision NOT NULL,
    last_used_at  double precision,
    PRIMARY KEY (digest),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Every refresh on a session must find its siblings (to revoke the family on
-- reuse), and every login must find a user's sessions (to list or revoke them).
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_session_digest ON refresh_tokens (session_digest);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id        ON refresh_tokens (user_id);

-- ---------------------------------------------------------------------------
-- 2. auth_tokens — single-use, expiring e-mail tokens
-- ---------------------------------------------------------------------------
-- `kind` is a CHECK rather than a free string on purpose: a reset token must
-- never be accepted where a verification token is expected.
CREATE TABLE IF NOT EXISTS auth_tokens (
    id         varchar(36) NOT NULL,
    user_id    varchar(36) NOT NULL,
    kind       varchar(20) NOT NULL,
    digest     varchar(64) NOT NULL,
    expires_at double precision NOT NULL,
    used_at    double precision,
    created_at double precision NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT auth_tokens_kind_ck CHECK (kind IN ('verify_email','reset_password')),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    -- Only the digest is stored, so a database read cannot be replayed as a link.
    UNIQUE (digest)
);

CREATE INDEX IF NOT EXISTS auth_tokens_user_kind_idx ON auth_tokens (user_id, kind);
CREATE INDEX IF NOT EXISTS ix_auth_tokens_user_id    ON auth_tokens (user_id);

-- ---------------------------------------------------------------------------
-- 3. waitlist double opt-in
-- ---------------------------------------------------------------------------
-- Guarded with IF EXISTS because `waitlist_signups` arrives in 004. A database
-- that ran only 004 and 005 has the table without these columns, which is
-- exactly the case this repairs.
ALTER TABLE IF EXISTS waitlist_signups ADD COLUMN IF NOT EXISTS confirm_digest varchar(64);
ALTER TABLE IF EXISTS waitlist_signups ADD COLUMN IF NOT EXISTS confirmed_at   double precision;

-- Every confirmation click looks the row up by digest, so it must be indexed.
CREATE INDEX IF NOT EXISTS ix_waitlist_signups_confirm_digest ON waitlist_signups (confirm_digest);

-- ---------------------------------------------------------------------------
-- 4. legal / age attestation on `users`
-- ---------------------------------------------------------------------------
-- `users` has existed since v1, so like the waitlist columns these are invisible on a
-- freshly created database and absent on every upgraded one.
ALTER TABLE users ADD COLUMN IF NOT EXISTS age_confirmed_at  double precision;
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at double precision;
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version     varchar(32);

UPDATE schema_version SET version = 6 WHERE id = 1;

COMMIT;
