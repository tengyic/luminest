# The Playground Design System

Every game in the simulator playground is an *archetype* plus a content spec. The
archetype owns the interaction; this document owns how it looks and behaves. A new
archetype that follows this document is visually indistinguishable from the other
twenty-three, which is the whole reason the playground is a system rather than a
folder of pages.

The rules here are not stylistic preferences. Each one exists because the first
draft of the playground broke it, and the break was visible to a learner.

---

## 1. Why the first draft failed

The first draft inherited its palette from `web/sims/supply-demand.html`, the
hand-authored seed simulation. That file was written as a *document* — off-white
paper, hairline grey borders, one dusty blue accent — and it was fine as a
document. Copied across forty-five games it produced a worksheet:

| Symptom | Cause |
|---|---|
| Games looked like a print-out | One flat surface, no elevation, no card |
| Nothing looked interactive | Controls styled as default browser widgets |
| Colour meant nothing | Five hues used decoratively, never semantically |
| Half of every page was empty | A fixed 860×460 canvas regardless of content |
| Labels sat on top of each other | No reserved gutters for axis titles |
| The same sentence appeared twice | Instruction rendered into both header and stage |
| Text too small to read comfortably | 12.5px body, 10.5px ticks, no type scale |

Meanwhile the native app had settled on a Morandi palette anchored on forest
green. The games sat inside that app looking like something stapled in.

---

## 2. Colour

Colour is **two ladders plus two groups**. The ladders build depth. The groups
carry meaning — and they are kept strictly apart.

### 2.1 The surface ladder

Warm paper, never neutral grey. A cool grey next to the app's warm surfaces reads
as a different product.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F7F5EF` | Page behind the stage |
| `--surface` | `#FFFFFF` | The stage card, controls, tiles |
| `--surface-2` | `#F6F4ED` | Wells, drop zones, slider tracks |
| `--surface-3` | `#EFEDE3` | Progress track, disabled fills |
| `--line` | `#E5E7DB` | Hairlines, gridlines |
| `--line-strong` | `#D3D7C7` | Control borders, drop-zone dashes |

### 2.2 The ink ladder

Three steps, none of them pure black or pure grey. `--ink` is a green-black that
belongs to the same family as the surfaces.

| Token | Value | Contrast on `--surface` | Use |
|---|---|---|---|
| `--ink` | `#24312A` | 13.4:1 | Titles, values, axis lines |
| `--ink-2` | `#5C6A60` | 5.9:1 | Instruction, captions, labels |
| `--ink-3` | `#8D9A90` | 3.4:1 | Tick numbers only — never body text |

`--ink-3` is deliberately *below* AA for body copy. It is reserved for axis ticks,
where the number is redundant with the axis itself. Any sentence a learner must
read uses `--ink-2` or darker.

### 2.3 The series group — five data hues

Series hues **identify data**. They never judge it. Each ships as a deep tone for
strokes and text plus a soft tint for fills, so a series can be drawn as a line, a
bar, a dot or a wash without inventing a second colour.

| Name | Deep | Soft | Typical role |
|---|---|---|---|
| `a` | `#47519C` indigo | `#CCD2F0` | Primary series — the thing being manipulated |
| `b` | `#3E7A55` forest | `#C4E6C9` | Secondary series, and the brand anchor |
| `c` | `#B35C2E` clay | `#FBD0B4` | Highlight marker, equilibrium, residual |
| `d` | `#8F6A1F` ochre | `#F7DFA8` | Third series, thresholds |
| `e` | `#7A3E8C` plum | `#E0C7EA` | Fourth series, annotations |

The names `a`–`e` are **load-bearing**: roughly a hundred call sites pass them to
`colour()` and to `Field(choices=('a','b','c','d','e'))`. Only the values moved.

**Rule:** a series hue may not be used to indicate correctness. A red-looking
curve is not "the wrong curve" — it is the clay series.

### 2.4 The semantic group — three verdict tones

Correctness is carried *only* by these. That separation is what stops decoration
from implying a verdict.

| Token | Value | Soft | Use |
|---|---|---|---|
| `--ok` | `#2C5C3E` | `#E7F2E9` | A correct commit |
| `--no` | `#A8422F` | `#FCEAE4` | An incorrect commit |
| `--hint` | `#47519C` | `#EDEFF9` | Neutral information, reveal, "try again" |

### 2.5 Legacy aliases

Archetypes written against the first draft pass `colour('dim')`, `colour('edge')`,
`colour('good')` and so on. Those names remain, mapped onto the new ladders. New
code should use the tokens above.

---

## 3. Typography

One family — `Inter`, falling back to the system UI stack. No web font is loaded,
because the page must be self-contained and offline.

The scale is a ~1.2 ratio with a deliberate jump between *label* and *body*, so a
heading never looks like a slightly larger sentence.

