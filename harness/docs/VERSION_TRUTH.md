# Version truth — sources and checker

## Why this document exists

The tree carries several version numbers that are legitimately different. Treating them as
one number would either mask real drift or "fix" a working system by relabelling artifacts.
`scripts/check_version_truth.py` reports the distinction explicitly and fails on actual
drift. It is **read-only**: it never edits a source file.

## The namespaces and their single sources of truth

| Namespace | Source(s) of truth | Expected | Relationship |
| --- | --- | --- | --- |
| Schema (coupled) | `backend/app/db.py:75` `SCHEMA_VERSION = 13`; `native/Sources/LearningHarness/BackendLauncher.swift:100` `expectedSchemaVersion = 13` | `13` | The two must match. `BackendLauncherTests` parses `db.py` and the packager refuses a frozen/source mismatch (`scripts/package.py:1054-1059`), so drift is already a red test/red build — this checker makes it visible in one place. |
| Marketing (shipped line) | `scripts/package_beta.py:36` `VERSION = "1.4.0"`; `docs/closed-beta/DISTRIBUTION.md` records `CFBundleShortVersionString = 1.4.0` | `1.4.0` | Cross-namespace equality is required for these two. |
| Marketing prerelease (allowlisted) | `beta_control/server.py:70` default `"1.4.0-beta.1"` | prefix `1.4.0-` | A beta child of the marketing line, not a competing version. The file is operator-owned and only read here. |
| Packaging / artifact records (allowlisted) | `DISTRIBUTION.md` recorded artifact `1.2.0`; `scripts/release_kit.py` example `1.1.16` | one of `1.1.16`, `1.2.0` | Historical/observed builds. They differ from `1.4.0` **by design** — their difference is not drift, but drift to any other value is. See `CHANGELOG.md`, which notes versions are those passed to `scripts/package.py --version`. |
| Packaging dev default (allowlisted) | `scripts/package.py:1524` `--version default="1.0.0"` | `1.0.0` | A developer fallback, not a release truth. |

The allowlists live as named constants with comments at the top of the checker
(`EXPECTED_MARKETING_VERSION`, `BETA_PRERELEASE_PREFIX`, `ALLOWED_PACKAGING_RECORDS`,
`ALLOWED_PACKAGING_DEFAULTS`). Adding a new legitimate packaging version is a deliberate edit
to that allowlist with a comment explaining why — not a silent relaxation of the check.

## How to run

```sh
cd /Users/tengyi/WorkBuddy\ AI/2026-10-10-18-14-50/harness
python3 scripts/check_version_truth.py
echo "exit=$?"
```

Expected (healthy tree): eight `OK` rows and

```
PASS: 8 version sources consistent across their namespaces. No files were modified.
exit=0
```

Exit codes:

- `0` — every source agrees with its namespace allowlist.
- `1` — at least one source is missing, unparseable, or outside its allowlist. Each failure
  is printed with observed and expected values. Nothing is modified on either path.

The checker resolves the repository root from its own location (`Path(__file__).parent.parent`),
so it can be run from any working directory. It has no third-party dependencies.

## Verification performed for this audit

- `python3 scripts/check_version_truth.py` → 8/8 OK, exit `0`.
- A drift test copied the eight sources to a temporary directory, changed only the copied
  `db.py` to `SCHEMA_VERSION = 99`, pointed the checker at that copy, and confirmed the
  checker reported `backend/app/db.py` observed `99` as `DRIFT` while leaving the real tree
  untouched. No source file in this working tree was modified by the test.

## Operational note

Backend and native engineers were editing `backend/app/db.py`, `beta_control/server.py` and
the migrations in parallel with this audit. Re-run the checker against the final tree before
using its output as a release gate; a value that is correct today may legitimately have
moved, in which case update the expected constant/allowlist deliberately and note the
reason here.
