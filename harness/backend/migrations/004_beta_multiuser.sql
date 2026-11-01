-- ============================================================================
--  Luminfest Learning Harness — schema v3 -> v4
--  "Beta multi-user" migration.  PostgreSQL 15+.
--
--  Design contract (matches backend/scripts/init_db.py):
--    * ADDITIVE ONLY. New tables and new columns; no existing row is rewritten,
--      no column is dropped, no type is narrowed.
--    * IDEMPOTENT. Every statement is guarded, so running it twice is a no-op.
--    * BACK-COMPATIBLE. The v3 application keeps running against this schema;
--      the v4 code merely starts reading the new columns.
--
--  Adds, in order:
--    1. account lifecycle      (role / status / cohort / verification)
--    2. cohorts                (staged Beta rollout)
--    3. waitlist_signups       (pre-launch demand capture)
--    4. beta_invites           (redeemable access codes)
--    5. invite_redemptions
--    6. feedback + feedback_events   (in-product UX + bug/survey capture)
--    7. experiments + experiment_assignments  (UX personalisation)
--    8. session hardening on `tokens`
--    9. usage_ledger + usage_daily_rollup     (LLM token/cost accounting)
--   10. quota_policies + quota_counters       (per-user token/request budgets)
--   11. user_preferences + teacher_style_profiles  (durable personalisation)
--   12. consent_ledger                        (generalised consent trail)
--   13. admin_audit_log                       (operator accountability)
--
--  Run:  psql "$HARNESS_DATABASE_URL" -v ON_ERROR_STOP=1 -f 004_beta_multiuser.sql
-- ============================================================================

BEGIN;

-- Referral codes are generated below; pgcrypto ships with the official postgres image.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 0. helper: add a CHECK constraint only if it does not already exist
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION luminfest_add_check(p_table text, p_name text, p_expr text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = p_name AND conrelid = p_table::regclass
    ) THEN
        EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I CHECK (%s)', p_table, p_name, p_expr);
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. cohorts  (must precede users.cohort_id and beta_invites)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cohorts (
    id                    text PRIMARY KEY,
    name                  text NOT NULL UNIQUE,
    description           text,
    rollout_stage         text NOT NULL DEFAULT 'closed_beta',
    token_quota_monthly   bigint,
    request_quota_daily   integer,
    is_active             boolean NOT NULL DEFAULT true,
    created_at            double precision NOT NULL DEFAULT extract(epoch FROM now())
);
SELECT luminfest_add_check('cohorts', 'cohorts_rollout_stage_ck',
    $$rollout_stage IN ('internal','closed_beta','open_beta','general')$$);

-- ---------------------------------------------------------------------------
-- 1. account lifecycle columns on users
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS role                  text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS status                text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS cohort_id             text REFERENCES cohorts(id) ON DELETE SET NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name          text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locale                text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone              text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at     double precision;
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed_at double precision;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at          double precision;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code         text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by           text REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at            double precision;

UPDATE users SET role     = 'learner' WHERE role     IS NULL;
UPDATE users SET status   = 'active'  WHERE status   IS NULL;
UPDATE users SET locale   = 'en'      WHERE locale   IS NULL;
UPDATE users SET timezone = 'UTC'     WHERE timezone IS NULL;
UPDATE users SET referral_code = encode(gen_random_bytes(6), 'hex')
    WHERE referral_code IS NULL;

ALTER TABLE users ALTER COLUMN role     SET DEFAULT 'learner';
ALTER TABLE users ALTER COLUMN role     SET NOT NULL;
ALTER TABLE users ALTER COLUMN status   SET DEFAULT 'active';
ALTER TABLE users ALTER COLUMN status   SET NOT NULL;
ALTER TABLE users ALTER COLUMN locale   SET DEFAULT 'en';
ALTER TABLE users ALTER COLUMN locale   SET NOT NULL;
ALTER TABLE users ALTER COLUMN timezone SET DEFAULT 'UTC';
ALTER TABLE users ALTER COLUMN timezone SET NOT NULL;

SELECT luminfest_add_check('users', 'users_role_ck',
    $$role IN ('learner','teacher','admin')$$);
SELECT luminfest_add_check('users', 'users_status_ck',
    $$status IN ('waitlist','invited','active','suspended','deleted')$$);

CREATE UNIQUE INDEX IF NOT EXISTS users_referral_code_key ON users (referral_code);
CREATE INDEX IF NOT EXISTS users_status_idx  ON users (status);
CREATE INDEX IF NOT EXISTS users_cohort_idx  ON users (cohort_id);

