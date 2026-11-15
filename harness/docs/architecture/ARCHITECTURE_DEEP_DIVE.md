# Luminest — Architecture Deep Dive

**Scope.** The control flow, algorithms, tool surface and stack of the Luminest
learning harness, with the constants that actually run. Every claim below cites a
file and, where it matters, a line. Verified against the working tree on
**2026-11-16** by reading the code, not by reading other docs.

**Notation.** `path:line` is relative to `harness/`. Formulas are transcribed from
the implementation (variable names kept) so they can be checked against the source.

> **A note on an existing dead reference.** `docs/architecture/INDEX.md:10` points at
> `../../ARCHITECTURE.md`, which does not exist in this tree. This document is the
> missing overview; `INDEX.md` remains the capability→file→test map.

---

## 0. The system at a glance

Four cooperating surfaces, one backend, one licence policy:

```
┌──────────────────────┐   ┌──────────────────────┐
│ native macOS app      │   │ static web workbench │   ← clients
│ SwiftUI / SwiftPM     │   │ vanilla JS, no build │
└──────────┬───────────┘   └──────────┬───────────┘
           │  HTTPS/JSON + SSE        │
           ▼                          ▼
┌──────────────────────────────────────────────────┐
│ FastAPI app  (create_app --factory)              │
│  auth → context → prompt assembly → agent loop    │
│  → toolbox (53 tools) → post-processing           │
├──────────────────────────────────────────────────┤
│ teaching layer: decision scorer · procedure FSM   │
│ algorithms: FSRS-6 DSR · BKT mastery · grading    │
│ gates: licence policy · coverage · creation gate  │
├──────────────────────────────────────────────────┤
│ SQLAlchemy 2.x: SQLite (default) | PostgreSQL     │
│ files: boards/, media cache, audio cache          │
└──────────────────────────────────────────────────┘
```

The rule that shapes everything else: **the model decides *what* and *when*; the server
owns *which*.** Concept ids, board ids, tool availability, surface ownership and
licence class are server facts. A model that invents one gets corrected or refused,
never trusted.

---

## 1. Control flow: the request path

### 1.1 `POST /api/v1/agent/chat`

Body cap **16 MiB** (`app/main.py:86`). Handler `agent_chat` at `app/main.py:3941`
delegates to the generator `agent_turn_events` (`:3679`), which:

1. **Builds context** (`harness_context`, `:478-490`): enrolled course → `context_for`
   → `ToolContext` with `db`, `user`, `settings`, `workspace`, `graph`,
   `subject_kind`, `course_id`.
2. **Attaches client routing facts** (`:3700`): `ctx.client_context = dict(payload.context or {})`
   — the only channel for `concept_id` / `board_id`.
3. **Derives the live surface server-side** (`:3708-3710`): if `concept_id` matches
   `[a-z0-9_.-]{1,80}`, `ctx.surface` is read from `procedure_service.surface_state`,
   **not** from the request.
4. **Builds the tool payload** (`:3715`): `agent_loop.tools_payload(toolbox.available_specs())`.
5. **Assembles the system prompt** (`agent_messages`, `:3533`): persona + teaching
   protocol + conduct + sequence requirement; optional speak/interrupted/style blocks;
   then, guarded by regexes, the real `concept_id` and `board_id` with their plan,
   procedure and draw-aloud sections; then the acting role; then up to **4** images
   (`data:image/(png|jpeg|webp);base64`, each ≤ 2,000,000 chars, else 422).
6. **Runs the loop** (`:3718`) and post-processes the final event.

**No history is replayed.** `agent_messages` returns exactly two messages — one
`system`, one `user` (`:3534-3536`). Continuity is the `memory` tools' job, not the
transcript's. That keeps the prompt bounded and makes recall an explicit, auditable
action rather than a side effect.

### 1.2 The agent loop, exactly

`app/harness/agent_loop.py:159`

```python
def run_agent(settings, messages, registry, ctx, *, tools=None,
              max_steps=DEFAULT_MAX_STEPS, developer_mode=False,
              cancelled=None, usage_out=None, max_tokens=8000,
              temperature=0.2) -> Iterable[dict]
```

Limits (`:42-43`), with a clamp the caller cannot override (`:179`):

```python
DEFAULT_MAX_STEPS = 8
HARD_MAX_STEPS    = 24
steps = max(1, min(int(max_steps), HARD_MAX_STEPS))
```

The loop, reduced to its skeleton:

```python
if not provider.available(settings):                 # :180
    yield {'type': 'error', ...}; yield {'type': 'turn_end', 'reason': 'unavailable'}; return

yield {'type': 'turn_start'}                          # :188
reason, content = 'completed', None

for _ in range(steps):                                # :191  ← the only iteration
    if cancelled and cancelled():                     # :192
        reason = 'cancelled'; break
    _release(ctx)                                     # :195  commit before each model call

    result = provider.chat_tools(settings, messages, tools=tools, ...)   # :196
    if result is None:                                # :199
        yield {'type': 'error', ...}; reason = 'provider_error'; break

    content, calls = result.get('content'), result.get('tool_calls') or []
    if not calls:                                     # :208  ← exit 1: model wants no tool
        if content: yield {'type': 'message_delta', 'text': content}
        reason = 'completed'; break

    messages.append({'role': 'assistant', 'content': content, 'tool_calls': calls})

    for call in calls:                                # :221  sequential, same turn
        yield {'type': 'tool_call', 'id': ..., 'name': ..., 'arguments': ...}
        outcome = _execute(registry, call, ctx)       # :228  never raises
        yield {'type': 'tool_result', 'ok': outcome.ok, 'data': outcome.to_dict()}
        messages.append({'role': 'tool', 'tool_call_id': call['id'],
                         'content': _tool_message(outcome)})

    if images_seen:                                   # :237  images come back as a user turn
        messages.append({'role': 'user', 'content': [text_note] + [part(i) for i in images[:4]]})
        yield {'type': 'observation', ...}

    _release(ctx)                                     # :251
else:
    reason = 'max_steps'                              # :255  ← for/else
yield {'type': 'turn_end', 'reason': reason, 'content': content}
```

