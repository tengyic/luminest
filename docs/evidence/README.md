# Evidence

Dated, machine-readable evidence for the claims on the repository front page. Nothing here is a summary of a summary: the raw outputs are committed alongside this file.

| Artefact | What it is |
|---|---|
| [`gate-2026-11-08/GATE.md`](gate-2026-11-08/GATE.md) | Human-readable release-gate verdict |
| [`gate-2026-11-08/gate.json`](gate-2026-11-08/gate.json) | Commands, exit codes, timings and captured stdout for both layers |
| [`first-person-run-2026-11-06.json`](first-person-run-2026-11-06.json) | Full 20-step acceptance run, with the request/response evidence for each step and the database row counts |

Bearer tokens, refresh tokens and the throwaway account's email were redacted from the first-person run before publishing. All other fields are verbatim.

---

## 1. Release gate — 2026-11-08

**Verdict: PASS** (run `20261108-131016`, started `2026-11-08T13:11:39+0800`).

| Layer | Result | Tests | Time |
|---|---|---:|---:|
| 1 · unit | PASS | 66 passed | 38.5 s |
| 2 · integration | PASS | 45 passed | 44.4 s |
| **Total** | **PASS** | **111 passed, 0 failed** | 82.9 s |

The unit layer covers scheduler maths, FSRS property invariants, grading and mastery, deck scheduling, tenant isolation and permissions. The integration layer covers the API end-to-end, SQLite/PostgreSQL parity, fresh install and v7→v11 upgrade, desktop privacy defaults, and provider-outage fallback.

Reproduce it with a complete development environment:

```bash
cd harness/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q tests/test_memory.py tests/test_flashcards.py \
  tests/test_learning_science.py tests/test_memory_properties.py \
  tests/test_learning_properties.py tests/test_security_contract.py
.venv/bin/python -m pytest -q tests/test_api.py tests/test_database_engines.py \
  tests/test_desktop_environment.py
```

**An interpreter trap worth recording.** An earlier run the same morning (`20261108-130611`) reported **FAIL** for both layers. The cause was not product code: the gate auto-selected `backend/.venv-phase2-test/bin/python`, a Python 3.14 environment missing `hypothesis` and `pandas`. Two property-test modules failed at collection, and one integration test failed on `import pandas`. Re-running with `backend/.venv/bin/python` (which has `requirements-dev.txt` installed) produced the PASS above. The gate behaved correctly — a skip or a collection error is not a pass.

The gate runner itself currently lives on the `feature/a11y-i18n` development branch and is not yet merged to `main`; the test files it invokes are on `main`. PostgreSQL parity skips locally when no server is reachable, and the native UI layer needs a signing identity unavailable on this machine — neither is counted as a pass.

---

## 2. First-person acceptance run — 2026-11-06

A *user-like* run, not a snapshot: fresh account, a topic absent from the curriculum, real HTTP calls against a real SQLite database.

- **Topic:** creep deformation of titanium aluminide turbine blades (confirmed unseen: `results: []`)
- **Result:** **17 / 20 steps passed**, 3 failed
- **Backend:** `http://127.0.0.1:8794`, schema version 11, `generation_mode: grounded-offline`

What passed, in order: health declares its own limits → a fresh learner registers as `role: learner` → a course is generated (42 concepts, 168 questions) → saved and enrolled → a lesson procedure starts → a real question is served → an answer is graded → the learning state moves and a review is scheduled → the plan is recompiled → voice behaviour is honest → the lesson ends with a summary.

Database rows before and after the answer:

| Table | After generation | After answer |
|---|---:|---:|
| `attempts` | 0 | **1** |
| `learning_states` | 0 | **1** |
| `created_courses` | 0 | **1** |
| `procedure_runs` | 1 | 2 |

This is the evidence that the answer-to-adaptation loop is connected: an answer writes an attempt, the attempt moves a learning state, and the next plan differs from the previous one.

**The three failures, verbatim in intent:**

1. *Ask to be taught the unseen topic via agent chat* — `message: null`, `finish_reason: unavailable`, with the honest error `"Model not configured. The harness falls back to deterministic, grounded-offline content when no provider is set."`
2. *Generated lesson has an independent worked example* — the lesson exists and is real, but lacks that specific block.
3. *Completing the first block writes an attempt* — block completion alone does not record one; the graded question in step 11 does.

These are recorded as findings, not quietly dropped or reclassified.

---

## 3. Earlier documented measurement

`harness/docs/READINESS_ASSESSMENT.md` (2026-11-05) reports a full backend-suite run of **1813 passed / 1 failed / 2 skipped**, with the single failure identified as a pre-existing wall-clock flake that was then made deterministic. That document also records the live service checks: VoiceStudio TTS returning a real MP3, Chromium-based web search and video discovery without an API key, PPTX export of a real 8-slide OOXML file, and a course built from pasted text producing 6 concepts / 24 questions.

Test counts differ across documents because they were measured on different days against a moving tree. The dated snapshots above are the authoritative ones for this front page.

---

## 4. What this evidence does **not** claim

- It does not claim a cleared public release. Signing, notarization and legal-text placeholders remain open (`harness/DISTRIBUTION.md`).
- It does not claim a configured LLM tutor. The provider is offline by default and says so.
- It does not claim 100% feature coverage. A gap or a skip is never collapsed into a pass.
- It does not claim the walkthrough video is a continuous screen recording. The video is assembled from the real captures in `docs/assets/screenshots/`, each labelled as such.
