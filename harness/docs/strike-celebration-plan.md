# Strike celebration — animation & sound plan

The **rules already exist**. `app/harness/teaching/motivation.py` implements exactly this
spec: `STREAK_MILESTONES {5, 10, 15}`, `QUIZ_MILESTONES {5, 10}`, `NODE_MILESTONES
(0.80, 1.00)`, `badges()`, `certificate()`, and — critically — `STREAK_CONTEXTS =
('quiz', 'practice')`, so unit tests and diagnostics can never feed a question streak.

The mascot exists too: seven sprites under `native/.../Resources/Lumi/` and a data-driven
choreography system in `LumiCompanion.swift` (`LumiAction`: blink / hop / nod / greet /
celebrate). What is missing is the **presentation layer** — turning a milestone into an
animated popup and a sound. This plan adds that without rebuilding the rules.

Guiding constraint, stated up front because it is the whole point: **this is a positive
system.** A broken streak announces nothing. There is no loss-aversion animation, no red, no
"you lost it" state. The unactive chain is a separate, softer notification and never looks
like a celebration.

## 0. What is built (2026-10-25)

Phases 1 and 2 below are implemented; phase 3 is not. The rules were already done
(`motivation.py`), so everything added here is the emitter, the route and the presentation.

| Layer | File | What it does |
|---|---|---|
| Rules | `backend/app/harness/teaching/motivation.py` | unchanged — thresholds, contexts, badges |
| Emitter | `backend/app/harness/rewards.py` | `events(...)` → flat event dicts; `kind → (tier, mascot, sound)` in one table; stable `id` per achievement; heaviest tier sorts first |
| Route | `backend/app/routes_rewards.py` | `GET /api/v1/rewards/events` — reads `attempts`, `learning_states`, `procedure_runs`; read-only; mounted via `FEATURE_ROUTERS` |
| Choreography | `native/.../LumiCompanion.swift` | `LumiAction.cheer` (crouch → hop → settle, 0.54 s) and `.sparkle` (nod + lean, 0.32 s); `LumiCompanion.celebrate(tier:line:)` and `.settle()` |
| Sound | `native/.../SoundBank.swift` | five voices **synthesized** at first play (no audio assets, no licence): `chime_soft`, `chime`, `fanfare`, `sparkle`, `badge`; deterministic noise; rendered into a 16-bit mono WAV in memory |
| Queue | `native/.../RewardCenter.swift` | fetches, dedupes by id in `UserDefaults`, orders by tier, presents one at a time |
| Presentation | `native/.../CelebrationOverlay.swift` | the three tiers; seeded `Canvas` confetti; VoiceOver announcement; reduce-motion path skips particles |
| Wiring | `LuminfestApp.swift` | `RewardOverlay` above everything, 60 s poll while signed in |

Tests: `backend/tests/test_rewards.py` (21, passing). `native/Tests/.../RewardsTests.swift`
(8) pins sound length/loudness/container and the client's dedupe + ordering — written, and
**not yet run**: `swift build` cannot run in this sandbox (see `DISTRIBUTION.md`), so the
sources were verified with `swiftc -typecheck` only.

Two deliberate gaps:

- **No count-up on the milestone number.** The plan called for one; a static number is what
  shipped, because a count-up needs its own animation state per tier and the moment already
  reads without it. Add it when the badge wall lands.
- **`unactive_notification` and `active_watch` are declared but not emitted here.** Both
  describe a moment *inside* a session — idle time, share of the window active — which
  `supervision.py` and `classroom.py` already measure from live signals. Recomputing them
  from stored attempts would be a second, worse measurement of the same thing. The client
  has their tier/mascot/sound ready for when those paths emit them.

Also missing, and knowingly: no UI for the sound toggle (`SoundBank.isEnabled` is persisted
and honoured, but nothing sets it), no badge wall, no certificate moment.

## 1. Event contract (backend → client)

Add a thin emitter beside `motivation.py` (pure, no new clock): `rewards.events(...)` returns
a list of **reward events**. The client renders them; it never recomputes thresholds.

