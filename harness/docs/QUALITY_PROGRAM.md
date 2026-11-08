# Test engineering and release gate

Four layers, ten golden journeys, and the checks that decide whether a build may ship.
Everything here is runnable from a clean checkout; nothing is aspirational.

```bash
cd harness
python3 scripts/quality_gate.py                 # all four layers
python3 scripts/quality_gate.py --layers 1,2    # backend only (fast)
python3 scripts/quality_gate.py --strict        # a skip also fails the gate
```

The gate writes `outputs/quality/<run>/gate.json` (machine) and `GATE.md` (human). A run
exits non-zero if any requested layer failed, any journey failed, or — in `--strict` — a
layer skipped.

---

## Layer 1 — Unit

*Individual services, models, calculations, schedulers, permissions and business rules.*

| What | Where |
|---|---|
| Scheduler maths (FSRS-6 DSR) | `tests/test_memory.py`, `tests/test_memory_properties.py` |
| Grading and mastery (BKT) | `tests/test_learning_science.py`, `tests/test_learning_properties.py` |
| Deck scheduling and interchange | `tests/test_flashcards.py` |
| Tenant isolation and permissions | `tests/test_security_contract.py` |

**Property-based tests.** The scheduler decides *when a learner sees an item again*, and a
wrong constant there is invisible to a handful of examples. `hypothesis` searches for
counterexamples against invariants instead:

- `0 < R(t) ≤ 1`, `R(0) = 1`, and `R(S) = 0.9` by construction;
- `R` never rises with elapsed time, never falls with stability;
- the interval respects the product's own five-minute floor and 36 500-day cap;
- a review never yields non-positive stability or difficulty outside `[1, 10]`;
- `review` is pure — the caller's dict is untouched;
- Easy ≥ Good ≥ Hard ≥ Again when everything else is held constant.

Two boundaries are asserted explicitly rather than papered over: at mastery `0.0` and at
`1.0` the grading formula collapses both outcomes onto the LEARN floor or the `0.995` cap,
so strict ordering is asserted only over the reachable domain (`PRIOR ≤ m ≤ 0.9`).

## Layer 2 — Integration

*API endpoints, persistence, transactions, migrations and external-provider failure.*

| What | Where |
|---|---|
| End-to-end API behaviour | `tests/test_api.py` |
| SQLite **and** PostgreSQL parity, fresh install, v7 → v11 upgrade | `tests/test_database_engines.py` |
| Desktop defaults (privacy switches) | `tests/test_desktop_environment.py` |
| Provider outage → grounded fallback | `tests/test_api.py::test_provider_failure_falls_back_to_the_curriculum` |

`test_database_engines.py` runs one identical journey — register, create a card, review it,
read stats, export the deck — against both engines and compares the observable result. It
then rolls a database back to v7 (drops the v8 column and the v9/v11 tables) and runs the
real `scripts/init_db.py` forward, asserting the rows survive and the missing schema comes
back. That is the failure `create_all` cannot catch: a column added to an old table appears
on fresh installs and never on upgraded ones.

**PostgreSQL is required in CI, optional locally.** With no server the PostgreSQL half
skips with the connection error as its reason. The gate prints `SKIPPED`, and `--strict`
fails on it — a skip is never counted as a pass.

## Layer 3 — Native UI

*Real SwiftUI interactions, navigation, form input, dialogs, accessibility, error states.*

Ten journeys are driven through the running app: `AXUIElement` presses on real buttons,
typing into real fields, real sheets. No HTTP shortcut, no state injection, no synthetic
views.

```bash
python3 scripts/native_qa.py --journeys \
  --app native/.build/debug/LearningHarness \
  --backend-python backend/.venv0000/bin/python \
  --port 8891 --output /tmp/journeys --timeout 900
```

The launcher owns an isolated backend and an isolated `HOME`, holds the listening socket
before spawning (no check-then-bind race), and inspects its own database afterwards so a
green UI cannot stand alone.

### Verdicts

| Verdict | Meaning |
|---|---|
| `pass` | Exercised through the app and observed. |
| `fail` | The product broke. |
| `gap` | No native path exists. Not coverage. |
| `blocked` | Could not be exercised here, with the reason recorded. |

Collapsing `gap` or `blocked` into `pass` would make the gate lie about coverage;
collapsing them into `fail` would make it unable to distinguish "we shipped this broken"
from "we never shipped this".

### XCUITest status

`ui-tests/` holds a real XCUITest target with accessibility-identifier-driven journeys. It
**cannot bootstrap on this machine**, and the reason is recorded rather than worked around:

- the XCTest runner is ad-hoc signed (`CODE_SIGN_IDENTITY = "-"`), and no Apple Development
  identity exists here (`security find-identity -v -p codesigning` → *0 valid identities*);
