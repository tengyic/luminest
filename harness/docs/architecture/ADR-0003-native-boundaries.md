# ADR-0003 — Native source boundaries

- **Status:** accepted
- **Date:** 2026-11-08
- **Scope:** `harness/native/Sources/LearningHarness`
- **Deciders:** native architecture pass

## Context

The native app is one SwiftPM executable target with 44 `.swift` files sitting flat in
`Sources/LearningHarness/`. Nothing about that layout says which file a change belongs in,
and two files had grown past the point where a reader could hold them: `Core.swift` (1,434
lines) and `BoardEditor.swift` (2,386 lines). Both mixed a dozen responsibilities.

The cost is concrete. `Core.swift` held the JSON wire type, the keychain, the HTTP client,
the navigation enum and the whole `AppStore`; a change to how `Accept-Language` is built
therefore sat two screens away from the state that consumes it. `BoardEditor.swift` held
an AppKit event bridge, a coordinate transform, a 66-property view, and seven modal sheets —
so "the draw surface behaves oddly under pressure" meant reading the whole file.

This ADR records the layout we are moving to, the split executed in this pass, and what is
deliberately still flat.

## Decision

### Target layout

```
Sources/LearningHarness/
  App/                    root scene, app delegate, shell, onboarding gate
  Features/
    Authentication/
    Dashboard/
    Courses/
    Lessons/
    Practice/
    Reviews/
    Projects/
    Tutor/
    Insights/
    Settings/
    Board/                (exists now — see below)
  Shared/
    Components/           reusable views with no domain knowledge
    DesignSystem/         Palette, Accent, button styles, typography
    Networking/           APIClient, wire types, request construction
    Persistence/          keychain, defaults, file-backed caches
    State/                the observable stores
```

`App/`, `Features/{Authentication,Dashboard,Courses,Lessons,Practice,Reviews,Projects,
Tutor,Insights,Settings}` and `Shared/{Components,DesignSystem}` do **not** exist yet.
Directories are created when they receive code, not in advance: an empty
`Features/Authentication/` added "for later" is noise that makes the real structure
harder to see. `Features/README.md` states what belongs in each directory that exists.

`Board` is in that list even though the earlier sketch did not name it, because the
whiteboard is a surface the learner is on, not a component and not a service.

### What goes where

- **`Features/<Surface>/`** — views, view-local state, and the request/response shapes that
  exist only for that surface. A feature may read from `Shared/`.
- **`Shared/`** — anything more than one feature needs, or that has no view at all: the API
  client, value types, the stores, design tokens.

**The rule: a feature may import Shared; Shared may never import a Feature.**

**It is not enforced.** There is no `import` to check, because there is one module: every
file already sees every other file. Today the rule is a review convention documented here
and in `Features/README.md`. Nothing will fail to compile if someone puts a
`StudioView` reference inside `Shared/State/AppStore.swift`.

What enforcement would require, and what it costs: split the target into several SwiftPM
targets (or a project with explicit modules) — `HarnessShared`, `HarnessDesign`,
`HarnessFeatures`, `HarnessApp` — and make the dependency edges the only legal ones. That
buys a compiler error instead of a convention, and costs:

- every `internal` type that currently crosses the line becomes `public`, with a
  public-API surface that now has to be maintained and cannot be changed freely;
- `@testable import` stops reaching the internals the tests currently use, so tests either
  move next to the code they test or grow new public seams;
- the resources bundle is per-target, so `AppResources.bundle` and the localisation lookup
  would have to be re-pointed and re-proved in a packaged `.app` (this exact class of
  failure — resource lookup that resolves on the build machine and not in the `.app` — is
  documented in `AppResources.swift`);
- a full clean build per target, and previews that need the extra module.

That is a real piece of work with a real risk to packaging. It is worth doing when the
directory layout has stopped moving, not now.

## What moved

### `Core.swift` (1,434 lines) — deleted, content split