**Exit reasons** — five, and only these:

| reason | trigger | line |
|---|---|---|
| `unavailable` | `provider.available()` false | `:186` |
| `cancelled` | client callback true at a step boundary | `:192` |
| `provider_error` | `chat_tools` returned `None` | `:199` |
| `completed` | a turn with no `tool_calls` | `:208` |
| `max_steps` | `for` exhausted | `:255` |

**Event contract** (7 types, `:49-50`): `turn_start`, `message_delta`, `tool_call`,
`tool_result`, `observation`, `turn_end`, `error`. Events stream straight out; only
`turn_end` is held back for rewriting.

**State.** `messages` is the caller's list, mutated in place and never persisted by
this function (`:19-21`). `usage_out` is a mutable dict filled by `provider.meter_usage`.
`_release` (`:261-281`) commits, falls back to rollback, and swallows a second failure
— "a poisoned session must not kill the turn". This exists because an uncommitted
write held across a 30 s model call would pin SQLite's write lock.

**Failure containment** (`_execute`, `:292-306`): unknown tool → `refused`; non-dict
arguments → `refused`; any exception from a tool → `ToolResult(ok=False, error=...)`.
A tool cannot take the loop down. Tool messages are JSON, truncated to
`MAX_REPLY_CHARS = 40000` (`:323`).

### 1.3 Post-processing of `turn_end`

Three rewrites in fixed order (`:3739-3793`):

1. Empty content with `unavailable` / `provider_error` → `grounded_tutor_reply(...)`,
   a deterministic grounded answer, with `grounded_offline=True` and an extra
   `message_delta`.
2. Still empty → `notice = {kind: 'unavailable', reason, next_action}`.
3. `speak` and content → `speech.request_sequence` + `classify` (TTS clip request).

Then, in `finally`, usage is recorded with a status mapping
`unavailable→fallback`, `cancelled→refused`, `provider_error→error` (`:3795-3822`).

---

## 2. Provider layer

`app/harness/provider.py`

| | `chat` (`:113`) | `chat_tools` (`:199`) |
|---|---|---|
| Purpose | one completion | one function-calling turn |
| Ollama endpoint | `POST {url}/api/chat` (`:152`) | `POST {url}/v1/chat/completions` (`:236-241`) |
| Other providers | `POST {url}/chat/completions` | same |
| Default max tokens | 900 | 1200 (loop passes 8000) |
| Returns | `str \| None` | `dict \| None` |

The Ollama `/v1` rule is load-bearing and was a real bug once:

```python
completions_base = cfg.provider_url.rstrip('/')
if cfg.provider == 'ollama' and not completions_base.endswith('/v1'):
    completions_base += '/v1'
```

Ollama's native `/api/chat` silently answers in prose when tools are supplied;
`/v1/chat/completions` is the OpenAI-compatible surface that actually carries
`tool_calls` (`:222-228`). Tests pin all three cases (bare URL, already-`/v1`, non-Ollama).

HTTP client: `httpx.Client(timeout=cfg.provider_timeout, follow_redirects=False,
trust_env=False)`; `provider_timeout` defaults to **30.0 s**, allowed range 1–300
(`app/model_config.py:86`, `:302`).

Parsing (`:285-310`): take `choices[0].message`; each `tool_calls[]` with a non-empty
name becomes `{id, name, arguments}`; `arguments` is JSON-decoded, and a decode failure
keeps the raw string so the tool layer can refuse it visibly. `reasoning_content`
(DeepSeek-style) is kept in a separate field and never merged into `content`.

Degradation, all returning `None` rather than raising: not configured; HTTP/parse error
(detail stored in `usage_out['error_detail']`); response body > `MAX_REPLY_CHARS * 4`
bytes; empty or over-long text.

---

## 3. Tool surface

### 3.1 Size and groups

**53 tools registered** in `toolbox.REGISTRY` (`app/harness/toolbox.py:1010`).
**52 available** in a stock environment: `browser_snapshot` declares
`requires=('playwright',)` (`:1436`) and is filtered out when Playwright is absent
(`available_specs`, `:1025-1044`).