- Xcode 26 injects `com.apple.security.app-sandbox` into the UI-test runner regardless of
  `ENABLE_APP_SANDBOX = NO`;
- a sandboxed ad-hoc app cannot be granted a container, so `libsecinit` traps in
  `_libsecinit_appsandbox` during dyld initialisers: *"The test runner exited with code 1
  before establishing connection."*

Re-signing the runner without the sandbox entitlement moved the failure to a silent exit 1.
On a machine with a signing identity, or a CI runner provisioned with one, the XCUITest
target runs as written. Until then Layer 3 is executed by the in-process AX driver, which
is a genuine first-person test of the same application.

## Layer 4 — End-to-end system

*Complete journeys across app, backend, database, offline behaviour and distribution.*

Layer 4 is the corroboration half of Layer 3: the launcher reads its isolated database
after the app exits and checks the counts that the UI claimed (attempts written, messages
stored, preferences saved). A UI that reports success without the data is a failure.

---

## The ten golden journeys

Machine-readable source: `harness/quality/journeys.json` — each journey carries the six
elements (requirement, native path, backend path, data model, tests, acceptance criterion).

| # | Journey | Native coverage |
|---|---|---|
| J1 | First launch, registration and onboarding | `--ui-test` + real form fields and setup sheet |
| J2 | Selecting a course and starting a lesson | Studio, course-scoped lesson actions |
| J3 | Practice question → grading feedback | `question.option`, `question.submit`, `question.next` |
| J4 | Review → next scheduled review | Review queue, FSRS round-trip |
| J5 | Leave and reopen an autosaved project | Type, navigate away, return, compare field value |
| J6 | Create a course and access it again | `course.create` → `CourseAuthoringSheet` → `course.create.enrol` |
| J7 | Tutor offline / provider failure | Teacher panel, grounded reply, no raw error |
| J8 | Read-aloud and unavailable voice | `lesson.read`, refusal named, app stays responsive |
| J9 | Insights: learning vs engagement | `SUBMITTED ANSWERS ONLY`, empty state gone |
| J10 | Consent, export, deletion | Toggle + save, export control, gated destructive action |

**J6 is now a real native journey, not a declared gap.** The shell header's
`course.create` opens `CourseAuthoringSheet`; the AX driver types unseen notes into
`course.create.notes`, checks that `course.create.preview` saved nothing, creates the course,
enrols in it, and verifies the sidebar still works. A missing control or an undrivable step
is still reported as `gap` or `blocked` — the presence of the code is not evidence of a pass.
The remaining honest limit: the journey enrols the new course but does not leave the app and
reopen it in a later process, so "access it again" is covered by the backend course store and
`tests/test_course_creation.py`, not by a second launch.

**J10 deliberately cancels the deletion.** The destructive action is verified as *gated*
(the confirm button stays disabled until `DELETE MY ACCOUNT` is typed) and then abandoned,
because erasing the account would also erase the database evidence for J1–J9 that the
launcher reads afterwards. Actual erasure is covered by `tests/test_account_deletion.py`.

---

## Additional gates

| Gate | How | Fails when |
|---|---|---|
| Pinned dependencies | `requirements.txt` / `requirements-dev.txt` pin every version | A build resolves a different version |
| SQLite vs PostgreSQL | `tests/test_database_engines.py` | The two engines disagree, or PostgreSQL silently skips |
| Fresh install + upgrade | `tests/test_database_engines.py` | A migrated database loses rows or a column |
| Property-based tests | `tests/test_*_properties.py` | Any invariant is violated for a generated input |
| Mutation testing | `python3 scripts/mutation_check.py` | A curated defect is not caught by the suite |
| Dependency and vulnerability scan | `pip-audit -r requirements.txt` | A known advisory affects a pinned version |

### Mutation testing

Six curated defects are injected one at a time into the scheduling and grading code; each
must make a test fail. The mutants are plausible mistakes, not type noise: a flattened
forgetting curve, a dropped due-time floor, an ignored lapse counter, a removed LEARN floor,
a raised mastery cap, and swapped grade evidence. The original file is restored in a
`finally` block and verified by SHA-256. A surviving mutant means the suite would not have
caught that bug in production.

---

## CI

`.github/workflows/quality.yml`:

- **layer-1-unit** — Ubuntu, pinned deps, unit + property tests.
- **layer-2-integration** — Ubuntu with a `postgres:16` service container; fails if the
  PostgreSQL half skips.
- **layer-3-native** — macOS, `swift build`, the ten journeys, evidence uploaded.
- **dependency-audit** — `pip-audit` against the pinned runtime requirements.
- **mutation** — every curated mutant must be killed.

A skip or a gap never turns a job green.
