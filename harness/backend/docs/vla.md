# The VLA layer: seeing, acting, speaking, and reading the room

Operator-facing. This is the contract for the five things the tutor model does beyond
writing prose: **see** an image, **act** on it with tools, **make a deck**, **speak**,
and **read whether the learner is on task**. It records what is wired, what is verified
against the live endpoint, and what is deliberately not built.

The short version: all five are implemented, and the two that need the model were verified
against `https://api.deepseek.com` on **2026-10-22** with this account's key.

---

## 1. "VLA", precisely

A VLM describes a picture. A **VLA** (vision-language-**action**) takes actions based on
what it sees. The difference is not a rebrand; it is a property of the loop, and it needs
three things that a chat completion does not give you:

| Piece | Where it lives | What it does |
|---|---|---|
| **Model card** | `app/harness/vla.py` → `MODELS` | Answers "does this model accept an image, and can it call tools?" from recorded facts, not from the model's name. |
| **Eyes** | `vla.observe`, `vla.read_json` | One vision call about one or more images, returning text or parsed JSON plus the digest of each image. |
| **See → act → see** | `agent_loop.run_agent` | A tool that returns an image has it re-injected as a `user` message with image parts before the next step, because OpenAI's `role: 'tool'` message is text-only. |

That third row is the one that is easy to miss and the one that matters. Without it the
model is told "the screenshot shows a mistake" by a tool and cannot check; with it, the
model looks at the actual pixels and decides the next action.

The loop stays single. There is no second agent loop beside `agent_loop`; the vision path
is a message the existing loop appends. `EVENT_TYPES` gains exactly one entry,
`observation`, emitted only when an image was re-injected.

## 2. The model, and why the id matters

`GET {HARNESS_TUTOR_URL}/models` on this account returns two ids:

| Wire id | Display | Context | Max output | `input_modalities` | Tools |
|---|---|---|---|---|---|
| `deepseek-flash` | DeepSeek-V4.1-Flash | 1,048,576 | 393,216 | `text`, `image` | yes |
| `deepseek-v4-pro` | DeepSeek-V4-Pro | 1,048,576 | 393,216 | `text` | yes |

**`deepseek-flash` is the VLA; `deepseek-v4-pro` is not.** It can act but it cannot see,
and the harness refuses to send it an image rather than accept a fluent invention. The
build label operators use in conversation — "V4.1-Flash-1047" — resolves to the same wire
id; `vla.model_card` accepts these aliases:

```
deepseek-flash  deepseek-v4.1-flash  deepseek-v4.1-flash-1047
deepseek-flash-1047  deepseek-v4-flash        (retired id, still routed)
```

An unknown model id is treated as **blind** until an operator vouches for it with
`HARNESS_TUTOR_VISION=1`. That default is deliberate: sending an image to a text endpoint
produces a confident description of nothing, which is worse than a refusal.

### Configuration

```dotenv
# backend/.env
HARNESS_TUTOR_PROVIDER=openai
HARNESS_TUTOR_URL=https://api.deepseek.com        # DEEPSEEK_BASE_URL also works
HARNESS_TUTOR_MODEL=deepseek-flash                # the VLA
HARNESS_TUTOR_KEY=sk-...                          # or DEEPSEEK_API_KEY
HARNESS_TUTOR_TIMEOUT_SECONDS=240                 # reasoning turns are slow
HARNESS_ATTENTION_MONITOR=1                       # on-task reading (section 5)
```

`/api/v1/harness/status` reports the posture under `vla`:

```json
{"vla": {"model": {"id": "deepseek-flash", "vision": true, "action": true, "vla": true},
         "vision": {"ready": true, "note": "DeepSeek-V4.1-Flash accepts image input."},
         "action": {"ready": true}, "vla": true}}
```

### Verified, not assumed

Run 2026-10-22 against this key:

```
GET  /models                         200   deepseek-flash: image + text, 1,048,576 ctx
POST /chat/completions (1x1 PNG)     200   content "Black"  (the pixel is black)
POST /chat/completions (tools)       200   tool_calls [speak {"text": "The denominator names the unit."}]
```

