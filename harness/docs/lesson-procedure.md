# The lesson procedure

**Status:** implemented. `app/harness/teaching/procedure.py`, `app/procedure_service.py`,
`app/routes_procedure.py`, `native/Sources/LearningHarness/LessonProcedure.swift` (the card
and the artifact sheet), `tests/test_lesson_procedure.py`.

A **lesson procedure** is the run of show for one concept: an ordered list of activities,
each bound to one artifact, priced in minutes, compiled on the server from this learner's
own evidence and the material this instance actually holds.

The harness has three layers of teaching decision, and they answer different questions:

| layer | module | question | scope |
|---|---|---|---|
| policy | `harness/teaching/policy.py` | which *move* now? | one turn |
| session | `harness/teaching/session.py` | which *phases* does this turn walk through? | one turn |
| procedure | `harness/teaching/procedure.py` | which *activities*, in what order, through which artifacts? | one lesson |

The first two were already there and both are per-turn. The missing layer was the
sequence: a model that reads "teach, through a figure" performs that move well and then
invents the next activity from its own preferences — a video here, three questions there,
a deck nobody authored. The procedure removes that choice. It is compiled, persisted,
delivered in the system prompt, and advanced one block at a time.

## The four rules

Everything in `procedure.py` follows from these. If a change breaks one, the change is
wrong.

### 1. An activity is chosen by what it does to *evidence*

Each activity declares a `role`:

| role | activities | what it produces |
|---|---|---|
| `input` | `deck`, `video`, `explain`, `worked_example` | nothing measurable |
| `commitment` | `simulation`, `practice`, `discussion`, `recap` | a scored observation, or a visible attempt |
| `exit` | `close` | nothing; it ends the lesson |

`practice` is therefore always present and always last among the commitments: it is the
only block that produces a scored observation, and a lesson without it is a presentation.
Conversely an input is *skipped entirely* once the learner is already answering above the
bar (`recent_accuracy >= 0.80` or `mastery >= 0.80`), because a deck then spends the
budget on what they already know.

### 2. One input per lesson

`deck`, `video`, `explain` and `worked_example` are **alternatives, not a sequence**. A
lesson that shows a video *and* a deck has spent the budget twice on the same job, and the
second one is the one the learner skips.

Which one is chosen, in order:

| condition | input | why |
|---|---|---|
| capable (see above) | *none* | practice teaches them |
| `top_error == 'procedural'` and a worked example exists | `worked_example` | a solved instance repairs a wrong *process*; an overview does not |
| first exposure and a curated video exists | `video` | a video orients; it repairs a specific error badly |
| an authored deck exists and no deck ran in the last 24 h | `deck` | ordered and revisitable, built from the lesson itself |
| a curated video exists | `video` | no deck available, so the video carries orientation |
| a worked example exists | `worked_example` | no deck, no video |
| nothing else | `explain` | the tutor teaches directly rather than pretending an asset exists |

The video row used to carry a subject gate — science, social science and computing only —
on the grounds that a mathematics concept with an authored deck was better served by the
deck's own structure. That was reversed by operator decision: an embed-verified, curated
video is the fastest way to put a learner in front of an idea in *any* subject, and the
deck is still there for consolidation on the next pass. The remaining gate is existence,
not subject — no curated video still means the deck opens, and nothing invents one.

Every unchosen input is recorded in `skipped` with the specific reason it lost. That list
is published to the learner, not hidden.

### 3. Only artifacts that exist may be promised

`ProcedureAssets` is built by `app/procedure_service.py` from things that are actually
there:

- **deck** — only when the concept has authored lesson blocks. The slides are the lesson's
  own sentences, capped at six. Reflections are excluded: they are prompts for the
  learner, not content to present.
- **video** — only a concept-specific entry from the curated allowlist
  (`app/harness/video.py`). Never a generic provider link; a search result is a reference,
  not a lesson.
