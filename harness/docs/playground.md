# The Simulator Playground

A template system for interactive learning games, and the content-generation pipeline
that fills it.

The short version: **an archetype is a reusable interaction; a game is an archetype plus
a content spec.** Twenty-four archetypes are registered; the bundled packs carry
**forty-five games** across biology, computer science, earth science, economics,
mathematics, physics and science. Twenty-three archetypes are used by a bundled game —
`curve_shift` is the reference implementation and is used by none. A new game in an
existing shape costs a JSON object. A new *kind* of game costs one archetype module.

Those counts are **derived, not maintained**: `catalogue.summary()` recomputes them from
the packs on every call, so the prose here cannot drift from the content. The command to
print them is in [Verification](#verification).

---

## Why this exists

The harness already offers third-party simulations — PhET embeds and Gizmos deep links —
through `app/simulation_map.py`. Those are permanently marked `observable: false`, and
correctly so: PhET's free tier exposes no telemetry, and Gizmos is a per-seat product we
may not instrument. The consequence was that a learner could spend an hour experimenting
and the harness would learn nothing. It could not tell whether they had discovered
anything, because it could not see them.

A **first-party** game has no such limitation. It runs in the workbench's own web view,
so it reports what the learner committed to. That is the whole point of the playground,
and it is why `evidence.py` can move mastery from a game while `simulation_map.py`
cannot.

---

## What the reference material taught us

Four sources were studied before any archetype was written. Each contributed a distinct
interaction archetype rather than a game to copy.

**ReviewEcon's 78 activities** (`reviewecon.com/games-activities`) is the richest
taxonomy of graph-and-reasoning interactions found. Its mechanics reduce to a small set:
read a shock and shift a curve; sort determinants into columns where a wrong drop bounces
back; compute a coefficient and classify it; work out opportunity costs from intercepts.
Those became `curve_shift`, `sort_columns`, `calc_choice`, `elasticity_probe` and
`ppf_frontier`.

**The economics practice app** (the `*.app.workbuddy.host` instance) showed how those
mechanics look as five self-contained pages — *Production Possibilities*, *Comparative
Advantage*, *Determinants of Supply and Demand*, *Shifting Markets*, *Elasticity
Coefficients* — each with an explicit interaction label in its own UI: "Click arrows &
drag", "Multiple choice & calculations", "Drag & drop", "Graph animates as you go",
"Point & mid-point". The labels are the useful part: they name the interaction, and each
name is an archetype. Two details were reproduced deliberately, because they are what
make those activities teach rather than entertain: **a wrong drop bounces straight back**
to the tray, and **the graph animates as you go** rather than only on submission.

**MathPlayground** (`mathplayground.com`) confirmed the mathematics set from the other
direction. Its catalogue is overwhelmingly four things: placing a value on a number line
(*Bingo Fractions*), building an area or perimeter (*Perimeter Snatch*, *Tangram*),
ordering operations (*PEMDAS Exhibit*), and extending a pattern (*Number Sequence*,
*Follow the Code*). Those are `number_line`, `area_model`, `order_sequence` and
`pattern_sequence`. The linear-functions work the brief pointed at (Amplify's Desmos-style
activities) is the plot-points-and-guess-the-rule loop, which became `plot_points` and
`function_machine`.

**PhET and Gizmos** supplied the science set: particle sandboxes, circuit builders,
equation balancers, titration curves, wave superposition, projectiles, Punnett squares and
orbital mechanics. These are the simulators a student actually meets in a physics or
chemistry course, and building them first-party is what makes them observable.

Two archetypes were added that no reference contained, because a template system with
gaps invites ad-hoc pages: `step_algorithm` (walk a sorting algorithm's state, with
genuinely correct comparison counts) and `probability_lab` (run trials and watch the
empirical distribution converge).

---

## Architecture

```
app/harness/playground/
  runtime.py         the page shell: CSS tokens + the JavaScript helper surface
  archetypes.py      the contract — Archetype, Field, spec validation, the registry
  archetypes_core.py the reference implementation (curve_shift)
  archetypes_*.py    the archetypes, one module per subject family
  catalogue.py       which games exist; withholds an invalid one with its reason
  pipeline.py        spec -> validated page -> stored artifact; the model path
  evidence.py        what a completed game means, and when it may move mastery
app/playground_routes.py   the HTTP surface
web/playground.html        the gallery a learner opens
media_packs/playground_games*.json   the content
```

Five layers, each owning one thing:

| layer | owns | never does |
|---|---|---|
| **runtime** | the shell, the helpers, the bridge | know any subject |
| **archetype** | the mechanic, the rendering, the check, the telemetry | contain content |
| **spec** | content only | contain code |
| **pipeline** | validation, rendering, storage, the model path | contain either |
| **evidence** | what a run means | score anything itself |

That separation is what makes machine-authored content safe. A model filling a spec
cannot introduce behaviour, because **nothing in a spec is ever evaluated** — it is
embedded as JSON and read as data.

---

## The two messages

Every game talks to the harness through exactly two `postMessage` calls, defined in
`runtime.py`. Keeping them distinct is the central design decision.

**`luminfest:readout`** — continuous state, for the workbench's live display. Fired as the
learner drags. *Never stored.*

**`luminfest:outcome`** — one completed, scored task. Fired once, when the learner commits.
*This is the only thing recorded as evidence.*

Collapsing them would let time spent dragging a slider masquerade as mastery. A readout is
the simulation talking to the screen; an outcome is the learner having committed to
something checkable.

### When a game may commit: `commits_on`

An outcome is only honest if it fires at the moment the learner has actually committed to
an answer. For most archetypes that moment is a **Check button**, and the contract forbids
`luminfest:outcome` before it. But a few interactions have no button: `sort_columns` scores the
finished board, and a wrong drop bounces straight back to the tray, so *reaching the
completed state is itself the answer*. Such a game commits on completion, not on a press.

`Archetype.commits_on` declares which it is, from a closed vocabulary of exactly two
values:

| value | meaning |
|---|---|
| `'check'` | the learner presses Check; nothing may commit before that (the default) |
| `'completion'` | the interaction has a terminal state that *is* the answer; reaching it commits |

It is **declared rather than inferred** because it is the one field that decides whether
exploration can masquerade as mastery, and no verifier can guess it from the markup.
Guessing wrong either waves through a game that scores a stray drag, or condemns a game
behaving exactly as designed. `_validate_declaration` in `archetypes.py` enforces the
declaration at registration: an unknown value is refused by name, and `'completion'` on an
**unscored** archetype is refused outright — a sandbox has no answer to complete.

`sort_columns` is the single archetype declaring `'completion'`; every other archetype
declares `'check'`. The value is published through `Archetype.describe()` (so
`GET /api/v1/playground/archetypes` carries it) and is copied into each entry of
`pages.json` by `playground_render_pages.py`, which is how the behavioural verifier knows
when an outcome is allowed to appear.

---

## Authoring a game: fill a schema

This is the common case and it needs no code.

1. **Pick an archetype.** `GET /api/v1/playground/archetypes` returns every archetype with
   its full schema — field names, types, bounds, and closed vocabularies.
2. **Write the spec.** It must satisfy that schema exactly. Extra fields are refused by
   name; a value outside a declared vocabulary is refused with the allowed set.
3. **Add it to a pack** as an entry in `media_packs/playground_games*.json`:

```json
{
  "slug": "econ-shifting-markets",
  "archetype": "curve_shift",
  "title": "Shifting Markets — Supply & Demand",
  "course_id": "ap_microeconomics",
  "concept": "Supply and demand equilibrium",
  "subjects": ["economics"],
  "difficulty": "core",
  "minutes": 6,
  "prompt": "Read the shock, then shift the right curve.",
  "learning_objective": "Predict the direction of price and quantity after a curve shifts.",
  "reference": "Shifting Markets, reviewecon.com",
  "spec": { "...the archetype's own schema..." }
}
```

4. **Play it.** `GET /api/v1/playground/games/{slug}/html` renders it on demand;
   `POST .../instantiate` stores it as a versioned artifact for the desktop workbench.

A malformed entry is **withheld with its reason** and listed at
`GET /api/v1/playground/summary`, never silently dropped. A content bug should be visible
to the operator, not only to the learner who hit it.

### Authoring without editing the repo

```http
POST /api/v1/playground/compose
{ "archetype": "curve_shift", "spec": { ... }, "title": "My market game" }
```

Validated, rendered and stored in one call. Returns the artifact id and its `/sims` URL.

---

## Producing more games: the model path

```http
POST /api/v1/playground/draft
{ "archetype": "wave_lab", "topic": "sound interference in noise-cancelling headphones",
  "course_id": "physics", "difficulty": "core" }
```

The model is given the archetype's schema and asked for **one JSON object** matching it.
It is never asked to write code. The result is validated; if it fails, the validator's own
messages are fed back and the model gets **one** more attempt. Two attempts is deliberate:
one is a coin flip, and more than two burns tokens on a model that has shown it cannot
follow the schema.

Nothing is stored unless a spec validated. With no model configured the endpoint returns
`503` with `{"ok": false, "stage": "provider", ...}` and the bundled games remain
playable — the model path is an accelerator, never a dependency.

---

## Adding an archetype: the template system

Only when a genuinely new *interaction* is needed.

1. Write `app/harness/playground/archetypes_<family>.py` following
   `archetypes_core.py`. An archetype declares its metadata, its `spec_fields`, a
   `body(spec)` returning stage markup, and an `engine(spec)` returning JavaScript that
   defines `build(root, spec)`.
2. Add the module to the static imports and the `register_all(...)` call in
   `playground/__init__.py`. **This line is not optional and not inferable** — PyInstaller
   only bundles modules it can see imported, and this project has already shipped a build
   whose feature routers were absent from the frozen archive for exactly this reason.
3. Add games to a pack.
4. Run the verification (below).

The full authoring contract — every runtime helper, every hard constraint, the quality
bar — is in [`playground-archetype-brief.md`](playground-archetype-brief.md).

### Hard constraints

A rendered page is refused by `app.harness.sims_store.validate_html` unless it is:

- **self-contained** — no external script, stylesheet, image, font, `fetch`, XHR,
  WebSocket or meta refresh. Nothing may touch the network.
- **free of dynamic code** — no `eval(`, no `Function(`, no `setTimeout('string')`.
- **well-formed**, under 400,000 bytes, and carrying a `data-series` attribute.
- **deterministic** — randomness only through `rand(seed)`/`shuffle(list, seed)` seeded
  from the spec, so one spec always renders the same game.

### The quality bar

1. The learner must **commit** to something checkable. Dragging is exploration.
2. `BRIDGE.readout` on live change; `BRIDGE.outcome` once per committed task.
3. Feedback must **teach** — on a wrong answer, say what to reconsider; on a right one,
   say why it is right.
4. **Give up gracefully** after three tries, and report `gave_up: true`.
5. The subject content must be **correct**. A game whose right answer is wrong teaches the
   wrong thing.

---

## The evidence model

`POST /api/v1/playground/games/{slug}/outcome` records a run.

Two things happen, and keeping them separate is the point:

1. A **`PlaygroundRun`** row — game, task, correctness, tries, elapsed time, the game's
   own telemetry, and mastery before and after. Deliberately *not* an `Attempt`: an
   attempt answers a vetted item from the question bank under a receipt, and a game
   answer should not borrow that authority.
2. An update to the learner's **mastery state** for the concept, through the *same*
   `learning.update` and `propagate_implicit_credit` calls the question route uses. A run
   therefore cannot inflate mastery through a private path.

**Attribution is resolved, not assumed.** A learner enrolled in algebra may legitimately
play a physics game. The run is recorded either way, but mastery only moves when the
game's concept resolves inside the learner's *own* course — by explicit `concept_id`,
then exact title match, then word overlap above a high threshold. When nothing clears the
bar, the response says so and the run is recorded uncredited. Crediting the wrong concept
would be an invention dressed as measurement.

**Scoring is the game's.** The game holds its own answer key and reports whether the
learner was right. This is a real trust boundary and it is stated rather than hidden: a
learner who tampers with their own browser can overstate their own mastery, which harms
only themselves, and re-implementing twenty-four archetypes' checks server-side would
defeat the architecture that makes twenty-four archetypes possible. Each run records the
artifact id and content revision it was played from, so a result is traceable to exact
bytes. Nothing here feeds a credential.

**The first observation has no baseline.** On a learner's *first* run for a concept,
`mastery_before` is `None`, and therefore `mastery_delta` is `None` — not `0.0`. The
estimator's baseline for a concept it has never measured is `PRIOR = 0.15`
(`app/learning.py:67`), not zero, so a delta measured from an implicit `0.0` would
overstate the gain by exactly that prior. `None` means "no prior measured estimate
existed"; it is a fact about the record, not a missing value to be filled in. On every
later run the baseline is real and the delta is a number.

**Nothing plays during an exam.** Every play and authoring surface in
`playground_routes.py` — rendering a game, instantiating one, recording an outcome,
composing a spec, drafting one — calls `exam_guard.block`, which raises `403` while the
learner has an open, unexpired exam. A game that teaches the concept being examined is
help, whatever it is called. The guard runs *before* the run is written, so a refused
`POST /outcome` writes **no `PlaygroundRun` row** at all: an exam cannot be polluted by a
record that was refused.

---

## The archetypes

| id | interaction | subjects |
|---|---|---|
| `curve_shift` | drag a curve; the intersection animates live | economics, science, mathematics |
| `ppf_frontier` | move production along a frontier, or grow it | economics |
| `sort_columns` | sort tiles into columns; a wrong drop bounces back | economics |
| `calc_choice` | compute a value, then choose a course of action | economics |
| `elasticity_probe` | point and mid-point coefficients, then classify | economics |
| `plot_points` | place points that satisfy a rule; fit the line | mathematics |
| `function_machine` | feed inputs, build the table, guess the rule | mathematics |
| `number_line` | place a value at the right position | mathematics |
| `balance_scale` | keep a scale level while solving for x | mathematics |
| `area_model` | set side lengths; watch the partial products | mathematics |
| `probability_lab` | run trials; watch the empirical distribution converge | mathematics |
| `pattern_sequence` | extend a pattern and state its rule | mathematics |
| `step_algorithm` | step a sort forward and back; predict the counts | computer science |
| `particle_sandbox` | gas laws — temperature, volume, pressure | physics |
| `circuit_builder` | Ohm's law — set V and R, read the current | physics |
| `balance_equation` | adjust coefficients until the atoms balance | chemistry |
| `titration_curve` | add titrant; find the equivalence point | chemistry |
| `wave_lab` | superposition — amplitude, wavelength, phase | physics |
| `projectile` | set angle and speed; read the range | physics |
| `punnett` | choose parent genotypes; read the ratios | biology |
| `orbit_gravity` | set speed and mass; closed orbit or escape | physics, earth science |
| `order_sequence` | drag steps into the correct order | any |
| `matching_pairs` | match terms to definitions | any |
| `label_diagram` | drag labels onto diagram hotspots | any |

`curve_shift` is registered but used by no bundled game — it is the reference
implementation in `archetypes_core.py`, kept as the worked example the authoring brief
points at. The other twenty-three archetypes each carry at least one bundled game.

---

## The visual system

The full specification is [playground-design.md](playground-design.md). This section is
the summary and the reason it exists.

The first draft of the playground inherited its palette from the hand-authored seed
simulation: off-white paper, hairline grey borders, one dusty blue accent. Copied across
forty-five games it produced a worksheet — every game looked like a print-out stapled
into the app, controls looked like default browser widgets, colour carried no meaning,
half of every canvas was empty, and axis labels sat on top of each other.

The runtime now carries the **product's own design language** — the Morandi palette the
native app already uses, anchored on forest green — and the rules that make it a system:

| Concern | Rule |
|---|---|
| Colour | Two ladders (surface, ink) plus two groups. Five *series* hues (`a`–`e`) identify data; three *semantic* tones (`ok`/`no`/`hint`) judge it. A series hue may never mean "wrong". |
| Type | One family, a ~1.2 scale, and tabular figures on every number that changes while dragging. |
| Elevation | Three warm-tinted shadow levels. The stage is a raised white card on a warm page. |
| Motion | One easing, three durations; 120 ms for interaction, 340 ms for layout. |
| Components | Buttons, chips, verdict banners, tiles, drop zones and the range slider are defined once and inherited. An archetype that re-implements any of them is a bug. |

Four of the layout rules are **measured rather than argued** by
`scripts/playground_layout_audit.mjs`, which drives a real headless Chromium:

- **fill** — painted content must cover ≥55% of the declared viewBox;
- **clipped** — nothing may be drawn outside the viewBox, where it is invisible;
- **duplicate instruction** — `#instruction` and `#prompt` must not say the same sentence;
- **collisions** — no two `<text>` nodes may overlap, and no text may cross the canvas edge.

Fill is reported twice, and the difference matters. The **gated** number is the union
bounding box of the painted marks over the declared viewBox. The per-page line prints
**`sees`** instead: the same box measured against the scene element's own rect. They
disagree wherever the aspect ratio is letterboxed — the canonical viewBox is 860×460
(1.87) and the stage card is nearer 1.41, so roughly 90 px of card height is unreachable
on every page. `sees` is the honest number, because a page can cover 80% of its viewBox
and still look sparse.

The audit had to be fixed twice before it told the truth, and both failures are worth
recording because they are the failure mode of every visual metric: it first counted a
full-canvas *transparent* pointer rect as content, so every page scored 100% fill; then it
counted drag markers parked off-canvas at rest, which made the emptiest page in the
catalogue — the number line — score 119%. It now measures only painted leaves inside the
viewBox, and reports off-canvas marks separately. On the corrected metric the number line
was 7% full, which matched what a person saw; after the redesign it is 80%.

One trap in the *renderer* is worth more than the audit. `scripts/playground_render_pages.py`
used to render with `render(archetype, spec)` — the bare spec — while the app renders with
`pipeline.page_args()`. The two drifted, so every artifact carried `MATHEMATICS` on a
biology game (three archetypes are shared across subjects) and several pages printed the
same sentence in the header and the task line. The audit was measuring a page nobody
plays. Both callers now go through `page_args`, and the audit fails on a duplicate
instruction, which is how the drift was caught.

---

## Verification

Six scripts, six different questions, each a separate gate because each can see a defect
the others cannot. Run them from `harness/`.

> Write the scratch files **inside the workspace**, not to `/tmp`. The temp directory is not
> preserved between shell invocations here, so a later step silently reads a file of unknown
> provenance — which is how one run reported a clean result for a `pages.json` that no
> current script had produced.

### 1. Render every game through the real pipeline

```bash
cd harness
mkdir -p .verify
PYTHONPATH=backend ./ui-tests/.venv/bin/python scripts/playground_render_pages.py .verify/pages.json
```

Imports the real catalogue, renders every bundled game with the real `render()`, and writes
`[{slug, archetype, scored, commits_on, html}]` to `pages.json`. It also prints the withheld
count. This is the fixture the next four scripts consume. It is also where the counts in
the introduction come from:

```bash
cd harness/backend
PYTHONPATH=. ../ui-tests/.venv/bin/python -c "
from app.harness.playground import all_archetypes, catalogue
print('archetypes', len(all_archetypes()))
print('games', len(catalogue.all_games()), 'withheld', len(catalogue.withheld()))
print(catalogue.summary())"
```

### 2. The crash checker — "does it run?"

```bash
node scripts/playground_dom_smoke.js <page.html> [<page.html> ...]
```

Runs each page's script in a stub DOM and exercises every handler it registered — a drag on
every element that took a pointer handler, a click on every button. It proves a page does
not throw on load or in a driven handler. It cannot prove a game is *right*, and it cannot
reach a geometry-bound commit (a drag to the wrong pixel is not a crash). `tests/test_playground.py`
drives it over every bundled page.

### 3. The behavioural verifier — "does it commit honestly?"

```bash
node scripts/playground_verify.mjs .verify/pages.json
```

Archetype-agnostic and geometry-blind. Asserts the contract: no outcome on load, none from
exploration, exactly one per commit, a give-up carries `correct: false`, and an unscored
sandbox posts nothing. It reads `commits_on` from `pages.json` to know when an outcome is
allowed to appear. Where an archetype cannot be driven generically it reports `undriven` —
an untested contract stated as untested, never as a pass and never as a failure.

A load failure must **fail** the run. It once did not: both early returns set
`res.load_error` and returned with `ok: true`, so a bundle of entirely broken pages exited
0 — and a real run printed `failed: 0` across all 45 games while every single page carried
`load_error: 'no <script> block'`. A verifier that green-lights a catalogue of broken pages
is worse than no verifier, because it manufactures confidence. The negative control for this
is two deliberately broken pages: they must produce `failed: 2` and exit 1.

### 4. The correctness oracle — "does it score correctly?"

```bash
PYTHONPATH=backend ./ui-tests/.venv/bin/python scripts/playground_correctness_cases.py .verify/cases.json
node scripts/playground_correctness.mjs .verify/cases.json
```

The first script derives each case's **right answer from the spec** (and, where the spec
alone is not enough, from an independent re-derivation of the subject matter) and writes the
DOM actions that commit it; the second drives the rendered page and checks what the game
actually scored. Neither reads the engine's private state, so they cannot agree with the
engine by construction. Geometry-bound archetypes are covered too: the drop pixel is
computed from the spec's declared axis bounds (or declared coordinates) through the engine's
own coordinate mapping, never guessed. The one archetype left out is `curve_shift`, which no
bundled game uses — and it is listed in the script's `SKIPPED` with that reason rather than
silently omitted.