```json
{
  "id": "streak:2026-10-24:5",
  "kind": "streak_milestone",
  "value": 5,
  "tier": "celebrate",
  "mascot": "celebrating",
  "sound": "fanfare",
  "title": "5 days in a row",
  "announce": "5 days in a row - five days in a row."
}
```

| `kind` | Trigger (already in `motivation.py`) | `tier` | `mascot` | `sound` |
|--------|--------------------------------------|--------|----------|---------|
| `streak_notification` | a day counted, no milestone | `toast` | `greeting` | `chime_soft` |
| `streak_milestone` | 5 / 10 / 15 consecutive days | `celebrate` | `celebrating` | `fanfare` |
| `unactive_notification` | inactivity (separate chain) | `toast` | `listening` | `chime_soft` |
| `active_watch` | active ≥ 80 % / 90 % of the window | `toast` | `listening` → `hop` | `sparkle` |
| `question_strike` | 5 / 10 correct in `quiz`/`practice` only | `banner` / `celebrate` | `nod` / `celebrating` | `chime` / `fanfare` |
| `node_milestone` | mastery crosses 0.80 / 1.00 | `banner` / `celebrate` | `nod` / `celebrating` | `chime` / `fanfare` |
| `badge` | a composite condition in `badges()` | `celebrate` | `celebrating` | `badge` |

`id` is the idempotency key: the client shows each id once, so a retry or a second poll
cannot double-celebrate. `value` lets the client pick the number to animate ("5", "10").

**Boundary enforcement** stays in `motivation.quiz_streak` (`STREAK_CONTEXTS`), not in the
client. The client must never grant a `question_strike` for `test` or `diagnostic`; if the
backend withholds it, there is nothing to render.

## 2. Animation tiers

Three tiers, so a 5-day streak and a quiet nudge do not use the same weight of ceremony.

- **`toast`** — a small card slides in bottom-trailing, Lumi hops, text, 2.5 s, auto-dismiss.
  Used for `unactive_notification`, `active_watch`, `streak_notification`.
- **`banner`** — a centred card with a soft scale-in, Lumi nods, a light sparkle burst, 3.5 s.
  Used for `question_strike` 5, `node_milestone` 0.80.
- **`celebrate`** — a full-screen (or large panel) moment: dimmed backdrop, Lumi centre stage
  plays `.celebrate`, confetti/sparkle, the milestone number counts up, the line is spoken
  by Lumi, a "Continue" affordance. Used for `streak_milestone`, `question_strike` 10,
  `node_milestone` 1.00, `badge`.

All three are pure SwiftUI, no Lottie/Rive dependency, matching the existing renderer style.

### Confetti / sparkle

A `CelebrationParticles` view: `Canvas` + `TimelineView(.animation)` with a **seeded**
particle system (position, velocity, rotation, fade) so a test can assert determinism and a
screenshot is reproducible. Palette from `Palette` (sage / ochre / peach), never red. Under
`accessibilityReduceMotion`, particles are skipped and the card simply fades in.

### Mascot choreography

Extend `LumiAction` with two data-driven scripts (the existing `LumiStep` model already
supports hold / rise / squash / tilt):

- `.cheer` — three beats: squash-crouch → hop with `celebrating` → settle, ~0.9 s. The
  celebration for `celebrate` tier.
- `.sparkle` — a quick nod + tilt with `greeting`, ~0.45 s. For `toast` / `banner` praise.

`LumiCompanion` gains `celebrate(kind:line:)` that sets mood `.celebrating`, plays the script,
and `say(line)`. Existing `play`/`say`/`setMood` already handle interruption and return-to-
mood, so no new timing machinery is needed.

**Both scripts reuse the seven shipped sprites, so phases 1–2 need no new art.** That is
deliberate: Lumi has one formal look (the painterly render from
`outputs/luminfest-avatar/lumi-master.png`) and the flat-vector sketch that circulates is not
her — see `lumi-companion.md` §"The one formal Lumi" and
`backend/tests/test_lumi_art.py`, which fails the build if a sprite is swapped for
differently-produced art. If a celebration later wants a pose the seven do not cover, it is
rendered from the master through `normalise.py` + `make_alpha.py`, never drawn in another
style to fill the gap.