| Group | n | Tools |
|---|---|---|
| Course / memory / teaching | 21 | `search_concepts`, `read_concept`, `inspect_prerequisites`, `recall_learner_memory`, `read_learner_evidence`, `search_material`, `fetch_material_text`, `prepare_case_study`, `build_figure`, `deck_control`, `stage_surface`, `check_understanding`, `compose_content`, `find_image`, `find_video`, `find_simulation`, `build_presentation`, `run_in_workspace`, `list_workspace`, `write_workspace_file`, `read_workspace_file` |
| Creation + multimodal | 10 | `write_simulation`, `edit_simulation`, `check_simulation`, `generate_slides`, `text_to_speech`, `image_search`, `web_search`, `image_generate`, `fetch_page_text`, `wikipedia_summary` |
| Vision / attention | 2 | `look_at_image`, `check_on_task` |
| External media | 3 | `find_game`, `search_videos`, `browser_snapshot`* |
| Stage whiteboard | 5 | `whiteboard_read`, `whiteboard_apply`, `whiteboard_write`, `whiteboard_place_image`, `draw_diagram` |
| Board canvas | 3 | `board_read`, `board_apply`, `board_place_media` |
| Course authoring | 9 | `author_course`, `draft_course`, `list_authored_courses`, `read_course_blueprint`, `extend_course`, `describe_methodology`, `illustrate_course`, `attach_lesson_image`, `course_images` |

\* unavailable without Playwright.

`ToolSpec` (`:54-80`) is deliberately prose, not JSON Schema: `name`, `summary`,
`arguments` (a sentence), `posture`, `returns`, `requires`. Postures
(`internal / personal / ingestible / embed_only / link_only / sandboxed`) record *how*
a tool touches the outside world.

### 3.2 `invoke` — the single choke point

`toolbox.py:1688`. Every tool call from the loop goes through it, which is why the
cross-cutting rules live in one place rather than in 53 tools:

```python
entry = REGISTRY.get(name)                       # unknown → refused
active = ctx.surface; owner = surface_router.tool_surface(name)
if active and owner and owner != active and name != 'stage_surface':
    return ToolResult(..., refused='The live lesson is on X; this tool belongs to Y. '
                                  'Call stage_surface first.')      # decision boundary
arguments, grounded = _ground_identifiers(ctx, fn, dict(arguments or {}))
try:
    result = fn(ctx, **arguments)
except TypeError as exc:
    return ToolResult(..., refused=f'Bad arguments for {name}: {exc}')
```

Three gates, in order:

1. **Surface ownership** (`:1701-1712`). A tool belonging to another surface is refused
   with instructions, not silently run. `stage_surface` is the neutral decision tool and
   is always allowed. This is what stops the model from drawing on a whiteboard while
   the class is on a deck.
2. **Identifier grounding** (`:1647-1685`). For the parameters a tool actually declares
   (`inspect.signature`), `board_id` and `concept_id` are replaced when they are
   missing, placeholder-shaped, or — for `board_id` — **not resolvable** via
   `whiteboard.concept_node_id()` (`:1632-1644`). A resolvable explicit id is never
   overwritten. Every substitution appends a note the trace can show.
3. **Role** (`_require_teacher`, `:1064-1086`): creation tools fail closed unless the
   authenticated principal's role ∈ {`teacher`, `staff`, `admin`}. The role is read from
   the principal, never from tool arguments.

### 3.3 Surfaces and the switch

`app/harness/teaching/surface.py`.

```python
SURFACES = ('deck', 'video', 'whiteboard', 'chat')
NEUTRAL_DECISION_TOOL = 'stage_surface'
```

`choose_surface(...)` (`:233`) fires six rules in order (`:267-349`):

1. `interrupted` → keep the current surface (except `intent == 'draw'`, which switches to
   whiteboard and records `resume_surface`). An interruption must not advance the deck.
2. Primary is `deck`/`video` → use it if its artifact is bound; otherwise a declared
   fallback (deck→chat, video→deck/chat) with `source='ceiling'`.
3. `intent == 'draw'` and a board exists → whiteboard, `source='teacher'`.
4. Drawable block kind + `top_error == 'conceptual'` + not frustrated → whiteboard.
5. Frustrated → chat, unconditionally.
6. Otherwise `primary or 'chat'`.

`stage_surface` (`toolbox.py:630`) has a side effect that matters: on success it sets
`ctx.surface = chosen`, so the new surface's tools are callable **in the same turn**.
Persistence is a triple-checked write (`procedure_service.set_surface`, `:818-880`):
unknown surface name, unbound artifact, or a deviation from the compiled surface
without a `reason` are all rejected.

---

## 4. Teaching decision: a one-shot scorer, not a loop

**This is the most commonly misread part.** `app/harness/loop.py` is not the lesson
loop. It is a deterministic scorer called once per decision.

Nine moves (`:41-51`), each with a base score and additive rules (`:394-522`):

| move | base | dominant triggers |
|---|---:|---|
| `orient` | 0.22 | `attempts == 0` +0.42 |
| `explain` | 0.20 | first attempt +0.30; `top_error == 'conceptual'` +0.38 |
| `simulate` | 0.18 (0.02 without figure) | conceptual/procedural error +0.40 |
| `retrieve` | 0.18 (0.02 without lesson) | `due` +0.55; frustration −0.30 |
| `discuss` | 0.12 | mastery ≥ 0.7 +0.36 |
| `project` | 0.08 | mastery ≥ 0.85 and attempts ≥ 4 +0.52 |
| `generate` | 0.14 | repeated move +0.34 |
| `consolidate` | 0.10 | mastery ≥ 0.8 +0.34 |
| `rest` | 0.03 | frustration +0.48; overload +0.34 |

