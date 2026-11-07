# 04 — Open gaps (curated, not generated)

The generator does not overwrite this file. It records what an audit against the original
brief found, so a fresh session does not have to re-derive it.

Audited 2026-11-04 against the product brief. Verdict: the project is that brief, with
~80 % of it verifiably in code. These four items are the remaining delta.

## 1. Unit projects — absent

The brief asks for a small project after each unit: a presentation delivered on camera with
speaking, or a research task with limited AI use.

`deck.py` and `pptx_export` produce *slides* (teacher-authored), and `procedure_service`
runs a lesson. There is no student-produced artifact: no camera capture, no recording, no
submission, no rubric. Grep for `camera` returns nothing in `backend/app`.

This is the most conspicuous omission. Cheapest honest version: a `ProjectSubmission` row +
a recording surface in the native app + a rubric scored by the teacher agent, reusing
`psychometrics` for the scale.

## 2. Multi-perspective analytics — 3 of the listed dimensions missing

The brief lists participation, soft skills, creativity, communication, collaboration,
attention %, streak, struggle %.

Present: participation (`harness/classroom.py`, `harness/teaching/supervision.py`),
struggle (`classroom.py`, `loop.py`, `socratic.py`), attention (`harness/attention.py`),
streak (`harness/teaching/motivation.py`).

Absent: **collaboration, creativity, soft skills** — zero hits across the backend.

Cheapest to close: these are rubric fields over data already logged. They need a scoring
path, not new instrumentation. Note collaboration has no product surface at all today
(single-learner sessions), so it is a feature, not a field.

## 3. Teacher clone — transcript only

`teacher_clone.py` (128 ln) is "consent-gated teacher transcript analysis". The brief wanted
video: CV detection, facial expression, body language, voice tone. None of that exists.

The brief called it a bonus. Treat it as optional and large; do not start it before 1 and 2.

## 4. No live training

`training.py` is a consent ledger plus a *minimised offline worker export*;
`adaptation.train_on_opt_in_csv` trains offline. The brief wanted "training while user
using". Nothing trains live, and this is arguably the correct choice — the adaptation
layer is IRT/KST, which is fitted, not gradient-trained. Do not "fix" this without deciding
which it is.

## Also worth knowing

- Content coverage: ~30 of 164 graph nodes have authored lessons. The engine is complete;
  the curriculum behind it is not.
- `check_simulation` reports `checked=False` in the packaged app because Playwright is not
  shipped in the bundle. Unverified, not broken — the tool says so.
- A diagnostic block cannot be satisfied through chat alone: `POST
  /api/v1/procedure/runs/{id}/advance` is the only way past it. No tool records an answer.

## What is verified present (do not rebuild)

FSRS-6 scheduler (`memory.py`), knowledge graph (`knowledge_graph.py`), IRT + CAT
(`psychometrics.py`), Knowledge Space Theory (`kst.py`), Socratic ladder (`socratic.py`),
on-task reading (`attention.py`), concept/procedure/calculation diagnosis triples
(`curriculum.py`), 102 endpoints, 51 agent tools, 37 tables, 1518 tests, native SwiftUI with
the Morandi palette.
