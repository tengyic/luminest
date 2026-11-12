# Evidence

Dated, machine-readable evidence for the claims on the repository front page. Nothing here is a summary of a summary: the raw outputs are committed alongside this file.

| Artefact | What it is |
|---|---|
| [`gate-2026-11-11/GATE.md`](gate-2026-11-11/GATE.md) · [`gate.json`](gate-2026-11-11/gate.json) | Release-gate verdict, layers 1–2, run `20261111-102057` on `a7bfb6d`. **9 of 122 test files** |
| [`gate-2026-11-08/GATE.md`](gate-2026-11-08/GATE.md) · [`gate.json`](gate-2026-11-08/gate.json) | The earlier gate run, kept for comparison. Same 9 files; integration has since grown 45 → 47 |
| [`first-person-run-2026-11-11.json`](first-person-run-2026-11-11.json) | 29-step acceptance run, **29/29**, fresh database, provider explicitly unconfigured |
| [`first-person-run-2026-11-06.json`](first-person-run-2026-11-06.json) | The earlier 20-step run, **17/20**, kept because its three failures are still the honest description of a provider-less instance |
| [`full-suite-2026-11-12/SUMMARY.md`](full-suite-2026-11-12/SUMMARY.md) · [`full-suite.log`](full-suite-2026-11-12/full-suite.log) · [`collection.txt`](full-suite-2026-11-12/collection.txt) | Full backend suite **after** the three fixes, on `c35d24f`: **2,289 passed / 0 failed / 2 skipped**, 2,291 collected, 14 m 49 s |
| [`native-layer3-2026-11-12/SUMMARY.md`](native-layer3-2026-11-12/SUMMARY.md) · [`run-summary.json`](native-layer3-2026-11-12/run-summary.json) · [`journeys.json`](native-layer3-2026-11-12/journeys.json) | Ten native journeys on the rebuilt app: **6 passed / 1 blocked / 3 failed**, `databaseVerified: true`, 3 m 03 s |

Bearer tokens, refresh tokens and the throwaway account's email were redacted before publishing. All other fields are verbatim.

---

## 1. Release gate — 2026-11-11 (current) and 2026-11-08 (earlier)

**Both PASS. Neither is the suite.** The gate runs a fixed nine files chosen for speed — six in the unit layer, three in the integration layer — and the two layers together are **9 of 122 test files (7.4%) and 113 of 2,291 collected tests (4.9%)**. Publishing "113 passed" next to a full-suite number, as an earlier revision of the front page did, makes a subset read as the whole.

| Layer | 2026-11-08 | 2026-11-11 | Files |
|---|---:|---:|---|
| 1 · unit | 66 passed | 66 passed | `test_memory`, `test_flashcards`, `test_learning_science`, `test_memory_properties`, `test_learning_properties`, `test_security_contract` |
| 2 · integration | 45 passed | **47 passed** | `test_api`, `test_database_engines`, `test_desktop_environment` |
| **Total** | **111** | **113** | verdict PASS, 0 skipped, ~71 s |

The +2 is not new parity coverage: `test_database_engines.py` gained two functions at `cbe84d3`, twenty‑three hours *after* the 2026-11-08 run, and both run without a PostgreSQL server.

What the unit layer covers: scheduler maths, FSRS property invariants, grading and mastery, deck scheduling, tenant isolation and permissions. The integration layer covers the API end-to-end, SQLite/PostgreSQL parity, fresh install and v7→v11 upgrade, desktop privacy defaults, and provider-outage fallback.

**An interpreter trap, now closed in code.** The 2026-11-08 morning run reported FAIL for both layers because `find_python()` selected `backend/.venv-phase2-test/bin/python` — `sorted(glob('.venv*/bin/python'))[-1]`, i.e. whichever throwaway venv sorted last — which has no `hypothesis` or `pandas`. The published fix was to pass `--python` by hand. That is not a fix; it teaches people to distrust the default. `find_python()` now prefers `backend/.venv` by name and, if that is absent and several candidates exist, **refuses with the list** instead of picking one.

**Skips.** A layer's verdict still comes from its runner's exit code, but the gate now also parses the skipped-test count out of that layer's own summary and treats it as a blocker at every strictness level. Before this, a test-level skip sailed through: pytest exits 0 with skips, so a layer whose PostgreSQL half never ran was green. That is the difference between "a skip is never a pass" as a published promise and as behaviour.

