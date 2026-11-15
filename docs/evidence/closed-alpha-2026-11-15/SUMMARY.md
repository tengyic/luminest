# Closed-Alpha evidence — 2026-11-14 / 2026-11-15

The numbers added to the front page on 2026-11-16 come from the shipping branch
`feature/a11y-i18n`, at commits `4a83d86` (gate + suite fixes + frozen bundle) and
`5bc4a18` (README only, no code). This is the same convention the front page already
uses for `c35d24f`: a measurement states the branch/commit it was taken on. These
commits are **not** on `main`. Nothing here is claimed to have been measured on `main`.

Raw outputs are committed next to this file; throwaway account emails were redacted
to `*@redacted.test`. All other fields are verbatim.

## 1. Closed-Alpha end-to-end gate — 47/47

| | |
|---|---|
| Command | `python3 scripts/alpha_e2e_gate.py --base http://127.0.0.1:<port> --course ap_psychology` |
| Scope | A real AP Psychology course, registration → analysis report, over HTTP |
| Result | **47 checks / 47 passed**, 0 failed steps |
| Raw output | [`alpha_e2e_evidence.json`](alpha_e2e_evidence.json) |

The gate rejects an HTTP-200-only pass. It requires a model-backed answer (not a
fallback string), both `stage_surface` and `whiteboard_write` dispatched and successful,
real MP3 bytes from TTS, `transport: stream` from ASR, attribution on shipped images,
and a cross-account 404. The course source clears the builder's real thresholds
(2 paragraphs / 80 words / 4 concepts).

## 2. Backend full suite — 2451 / 0 / 2

| | |
|---|---|
| Command | `cd backend && env -u PYTHONPATH -u NODE_OPTIONS .venv/bin/python -m pytest -q --basetemp=.pytest-basetemp-XXXX -p no:cacheprovider` |
| Scope | All backend tests, one process, 2453 collected |
| Result | **2451 passed / 0 failed / 2 skipped**, 19 m 33 s |
| Raw output | [`test_suite_2026-11-15.json`](test_suite_2026-11-15.json), [`full-suite.log`](full-suite.log) |

Both host shims are excluded from this run. `PYTHONPATH` otherwise injects WorkBuddy's
`sitecustomize.py` broker shim; `NODE_OPTIONS` injects a Node `--require` preload whose
broker execution credential expired during a 16-minute run and produced 5 false
failures in `tests/test_web_telemetry_helper.py`. That module passes 7/7 in isolation
and with the preload stripped; its assertions were not weakened. The probe now removes
`NODE_OPTIONS` from its own subprocess. An earlier full run had 3 assertion-drift
failures from the `Luminfest` → `Luminest` brand rename plus beta cohort fields, fixed
in `capabilities.py` (23/23 in isolation). Failure counts across the three full runs:
**3 → 5 → 0**, each attributed, none skipped by re-running.

The two skips are explicit opt-in live-provider smokes, not passes.

## 3. Frozen backend smoke — 11/11

| | |
|---|---|
| Command | `python3 scripts/package.py --backend-only --allow-template-legal` |
| Result | **11/11** frozen-backend smoke checks |
| Note | Produced the 72 MB arm64 bundle `Luminfest-Server-2026-11-15.zip`, sha256 `52b4a5f5e5f16556b673bb0c7ff8648ccb060946d96374e7193c9e6ef7c28008`. The zip and sha256 are unchanged by all evidence above. |

## 4. Native journey gate — 10/10 (supersedes 2026-11-12)

| | |
|---|---|
| Command | `swift build --disable-sandbox`, then `scripts/native_qa.py --journeys --port <free>` against an isolated backend and database |
| Scope | 10 golden journeys in the rebuilt real app |
| Result | **10/10** — `journeyGate.allGreen: true`, passed `J1…J10`, `failed/blocked/missing/gaps: []`, `appExitCode: 0`, `databaseVerified: true` |
| Raw output | [`native-run-summary-2026-11-14.json`](native-run-summary-2026-11-14.json) |

This **supersedes** the 2026-11-12 `6 passed / 1 blocked / 3 failed` result on `c35d24f`.
Commit `60a70bd` fixed the J8 read-aloud hang (it now speaks or refuses with a named
reason) and made the wrapper read the real `journeys-events.json` rather than a stub,
which is what had made J4 appear blocked. Both the earlier not-green run and this
green run are kept: the earlier row stays on the front page as history.

## What this evidence does not claim

- Not measured on `main` — all rows are from `feature/a11y-i18n`.
- Not 100% feature coverage: the capability register still lists 12 `partial` and
  2 `external` items. Duplex voice, browser window stream, email verification, teacher
  clone, project workflows and others remain partial; mindmap/flashcards had their
  **media pipeline** fixed, while their presentation is still an SVG tree and text cards.
- No public beta link exists. A site publish attempt returned `SITES_APP_NOT_FOUND` for
  the deleted appId three times; the landing decision's earlier "published" claim was
  corrected. Closed Beta is ready-but-not-accepted: TLS + PostgreSQL + invite codes +
  a remote voice gateway have not been exercised end-to-end.
- No legal contracts, commercial plans, pricing or licensing terms are decided here.

The full technical verdict is `docs/ALPHA_VERDICT_2026-11-15.md` (on the shipping branch).