- **simulation** — a first-party playground game whose own concept line and tags
  *contain* every significant word of the concept (containment, not overlap: scoring by
  overlap once bound "determinants of supply and demand" to "determinants of price
  elasticity of demand"). Falls back to the symbolic maths engine **for mathematics only**:
  `mathkit.template_for` will happily return a generic parabola for a physics concept, and
  presenting that as "acceleration" is the confident fabrication the rest of this project
  exists to prevent. For any other subject the resolver refuses and says why.
- **worked_example** — only an authored `worked_example` block.
- **practice** — counted from the question bank; the block can never promise more items
  than the bank holds.

A missing asset becomes a *reason string* the compiler publishes, never a silently empty
field. That is why `skipped` is not a debug field: a lesson is defined as much by what it
refuses to do as by what it does.

### 4. The budget is a contract

`total_minutes <= budget_minutes`, always. The budget comes from `user.daily_minutes`
unless the caller passes `?minutes=`; it is clamped to `[6, 45]`.

Allocation spends the budget **by priority** rather than building a rich lesson and
chopping its tail:

1. one practice item — a lesson with no commitment is a presentation;
2. the diagnostic, when there is no evidence;
3. the one input block;
4. practice up to the size the evidence asked for;
5. the interactive;
6. discussion, then recap;
7. whatever is left buys extra practice items, up to `min(practice_max_items, bank size)`.

Each step either fits or is refused *with the budget as the reason*. A short session is a
**smaller** lesson, not a truncated one — a 6-minute session is a diagnostic plus two
questions, not a deck with its practice cut off.

The budget ladder, for the default profile:

| budget | blocks |
|---|---|
| 6 | diagnostic, practice ×2 |
| 8 | diagnostic, practice ×3 |
| 10 | diagnostic, deck, practice ×1 |
| 12 | diagnostic, deck, practice ×2 |
| 20 | diagnostic, deck, simulation, practice ×4 |

## Stop conditions

Two, and they are checked before anything else:

- **overload** — `frustrated` (≥3 attempts, accuracy ≤0.34, and much faster than before).
  The lesson ends rather than shrinking: a shorter version of the thing that is failing is
  still the thing that is failing.
- **over budget** — the session already ran past `long_session_minutes`.

Both produce a single `close` block carrying `artifact.reason` (`overload` /
`over_budget`) and record every other activity as skipped.

## The simulation gate

The interactive runs only inside a band, and each edge states its own measurement:

- already used this session → no second run ("novelty without new information");
- `mastery < 0.25` → no, unless a diagnostic just measured the learner;
- `mastery >= 0.85` and the error is not procedural → no, the mechanic is already fluent;
- otherwise yes.

The block also carries `observable`. A playground game reports what the learner committed
to, so its outcome can move mastery. The symbolic figure reports nothing, so
`practice` grows by one item — the only honest way to learn something from a block the
harness cannot see inside.

## Persistence

`procedure_runs` (schema v11, `migrations/010_lesson_procedure.sql`) holds one row per
`(user, concept, procedure_hash)`:

| column | meaning |
|---|---|
| `procedure_hash` | sha256[:32] over concept, course, budget, profile, block kinds + minutes + stable artifact keys, and skipped kinds |
| `blocks` | the compiled plan exactly as compiled, including bound artifacts and refusal reasons |
| `completed` | append-only `{order, kind, outcome, at, seconds, note}` |
| `skipped` | the refusal list, as compiled |
| `status` | `active` / `completed` / `abandoned` |

Three properties matter:

- **The plan is not the evidence.** Advancing a block records that the learner did the
  activity. Mastery still moves only through `POST /attempts` and the playground's outcome
  route. Nothing in `procedure_service.py` writes to `State` or `Attempt`.
- **Starting is idempotent** on `(user, concept, hash)`. A retried request returns the row
  it already had; a *different* plan (new evidence, new budget) is a new row and abandons
  the old one, because resuming a lesson whose shape changed is worse than starting the
  changed one.
- **An active run wins over a recompile.** A lesson that changes underneath the learner
  because a practice item moved the mastery estimate is not a lesson.

The sequence is frozen at **first contact**: `prompt_context` compiles the plan and starts
it when there is no run. That is a write on a read path, and it is deliberate. Without it
the tutor's list is recompiled from fresh evidence every turn, so a prompt that says "you
may not reorder an activity" would reorder them itself — turn 1 "block 2 of 4: the deck",
turn 2 "block 2 of 3: the simulation". Starting on first contact freezes the shape at the
only moment it was a decision; later evidence shapes the *next* lesson. A failed start
degrades to the compiled-but-unpersisted plan rather than failing the turn.

`recent_kinds` reads `completed`, not `blocks`, and only entries whose outcome was `done`.
Reading the proposal made starting a lesson change the next lesson's shape, so the same
learner got a different plan on every retry.

## API

All routes are behind `exam_guard.block` — a plan that names a deck, a simulation and a
video for the concept under examination is help, whatever it is called. The guard runs
before any write, so a blocked request leaves no partial progress.

```
GET  /api/v1/procedure                     -> active lessons for this account
GET  /api/v1/procedure/{concept_id}        -> {plan, evidence, active}; ?minutes=6..240
POST /api/v1/procedure/{concept_id}/start  -> compile, persist, materialise the deck
GET  /api/v1/procedure/runs/{run_id}       -> one run: plan, progress, current block
POST /api/v1/procedure/runs/{run_id}/advance -> {order, outcome, seconds?, note?}
POST /api/v1/procedure/runs/{run_id}/abandon
```

- A concept outside the caller's own course is a **404**, and so is another learner's run —
  a 403 would confirm the run exists.
- `advance` refuses an unknown block, an already-complete block and a finished run with a
  **409**. Each refusal is a real client bug (a double tap, a stale screen); accepting it
  silently would make the progress record lie.
- `outcome='skipped'` is a real outcome: a learner who declines the simulation has still
  completed that block, and recording the refusal honestly beats pretending they played it.
- `concept_id` accepts both namespaces (lesson id `fractions`, graph node id
  `fraction_equivalence`). The run is filed under the **lesson id** — the key the question
  bank and the chat history use — and the graph id stays an accepted alias.
- Every response carries `concept_title` resolved from the **authored lesson**, not from
  the graph node. The row stores an id (a title is curriculum content and a stored copy
  goes stale on a rename), so the title is resolved at serialisation time through one
  helper. Without that, a card reads "Fraction Equivalence" for the lesson the course
  calls "Fractions and equivalent quantities".

The deck is materialised lazily, on `start`, and its id is stored on the block so a resumed
run reopens the same deck. `artifact` then carries `artifact_id`, `raw_url` (the HTML deck),
`pptx_url` (the `.pptx` twin, served by `/api/v1/sims/{id}/download/{name}`) and
`materialized`.

## Prompt injection

`render_procedure_block` turns the plan into the system prompt. It is the block that makes
the model follow the sequence instead of picking one:

```
This session follows a lesson procedure compiled by the harness ...
You may not add, remove, reorder or substitute an activity:
- Concept: Fraction equivalence (integrated_math_1)
- Budget: 20 minutes across 4 block(s), 19 planned.
1. [done] diagnostic (3 min) - Quick check
   Do: ...
   Because: ...
   Bound artifact: 2 question(s) from the question bank ...
2. [NOW] deck (5 min) - Lesson deck
   Do: ...
   Because: ...
   Bound artifact: the bound deck (5 slides: ...). Present it; do not write your own slides.
3. [next] simulation (5 min) - ...
```

It is delivered on **both** paths:

- `POST /chat` → `main.grounded_tutor_reply` → `tutor.respond(..., procedure=..., procedure_completed=...)`
- `POST /agent/chat` → `main.agent_messages` → `system += tutor._procedure_section(...)`

The agent path matters most: that is where the simulation, whiteboard and media tools
actually run, so it is where an unconstrained model would otherwise assemble its own
sequence. The block is complementary to `tutor._plan_section` (the per-turn move), not a
replacement — the move says "teach", the procedure says "teach as block 2 of 5, through
the bound deck, for five minutes".

Both are server-authored text only. The concept title and artifact labels are bounded; the
learner's own words never enter the block.

## How a learner opens an artifact

A block that names an artifact must be openable, or the procedure has promised something it
cannot deliver. The native app decides *whether* to offer a button from the artifact's own
contents — never from the block's kind — so a deck whose sections failed to compose, or a
video whose URL is not on the provider allowlist, gets no button rather than a button that
opens nothing.

| artifact | surface | opened as |
|---|---|---|
| `slides` | `LessonBlockSheet` → deck pager | the block's own `sections`, one slide at a time, with the authored body as a collapsible source text |
| `video` | same sheet → player | the provider's own embed via `EmbeddedLessonWebView`; the watch page is offered when `embed_url` is empty |
| `text` (worked example) | same sheet → reader | the authored body, selectable |
| `simulation` (`mode: playground`) | `openPlayground(slug:)` | the hosted gallery, which owns the outcome POST that makes a run observable |
| `simulation` (`mode: exploratory`) | same sheet → `SimulationLab` | the backend engine's own figure for the bound concept, re-asked on every slider move |
| `questions`, `dialogue`, `summary`, `prose` | no button | these happen in the tutor conversation; there is nothing behind them to open |

Two constraints shape this:

- **Nothing is fetched to show a deck.** The materialised HTML and its `.pptx` twin both sit
  behind the bearer token, and a web view or browser pointed at them has no session to send.
  The slides are already in the block, so they are drawn natively — no token, no web view, no
  network.
- **The `.pptx` is fetched, not linked.** `APIClient.artifact(_:)` refuses any path outside
  `/api/v1/`, then `saveLessonDeckPPTX` writes the bytes to a file the learner chooses with
  an `NSSavePanel`. That is the only version of "download the deck" the app can actually
  keep.

An exploratory interactive is the one artifact drawn from the engine rather than from the
block. It reports nothing back, so `observable` stays false and the compiler still prices the
lesson with the extra practice item — presenting it in the app changes nothing about what the
harness knows, which is the property that makes the extra item honest.

`LessonBlockSheet` offers **Done** only while the block is the current one (advancing out of
order is a 409), and closes only if the run actually moved, so a refused advance is not hidden
behind a dismissed sheet. A finished block opens for review instead.

## Configuration

`ProcedureConfig` in `harness/teaching/config.py`, reachable as `TeacherProfile.procedure`:

| field | default | meaning |
|---|---|---|
| `enabled` | `True` | off → no blocks, and the tutor follows the move policy only |
| `min_minutes` / `max_minutes` | 6 / 45 | the clamp on any budget |
| `skip_input_accuracy` / `skip_input_mastery` | 0.80 / 0.80 | the bar above which no input is scheduled |
| `simulation_min_mastery` | 0.25 | below this there is nothing to predict with |
| `simulation_skip_mastery` | 0.85 | above this the mechanic is fluent |
| `practice_min_items` / `practice_max_items` | 2 / 4 | the practice floor and ceiling |
| `practice_minutes_per_item` | 1.5 | how practice is priced |
| `diagnostic_items` | 2 | size of the opening check |
| `minutes` | per-kind table | the default price of each activity |

The profile round-trips through `to_dict`/`from_dict`, so a stored teacher profile keeps its
procedure settings. `_procedure_sanity` refuses a profile whose minutes table has a
non-positive value, whose `max_minutes < min_minutes`, or whose practice ceiling is below
its floor.

## Adding an asset

1. **A video** — add a row to the curated allowlist (`app/harness/video.py`, or the
   `HARNESS_VIDEO_ALLOWLIST` file) keyed by `course_id` + `concept_id`. It must be
   concept-specific and licence-cleared for embed; nothing generic.
2. **A simulation** — either a playground game in `catalogue.py` whose `concept` + `tags`
   contain every significant word of the concept title, or nothing. Do not widen the
   matcher to overlap scoring; the false positive teaches the wrong idea.
3. **A deck** — nothing to add: a deck is built from the lesson's own blocks. If a concept
   has no authored blocks, it has no deck, and the procedure says so.
4. **A worked example** — an authored `worked_example` block in the lesson.

Then re-run `pytest tests/test_lesson_procedure.py`: the invariant tests
(`one input per lesson`, `budget is a contract`, `every refusal carries a reason`) will
catch a resolver change that breaks the contract.

## Tests

`backend/tests/test_lesson_procedure.py` — 83 tests, in two halves:

- **The compiler** (no database): the four rules, the stop conditions, the simulation band,
  determinism, the hash's stability, and the rendered prompt.
- **The wiring** (a real app): the block reaching both system prompts, progress moving the
  next turn, the sequence staying frozen once the lesson begins, idempotent start, the
  advance refusals, ownership 404s, the exam guard leaving no partial progress, deck
  materialisation and the `.pptx` twin, the authored title on every response, the preview
  persisting nothing, and — the one that keeps the feature honest —
  `test_advancing_writes_no_evidence`.

The third group — `the deck block carries the slides a client can present`, `the video block
carries a URL a player can actually use`, `the simulation block carries what the app needs to
open it`, `the started run still carries what the preview promised` — guards the client
contract. They exist because the app's "Present" / "Watch" / "Explore" / "Read" button is
decided by the artifact's contents: if a serialiser ever stopped sending `sections`, the deck
would still materialise and still be named, and nothing would open it.

Run them with a writable base directory, because the sandbox denies pytest's default tmp
parent:

```sh
python -m pytest tests/test_lesson_procedure.py --basetemp=./.pytest-tmp
```

## Deck control

The deck is rendered natively from the run's blocks, so the server cannot see which slide
is on screen. A shared cursor closes that gap without a new table:

- **State**: `user_preferences.ui['deck_cursor'] = {concept_id, slide, at}`, keyed by the
  authored-lesson id. It is UI state, not progress — mastery and `completed` are untouched —
  and it survives a restart, so a deck reopens where the learner left it.
- **Tool**: `deck_control(concept_id?, action, slide?)` with `next | prev | first | last |
  goto`. **Ungated**, deliberately: it moves the learner's own view, the same way
  `board_apply` writes their own board. Gating it recreates the original bug — a tutor that
  says "next slide" and is refused. `concept_id` may be omitted when exactly one lesson is
  open; two open lessons are refused rather than guessed, because moving the wrong deck is
  worse than asking.
- **Routes**: `GET|PUT /api/v1/procedure/{concept_id}/deck-cursor`. The PUT is how the
  learner's own Back/Next reaches the tutor, so "next" starts from the slide actually
  showing rather than from the server's last guess.
- **Client**: `DeckCursorStore` polls the GET every 1.5s while a deck sheet is open and
  PUTs on manual navigation. Polling, not push, because the SSE turn stream only exists
  while a reply is streaming — the wrong lifetime for a deck the learner keeps open.
- **Prompt**: when the current block is a deck, the rendered procedure tells the tutor it
  can move the sheet and to name the slide it moved to. The capability existed before and
  was never advertised at the moment it was needed.

## Known limits

- The procedure plans; it does not grade. A learner can tap through a lesson without
  learning anything, and the harness will not claim otherwise — mastery is unmoved.
- `practice` names how many items to answer and which concept, not which items: the
  scheduler chooses them at the question route, so the procedure cannot guarantee the
  exact items a learner will see.
- The video allowlist is small by design. Most concepts have no video, and the procedure
  says so rather than substituting a search result.
- The web workbench has no procedure card. The native app is the surface that renders the
  run of show; the workbench already shows decks and simulations through its own artifact
  panes, and a second card would be a second place for the sequence to be stated.
- The native suite is typechecked here, not run. `swift build` needs `--disable-sandbox`
  in this environment (SwiftPM's manifest sandbox fails with `sandbox_apply`); with it the
  release binary builds, but the XCTest suite is still verified by review plus the backend
  contract tests above.
- One lesson per concept at a time. Starting a materially different plan abandons the
  running one; there is no merge.
