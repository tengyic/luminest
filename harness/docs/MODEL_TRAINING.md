# Model configuration, fitting and training boundaries — harness v1.4.0

This document separates three things that are easy to conflate: (1) the *runtime* model
configuration (which provider answers a learner now), (2) *offline research* model fitting
under `model/` and `backend/ml/`, and (3) the new *production BKT registry* that governs
which parameters may affect a learner.

## 1. Runtime model configuration — configuration, not training

`backend/app/model_config.py` is a configuration layer only. It does not fit or update
weights.

- There are two sources, in precedence order: a persisted runtime override at
  `<data_dir>/model_config.json` written by the admin `PUT /api/v1/settings/model-config`
  endpoint (live without a restart), then the environment-derived `Settings`
  (`HARNESS_TUTOR_*`) (`model_config.py:10-18`). `provider.py` consults `effective` on
  every call, so a model entered in the settings UI is live immediately.
- The catalogue is a small, opinionated set of verified endpoints (`model_config.py:60-75`):
  DeepSeek, OpenAI, a free-form OpenAI-compatible endpoint, and Ollama (local). A small
  local Ollama model is a deployment choice, not a claim of model quality.
- The API key is stored in `model_config.json` inside the same trust boundary as the
  database; `GET` never returns it, only `api_key_set` (`model_config.py:20-24`). Operators
  who do not want a persisted key can configure entirely through environment variables.
- The harness **requires** a configured model: `HARNESS_TUTOR_PROVIDER=offline` is rejected,
  and an unconfigured instance reports `unconfigured` and refuses generative work instead
  of emitting deterministic content as if it were authored (`model_config.py:3-8`). A
  configured model that transiently fails degrades gracefully — that is a request-time
  safety net, not a product mode. `config.py:266-284` enforces at boot that production has
  a configured provider and that a remote tutor URL is HTTPS.

## 2. Offline BKT fitting — research code, not a production model

`backend/ml/bkt.py` is an explicitly "deliberately simple, legible baseline": standard BKT
(Corbett & Anderson 1995) with Baum-Welch/EM fitting on **training students only** and
scoring on held-out students (`ml/bkt.py:1-21`). The point is "a correct evaluation
harness, not a leaderboard model." Parameters (`prior`, `learn`, `guess`, `slip`) are kept
in `(0, 1)` (`:32-43`). Its `predict` runs the forward update and returns
P(next response correct) (`:45-54`).

The separate `model/` directory holds a research training pipeline (`model/train.py`)
whose provenance file is explicit about its limits. `model/provenance.json` records:

- `research_only: true`, domain `ednet_english_toeic`, `actual_training: true`, disjoint
  train/validation/test students, seed 42, and SHA-256 hashes of data and source.
- `consent_verification_boundary: null` — this is research data, not the consented learner
  export path described in §3.
- Limitations stated by the artifact itself: "EdNet English/TOEIC is not evidence for
  mathematics"; "No commercial rights or readiness certification"; "NC source and
  derivative research artifact must remain separate"; "No external or prospective
  validation"; observed histories and item effects are predictive associations, not causal
  treatment effects.
- `scripts/package.py` only includes such a research artifact with the explicit
  `--include-research-artifact` opt-in, and the option's help text says it is "never
  promoted to a math model" (`scripts/package.py:1521-1523`).

**Neither the EdNet research artifact nor the offline `ml/bkt.py` fitter is the production
teaching model.** Treat both as analysis inputs, not as a shipped capability.

## 3. Consent and the training-data boundary

`backend/app/training.py` is the trusted, server-side consent ledger and minimized offline
export path (`:1-2`).

- Consent is explicit per user and versioned (`POLICY = 'training-v1'`). Only attempts
  submitted **after** the current opt-in, with a nonblank `option_id` or `answer_text`, are
  eligible. Reasoning, telemetry and identity are not exported (`:17-35`).
- Pseudonymous student ids are HMAC-SHA256 of the user id with a server secret (`:49-50`).
  Exports contain only `student_id, question_id, concept_id, is_correct, timestamp`.
- Thresholds: `MIN_ROWS = 20` eligible samples per user and `MIN_USERS = 30` qualified users
  (`:12-14`). `training_status` reports `worker_eligible`, `automatic_promotion: False`, and
  an explicit scope note: telemetry consent is separate; opt-out excludes existing rows
  from *future* exports but cannot undo an already trained artifact; no model promotion or
  efficacy certification follows (`:38-46`).
- `export_training` writes `training.csv` and a `consent_manifest.json` with mode `0600`,
  refuses to overwrite existing files, signs the manifest with an HMAC, and refuses to
  create an export when no currently consented rows exist (`:57-96`).
- `verify_export` re-checks the HMAC, the data digest, and that each exported student's
  consent is still active; revoked or changed consent fails verification (`:99-116`).

This is an **export boundary for an offline worker**, not in-product training. No graded
result or model in the serving path is derived from it automatically.

## 4. Production BKT registry — fitting made governable

`backend/app/bkt_registry.py` is the boundary between "can these parameters be estimated?"
and "which parameters may affect a learner right now?" (`:1-12`).

- Lifecycle: `candidate → shadow → active`, plus `rolled_back`. Registration requires a
  short lowercase version, a 64-character lowercase SHA-256 digest, an artifact path and a
  metrics object (`:90-111`). No model file is executed or loaded from a client-supplied
  path; serving parameters are read from the registry row and clamped to `(0, 1)`
  (`:10-11`, `:43-48`).
- **Shadow models record predictions but never affect teaching.** `update_state` writes the
  shadow estimate with `serving: False` and a note that it did not affect teaching
  (`:235-274`). The active estimate is an additional, versioned field beside DSR/mastery
  state — "not a certified mastery score" (`:253-261`), and not a replacement for the
  receipt-bound answer path (`:238-243`).
- **Metrics gates** (`promotion_gate`, `:51-74`): at least 20 held-out sequences, at least
  10 held-out students, logloss no worse than baseline, calibration error ≤ 0.10,
  `training_consent_only`, a licence note present, and all four parameters present.
  Every check is returned visibly with its thresholds; `promote_to_active` refuses when
  any check fails (`:159-181`).
- **Promotion and rollback are audited transitions.** Both require a reason at the HTTP
  boundary; promotion records `previous_version` and events carry an actor and reason;
  rollback reactivates the previous active version when known, otherwise serving falls back
  to a documented built-in default (`builtin-default-v1`) (`:148-203`,
  `backend/app/main.py:2147-2191`). The HTTP routes are admin-only.

## 5. What cannot be claimed

- No efficacy or superiority claim: the gate checks minimum evidence and non-regression
  against a baseline; it does not certify that a model is "better" for learners, and there
  is no prospective/external validation of the production registry here.
- No automatic promotion: `training_status` and the export manifest both say
  `automatic_promotion: False`; promotion is an explicit admin action through a gate.
- No claim that the EdNet research artifact is relevant to mathematics training; its own
  provenance says the opposite.
- No claim that a generated interaction, declarative feedback or BKT estimate is a grade
  or a certified mastery measure (see `docs/API.md` and `docs/AGENT_TOOLS.md`).
- No claim that the consented export has been used to train a shipped model; this tree
  contains the export/verification boundary and the registry, not a completed production
  retraining with certified outcomes.