Then history weighting (`HISTORY_WEIGHT = 0.12`, `HISTORY_CAP = 3`), sort, and
`choose = score_moves(evidence)[0]` (`:543-545`) — a pure argmax with
`MOVES.index` as the tie-break. `PROGRESS_THRESHOLD = 0.05` decides whether an outcome
is worth writing to procedural memory (`record_outcome`, `:628`).

Exam mode is a **hard constraint**, not a penalty (`:555-569`): every move except
`rest` is zeroed, `rest` gets +0.6.

`plan()` (`:550`) is the whole pipeline: gather ~30 evidence fields → score → constrain →
`modality.route` → `socratic.step` → persist a `HarnessRun(chosen=True)`.

---

## 5. The real lesson loop: a procedure state machine

`app/harness/teaching/procedure.py` + `app/procedure_service.py`.

### 5.1 Compile (pure function)

`compile_procedure(facts, evidence, assets, profile=None, *, minutes_budget=20, recent_kinds=())`
(`procedure.py:387`).

Ten activities, closed vocabulary (`:70-124`); exactly one is "teaching input" at a time:

```python
ACTIVITIES = {'diagnostic','deck','video','explain','worked_example','simulation',
              'practice','discussion','recap','close'}
INPUT_KINDS = frozenset({'deck','video','explain','worked_example'})
_DISPLAY_ORDER = ('diagnostic','deck','video','explain','worked_example',
                  'simulation','practice','discussion','recap','close')
```

`_allocate` (`:761-863`) **spends a minute budget by value priority** rather than
building then trimming:

1. one practice item, always;
2. the diagnostic;
3. the single input block (`worked_example > deck > video > explain`, first hit wins);
4. more practice, up to what the evidence asked for;
5. the interactive;
6. discussion + recap;
7. leftover budget → more practice, capped by `practice_max_items` and bank size.

Constants (`app/teaching/config.py:242-272`): `min_minutes=6`, `max_minutes=45`,
`skip_input_accuracy=0.8`, `skip_input_mastery=0.8`, `simulation_min_mastery=0.25`,
`simulation_skip_mastery=0.85`, `practice_min_items=2`, `practice_max_items=4`,
`practice_minutes_per_item=1.5`, `diagnostic_items=2`, and per-activity minute weights
(`diagnostic 3, deck 5, video 4, explain 4, worked_example 4, simulation 5,
practice 5, discussion 3, recap 2, close 1`). Requested budgets clamp to `[6, 45]`;
the real source is `user.daily_minutes or 20`.

### 5.2 Run (the state machine)

`ProcedureRun` is keyed by `(user_id, concept_id, procedure_hash)` — idempotent, so a
re-plan with the same hash resets `completed=[]` instead of stacking lessons
(`start_run`, `procedure_service.py:897`). `prompt_context` (`:1268`) compiles **and
starts** on first contact; otherwise the sequence would be recomputed each turn.

Current block = first not-completed block (`_current_block`, `:741`).

`advance_run(db, run, order, *, outcome='done', seconds=None, note='')` (`:1082`)
refuses five ways:

```python
run.status != 'active'                      → ValueError('This lesson is <status>')
block is None                               → KeyError
order already completed                     → ValueError
order != current order                      → ValueError('…Refresh the lesson…')
outcome not in {'done','skipped'}           → ValueError
# plus: 'done' with an unanswered promised item still refuses
```

Completion (`:1133`):

```python
run.status = 'completed' if len(completed) >= len(blocks) else 'active'
```

After advancing while still active, `_clear_surface` (`:1137`) prevents the previous
block's surface from leaking into the next. `render_procedure_block` (`procedure.py:1119`)
emits `[done] / [NOW] / [next]` with `Do:`, `Because:`, `Bound artifact:`, `Surface:`,
and forbids adding, removing or reordering blocks; when everything is complete it says
so and tells the model not to invent an activity.

---

## 6. Algorithms

### 6.1 Spaced repetition — FSRS-6 DSR

`app/memory.py` (374 lines). **`app/harness/memory.py` is a different thing** (learner
notes; see 6.2). State per item: `stability S` (days), `difficulty D` (1–10),
`last_review`, plus diagnostics. `R` is **not stored**; it is recomputed.

**Forgetting curve** (`:112-128`):

```
R(t) = (1 + FACTOR · t / S) ^ DECAY
DECAY  = -w20 = -0.1542
FACTOR = 0.9^(1/DECAY) − 1 ≈ 0.9803
```

By construction `R(0) = 1` and `R(t = S) = 0.9` (asserted in `tests/test_memory.py:37-39`).

**Next interval** (`:230-242`):

```
I_days = (S / FACTOR) · ( r^(1/DECAY) − 1 )      r = desired_retention = 0.9
due_at = last_review + min(MAX_INTERVAL_DAYS, I_days) · 86400
MAX_INTERVAL_DAYS = 36500
```

**Initial values** (`:154-156`, `:218`):

```
S0 = max(0.001, w[rating−1])           → Again 0.212, Hard 1.2931, Good 2.3065, Easy 8.2956 days
D0 = clamp[1,10]( w4 − e^(w5·(rating−1)) + 1 )   w4 = 6.4133, w5 = 0.8334
```

**Successful recall** (`_recall_stability`, `:137-152`):

```
S' = S · ( 1 + e^w8 · (11 − D) · S^(−w9) · (e^(w10·(1−R)) − 1) · HP · EB )
HP = w15 (0.6014) if rating == Hard else 1
EB = w16 (1.8729) if rating == Easy else 1
```