Two rules keep that honest, and both were learned the hard way:

**The stub reports the page's own viewBox.** The driver's `getBoundingClientRect()` once
returned a hard-coded 860×460. That was invisible while `point()` also assumed the box and
the viewBox had the same aspect — the mapping was the identity and every drag landed. The
moment `point()` became letterbox-aware, any archetype declaring a taller canvas
(`number_line` and `plot_points` are 860×600) had every dispatched drag silently rescaled
and re-centred, and the oracle reported four scoring failures on two games that were
perfectly correct on screen. The stub now returns whatever box `#scene` declares, so the
mapping is the identity at any canvas height, and a layout change cannot masquerade as a
scoring bug.

**A case builder that touches geometry mirrors the engine, including its clamps.** When the
`label_diagram` tray moved from a row to a column and the `order_sequence` rows were fitted
to the canvas height, the drop targets moved with them; `_label_layout` and `_order_rows`
were updated in the same commit. A case builder that guessed would have reported a layout
change as a scoring bug — which is exactly what the geometry rule exists to prevent.

#### Why "does it crash" and "does it commit" are both weaker than "does it score correctly"

On the day it was written, the oracle found a real bug that every other gate had passed.
`elasticity_probe` computed `correct = numOK && classOK` and dropped the sign stage
entirely, so a learner who read the sign wrong three times was scored `correct: true` — a
mastery-corruption bug: the record said the learner had mastered something they had got
wrong, and the give-up was marked correct too. The crash checker was green (the page ran),
the behavioural verifier was green (it committed exactly once, on Check), the schema
validation was green (the spec was well-formed), and every existing test was green. None of
them knew the right answer, so none could see that the game scored the wrong one. The fix
folds the sign into the score and records the learner's own pick (`detail.sign`) separately
from the answer (`detail.sign_answer`).