| Role | Size | Weight | Tracking | Colour |
|---|---|---|---|---|
| Eyebrow | 10 | 700, uppercase | +0.15em | `--ink-3` |
| Page title | 19 | 650 | −0.018em | `--ink` |
| Instruction | 13 | 450 | 0 | `--ink-2` |
| In-scene label | 12 | 650 | 0 | `--ink` |
| In-scene note | 11 | 450 | 0 | `--ink-3` |
| Axis tick | 10.5 | 500 | 0 | `--ink-3` |
| Button | 12.5 | 600 | +0.005em | `--ink` |
| Chip | 11.5 | 550 | 0 | `--ink-2` |

Every number a learner reads while dragging uses `font-variant-numeric:
tabular-nums`, so digits do not jitter as values change. This is the single
cheapest quality signal in the whole system.

---

## 4. Space, radius, elevation, motion

**Space** is a 4px base: 4, 8, 12, 16, 20, 24, 32. Page padding is 20/16. Gaps
inside the frame are 10.

**Radius** — `--r-sm: 8`, `--r-md: 11`, `--r-lg: 16`, `--r-xl: 22`, `--r-pill`.
The stage card uses 16; controls use 11; chips use pill.

**Elevation** — three levels, all warm-tinted (`rgba(36,49,42,…)`) rather than
neutral black, so shadows sit on the paper instead of greying it.

| Token | Use |
|---|---|
| `--e1` | Resting controls, chips, tiles |
| `--e2` | The stage card, hovered controls |
| `--e3` | A tile being dragged |

**Motion** — one easing (`--ease`, a soft ease-out), three durations (120 / 200 /
340 ms). Interactive feedback is always 120 ms so it feels immediate; layout
transitions are 340 ms so they feel considered. `--spring` is reserved for the
commit moment.

---

## 5. Components

### 5.1 Page shell

```
┌──────────────────────────────────────────────────┐
│ ECONOMICS · PRODUCTION POSSIBILITIES   Task 2/4  │  eyebrow · title · progress
│ Production Possibilities — the Cost of Moving    │
│ The frontier shows the most the economy can...   │
├──────────────────────────────────────────────────┤
│                                                  │
│                  the stage card                  │  raised, white, r=16
│                                                  │
├──────────────────────────────────────────────────┤
│ ● Butter  6.00   ● Guns  4.00                    │  readout chips
├──────────────────────────────────────────────────┤
│ ✓ Correct — moving to 6 t costs 4 000 guns.      │  verdict banner
└──────────────────────────────────────────────────┘
```

The **eyebrow** names the subject and the *interaction*, not the game. A learner
who met "drag a point along a number line" in maths should recognise it in
science; seeing the same label is what makes the transfer visible.

### 5.2 Stage

A single raised white card on the warm page. It is the only place content lives,
and the only surface with `--e2` at rest. The scene fills it.

### 5.3 Buttons

| Variant | Look | Use |
|---|---|---|
| Primary | Forest gradient, white text, green glow | The commit action — exactly one per screen |
| Default | White, hairline, `--e1` | Reset, Next, secondary actions |
| Ghost | No border, no shadow | Tertiary, inline |

Hover lifts 1px and deepens the shadow; press returns to rest and scales to 0.985.
Disabled drops to 42% opacity and loses its shadow — it must look *inert*, not
merely faint.

### 5.4 Chips

Pill, white, hairline, `--e1`, with a 6px dot tinted to the series the value
belongs to. The dot is the connection between a number and the mark it describes;
without it a readout is a row of anonymous numbers.

### 5.5 Verdict banner

The single most important moment in the loop, so it gets a real treatment: tinted
surface, matching border, a circular mark (✓ / ✕ / ◆) and the reason. It animates
in over 200 ms from 3px below. It is never a line of grey text.

### 5.6 Tiles and drop zones

A tile is a white card with `--e1` and a 1.3px border. On hover the shadow deepens
to `--e3`. A drop zone is a **dashed well** in `--surface-2` at rest and a solid
forest-bordered, green-tinted target on drag-over. Both states must be visible
before the learner touches anything — an affordance you only discover by
accident is not an affordance.

A labelling diagram places its tray **where the drawing cannot reach**: a row beneath a
wide diagram, a column beside a tall one, chosen from the diagram's own aspect ratio
(threshold 1.5). The animal cell is 1.2:1, so fitted above a full-width row of pills it
used 44% of its canvas and left two empty gutters either side of the drawing; the same
tray in the right-hand gutter takes it to 65%. The star network is 2.6:1, already spans
the card, and is unchanged. The rule generalises: a fixed tray position is a decision
about one diagram that has been imposed on all of them.

### 5.7 Slider

The native range input is the least designed control on the platform. It is
replaced: 5px track in `--surface-3`, 17px white thumb with a 2.5px forest ring,
scale 1.12 on hover.

---

## 6. The layout contract

These are the rules the six archetype modules are audited against. They are
mechanical on purpose: `scripts/playground_layout_audit.mjs` measures four of
them and fails a page that breaks one.

**L1 — Fill the canvas.** The union bounding box of everything drawn inside the
scene must cover at least **55%** of the declared viewBox area, and no mark may
fall outside it. A game whose content occupies a tenth of its canvas has not
been laid out; it has been dropped on a page.