**What the gate does not cover.** Layer 3 (the ten native journeys) was not requested in either gate snapshot. It does not need a signing identity — it drives the app in-process — it needs a built binary and takes minutes; it has since been run separately on 2026-11-12 and is **not green** (6 of 10 passed, see §5). Layer 4 is the packaging/distribution check. Both are outside these numbers.

---

## 2. First-person acceptance run — 2026-11-11 (current) and 2026-11-06 (earlier)

A *user-like* run, not a snapshot: fresh account, a topic absent from the curriculum, real HTTP calls against a real SQLite database, `HARNESS_ENV=test`, and the provider **explicitly emptied** so the run is reproducible by anyone.

| | 2026-11-06 | 2026-11-11 |
|---|---|---|
| Steps | 20 | **29** |
| Passed | 17 | **29** |
| Provider | unconfigured | unconfigured |

**The scores are not comparable.** The runner changed: 18 steps are unchanged, 2 were re-specified, and 9 are new (grade book, written perspective evidence, export). "17/20 → 29/29" is not a fixed defect count going to zero; it is a different instrument on a later tree.

- **Topic:** creep deformation of titanium aluminide turbine blades (confirmed unseen: `results: []`)
- **Backend:** schema version 11, `tutor.state: unconfigured`

What passed: health declares its own limits → a fresh learner registers as `role: learner` and is **not** promoted → the topic is confirmed unseen → an agent turn refuses with a named reason instead of inventing a lesson → a course is generated from that topic (42 concepts, 168 questions) → saved and enrolled → the generated lesson is served → the lesson procedure starts → block completion is refused until the promised answers exist → a signed question is served → it is graded with a diagnosis → the learning state moves and a review is scheduled → the plan is recompiled → voice returns a real MP3 → the lesson ends with a summary → the grade book declares standards and refuses an unevidenced grade → empty perspectives are `null`, not zero → a written observation is scored only against a real artefact → export covers the grade book and perspective records.

Database rows: `attempts: 0 → 1`, `learning_states: 0 → 1`, `created_courses: 0 → 1`.

**The three failures of the 2026-11-06 run are still the honest description of a provider-less instance**, even though the current runner scores them as passes:

1. *Ask to be taught a wholly unseen topic* — returns `message: null`, `finish_reason: unavailable`. In 2026-11-06 the notice said "falls back to deterministic, grounded-offline content"; it now names the missing configuration and points at Settings. The step passes **because the refusal is honest**, not because the topic can be taught.
2. *The generated lesson lacks an independent worked example* — still true. The generator emits four blocks and no worked example, and the tutor is required to say so.
3. *Block completion does not itself write an attempt* — still true; the graded question writes it.

---

## 3. Numbers withdrawn from earlier revisions

An earlier revision of the front page published **1813 passed / 1 failed / 2 skipped (2026-11-05)**. It has been removed rather than footnoted, for two reasons found by re-measuring:

- **It is not reproducible on any commit.** `main` today collects 1,838 tests across 101 files and reports 1,835 / 1 / 2. The 1,813 figure matches no commit on `main`; it came from an uncommitted working tree.
- **Its single failure was misattributed.** The failure described as "a wall-clock flake, since made deterministic" is `test_stream.py::test_the_event_budget_bounds_a_held_key`, and that test now passes (17 passed in its file, 6/6 on narrow re-runs — `main` already carries the frozen-clock fix). The actual failure on `main` today is a *different* test failing on the developer venv's package versions.

The 2026-11-05 document is kept as history at [`harness/docs/READINESS_ASSESSMENT.md`](../../harness/docs/READINESS_ASSESSMENT.md), with a dated correction at the top pointing here.

**Why this section exists.** The previous revision of this file explained the divergence as "test counts differ across documents because they were measured on different days against a moving tree." That is true and it is not an excuse: a reader cannot tell a 9-file subset from a 122-file suite, or a 20-step instrument from a 29-step one, when both are printed as bare fractions. Every number on the front page now carries its scope, its commit and its command.

---

## 4. What this evidence does **not** claim

