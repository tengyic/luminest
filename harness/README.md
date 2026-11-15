# Luminfest Learning Harness

An AI-assisted learning harness: a learner registers, gets a personalised plan, works
through lessons, practices, reviews, authors courses, talks to a tutor, and owns their
data — across a **native macOS app**, a **static web workbench**, and a shared
**FastAPI backend**. Every external learning resource (textbook, image, video,
simulation) is gated by a single fail-closed licence policy before it is shown.

> Verified state (2026-11-14): the **native journey gate is all-green — 10/10 journeys
> pass**, `appExitCode=0`, backend database verified. See
> [`outputs/native-qa/journey-full-10/`](outputs/native-qa/journey-full-10) and the
> *Native journey gate* section below.

---

## What is in the box

| Surface | Path | Stack | Notes |
| --- | --- | --- | --- |
| Backend API | `backend/` | FastAPI (Python 3) | App factory at `app/main.py:create_app`; SQLite by default, PostgreSQL via `HARNESS_DATABASE_URL`. |
| Native app | `native/` | SwiftUI on macOS (SwiftPM) | SwiftPM target `LearningHarness`; bundle `LuminfestLearningHarness`. Builds to `.build/release/LearningHarness`. |
| Web workbench | `web/` | Vanilla JS/CSS, **no build step** | Static; the backend can serve it as-is. Preview a simulation, select parts, ask the AI. |
| QA harness | `scripts/native_qa.py` | Python | Drives the built native app via in-process `AXUIElement`. Does **not** build or use XCTest. |

The three surfaces share one backend and one licence policy, so a resource that is
withheld on one surface is withheld everywhere.

---

## Repository layout

```
harness/
├── backend/            FastAPI service: auth, courses, lessons, practice, reviews,
│                       tutor, media, board, insights, consent/export/delete.
├── native/             SwiftUI macOS app (SwiftPM). Sources under
│                       Sources/LearningHarness/{Shared,Features}.
├── web/                Static web workbench (vanilla JS/CSS).
├── scripts/            native_qa.py, release/package tooling, refresh + probe scripts.
├── docs/               Architecture, quality program, evidence packs, design notes.
├── deploy/             docker compose (PostgreSQL + migration + API).
├── model/              Curriculum / course model assets.
├── outputs/            Build artifacts, release bundles, and native-qa evidence runs.
├── CHANGELOG.md        Canonical "what changed / what the gate accepts" log.
├── DISTRIBUTION.md     Packaging, codesign/notarization, staging-archive rules.
├── RELEASE_CHECKLIST.md / ROLLBACK.md / REBUILD_PROMPT.md
└── evidence.json       Machine-readable release-gate evidence bundle.
```

---

## Architecture in one breath

- **Licence gate is the spine.** `backend/app/ingest/policy.py` holds one audited list
  of allowed external sources (text, image, video, simulation). Unknown policy name →
  withhold; unknown licence code → refuse. Clients never upgrade a card's status.
- **Four media pipelines.** `media.py` (images, cached), `video.py` (Khan/YouTube —
  **EMBED_ONLY**, never downloaded or transcribed), `simulation_map.py` + media-packs
  (PhET slug verification / Gizmos deep-links), and `presentation.py` (a NotebookLM-style
  single-narrator, audio-led lesson replica). Simulations are `observable: false` — they
  are not evidence.
- **Commercial use is per-use, not per-user.** Under `HARNESS_COMMERCIAL_USE=1`, Khan/PhET
  are withheld automatically; `reapply_media_policy` re-evaluates at lesson-read time
  (not frozen at materialise time).
- **Interactive Board.** `backend/app/harness/board.py` (node store, optimistic
  concurrency, owner-scoped sharing) plus the Swift `Board.swift` renderer. Image nodes
  roll up into the export licence; video/simulation export as link chips, never re-distributed.

---

## Prerequisites

- **Python 3** with a venv at `backend/.venv` (the QA runner's first interpreter
  candidate). Build it from `backend/requirements.txt`.
- **Swift toolchain** (macOS) for the native app.
- For hosted deployment only: Docker + a configured language-model provider (see
  `deploy/README.md`). Local dev uses SQLite and needs no external services.

---

## Quick start

### 1. Backend (local dev)

```sh
cd harness/backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory
# → http://127.0.0.1:8000  (default SQLite at the app data dir)
```

The app is an ASGI **factory** (`create_app`), not a module-level `app`. Health:
`GET /api/v1/health`.

### 2. Native app (macOS)

```sh
cd harness/native
swift build -c release --disable-sandbox
# binary: .build/release/LearningHarness
```

