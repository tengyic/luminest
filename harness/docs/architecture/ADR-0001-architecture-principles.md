# ADR-0001 — Architecture principles

- **Status:** accepted
- **Date:** 2026-11-08
- **Scope:** the whole `harness/` tree — Python backend, Swift app, browser UI
- **Deciders:** architecture governance pass

This is not a list of things that are generally true of software. Each principle below is
stated because this repository has already paid for violating it, names where the violation
is recorded, and says honestly whether a machine enforces it today or only a reviewer does.
Where a number appears, it was measured on the tree at the date above and the command that
produced it is given.

Companion records: [ADR-0003](ADR-0003-native-boundaries.md) for the native source
layout, [ADR-0004](ADR-0004-api-contract-discipline.md) for the HTTP surface,
[ADR-0005](ADR-0005-database-migration-policy.md) for the schema,
[ADR-0006](ADR-0006-no-duplicated-business-logic.md) for cross-surface duplication.

---

## 1. A boundary is a directory until it is a target

**Rule.** Code may be grouped into directories (`backend/app/api/v1/`,
`native/Sources/LearningHarness/Shared/`, `.../Features/`), but a directory does not stop
one file calling another. Do not describe it as an enforced boundary. Either the toolchain
enforces the edge (a Python package with an import-linter, a separate SwiftPM target) or the
boundary is a review convention and must be labelled as one.

**Why here.** The Swift package has exactly one executable target:

```
native/Package.swift:13-19  products: [.executable(..., targets: ["LearningHarness"])]
                            targets: [.executableTarget(name: "LearningHarness", ...)]
```

`Shared/` and `Features/Board/` exist and are meaningful, but every file still sees every
other file. ADR-0003 already records the decision and its price
(`docs/architecture/ADR-0003-native-boundaries.md:67-90`): splitting into modules would
force `internal` types to `public`, break `@testable import`, and move the resource bundle.
On the Python side `backend/app/api/v1/` is a real package, but nothing forbids a feature
module importing the composition root — and three of them do, for `start_write`:
`backend/app/routes_flash.py:39`, `backend/app/routes_procedure.py:69`,
`backend/app/routes_supervision.py:50`.

**What is enforced.** Not the import direction. What *is* enforced is that a feature module
named in the router list exists, is mounted, and ships: the tuple in
`backend/app/feature_routers.py:27-41` is read by `main.create_app`
(`backend/app/main.py:4214-4222`), declared to PyInstaller by `scripts/package.py`, and
checked by `backend/tests/test_feature_routers.py`. That is a boundary in the deployment
sense — a capability cannot silently vanish from the frozen app — not an import boundary.

**Enforcement status:** convention for import direction (ADR-0003); test + packaging gate
for "a listed capability must exist and be mounted".

---

## 2. One resolver for authentication

**Rule.** Only `backend/app/security.py` parses an `Authorization` header or a credential
query parameter. Every route reaches the account through `resolve_account`,
`resolve_optional_account`, `require_principal` or `require_optional_principal`. A route
module may wrap the resolver in a local dependency, but it may not re-implement the token
lookup.

**Why here.** This is the most expensive incident in the repository. Twelve route modules
carried their own copy of the bearer parsing, each documented as "line-for-line identical to
`main.authenticated`". They had forked, and none of them consulted the erasure ledger, so a
deleted account's still-valid token kept returning its flashcards, decks and courses. The
account of the incident is at `backend/app/security.py:44-52` and
`backend/app/main.py:880-884`; the test file's header explains why the first, textual guard
failed — it matched four literals across eleven hardcoded module names, and a dependency
spelled `request.headers.get('Authorization')` walked straight past it
(`backend/tests/test_account_auth_single_source.py:1-22`).

The number is **twelve**, not fourteen. No commit in this repository separately records the
incident: the history is 16 commits and the code arrived in the squash "Ship current
Luminfest work". The only contemporary evidence is the comments and the test. (The number
"fourteen" does appear in this codebase, but it is the backup retention ceiling — 10
ordinary backups + 4 anchors — at `backend/app/database_backup.py:223`, not an auth count.)

**How it is enforced — three layers, all currently green:**

| Layer | Mechanism | Location |
| --- | --- | --- |
| Route graph | every `APIRoute` must have a resolver in its dependency tree unless it is in `PUBLIC_ROUTES` | `backend/app/security.py:296` (`routes_without_principal`), asserted in `backend/tests/test_account_auth_single_source.py` |
| HTTP boundary | any 2xx to a request that carried a credential, from a route that never set `principal_resolved`, is replaced with 401 | `backend/app/main.py:845-868` |
| Per-family behaviour | a deleted account's token gets 401 from one endpoint of every route family, after a real snapshot restore | `backend/tests/test_account_auth_single_source.py` (last test) |

The guard added in this pass
(`backend/tests/test_architecture_guards.py::test_no_module_outside_security_parses_the_authorization_header`)
is a cheap fourth check: no source line outside `security.py` may read the header. It is
deliberately textual and deliberately subordinate to the three behavioural layers above; it
catches the careless reintroduction, not a determined one.

---

## 3. Errors have one shape

**Rule.** An error is `{"detail": <string>}` with the HTTP status carrying the class of
failure. Raise `HTTPException(status, "message")`; let the boundary return
`JSONResponse({"detail": ...})`. Do not invent a second envelope (`{"ok": false, "reason":
...}`, `{"error": ...}`) in a new route.

