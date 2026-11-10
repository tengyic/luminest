# Luminfest Learning Harness — Setup & the three completed gaps

This note covers how to run the harness end‑to‑end and documents the three
capabilities that were closed out: **app‑wide click/key telemetry**, **real‑time
duplex voice**, and **a learner‑facing level**.

It is deliberately honest about scope: telemetry is coarse and consented, voice has
an offline turn‑taking path and a separate hosted duplex path (the latter is not the
backend tutor), and the level is a communication layer over an IRT ability estimate,
not a certified test.

---

## 1. Launch the backend

From the repo root:

```bash
cd harness/backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"          # or: pip install -r requirements.txt
uvicorn app.main:app --reload --port 8765
```

The client defaults to `http://127.0.0.1:8765` (`UserDefaults` key
`luminfest.endpoint`). Change it in the app's **Settings → Learning environment**.

---

## 2. Tutor LLM key (required, configured in the app)

A language model is required; there is no offline tutor mode. The customer-facing path is
**Settings → Language model**: pick a preset, enter a model id and key, save, and it is
live without a restart (`PUT /api/v1/settings/model-config`). For a headless instance the
same values come from `HARNESS_TUTOR_*`. A working, cheap starting point is DeepSeek
(aliased automatically from `DEEPSEEK_API_KEY`):

```bash
# harness/backend/.env
HARNESS_TUTOR_PROVIDER=openai
HARNESS_TUTOR_URL=https://api.deepseek.com/v1
HARNESS_TUTOR_MODEL=deepseek-v4-pro      # or deepseek-flash
HARNESS_TUTOR_KEY=sk-...
```

(The loader in `app/config.py` maps `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` onto
the `HARNESS_TUTOR_*` fields when those are unset, so a DeepSeek key alone works.)
The harness stays grounded: citations and the knowledge graph are server‑side; the
model only composes explanations.

---

## 3. Real‑time duplex voice (OpenAI Realtime)

Duplex voice is **client‑side**: the native macOS app opens a WebSocket straight
to OpenAI and holds the API key in the macOS Keychain. The backend does **not**
need a key for this to work.

**Enter the key in the app** (recommended — never leaves the device):

> Settings → **Duplex voice (OpenAI Realtime)** → paste `sk-…` → **Save key**.

The key is stored in the Keychain (`com.luminfest.learning-harness.realtime`),
shown as `KEY SAVED`, and clearable in‑app.

**Optional server proxy:** an operator may instead set `HARNESS_REALTIME_KEY`
and `HARNESS_REALTIME_MODEL` in `backend/.env`. This is only used today to
*advertise* that duplex voice is available; the native client still connects
directly. The key is never logged and never returned by any route.

Create a key at <https://platform.openai.com/api-keys>.

In the **Stage** header, the new **Voice chat** button starts/stops the session.
While connected, push‑to‑talk is suppressed (one mic capture at a time) and the
tutor can be interrupted mid‑sentence (server‑VAD barge‑in).

---

## 4. The three gaps, closed

### 4.1 App‑wide interaction telemetry
- **Backend:** `POST /events` accepts an `interaction` event. The vocabulary lives
  in `app/harness/telemetry.py`, not in the route, so the validator, the summary
  and the client‑facing description cannot drift apart: `kind` ∈
  click / tap / key / blur / focus, a target matching `[A-Za-z0-9][A-Za-z0-9._:-]{0,63}`,
  and **no other field**. `GET /api/v1/events/interactions` returns counts plus
  `is_evidence: false` and an `interpretation` string; `GET /api/v1/attention/window`
  derives real `active_seconds` from the gaps between interactions and feeds
  `app/harness/attention.telemetry()`.
- **Native:** `ClickTelemetry.swift` installs a **local** `NSEvent` monitor (no
  Accessibility permission needed) for click / key / window focus and blur, and
  batches to `/events` every 5 s or every 40 events. It is gated on the learner's
  `telemetry_consent` and torn down on sign‑out; the buffer is dropped, not
  uploaded, when consent is revoked.
- **Two sources, one buffer.** The monitor can only see *where the pointer was*, so
  its target is the page (`page:studio`). Call sites that know better call
  `store.recordInteraction("stage.tab.deck")` and record the control. That is the
  half that answers "did the learner open the hint before or after trying".
- **Honesty:** no keystroke content, no window titles (a title is a document name
  or a URL, which would turn an engagement signal into a reading log), and no
  engagement score. `test_a_tap_cannot_move_mastery` pins the important half: a
  hundred taps create no `State` row and leave `/ability` at zero calibrated items.

### 4.2 Real‑time voice, two channels