**Lapse** (`_forget_stability`, `:163`): `S'_f = min(long_term, short_term)` where

```
long_term  = w11 · D^(−w12) · ((S + 1)^w13 − 1) · e^(w14·(1−R))
short_term = S / e^(w17·w18)
```

so a lapse is "not above ~0.9518·S", not "drop to a formula value".

**Same-day review** (`_short_term_stability`, `:182`), used when `days_elapsed < 1.0`:

```
S' = clamp_{≥0.001}( S · max(1, e^(w17·(rating−3+w18)) · S^(−w19)) )
```

**Difficulty** (`_next_difficulty`, `:199-203`):

```
Δ      = −w6 · (rating − 3)
damped = (10 − D) · Δ / 9
D'     = clamp[1,10]( w7 · D_prior + (1 − w7) · (D + damped) )
```

**Rating mapping.** Practice answers use only two of the four ratings:
`learning.py:289` — `rating = GOOD if correct else AGAIN`. `HARD`/`EASY` exist only for
manual flashcard grading.

**Implicit credit propagation** (`learning.py:133-166`): a successful review awards a
distance-decayed, `IMPLICIT_CREDIT_DECAY = 0.5` stability increment to **prerequisites**,
by BFS, under `with_for_update()`, and only when `last_stability_gain > 0` and
`last_correct is not False`. It is a weak-evidence update on the same DSR state — a
reimplementation of the published FIRe idea, no proprietary code.

### 6.2 Learner-note decay (different model, often confused)

`app/harness/memory.py:29-39, 60-63, 96-101`

```
C(t) = max(0.05, C0 · 2^(−Δt / HALF_LIFE))     HALF_LIFE = 21 days
reinforce:  C ← clamp[0.05, 0.95]( C(t) + 0.22 )
start 0.35
```

Exponential, not power-law, and the decay is never written back. Retrieval ranking is
`aged(now) · weight` with weight 1.6 same-concept / 1.2 neighbour / 0.45 other, times
1.25 semantic / 1.1 procedural / 0.9 episodic; sorted by `(-score, last_seen, id)`.

### 6.3 Mastery — Bayesian belief update (BKT-style)

`app/learning.py:7-13, 74-100`. Constants: `PRIOR = 0.15`, `GUESS = 0.25`,
`SLIP = 0.10`, `LEARN = 0.12`, `MASTERY_THRESHOLD = 0.6`.

```
numerator   = p · (1 − SLIP)            if correct else p · SLIP
denominator = numerator + (1 − p) · (GUESS if correct else 1 − GUESS)
posterior   = numerator / denominator
p'          = min(0.995, posterior + (1 − posterior) · LEARN)
```

Worked example: `p=0.15`, correct → `posterior = 0.15·0.9 / (0.15·0.9 + 0.85·0.25)
= 0.135/0.3475 ≈ 0.3885` → `p' ≈ 0.3885 + 0.6115·0.12 = 0.4619`.

This is deliberately separate from `S`: memory strength answers "when will this be
forgotten", mastery answers "can they do it now". Keeping the mastery rule identical
across both memory paths is what stops the recommender changing behaviour when the
scheduler switches (`:66-69`).

`MASTERY_THRESHOLD = 0.6` drives "mastered" in recommendations, missing-prerequisite
counting and skipping; the assessment book uses a different bar, `0.70`
(`app/assessment_book.py:581`), for standards `met` / `not_yet_met`.

### 6.4 Grading

`POST /api/v1/attempts` (`app/main.py:1708`). Two input shapes, mutually exclusive (422
if both):

```python
# multiple choice
if option_id not in {o['id'] for o in question['options']}: 422
correct = (option_id == question['answer_id'])

# free text
actual = payload.answer_text.strip().casefold()
correct = (actual == question['answer_text'].strip().casefold())
if not correct:
    correct = (Fraction(actual) == Fraction(expected))   # numeric equivalence
else: False on any parse failure
```

`Fraction` is why `1/2`, `0.5` and `2/4` all grade as correct; `.casefold()` is why case
and padding never do. A receipt (`receipts.id`) must exist and be unexpired, and the
attempt stores a `payload_hash` so a graded row cannot be edited into a different claim
afterwards.

### 6.5 Misconception diagnosis

`learning.diagnose(question, correct, option_id, confidence)` (`:203`). Distractors carry
`distractor_diagnoses`; a chosen distractor with evidence yields a `category` with
`confidence = 0.35` and alternatives listed. Correct answers yield `supported_correct`
at 0.6, with "a lucky guess" explicitly among the alternatives. No evidence → `uncertain`
(or `unanswered`) at 0.2. Every result is stamped
`scope: 'Task-level hypothesis; confidence is a heuristic, not calibrated diagnostic probability'`.
That wording is the point: the system does not claim to know *why* a learner erred.

### 6.6 Concept extraction and course intake

`app/course_builder.py`. Thresholds (`:617-620`):

```python
MIN_SOURCE_CHARS       = 400
MIN_SOURCE_WORDS       = 80
MIN_SOURCE_PARAGRAPHS  = 2
MIN_CONCEPTS           = 4      # four concepts give three grounded distractors
```