That number is reported twice, and the second one is the one to look at. The **gate** is
the box over the declared viewBox. The per-page line prints **`sees`** — the same box over
the scene element's own rect. They disagree wherever the aspect ratio is letterboxed: the
canonical canvas is 860×460 (1.87) and the stage card is nearer 1.41, so about 90 px of
card height is unreachable on every page. A page can cover 80% of its viewBox and still
look sparse, which is why the human-facing number is the stricter one.

**L2 — One instruction.** `#instruction` carries the general instruction.
`#prompt` (or `#task`) carries *this task*. They must not contain the same
sentence. If an archetype has nothing task-specific to say, it renders no prompt
element at all rather than echoing the header.

**L3 — No text collisions.** No two `<text>` nodes may overlap, and no text may
cross the canvas edge. Axis titles live in reserved gutters outside the plot
rectangle. Annotations are clamped inside the plot.

**L4 — No undesigned empty state.** Before the first action, a chart shows either
the full scaffolding (axes, grid, guides) or an explicit invitation ("Press Run to
start") — never a row of zero-height bars reading `0.000`.

**L5 — Show progress.** Any game with a fixed number of tasks calls
`UI.progress(done, total)`. Free-play sandboxes do not, and the rail stays hidden.

**L6 — Affordances are visible at rest.** Handles ≥ 11px radius with a white ring.
Drop zones dashed at rest. Draggable things carry a grab cursor.

**L7 — Hit targets.** Every interactive mark is ≥ 44px across in screen space at
the default viewport.

**L8 — Contrast.** Body text ≥ 4.5:1. Ticks may use `--ink-3`.

---

## 7. Using the system

An archetype supplies two functions:

- `body(spec) -> str` — markup inside the stage. Use `.stagecol`, `.scene-wrap`,
  `.controls`, `.panel` and `.verdict`; do not invent layout classes.
- `engine(spec) -> str` — JavaScript defining `build(root, spec)`. Use `el`,
  `svg`, `colour`, `scale`, `drag`, `point`, `UI.chip`, `UI.feedback`,
  `UI.score`, `UI.progress`.

Everything else — palette, type, elevation, motion, the shell — is inherited. An
archetype that re-implements any of it is a bug.

### Adding a game

```python
Field('title', 'text', 'Shown as the page heading.'),
Field('instruction', 'text', 'One or two sentences telling the learner what to do.'),
```

Then a spec. The page is assembled by `runtime.render_page`, stored as a normal
harness artifact, and played in the workbench by the same path as a hand-authored
simulation. No CSS, no shell, no bridge code.

### Adding an archetype

Implement `body` and `engine`, declare `spec_fields`, `telemetry`, `commits_on`
and `scored`, and register it in `playground/__init__.py` — statically, because
PyInstaller only bundles modules it can see imported.

Then run the audit:

```bash
python scripts/playground_render_pages.py /tmp/pages.json
python scripts/playground_dump_pages.py /tmp/pages.json /tmp/html
node scripts/playground_layout_audit.mjs /tmp/html
```

A new archetype is done when the audit reports it clean.

---

## 8. Known gaps

Stated rather than hidden, because a design system that claims completeness it does not
have is worse than one that names its edges.

**L4 and L6 are enforced by eye, not by the audit.** The audit measures fill, clipping,
duplicate instructions and text collisions. It cannot see an empty chart or an invisible
handle. `titration_curve` shipped with a blank fourteen-unit grid and a 12 px playhead
sitting on the axis — both faults, neither measurable — and now draws an invitation
sentence plus a ringed 18 px handle with a stem. Every clause in section 6 that has no
metric behind it is a clause that can regress silently.

**The canonical canvas fights the stage.** The page shell gives the scene a box around
1.41:1 and the viewBox is 1.87:1, so `xMidYMid meet` scales by width and leaves vertical
slack that no archetype can reach. Declaring a taller canvas (860×600 on the number line
and plot-points, 565 on the balance scale) is the per-archetype workaround, not a fix; the
systemic fix is for the shell and the canvas to agree on one aspect ratio.

**Keyboard operability.** Every game is played by dragging or tapping. There is no
keyboard path to a drag handle, so a learner who cannot use a pointer cannot play. The
runtime's `drag()` helper is the single choke point where a fix belongs — bind arrow keys
to the same `move` handler for a focusable target — but that needs a `tabindex` and an
announced value per handle, which is per-archetype work that has not been done. (A few
archetypes — `matching_pairs`, `sort_columns` — do expose a keyboard path of their own,
because they were built from cards rather than from a drawing.)

**Dark mode.** The games inherit the light Morandi palette unconditionally. The native app
is light-only today, so this is consistent rather than broken; it would need a
`prefers-color-scheme` token block if the app ever gains a dark appearance.

**Screen-reader narration of the scene.** The stage carries `data-series` and the verdict
banner is a live region, but the drawing itself is not described. A `<title>`/`<desc>` pair
per scene would be the start.

**Reduced motion** *is* handled — every transition collapses under
`prefers-reduced-motion`, matching what `Design.swift` already does natively.
