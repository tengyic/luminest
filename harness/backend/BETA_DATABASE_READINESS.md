# Luminfest — Beta Database Readiness

**Verdict: the schema is Beta-ready for all five requirements. Four defects found, all fixed.
One piece of schema is dead code and needs your decision. Nothing here was executed — see
"Verification status" before you trust any of it.**

Scope: `harness/backend` — SQLAlchemy 2.x models (`app/db.py`), the Beta service layer
(`app/accounts.py`), the PostgreSQL reference DDL (`migrations/004..007`), and the initializer
(`scripts/init_db.py`). 33 tables at schema v7. SQLite in development, PostgreSQL 15+ in
production (`app/config.py` refuses anything else when `HARNESS_ENV=production`).

---

## 1. Requirement matrix

| Beta requirement | Status | Where it actually lives |
|---|---|---|
| **Multi-user usage** | Pass | Every learner-owned table carries `user_id` FK + `ON DELETE CASCADE`. Per-user uniqueness is enforced, not assumed: `(user_id, concept_id)` on `learning_states`/`projects`, `(user_id, client_event_id)` on `attempts`/`telemetry_events`. `users.course_id` scopes every course view so one learner's Physics graph never mixes with another's algebra. `role`/`status` are DB-level gates. Soft delete via `deleted_at` plus `/api/v1/export` and `DELETE /api/v1/me`. |
| **Personalization** | Pass | `user_preferences` (`theme`, `default_modality`, `accessibility`, `notifications`, `ui` as `jsonb`), `teacher_style_profiles`, `experiments` + `experiment_assignments`, `memory_notes`. Server-side, so it survives a reinstall. `GET`/`PATCH /api/v1/preferences`. |
| **UX & feedback** | Pass | `feedback` — 9 kinds, 6-state lifecycle, severity, 0–10 rating, `jsonb` context with a GIN index, idempotent on `client_event_id`. `feedback_events` is the audit trail. `telemetry_events` for behavioural signal. Submission works signed-out (`user_id` nullable), which is what the waitlist page needs. |
| **Waitlist** | Pass | `waitlist_signups` — dedupe on `normalized_email`, `priority` + `position`, double opt-in (`confirm_digest` / `confirmed_at`), referral codes, conversion tracking. `beta_invites` (cohort-scoped, optionally email-addressed, `max_uses`, expiry) + `invite_redemptions` + `cohorts` for staged rollout. |
| **Token management** | Pass, after 2 fixes | Both senses are covered. *Credentials:* `tokens` / `refresh_tokens` (single-use rotation with theft detection) / `auth_tokens` (single-use verify & reset, `kind`-checked so the flows are not interchangeable). *LLM tokens & cost:* `usage_ledger` (append-only, one row per provider call **including fallbacks and errors**), `quota_counters` (day/month/lifetime), `quota_policies` (user/cohort/global × hard/soft/observe), `usage_daily_rollup`, `GET /api/v1/usage`. |

---

## 2. Findings

### F1 — The two build paths produced different schemas *(fixed)*

This is the substantive finding. Two different mechanisms build this schema:

* `scripts/init_db.py` calls `Base.metadata.create_all()` — this is what builds **every
  development database and any production database created fresh**;
* `migrations/*.sql` upgrades a database that already exists.

`migrations/004_beta_multiuser.sql` declares about twenty indexes. The SQLAlchemy models
declared almost none of them. So a fresh database had **no index at all** on the hot paths:

* `POST /api/v1/waitlist` computes the caller's queue position with a `COUNT(*)` over
  `waitlist_signups` filtered on `(priority, created_at)`
  (`accounts.waitlist_position`) — a sequential scan plus a sort, on every signup;
* the cost dashboards window `usage_ledger` by `created_at`, on a table that is append-only
  and never shrinks.

`tests/test_schema_equivalence.py` cannot see this. Its `_snapshot()` compares
`{table: {column names}}` — and an index contributes neither a table nor a column. The suite
was green while the two paths diverged.

**Fix:** those indexes are now declared in `app/db.py` as `BETA_INDEXES`, `users.role`/`status`
CHECKs as `USER_CHECKS`, and the diff is now machine-checked:

```
PYTHONPATH=backend python3 backend/scripts/schema_parity.py --check
```

It compares by `(table, sorted columns, unique)` rather than by name, because the two paths
legitimately name the same index differently (`ix_users_email` vs a column-level `UNIQUE`).
Exit status 1 only for the actionable direction. Two SQL-only indexes are listed as
intentional with reasons, not silently ignored.