-- ---------------------------------------------------------------------------
-- 3. waitlist_signups
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS waitlist_signups (
    id                text PRIMARY KEY,
    email             text NOT NULL,
    normalized_email  text NOT NULL UNIQUE,
    name              text,
    source            text NOT NULL DEFAULT 'landing',
    referrer_code     text,
    position          integer,
    priority          integer NOT NULL DEFAULT 0,
    status            text NOT NULL DEFAULT 'pending',
    consent_marketing boolean NOT NULL DEFAULT false,
    ip_hash           text,
    user_agent_hash   text,
    notes             text,
    created_at        double precision NOT NULL DEFAULT extract(epoch FROM now()),
    invited_at        double precision,
    converted_user_id text REFERENCES users(id) ON DELETE SET NULL,
    converted_at      double precision
);
SELECT luminfest_add_check('waitlist_signups', 'waitlist_source_ck',
    $$source IN ('landing','referral','teacher','partner','event','import')$$);
SELECT luminfest_add_check('waitlist_signups', 'waitlist_status_ck',
    $$status IN ('pending','invited','converted','declined','unsubscribed')$$);
CREATE INDEX IF NOT EXISTS waitlist_status_idx    ON waitlist_signups (status);
CREATE INDEX IF NOT EXISTS waitlist_created_idx   ON waitlist_signups (created_at);
CREATE INDEX IF NOT EXISTS waitlist_priority_idx  ON waitlist_signups (priority DESC, created_at);

-- ---------------------------------------------------------------------------
-- 4. beta_invites  (redeemable, cohort-scoped access codes)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS beta_invites (
    id                text PRIMARY KEY,
    code              text NOT NULL UNIQUE,
    cohort_id         text REFERENCES cohorts(id) ON DELETE SET NULL,
    email             text,
    normalized_email  text,
    max_uses          integer NOT NULL DEFAULT 1,
    uses              integer NOT NULL DEFAULT 0,
    status            text NOT NULL DEFAULT 'active',
    expires_at        double precision,
    created_by        text REFERENCES users(id) ON DELETE SET NULL,
    created_at        double precision NOT NULL DEFAULT extract(epoch FROM now())
);
SELECT luminfest_add_check('beta_invites', 'beta_invites_status_ck',
    $$status IN ('active','revoked','exhausted','expired')$$);
SELECT luminfest_add_check('beta_invites', 'beta_invites_uses_ck',
    $$uses >= 0 AND max_uses >= 1$$);
CREATE INDEX IF NOT EXISTS beta_invites_email_idx  ON beta_invites (normalized_email);
CREATE INDEX IF NOT EXISTS beta_invites_status_idx ON beta_invites (status);

-- ---------------------------------------------------------------------------
-- 5. invite_redemptions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invite_redemptions (
    id          text PRIMARY KEY,
    invite_id   text NOT NULL REFERENCES beta_invites(id) ON DELETE CASCADE,
    user_id     text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redeemed_at double precision NOT NULL DEFAULT extract(epoch FROM now()),
    ip_hash     text,
    UNIQUE (invite_id, user_id)
);
CREATE INDEX IF NOT EXISTS invite_redemptions_user_idx ON invite_redemptions (user_id);

-- ---------------------------------------------------------------------------
-- 6. feedback + feedback_events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    id              text PRIMARY KEY,
    user_id         text REFERENCES users(id) ON DELETE SET NULL,
    kind            text NOT NULL,
    rating          smallint,
    message         text NOT NULL,
    context         jsonb NOT NULL DEFAULT '{}'::jsonb,
    contact_email   text,
    status          text NOT NULL DEFAULT 'new',
    severity        text,
    assigned_to     text,
    resolution_note text,
    client_event_id text,
    created_at      double precision NOT NULL DEFAULT extract(epoch FROM now()),
    updated_at      double precision NOT NULL DEFAULT extract(epoch FROM now()),
    resolved_at     double precision
);
SELECT luminfest_add_check('feedback', 'feedback_kind_ck',
    $$kind IN ('bug','idea','praise','question','nps','csat','survey','accessibility','content_error')$$);
SELECT luminfest_add_check('feedback', 'feedback_status_ck',
    $$status IN ('new','triaged','in_progress','resolved','wontfix','duplicate')$$);
SELECT luminfest_add_check('feedback', 'feedback_severity_ck',
    $$severity IS NULL OR severity IN ('low','medium','high','critical')$$);
SELECT luminfest_add_check('feedback', 'feedback_rating_ck',
    $$rating IS NULL OR (rating BETWEEN 0 AND 10)$$);
CREATE UNIQUE INDEX IF NOT EXISTS feedback_idempotency_key
    ON feedback (user_id, client_event_id) WHERE client_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS feedback_status_idx  ON feedback (status, created_at DESC);