| New file | Lines | Contents |
| --- | --- | --- |
| `Shared/Models/JSON.swift` | 43 | `JSON` wire value |
| `Shared/Models/AppFailure.swift` | 7 | `AppFailure` |
| `Shared/Models/ChatActivity.swift` | 12 | `ChatActivity` |
| `Shared/Models/Page.swift` | 22 | `Page` navigation enum |
| `Shared/Networking/ServerEvent.swift` | 11 | `ServerEvent` (SSE frame) |
| `Shared/Networking/APIClient.swift` | 199 | `APIClient` + `Accept-Language` + failure detail |
| `Shared/Persistence/SecureSession.swift` | 25 | keychain read/write/remove |
| `Shared/State/AppStore.swift` | 524 | all stored state, `init`, session lifecycle, navigation, the practice session, the one-second clock and silent supervision |
| `Shared/State/AppStore+CoursePlan.swift` | 93 | course/plan/graph derived reads, `saveSetup`, `switchCourse`, `loadMap` |
| `Shared/State/AppStore+Tutor.swift` | 197 | `loadChat`, `sendMessage`, turn media, speech |
| `Shared/State/AppStore+Media.swift` | 91 | deck, external simulations, playground, media posture |
| `Shared/State/AppStore+Harness.swift` | 58 | 9-moves plan and outcome |
| `Shared/State/AppStore+LessonProcedure.swift` | 92 | procedure compile/start/advance, deck `.pptx` save |
| `Shared/State/AppStore+Account.swift` | 94 | settings, consent, export, diagnostics, delete |

Every method is byte-for-byte the original; the split is `extension AppStore` per
responsibility, not a rewrite. Splitting by extension is what makes this safe: the methods
keep their names, their signatures and their place in the type.

One consequence worth naming: **all stored state stays in `AppStore.swift`**, including
the `@Published` properties for the media, harness and procedure sections. Swift forbids
stored properties in extensions, so the choice was either "state and behaviour in one
place, or behaviour split by file with its state left behind". The second is what happened:
`AppStore.swift` is the only file that declares mutable state, and every other `AppStore+*`
file is behaviour. That is a rule a reviewer can check by eye.

### `BoardEditor.swift` (2,386 lines) — moved to `Features/Board/`, split in three

| New file | Lines | Contents |
| --- | --- | --- |
| `Features/Board/BoardEditor.swift` | 1,986 | the view: 70 `@State` properties, body, toolbar/canvas/footer, interaction state machine, commands and keyboard, `GraphicsContext` rendering, live gesture overlays, diagram/curve/catalog/vectorizer/ask sheets |
| `Features/Board/BoardCanvasPrimitives.swift` | 225 | `BoardEraserMode`, `BoardViewport` (board↔view transform, zoom-at-cursor, fit), `Comparable.clamped`, `BoardEventBridge` + its `BridgeView` (pressure, scroll, magnify, first-responder keys) |
| `Features/Board/BoardSheets.swift` | 176 | `TextSheet` (write on board), `ImagePickerSheet` (licence-cleared image insert) |

## Access-level changes

Six members were widened. Each one is marked with a comment at its declaration, and the
total is the whole list — nothing was widened silently.

| Member | Before | After | Why |
| --- | --- | --- | --- |
| `AppStore.epoch` | `private` | `internal` | read by five `AppStore+*` files to discard replies that arrive after a session change |
| `AppStore.activeSeconds` | `private` | `internal` | written by `updateSettings` in `AppStore+Account.swift` |
| `AppStore.playSpeech(_:version:)` | `private` | `internal` | called by the silent supervisor in `AppStore.swift` and by `sendMessage` in `AppStore+Tutor.swift` |
| `BoardEventBridge` | `private` (file) | `internal` | used by `BoardEditor.body` from another file |
| `TextSheet` | `private` (file) | `internal` | same |
| `ImagePickerSheet` | `private` (file) | `internal` | same |

