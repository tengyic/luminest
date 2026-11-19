# Luminfest Learning Harness

An AI-assisted learning harness: a learner registers, gets a personalised plan, works
through lessons, practices, reviews, authors courses, talks to a tutor, and owns their
data — across a **native macOS app**, a **static web workbench**, and a shared
**FastAPI backend**. Every external learning resource (textbook, image, video,
simulation) is gated by a single fail-closed licence policy before it is shown.

> **Verified state**
>
> - **2026-11-19 — schema 13, provider funded**: end-to-end gate **47/47 checks, 0
>   failed steps** on a real AP Psychology course. The two checks that failed on
>   2026-11-17 now pass on genuine model work, not on a retry-until-green:
>   `MODEL TEACHER TURN` → `answered_by: openai:deepseek-flash`, tools
>   `check_understanding` + `inspect_prerequisites`; `TEACHER ORCHESTRATES A TOOL` →
>   `stage_surface`, `whiteboard_read`, `whiteboard_write` dispatched. Backend suite
>   **2482 passed / 0 failed / 2 skipped** (2484 collected, 32 m 33 s); native
>   **140/140**.
> - **2026-11-17 — schema 13 at `6cd5733`, provider out of credit**: same tree, gate
>   **45/47**. Both failures were one external cause: the provider answered **HTTP 402
>   Insufficient Balance**, so no model turn and therefore no tool dispatch could happen.
>   The harness served its *labelled* grounded fallback (`answered_by:
>   model-unavailable`) rather than passing prose off as a model reply, and the gate
>   correctly refused to count it. Kept here because "45/47 caused by a 402" and
>   "47/47" are different facts about the same code.
> - **2026-11-15 — Closed Alpha (provider funded)**: end-to-end gate **47/47** on a real AP Psychology
>   course with hard "no fake pass" assertions; backend suite **2451 passed /
>   0 failed / 2 skipped**; frozen backend smoke **11/11**. See
>   [*Test evidence*](#test-evidence) below and
>   [`docs/ALPHA_VERDICT_2026-11-15.md`](docs/ALPHA_VERDICT_2026-11-15.md).
> - **2026-11-14 — native journey gate**: all-green **10/10 journeys**, `appExitCode=0`,
>   backend database verified ·
>   [`outputs/native-qa/journey-full-10/`](outputs/native-qa/journey-full-10).

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

## Test evidence

Every number below comes from a reproducible command and a machine-readable/log
artifact, not from the presence of a file. Run them from `harness/` unless noted.

| Gate | Result | Reproduce | Evidence |
| --- | --- | --- | --- |
| Closed-Alpha end-to-end | **47/47 checks, 0 failed steps** (2026-11-19, provider funded). Was 45/47 on 2026-11-17 on the same code, both failures caused by provider **HTTP 402** | `python3 scripts/alpha_e2e_gate.py --base http://127.0.0.1:<port> --course ap_psychology` | `outputs/alpha_e2e_evidence.json` |
| Backend full suite | **2482 passed / 0 failed / 2 skipped** (2484 collected, 32m33s, 2026-11-17) | `cd backend && env -u PYTHONPATH -u NODE_OPTIONS .venv/bin/python -m pytest -q --basetemp=.pytest-basetemp-XXXX -p no:cacheprovider` | summary embedded here; raw log stays local (see note below) |
| Native unit tests | **140 passed / 0 failed** (3.9 s) | `cd native && env -u PYTHONPATH swift test --disable-sandbox` | — |
| Frozen backend smoke | **11/11** | `python3 scripts/package.py --backend-only --allow-template-legal` | `outputs/closed-beta-2026-11-15/` |
| Native journey gate | **10/10 journeys**, `appExitCode=0` | see *Native journey gate* above | `outputs/native-qa/journey-full-10/` |
| Capability register | 47 implemented / 16 partial / 2 external | `python3 scripts/verify_feature_register.py --check` | `docs/feature_verification_register.json` |

The register and the verdict document are committed. The raw evidence under `outputs/`
and `*.log` is intentionally gitignored (local build/QA artifacts), so the `outputs/…`
paths in the table are **where the artifact lands when you reproduce a run locally** —
they are not clickable on GitHub. The numbers are therefore embedded in this README and
in the tracked `docs/ALPHA_VERDICT_2026-11-15.md`; if a number here ever disagrees with
the tree, the tree wins.

The E2E gate deliberately rejects "HTTP 200 but nothing really happened": it requires a
model-backed answer, both `stage_surface` **and** `whiteboard_write` dispatched and
successful, real MP3 bytes from TTS, `transport=stream` from ASR, attribution on shipped
images, and a cross-account 404. The course source clears the builder's real thresholds
(2 paragraphs / 80 words / 4 concepts).

Two test-environment notes, stated plainly because they were real failures on the way
to green, not swept aside:

- The suite is run with `PYTHONPATH` and `NODE_OPTIONS` stripped. The host injects a
  Python `sitecustomize.py` broker shim and a Node `--require` preload; a 16-minute run
  made the Node broker's "execution capability expired" produce 5 false failures in
  `tests/test_web_telemetry_helper.py`. That module passes 7/7 both in isolation and
  with the preload stripped, and its assertions were **not** weakened. The probe now
  removes `NODE_OPTIONS` from its own subprocess.
- An earlier full run had 3 assertion-drift failures from the `Luminfest` → `Luminest`
  brand rename plus beta cohort fields; those were fixed in `capabilities.py` and its
  tests (23/23). Failure counts across the three full runs: **3 → 5 → 0**, each
  attributed, none skipped by just re-running.

These gates are not a claim that every feature is complete. The register still lists
16 `partial` and 2 `external` capabilities (duplex voice, browser window stream, email
verification, teacher clone, project workflows and others); mindmap/flashcards had their
**media pipeline** fixed, while their presentation remains an SVG tree and text cards.
The full verdict is in `docs/ALPHA_VERDICT_2026-11-15.md`.

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