### 5. The real-browser check — "does it behave the same outside the stub?"

```bash
PYTHONPATH=backend ./ui-tests/.venv/bin/python scripts/playground_dump_pages.py .verify/pages.json .verify/games
node scripts/playground_browser_check.mjs .verify/games .verify/browser.json .verify/pages.json
```

The third argument is optional but it is what turns one of the results from a number into a
verdict: it supplies each page's `commits_on`, so the driver can tell a commit-on-completion
page (which is *supposed* to post an outcome the moment the board is finished) from a
commit-on-check one (which must post nothing until Check is pressed). Without it the
exploration count is reported raw and unjudged.

Scripts 2 and 3 drive a **hand-written DOM stub**. That stub fakes
`getBoundingClientRect`, event dispatch, layout and animation frames. If it is wrong in a
way that matters, every `failed: 0` verdict it produces is wrong *together*, and nothing
else in this list would notice. This script is the only one that runs the pages in a real
engine — headless Chromium, each page inside an iframe so the real
`window.parent.postMessage` bridge is the one under test — and reports where the real
browser **disagrees** with the stub. A pass count is not the deliverable; the disagreement
is.

What it establishes, and what it does not:

- **Corroborated.** All 45 pages load, render non-empty content, throw no uncaught
  exception, make no external request, and post **no outcome on load**. These are the
  contracts that matter most, and the stub was right about every one of them.
