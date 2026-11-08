# 04 — Open gaps (curated, not generated)

The generator does not overwrite this file. It records what an audit against the original
brief found, so a fresh session does not have to re-derive it.

First audited 2026-11-04; re-audited 2026-11-08 after the answer-channel repair and the
assessment/analytics work. The four items below are no longer all open — their *remaining*
delta is what is recorded now. Durable acceptance evidence:
`docs/evidence/2026-11-08-first-person.md`.

## 1. Unit projects — partial (was absent)

The brief asks for a small project after each unit: a presentation delivered on camera with
speaking, or a research task with limited AI use.

Present: `GET /api/v1/projects` materialises a project per concept in the learner's own
course; `POST /api/v1/projects/{id}/submit` stores the submission, reflection and AI
disclosure, returns the unit rubric and explicitly *formative* feedback. `ProjectEditor`
renders all of it; `ProjectDrafts.swift` keeps unsubmitted writing between visits, scoped
to the signed-in account. `app/perspectives.py` anchors a written observation to the real
project row.

Still missing: camera capture / on-camera presentation recording, and a teacher-scored
certified grade. The feedback string says it is a formative rubric checklist with no
automated correctness claim — do not quietly promote it to a grade.

## 2. Multi-perspective analytics — implemented with declared limits

The brief lists participation, soft skills, creativity, communication, collaboration,
attention %, streak, struggle %.

`app/perspectives.py` now defines all five judgement dimensions with published measurement
definitions, and `perspective_reviews` stores 0–4 scores **with written evidence**, tied to
an artifact that exists. `/api/v1/perspectives`, `/perspectives/dimensions` and the
`PerspectiveCard` native surface expose them. `analytics_data()` includes the rows, and the
Insights view renders them.

The important design decision: an unobserved dimension is `value: null` with status
`insufficient_evidence` (collaboration: `not_measured`), **never** a value inferred from
foreground activity, pointer movement or idle time. Cognitive attention remains explicitly
`not_measured` and is still the last analytics dimension — `test_api.py` and
`test_final_contract.py` pin that. Collaboration requires a teacher-recorded group
observation with `group_size >= 2`; there is still no direct peer-to-peer surface.

These are human judgements with a written rationale, not validated psychometric
instruments. Presenting them as trait scores would be a new defect.

## 3. Formally graded unit tests — partial (was absent)

`app/assessment_book.py` declares one standard per unit topic from the enrolled course
graph, scores each standard from server-graded `Attempt` rows (with both concept id
namespaces bridged), and refuses a unit grade until every declared standard has at least
two graded attempts. `POST /api/v1/gradebook/{unit_key}/grade` freezes a `unit_grades` row
with the standards snapshot; re-grading updates rather than duplicating. `GradebookCard`
renders "NO GRADE YET" instead of an average over the answered half of a unit.

Still missing: alignment to external academic standards (Common Core / AP), proctoring and
external moderation. The API's `scope_note` says the score is a formative, course-local
mastery measure — keep that sentence.

## 4. Teacher clone — still transcript only

`teacher_clone.py` is "consent-gated teacher transcript analysis". The brief wanted video:
CV detection, facial expression, body language, voice tone. None of that exists. The brief
called it a bonus; treat it as optional and large.

## 5. No live training — deliberate, not a missing function

`training.py` is a consent ledger plus a *minimised offline worker export*;
`adaptation.train_on_opt_in_csv` trains offline. The adaptation layer is IRT/KST, which is
fitted, not gradient-trained. Do not "fix" this without deciding which product is wanted.

## Also worth knowing

- Content coverage: many graph nodes have generated lessons rather than hand-authored ones.
  The engine is complete; the authored curriculum behind it is not.
- `check_simulation` reports `checked=False` in the packaged app because Playwright is not
  shipped in the bundle. Unverified, not broken — the tool says so.
- The old claim that "no tool records an answer" is **resolved**: commitment blocks bind
  signed question receipts, `POST /api/v1/attempts` is the single scoring path, and
  `advance(done)` returns 409 until the bound items are answered. See
  `docs/lesson-procedure.md`.
- An unseen topic with no configured tutor provider still returns a structured,
  non-fabricating `notice` rather than a lesson. That is an honest declared fallback, not a
  passing answer — the first-person runner names the step "answer or declared fallback".
- Persistent private simulation creation/edit remains restricted pending owner/read
  isolation. `PROJECT-02` is partial because URL/file-source course creation is still a
  browser-workbench path.
- Actual signing/notarization has not been performed; no Developer ID credentials exist in
  this environment. The release gate fails closed without them.

## What is verified present (do not rebuild)

FSRS-6 scheduler (`memory.py`), knowledge graph (`knowledge_graph.py`), IRT + CAT
(`psychometrics.py`), Knowledge Space Theory (`kst.py`), Socratic ladder (`socratic.py`),
on-task reading (`attention.py`), concept/procedure/calculation diagnosis triples
(`curriculum.py`), the compiled lesson procedure and its answer channel, native SwiftUI with
the Morandi palette.
