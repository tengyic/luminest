# API map — harness v1.4.0

Base prefix: `API = '/api/v1'` (`backend/app/main.py:74`). Routes are defined in
`backend/app/main.py` and the `routes_*.py` modules. This document emphasises the routes
changed or added for the 2.0 substrate; it is not a complete catalogue of every endpoint.

## Authentication conventions

- Almost every route below declares `auth=Depends(authenticated)`, which resolves the
  principal through `security.resolve_account` (bearer token, rate limit, status and erasure
  checks) and yields `(db, user)` (`main.py:994-1013`, `backend/app/security.py:144-195`).
- **Admin-only** routes add `require_admin(user)`, which accepts roles `admin` or `staff`
  and otherwise raises `403` (`main.py:4514-4516`). A separate reviewer gate applies to
  summative project grading (below).
- `block_exam_help(db, user)` (`main.py:304`) is applied to study/analytics/agent routes;
  during an exam it refuses help rather than silently degrading.
- For contrast, the deliberately public routes are enumerated in
  `security.PUBLIC_ROUTES` (`security.py:265-289`): health, legal, share links, register /
  login / refresh / forgot / reset, feedback, waitlist, playground, and two static catalog
  reads (`whiteboard-agent/catalog`, `settings/model-config/catalog`). Everything else must
  have a resolver in its dependency tree.

## Route summary

| Method & path | Auth | Purpose |
| --- | --- | --- |
| `GET /api/v1/analytics` | authenticated + exam guard | Progress/measurement analytics; `dimensions[].status` is `observed` / `insufficient_evidence` / `not_measured`, never a fabricated zero. |
| `GET /api/v1/interactive/registry` | authenticated | Publishes the closed declarative component and expression vocabulary (`docs/AGENT_TOOLS.md`). |
| `GET /api/v1/interactive/example` | authenticated | A validated native-renderable probe spec; **authored**, not model output. |
| `POST /api/v1/interactive/validate` | authenticated | Validate/normalize a model spec; `422` with a named reason on refusal. |
| `POST /api/v1/interactive/evaluate` | authenticated | Recompute one frame from a spec + state via the closed evaluator. |
| `POST /api/v1/interactive/evidence` | authenticated | Record one evidence frame against a stored artifact. Not an `Attempt`; not a grade. |
| `GET /api/v1/interactive/artifacts/{artifact_id}` | authenticated | Reload one generated artifact; looked up with `user_id == user.id`, `404` otherwise. |
| `GET /api/v1/learner-graph` | authenticated | This learner's four-facet concept graph with provenance and honest unknowns. |
| `GET /api/v1/bkt/registry` | authenticated | Read BKT serving/shadow/candidate state and events. |
| `POST /api/v1/bkt/models` | authenticated + **admin** | Register a candidate version (metrics, digest, licence note). |
| `POST /api/v1/bkt/models/{version}/promote` | authenticated + **admin** | Move `candidate → shadow` or `shadow → active`; reason required; promotion gate enforced. |
| `POST /api/v1/bkt/models/{version}/rollback` | authenticated + **admin** | Roll an active model back; reason required; restores the previous active version when known. |
| `POST /api/v1/projects/{project_id}/grade` | authenticated + **configured reviewer** | Human summative rubric judgement; `403` if the account is not an assessment-book reviewer. |
| `POST /api/v1/agent/chat` | authenticated + exam guard | One agentic turn: final message + full inspectable event trace. |
| `POST /api/v1/agent/stream` | authenticated + exam guard | The same turn over SSE, one event per loop step. |

## Declarative interactive runtime (`main.py:2033-2117`)

- `GET /interactive/registry` returns `declarative_ui.registry()` — component roles, required
  fields, expression operators/arities, limits and the explicit note that feedback is
  authored guidance, not a grade (`backend/app/declarative_ui.py:71-91`).
- `GET /interactive/example` builds a slider/slider/readout/feedback/reset probe, runs the
  same validator a generated spec will use, and returns the normalized spec. It is an
  authored probe, not model output.
- `POST /interactive/validate` calls `declarative_ui.validate(payload)`; a `ValueError`
  becomes `422` with the validator's named reason. The validator refuses unknown fields,
  unsupported component types/operators, over-depth expressions, unknown `ref` ids, and
  more (`declarative_ui.py:155-258`).