What was *not* widened, and why: the other 15 `private` stored properties on `AppStore`
and all 66 `@State` properties on `BoardEditor` stayed `private`. Moving the code that owns
them was rejected where the move would have cost more access than it bought — see
"Deliberately not split".

## Evidence

**Subdirectories compile and do not move resources (checked before anything was moved).**
A probe `enum` was added at `Shared/Probe/Probe.swift`, the package was built (success), and
`LocalizationTests` + `ContentLanguageTests` were run with the probe in place: 13 tests, 0
failures. The probe was then deleted.

Resource lookup cannot be affected by source placement in this package: `AppResources.bundle`
resolves through `Bundle(for: BundleFinder.self)`, which is the built binary's bundle, not a
path derived from the source file. There is no `#file`, `#filePath` or
`URL(fileURLWithPath:)` relative to `Sources/` anywhere in the target (grep: no matches), and
the resource declaration `resources: [.process("Resources")]` is relative to the target root,
which did not move.

**Symbol inventory, before and after.** A throwaway script walks every `.swift` file and
emits `kind name` for every declared type, function and property, sorted.
Baseline: 3,564 entries, kept at
`/Users/tengyi/WorkBuddy/2026-10-23-22-10-20/outputs/raw/architecture/swift_symbols_baseline.txt`;
the post-split run is beside it as `swift_symbols_after.txt` (3,570 entries).
After both splits the sorted `kind name` list is identical except for the six
`extension AppStore` declarations and the two `AppStore` property access changes in the
table above. An access-annotated variant (`kind name access`) diffed against `git show HEAD:`
of the two original files reports exactly the six rows in the table below and nothing else.
No type was renamed, no signature changed, nothing appeared or disappeared.

This matters more than a green build: `swift build` compiles a subtly changed signature
happily. The inventory is the instrument that would have caught it.

**Tests.** 113 XCTest cases before the first move, 113 after the last one, 0 failures both
times (`swift test --disable-sandbox --scratch-path /tmp/arch-native`). The swift-testing
suite reports 0 tests in 0 suites before and after.

The last of those runs was taken on an isolated copy of the package (`/tmp/verify-native`,
with `/tmp/backend` linked to `harness/backend` so the schema-version test still runs) and
with the two files being edited concurrently by other passes — `NativeQA.swift` and
`ProjectsInsightsSettings.swift` — restored from `HEAD`. The shared tree did not compile at
that moment because of an in-flight edit to `NativeQA.swift` (`navigateRetry(_:text:)` calls
a signature that no longer exists there); nothing in this pass touches that file. Restoring
those two files is what makes the 113-test figure attributable to this change rather than to
someone else's half-finished work.

**Line count.** The two files held 3,820 lines (1,434 + 2,386) before the pass and 3,855
after (17 files): +35, all of them `import` lines, file headers and one blank line at a
join. No logic was added.
(The tree total cannot be used for this check — other files were being edited concurrently.)

## Seams found in `BoardEditor.swift`, and the ones that are not there

What genuinely separated:

1. **Canvas primitives** — `BoardViewport` and the `BoardEventBridge` never touch the
   view's state. They are a coordinate transform and an `NSView` adaptor; the bridge's only
   contract is seven closures. Moving them removes the AppKit surface from the file a
   SwiftUI reader opens.
2. **Self-contained sheets** — `TextSheet` takes a `@Binding` and a closure;
   `ImagePickerSheet` owns its own `@State` and talks to `BoardStore`. Neither reads the
   editor's state, and the only thing they needed from it was to be visible across files.

What is **not** a seam, and why:

3. **The selection/tool state machine does not exist as a type.** `press`, `drag`,
   `release`, `resize`, `erase`, `keyPress`, `align`, `distribute`, `stack`, `paste` are
   `fileprivate` methods on the `View` that read and write 66 `@State` properties. The
   *model* types they operate on — `BoardTool`, `BoardSelection`, `ResizeHandle`,
   `SnapGuide`, `SnapEngine`, `BoardGeometry`, `AlignCommand`, `DistributeCommand` — are
   already extracted, in `BoardKit.swift`. So the state machine's data is separated and its
   transitions are not. Extracting the transitions means introducing a
   `BoardInteraction`/`BoardEditorModel` type and moving every `@State` write into it. That
   is a rewrite of the drawing surface, not a move, and it changes behaviour (SwiftUI update
   ordering, undo coalescing, gesture liveness). It is not in this pass.
4. **Board document persistence is not in this file at all.** `BoardNode`, `BoardSnapshot`,
   `BoardStore` (load/save, `beginEdit`, `reconcile(to:)`, mutation batches, undo/redo) and
   `BoardRenderer` live in `Board.swift`. `BoardEditor.swift` only calls `board.beginEdit()`
   / `board.add(node:)` / `board.mutate(...)`. There was nothing to separate.

A split of `BoardEditor.swift`'s remaining extension blocks was considered and rejected:
each block (`Interaction`, `Commands`, `Rendering`, `Live gesture`, `AI line diagrams`,
`Ask the tutor`) is `fileprivate`/`private` and closes over the same `@State`. Putting any
one of them in another file would force dozens of `private` → `internal` widenings — all 66
`@State` properties plus 57 `fileprivate`/`private` methods — which removes the only thing that
currently stops other files from mutating an editor's transient gesture state. That is a
cost with no structural benefit: the coupling is the state, and the state cannot move.

## Deliberately not split

| Thing | Reason |
| --- | --- |
| The practice session in `AppStore` (`startQuestion`, `submitAnswer`, `finishQuestion`, `requestFinishQuestion`) | ~56 lines. Moving it would have widened `frozenAnswer`, `questionGeneration`, `eventID`, `lastTick` and both `pendingQuestion*` setters — six access changes for a 56-line move. Left in `AppStore.swift`. |
| The one-second clock and silent supervision (`tick`, `refreshTelemetryMonitor`, `silentCheckIfDue`, `recordInteraction`) | ~130 lines, but it owns eight private clock/monitor properties that `logout`, `selectConcept` and `updateSettings` also write. Moving it meant widening all eight. Left in `AppStore.swift`. |
| `AppStore` stored state | Stored properties cannot live in an extension. Keeping all of it in one file is the price of splitting behaviour at all, and it is a checkable rule. |
| `BoardEditor` view + all extension blocks | See seam 3/4 above. |
| `Board.swift`, `BoardKit.swift` | Not owned by this pass, and `BoardKit`'s types are shared by the editor, the renderer and the export path. |

## What is still flat, and the order to split it

42 files remain flat. Nothing here is blocked on design; it is blocked on ownership and on
doing one surface at a time so each move can be proved with the same inventory instrument.

Ordering, by "how independent is it" then size:

| Order | File | Lines | Target | Note |
| --- | --- | --- | --- | --- |
| 1 | `Design.swift` | 972 | `Shared/DesignSystem/` | `Palette`, `Accent`, `Color`/typography extensions, `Card`, `Eyebrow`, `Tag`. Zero domain knowledge — the easiest and highest-leverage move, since everything else depends on it. |
| 2 | `StateViews.swift` | 749 | `Shared/Components/` | `ViewState`, `StateContainer`, empty/loading/failure views. Generic over `Value`; no domain types. |
| 3 | `Localization.swift` + `Theme.swift` | 185 + 146 | `Shared/DesignSystem/` | Small, shared by everything. `Localization` carries the resource-bundle lookup, so move it only with the localisation tests green. |
| 4 | `BoardKit.swift` | 788 | `Features/Board/` | Pure geometry/snap/align model used only by the board; must move *before* `Board.swift` so the feature directory owns its model. |
| 5 | `Board.swift` | 988 | `Features/Board/` | Document model + `BoardStore` + `ImageCache`. Re-check `CanvasView.swift`, which extends `BoardNode`. |
| 6 | `CanvasView.swift` | 728 | `Features/Board/` | Its own tool enum and `NodeView`; overlaps `BoardEditor`'s drawing. Merge or retire, do not just move. |
| 7 | `DeckEditor.swift` | 1,467 | `Features/Lessons/` | Largest remaining file; `DeckStyle`/`DeckDocument` model plus `DeckEditorView`. Same shape of problem as `BoardEditor.swift`: expect the same 1+2 split. |
| 8 | `LessonProcedure.swift` | 933 | `Features/Lessons/` | `LessonProcedureState` is already referenced from `AppStore+LessonProcedure.swift`; move model and card together. |
| 9 | `Stage.swift` | 778 | `Features/Lessons/` | `StageStore` + panes; depends on board and deck. |
| 10 | `Studio.swift` | 934 | `Features/Courses/` | `StudioView`, `PlotMath`, simulation views. |
| 11 | `TodayKnowledge.swift` | 773 | `Features/Dashboard/` + `Features/Reviews/` | Contains `TodayView`, `KnowledgeView` **and** `ReviewView` — three surfaces in one file; split along those first. |
| 12 | `LuminfestApp.swift` | 874 | `App/` | `AppDelegate`, `RootView`, `AppShell`, `OnboardingView` (→ `Features/Authentication/`), `SidebarLayout`. |
| 13 | `NativeQA.swift` | 1,625 | `App/` (or a `QA/` target) | The in-process driver. Largest file left, but test-only in practice; moving it is mechanical and should follow the features it drives. |
| — | `ProjectsInsightsSettings.swift`, `Flashcards.swift`, `CourseSetup.swift`, `LectureMode.swift`, `Voice*.swift`, `MediaTools.swift`, `Markdown*.swift`, `Playground.swift`, `PerfectFreehand.swift`, `SessionVault.swift`, `ClickTelemetry.swift`, `RewardCenter.swift`, `HarnessPlan.swift`, `TeacherProfile.swift`, `GuidedTour.swift`, `LumiCompanion.swift`, `BackendLauncher.swift`, `AppResources.swift`, `WindowStream.swift`, `RealtimeKey.swift`, `SoundBank.swift`, `CelebrationOverlay.swift`, `GeneratedSimulation.swift`, `SimulationDetail.swift`, `QuestionView.swift`, `BoardMenu.swift` | 4,000–13,000 B each | per surface | Mostly one file per surface already, or genuinely shared. Move as each feature directory is opened; no split needed. |

Rules for every one of these moves, so the proof stays cheap:

1. Move bytes. Do not reformat, rename or "tidy while here".
2. Re-run the inventory before and after; the sorted `kind name` list must differ only by the
   new `extension` declarations.
3. Any `private` that has to be crossed becomes `internal` and is added to a table in the
   PR description, never widened quietly.
4. `swift test` count must be unchanged. If it drops, a test was moved out of the target's
   reach — fix the move, do not delete the test.

## Consequences

- A reader looking for "how does the app talk to the server" now opens
  `Shared/Networking/APIClient.swift`, and one looking for "what does the learner see" opens
  `Features/<surface>/`. That is the whole benefit and it is real.
- `AppStore.swift` at 523 lines is now behaviour-plus-state; the other six `AppStore+*` files
  are behaviour only. A future reader who puts state in an extension will not be able to
  compile, which keeps the convention honest without a document.
- `BoardEditor.swift` is still 1,986 lines and still the hardest file in the target. This ADR
  does not claim otherwise; it records why the remaining split is a rewrite and what the
  rewrite is (a `BoardInteraction` type owning the gesture/selection state).
- The directory boundary is a convention. It will hold as long as reviewers say no to
  `Shared/` importing a feature; if that stops happening, this ADR is the record that the
  convention was the decision and the compiler was never asked.
