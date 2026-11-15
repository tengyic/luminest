# Luminest — Web client

A browser-native React client for **Luminest**. Internal identifiers, the bundle
identifier and the on-disk data directory keep their historical `luminfest` spelling
on purpose -- renaming them would orphan existing installs and break the sim bridge. It is the
cross-platform counterpart to the macOS native app and talks to the **same** `harness/backend`
FastAPI service (`/api/v1`). It does **not** modify the backend.

> Paths below are shown from the repo root `harness/`. If you are in another directory, use the
> absolute path, e.g. `cd "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/webapp"`.

## Stack

- React 18 + TypeScript + Vite 5
- `react-router-dom` for routing
- Plain CSS (no UI framework)

## What it does

| Area | Endpoint(s) used | Status |
| --- | --- | --- |
| Auth (register / login / refresh) | `POST /auth/register`, `/auth/login`, `/auth/refresh` | ✅ |
| Capability matrix | `GET /capabilities` (anonymous) | ✅ |
| Curriculum / course map | `GET /curriculum` | ✅ |
| Build a course from text | `POST /create/course` → `POST /my-courses/{id}/enrol` | ✅ |
| Lesson viewer | `GET /lessons/{concept_id}` | ✅ |
| Practice quiz | `GET /questions/next` → `POST /attempts` | ✅ |
| Training telemetry consent | `POST /training/consent` | ✅ |

Not yet wired into the UI (backend already supports them): Interactive Board, Presentations,
Classroom, live voice, multimodal authoring. These are additive — the client degrades gracefully.

## Running locally

### 1. Start the backend

```bash
cd "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/backend"
env -u PYTHONPATH .venv/bin/python -m uvicorn app.main:create_app --factory --port 8766
```

> The backend uses `requirements.txt` (no `pyproject.toml`) and `uvicorn` ships as a module in
> `.venv`, so launch it as `python -m uvicorn`. The `env -u PYTHONPATH` line avoids a WorkBuddy
> sitecustomize shim that interferes with the sandbox.

### 2. Start the web client

```bash
cd "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/webapp"
npm install
npm run dev        # http://localhost:5173  (proxies /api -> http://localhost:8766)
```

Open <http://localhost:5173>, register an account, paste some text to build a course, then open a
lesson and practice.

## Building for deployment

```bash
npm run build      # outputs dist/
npm run preview    # serve the built bundle locally
```

For a production deploy, set `VITE_API_BASE` to your backend origin before building, e.g.
`VITE_API_BASE=https://api.luminest.example npm run build`. The client appends `/v1`, so the base
should be the origin (or a path that ends in `/api`). See `.env.example`.

## Notes on the contract

- Auth uses `Authorization: Bearer <token>`; on 401 the client transparently refreshes via the
  refresh token and retries once.
- Quiz grading is server-side. `GET /questions/next` returns a **signed receipt**; the client must
  echo it back on `POST /attempts` along with a `client_event_id` (idempotency key). The client
  never sees the correct answer — it only submits the chosen `option_id`.
- Telemetry events (`POST /events`) accept `heartbeat`, `lesson_view`, `simulation_interaction`,
  `modality_selected`, `interaction`, `external_simulation_opened`, each with a timezone-aware
  `occurred_at`. This client records consent but defers bulk event shipping to a future pass.

## Verification

`npm run build` runs `tsc --noEmit` then `vite build`; both must pass. The backend boot and the
`/api/v1/capabilities` endpoint were smoke-tested against a live local instance.