- **Corroborated: exploring posts nothing.** The outcome count is sampled after the
  non-commit taps and one drag pass and before any commit press, then judged per page
  against its own `commits_on`. `prematureOutcome` is `0` across the catalogue — and the
  check is not vacuous: a synthetic page that posts an outcome from a non-commit button is
  reported as `prematureOutcome: 1`.

  Where the sample is taken matters. Taken just before the final Check it reads `0` for
  every page and means nothing, because the tap sweep legitimately presses Check to advance
  a staged game within its first few pairs — so the count is always captured after a commit
  press and can never be non-zero. That version of the check was in this script for one run
  and was measuring its own timing.
- **Corroborated by direct measurement.** A real pointer drag into a real drop zone is
  accepted (`correct_drops` increments); a real select-then-place click pair is accepted;
  the `viewBox → page` mapper round-trips to **0.00 px**; and a real `luminfest:outcome`
  reaches the parent listener through the real bridge.
- **Not established.** The commit count is not a substitute for script 3's. This driver
  aims at a grid derived from the scene's own `viewBox`, whereas script 3 drives the exact
  handlers the page registered. Where the two disagree, script 3 is the stronger evidence
  and this one is reporting its own reach. A page it cannot complete is reported as
  undriven, never as a failure.

Playwright is not bundled with the app and is not needed to run the games — it is a
development dependency of this script only. It lives in the isolated node workspace:

```bash
cd /Users/tengyi/.workbuddy-ai/binaries/node/workspace
/Users/tengyi/.workbuddy-ai/binaries/node/versions/22.22.2-6/bin/npm install playwright
```

`harness/node_modules` is a symlink to that workspace, so the scripts under `scripts/`
resolve `playwright` when run from `harness/`. It is gitignored.

### 6. The layout audit — "is the canvas actually used?"

```bash
node scripts/playground_layout_audit.mjs .verify/html .verify/layout.json
node scripts/playground_shots.mjs .verify/html .verify/shots      # then look at the PNGs
```

Measures the four mechanical rules from
[playground-design.md](playground-design.md#6-the-layout-contract) — fill, clipped marks,
duplicate instruction, text collisions — in a real browser with the real CSS, because every
one of those quantities depends on font metrics and layout. It exits non-zero when any page
fails, so it can gate a build.

It is a **smell detector, not a verdict**. It cannot see whether a diagram reads, whether a
composition is balanced, or whether a control looks like a control. That is what
`playground_shots.mjs` is for: the audit found the number-line page at 7% fill, but only
the screenshot showed that its drag handle was parked off-canvas where no learner could
see it.

#### The test suite

```bash
cd harness/backend
TMPDIR="$PWD/.pytest-tmp" ../ui-tests/.venv/bin/python -m pytest \
  tests/test_playground.py tests/test_playground_pipeline.py \
  tests/test_playground_gallery.py tests/test_playground_correctness.py \
  tests/test_playground_attribution.py tests/test_resource_paths.py -q
```

The suite asserts the rules, not the current output:

- every bundled game renders a page the artifact store **accepts**;
- no page can reach the network or evaluate dynamic code;
- no page calls a runtime helper that does not exist (a real bug found in review: an
  earlier revision called `UI.outcome`, which was never defined — it rendered perfectly
  and threw the moment a learner pressed Check);
- every rendered page is **byte-deterministic** for one spec;
- every game **executes** under the crash checker;
- every **scored** game actually posts an outcome when its controls are exercised;
- the catalogue withholds an invalid game with its reason rather than dropping it;
- a run moves mastery, and records the before/after;
- an unattributed run is recorded and does **not** move mastery;
- a stored page is attributed to the right slug **and** the right spec revision, so an
  edited spec can never silently serve its stale page;
- the frozen bundle's resource paths resolve in both layouts, including the bytecode-only
  model package the packager ships.

`tests/test_playground_correctness.py` is the pytest gate over the correctness oracle in
section 4. `tests/test_playground_attribution.py` guards the `(slug, spec_hash)` pair in
`pipeline._find_artifact` — drop the hash and an edited game serves its stale page, drop the
slug and two games collide onto one artifact. It is proven non-vacuous: reintroducing a
slug-only lookup fails three of its tests.

---

## Required external services

None. Every game is self-contained, offline and free of API keys.

Optional, and only for *authoring new content* rather than playing it: a language-model
endpoint (`POST /api/v1/playground/draft`). Without one, `compose` still works — you
write the spec yourself.
