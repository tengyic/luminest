# The Content Foundry

**Status:** implemented. `app/harness/authoring/`, `app/routes_authoring.py`,
`tests/test_authoring.py`.

## 0. The gap this closes

The harness could already teach. `app/harness/loop.py` decided the next move from
evidence, `app/harness/generate.py` produced artefacts for a concept,
`app/harness/playground/pipeline.py` drafted a game from a topic, and
`app/course_builder.py` built a course from a learner's own document.

What it could not do was **design a course of its own**. Every shipped course was
designed outside the running system — in an editing session — and committed as JSON in
`app/curriculum_packs/`. The consequence is easy to miss because the catalogue is large:
the ability to produce a *new* course lived in whoever wrote the pack, not in the
product. Adding a subject meant editing `app/courses.py` (a hardcoded tuple), adding a
pack file, and hoping the generated layer materialised it correctly.

That is the gap. It is a gap in capability, not in code volume: a hundred functions that
all depend on someone else's authoring session are one capability short.

### What moved, and to where

| Capability | Before | Now |
|---|---|---|
| Course design method | In the author's head / a prompt | `authoring/methodology.py` — `AuthoringProfile`, as data |
| Course specification | A JSON pack written outside the product | `authoring/blueprint.py` — a validated document |
| Lesson + item construction | Hand-authored per pack | `authoring/synthesize.py` — deterministic |
| Quality control | Review, informally | `authoring/audit.py` — mechanical, blocking |
| New subject from a topic | Not possible in-product | `authoring/draft.py` — two-pass, model-assisted |
| Registration of a new course | Edit `courses.py` + a pack file | `authoring/registry.py` — publish at runtime |
| Real photographs in the lessons | Not possible in an authored course | `authoring/illustrate.py` — licence-gated, attributed |
| Reachable by the tutor | Not reachable | `harness/authoring/tools.py` — 9 tools |
| Reachable by a client | Not reachable | `routes_authoring.py` — 12 endpoints |

## 1. The four layers

They are separate because each one can be reviewed on its own, and because a change in
one should not require re-reading the others.

```
methodology.py     HOW a course is designed      (shape, load, sequence, assessment)
      │
blueprint.py       WHAT it contains              (units, concepts, prose, prereqs)
      │
synthesize.py      MATERIALISE                   (graph + lessons + items)
      │
audit.py           REFUSE                        (the gate)
      │
registry.py        MAKE IT REAL                  (store, publish, hydrate)
```

### 1.1 `methodology.py` — the method is data

An `AuthoringProfile` fixes five things and every authoring decision reads from it:

- **Shape** — units (3–12), concepts (9–60), concepts per unit (2–6), at most two
  prerequisites per concept, no forward edges.
- **Load** — 180 words per block, 700 per concept, a 12-word floor on a summary, 2–6
  steps in a worked example.
- **Sequence** — a difficulty ramp from 1 to 5, teaching order recorded separately from
  dependency.
- **Assessment** — 4–10 items per concept, 4 options, an interleaved checkpoint per unit.
- **Honesty** — no concept may ship as a title with no prose.

`LINEAGE` records the published finding each section rests on (retrieval practice,
worked-example fade, misconception-targeted feedback, mastery sequencing, interleaving).
The citations justify a *design*, never an efficacy claim — a harness that cites research
for its own effectiveness is doing marketing.