- `POST /interactive/evaluate` validates `payload.spec`, then recomputes `inputs`,
  `readouts`, `feedback`, `reset_state` and an `evidence` block from `payload.state`.
  The evidence block states it is **not an Attempt, not a receipt-bound answer, and not a
  grade** (`declarative_ui.py:322-361`).
- `POST /interactive/evidence` does **not** accept a client-supplied spec: it looks up the
  artifact under the authenticated learner via `interactive_runtime.record_evidence`,
  checks the state against that artifact's declared inputs, evaluates with the same closed
  evaluator, and stores an append-only frame (`main.py:2088-2104`,
  `backend/migrations/012_2_0_substrate.sql`). The row is evidence of an authored task.
- `GET /interactive/artifacts/{artifact_id}` selects by both id and `user_id`; another
  learner's artifact is indistinguishable from a missing one (`404`).

## Learner graph and BKT registry (`main.py:2119-2191`)

- `GET /learner-graph` returns `learner_graph.snapshot(db, user, concept_id)` — the
  learner's four-facet concept state with provenance and explicit unknowns.
- `GET /bkt/registry` returns `bkt_registry.snapshot(db)` — models, recent events, the
  serving model, and a documented built-in fallback
  (`backend/app/bkt_registry.py:125-145`). Read-only for any authenticated user.
- The three mutating `/bkt/models*` routes are admin-only. Promotion is a two-step
  lifecycle (`candidate → shadow → active`) and `promote_to_active` refuses when
  `promotion_gate` fails (held-out sequence/student minimums, logloss no worse than
  baseline, calibration tolerance, training-consent-only, licence note, parameters
  present — `bkt_registry.py:51-74`, `:159-181`). A reason string is required at the HTTP
  boundary for promotion and rollback. See `docs/MODEL_TRAINING.md`.

## Projects and analytics (`main.py:2030`, `:2685-2759`)

- `GET /projects` materialises one row per concept in the learner's own course only.
- `POST /projects/{id}/submit` records the learner's submission, AI disclosure, reflection
  and assistance level, and returns **formative** rubric feedback with an explicit
  "no certified grade or automated correctness claim" note.
- `POST /projects/{id}/grade` is the summative path: it requires the caller's e-mail to be
  in `assessment_book.reviewer_emails()` (`403` otherwise), reads the project regardless
  of owner (reviewer context), requires an existing submission (`409`), and writes a
  `project_grades` row with a `supersedes` pointer so corrections keep history.
- `GET /projects/{id}/grades` is visible to the owning learner or a configured reviewer;
  otherwise `404`.
- `GET /analytics` returns analytics with measurement dimensions; empty measurements are
  reported as such, never inferred from foreground activity.

## Agent turns (`main.py:4275-4399`)

- `POST /agent/chat` runs one turn and returns the final message plus the full event trace,
  provider/`answered_by`, grounding, a `notice` (reason + next action) when the turn was a
  declared fallback, surfaced `interactive` artifacts, media, and token usage. When the
  turn is scoped to a real concept, user and assistant messages are persisted to the same
  `messages` table the classic chat path writes, so history stays coherent across surfaces.
  A completed turn consumes its raised-hand interrupts exactly once.
- `POST /agent/stream` is the same turn over SSE. The provider adapter is synchronous, so
  events are produced per loop step and flushed in order — **token-level streaming is not
  faked**. Only the six contract event types travel on the wire; the reasoning channel
  appears only when developer mode was requested. Events are generated lazily so an
  activity chip arrives while the action happens, and cancellation is server-side via a
  disconnect scope event (a disconnecting client still books a `refused` turn).
- In both paths, generated interactions are artifacts/evidence carried with the turn —
  they are not grades.

## Not claimed

- Presence of a route is not evidence of a passing end-to-end journey or of a public
  Beta; see `docs/ALPHA_VERDICT_2026-11-15.md` §6 for the hosting/publication boundary.
- Audio/video streaming contracts and the full tool catalogue are out of scope here;
  tool behaviour is described in `docs/AGENT_TOOLS.md`.
