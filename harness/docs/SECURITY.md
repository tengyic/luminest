# Security model — harness v1.4.0

Scope: the legacy harness in this working tree (FastAPI backend under `backend/app`, native
macOS client under `native/Sources`). This document describes the mechanisms that exist in
the code today, the boundaries that are enforced by structure versus by review, and the
gaps that are honestly open. It is a description, not a certification.

**No security certification is claimed.** There is no SOC 2 / ISO 27001 attestation, no
independent penetration test, and no third-party audit of this tree. "Structurally enforced"
below means the backend will refuse the request at runtime; it does not mean an adversary
has been exhaustively modelled.

## 1. Authentication and sessions

- Passwords are hashed with Argon2 (`backend/app/security.py:20`,
  `PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)`). Verification failures
  run through a dummy hash so an unknown user is not distinguishable by timing alone.
- Credentials are short-lived bearer tokens: access TTL 3600 s, refresh TTL 60 days,
  e-mail verification TTL 3 days, password-reset TTL 1 hour (`security.py:23-27`). Tokens
  are looked up by their SHA-256 digest, never by the raw secret (`security.py:30`,
  `:186`).
- **One resolver.** `security.resolve_account` is the only place the `Authorization`
  header is parsed and the token, rate limit, account status and erasure check are applied
  (`security.py:144-195`). Route modules must not carry their own copy of this logic; the
  scheme comparison is case-insensitive per RFC 7235 and credentials passed in query
  parameters (`?t=`, `?token=`, `?access_token=`) are treated as credentials at the HTTP
  boundary (`security.py:52-101`).
- **Two structural checks keep a new route from bypassing the resolver:**
  1. `security.routes_without_principal` walks FastAPI's real dependency graph — including
     included routers and WebSocket routes — and fails any route that can answer without a
     resolver unless it is on the reviewed `security.PUBLIC_ROUTES` decision list
     (`security.py:257-289`, `:325`).
  2. The HTTP boundary middleware refuses (`401`) any < 400 response to a request that
     carried a credential but never set `request.state.principal_resolved`, unless the
     matched route is public (`backend/app/main.py:945-978`). A hand-rolled dependency with
     different spelling still produces a 200, which the boundary throws away.
- Per-route-family rate ceilings are preserved as parameters of the single resolver (180
  API, 900 playground, 120 media; `security.py:144`, `:153-155`).
- Production boot is fail-closed in `backend/app/config.py:248-255`: `HARNESS_ENV=production`
  requires PostgreSQL (`postgresql+psycopg://`), a `HARNESS_SECRET` of at least 32
  characters with at least 12 distinct characters, and explicit `HARNESS_ALLOWED_HOSTS`
  with no `*`; a remote tutor URL must be HTTPS (`:277-280`) and a configured model is
  mandatory (`:283`). Signup age attestation and Terms acceptance default on, and an
  invited cohort gate defaults on, in production (`:306-311`). The desktop build is
  deliberately production-strict on consent while staying on SQLite (`:299-301`).

## 2. Tenant isolation — what is structurally enforced

`backend/app/user_scope.py` turns "remember to filter by `user_id`" into a runtime
constraint. It installs a `do_orm_execute` event listener on SQLAlchemy's `Session` class
when the module is first imported, so every session in the API, scripts and tests runs
under the same rule (`user_scope.py:42-46`, `:214-221`).

- Every ORM `SELECT` that reads a table in the reviewed `USER_SCOPED_TABLES` list must carry
  a `user_id` predicate or a primary-key predicate, otherwise the query raises
  `UnsafeQueryError` (`user_scope.py:67-96`, `:168-208`). The list is a decision, not a
  pattern: it includes the v13 learner-owned tables `interactive_artifacts`,
  `interactive_evidence`, `learner_concept_facets`, `learner_concept_edges` and
  `concept_evidence_ledger`, alongside sessions, attempts, messages, projects and grades.
- Deliberate allowances, each reasoned in the module docstring (`user_scope.py:26-40`):
  - **Primary-key lookups** (e.g. `db.get(Token, digest)`) need no `user_id` predicate —
    the digest/UUID is unguessable.
  - **`unscoped(reason)`** is an audited escape hatch for cross-user reads by design. It
    requires a non-empty reason, logs a warning and appends `(epoch, reason, tables)` to a
    process-local `deque` (`user_scope.py:111-149`). Reviewers can enumerate every place
    that deliberately reads across users.
  - **Non-ORM statements (`text()`), DDL/migrations and writes are not inspected.** This is
    a read guard; writes are bounded by foreign keys and by code review.