**Offline conversation mode (`Voice.swift`, no key, no network).** `VoiceIO` gained
an energy voice‑activity detector with a noise floor that follows the room
(`VoiceActivityDetector`), silence endpointing at 1.1 s, and **barge‑in**: while the
tutor is speaking, roughly a third of a second of speech above a raised threshold
stops it. The threshold is raised rather than disabled because the microphone also
hears the speakers — cutting the reply off on the first loud frame is how a duplex
session ends up interrupting itself every time it starts talking. A **Converse**
button on the Stage keeps the mic open across turns, speaks each reply, and reopens
the recogniser 220 ms after each finalisation (reopening inside the recogniser's own
callback races the task teardown and eats the next syllable). ASR stays on‑device
when the recogniser supports it.

**Hosted duplex (`VoiceRealtime.swift`, needs a key).** Connects to
`wss://api.openai.com/v1/realtime`, streams 24 kHz PCM16 mic audio, plays model
audio deltas as they arrive, and uses server‑VAD so the learner can interrupt.
`RealtimeKey.swift` owns the Keychain storage. The Stage header gains a **Voice
chat** toggle; Settings gains the key‑entry card. While connected, the offline
push‑to‑talk and Converse paths are disabled — one mic capture at a time.

Packaging: `package_app.sh` writes `NSMicrophoneUsageDescription` and
`NSSpeechRecognitionUsageDescription`; the Developer‑ID (`-Direct`) entitlements
now include `com.apple.security.device.audio-input`, which the sandbox file already
had. Without it a notarised build asked for a microphone it had no entitlement to
open, and TCC refused.

### 4.3 Learner‑facing level
- `app/harness/leveling.py` maps the internal IRT ability θ (logits) onto a CEFR
  band (Pre‑A1 … C2) and a US school grade (K … 12). `GET /api/v1/ability` returns
  `{theta, se, n_calibrated, level: {...}}` where `level` carries `known`,
  `label`, `interpretable`, `cefr`, `cefr_name`, `cefr_reason`, `grade`,
  `grade_label`, `success_on_average_item`, `note` and `not_certified`.
- **Three ways this mapping goes wrong, and what stops each.** (1) A learner with
  no evidence is given a level — `learner_level` returns `known: false` and no band
  until 5 calibrated items exist, because θ starts at the prior and the prior maps
  cleanly onto "A2 / Grade 5". (2) CEFR is applied to a subject it does not
  describe — `cefr` is `None` unless the enrolled course's subject is a language,
  with `cefr_reason` saying why. (3) A cut point is presented as a measurement —
  the bands are explicit numbers in `CEFR_BANDS`, and every payload carries
  `not_certified`.
- The **Studio** shows a **Your level** card (CEFR for a language course, grade band
  otherwise, plus "on an average question") that refreshes when the analytics
  snapshot changes. With no evidence it shows the refusal, not a number.

---

## 5. Build the native app

```bash
cd harness/native
swift build --disable-sandbox
sh harness/native/package_app.sh        # bundles + codesigns + launches
```

`package_app.sh` writes the Info.plist (including the two mic/speech usage
strings) and signs the `.app`. The sandbox build (`LuminfestLearningHarness.
entitlements`) already carried `audio-input`; the Direct entitlements now do too.

---

## 6. Known limitations (no silent downscoping)

- **Duplex voice is a voice‑only channel to OpenAI.** It is independent of the
  backend tutor and curriculum; it does not yet inject the learner's current
  concept into the model prompt. The offline Converse mode does go through the
  tutor, but it is turn‑taking: the recogniser finalises, the text is sent, the
  reply is spoken. There is no streaming ASR, so the tutor cannot start answering
  before the learner stops, and no partial‑transcript barge‑in — barge‑in is
  energy‑based and needs ~0.33 s of speech.
- **The VAD is a heuristic, not a model.** Energy plus a tracked noise floor. It
  decides "they have stopped talking" well enough; it cannot distinguish speech
  from a television. A learned VAD would be more accurate and would also be another
  download that cannot run offline on first launch.
- **`/deck/from-concept/{concept_id}` persists a fresh editable deck each time it
  is composed with no existing deck.** Re‑opening the editor for the same concept
  without a saved deck can create duplicate deck resources. A concept→deck mapping
  would make this idempotent.
- **The level needs calibrated items.** Below `MIN_ITEMS_FOR_LEVEL` (5) calibrated
  items the card says "Not yet measured" rather than naming a band. The grade
  mapping is a linear stand‑in over the served θ range, not a placement decision.
- **Telemetry is consented and coarse.** Turning it off stops collection after
  saving; the on‑task *reading* is additionally operator‑gated by
  `HARNESS_ATTENTION_MONITOR`. The control‑level targets are only as good as the
  call sites that record them — the page‑level monitor is the floor, not the goal.
