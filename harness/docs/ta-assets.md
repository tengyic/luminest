# TA: asset review and the interval check

SSOT for the split between what the **teacher** does and what the **TA** does, and for the
one route that enforces it: `POST /api/v1/ta/sweep`.

## The division of labour

The teacher talks. The TA makes sure there is something to talk *about*. That is not a
stylistic preference — it is the difference between a lesson that stalls and one that does
not. A teacher who has to stop mid-sentence to discover that the simulator is wrong, or that
the video does not embed, has already lost the room.

| Job | Owner | Where |
|---|---|---|
| Explain, question, draw, hold the turn | teacher | `policy.py`, `session.py`, `conduct.py` |
| Decide *whether* to speak at all | supervisor | `teaching/supervision.py` |
| Decide *what* the lesson is | procedure | `teaching/procedure.py` |
| Check the assets exist, are on topic, are showable | **TA** | `teaching/assets.py`, `routes_ta.py` |
| Repair a broken asset | **TA** | `ta.plan_repair` → `ta.dispatch` |
| Speak | VoiceStudio | `harness/speech.py` |

## Why the check exists

The generators are deterministic, which makes them reliable but not automatically
*relevant*. The template table matches a concept's title, topic and keywords against a rule
list, and when no rule fits, the concept falls through to a neighbour that is real content
for a **different** idea. The engine cannot notice, because from its point of view it
succeeded.

This is not hypothetical. `Permutations and combinations` was rendered as a **binomial
sampling distribution** — correctly drawn, with real readouts — because the probability rule
claimed the keyword `permutation`. A learner asking about `nPr` and `nCr` would have been
shown a distribution over success counts.

So the review asks the one question the generator cannot ask itself: **does this artefact
talk about this concept?** The test is the concept's own identifying vocabulary — title and
keywords, minus words every figure in the subject uses — appearing in the artefact's own
prose (title, objective, notes, steps, readout labels).

The **topic is deliberately excluded** from that vocabulary. Every concept in a unit shares
its topic ("Conditional probability and counting"), so a figure that only mentions the topic
has said nothing about *this* concept. Including it made the binomial figure pass.

## Verdicts

| Verdict | Usable? | Meaning | Substitute now | Fix afterwards |
|---|---|---|---|---|
| `ok` | yes | about this concept, has controls or a curve | — | — |
| `fallback` | yes | honest concept map; no template matched | — | `rebuild_simulation` |
| `unverified` | yes | video failed the oEmbed probe; link only | `watch_link` | `search_videos` |
| `off_topic` | **no** | a figure for a different idea | `video` if one is curated, else `concept_map` | `rebuild_simulation` |
| `broken` | **no** | no controls and no curve | `video` if one is curated, else `concept_map` | `rebuild_simulation` |
| `missing` | **no** | nothing was generated | `concept_map` | `build_figure` |

A broken or off-topic interactive hands off to the curated video **when one already exists
for this concept**, and to a concept map otherwise. A video teaches the same idea; a concept
map only shows where the idea sits. The repair is unchanged either way — the TA still
rebuilds the interactive, because the video is a stand-in, not a replacement.

`missing` is deliberately excluded from that hand-off. A broken simulation has something to
hand off *from*; a missing one does not, and reaching for a video there would quietly turn
"this concept has no interactive" into "this concept is taught by video", which is a
different promise.

A repair plan never depends on the network to keep the lesson going. Substitution is always
something the instance can already do — a curated video, a concept map for a missing
simulation, the watch link for an unverified video. A video *search* is an upgrade, and it
is only planned when `media_enabled` is on, because planning a job that is guaranteed to
refuse is worse than planning nothing.

`blocking` (not usable) and `downgrades` (usable but improvable) are separate lists because
they call for different behaviour: the first must be said before the teacher reaches for the
asset, the second is reported so the TA can improve it without interrupting anything.

## The route

```
POST /api/v1/ta/sweep          (teacher only)
  { "concept_id": "algebra_2_permutations_and_combinations",
    "signals": { ...AssessInput, optional } }
→ { concept, figure, assets{reviews,problems,downgrades,clean,all_ok},
    plan[], supervision|null, report, ready }
```