## 3. Sound design

There are **no audio assets** in the bundle today (`Resources/` holds only `PrivacyInfo`), and
`Voice.swift`'s `ClipPlayer` already plays mp3 via `AVAudioPlayer` for tutor speech. Two
routes:

**Recommended — synthesize the SFX (no files, no licensing, deterministic).**
A `SoundBank` built on `AVAudioEngine` + `AVAudioSourceNode` renders short envelopes at
launch:

| name | recipe | length |
|------|--------|--------|
| `chime_soft` | two sines (C6 1046.5 Hz + E6 1318.5 Hz), ADSR 10/80/0/350 ms | 0.45 s |
| `chime` | three sines (C6, E6, G6), 60 ms stagger, gentle decay | 0.7 s |
| `fanfare` | triangle arpeggio C5-E5-G5-C6 (523/659/784/1046), 90 ms stagger | 1.2 s |
| `sparkle` | white noise through a band-pass sweep 2→6 kHz, 120 ms decay | 0.35 s |
| `badge` | FM bell (carrier 880, modulator ×1.4, index 2) + shimmer tail | 1.0 s |

This matches the codebase posture (offline, deterministic, no provenance problem) and is
~200 lines. Volume respects the system output and a user `soundEnabled` toggle.

**Optional — bundle a richer fanfare.** If a produced fanfare is wanted, put it under
`Resources/Sounds/` and play it with the existing `ClipPlayer`. Only use assets with a
verified licence — the media pipeline already refuses unverified ones, and the same rule
should apply to audio. `sound` in the event payload lets the client fall back to the
synthesized name when a bundled file is absent.

## 4. Architecture

```
motivation.py  ──►  rewards.events(...)  ──►  GET/POST /api/v1/rewards/events
                                                  │  (idempotent, scoped to caller)
                                                  ▼
                          native: RewardCenter (ObservableObject)
                          ├─ consumes events, dedupes by id
                          ├─ maps kind → tier / mascot / sound
                          ├─ presents CelebrationOverlay(tier:event:)
                          └─ drives LumiCompanion.celebrate(...) + SoundBank.play(...)
```

- **Backend**: one route returns pending events for the caller; the emitter is pure and the
  route only scopes and serialises (same shape as `routes_supervision.py`).
- **Client**: a `RewardCenter` owned by `AppStore`, subscribed on the polling tick the app
  already runs. It queues events so two at once do not collide (celebrate beats banner beats
  toast).
- **Presentation**: `CelebrationOverlay` is a single `ZStack` layer at the shell root; it
  renders one event at a time and dismisses on tap / timer / "Continue".

## 5. Accessibility & tone

- **Reduce Motion** → no particles, no bounce; fade + text + Lumi mood change only.
- **Sound toggle** → persisted; default on, respects a system "mute".
- **VoiceOver** → the overlay posts an announcement with `title` + `announce`; Lumi is
  `accessibilityHidden` (the existing sprite view already is).
- **Contrast** → celebration text on the palette surface, not on a bright particle field.
- **Tone** → no streak language in Lumi's ordinary lines (existing rule); milestone lines are
  second person, factual, and never compare the learner to others. A broken streak says
  nothing.

## 6. Phasing & tests

**Phase 1 — contract + Lumi.** `rewards.events` + route + `RewardCenter` + `toast`/`banner`
overlay + `LumiCompanion.celebrate`. Tests: thresholds map to kinds; `quiz_streak` ignores
`test`/`diagnostic`; each id is emitted once; client dedupe.

**Phase 2 — sound + celebrate tier.** `SoundBank` synthesis, `.cheer`/`.sparkle` scripts,
confetti `Canvas`, full-screen celebration. Tests: deterministic particle seed; sound names
resolve; reduce-motion path skips particles.

**Phase 3 — badges + polish.** Badge wall, certificate moment, queueing, VoiceOver pass,
screenshot regression for each tier.

Existing tests to keep green: `tests/test_supervision.py` (motivation rules),
`LumiCompanion` choreography tests, and `test_packaging_manifest` if new resources ship.