CREATE INDEX IF NOT EXISTS feedback_kind_idx    ON feedback (kind, created_at DESC);
CREATE INDEX IF NOT EXISTS feedback_user_idx    ON feedback (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS feedback_context_idx ON feedback USING gin (context jsonb_path_ops);

CREATE TABLE IF NOT EXISTS feedback_events (
    id            bigserial PRIMARY KEY,
    feedback_id   text NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
    actor_user_id text REFERENCES users(id) ON DELETE SET NULL,
    from_status   text,
    to_status     text,
    note          text,
    created_at    double precision NOT NULL DEFAULT extract(epoch FROM now())
);
CREATE INDEX IF NOT EXISTS feedback_events_feedback_idx ON feedback_events (feedback_id, created_at);

-- ---------------------------------------------------------------------------
-- 7. experiments + experiment_assignments  (UX personalisation / A-B)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS experiments (
    id          text PRIMARY KEY,
    key         text NOT NULL UNIQUE,
    description text,
    variants    jsonb NOT NULL DEFAULT '[]'::jsonb,
    status      text NOT NULL DEFAULT 'draft',
    started_at  double precision,
    ended_at    double precision,
    created_at  double precision NOT NULL DEFAULT extract(epoch FROM now())
);
SELECT luminfest_add_check('experiments', 'experiments_status_ck',
    $$status IN ('draft','running','paused','completed')$$);

CREATE TABLE IF NOT EXISTS experiment_assignments (
    id            text PRIMARY KEY,
    experiment_id text NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    user_id       text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    variant       text NOT NULL,
    assigned_at   double precision NOT NULL DEFAULT extract(epoch FROM now()),
    UNIQUE (experiment_id, user_id)
);
CREATE INDEX IF NOT EXISTS experiment_assignments_user_idx ON experiment_assignments (user_id);

-- ---------------------------------------------------------------------------
-- 8. session hardening on tokens
-- ---------------------------------------------------------------------------
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS label          text;
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS user_agent_hash text;
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS ip_hash        text;
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS last_used_at   double precision;
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS revoked_at     double precision;
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS rotated_from   text;

CREATE INDEX IF NOT EXISTS tokens_user_expiry_idx ON tokens (user_id, expires_at);
CREATE INDEX IF NOT EXISTS tokens_expiry_idx      ON tokens (expires_at);

-- ---------------------------------------------------------------------------
-- 9. usage_ledger + usage_daily_rollup  (LLM token / cost accounting)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usage_ledger (
    id                bigserial PRIMARY KEY,
    user_id           text REFERENCES users(id) ON DELETE SET NULL,
    request_id        text,
    feature           text NOT NULL,
    provider          text NOT NULL,
    model             text,
    prompt_tokens     integer NOT NULL DEFAULT 0,
    completion_tokens integer NOT NULL DEFAULT 0,
    total_tokens      integer NOT NULL DEFAULT 0,
    cost_micros       bigint  NOT NULL DEFAULT 0,
    latency_ms        integer,
    outcome           text NOT NULL DEFAULT 'ok',
    created_at        double precision NOT NULL DEFAULT extract(epoch FROM now())
);
SELECT luminfest_add_check('usage_ledger', 'usage_feature_ck',
    $$feature IN ('tutor_chat','harness_generate','harness_plan','teacher_analyze','ingest','other')$$);
SELECT luminfest_add_check('usage_ledger', 'usage_outcome_ck',
    $$outcome IN ('ok','fallback','error','refused')$$);
CREATE INDEX IF NOT EXISTS usage_ledger_user_time_idx ON usage_ledger (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS usage_ledger_time_idx      ON usage_ledger (created_at DESC);
CREATE INDEX IF NOT EXISTS usage_ledger_request_idx   ON usage_ledger (request_id);

CREATE TABLE IF NOT EXISTS usage_daily_rollup (
    user_id           text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day               date NOT NULL,
    feature           text NOT NULL,
    provider          text NOT NULL,
    model             text NOT NULL DEFAULT '',
    requests          integer NOT NULL DEFAULT 0,
    errors            integer NOT NULL DEFAULT 0,
    prompt_tokens     bigint  NOT NULL DEFAULT 0,
    completion_tokens bigint  NOT NULL DEFAULT 0,
    total_tokens      bigint  NOT NULL DEFAULT 0,
    cost_micros       bigint  NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day, feature, provider, model)
);
CREATE INDEX IF NOT EXISTS usage_rollup_day_idx ON usage_daily_rollup (day);

-- ---------------------------------------------------------------------------
-- 10. quota_policies + quota_counters
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quota_policies (
    id                text PRIMARY KEY,
    scope             text NOT NULL,
    scope_id          text,
    period            text NOT NULL,
    token_limit       bigint,
    request_limit     integer,
    cost_limit_micros bigint,
    enforcement       text NOT NULL DEFAULT 'soft',
    is_active         boolean NOT NULL DEFAULT true,
    created_at        double precision NOT NULL DEFAULT extract(epoch FROM now()),
    updated_at        double precision NOT NULL DEFAULT extract(epoch FROM now())
);
SELECT luminfest_add_check('quota_policies', 'quota_scope_ck',
    $$scope IN ('user','cohort','global')$$);
SELECT luminfest_add_check('quota_policies', 'quota_period_ck',
    $$period IN ('day','month','lifetime')$$);
SELECT luminfest_add_check('quota_policies', 'quota_enforcement_ck',
    $$enforcement IN ('hard','soft','observe')$$);
CREATE UNIQUE INDEX IF NOT EXISTS quota_policies_unique_active
    ON quota_policies (scope, coalesce(scope_id, ''), period)
    WHERE is_active;

CREATE TABLE IF NOT EXISTS quota_counters (
    id           text PRIMARY KEY,
    user_id      text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period       text NOT NULL,
    period_start double precision NOT NULL,
    requests     integer NOT NULL DEFAULT 0,
    total_tokens bigint  NOT NULL DEFAULT 0,
    cost_micros  bigint  NOT NULL DEFAULT 0,
    updated_at   double precision NOT NULL DEFAULT extract(epoch FROM now()),
    UNIQUE (user_id, period, period_start)
);
CREATE INDEX IF NOT EXISTS quota_counters_lookup_idx ON quota_counters (user_id, period, period_start);

-- ---------------------------------------------------------------------------
-- 11. durable personalisation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id        text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme          text NOT NULL DEFAULT 'system',
    default_modality text NOT NULL DEFAULT 'reading',
    accessibility  jsonb NOT NULL DEFAULT '{}'::jsonb,
    notifications  jsonb NOT NULL DEFAULT '{}'::jsonb,
    ui             jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at     double precision NOT NULL DEFAULT extract(epoch FROM now())
);
SELECT luminfest_add_check('user_preferences', 'user_preferences_theme_ck',
    $$theme IN ('system','light','dark','high_contrast')$$);