It is a route and not a `ta.dispatch` job because it needs neither a model nor a network: it
builds the figure with the symbolic engine, reviews the text it produced, and reads the
account's own state. That makes it cheap enough to call on every interval tick, which is what
"silently, on an interval" requires. `dispatch` remains for the slow work of *making* the
class ready.

It never writes. The figure is rebuilt rather than cached because the engine is
deterministic, so rebuilding is the cheapest guarantee that what was reviewed is what the
teacher will show.

`signals` reuses `AssessInput` verbatim, so a client that already posts to
`/supervision/assess` sends the same body. A client-supplied `mastery` is refused (422,
`extra='forbid'`) and overwritten from the account's own state: the check does not grade its
own homework.

## What it found, and what was fixed

* **The counting template.** `mathkit` gained `fact`/`choose`/`permute` and an
  `arrangements` template: P(n,r) and C(n,r) over the same n and r, with the curve C(n,r) as
  r varies and a readout showing P ÷ C = r!. This is the concept's own contrast, generated
  deterministically, with no model.
* **`video_search` read `result.get('ok')`** from `video.verify`, which reports
  `embeddable`/`method` and has no `ok` key. Every verified video was silently demoted to a
  plain outbound link, so no embed was ever offered.
* **Scraped titles.** The keyless DuckDuckGo fallback can return several results' titles
  concatenated into one row. The oEmbed probe's title is authoritative and now wins.

## Measured coverage

`scripts/probe_assets.py` reviews every concept in every shipped pack:

| Pack | Concepts | Result |
|---|---|---|
| algebra_one_year | 164 | 164 on-topic simulations |
| ap_calculus | 79 | 79 on-topic simulations |
| algebra_2 | 80 | 75 on-topic, 5 concept maps (matrices) |
| physics, chemistry, biology, earth/space, CS, econ | 626 | concept maps — the honest figure for a non-mathematical subject |

Every mathematics concept gets a figure about itself. The five that fall back are the matrix
concepts, which are genuinely not "a quantity as a function of one variable"; a plot of one
would be a lie. `tests/test_assets.py::test_the_only_mathematics_concepts_without_a_simulation_are_the_matrices`
pins that set, so closing the gap is a deliberate act.

For science and social science the honest answer is a concept map, not an experiment.
`simulation_map.py` maps those concepts to real external simulations (PhET, Gizmos deep
links), and every slug is re-verified over HTTP before it is shown.

## What still needs an operator decision

* **A model-backed tutor.** `HARNESS_TUTOR_PROVIDER=openai` (plus `HARNESS_TUTOR_KEY`, or
  `DEEPSEEK_API_KEY` in `backend/.env`) is required for a tutor that answers questions. An
  offline instance still builds the figure, the deck and the practice items; it just cannot
  hold a conversation.
* **`write_simulation`** (model-authored HTML simulations) refuses without a provider. The
  symbolic engine covers mathematics without one; everything else uses the external mapping.
* **Video curation is now the TA's job.** `POST /api/v1/ta/prepare` searches, verifies and
  curates in one call, so a class can have a video without an operator. See below.
* **A YouTube Data API key** (`HARNESS_YOUTUBE_API_KEY`) makes search authoritative and
  quota-metered instead of scraping, which also removes the rate-limit caveat.

## Getting a class ready: `POST /api/v1/ta/prepare`

`sweep` answers "is this class ready?". `prepare` answers "make it ready", and the difference
is one write.

```
POST /api/v1/ta/prepare        (teacher only)
  { "concept_id": "...", "curate_video": true }
→ { concept, assets, figure, video{curated,title,reason,search_path}, ready, report }
```

A concept with no curated video has none in its lesson, because the procedure refuses to
promise a video it cannot verify — correct, and it leaves every uncurated concept without a
video. Curating is what turns "no video" into "video":

* `video_search.curate_for_concept` searches, then ranks candidates by how many of the
  concept's own terms appear in the title (`relevance`), then takes the best one that passed
  the oEmbed probe.
