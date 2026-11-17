# Luminest 2.0 — repository and distribution boundary

## Status: policy, not an executed repository split

This working tree is still the **legacy harness v1.4.0**. Nothing in this directory has
created, published, or switched the default branch of a separate Luminest 2.0 repository.
The sections below describe the intended boundary and the actions that remain; they are
not a claim that those actions happened. No push, tag, release or public link was created
by this work.

## 1. The intended clean 2.0 repository

A clean 2.0 repository should contain only 2.0-owned material, with a coherent history and
no legacy build/test residue:

- the 2.0 application source, its own tests and its own package manifests;
- the 2.0 schema substrate and migrations, with a single declared schema version;
- the 2.0 documentation set (security, schema, API, model-governance, tool registry,
  dependency advisories, version truth) **written for the 2.0 code**, not copied from here;
- CI that runs the 2.0 gate, and release metadata that names a 2.0 version.

It should **not** contain the scratch/test residue that accumulates in this tree
(`.pytest-*`, `.tmp*`, `outputs/`, per-OS caches), live secrets (`backend/.env`,
`model_config.json`), or unverified third-party research data.

## 2. `harness/` is preserved as read-only legacy reference

`harness/` — this tree — stays as a **read-only legacy reference** for the 2.0 project.
Its value is the decisions and mechanisms already tested here, which are catalogued in
`harness/legacy_reuse_registry.json` (the root of *this* tree, not of the git repository).
Concretely, the 2.0 team may read and learn from:

- the tenant-isolation guard (`backend/app/user_scope.py`) and single auth resolver
  (`backend/app/security.py`);
- the v13 substrate (`backend/migrations/012_2_0_substrate.sql`,
  `backend/app/db.py:75` with `SCHEMA_VERSION = 13`) and the additive migration discipline
  in `backend/scripts/init_db.py`;
- the closed declarative UI vocabulary (`backend/app/declarative_ui.py`) and its
  `emit_interactive` boundary (`backend/app/harness/toolbox.py:749`; the contract is
  enforced by `backend/tests/test_tool_contracts.py` and `test_declarative_ui.py`);
- the BKT registry governance (`backend/app/bkt_registry.py`) and consent/export boundary
  (`backend/app/training.py`);
- the native launcher schema-version guard
  (`native/Sources/LearningHarness/BackendLauncher.swift:100`).

"Read-only reference" means: no 2.0 build imports from `harness/` at runtime, and no legacy
file is edited as part of 2.0 feature work. Reuse is an explicit decision recorded as
`reference` / `port` / `adapt` / `exclude` in the registry, with an owner, rationale and
risk — not an implicit dependency on a path that may change.

## 3. Creating the public repository is an operator/owner action

This is the part the audit asked to be explicit about rather than aspirational:

- A separate public repository requires **credentials and authority** this working session
  does not have: an account with rights to create a repository, push the initial history,
  and (if desired) configure branch protection, secrets and a release channel. That is an
  operator/owner action, not something a documentation change can perform.
- Consequently there is **no public Luminest 2.0 URL** produced here. Do not infer one from
  the existence of these docs. The legacy alpha verdict already records the same boundary
  for the 1.4.0 Beta: the site was tested only at `127.0.0.1`, the publishing tool returned
  `SITES_APP_NOT_FOUND` on repeated attempts, and Beta was therefore **not** called
  published (`docs/ALPHA_VERDICT_2026-11-15.md`, §6).
- Required operator steps, in order, when the owner chooses to do it:
  1. Create the empty 2.0 repository under the owner's account/organisation.
  2. Populate it with 2.0-owned sources and docs; keep this `harness/` tree as a separate
     read-only reference (archive, submodule pinned to a commit, or internal repo — the
     choice is the owner's).
  3. Import `legacy_reuse_registry.json` and assign an owner to every non-`exclude` entry.
  4. Configure CI, protected branches and any release/signing secrets with the real
     credentials; verify the gate on a clean runner.
  5. Publish only after the owner confirms the distribution/legal gates. Signing and
     notarization remain unresolved red-line items in the legacy tree, and no claim about
     them is made here.

## 4. Scope of changes made in this tree for this audit

Only documentation under `docs/`, the new `scripts/check_version_truth.py`, and the new
`harness/legacy_reuse_registry.json` were added here. Backend/native source files,
migrations, package manifests and beta control were **not** edited by this work; they were
being changed in parallel by other engineers. These docs therefore describe the code as
read at the time of writing and should be re-checked against the final tree before being
published as 2.0 documentation.