`--disable-sandbox` is required: SwiftPM's manifest compile also routes through
`sandbox-exec`, and a nested sandbox is rejected on this platform.

### 3. Web workbench

Static files in `web/`; serve them with any static server, or let the backend serve
`index.html` as-is. No build step. See `web/README.md`.

### 4. Native journey gate (the acceptance harness)

`scripts/native_qa.py` launches the **already-built** native binary against an
**owned, isolated** backend database and drives it through ten end-to-end learner
journeys with the in-process accessibility tree. It never builds the app or uses XCTest.

```sh
cd harness
python3 scripts/native_qa.py \
  --journeys \
  --port 8777 \
  --backend-python backend/.venv/bin/python \
  --output outputs/native-qa/journey-full-N
```

Notes:
- `--port 0` (default) auto-scans `8765..8785`, matching `BackendLauncher`. A developer
  already owning `8765` is **not** treated as a product failure.
- `--timeout` defaults to `420s`; pass `--timeout 1800` for full runs.
- `--expire-access-after` / `--access-token-ttl` inject an expired access token into the
  isolated DB to exercise the refresh-token renewal path (the B8 regression).
- The binary path defaults to `native/.build/release/LearningHarness`.

---

## Native journey gate

The gate is the product's definition of "the native experience actually works". A
successful database registration **alone does not** count as a successful journey —
each journey asserts real UI behaviour, and `journeyGate.allGreen` requires all ten
with zero weakened assertions.

| ID | Journey | Requirement (asserted) |
| --- | --- | --- |
| J1 | First launch, registration, onboarding | A stranger installs, registers, reaches a personalised plan. |
| J2 | Course → lesson | A lesson opens for the enrolled course with read-aloud offered. |
| J3 | Practice + grading | A submitted answer yields evaluated feedback and is recorded. |
| J4 | Review + next schedule | A completed review returns a next due date, not a dead end. |
| J5 | Autosaved project | Draft text survives navigate-away-and-back without explicit save. |
| J6 | Author a course | The app can create a course and reopen it as the active course. |
| J7 | Tutor offline / provider failure | A missing model still yields a grounded answer, never an empty bubble. |
| J8 | Read-aloud / unavailable voice | Read-aloud speaks **or** refuses with a named reason — it never hangs. |
| J9 | Insights | Learning (measured) is separated from engagement (activity), and labelled. |
| J10 | Consent / export / delete | Consent is changeable, export reachable, deletion gated by exact phrase. |

### Latest verified run — `journey-full-10`

- `journeyGate.allGreen = true`, `total = 10`, `passed = [J1…J10]`, `failed/blocked/missing/gaps = []`
- `appExitCode = 0`, `nativeStatus = completed`, `status = passed`
- `databaseVerified = true`, `screenshotsPresent = true` (16 non-blank captures)
- Backend DB at end of run: `users=1, attempts=1, flashcards=12, created_courses=1,
  consent_ledger=2, auth_tokens=1, receipts=1, learning_states=1`
- Generated `2026-11-14T02:02:09Z`; account `native-20261114-095823-af9e1d81@example.com`
- Binary: `.build/arm64-apple-macosx/release/LearningHarness`
  (sha256 `525f181d…fcb6d`)

The wrapper reads `journeys-events.json` (not a stub) and ANDs it with
`journeyGate.allGreen`, so a passing DB registration cannot mask a failed UI journey.

---

## Documentation index

- `CHANGELOG.md` — what changed and what the release gate accepts (canonical).
- `docs/architecture/` — system, media, board, and policy design.
- `docs/QUALITY_PROGRAM.md`, `docs/FEATURE_VERIFICATION_REGISTER.md` — verification regime.
- `docs/evidence/` — per-finding evidence packs (e.g. `2026-11-12/B8-post-registration-navigation.md`).
- `deploy/README.md` — hosted `docker compose` boot, model options, operations.
- `web/README.md` — the static workbench.
- `native/Sources/LearningHarness/Features/README.md` — native surface layout (ADR-0003).

---

## Compliance posture

The harness is fail-closed on licensing: anything not on the audited source list, or
with an unrecognised licence code, is withheld or refused rather than shown. Textbook
licences are re-derived on every import via `classify_licence`; editing the source
catalogue never "upgrades" a book's permission. See `backend/app/ingest/policy.py` and
`openstax.py`. Distribution, codesign/notarization, and the unsigned staging-archive
rules live in `DISTRIBUTION.md`; the only supported rollback is in `ROLLBACK.md`.