Validation order (`:643-654`): chars/words → paragraphs → extraction, each a distinct
refusal code (`too_short`, `too_few_paragraphs`, `too_few_concepts`). Markdown headings
declare concepts, which is why a headed 4-paragraph source reliably clears 4 concepts
while a single dense paragraph does not. `MIN_CONCEPTS = 4` is not arbitrary: a 4-option
question needs three distractors that are actual neighbours in the same material.

### 6.7 Licence classification and rollup

`app/ingest/policy.py`. Ten classes (`:42-70`):

```
public_domain, cc0, cc_by, cc_by_sa, cc_by_nc, cc_by_nc_sa, cc_by_nd,
embed_only, link_only, prohibited
```

`INGESTIBLE = {public_domain, cc0, cc_by, cc_by_sa}` — only these may enter the
knowledge graph. `CC_BY_NC*` is **not** storable in this build, regardless of who the
user is; non-commercial is a *use*, re-evaluated at read time
(`reapply_media_policy`), not a property baked in at download time.

Rollup for board export (`board.py:644-684`) considers **image nodes only**, with
severity `CC_BY_SA(5) > CC_BY(4) > unknown(3) > CC0(2) > PD(1)`: one ShareAlike member
makes the whole export ShareAlike, because a mixed board rasterised into one artifact is
one derivative work.

### 6.8 Simulation coverage

`app/simulation_map.py`. Similarity is the **overlap coefficient**, not Jaccard:

```
overlap(A,B) = |A ∩ B| / min(|A|, |B|)
earned = max(concept-label similarity, simulation-title similarity)
score  = earned + 0.15 · unit-name similarity
keep   = earned >= 0.34
```

The threshold applies to `earned`, so the unit bonus (≤ 0.15) can reorder candidates but
**cannot rescue** a match below 0.34. Unit name is a tie-breaker only.

### 6.9 Measurement

`app/measurement/`. Deliberate design choices, not incidental:

- **Cold probe conditions are published with every probe** (`probe.py:80-85`): no
  feedback until submit, no lesson text on screen, no tutor turn in between, and the
  item is outside the recognition window. Otherwise "correct" measures recognition.
- **Probing is rate-limited on purpose** (`:128-131`): frequent probing turns practice
  into assessment and teaches learners to practise for the probe.
- **Efficiency is a slope, not a ratio of wall-clock** (`contracts.py:27, 48`): idle time
  inflates every wall-clock ratio, so the episode boundary is explicit and the headline
  metric is a slope against measured learning.
- **Aid conditions are treated as measured variables**, not as learning. The benchmark
  validates the estimator against a known generating process and says so: it does not
  prove the learner-facing figure is unbiased (`bench.py:10`).

---

## 7. Data model and tenancy

`app/db.py`, SQLAlchemy 2.x typed ORM (`Mapped[...] = mapped_column(...)`),
`SCHEMA_VERSION = 11` (`:75`).

**41 tables**: 37 `__tablename__` in `db.py`, plus `created_courses`
(`course_builder.py:1771`), `unit_grades` (`assessment_book.py:196`),
`perspective_reviews` (`perspectives.py:106`), `measurement_probes`
(`measurement/models.py:55`). Boards are **files**, not tables.

Core rows and the invariant each carries:

| Table | Invariant |
|---|---|
| `users` | `role` (learner/teacher/staff/admin), `status`, `cohort_id`, `deleted_at` |
| `learning_states` | `UNIQUE(user_id, concept_id)`; `data` JSON holds mastery + DSR + due |
| `attempts` | must reference `receipts.id`; `payload_hash` prevents post-hoc editing |
| `assessments` | `mode`, `delay_days` (7d/28d transfer) |
| `consent_ledger` | `kind ∈ {telemetry, training, marketing, research, terms, privacy}` |
| `auth_tokens` / `tokens` / `refresh_tokens` | **digest only**, never the token |
| `projects` | `UNIQUE(user_id, concept_id)`; submission, feedback, `ai_disclosure`, reflection |

**Isolation.** Every user-scoped query is keyed by `user.id` from the authenticated
principal. Cross-account reads return 404, not 403 — presence is not leaked. The E2E
gate asserts exactly this ("cross-account deck is refused", 404).

**Migration policy.** Startup **never** migrates: `create_app` raises
`RuntimeError('Schema upgrade required; run scripts/init_db.py explicitly…')` on a
missing or mismatched `schema_version` (`main.py:749-754`). `backend/scripts/init_db.py`
adds columns one by one (`ADDED_COLUMNS`), takes an online backup first, and refuses a
half-migrated database whose schema is ahead of its version stamp.

**Engines.** SQLite default (`<data_dir>/harness.sqlite3`, `WAL`,
`busy_timeout=30000`, `foreign_keys=ON`). PostgreSQL via `HARNESS_DATABASE_URL`, with
`pool_size=10, max_overflow=20, pool_recycle=1800`, and per-connection
`statement_timeout=15000`. **Production refuses anything but PostgreSQL**
(`config.py:248-250`).

---

## 8. Technology stack

