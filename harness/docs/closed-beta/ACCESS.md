# Closed-beta access, token management and data collection

## What already existed (no reinvention)

`harness/backend` already shipped a complete invite subsystem, verified in source:

| Piece | Location |
| --- | --- |
| `BetaInvite` / `InviteRedemption` tables | `app/db.py:413` / `:432` |
| `require_invite` setting | `app/config.py:87` |
| Register gate (403 on bad/missing code) | `app/main.py:988` |
| `/admin/invites` GET / POST / DELETE | `app/main.py:4277–4318` |
| `InviteCreate` schema | `app/schemas.py:97` |
| `new_invite_code`, `find_invite`, `invite_is_redeemable` | `app/accounts.py` |
| `Mailer` (SMTP or dev log) | `app/accounts.py:43` |

So the "small server" is **not** a second auth system. It is a thin control plane
that owns the operator workflow and mirrors codes into the same `beta_invites`
table when `LUMINEST_BACKEND_DB` points at the backend SQLite file.

## The small server

`harness/beta_control/server.py` — one Python process, **standard library only**,
SQLite file, no pip install, no Redis, no managed DB. Runs on a Raspberry Pi, a
spare Mac mini, a $5 VPS, or the single-port publishing sandbox (`PORT`, binds
`0.0.0.0`). Start with `sh harness/beta_control/run.sh`.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health`, `/api/beta/config` | liveness + public decisions |
| `POST/GET/DELETE /api/beta/codes` | operator issues / lists / revokes share codes |
| `POST /api/beta/redeem` | code → 30-day session token (single-use, expiry, addressed email) |
| `GET /api/beta/verify` | token validity + `downloads_unlocked` |
| `POST /api/beta/collect` | consent-gated user data |
| `GET/POST /api/updates/manifest[.json]` | remote update manifest |
| `ANY /api/v1/*` | reverse proxy to the FastAPI backend (same-origin web client) |
| `ANY /*` | static site, SPA-aware; `/downloads/*` gated server-side |

Verification: `12/12` unittest cases pass, including single-use, revoke,
consent fail-closed, field allow-listing, download gating, sensitive-file
blocking, and token redaction in access logs.

## Decision 1 — email auth: **NO verification email**

Email remains an **identifier** (`Register.email` is required by the backend),
but it is not an authentication factor and no mail round-trip is required.

Evidence: `Mailer.from_env` falls back to writing messages to the log when
`HARNESS_SMTP_HOST` is unset (`app/accounts.py:82–92`). A small device has no
mail transport. The share code, distributed out of band, is the credential.
This also removes a documented contradiction on the old landing page: it said
"You're in the queue — check your inbox for confirmation" *and* "nothing is sent
anywhere from here" (`outputs/LUMINEST-WEBSITE-PROMPT-PACK.md` §0.6 B3).

Optional: when SMTP is configured, `POST /api/beta/codes` with an `email` field
can still mail the code via the backend admin flow. Nothing depends on it.

## Decision 2 — no billing

`HARNESS_ALPHA_FREE=1` on the backend. `capabilities.resolve()` now also returns
`billing_required: false`, `cohort: "closed-beta"`, and an empty `paid_plan`
during the beta; Plus capabilities resolve as `enabled` with the reason
"Free for every account during the closed beta". The old
"Pay to enable it" string is unreachable in this configuration.

## Decision 3 — collection is fail-closed

A record is written only when **all** hold:

1. a live, non-revoked session token,
2. `consent: true` explicitly in the body,
3. an allow-listed field set (`platform`, `app_version`, `event`, `note`).

Missing consent and bad tokens both return 403 and store nothing. The allow-list
also drops any extra field (a test sends `password` and asserts it is absent from
both the response and the stored row). Never collected: window titles,
keystrokes, passwords, share codes, lesson content, payment data. 90-day
retention; withdraw by stopping submissions.

## Operator runbook

```bash
# 1. backend: enforce the same codes
cd "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/backend"
HARNESS_REQUIRE_INVITE=1 HARNESS_ALPHA_FREE=1 \
  env -u PYTHONPATH .venv/bin/python -m uvicorn app.main:create_app --factory --port 8766

# 2. control server (same SQLite file for the mirror)
cd "../beta_control"
LUMINEST_BETA_ADMIN_TOKEN='<long-random>' \
LUMINEST_BACKEND_DB='<absolute path>/harness.sqlite3' \
LUMINEST_BACKEND_URL='http://127.0.0.1:8766' \
LUMINEST_SITE_DIR='<absolute path>/outputs/closed-beta-site' \
PORT=8788 sh run.sh

# 3. issue 10 codes
curl -sS -X POST http://127.0.0.1:8788/api/beta/codes \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer <long-random>' \
  -d '{"count":10,"max_uses":1,"expires_in_days":30,"scope":"beta"}'
```

Codes are `LUMINEST-XXXX-XXXX`, upper-cased by `accounts.find_invite()`, so the
same string works on both the control server and `/api/v1/auth/register`.