- A 500 on an unscoped query is the guard working, not a flaky database. The fix is a
  `user_id` predicate or an explicit, reviewed `unscoped()` call — never a suppression of
  the guard.
- The guard's audit trail is process-local (`_AUDIT`, max 1000 entries). The module notes
  that a production deployment *should* ship these events to the admin audit log; that
  shipping is not implemented here. `unscoped_events()` exists for tests and audit tooling.

## 3. What remains external / code-review-bounded

These are real boundaries of the claim, not footnotes:

- Raw SQL (`text()`), DDL, migrations and all writes are outside the ORM read guard. Their
  correctness (including `user_id` columns on new tables) depends on schema discipline and
  review. The v13 migration states the tenancy rule explicitly: every learner-owned table
  gets `NOT NULL user_id ... ON DELETE CASCADE` **and** an entry in `USER_SCOPED_TABLES` in
  the same change (`backend/migrations/012_2_0_substrate.sql:14-16`).
- `unscoped()` is only as safe as its reviewers. The reason string is mandatory and logged,
  but the cross-user reads themselves are permitted by design.
- Admin surfaces use per-route checks, not the tenant guard: `require_admin` allows roles
  `admin`/`staff` (`main.py:4514`), and summative project grading additionally requires the
  reviewer e-mail to be configured in the assessment book (`main.py:2725-2732`). These are
  authorisation decisions in individual handlers, reviewed rather than structurally
  enforced for every future route.
- The erasure ledger lives outside the database and must be readable; an unreadable ledger
  is a `503` that refuses credentials, not an assumed "no erasures" (`security.py:104-126`).
- Secrets: the runtime model-config override stores the provider key in
  `<data_dir>/model_config.json`, inside the same trust boundary as the application
  database. `GET` reports only `api_key_set`, never the key; operators who do not want a
  persisted key can configure entirely through environment variables
  (`backend/app/model_config.py:20-24`). On-disk permissions must be set by the operator.
- No threat model, adversarial review or external security assessment is part of this
  tree. Public hosting (TLS + PostgreSQL + invitations + remote voice) was **not**
  end-to-end accepted in the alpha verdict (`docs/ALPHA_VERDICT_2026-11-15.md`, §6).

## 4. Data erasure

The deletion policy is stated once, as data, in `backend/app/account_erasure.py` (`:1-29`,
`:79`); `backend/legal/privacy.md` §7 restates it for readers, and the code is authoritative
when they disagree.

- **Cascade.** Deleting the `users` row with `PRAGMA foreign_keys=ON` removes rows with
  `ON DELETE CASCADE` (25+ tables plus children cascading through receipts/attempts and
  feedback events). The deletion path does not re-list them; it reads the live schema via
  `foreign_key_fates`, and a test fails if a new `users`-referencing table is neither
  `CASCADE` nor `SET NULL` (`account_erasure.py:9-16`). `SET NULL` tables keep their row and
  lose the reference; `feedback` is the one `SET NULL` table whose content is the learner's
  own words, so those rows are removed explicitly (`:65-69`). Per-account directories
  (`workspaces`) are deleted with the account (`:71-73`).
- **Erasure ledger.** A snapshot restore replaces the database file wholesale, so the
  tombstone lives outside it at `<data_dir>/erased_accounts.jsonl`: append-only, fsync'd,
  one line per erased account id. It survives restores and WAL checkpoints and holds only
  the opaque account UUID, a timestamp and counts — never e-mail, name or learner content
  (`:18-28`, `:62-63`). On boot and on **every authenticated request** the id is re-purged
  rather than trusted (`security.py:104-142`). This is why an expired-but-valid token from a
  deleted account cannot keep returning data.
- **Backups are the residual.** Plaintext whole-database snapshots live under
  `<data_dir>/backups/` and are the only place a deleted account can still exist. The
  retention window is imported from `database_backup.py` so the sweep and the deletion
  receipt cannot drift (`account_erasure.py:42-59`). The sweep keeps the newest usable
  snapshot of each kind even when older than the window and caps the directory, so a flat
  claim of "erased after N days" would overstate the policy; the policy text says so.

## 5. Dependency advisory status

Recorded in `docs/DEPENDENCY_ADVISORIES.md`. Honest summary at the time of writing: a
fresh installed-development-environment scan (2026-11-16) still reports advisories; they
are **not** fixed by this work. The CI-authoritative `pip-audit -r <requirements>` scans
could not be reproduced locally because pip-audit's helper venv creation fails here
(`ensurepip` abort). No suppression flags were used, and no finding is claimed resolved.