### F2 — First metered call of every window could 500 on PostgreSQL *(fixed)*

`accounts.record_usage` did `SELECT ... FOR UPDATE`, and inserted the counter row if it was
absent. `FOR UPDATE` locks a row that **exists**; on a missing row it locks nothing. Under
READ COMMITTED two concurrent first calls for the same `(user, period)` both read `None`,
both inserted, and one died on the `(user_id, period, period_start)` unique constraint.

That is the first metered call of every new day, for every active learner — the call a Beta
makes most often. It was invisible in testing because `main.start_write` issues
`BEGIN IMMEDIATE` on SQLite, which takes the write lock before the read, so the race cannot
form.

**Fix:** the insert now happens inside a savepoint (`db.begin_nested()`); losing the race
rolls back only the savepoint, and the winner's row is re-read under the lock and
incremented.

### F3 — A daily request quota was measured against a monthly counter *(fixed)*

`accounts.effective_policy` collapsed a cohort's two separate limits into one policy with
`period='month'`, then attached `request_quota_daily` as its `request_limit`. A cohort that
meant "50 requests a day" was enforced as "50 requests a month" — up to 31× the intended
allowance.

**Fix:** `effective_policies()` returns one policy per window, so each limit is measured
against the counter that corresponds to it. `usage_summary` gained a `windows` list and the
existing `limits`/`period`/`used` keys are unchanged, so the current assertions still hold
(`test_accounts.py:223` asserts `body['limits'] is None` for a fresh account — still true).

### F4 — The role the application accepts was the role the database rejected *(fixed)*

`main.require_admin` admits `{'admin', 'staff'}`. `004`'s `users_role_ck` allowed only
`learner`/`teacher`/`admin`. So an operator account with role `staff` could not be created on
a migrated database at all — a 500 on the insert, from the database, for a role the code
explicitly permits.

**Fix:** the CHECK is widened to `('learner','teacher','staff','admin')` in both `app/db.py`
(so a fresh database allows it) and `migrations/007` (so a migrated one does). The new
predicate is strictly wider, so no existing row can fail it.

### F5 — `usage_daily_rollup` is dead schema *(needs your decision)*

Defined in `app/db.py`, created by `004`, and **written by nothing and read by nothing** —
`usage_summary` queries `quota_counters` and `usage_ledger` directly. A full-tree grep for the
name returns only the model and the DDL.

It exists for a good reason: `usage_ledger` is append-only and unbounded, so any
month-over-month or per-model cost dashboard will eventually be a full scan. But right now the
table is an empty promise. Pick one before open Beta:

* **add the rollup job** (a nightly `INSERT ... SELECT ... GROUP BY user_id, date_trunc('day',
  to_timestamp(created_at)), feature, provider, coalesce(model,'')` with `ON CONFLICT DO
  UPDATE`), or
* **drop the table** and accept that cost reporting reads the ledger directly until it hurts.

I did not choose for you — it is a product decision about how much cost visibility the Beta
needs on day one.

### F6 — Redundant single-column indexes *(low, deliberate non-fix)*

`feedback_user_idx (user_id, created_at)` makes `ix_feedback_user_id` a strict prefix;
`tokens_user_expiry_idx (user_id, expires_at)` does the same to `ix_tokens_user_id`. They cost
writes and earn nothing. I left them: removing `index=True` from a column would change freshly
created databases without touching already-migrated ones — the exact divergence F1 exists to
remove. Consolidating them is a cleanup, not a Beta blocker.

### F7 — Migrations 001–003 have no `.sql` *(documentation)*

`init_db.py` accepts versions `None, 1..7`, and v1→v3 exists only as Python (the inline
`ALTER TABLE users ADD COLUMN training_consent`). `004` onward have reference DDL. So a
v1/v2/v3 database can be brought forward by this codebase but not by following the SQL folder.
Fine as long as the runbook below is the documented path; worth stating in the deploy notes.

---

## 3. What changed

