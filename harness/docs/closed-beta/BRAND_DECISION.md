# Brand decision — Luminest (2026-11-15)

## Status: RESOLVED → **Luminest**

The website prompt pack recorded a pending **Q0 brand conflict** (`Luminfest` in
code/site vs `Luminest` in the request) and forbade the agent from deciding it.
Tengyi resolved it explicitly: *"fix the name of the frontend from luminfest to
luminest"*. A later message offered a fallback (*"if it's hard to change you can
also make the branding luminfest instead"*). That fallback was **not** taken,
with evidence:

| Evidence | Where |
| --- | --- |
| The rename was already complete: 35 replacements, 0 residual user-visible strings | `scripts/rename_frontend_brand.py --check` |
| webapp `npm run build` and beta server `12/12` tests pass after the rename | this session |
| The **shipped** bundle is already branded Luminest | `outputs/Luminest.app/Contents/Info.plist`: `CFBundleDisplayName`/`CFBundleName` = `Luminest` |
| Release artifacts, download site and manifests are already named Luminest | `outputs/Luminest-arm64.dmg`, `.zip`, `outputs/luminest-download-site/` |

Reverting would make the landing page, the shipped `.app`, the download manifest
and the beta control server disagree with each other. That is a regression, not a
simplification. **The condition in the fallback ("if it's hard") was false.**

## Scope of the rename — user-visible strings only

Renamed: page/window titles, brand labels, AX labels, in-app prose, mail subjects,
the tutor system prompt's self-identification, PDF creator metadata, bundle
display name in `package_internal.sh`, and the closed-beta docs/site.

**Deliberately NOT renamed** (internal identifiers; renaming these breaks things):

| Kept as `luminfest` | Why |
| --- | --- |
| `luminfest:ready` / `:hover` / `:select` / `:readout` / `:outcome` | postMessage protocol between sim iframes and the workbench |
| `luminfest.token`, `luminfest.sessions.v1`, `luminfest.role`, `luminfest.appearance`, `luminfest.textScale` | storage / AppStorage keys — renaming orphans existing sessions and preferences |
| `LuminfestCards`, `LuminfestTelemetry`, `LuminfestButtonStyle`, `LuminfestArt`, `LuminfestMotion`, `LuminfestApp` | Swift/JS type names |
| `LuminfestLearningHarness_LearningHarness` | SwiftPM resource bundle name in `AppResources.swift` |
| `web/luminfest-agent.js`, `Luminfest.icns` | file names and injection paths |
| `com.luminfest.learningharness`, `workbuddy.LearningHarness` | bundle identifiers — changing invalidates signing/keychain |
| `LuminfestBackend/` | embedded PyInstaller executable path in `BackendLauncher.swift` |
| `~/Library/Application Support/Luminfest Learning Harness/` | on-disk data directory — renaming **moves/loses existing user data** |

## One-command reverse switch

```bash
cd "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness"
python3 scripts/rename_frontend_brand.py --revert-to-luminfest
python3 scripts/rename_frontend_brand.py --check     # forward audit
```

Verified dry-run: `--revert-to-luminfest --check` reports 34 reversible
replacements and does not write. The switch only touches the source strings in
its `CHANGES` map; it does **not** rename `outputs/closed-beta-site/**`,
`beta_control/**` or the shipped `Luminest.app`. If a full product-wide revert is
ever wanted, those three must be handled explicitly — do not assume the switch
covers them.