Three profiles ship: `default`, `compact` (a unit of study rather than a year), and
`seminar` (no fade, because a seminar's evidence of understanding is an argument). An
unknown profile raises rather than falling back; an override that names a field that does
not exist raises rather than being ignored.

### 1.2 `blueprint.py` — one document a model may write

```json
{
  "schema": 1,
  "course": {"id": "cell_biology", "title": "Cell Biology", "subject": "Biology",
             "description": "…", "expected_weeks": 8, "profile": "default"},
  "units": [{"title": "What a cell is", "strand": "Structure", "objective": "…",
             "concepts": [{"title": "Cell membrane", "summary": "…",
                           "definition": "…", "example": ["…", "…"],
                           "misconception": "…", "correction": "…",
                           "application": "…", "prerequisites": ["Cell theory"]}]}]
}
```

Two conveniences exist because a model writes these: prerequisites may be given by
**title** (a model reliably knows the title it just wrote and unreliably invents slugs),
and concept ids are derived from titles when absent.

The parser never raises on content. It returns `(plan, problems)`, and the plan is `None`
only when a problem is *structural* — a dangling prerequisite, a forward edge, a cycle, a
duplicate id. Everything else (a thin summary, a two-concept unit) is advisory at parse
time and blocking at audit. One gate decides what may ship; two would disagree.

### 1.3 `synthesize.py` — not a special case

A foundry course is published into the registries the rest of the harness already reads.
If it needed its own route, its own lesson renderer or its own grading branch, the
capability would not have moved into the harness — it would have moved next to it.

Two sources of structure, in order:

1. **The generated layer** (`generated_curriculum.materialise_graph`) builds the
   concept-level items — the concept's statement, its terms, and the concept behind
   each — from the graph. Reused, not reimplemented.
2. **The blueprint** supplies the depth the generated layer cannot: the worked example,
   the misconception and its repair, the task that requires the idea, and two items that
   ask about them.

Depth is an **overlay**: the generated concept entry keeps its shape and its simulation
and media, and its generic blocks are replaced by the blueprint's prose. That is why the
lesson a learner reads and the items they are asked are written by the same author about
the same sentence — and why the audit can check that every answer is literally present.

The worked example **fades** in the final unit: it is replaced by a prompt that keeps the
method and withholds the worked content (expertise reversal). Every lesson ends with a
provenance block naming the blueprint digest and its author.

`subject_kind` is `custom` for every foundry course, including a mathematics one.
`courses.Course.uses_symbolic_engine` routes `mathematics` through `app/mathkit`, whose
templates match authored concept ids and fall back to a generic quadratic — so declaring
a foundry maths course `mathematics` would draw an unrelated parabola and present it as
though it were about the concept. The subject *name* still says Mathematics.

### 1.4 `audit.py` — the reason a generated course may exist

The failure mode of an authoring system is not a crash. It is a course that looks
complete: forty nodes, a lesson for each, four options on every item, nothing empty, and
nothing taught.

| Check | Refuses when |
|---|---|
| `item_unanswerable` | the correct option is not present in the block the item claims |
| `item_answer_mismatch` | `answer_id` and `answer_text` disagree |
| `item_duplicate_option` | two options carry the same text |
| `block_missing` | a required block is absent (and not deliberately faded) |
| `lesson_thin` | the whole lesson is under 60 words |
| `summary_thin` / `example_thin` | the prose floors are not met |
| `misconception_missing` | the lesson names no mistake, so it cannot teach a discrimination |
| `items_too_few` | fewer than four items on a concept |
| `difficulty_flat` | every concept is the same difficulty |
| `category_missing` | the course asks only recall, or only application |
| `origin_missing` / `not_marked_derived` | a concept cannot be told apart from hand-written material |
| `graph_*` | the graph is cyclic, or a prerequisite does not exist |

Severity is two-valued on purpose. `error` means do not publish; `warning` means a human
should look. A three-valued scale invites the argument about which middle tier a problem
belongs in, and that argument is how a blocking check becomes advisory.

## 2. Three entry points

Mirroring `app/harness/playground/pipeline.py`:

| Function | Invented | Needs a model |
|---|---|---|
| `synthesize.build(plan)` | nothing — the blueprint says it | no |
| `registry.store(settings, course)` | nothing — audit, persist, publish | no |
| `draft.draft(settings, topic)` | the outline, then the prose | **yes** |

### Drafting is two passes, on purpose

1. **Skeleton** — metadata, unit titles, concept titles, prerequisite intent. Cheap,
   reviewable at a glance, and where sequencing errors live.
2. **Expansion, unit by unit** — summary, definition, worked example, misconception and
   repair, transfer task.

One pass would truncate at twelve concepts and rush the last four, invisibly. One unit at
a time keeps every request inside a budget where the model can finish, and makes a
partial failure one retry rather than a discarded course.

The retry carries the validator's own complaint — the JSON path and the rule it broke —
because a retry that re-asks the same question is a second coin flip, not a retry.

### Without a model

`draft` refuses, with a reason, and points at the path that does work: supply a
blueprint. A teacher, an operator or the tutor itself can write one with no model at all,
and the same synthesizer and audit build it. There is no template that turns the string
"thermodynamics" into a course, and pretending otherwise would produce exactly what the
rest of the harness is built to avoid.

## 3. Persistence and reach

`registry.py` stores one JSON file per course under `data_dir/authored_courses/`,
carrying **the blueprint and the materialised lessons and items**. What was audited must
be what is served: re-synthesizing on load would mean a code change could silently alter
a course a learner is halfway through, and the audit that let it in would no longer
describe it. `POST /rebuild` is how a course picks up a new synthesizer deliberately.

Publishing rebinds `courses.COURSES` and updates `COURSE_BY_ID`,
`curriculum.CONCEPTS`/`QUESTIONS`/`CONCEPT_COURSE`. The patch on `courses.course` /
`graph_for` wraps whatever is installed, so it chains with `course_builder`'s identical
patch: a miss falls through both, and an unknown id still raises `UnknownCourse`.

Three collisions are refused: a shipped course id, a learner-built course id, and a
concept id that already belongs to another course.

`hydrate(settings)` runs in `create_app`'s lifespan, after `validate_curriculum()`. An
unreadable record is withheld with its reason and reported through
`GET /api/v1/author/courses`, never silently dropped.

### Surfaces

```
GET    /api/v1/author/methodology
GET    /api/v1/author/courses
POST   /api/v1/author/preview        plan and audit; store nothing
POST   /api/v1/author/courses        build, audit, store, publish, illustrate
POST   /api/v1/author/draft          author from a topic (503 without a model)
GET    /api/v1/author/courses/{id}
GET    /api/v1/author/courses/{id}/blueprint
POST   /api/v1/author/courses/{id}/units     append a unit and rebuild
POST   /api/v1/author/courses/{id}/rebuild
POST   /api/v1/author/courses/{id}/illustrate  whole book, or one concept with an image
GET    /api/v1/author/courses/{id}/images    the photographs it actually serves
DELETE /api/v1/author/courses/{id}
```

Agent tools (teacher-gated, fail-closed, role read from the authenticated principal):
`author_course`, `draft_course`, `list_authored_courses`, `read_course_blueprint`,
`extend_course`, `describe_methodology`, `illustrate_course`, `attach_lesson_image`,
`course_images`. `author_course` and `draft_course` illustrate by default, so one tool call
produces a textbook that already carries its photographs.

Operator CLI — the third entrance to the same library calls, for a box with a shell:

```
python scripts/author_course.py --methodology
python scripts/author_course.py --blueprint my_course.json --preview
python scripts/author_course.py --blueprint my_course.json
python scripts/author_course.py --topic "cell biology" --units 3
python scripts/author_course.py --blueprint my_course.json --illustrate
python scripts/author_course.py --blueprint my_course.json --render review.html
python scripts/author_course.py --images cell_biology
python scripts/author_course.py --list
python scripts/author_course.py --delete cell_biology
```

It prints the audit rather than hiding it, so a refusal on the command line shows exactly
what the HTTP route would have returned as a 422.

`--render` writes a standalone review copy: units, concepts, every block, every item with
its four options and the correct one marked, and the audit verdict at the top. The stored
record is the JSON; the review copy exists because a course is prose, and prose has to be
read before it can be approved. The page escapes everything it prints — the body is
model-written text, and a `<` in a lesson must stay a `<`. It renders a *refused* course
too, with the findings listed, since that is the case where a human most needs to look.
`docs/authored_course_sample.html` is a checked-in example (9 concepts, 54 items) so the
format can be inspected without running anything. `docs/authored_course_illustrated.html`
is the same course after illustration, with the four photographs inlined as data URLs — it
opens with no server and no network, which is what a reviewer needs to be able to send it
to somebody.

### Proof that it is not a special case

`test_an_authored_course_is_studyable_through_the_existing_endpoints` authors a course,
enrols a learner in it, and then serves it through `GET /curriculum`,
`GET /lessons/{concept_id}`, `GET /knowledge-graph` and `GET /questions/next` — the same
four routes that serve the shipped courses, with no branch of their own. If any of them
needed one, the capability would have moved next to the harness rather than into it.

## 3a. Real images in the textbook

A course written by the foundry used to be text. That is a real defect for exactly the
parts of a subject that are about what something *looks like*: a lesson on a phospholipid
bilayer that never shows one is asking the learner to build the picture from a sentence.

The image machinery already existed and was already complete —
`app/harness/media.py` searches four providers, classifies each candidate's licence, caches
what it may store, records the manifest, and `GET /lessons/{id}` already inserts
`photograph` blocks. What did not exist was **any connection from authoring, or from the
tutor, into it**. `authoring/illustrate.py` is that connection and nothing else.

### How a photograph gets into a lesson

1. `illustrate(settings, course)` walks the concepts in teaching order. For each one,
   `media.fetch_for_lesson` decides which block positions want a picture (the concept
   itself, and a `worked_example`), builds the query from the concept's own title, and
   passes the summary as *ranking* evidence.
2. A candidate must clear the licence gate and the relevance filter before anything is
   downloaded. A cleared asset is downloaded, content-addressed, and written to the
   manifest with its author, licence code, licence URL and attribution string.
3. The assignment (`concept → block_index → sha256`) is appended to
   `media/lesson_images.jsonl`, which is what the lesson route reads. The lesson therefore
   serves the image on the next read with **no branch of its own**.
4. `attach(settings, course, concept_id, query=...|sha256=...)` is the single-image move:
   the tutor searched with `image_search`, chose one, and pins it next to the definition.

### Five rules this layer keeps

- **Nothing is fabricated.** No placeholder, no generated stand-in, no "image pending"
  block. A concept that found nothing is reported with the reasons its candidates were
  dropped, and keeps its deterministic concept map.
- **A textbook image must have a verified licence.** A clipboard paste and a
  bundle-restored file are real images with no rights position; they stay servable to the
  account that owns them and are refused for a textbook, because the block renders a credit
  line and a credit line reading "unverified" is a rights problem printed on the page.
- **The record does not own the images.** The authored JSON deliberately does *not* store
  the photograph list: the manifest and the assignment index are the truth, so a record
  cannot claim an image whose bytes were deleted, and a rebuild does not lose the pictures.
- **Illustration runs after the audit, never inside it.** The audit decides whether the
  *content* may ship; a network call must not sit in that path. An offline instance
  publishes a complete, audited, text-only textbook and says so in the response.
- **Deleting a course forgets its photographs.** The index is keyed by concept and knows
  nothing about courses, so `registry.delete` drops those rows — otherwise a later course
  reusing an id would inherit photographs nobody chose for it.

### Two defects found by running it, both now pinned by tests

The first end-to-end run illustrated 3 of 9 concepts, and a later run illustrated all 9
with, among others, a photograph of a band called "The Cell Theory" and two NASA station
shots. Both are fixed in `media.py` and each has a regression test:

- **The concept query appended the summary's first clause.** Measured against the live
  providers, `"Cytoplasm The aqueous interior of the cell where most metabolic reactions
  take place"` returns **zero** candidates while `"Cytoplasm"` returns 41. The clause did
  not sharpen the search, it emptied it — and the empty result was reported as "no
  photograph exists for this concept". The query is now the title; the summary travels as
  `support` and only *orders* the cleared candidates.
- **The download loop walked the whole ranked list.** When the top candidates were
  rate-limited (HTTP 429), the loop silently skipped past them and attached whatever
  finally answered — the ninth-ranked hit. The ranking *is* the relevance judgement, so the
  fetch now stops after `MAX_DOWNLOAD_ATTEMPTS` (4), stops immediately on a 429, and always
  reports `skipped` with the reason. A wrong image with a real credit line is worse than no
  image, because it looks authoritative.

A third defect was found on 2026-10-26, while asking why 56 of 57 economics concepts had no
photograph. It was not the relevance filter working as intended — it was the **User-Agent**:

- **Wikimedia Commons answered 403 to every request.** Its API policy refuses an agent whose
  `User-Agent` carries no reachable contact route, and the identifier line this project sent
  had none. The same line plus `contact: operator@example.invalid` returns 200; a contact on
  a dotless host (`operator@localhost`) is refused again, which is how the rule was pinned
  down. A 403 here is *the provider answering*, and the code reported it as
  `unavailable: HTTPStatusError`, i.e. as a transport fault, so the empty result read as
  "Commons has no photograph of this concept". The largest cacheable photo collection in the
  world was offline for the whole project and nothing failed. The UA is now built by
  `media.user_agent(settings)` from `HARNESS_MEDIA_CONTACT`; when the operator has not set it
  the reserved placeholder `operator@example.invalid` is sent and *the search notes say so*,
  because an unset contact is an operator fact, not a photograph that does not exist.
- **A block-level image slot searched a ten-word phrase.** `lesson_image_needs` appended two
  words from the block body to the concept title. These APIs AND their terms, so that
  lowered recall to zero — exactly the failure `_concept_query` documents. The slot now
  searches the title and passes the block body as `support`, which ranks without gating.
- **Figures were painted over by their own background.** The paper rectangle was emitted by
  `_axes`, i.e. *after* the title text, so every figure with axes had an invisible title. All
  57 lessons shipped this way and no test noticed, because every assertion was about
  arithmetic. `scripts/check_figures.py` now lints the geometry of every template (text
  outside the canvas, labels overlapping by more than a quarter, paper painted after the
  title) and reports 44/44 clean; a test pins the paint order.

### Reviewing what was attached

`--images COURSE_ID`, `GET /courses/{id}/images` and the `course_images` tool all report
the same thing: per concept, the photographs served, with their credit. `--render` draws
them, and prints "No photograph: no candidate cleared the licence and relevance gate" where
a concept has none — the absence is stated rather than left as a blank space.

A note on quality that the pipeline cannot fix for you: full-text image search over a
general corpus is a weak instrument for an abstract concept. The guard rails are that the
candidate must clear a size/aspect floor, a lexical overlap gate and the licence gate, and
that a human reviewing `--render` sees every credit line before the course is approved.
Treat the illustration report as a *first draft with provenance*, not as a finished plate.

### The second pass: 22 photographs, half of them wrong

Fixing the User-Agent took AP Microeconomics from 1 photograph to 22 of 57 concepts. Reading
the list was the point of the exercise, and about ten of the 22 were wrong — every one of
them with a correct credit line:

| concept | what was attached |
|---|---|
| Asymmetric information | "Asymmetric Ashes (artist's impression)", an ESO nebula |
| Short-run cost curves | "Brennan Gyroscope Car, 1907" |
| Price ceilings and floors | "8th Street, Lower Price Hill, Cincinnati" |
| Tragedy of the commons | "Topographic map of United Kingdom of Libya" |
| Perfect competition | "Hiller XHOE-1 Hornet", an aircraft |

Each shared exactly one word with its concept. The gate was a lexical *overlap* score with a
0.5 floor, and covering half of a two-word title is one word — so the score was satisfied by
a coincidence. Five changes came out of it, and each one is a test:

- **A shared word is not a shared subject.** `media.head_mentioned` requires the asset's
  **title or tags** to mention the query's **head term**, which English noun phrases put
  last: *asymmetric **information***, *cost **curves***, *the **commons***. Inflections are
  compared by root, because requiring four characters after stripping the suffix left
  "taxation" unable to reach a caption that says "tax"; the roots must be *equal*, because a
  prefix rule (tried and removed the same hour) matched `infographic` against `information`
  and attached a "Balance of power graph" to asymmetric information. A rejection names the
  missing term rather than the score, since "only 50% of the query words appear" is true and
  useless when the half that appeared is the half that means nothing.
- **The description is not identity.** The head test reads the title and tags only. A
  topographic map of Libya cleared "tragedy of the commons" because its Commons description
  says `commons.wikimedia.org`; a street photograph cleared "price ceilings and floors"
  because the building has floors; a 1907 aircraft cleared "perfect competition" on the word
  "characteristics" in a museum's cataloguing note. A free-text description mentions
  everything. It still ranks candidates; it does not pass them.
- **The other half of the concept is a wrong answer.** "Monopolistic competition in the long
  run" was illustrated with the *short-run* equilibrium diagram, and entry and exit — the
  whole difference — are absent from that picture. The same shape appeared once more: a graph
  whose own description reads "Balance of Power with **Perfect** Information" was attached to
  the lesson on *asymmetric* information, i.e. the case the concept is defined against.
  `media.contradicts` refuses an asset whose own words claim the opposite of a phrase the
  query turns on.
- **"No photograph" is a state the index has to hold.** The assignment index is append-only
  with "newest row wins", so a stricter pass reported concepts with no photograph while the
  lessons still served the pictures the earlier pass had attached. `withdraw_lesson_images`
  writes a tombstone row, and the reader honours it, so the report and the page agree.
- **A short query has to be covered completely.** "Asymmetric information" has two content
  words, so half of it is one word — and one word is what a coincidence looks like: a
  heritage photograph of "The Old Coach House, Parkview Clinic" cleared it on the tag
  *information*. Queries of two words or fewer now require every word; longer ones keep the
  0.5 floor, because demanding all of "long-run average total cost and economies of scale"
  would refuse the one asset that is exactly about it. The rule is graded because the two
  failure modes are.
- **The figure a concept carries is decided by the pack, not by the last publish.** Overlay
  publication writes its own summary onto the materialised concept, and the figure
  classification read that summary, so a rebuild could silently lose a diagram: two finished
  lessons came back with no figure and the audit passed, because the audit checks prose and
  the figure is not prose. Classification now reads the graph node's own title, summary and
  keywords.
- **The word "market" was a shape.** The catch-all rule for supply-and-demand listed `market`
  among its triggers, so every concept whose summary mentioned a market got a generic
  two-curve picture — including asymmetric information, whose claim is that a market *fails*
  to clear. The catch-all now needs an actual market phrase, and the concept got a template
  that models it: the lemons figure draws one supply line for good units and one for lemons
  against the value of an *average* unit, so the good market is shown missing rather than
  cheap. Where no template models a concept, `for_concept` returns `None` and the lesson
  keeps its prose and no figure.

The arithmetic of the second pass, for the record: 22 attached, about ten wrong; after the
gate above, 16 attached and the wrong ones are the marginal cases a lexical filter cannot
settle (a receipt for two identical cars under "price discrimination"). Photographs are a
*first draft with provenance*; `scripts/render_figure_sheet.py` is the page a reviewer reads
to judge the deterministic layer, and `--render` is the page that carries both.

## 4. Deliberately not done

- **No code generation.** A blueprint has no field that can become code, no field that can
  override a limit, and no field whose value is evaluated. The worst a bad blueprint can
  do is fail the audit.
- **No invented sources.** A foundry course cites `policy.reference_media` like any other;
  external readings are link-only.
- **No silent authorship.** Every concept and item carries `origin: harness_authoring` and
  `generated: true`, `curriculum.authored_share` counts them as derived, and every lesson
  says so in a block the learner reads.
- **No symbolic engine.** See §1.3.
- **No automatic publication from a draft.** `draft` returns a course only if it passed
  the audit; there is no path that stores an unaudited one.

## 5. Adding a profile

A new method is a named profile in `methodology.py`, not an edit to a prompt:

```python
def laboratory_profile() -> AuthoringProfile:
    return replace(default_profile(), name='laboratory',
                   assessment=replace(Assessment(), min_items_per_concept=6),
                   fade_in_final_unit=())
```

Register it in `PROFILES`, add a test that a course built under it passes its own audit,
and it is available to every surface by name.
