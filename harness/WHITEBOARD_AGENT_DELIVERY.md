# Whiteboard Agent — Delivery & Verification Note

> Repo: `tengyic/luminest` · branch `feature/a11y-i18n`
> Commit: `1e40086 feat(whiteboard): add isolated scratch-region draw agent (teacher-safe)` (pushed to `origin/feature/a11y-i18n`)
> State captured: 2026-11-10

## 0. Premise correction (important)

The previous session's closing summary asserted the whiteboard work was
**“not committed or pushed”** and that **“8 files [were] staged-eligible.”**
That was stale. By the time this note was written, the feature had already been
committed and pushed in `1e40086`. Verification against the live tree confirms:

| Prior summary claim | Reality on disk |
|---|---|
| Not committed, 8 files staged-eligible | Committed in `1e40086` (8 files) **and pushed to `origin/feature/a11y-i18n`** |
| `security.py` catalog entry uncommitted | Whiteboard-agent catalog PUBLIC_ROUTES entry is in committed `security.py:275` |
| 12 full-suite failures, none from this feature | Full suite now **2148 passed / 2 skipped / exit 0** — all 12 resolved by concurrent other-session stabilization |

So there was **no whiteboard work left to commit**. The only outstanding
uncommitted changes on the branch belong to a *different, in-progress* feature
(see §4).

## 1. The 8 files (all in `1e40086`)

```
harness/backend/app/routes_whiteboard_agent.py    +68   (routes: catalog / boards / draw)
harness/backend/app/harness/whiteboard_agent.py   +481  (the agent: scratch-region draw, resolver contract)
harness/backend/app/harness/board.py              +32   (list_for_owner + SCRATCH_BOARD_PREFIX isolation)
harness/backend/app/harness/visual_specs.py       +630  (visual spec authoring the agent consumes)
harness/backend/app/security.py                    +5   (catalog added to PUBLIC_ROUTES)
harness/backend/app/feature_routers.py             +4   (router registered / frozen-bundle probe)
harness/backend/tests/test_whiteboard_agent.py    +432  (regression suite)
harness/scripts/package.py                         +3   (packaging surface)
```

## 2. Auth / isolation design

- **`GET /api/v1/whiteboard-agent/catalog`** — public read (static preset data, no
  secrets). Declared in `security.PUBLIC_ROUTES`; no resolver on the route, so the
  frozen-bundle probe and anonymous reads both succeed.
- **`GET /boards` and `POST /draw`** — each route carries
  `dependencies=[Depends(require_principal('api', 180))]` explicitly. Route-level
  deps run before `authenticated`, so `request.state.token` is still set for the
  heartbeat. No router-level global dependency (it was removed because it broke the
  token cache path for these routes).
- **Agent scratch boards are isolated from the teacher's board list** by construction:
  the agent writes `agent-scratch-<hash>.json` while `list_for_owner` only globs
  `board-*.json`. The agent board therefore never appears in the teacher's
  `GET /boards`; it is reachable only through the agent's own list path. This is the
  intended “no collision with teacher content” guarantee, not a bug.

## 3. Verification matrix

| Scope | Command | Result |
|---|---|---|
| Whiteboard agent (targeted) | `pytest tests/test_whiteboard_agent.py` | **43 passed** |
| Full backend suite | `pytest` (2100+ tests, 300s/timeout ceiling) | **2148 passed, 2 skipped, exit 0** |

Real-HTTP end-to-end coverage includes: catalog returns 200 anonymously **and**
with a credential; draw is refused without auth; spec write creates a real board
node over HTTP; concurrent identical requests draw exactly one node; forged
envelope fields are refused; unfaithful/unsafe resolver output never reaches the
board.

## 4. Outstanding uncommitted changes — NOT this feature (left untouched)

These belong to a concurrent, in-progress **model-config** feature owned by another
session. They were deliberately **not** touched:

```
?? harness/backend/app/model_config.py          (new, untracked)
?? harness/backend/app/routes_model_config.py   (new, untracked)
 M harness/backend/app/feature_routers.py
 M harness/backend/app/main.py
 M harness/backend/app/security.py              (model-config catalog PUBLIC_ROUTES entry)
 M harness/scripts/package.py
```

`routes_model_config.py` already wires `dependencies=[Depends(require_principal)]`
on all four protected routes and keeps the catalog public — which is why the two
app-wide auth-gate failures from the earlier assessment are now cleared.

## 5. Conclusion

The whiteboard agent feature is complete, committed, pushed, and covered by a green
suite. The earlier “12 failures” were a transient artifact of other sessions’
in-flight edits; the tree has since stabilized to a fully green run. No action is
required on the whiteboard side. The model-config feature above should be committed
by its owning session when it is ready.

## 6. The visual host bundle — how it is built, and why it is committed

`native/Sources/LearningHarness/Visuals/` is **generated**, and it is committed on
purpose: it is the WKWebView document root declared as `.copy("Visuals")` in
`Package.swift`, so a checkout that lacks it builds an app whose every visual renders
`RENDERER_ASSETS_NOT_INSTALLED`. SwiftPM's `.process` rule would flatten the directory
anyway, which is why the hierarchy (`vendor/…`, `vendor/tikzjax/fonts/…`) has to be
preserved rather than rebuilt at package time.

Regenerate it — never hand-edit it:

```sh
cd harness/web-visuals
npm ci                 # first time only; node_modules is gitignored
node build.mjs         # writes out/, then copies the tree into native/…/Visuals/
node test/smoke.mjs    # drives all eight renderers in headless Chrome
```

What `build.mjs` guarantees, in order: the catalog is exported from
`app/harness/visual_specs.py` (the backend is the single source of truth, not this
directory); the ESM renderers are bundled by esbuild; plotly/jsxgraph/3Dmol/mafs/mathbox
CSS are copied; the TikZ TeX-WASM engine is patched off its S3 base and all 140 Bakoma
fonts are shipped; **KaTeX's stylesheet and its 60 font files are vendored for the `tex`
type**; every local `src`/`href` in `index.html` is resolved against the produced tree; a
SHA-256 manifest is written. Anything missing aborts the build rather than producing a
partial bundle that looks fine until a learner opens one renderer.

`node test/smoke.mjs` treats a 404 as a failure on purpose. A missing font does not raise —
the renderer falls back and reports success — so a green status table is not evidence on
its own. That change is what caught the KaTeX path bug described in `CHANGELOG.md`.