**Why here.** Three surfaces consume these responses — the Swift `APIClient` turns `detail`
into user-facing failure text (`native/Sources/LearningHarness/Shared/Networking/APIClient.swift:96`),
the browser shows it directly, and tests assert on it. A second shape is invisible until a
client hits that one endpoint.

**What is true today (measured):**

- 236 `HTTPException(` call sites across `backend/app/*.py` and `backend/app/api/v1/*.py`.
- 7 boundary returns of `JSONResponse({'detail': ...})` in `backend/app/main.py`.
- Two modules return a different envelope:
  `backend/app/routes_deck.py:330` and `:365` return `{"ok": false, "reason": ...}` with 503;
  `backend/app/playground_routes.py:420` forwards a structured result with 503.

Those three are pre-existing exceptions. They are listed here rather than silently
grandfathered: a new route may not add a fourth. If the deck/playground envelopes are ever
unified, ADR-0004's contract instrument is where the change becomes visible.

**Enforcement status:** nothing systematic. Individual tests assert specific messages;
there is no test that forbids a new error shape. A guard would have to whitelist the three
existing sites, and that whitelist is the honest form of the rule.

---

## 4. Configuration is read through `Settings`

**Rule.** Application code takes a `Settings` object (`backend/app/config.py:60`) or reads
`app.state.settings`; it does not call `os.getenv` itself. `Settings.from_env()` is the one
place environment variables become configuration.

**Why here.** `Settings` is passed explicitly through `create_app` and stored on
`app.state` (`backend/app/main.py:764`), so a test can build an app with a throwaway data
directory and no real environment. A module that reads `os.getenv` at call time escapes that
control and cannot be tested by constructing a `Settings` — the exact failure the test
fixtures in `backend/tests/conftest.py` exist to prevent.

**What is true today:** 23 direct reads of `os.environ`/`os.getenv` outside
`backend/app/config.py`. They cluster in provider adapters that deliberately own their own
credentials:

- `backend/app/database_backup.py:570,603` — backup encryption key (injectable `environ`)
- `backend/app/accounts.py:60-88` — mail transport and SMTP credentials
- `backend/app/memory.py:120-126` — scheduler selection and FSRS parameters
- `backend/app/harness/diagram.py:699-705` — diagram provider endpoint/key/model
- `backend/app/harness/vla.py:173`, `backend/app/harness/chromium_search.py:86-91` —
  optional vision/browser providers
- `backend/app/ingest/policy.py:289`, `backend/app/source_extension.py:412` — operator
  kill switches

These are a de-facto exception list, not a licence. A new feature reads `Settings`; if it
needs a provider credential, it belongs in one of the adapter modules above and should be
added to this list in the same change.

**Enforcement status:** none. This ADR is the list; there is no lint.

---

## 5. A policy number lives in one place and is quoted, never retyped

**Rule.** A number that a user-facing promise depends on is a named constant, and every
document or client that states it quotes the constant or is bound by a test to it. Two
literals typed in different months is how a policy document ends up promising a window the
code does not honour.

**Why here.** `backend/legal/privacy.md:139-179` makes three quantitative promises about
backup retention. The numbers live in `RETENTION_MAX_BACKUPS`, `RETENTION_MAX_ANCHORS`,
`RETENTION_MAX_PRE_RESTORE`, `RETENTION_MAX_AGE_DAYS`
(`backend/app/database_backup.py:216-223`), are read through `RETENTION` (`:288`), and the
document is asserted against those constants — no literal `10`, `14`, `30`, `3` or `4`
appears in the assertions (`backend/tests/test_account_deletion.py:617-641`). The deletion
receipt quotes the same constant rather than a copy
(`backend/app/account_erasure.py:56-60`).

The same principle already binds token lifetimes: `Settings.access_token_ttl` and
`security.ACCESS_TTL_SECONDS` were found disagreeing (7 days vs 1 hour) and now a test
pins them equal (`backend/tests/test_security_contract.py:24-31`).

**Where it is not yet true.** The Swift launcher states the schema version a second time:
`expectedSchemaVersion = 11` at `native/Sources/LearningHarness/BackendLauncher.swift:100`,
against `SCHEMA_VERSION = 11` at `backend/app/db.py:75`. `native/Tests/.../BackendLauncherTests.swift:82-98`
hardcodes 11 as well, so the Swift constant and its test would move together and neither
would notice the backend moving. That is the counter-example, not the model;
[ADR-0006](ADR-0006-no-duplicated-business-logic.md) records the missing binding and this
pass adds one (`test_swift_schema_mirror_matches_the_backend`).

**Enforcement status:** tests for retention and TTL; a new guard for the schema mirror; no
general mechanism.

---

## Consequences

- A contributor can tell, for any boundary, whether a broken rule is a build failure, a test
  failure, or a review comment. All three are legitimate; calling a convention "enforced"
  is not.
- Two of the five principles (1 and 4) are conventions with an explicit exception list.
  That is a deliberate choice: the compiler-level alternative for the native target costs a
  public API and the resource-bundle proof documented in ADR-0003, and a lint for
  `os.getenv` would have to whitelist 23 call sites on the day it was written.
- The guard file added alongside this ADR fails on drift in the two places where drift has
  already happened: a second auth parser and a stale schema mirror.