* Two query formulations are tried. The keyless DuckDuckGo fallback returns "no results" often
  enough (rate limiting, no exact-phrase match) that one query is a coin flip.
* `video.curate` writes the same `media/video_allowlist.json` a human curator writes, is
  idempotent (a TA may retry a job it never saw finish), and refuses an id on the operator
  revocation list, so re-curating cannot undo a withdrawal.
* An **unverified** candidate is not curated unless the caller explicitly accepts links.
  An unverified direction is never the permissive one.

Only video is repaired here. A figure that is off-topic is regenerated by the deterministic
engine on the next build; a broken one needs a new template, which is a code change, not a
job. Saying so is better than pretending to fix it.

## Speaking: what the engine actually does

Measured, not assumed, on this machine:

| Fact | Consequence in the code |
|---|---|
| One GPU worker; a second concurrent request is **refused** with a 429, not queued | `voice.synthesize` serialises per engine address (`_engine_lock`) |
| The 429 says the request never started and quotes the wait ("about 31s") | one retry after that interval, then an honest failure |
| ~8 characters per second; a 1,800-character reply is a 4-minute render | `speech.utterances` splits a reply into ~220-character clips |
| The first request after an idle engine pays the model load | `speech.warm` renders a short phrase at startup, in its own thread |
| A failed render writes no file, so every poll is a bare 404 | `speech.state` reports `failed` with the engine's own sentence |

Without the split, the tutor's first reply was a single utterance that outlived the 180-second
render timeout, so **every** spoken turn failed — which from the outside is a teacher who
simply never speaks. With it, the same reply is eight clips and all eight render.

`GET /api/v1/media/audio/{digest}/state` is the poll-friendly form: `ready`, `pending`,
`failed` (with `reason` and `code`) or `unknown`. The byte route's 404 is deliberately
ambiguous — a client that only polls bytes cannot tell "still rendering" from "never will".

## Which utterance may interrupt which

The teacher is spoken, so two of its sentences can be in the air at once. `speech.classify`
tags every clip with what it is *for*, and the tag decides how it meets whatever is playing:

| Kind | Delivery | When |
|---|---|---|
| `answer` | `replace` | the learner interrupted; stop the clip and answer |
| `explanation` | `append` | the teacher is mid-flow; queue it |
| `notification` | `idle_only` | the interval check; never cut across a sentence |

The tag is **not** part of the digest: the same words can be an explanation in one place and
an answer in another, and they are byte-identical audio.

When a learner interrupts, the client sends `interrupted: true` on the next turn. The turn's
system prompt then says the last reply was cut off and must not be resumed — a model that is
not told this finishes the abandoned sentence first and answers second, which reads as not
listening.

The interval check returns a `notice` alongside its reading: `say: false` with a reason when
the supervisor chose to stay quiet (working, or inside the cooldown), or `say: true` with the
one sentence and `delivery: idle_only`. A client cannot accidentally speak a thought the
harness decided to keep to itself.

## Generated questions: distractors come from nearby

`generated_curriculum.py` builds four items per concept for courses with no hand-written
questions. Its distractors used to be drawn from **other units** (`n.unit != node.unit`), on
the theory that same-unit options might be too similar. The result was a permutations item
offering *"radians measure an angle by arc length"* and *"a common denominator is required"* —
obviously wrong on sight, so the item tested nothing.

`_neighbours` now ranks candidates same-topic → same-unit → same-strand → the rest, and
`_near_duplicate` drops an option whose text overlaps the correct one by 80% or more. The same
item now offers *determinants*, *binomial coefficients from Pascal's triangle* and *sigma
notation*: wrong, and tempting.

## Scripts

* `backend/scripts/probe_assets.py` — review every concept in every pack; exit 1 on any
  off-topic or broken figure.
* `backend/scripts/class_pack.py` — print everything the harness can deliver for one concept
  (deck, figure, video, practice, review, repair plan).
* `scripts/probe_class.py` — start the real server, enrol, prepare the class, teach one turn
  with speech on, and print the transcript.
