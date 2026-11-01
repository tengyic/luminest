-- ============================================================================
--  Luminfest Learning Harness — schema v6 -> v7
--  Index and role-constraint parity.  PostgreSQL 15+.
--
--  Why this migration exists
--  -------------------------
--  Two build paths produce this schema: ``scripts/init_db.py`` (driven by
--  ``Base.metadata``) builds a *fresh* database, and ``migrations/004..006`` upgrade an
--  *existing* one. Nothing forced the two to agree, and until v7 they did not: 004 declared
--  about twenty indexes that the SQLAlchemy models never declared anywhere, so a database
--  created fresh carried none of them.
--
--  That is not a wrong-answer bug, it is a performance one, and it lands on exactly the
--  paths a Beta exercises first:
--    * ``POST /api/v1/waitlist`` computes the caller's queue position with a COUNT over
--      ``waitlist_signups`` filtered on ``(priority, created_at)`` — unindexed on a fresh
--      database that is a sequential scan plus a sort for every signup;
--    * the cost dashboards window ``usage_ledger`` by ``created_at``, on an append-only
--      table that never shrinks.
--
--  ``app/db.py`` now declares those indexes (``BETA_INDEXES`` / ``USER_CHECKS``), so a
--  freshly created database matches a migrated one. ``scripts/schema_parity.py`` is the
--  guard that keeps them matching. ``tests/test_schema_equivalence.py`` cannot see this
--  drift: its snapshot compares table and column *names*, and an index contributes neither.
--
--  This migration therefore carries only the changes that an already-migrated database
--  still needs and that cannot be expressed by the models alone:
--
--    1. ``users_role_ck`` widened to accept ``staff``. ``main.require_admin`` admits
--       ``{'admin', 'staff'}``, but 004's CHECK allowed only learner/teacher/admin — so the
--       one role the application treats as an operator was the one role the database
--       refused to store. An operator account could not be created on a migrated database.
--    2. ``quota_policies_global_unique`` — a partial unique index closing the last hole in
--       quota-policy uniqueness. 004's index already covers it via ``coalesce(scope_id,'')``;
--       this states the guarantee directly and matches what a fresh database now builds.
--
--  Contract (identical to 004, 005 and 006): additive, idempotent, no row rewritten, no
--  column dropped, no type narrowed. The CHECK replacement is a constraint swap, not a data
--  change — the new predicate is strictly wider than the old one, so no existing row can
--  fail it, and `role` is not a column any query filters on by index.
--
--  Run:  psql "$HARNESS_DATABASE_URL" -v ON_ERROR_STOP=1 -f 007_index_and_role_parity.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. users_role_ck: admit the role the application already accepts
-- ---------------------------------------------------------------------------
-- DROP then ADD, because PostgreSQL has no ALTER CONSTRAINT. Both statements are in this
-- transaction, so no concurrent writer observes the table unconstrained.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_ck;
ALTER TABLE users ADD  CONSTRAINT users_role_ck
    CHECK (role IN ('learner','teacher','staff','admin'));

-- ---------------------------------------------------------------------------
-- 2. quota_policies: make global uniqueness explicit
-- ---------------------------------------------------------------------------
-- `scope_id` is NULL for a global policy, and NULLs never collide in a unique index, so the
-- ordinary `(scope, scope_id, period)` index cannot constrain the global case at all. 004
-- already normalises this with `coalesce(scope_id, '')`; this adds the narrower and more
-- directly readable guarantee, and matches the index a freshly created database now builds.
-- Safe to create unconditionally: the wider 004 index already guarantees there is at most
-- one active global policy per period, so no existing row can violate this one.
CREATE UNIQUE INDEX IF NOT EXISTS quota_policies_global_unique
    ON quota_policies (period) WHERE is_active AND scope = 'global';

UPDATE schema_version SET version = 7 WHERE id = 1;

COMMIT;
