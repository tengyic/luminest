# Luminest closed-beta control server

A single Python process (standard library only) that owns the four things a
closed beta needs and that a static landing page cannot provide:

| Concern | Endpoint | Behaviour |
| --- | --- | --- |
| Share codes | `POST/GET/DELETE /api/beta/codes` | operator issues / lists / revokes; admin token required, disabled entirely when unset |
| Token management | `POST /api/beta/redeem`, `GET /api/beta/verify` | code → 30-day session token; single-use by default, expiry + addressed-email enforced |
| User data collection | `POST /api/beta/collect`, `GET /api/beta/collect/schema` | **fail-closed**: live token + explicit `consent: true` + whitelisted fields, otherwise nothing is stored |
| Remote updates | `GET /api/updates/manifest.json`, `POST /api/updates/manifest` | versioned artifact list with mandatory sha256 |

It also serves the landing page, `downloads/` (the macOS bundle), `app/` (the
browser build of Luminest) and reverse-proxies `/api/v1/*` to the FastAPI
backend — that proxy is what makes the web version work on iPad, Windows,
Linux and older macOS from the same origin without adding CORS to the backend.

## Run

```bash
cd "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/beta_control"
LUMINEST_BETA_ADMIN_TOKEN='a-long-random-string' sh run.sh
# → http://127.0.0.1:8788  (binds 0.0.0.0, so reachable from other devices on the LAN)
```

Zero dependencies: Python 3.9+, SQLite, `python3 -m http.server`-style static
serving. Runs on a Raspberry Pi, a spare Mac mini, a VPS, or the single-port
publishing sandbox (`PORT` is honoured and it binds `0.0.0.0`).

## Issue codes

```bash
curl -sS -X POST http://127.0.0.1:8788/api/beta/codes \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer a-long-random-string' \
  -d '{"count":10,"max_uses":1,"expires_in_days":30,"scope":"beta"}'
```

`scope: "beta"` unlocks downloads; `scope: "demo"` unlocks only the browser demo.
Codes are also mirrored into the FastAPI backend's `beta_invites` table when
`LUMINEST_BACKEND_DB` points at the same SQLite file — set
`HARNESS_REQUIRE_INVITE=1` there so both layers enforce one source of truth.

## Decisions made (see `docs/closed-beta/ACCESS.md`)

- **Email is an identifier, not an authentication factor.** No verification email,
  no magic link. The backend `Mailer` falls back to logging without SMTP, and a
  small device has no mail transport. The share code is the credential, issued
  out of band. This also removes the landing page's old contradiction
  ("check your inbox" while storing nothing).
- **No billing in beta.** `HARNESS_ALPHA_FREE=1`; the capability matrix reports
  `billing_required: false`. No card, no payment provider, no Plus upsell.
- **Collection is opt-in and minimal.** Only `platform / app_version / event / note`.
  Never window titles, keystrokes, passwords, share codes, lesson content or
  payment data. 90-day retention, withdraw by stopping submissions.

## Verify

```bash
env -u PYTHONPATH python3 -m unittest discover -s "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/beta_control" -p 'test_*.py' -v
curl -sS http://127.0.0.1:8788/api/health
curl -sS http://127.0.0.1:8788/api/beta/config
```