| Layer | Choice | Version / evidence |
|---|---|---|
| API framework | FastAPI, app **factory** | `fastapi==0.143.0`; `docs_url/redoc_url/openapi_url = None` (`main.py:789`) |
| ASGI server | uvicorn | `uvicorn[standard]==0.54.0`; `--factory --no-access-log --proxy-headers` |
| Python | CPython **3.12** shipping baseline | `backend/Dockerfile:1` `python:3.12-slim`; CI also runs 3.13 |
| ORM | SQLAlchemy 2.x typed | `SQLAlchemy==2.1.4` |
| Validation | Pydantic 2 | `pydantic==2.14.0` |
| HTTP client | httpx | `httpx==0.28.1`, `trust_env=False` |
| Hashing | argon2 | `argon2-cffi==25.1.0` |
| Numerics / images | numpy, Pillow | `numpy==2.5.3`, `Pillow==13.0.0` |
| Documents | python-pptx, pypdf | `python-pptx==1.0.2`, `pypdf==6.21.4` |
| Web search | ddgs | `ddgs==9.16.0` |
| Uploads | python-multipart | `python-multipart==0.0.31` |
| PostgreSQL driver | psycopg 3 (optional) | `psycopg[binary]==3.3.8` |
| Browser automation | Playwright (optional, teacher-only) | `playwright==1.62.0`; excluded from the shipped bundle |
| Native app | **SwiftUI + AppKit, SwiftPM** | `swift-tools-version: 6.0`, language mode `.v5`, `platforms: [.macOS(.v14)]` |
| Native deps | **none** | no `dependencies:` in `Package.swift` |
| Web workbench | vanilla JS/CSS | no `package.json`, no bundler, no build step |
| Containers | docker compose | `postgres:17-alpine`, `ollama/ollama:0.40.16`, API image from `backend/Dockerfile` |
| Packaging | PyInstaller onedir + codesign/notarytool | `scripts/package.py:724` (`--onedir --target-architecture arm64`) |

Scale, for orientation: backend `app/` ≈ 180 `.py` files / ~84k lines (`main.py` alone
4,527); native 76 `.swift` files / ~27k lines; web 8 files / ~3.5k lines.

**Route surface.** `main.py` declares 131 handlers inline; 18 feature-router modules are
dynamically imported (`app/feature_routers.py:27-61`). `scripts/api_surface.py` reports
**226 route registrations** (see `docs/architecture/INDEX.md`). Because routers are
imported by name, `package.py` must emit each as a `--hidden-import`; the comment at
`main.py:4508-4515` records the incident where a frozen build silently shipped with no
feature routes.

**Request hardening** (`main.py:793-906`): `TrustedHostMiddleware`; body cap 128 KiB
default, raised per path (`/agent/chat` and `/boards/import` 16 MiB, `/images/paste`
17 MiB, `/create/upload` 32 MiB); 413 on overflow or on a streamed body exceeding the
cap; 415 for non-JSON writes; 400 for non-HTTPS in production; `Cache-Control: no-store`
and `X-Content-Type-Options: nosniff` on responses; a 2xx that carried credentials but
resolved to no principal is rewritten to 401.

---

## 9. Voice and media

**TTS** (`app/harness/voice.py`) goes to a local VoiceStudio on
`http://127.0.0.1:3900`, OpenAI-compatible `POST /v1/audio/speech`, returning **MP3
bytes**. Because a paragraph costs 20–40 s, `speech.request` returns a `pending`
descriptor immediately, renders on a daemon thread, and the client polls
`GET /api/v1/media/audio/{digest}` (404 while rendering, 200 with bytes). The cache key
covers model + voice + speed + instruct + text and **excludes learner identity**, so one
learner's clip is not a covert per-user profile.

**ASR** (`voice.py`, `voice_ws.py`) prefers streaming: a hand-written ~180-line RFC 6455
client, `?pcm=1&sr=16000`, `s16le` mono 16 kHz, 640 bytes (20 ms) per frame, ≤ 30 s,
and reports `transport: 'stream'` plus `latency_ms`. Batch HTTP
`/v1/audio/transcriptions` (whisper-1) remains the declared fallback and reports
`transport: 'batch'`. Writing the socket client by hand was a deliberate trade: `httpx`
cannot upgrade, and adding `websockets` would add a dependency to the shipped bundle.

**Media pipelines** all pass one gate:

| Pipeline | Behaviour |
|---|---|
| `media.py` (images) | search ≠ fetch; licence travels with the asset; unknown licence refused; precision floor (width / aspect / token overlap); an offline answer is a first-class result; providers `openverse`, `wikimedia`, `met`, `nasa`; cache under `<data_dir>/media/images` |
| `video.py` | **EMBED_ONLY**: never downloads, re-encodes, re-hosts, fetches captions or transcripts, or sends any part to a model; `youtube-nocookie.com`; NC sources withheld when `HARNESS_COMMERCIAL_USE=1` |
| `presentation.py` | NotebookLM-style single narrator, audio-led: script → audio duration → page splits; exports deck/script/timeline/html/vtt; **no image-model generation** — a figure is a symbolic-engine output, a licence-cleared photograph with attribution, or a provider simulation |

`assert_extraction_allowed` exists so that a future caller must argue with a named
refusal rather than quietly adding the fourth thing.

---

## 10. Board (shared canvas)

`app/harness/board.py` (950 lines). One **JSON file per board** under
`<data_dir>/boards/`, plus append-only `manifest.jsonl` (audit) and `shares.jsonl`
(share tokens). Nine node kinds:
`path, shape, connector, text, image, video, simulation, answer, visual`.

- **Server owns identity.** `id = f'n-{secrets.token_hex(5)}'` and `z = top_z(nodes)`
  are assigned server-side; the client sends *ordering intent*, never an index.
