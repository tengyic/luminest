# Staging build — Lumen Harness (unsigned)

Runbook for the unsigned staging artifact produced during the 2026-11-11 shipping-audit
follow-up. This is **not** a release.

## What it is

- `outputs/staging/lumen-harness-staging-a7bfb6d5b433.tar.gz` — a source snapshot built with
  `git archive HEAD` from commit `a7bfb6d5b433e25518a05b97f3fef6fe94881c96`.
- Tracked files only. It contains no `.env`, no `model_config.json`, no `*.sqlite3`, no
  `*.pem`, no `*.key`.
- It carries `STAGING-MARKER.md` inside the archive declaring it **UNSIGNED — no codesign,
  no notarization, not shippable, not distributable**.

## Verify

```sh
shasum -a 256 -c outputs/staging/lumen-harness-staging-a7bfb6d5b433.tar.gz.sha256
# expected: outputs/staging/lumen-harness-staging-a7bfb6d5b433.tar.gz: OK
```

sha256 = `e7c2c8f51d9020348618a0d94a6f0033ab6816fb683500e7de09767a5df7f29e`

## What it is not

- It is not signed or notarized. Distributing it as-is would ship an unverified binary
  surface; a signed, notarized artifact remains blocked on credentials (see `CHANGELOG.md`
  → `## Unreleased` → `### Pending`).
- It is not the commit. It is a HEAD snapshot for QA; the Phase 4 docs/evidence/CI changes
  and the `requirements-dev.txt` test-dependency declaration land in the commit, not here.

## Rollback

See `harness/ROLLBACK.md` (C-12): `git checkout a7bfb6d…` plus `shasum -a 256 -c`. No secret
or `model_config` restore, no key rotation.
