# Web client — fixes delivered in this pass

Source: `harness/webapp/` (React 18 + TypeScript + Vite 5). It calls the same
`harness/backend` FastAPI service through `/api/v1`, and does not fork the API.

## Fixes

| # | Fix | Evidence |
| --- | --- | --- |
| 1 | **Brand Q0 resolved** — all user-visible `Luminfest` → `Luminest` across `webapp/`, `web/`, native strings and backend human-facing strings; internal identifiers preserved | `scripts/rename_frontend_brand.py --check` → 0 residual; see `BRAND_DECISION.md` |
| 2 | **Production base path** — Vite previously emitted `/assets/...`, which 404s when the site serves the client under `/app/`. `base: mode === 'production' ? '/app/' : '/'` | `vite.config.ts`, rebuild passed |
| 3 | **PWA for iPad** — `public/manifest.webmanifest` (`standalone`, `/app/` scope, theme colour) + `public/sw.js` caching the app shell only; API responses are never cached (they carry bearer tokens) | `dist/manifest.webmanifest`, `dist/sw.js` |
| 4 | **Share code in registration** — the field existed but was labelled "Invite code (optional)"; now "Share code (required for the closed beta)", with an honest note that email is identifier-only and no payment data is collected | `src/pages/Register.tsx` |
| 5 | **No billing** in the capability matrix — `capabilities.resolve()` now returns `billing_required: false`, `cohort: "closed-beta"`, empty `paid_plan`, and a beta-specific free reason | `backend/app/capabilities.py` |
| 6 | **Beta server 12/12 tests** including the privacy bug found in this pass: `/api/beta/verify?token=…` wrote the session token to stderr. `log_message` now redacts every query string | `beta_control/server.py`, `test_server.py::test_12` |
| 7 | **Server-side download gating + internal files blocked** — `/downloads/*` requires a beta-scope token; `seed_codes.json`, `server.py`, `*.db` return 403 | `test_server.py::test_10`, `::test_11` |
| 8 | **Dead landing variant fixed** — `outputs/luminest-beta/` had no `index.html` (blank page); now a 3-second redirect plus an explanation | `outputs/luminest-beta/index.html` |
| 9 | **Stale manifest field** — `outputs/luminest-download-site/download-manifest.json` still said `"bundle_name": "Luminfest"` | now `"Luminest"` |
| 10 | **README paths** — the earlier webapp README used `cd harness/backend`, which failed from `~`; absolute paths were already added in the previous pass and are retained | `harness/webapp/README.md` |

## Verified contract (previous pass, re-confirmed here)

`Authorization: Bearer <token>`; register → `{token, refresh_token, user}`;
`GET /capabilities` → `{capabilities:[{id,state,…}]}` (13 entries, `state` field
present); `GET /curriculum` → `{concepts:[…]}`;
`POST /create/course` → `{course:{id}, enrolled:false}` then
`POST /my-courses/{id}/enrol`; `GET /lessons/{id}`; `GET /questions/next` returns
a signed `receipt`; `POST /attempts` requires `question_id`, `option_id`,
`receipt`, `client_event_id`, `elapsed_seconds` and grades server-side.

## Build / run

```bash
cd "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/webapp"
npm install && npm run dev        # http://localhost:5173, /api proxied to :8766
npm run build                     # tsc --noEmit + vite build → dist/
```

For the published site, `package_beta.py` copies `dist/` into
`outputs/closed-beta-site/app/`; the control server serves it at `/app/` and
proxies `/api/v1/*` to the backend, so no CORS change is needed in the backend.