- **Z-order = base-62 fractional fixed point** (`_ALPHABET`, `:53`; `between`, `:107`).
  A z string is the digit expansion of a value in (0,1); `''` is zero; trailing zeros are
  stripped. Alphabet is ASCII-ascending, so **string sort == numeric sort** in both
  Python and Swift. Midpoint insertion is integer arithmetic at
  `max(len)+8` precision; `_renumber()` re-spaces at `62^6` when a gap is exhausted.
- **Concurrency = optimistic, version-based.** `apply_mutations` holds a per-board
  `threading.Lock`, checks `base_version`, and returns 409 with `X-Board-Version` on a
  stale write (`main.py:3316-3331`). Batch limits: `MAX_MUTATIONS = 128`,
  `MAX_NODES = 800`. `update` cannot rewrite server facts (`status`, `sha256`,
  `embed_url`, `src`, `url`, `provider`, `integration`, `licence_class`).
- **Export.** Server: `svg | lesson` only (`main.py:3341`). PNG and PDF are produced on
  the **client** by `BoardRenderer` (`Board.swift:581`, `NSBitmapImageRep` at
  `scale = 2`; `CGContext` PDF). Embedded video/simulation is drawn as a labelled chip,
  never a frame grab — a rasterised embed would be an unlicensed redistribution posing
  as a preview.
- **Sharing.** Only `sha256(token)` is stored; TTL 1–30 days; each resolve recomputes
  the snapshot and the licence rollup.

---

## 11. Honest limits

Architecture decisions worth knowing before extending:

1. **Two "memory" modules.** `app/memory.py` = FSRS DSR scheduling.
   `app/harness/memory.py` = learner-note confidence decay. Same word, different models.
2. **Two loops, one impostor.** `agent_loop.run_agent` iterates. `loop.plan` does not —
   it is a single argmax. The lesson sequence is a state machine in `procedure_service`.
3. **BKT constants are duplicated.** Runtime `guess = 0.25`; `ml/bkt.py` uses `0.20`.
   Mastery figures from an offline BKT fit are therefore not directly comparable.
4. **53 registered / 52 available.** `browser_snapshot` needs Playwright, which the
   shipped bundle excludes.
5. **`INDEX.md` links a missing `ARCHITECTURE.md`** — this document fills that gap.
6. **PNG/PDF are client-side.** Any doc that says the server exports PNG/PDF is wrong.
7. **Not notarized by default.** `package.py` is ad-hoc signed by default and says so;
   public distribution needs a Developer ID and notarization.
8. **Board duplicate helper.** `board.py:166` and `:192` define `_z_between_neighbors`
   twice; the latter shadows the former and lacks the renumber fallback, making the
   "insert between exhausted neighbours" renumber branch unreachable.

None of the above changes the shipped behaviour; each is a place where the next engineer
would otherwise lose an afternoon.

---

## 12. File map

```
backend/app/
├── main.py                     app factory, 131 inline routes, prompt assembly, post-processing
├── db.py                       41-table model, SCHEMA_VERSION = 11
├── learning.py                 mastery update, grading support, diagnosis, recommendation
├── memory.py                   FSRS-6 DSR scheduler
├── course_builder.py           intake validation, concept extraction, persistence
├── assessment_book.py          unit grade book (0.70 bar)
├── simulation_map.py           overlap-coefficient matching (0.34 floor)
├── ingest/policy.py            10 licence classes, INGESTIBLE set, fail-closed
├── measurement/                probes, estimators, contracts, bench
├── api/v1/account.py           first relocated route family
├── routes_*.py                 deck, flash, create, authoring, media, multimodal, source,
│                               procedure, supervision, rewards, ta, stream, whiteboard_agent,
│                               model_config, measurement, mindmap, live, web
└── harness/
    ├── agent_loop.py           run_agent (8/24 steps, 7 event types)
    ├── provider.py             chat / chat_tools, Ollama /v1 rule
    ├── toolbox.py              53 tools, invoke gate, identifier grounding
    ├── loop.py                 9-move scorer (one-shot)
    ├── teaching/procedure.py   compile_procedure, activity vocabulary
    ├── teaching/surface.py     surface ownership + switch rules
    ├── board.py                node document, base-62 z, version 409
    ├── memory.py               learner-note decay (21 d half-life)
    ├── voice.py / voice_ws.py  TTS clips, streaming ASR
    └── media.py / video.py / presentation.py

native/Sources/LearningHarness/
├── Shared/{Models,Networking,Persistence,State}/    AppStore(+7 domain extensions)
├── Features/Board/                                   BoardEditor + 12 companions
├── Board.swift                                        BoardStore + BoardRenderer (PNG/PDF)
├── CanvasView.swift / PerfectFreehand.swift           ink layer + stroke outline
├── BackendLauncher.swift                              spawns frozen backend, schema check
└── Voice.swift / VoiceRealtime.swift                  offline speech + OpenAI Realtime

web/                            vanilla JS workbench (no build)
deploy/compose.yaml             postgres + migrate + api (+ ollama profile)
scripts/package.py              PyInstaller onedir, codesign, notarytool
```

---

**How to check this document.** Every constant above can be re-read with
`grep -n` on the cited file. The counts (53 tools, 41 tables, 226 routes, 37+4 models)
are reproducible from `toolbox.REGISTRY`, `db.__tablename__`, and
`backend/scripts/api_surface.py`. If a number here disagrees with the code, the code wins.