- It does not claim a cleared public release. Legal text now has **0 placeholders**, but `security find-identity -v -p codesigning` reports 0 identities on the build machine, so `release_kit.py` refuses and the shipped artifacts are ad-hoc signed (`harness/DISTRIBUTION.md`).
- It does not claim a configured LLM tutor. A fresh clone boots unconfigured (`offline` was removed; production refuses to boot without a model), so a topic outside the curriculum is **refused with a reason, not taught**. That is the boundary this product still has.
- It does not claim complete or verified content. 30 of 2,205 graph nodes carry a hand-written lesson; 2,041 carry a generated four-block lesson with no worked example; 134 nodes of the default course have nothing. Breadth is not depth, and no check here measures whether a generated lesson teaches.
- It does not claim the native client works. Gate layer 3 was not run in either gate snapshot; the separate 2026-11-12 run executed all ten journeys and got **6 passed / 1 blocked / 3 failed**. The native client is now exercised, but it is not green.
- It does not claim 100% feature coverage, and it no longer claims that a skip is never a pass on trust: the gate now parses skipped-test counts and blocks on them.
- It does not claim certification. The gate covers 7.4% of the test files and its runner is not on `main`. A green full-suite aggregate is now archived here (2,289 / 0 / 2 on `c35d24f`), but that commit is on the development branch, and layer 3 remains not green.
- It does not claim the walkthrough video is a continuous screen recording. The video is assembled from the real captures in `docs/assets/screenshots/`, each labelled as such.

---

## 5. Full suite and native layer 3 — 2026-11-12

Two gaps named in earlier revisions of the front page were closed by measuring, not by
rewording. Both runs are on `c35d24f` (`feature/a11y-i18n`), which was pushed alongside them.

| | Full backend suite | Native layer 3 |
|---|---|---|
| Command | `pytest -q -rs -p no:cacheprovider --basetemp=<workspace>/outputs/qa/bt`, one process, `env -u PYTHONPATH` | `swift build --disable-sandbox`, then `native_qa.py --journeys --port 8891 --timeout 900` |
| Scope | 122 files, 2,291 collected | 10 golden journeys, isolated backend + SQLite |
| Result | **2,289 passed / 0 failed / 2 skipped**, 8 warnings, 14 m 49 s, exit 0 | **6 passed / 1 blocked / 3 failed / 0 gaps / 0 missing**, 3 m 03 s, `databaseVerified: true` |
| Raw output | [`full-suite.log`](full-suite-2026-11-12/full-suite.log), [`collection.txt`](full-suite-2026-11-12/collection.txt) | [`run-summary.json`](native-layer3-2026-11-12/run-summary.json), [`journeys.json`](native-layer3-2026-11-12/journeys.json), [`journeys-events.json`](native-layer3-2026-11-12/journeys-events.json) |

**Before → after.** `ab8bcda` measured 2,286 / 3 failed / 2 skipped. `a7bfb6d` fixed the three
tests (`test_teacher_clone`, `test_video_seed`, `test_mathkit`) and re-ran only those files
(130 passed), which is why the front page previously said the aggregate *after* the fix was
unmeasured. The 2026-11-12 run closes that arithmetic exactly: +3 passes, the same two
opt-in skips, zero failures. The two skips are live-provider smokes behind
`HARNESS_DIAGRAM_LIVE_SMOKE` / `HARNESS_LIVE_SMOKE`.

**Layer 3 needed a rebuild, not a signing identity.** The two attempts on 2026-11-11 ended
`blocked` with `total: 0` and `total: 1`, one of them spending 477 s between pressing
`auth.register` and the first diagnostic. The debug binary then on disk predated `a7bfb6d`,
which removed the now-rejected `HARNESS_TUTOR_PROVIDER=offline` from the QA child. Rebuilding
from the fixed source made all ten journeys execute in three minutes.

**The four non-passes are still open.** J4 is a legitimate `blocked` (no review due on a
brand-new account). J8 found no `lesson.read` in the current AX tree although the control
exists at `Studio.swift:124`; J10 found no phrase field although the `TextField` exists at
`ProjectsInsightsSettings.swift:522`; J9's global-text empty-state assertion was false even
though the database holds one real attempt. None was made green by weakening an assertion,
and none is claimed here as a proven product regression. See
[`native-layer3-2026-11-12/SUMMARY.md`](native-layer3-2026-11-12/SUMMARY.md).

**Content depth is unchanged by either run.** A read-only count of the shipped curriculum
pack: 2,071 concepts, 30 hand-written, 2,041 generated. `worked_example` blocks: **30**, all
in the hand-written lessons. `misconception` blocks: **0**. `overlay_concepts`: **0**.
Generated lessons contain only concept / reflection / retrieval blocks. No test run turns
breadth into depth; that remains a product investment, not an evidence gap.
