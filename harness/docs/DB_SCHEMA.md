# Database schema — harness v1.4.0 / v13 substrate

## 1. Version truth

- The authoritative schema version is `backend/app/db.py:75`: `SCHEMA_VERSION = 13`.
  `backend/scripts/init_db.py` (the initializer/migrator) imports that constant and
  stamps `schema_version` row `id=1` with it; it accepts every historical version
  `KNOWN_VERSIONS = (None, 1, …, 13)` so an operator is never forced to hand-edit an
  older database.
- Migration file numbers are one behind the version they produce:
  `011_project_grading.sql` is **v11 → v12** and `012_2_0_substrate.sql` is **v12 → v13**
  (first lines of both files). Do not read the filename as the schema version.
- The native client pins the same number at compile time:
  `native/Sources/LearningHarness/BackendLauncher.swift:100`
  `expectedSchemaVersion = 13`. `BackendLauncherTests` parses `backend/app/db.py` and
  fails if the two disagree, so drift is a red test rather than a shipped mismatch
  (see `docs/XCUITEST_BOOTSTRAP.md`).
- `scripts/package.py` refuses to ship when the frozen backend's own `SCHEMA_VERSION`
  disagrees with the sources (`expected_schema_version()` at `scripts/package.py:226-236`,
  checked at `:1054-1059`). One release therefore carries one matched pair.

## 2. Migration path and discipline

`backend/scripts/init_db.py` is explicitly **non-destructive**: "new tables are created and
new columns are added, and no existing row is ever rewritten or dropped." Its header
records the whole history (v1→v2 training consent, v3 memory/harness runs, v4 beta
multi-user, v5 course enrollment, v6 token split + waitlist double opt-in, v7 build-path
parity, …). The SQL files under `backend/migrations/` are the PostgreSQL reference DDL;
init_db applies the same additive change to SQLite through
`Base.metadata.create_all` and an `ADDED_COLUMNS` map.

- **`migrations/011_project_grading.sql` (v11 → v12)** adds
  `projects.assistance_level TEXT NOT NULL DEFAULT 'none'` (assistance disclosure is a
  fact about a submission, not an inference about AI use) and creates `project_grades`
  with a `supersedes` pointer: a correcting human review never erases the earlier review —
  the history is the evidence. It is indexed on `(user_id, project_id, created_at)` and
  `user_id` is `NOT NULL ... ON DELETE CASCADE` (the table is in
  `USER_SCOPED_TABLES` as `project_grades`).
- **`migrations/012_2_0_substrate.sql` (v12 → v13)** creates the 2.0 substrate: the
  declarative-interaction tables, the learner concept graph tables, and the BKT registry
  tables. It states the tenancy rule in the file: every learner-owned table has
  `NOT NULL user_id ... ON DELETE CASCADE` **and** is added to
  `backend/app/user_scope.USER_SCOPED_TABLES` in the same change. No existing row is
  rewritten or dropped.

## 3. New v13 tables

All are `CREATE TABLE IF NOT EXISTS` with indexes; names below are the real ORM mappings
in `backend/app/db.py`:

| Table | ORM class (`db.py`) | Purpose |
| --- | --- | --- |
| `interactive_artifacts` | `InteractiveArtifact` (`:790`) | A validated model-emitted declarative spec persisted under the learner. Columns include `concept_id`, `spec`, `schema_version`, `source`, `created_at`. |
| `interactive_evidence` | `InteractiveEvidence` (`:804`) | Append-only learner state frames and the derived evidence. **Not an `Attempt`, not a grade.** |
| `learner_concept_facets` | `LearnerConceptFacet` (`:817`) | Per-learner, multi-dimensional concept state. |
| `learner_concept_edges` | `LearnerConceptEdge` (`:838`) | Per-learner typed relations between concepts. |
| `concept_evidence_ledger` | `ConceptEvidenceLedger` (`:857`) | Append-only provenance for facet updates — a correction never erases the earlier observation. |
| `bkt_model_registry` | `BktModel` (`:872`) | Registered BKT candidates with metrics, digest, `stage` (`candidate`/`shadow`/`active`/`rolled_back`), `previous_version`. Operator/global domain. |
| `bkt_model_events` | `BktModelEvent` (`:895`) | Append-only promotion/rollback events with actor, reason and timestamp. |

The first five are learner-owned and appear in `USER_SCOPED_TABLES` in
`backend/app/user_scope.py:67-96`, so the ORM read guard enforces a `user_id`/PK predicate
on every `SELECT` against them. `bkt_model_registry` / `bkt_model_events` are deliberately
**not** in that list: they are operator/global model-control tables, not per-learner rows.

## 4. Native launcher guard

`BackendLauncher.swift` adopts a server only after checking its `/api/v1/health` payload:

- `service` must equal `"luminfest-learning-harness"`, otherwise `.foreignService`
  (a stranger's server on the port is never adopted).
- `ready` must be true, otherwise `.notReady`.
- `schema_version` is three-valued: `declared(Int)` / `unreadable` / `absent`. Only
  `declared(13)` equal to `expectedSchemaVersion` is adopted; a different integer or an
  unreadable value is `.schemaMismatch`. A server with no version field is adopted with an
  explicit "unknown" verdict — that protects older builds which predate the field and
  cannot emit it.
- The expectation is compile-time by design (`:87-100`): reading it from the server would
  compare the server with itself. Drift between the Swift constant and `db.SCHEMA_VERSION`
  is caught by `BackendLauncherTests`, which parses the Python source rather than trusting
  a transcribed number.

## 5. What is not claimed

- No DDL in these migrations rewrites or drops existing rows; do not assume a destructive
  upgrade path exists.
- `init_db.py` is the path used for SQLite development and for bringing an older database
  forward; the `migrations/*.sql` files are the PostgreSQL reference, not an alternate
  automatic runner that was verified here.
- The v13 substrate tables are created; the surrounding product behaviour (generated
  interactions, learner graph, BKT registry) is described in `docs/API.md`,
  `docs/MODEL_TRAINING.md` and `docs/AGENT_TOOLS.md`. Schema presence is not a claim of
  end-to-end acceptance.
