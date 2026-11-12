# Native UI layer 3 — measured run, 2026-11-12

**Verdict: NOT GREEN.** Ten golden journeys all executed; **6 passed, 1 blocked, 3 failed,
0 gaps, 0 missing**. This is the first archived layer-3 run on this snapshot. It is evidence
of specific behaviour on a specific date, not certification.

## What was measured

| Field | Value |
|---|---|
| Date | 2026-11-12, 11:14–11:17 local (3 m 03 s wall clock) |
| Branch / commit | `feature/a11y-i18n`, `c35d24f` (working tree also carries an uncommitted `AC-3.txt` note; no source changes) |
| App | `harness/native/.build/debug/LearningHarness`, rebuilt 2026-11-12 11:12, 27,680,112 B |
| Build command | `env -u PYTHONPATH swift build --disable-sandbox` (incremental, 9.88 s, "Build complete!") |
| Backend | owned isolated loopback backend on 127.0.0.1:8891, own `HOME`, own SQLite database |
| Python | `harness/backend/.venv/bin/python` (3.14) |
| Driver | in-process native AppKit accessibility (`AXUIElement`), no XCUITest, no HTTP shortcut |
| Exit | `native_qa.py` exited 1 because `journeyGate.allGreen` is false; app exit code 0, `databaseVerified: true` |

Reproduce (from the workspace root):

```sh
cd harness/native && env -u PYTHONPATH swift build --disable-sandbox
cd .. && env -u PYTHONPATH backend/.venv/bin/python scripts/native_qa.py --journeys \
  --app native/.build/debug/LearningHarness \
  --backend-python backend/.venv/bin/python \
  --port 8891 --output <fresh-empty-directory> --timeout 900
```

## Journey verdicts

| # | Journey | Status | Checks | Note |
|---|---|---|---|---|
| J1 | First launch, registration and onboarding | **pass** | 5 | completed in ~25 s |
| J2 | Selecting a course and starting a lesson | **pass** | 3 | |
| J3 | Practice question → grading feedback | **pass** | 3 | wrote a real attempt |
| J4 | Review → next scheduled review | **blocked** | 2 | no review items were due on a brand-new account and the deck could not be seeded: `Timed out waiting for a revealed card`. A `blocked` verdict is the honest one here; it is not coverage. |
| J5 | Leave and reopen an autosaved project | **pass** | 2 | |
| J6 | Create a course and access it again | **pass** | 6 | |
| J7 | Tutor offline / provider failure | **pass** | 3 | |
| J8 | Read-aloud and unavailable voice | **fail** | 1 | driver found no `lesson.read` on the studio surface. The control exists in the product (`Studio.swift:124`, `accessibilityIdentifier("lesson.read")`); this is a navigation/AX-state question, not a proven missing feature — it needs human adjudication before anyone calls it a regression. |
| J9 | Insights: learning vs engagement | **fail** | 3 | the driver's global-text assertion `!containsText("A clearer picture will emerge")` was false. The isolated database holds `attempts: 1` and `realPracticeAttempt: true`, so the assertion may be matching an empty-state caption belonging to a different section. The AX snapshot is archived (`journey-J9-insights-accessibility.json`) for inspection. |
| J10 | Consent, export, deletion | **fail** | 6 | `findPlaceholder("Type DELETE MY ACCOUNT")` found no phrase field. The product ships that `TextField` at `ProjectsInsightsSettings.swift:522` with the delete button disabled until the phrase matches; no `accessibilityIdentifier` is attached to it, so this is a driver AX-read problem, not proof the gate is absent. |

`run-summary.json` → `journeyGate`:
`{"allGreen": false, "passed": ["J1","J2","J3","J5","J6","J7"], "blocked": ["J4"],
"failed": ["J8","J9","J10"], "gaps": [], "missing": [], "total": 10}`

## Database corroboration (read after both processes stopped)

`attempts: 1`, `learning_states: 1`, `created_courses: 1`, `consent_ledger: 2`,
`auth_tokens: 1`, `messages: 0`. `backendIssuedSignedInSession: true`,
`onboardingCompletedThroughRealUi: true`, `realPracticeAttempt: true`,
`explicitActivityConsentSaved: true`, `databaseVerified: true`.
Several legacy single-workflow checks (`actualAssistantReplyRendered`,
`actualUserMessagePersisted`, …) are false because the `--journeys` driver does not exercise
that path; they are not journey failures and are recorded separately in
`backend-evidence.json`.

## Why the previous two attempts produced nothing

`outputs/native-qa/journeys-20261111-212451` and `...-220933` both ended `status: blocked`
with `total: 0` and `total: 1` — the 22:09 run spent 477 s between pressing
`auth.register` and the first diagnostic. The debug binary then on disk was built at 10:21,
two minutes **before** `a7bfb6d` (10:23) removed `HARNESS_TUTOR_PROVIDER=offline` from
`NativeQA.swift`; `config.py` rejects that value, so the QA child could not boot correctly.
Rebuilding from the fixed source made all ten journeys execute in 3 minutes. No test
assertion was weakened to obtain this result.

## What this does not establish

- Layer 3 is **not** green: one blocked and three failed journeys stand in the way of a
  release verdict.
- J8/J9/J10 were **not** "fixed" by editing the driver or the app; the three failures are
  reported with their evidence and remain open.
- No signing identity was needed (XCUITest is a separate, still-unavailable path), but
  this run says nothing about notarization or public distribution.