CREATE TABLE IF NOT EXISTS teacher_style_profiles (
    id                  text PRIMARY KEY,
    user_id             text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                text NOT NULL,
    source              text NOT NULL DEFAULT 'self',
    methodology         jsonb NOT NULL DEFAULT '[]'::jsonb,
    teaching_style      jsonb NOT NULL DEFAULT '[]'::jsonb,
    content_procedure   jsonb NOT NULL DEFAULT '[]'::jsonb,
    interaction_prompts jsonb NOT NULL DEFAULT '[]'::jsonb,
    tone                jsonb NOT NULL DEFAULT '[]'::jsonb,
    is_default          boolean NOT NULL DEFAULT false,
    created_at          double precision NOT NULL DEFAULT extract(epoch FROM now()),
    updated_at          double precision NOT NULL DEFAULT extract(epoch FROM now()),
    UNIQUE (user_id, name)
);
SELECT luminfest_add_check('teacher_style_profiles', 'tsp_source_ck',
    $$source IN ('self','transcript_analysis')$$);
CREATE UNIQUE INDEX IF NOT EXISTS tsp_one_default
    ON teacher_style_profiles (user_id) WHERE is_default;

-- ---------------------------------------------------------------------------
-- 12. generalised consent ledger
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consent_ledger (
    id             text PRIMARY KEY,
    user_id        text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind           text NOT NULL,
    enabled        boolean NOT NULL,
    policy_version text NOT NULL DEFAULT 'v1',
    created_at     double precision NOT NULL DEFAULT extract(epoch FROM now())
);
SELECT luminfest_add_check('consent_ledger', 'consent_kind_ck',
    $$kind IN ('telemetry','training','marketing','research','terms','privacy')$$);
CREATE INDEX IF NOT EXISTS consent_ledger_user_idx ON consent_ledger (user_id, kind, created_at DESC);

-- ---------------------------------------------------------------------------
-- 13. admin_audit_log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id            bigserial PRIMARY KEY,
    actor_user_id text REFERENCES users(id) ON DELETE SET NULL,
    action        text NOT NULL,
    target_type   text,
    target_id     text,
    detail        jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip_hash       text,
    created_at    double precision NOT NULL DEFAULT extract(epoch FROM now())
);
CREATE INDEX IF NOT EXISTS admin_audit_actor_idx  ON admin_audit_log (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS admin_audit_target_idx ON admin_audit_log (target_type, target_id);

-- ---------------------------------------------------------------------------
-- 14. bump the recorded schema version
-- ---------------------------------------------------------------------------
UPDATE schema_version SET version = 4 WHERE id = 1;

COMMIT;
