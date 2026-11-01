# Tutor model and voice: final configuration procedures

Operator-facing. This document is the **procedure** for switching the tutor from the
default testing model to a production vision model, and the reference for the voice
backend that ships today. Voice output is **already switched on** in the sense that
matters: `text_to_speech` talks to a local [VoiceStudio](https://github.com/debpalash/VoiceStudio)
backend, and the only thing an operator has to do is have that backend running. Sections
1–2 are still procedures; section 3 is now configuration, not a plan.

Everything is an environment variable read once by `Settings.from_env()`
(`app/config.py`), so a change needs an API restart and no code change. Two settings
are the whole model surface:

| Setting | Env var | Meaning |
|---|---|---|
| Provider kind | `HARNESS_TUTOR_PROVIDER` | `offline` (default), `ollama`, or `openai` (any OpenAI-compatible endpoint, including DeepSeek). |
| Endpoint | `HARNESS_TUTOR_URL` | Base URL. The provider appends `/chat/completions`. Must be a valid `https://` URL. |
| Model | `HARNESS_TUTOR_MODEL` | Required whenever the provider is not `offline`. |
| Key | `HARNESS_TUTOR_KEY` | Bearer token. May instead be supplied as `DEEPSEEK_API_KEY` in `backend/.env`. |
| Timeout | `HARNESS_TUTOR_TIMEOUT_SECONDS` | Default `12`. Raise to `300` for long agentic generations. |

---

## 1. The current default: DeepSeek-V4.1-Flash (testing)

The harness ships pointed at `offline` — a fully deterministic local content generator,
which is a complete product, not a degraded placeholder. For **testing**, the intended
override is DeepSeek-V4.1-Flash, whose model id on the wire is `deepseek-flash`:

```dotenv
# backend/.env  (real environment variables always win over this file)
HARNESS_TUTOR_PROVIDER=openai
HARNESS_TUTOR_URL=https://api.deepseek.com
HARNESS_TUTOR_MODEL=deepseek-flash
DEEPSEEK_API_KEY=sk-...            # alias for HARNESS_TUTOR_KEY
HARNESS_TUTOR_TIMEOUT_SECONDS=60
```

Notes verified against the live endpoint:

- **Base URL.** `https://api.deepseek.com` is correct. `https://api.deepseek.com/v1`
  also resolves (the provider appends `/chat/completions`, and DeepSeek accepts both the
  `/v1` and root forms). Prefer the bare host.
- **Model ids.** `GET /models` on this key returns exactly two:
  - `deepseek-flash` → **DeepSeek-V4.1-Flash**, `context_window` 1,048,576,
    `max_output_tokens` 393,216, **`input_modalities: ["text","image"]`**.
  - `deepseek-v4-pro` → **DeepSeek-V4-Pro**, same window, **`input_modalities:
    ["text"]`** (no image input).
  - The legacy id `deepseek-v4-flash` is retired but still accepted by the service and
    routed to V4.1-Flash. Use `deepseek-flash` in new configuration.
- **Live smoke test.** With the key exported:

  ```bash
  HARNESS_LIVE_SMOKE=1 \
  HARNESS_TUTOR_PROVIDER=openai \
  HARNESS_TUTOR_URL=https://api.deepseek.com \
  HARNESS_TUTOR_MODEL=deepseek-flash \
  HARNESS_TUTOR_KEY=sk-... \
  pytest -q backend/tests/test_live_smoke.py
  ```

  This is the only test that touches the network; the rest of the suite runs against
  fakes. It is skipped unless `HARNESS_LIVE_SMOKE=1`.

### Account balance: resolved, and how to re-check it

The supplied testing key used to authenticate and then fail every completion with:

```
HTTP 402  {"error":{"message":"Insufficient Balance", ...}}
```

That was a billing state, not a configuration error, and it is **no longer true**. On
2026-10-22 the same key returned `200` for `GET /models`, for an image completion (a 1x1
PNG, answered "Black") and for a tool-calling completion (`tool_calls: [speak]`). The
harness had been designed so that nothing depended on the model being reachable:
`provider.chat` and `provider.chat_tools` never raise, they return `None` on any failure,
and every caller already has an offline path. That design is still the contract — the
account is funded today, and a lapsed key must degrade to the deterministic content
rather than break a lesson. To re-check a key, run the live smoke test above and expect a
typed tool call plus `total_tokens > 0`.

---

## 2. The vision model (implemented and verified 2026-10-22)

This section used to be a procedure for a capability that did not exist. It now records a
capability that does: `deepseek-flash` accepts image input, the agent loop can act on what
it sees, and both were verified against the live endpoint. `docs/vla.md` is the full
contract — model cards, the see-act-see mechanism, the two vision tools, on-task
monitoring, and the measured token-budget trap. What follows is the short version.

The steps, in order:

1. **Confirm the target declares image input.** `GET {HARNESS_TUTOR_URL}/models` and
   read `input_modalities`. `deepseek-flash` lists `image`; `deepseek-v4-pro` does not,
   and the harness refuses to send it a picture rather than accept an invention.

2. **Point the settings at it.** Either keep `deepseek-flash` (already image-capable) or
   change the two variables:

   ```dotenv
   HARNESS_TUTOR_PROVIDER=openai
   HARNESS_TUTOR_URL=https://<vision-endpoint>       # any OpenAI-compatible VLM
   HARNESS_TUTOR_MODEL=<vision-model-id>
   HARNESS_TUTOR_KEY=...
   ```

3. **Send image content in OpenAI vision format.** `provider.chat` serialises the
   `messages` list straight to JSON, so a message whose `content` is a *list of parts*
   passes through unchanged even though the type hint says `str`. `app/harness/vla.py`
   is the module that builds that shape; do not hand-roll it at a call site, because the
   validation (magic bytes, size cap, data-URL-only) lives there.

   ```python
   {'role': 'user', 'content': [
       {'type': 'text', 'text': 'What is wrong with this worked step?'},
       {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,...'}},
   ]}
   ```

   A model can also acquire an image *during* a turn: `look_at_image` returns it in
   `ToolResult.images`, and `agent_loop` re-injects it as a user message with image parts
   before the next step. That is the see-act-see path, and it is why the loop is a VLA
   rather than a chain of text calls.

4. **Raise the timeout** for image-heavy or long agentic turns:
   `HARNESS_TUTOR_TIMEOUT_SECONDS=120` (max 300).

5. **Do not lower the observation token budget.** At `max_tokens=40` a live vision call
   returned `200 OK` with **empty content**, because V4.1-Flash spends the budget on
   `reasoning_tokens` first (a one-word answer cost 171). `vla.OBSERVE_MAX_TOKENS` is
   1500 for that reason; a smaller cap looks like a provider fault.

6. **Re-run the tests**:

   ```bash
   pytest -q backend/tests/test_vla.py backend/tests/test_agent_loop.py \
             backend/tests/test_capabilities.py
   ```

### Invariants that must not be weakened when the model changes

- **Never-raise fallback.** Every provider call returns `None` on failure and the caller
  degrades to deterministic offline content. Do not add a code path that assumes the
  model answered.
- **Licence gate.** A stronger model does not widen what may be ingested. Khan Academy
  stays link/embed-only; OpenStax stays LINK_ONLY; the policy gate in
  `app/ingest/policy.py` is evaluated at call time, not by memory.
- **Untrusted input blocks.** Learner text stays inside
  `<learner_message untrusted="true">`; the teacher-style profile stays inside
  `<teacher_style_profile untrusted="true">` and remains **style-only**, subordinate to
  safety and grounding. A vision model reading an image does not change this.
- **Usage metering.** `usage_out` still receives the provider's own token accounting plus
  `latency_ms` and `outcome`, so a paid tier can be metered without the provider module
  importing the database.

---

## 3. Voice output: the local VoiceStudio backend

Voice output is the `text_to_speech` tool in `app/harness/tools_creation.py`. It calls
**VoiceStudio** (https://github.com/debpalash/VoiceStudio), a self-hosted voice workbench
whose Python backend serves an OpenAI-compatible `POST /v1/audio/speech` on loopback.
`app/harness/voice.py` is the only module that knows that contract; nothing else in the
harness imports an HTTP client for audio.

**Why it replaced edge-tts.** The previous provider was the `edge-tts` library calling
Microsoft's public speech endpoint. Every utterance left the machine carrying the
learner's text to a third party, and a lesson could not speak with the network down.
VoiceStudio runs on the operator's own machine, so the audio path is local. That is the
whole reason for the swap, and it is the property to preserve if the provider changes
again: **learner text must not leave the host to be spoken.**

### 3.1 Start the backend first

The harness does not start VoiceStudio for you. Install it and leave it running:

```bash
curl -fsSL https://voicestudio.sh/install | sh     # or build from the repo, or run the desktop app
```

A stock install listens on `http://127.0.0.1:3900`. Confirm it before blaming the harness:

```bash
curl -s http://127.0.0.1:3900/.well-known/voicestudio-speech   # capability document
curl -s http://127.0.0.1:3900/v1/models                        # engine ids it can serve
```

The readiness probe in `app/capabilities.py` (`tts_service`) tries the discovery document
first and falls back to `/v1/models`, because the discovery document is newer than the
speech endpoint and an older build 404s it. If neither answers, the `audio_tts` capability
reports `degraded` with the sentence that says so.

Two operational facts that will otherwise look like harness bugs:

- **The port is the backend's, not ours.** VoiceStudio's own variable is `OMNIVOICE_PORT`
  (default `3900`); its docs describe the API as "HTTP `:3900`" and the discovery document
  as returning `voicestudio.speech.v1`. If the operator moved it, set
  `HARNESS_VOICE_BASE_URL` to match — do not edit code.
- **First use downloads a model.** A fresh install has no speech model until one is
  installed in the app (OmniVoice is the default engine). Until then synthesis fails as
  `model_missing`, which is the correct answer, not a fault. Budget the download and a
  first cold run before deciding the timeout is too short; on Apple Silicon the backend
  uses Metal (MPS), on CPU-only hosts it is markedly slower and
  `HARNESS_VOICE_TIMEOUT_SECONDS` may need raising. **On this machine OmniVoice and
  Kokoro-82M are already installed**, and a warm OmniVoice request takes roughly 20–40 s
  of wall time for a 7 s utterance, which is why the configured timeout is 180.

### 3.2 Settings

All five are read once by `Settings.from_env()`; a change needs an API restart.

| Setting | Env var | Default | Meaning |
|---|---|---|---|
| Base URL | `HARNESS_VOICE_BASE_URL` | `http://127.0.0.1:3900` | Where the backend listens. Must be `http(s)` with a host; a URL with embedded credentials is **rejected at startup** — use the key setting instead. |
| Engine | `HARNESS_VOICE_MODEL` | `omnivoice` | VoiceStudio engine id. `omnivoice`, `voxcpm2`, `cosyvoice`, `mlx-audio`, `kittentts`, `moss-tts-nano`; OpenAI model ids are accepted as aliases. |
| Voice | `HARNESS_VOICE_NAME` | `default` | A voice-profile name or id. `default` means the engine's own default. |
| Key | `HARNESS_VOICE_API_KEY` | empty | Sent as `Authorization: Bearer …`. **A loopback client needs no credential** — the route does not check one, and VoiceStudio's own docs say so explicitly. This exists so the same setting keeps working when the backend is fronted by a proxy or reached remotely; the server-side counterpart is VoiceStudio's `OMNIVOICE_API_KEY`. |
| Timeout | `HARNESS_VOICE_TIMEOUT_SECONDS` | `120` | 5–600. Long on purpose: a cold model on CPU can take a minute for a paragraph, and the 12 s media timeout would abort a healthy synthesis. |
| Tone | `HARNESS_VOICE_INSTRUCT` | empty | Default delivery instruction for every synthesis, sent as OpenAI `instructions`. What an engine can honour varies — see §3.4. Empty sends nothing, which is the honest default for a stock install. |

`HARNESS_MEDIA_ENABLED=1` is also required: voice output is gated off unless the
instance opts in, and the refusal says so by name.

```dotenv
# backend/.env — only needed when the defaults are wrong
HARNESS_VOICE_BASE_URL=http://127.0.0.1:3900
HARNESS_VOICE_MODEL=omnivoice
HARNESS_VOICE_NAME=default
HARNESS_VOICE_TIMEOUT_SECONDS=120
```

The client is built with `trust_env=False`, so `HTTP_PROXY`/`HTTPS_PROXY` in the shell
cannot silently redirect a loopback call to a proxy.

### 3.3 What the tool sends

`text_to_speech(text, voice='', rate='')` maps onto the `SpeechRequest` schema:

| Tool argument | Request field | Notes |
|---|---|---|
| `text` | `input` | Whitespace-collapsed; capped at **4096** characters, the schema's own `max_length`. Over the cap is a refusal before any network call. |
| `voice` | `voice` | An edge-tts voice name (`en-US-AriaNeural`) does **not** exist in VoiceStudio. It is replaced by the configured default **and the substitution is stated in a note** — silently passing it through would either 400 or produce the default voice while the caller believes it asked for Aria. |
| `rate` | `speed` | edge-tts took `'+25%'`; VoiceStudio takes a multiplier `0.25`–`4.0`. `'+25%'` → `1.25`, `'-10%'` → `0.9`. Out-of-range values are **clamped with a note** rather than becoming a 400; unparseable ones are refused as `bad_rate`. |
| — | `model` | `HARNESS_VOICE_MODEL`. |
| — | `response_format` | `mp3`. |
| — | `format` in the result | `mp3`; the cache path is always `.mp3`. |

Audio is cached by content digest — `sha256(model, voice, speed, tone, text)` — under
`data/media/audio/<digest>.mp3`, so the same passage is synthesised once. **A repeat is
served from disk without touching the backend** (`cached: true`, plus a note saying so),
which matters because a warm OmniVoice request costs 20–40 s. The tone is part of the key:
without it, asking for a different delivery would hand back the previous recording. It is
written through a sibling `.mp3.part` file and then `replace()`d: a crash mid-write must
not leave a truncated `.mp3` that looks like a cache hit on the next call. The cache key is
content, not learner, so a shared instance cannot leak one learner's audio to another.

`HARNESS_MEDIA_ENABLED` still gates synthesis, but its meaning changed. It used to mean
"this instance may make outbound calls"; the call is now loopback, so that reading is
false. It is kept as the operator's "this instance may produce audio at all" product
decision, and the refusal text says **"voice output is switched off"** rather than "the
network is off", because the second is no longer true.

### 3.4 Making it sound like a teacher

`tone` on the tool, and `HARNESS_VOICE_INSTRUCT` for the default, are a delivery
instruction: sent as OpenAI's `instructions`, which the backend forwards to the engine as
its own `instruct`. The teacher narration path (`teaching/modalities.py`) passes text
only, so the configured default is what gives it a voice.

**Two engines are installed on this machine and they are not interchangeable:**

| Engine | Model | Languages verified here | Tone control |
|---|---|---|---|
| `omnivoice` | k2-fsa/OmniVoice, 2.4 GB | Chinese **and** English (round-trip exact) | speaker-design tags only |
| `mlx-audio` | Kokoro-82M-bf16, 0.15 GB | English (exact); **Chinese mangled** | voice presets |

Measured with median F0 (autocorrelation over voiced frames) on the same Chinese
sentence, so "did the tone do anything" is a number rather than a hope:

| Instruction | Median F0 | Reading |
|---|---|---|
| *(none — engine default)* | 134 Hz / 175 Hz | **not stable** — two runs, identical input |
| `female, young adult, moderate pitch` | 305 Hz | high female |
| `female, middle-aged, low pitch` | **239 Hz** | **adult female — the shipped default** |
| `male, elderly, low pitch` | 167 Hz | lower male |

Two conclusions, and one caveat:

- **Tags work and are repeatable.** The male tag sets landed at 167–188 Hz across runs,
  the configured female set at 229–239 Hz. A 70 Hz shift from a text field is a real
  change in the voice, not a re-render.
- **An untagged request is not stable.** The same input measured 134 Hz and 175 Hz on two
  runs, i.e. the engine picks a voice when it is not told which. That is the practical
  reason to configure a tag list: a teacher who sounds like a different person every
  lesson is worse than one with a plain voice.
- F0 on a single short sentence is a noisy statistic. Treat these as direction, not as a
  voice fingerprint — the configured voice and the untagged default both round-tripped
  through ASR back to the exact input sentence, which is the property that actually
  matters.

**What OmniVoice cannot do.** Its instruction is a closed vocabulary of speaker-design
tags (gender, age, pitch, whisper, accent, dialect). Prose such as *"a warm, encouraging
teacher"* is **dropped with a 200**: the engine speaks in its default voice and reports
success. `voice.resolve_instruct` mirrors that vocabulary, so the tool sends only the tags
that will be honoured, explains the reduction in a note, and reports `tone: ''` when
nothing survives — it never claims a tone the audio does not have. Two consequences worth
stating plainly:

- **No engine available here advertises emotion control.** All four report
  `supports_emotion: false`, so "tone" in this install means *voice character and pacing*,
  not acted emotion. `indextts2` is the only engine in the catalogue that advertises
  emotion, and it is not installed.
- **Chinese needs no language hint.** OmniVoice detects it; the round-trip above was
  produced with no `language` field, which is what the harness sends.

Kokoro is the faster English option — about 8 s wall for 6.9 s of audio once warm — but it
produced unintelligible Chinese here (`中文字幕组` from a 35-character sentence, and 20 s
of audio for a sentence that should take ~7 s). Do not point a Chinese lesson at it. It
also accepts `instructions` without error and ignores it (its voice comes from the preset
name), so leave `HARNESS_VOICE_INSTRUCT` empty on a Kokoro run rather than have the result
report a tone the audio does not carry.

### 3.5 Every failure is named

A local service can be missing, still loading a model, waiting for a licence, or busy on a
GPU. Each has a different fix, so each gets its own code and its own sentence. None of
them writes a file, and none returns silence that looks like success.

| `VoiceError.code` | Cause | Reported as | Fix |
|---|---|---|---|
| `not_running` | Connection refused | `refused` | Start VoiceStudio, or set `HARNESS_VOICE_BASE_URL`. |
| `model_missing` | 400 naming the model | `refused` | Install the engine in the app, or change `HARNESS_VOICE_MODEL`. |
| `licence_not_accepted` | 403 | `refused` | Open VoiceStudio and accept the model licence. |
| `too_long` / `empty_text` / `bad_rate` | Caller error | `refused` | Split the passage / supply text / pass a multiplier. |
| `ambiguous_voice` | 409 | `error` | The name matches several profiles; use the profile **id**. |
| `busy` | 429 (honours `Retry-After`) | `error`, retryable | Wait; the GPU pool is full. |
| `engine_failed` | 500/502/503/504 | `error`, retryable | A model may still be loading, or the engine crashed. |
| `timeout` | Read timeout | `error`, retryable | Raise `HARNESS_VOICE_TIMEOUT_SECONDS`, or warm the model in the app. |
| `bad_response` | 200 whose body is not audio | `error` | Something between the harness and VoiceStudio answered — a proxy error page, a JSON error. |

`refused` means *the operator can fix this without a code change*; `error` means a fault.
The distinction is deliberate: a missing backend is not a bug report.

**The `bad_response` check is not defensive padding.** Without it a 200 carrying an error
page is written to `.mp3`, producing a file that exists, is non-empty, and will not play —
the failure mode that costs the most time to diagnose, because every size check passes.

Presentation constraint to preserve: the deck/audio overview path in
`app/harness/presentation.py` is deliberately a **single narrator** (not the two-host
dialogue of an audio overview). A new voice provider must keep that single-voice shape.

---

## 4. What is deliberately *not* configured

- No `HARNESS_MULTIMODALITY` master flag exists, and none should be added: each
  capability has its own provider, cost and fallback. See `multimodality.md`.
- `HARNESS_VOICE_*` configures **one** provider: the local VoiceStudio backend. There is
  no `HARNESS_VOICE_PROVIDER` switch and no cloud/Gemini branch. A second provider means a
  new module beside `voice.py` with its own contract, not a branch inside it — and it has
  to answer the same question the swap to VoiceStudio answered: does learner text leave
  the host to be spoken?
- The tutor provider stays `offline` until an operator sets the variables above.