| File | Change |
|---|---|
| `app/db.py` | `SCHEMA_VERSION` 6→7. New `BETA_INDEXES` (18 indexes) and `USER_CHECKS` (2 CHECKs), so `create_all` builds the same schema the migrations describe. Added the `desc` import. |
| `app/accounts.py` | New `_bump_counter()` (savepoint retry, fixing F2); `effective_policies()` + `effective_policy()` wrapper (fixing F3); `usage_summary` gained additive `windows`; `_window_totals()` helper; `IntegrityError` import. |
| `migrations/007_index_and_role_parity.sql` | **New.** Widens `users_role_ck` to accept `staff`; adds the explicit `quota_policies_global_unique` partial index; bumps `schema_version` to 7. Additive, idempotent, no row rewritten. |
| `scripts/schema_parity.py` | **New.** Machine-checks that the ORM and the reference DDL declare the same indexes. `--check` exits 1 on drift. |
| `scripts/init_db.py` | `KNOWN_VERSIONS` gained 7; docstring documents v6→v7. |

Not changed, on purpose: no new tables, no dropped columns, no type changes, and
`migrations/004..006` were not rewritten (they are shipped history).

---

## 4. Verification status

**I could not execute anything.** This session has no shell tool — no `python`, no `pytest`,
no `psql`, no `git`. Every claim above comes from reading the source; the concurrency and
index findings are reasoned from the code, not observed at runtime. The `274 passed, 1 failed`
figure in the session transcript is **not mine and I did not reproduce it**.

Run these, in this order, from `harness/backend`:

```bash
# 1. Does the ORM still import, and do the two build paths agree?
PYTHONPATH=backend python3 backend/scripts/schema_parity.py --check

# 2. Full suite
PYTHONPATH=backend python3 backend/scripts/test.py

# 3. The one test the transcript flagged as failing
PYTHONPATH=backend python3 -m pytest \
  backend/tests/test_multisubject.py::test_every_course_offers_a_citable_reference -q
```

**On F1's second half — the curriculum licence failure.** I read the code rather than trusting
the transcript. Both producers of a concept's `media` now route through
`policy.reference_entry()`, which stamps `licence`, `licence_class`, `scope` and
`status='reference_link'`:

* `app/curriculum.py:199` — the hand-authored mathematics course;
* `app/generated_curriculum.py:188` — `policy.reference_media(course_id)` for the other five.

A full-tree grep for `'media':` returns exactly those two sites. So the `KeyError: 'licence'`
the transcript reports is **not reproducible from the current source** — the fix appears to
have landed at 14:51, after the transcript's 12:51 snapshot. I did not "fix" anything, because
there is nothing left to fix that I can see. Command 3 above settles it; if it still fails even
though `reference_entry` is the only producer, the cause is somewhere I could not reach
without a shell (most likely an import-time shadowing of `reference_entry`).

---

## 5. PostgreSQL runbook

```bash
export HARNESS_ENV=production
export HARNESS_DATABASE_URL='postgresql://USER:PASS@HOST:5432/luminfest'
export HARNESS_SECRET="$(openssl rand -base64 48)"      # >=32 chars, >=12 distinct
export HARNESS_ALLOWED_HOSTS='luminfest.example.com'        # no '*'
export HARNESS_TUTOR_PROVIDER=openai
export HARNESS_TUTOR_URL='https://api.deepseek.com/v1'
export HARNESS_TUTOR_MODEL='<model>'
export HARNESS_MAIL_TRANSPORT=smtp
export HARNESS_SMTP_HOST=...   # the mailer raises rather than dropping a verify link

# A. Fresh database
PYTHONPATH=backend python3 backend/scripts/init_db.py

# B. Existing database — 004..007, in order, ON_ERROR_STOP=1
for f in 004_beta_multiuser 005_course_enrollment 006_session_tokens 007_index_and_role_parity; do
  psql "$HARNESS_DATABASE_URL" -v ON_ERROR_STOP=1 -f "backend/migrations/$f.sql"
done

# C. Prove A and B produced the same thing
PYTHONPATH=backend python3 backend/scripts/schema_parity.py --check
```

Rollout knobs already in the schema: `cohorts.rollout_stage` ∈
`internal|closed_beta|open_beta|general`; cohort-level `token_quota_monthly` /
`request_quota_daily`; every `quota_policies` row defaults to `enforcement='observe'`, which is
the right default for a Beta — meter first, limit later.

## 6. Recommended next steps

1. Run §4. Treat any failure there as blocking.
2. Decide F5 (rollup job or drop the table).
3. Extend `tests/test_schema_equivalence.py` to compare indexes and constraints, not just
   columns — or wire `schema_parity.py --check` into CI. Right now F1-class drift can only be
   caught by a human remembering to run the script.
4. Consolidate the redundant indexes from F6 in a v8 migration.