**One measured trap.** At `max_tokens=40` the vision call returned **200 OK with empty
content** and `finish_reason: stop` — the whole budget went to `reasoning_tokens`. A
one-word answer cost **171** completion tokens. `vla.OBSERVE_MAX_TOKENS` is therefore
1500, and a caller that lowers it will get silent emptiness that looks like a provider
fault. This is the single most likely cause of "the vision tool does nothing".

## 3. What an image may be

| Input | Accepted | Why |
|---|---|---|
| `data:image/(png\|jpeg\|webp);base64,…` | yes, ≤ 2 MB decoded | Self-contained; nothing is fetched. |
| Path inside the learner's own workspace | yes | Containment is `sandbox.Workspace.resolve`, the one place that decides what a path reaches. |
| An `http(s)://` URL | **refused** | Otherwise a model could make the server fetch an address of its choosing. |
| A path outside the workspace | **refused** | `..`, absolute paths and `~` are rejected by the workspace, not by this layer. |

The format is decided by **magic bytes**, never by the extension or the declared MIME: a
`.jpg` that is really a PNG is labelled PNG and accepted, and a 12 MB phone photo is
refused with the limit in the sentence instead of a provider timeout.

Four images per observation (`vla.MAX_IMAGES`). Six pictures in one question is a question
answered about none of them.

## 4. The tools

| Tool | Posture | What it does |
|---|---|---|
| `look_at_image(source, question="")` | personal | With no question: **attaches** the image so the model looks itself. With a question: one vision call answers it as text and the picture stays out of context. |
| `check_on_task(task, snapshot="", signals={})` | personal | The on-task reading (section 5). |
| `text_to_speech(text, voice, rate, tone)` | internal | Speaks through the local VoiceStudio backend (section 6). |
| `generate_slides(title, sections, concept_id)` | internal | The deck, HTML plus a real `.pptx` (section 7). |

The observer prompt (`vla.OBSERVER_SYSTEM`) forbids naming or identifying a person and
forbids stating age, identity or emotion as fact. It also forbids describing anything
outside the question, even if it is legible in the frame. That rule exists because the
same primitive powers the on-task check, where the subject is a learner.

## 5. Monitoring whether the student is on task

`app/harness/attention.py`. Read that module's docstring before changing anything here;
it states the design as a refusal of a worse product.

**What it is.** A reading assembled from signals the client already has — idle seconds,
hidden-window seconds, blur events, attempts — plus, when the learner has opted in and a
snapshot exists, a check of the **work in the frame**. The output is a state
(`on_task` / `drifting` / `off_task` / `unclear`), its evidence, a confidence, and a
teaching move.

**What it is not.** A camera pointed at a child, frames uploaded, a score written to a
record. It does not identify anyone, does not grade, and has no punitive branch: every
`suggested_action` is something a teacher does next (ask a question, shrink the step,
offer a break). There is no code path that reports, flags or blocks.

Rules that are enforced in code, not in prose:

* **Opt-in.** `HARNESS_ATTENTION_MONITOR=0` (the production default) makes the tool and
  the route refuse, naming the switch. Never a silent no-op.
* **Frames are not stored.** The snapshot is read inside the request. What returns — and
  all a caller may keep — is the state, the confidence, evidence sentences and image
  digests. The `privacy` block travels in the payload so a client cannot quietly keep the
  picture and claim the guarantee.
* **Disagreement is reported, not resolved.** If telemetry says `off_task` and the picture
  says `on_task` at ≥ 70 % confidence, the answer is `unclear` with both readings and a
  note. A confident wrong verdict here costs a learner their trust in the whole system.
* **Telemetry works offline.** No model, no camera, no network: the reading is still
  produced, and a note says the visual check was unavailable.

Thresholds are named constants at the top of the module (`IDLE_OFF_TASK_SECONDS = 240`,
`HIDDEN_OFF_TASK_RATIO = 0.60`, …) so a reader can disagree with one number and change it.

`POST /api/v1/attention/check` is the client-facing form:

```json
{"task": "finish question 4",
 "signals": {"idle_seconds": 400, "hidden_seconds": 20, "attempts": 0, "window_seconds": 300},
 "snapshot": "data:image/png;base64,…"}
```

→ `{"state": "off_task", "confidence": 0.85, "evidence": ["No interaction for 400 s …"],
    "suggested_action": "Pause the timer and ask one question …", "privacy": {…}}`

403 means the instance has monitoring switched off; 422 means the request itself cannot be
read. The two have different fixes.

## 6. Speaking

Unchanged by this work and already live: `text_to_speech` → `app/harness/voice.py` →
VoiceStudio's OpenAI-compatible `POST /v1/audio/speech` on loopback. Learner text does not
leave the host to be spoken; audio is cached by content digest under
`data/media/audio/<digest>.mp3`. See `provider-and-voice-setup.md` §3 for the full failure
table (`not_running`, `model_missing`, `licence_not_accepted`, `busy`, …).

The one constraint the VLA layer adds: **a spoken turn is still a single narrator**. The
deck/audio path is one voice, not a two-host dialogue. A model that decides to "make it
conversational" has broken the format.

## 7. The deck

Two paths, one of which is editable:

| Path | Entry point | Output |
|---|---|---|
| Narration-led | `build_presentation` → `app/harness/presentation.py` | Single narrator, one visual per slide, audio-led timing, WebVTT, self-contained HTML. |
| Deck twin | `generate_slides` → `tools_creation.py` | Print HTML **and** a real `.pptx` (python-pptx). |
| Editable document | `app/deck.py` + `/api/v1/decks` | A 960 × 540 pt document, exported to `.pptx` and imported back. |

The `.pptx` twin was a text dump (default 4:3 template, title-and-content layout, no title
slide). It is now a deck:

* **16:9 at 13.333 × 7.5 in** — the shape projectors and video calls share.
* **A real title slide** with the deck's subtitle, so the file does not open on "Slide 1".
* **One hierarchy**: title, accent rule, bullets, page number, source line — the same three
  positions on every slide.
* **Speaker notes carried across**, which is what makes the `.pptx` the editable twin of
  the narration rather than a screenshot of it.
* **Text that fits**: six bullets maximum, 220 characters maximum, truncated with an
  ellipsis rather than silently overflowing the box.

Quality findings (`_deck_quality`) are **notes, not refusals**: "Slide 1 has 8 bullets",
"Slide 3 has a 22-word bullet", "Slide 4 has no speaker notes". A teacher fixes one
sentence instead of regenerating the deck.

## 8. What is deliberately not built

* **No camera capture in the harness.** The client supplies a frame or it does not; the
  server never opens a device. A server-side camera is a consent problem no code can fix.
* **No face analysis, no emotion inference, no gaze estimate.** The visual question is
  about the work in the frame. The observer prompt enforces it and the on-task state has no
  branch that depends on a face.
* **No image generation in the deck path.** A synthesised picture of a concept is a
  plausible-looking wrong answer; a slide's visual is the symbolic engine's output, a
  licence-cleared photograph with attribution, or a provider-hosted simulation.
* **No second model provider inside `voice.py`.** A new TTS backend is a new module beside
  it with its own contract, not a branch inside it.
* **No `HARNESS_MULTIMODALITY` master flag.** Each capability keeps its own provider, cost
  and fallback; see `multimodality.md`.

## 9. Checks

```bash
# The VLA layer, offline, against fakes (28 tests, no network):
pytest -q backend/tests/test_vla.py

# The loop, the capability matrix and the deck:
pytest -q backend/tests/test_agent_loop.py backend/tests/test_capabilities.py \
          backend/tests/test_creation_tools.py

# The one test that touches the real endpoint, skipped unless asked:
HARNESS_LIVE_SMOKE=1 HARNESS_TUTOR_PROVIDER=openai \
HARNESS_TUTOR_URL=https://api.deepseek.com HARNESS_TUTOR_MODEL=deepseek-flash \
HARNESS_TUTOR_KEY=sk-... pytest -q backend/tests/test_live_smoke.py
```
