# Lumi — the in-app companion

Lumi is the product's character: a soft cream lantern sprite with an asterisk crest, one
glowing ember in the belly, and a three-dot constellation on one cheek. She appears in the
native app as a **companion** (sidebar), as the **guide for first-run setup**, and as the
voice that greets a returning learner.

Source art and the design rationale live in `outputs/luminfest-avatar/`
(`Lumi-Avatar-Spec.html` is the brand-book page).

---

## The one formal Lumi

Lumi has **exactly one approved look**: the painterly, soft-lit cream creature with the
asterisk crest and the glowing amber ember in the belly — the render in
`outputs/luminfest-avatar/lumi-master.png`.

A **flat vector** illustration of the same character circulates as a reference sketch. It
is **not** Lumi. It must not appear in the app, the website, the celebration overlay, a
placeholder state, or as a stand-in when a pose is missing — the two styles do not sit
together, and a flat Lumi in a painterly shell reads as a different character. If a pose
is missing, animate one of the seven sprites (`LumiAction`) instead of drawing a new one.

Enforced by `backend/tests/test_lumi_art.py`, which pins the signature the formal renders
leave behind: exactly seven files named after `LumiSprite`'s raw values, 256×256 8-bit
RGBA, a **matted** alpha channel (2–8 % partial pixels — the distance matte; a vector
cut-out sits near 0.5 % and fails), and a figure filling ~60 % of the canvas height, the
constant `LumiArt.fill` divides by. New renders from the master keep passing; different
art does not.

---

## 1. Why 2D and not a 3D model

This was a real fork in the road, so the reasoning is recorded rather than assumed.

**Decision: 2.5D sprite rig. No 3D model in v1.**

| What 3D would buy | Whether this product needs it |
|---|---|
| Free rotation, the character can turn | No. She faces the learner, in a 207pt rail, at 54pt. There is no second angle to see. |
| Dynamic lighting that reacts to the UI | No. The brand is flat, matte, low-chroma; the ember is the only light source that matters and it is authored, not simulated. |
| Skeletal animation (arms, blinks, physics) | Partly — but five renders plus transform tricks already read as alive (see §3). |
| One asset, infinite poses | Not at this scale. Seven PNGs total 196 KB. |

Against it: a rigged USDZ with blendshapes for expressions, a RealityKit/SceneKit view, an
authoring pipeline for every new gesture, and a runtime that has to work offline on macOS 14
with no external dependencies. That is weeks of work to make a 54pt character *worse* —
3D at that size loses the crisp silhouette that makes her readable in a sidebar.

The reference points the brief named are both 2D: Codex's companion and the WorkBuddy cat
are sprite/vector animations, not models.

**What would change the answer.** If Lumi ever needs to (a) be turned by the user, (b) walk
around a surface, or (c) be lit by the surrounding UI, then 3D earns its cost. The
integration is deliberately shaped so that swap is contained: every view reads
`LumiCompanion.sprite`, so a 3D replacement means changing `LumiSpriteView` and nothing else.

---

## 2. The sprite contract

Seven matted PNGs in `Sources/LearningHarness/Resources/Lumi/`:

| File | Role |
|---|---|
| `lumi-idle.png` | default mood |
| `lumi-listening.png` | the learner is answering |
| `lumi-thinking.png` | the app is scoring a move |
| `lumi-celebrating.png` | a delayed review held |
| `lumi-resting.png` | nothing due; rest is a legitimate move |
| `lumi-greeting.png` | **transient** — the wave |
| `lumi-blink.png` | **transient** — one frame, 110ms |

Rules the art depends on:

- **Straight alpha, not premultiplied.** `.process("Resources")` flattens the subdirectory,
  so `Bundle.module.url(forResource: "lumi-idle", withExtension: "png")` resolves at the
  bundle root — the same mechanism `LuminfestArt` already uses.
- **The figure occupies 60% of the square canvas.** `LumiArt.fill` holds that constant and
  `LumiSpriteView` divides by it, so a call site asks for the *character* height and never
  does the arithmetic. Getting this wrong by eye is how a companion ends up 40% too small.
- **Every frame is centred on the feet, not the bounding box.** A raised arm widens the bbox
  on one side only; centring on it would shove the body off-centre and make the crossfade
  jump. Measured across all seven: feet centres within 2px of the canvas centre.

---

## 3. Behaviour

`LumiCompanion` is a small state machine. Two concepts, deliberately kept apart:

- **Moods** (`LumiMood`) are persistent states. Setting one changes the sprite and it stays.
- **Actions** (`LumiAction`) are transient gestures. An action plays a script, then the
  controller *always* restores `LumiSprite(mood:)`.

That split is what stops a one-shot from becoming a permanent expression — the classic
mascot bug where the character is stuck mid-wave because nothing reset it.

Scripts are **data**, in `LumiAction.steps`, not code in the view. Timing is therefore
assertable in a unit test and tunable without touching SwiftUI.

### Idle life

Two loops make a still image read as a creature, and both are driven from the controller
rather than a `repeatForever` SwiftUI animation — a repeating modifier cannot be paused, and
a script must be able to interrupt it cleanly.

- **Breathing** — `rise` toggles 0 → 1.4pt over 2.3s, skipped while a script runs or while
  resting.
- **Blinking** — every 2.4–6.4s, 110ms on the blink frame. Suppressed when resting: closed
  eyes are already her resting face, so blinking it looks like a twitch.

### Wiring

| Surface | File | Behaviour |
|---|---|---|
| Sidebar | `LumiSidebarSlot` | Greets once per launch (time-of-day line), `thinking` while `store.busy`, `celebrate` + "That's saved." on `store.notice` |
| First-run setup | `LumiSetupGuide` | `listening` while answering, `thinking` on the pace step where the app does arithmetic |
| Tap | `LumiCompanionView` | Hop + a quiet line from `LumiCompanion.affirmations` |

The companion observes `AppStore.busy` and `AppStore.notice` through SwiftUI `onChange`, so
**no store or networking code was touched** to add her.

### Voice

Lines follow `outputs/marketing/01_BRAND_TRAITS.md` §A4: second person, short declaratives,
no streak language ever. `testAffirmationsAreOnBrand` fails the build if someone adds
"keep your streak alive".

---

## 4. Accessibility

- Decorative appearances are `accessibilityHidden(true)`; the sprite carries no information
  the text does not.
- The speech bubble is labelled "Lumi says: …", so VoiceOver reads the sentence rather than
  the character.
- The tap target is marked `.isButton` and is the sprite itself (54pt — comfortably above the
  44pt minimum).
- `accessibilityReduceMotion` disables breathing, hop, squash and tilt; sprite swaps remain,
  because a static expression change is not motion.

---

## 5. Regenerating the art

The renders are generated, not drawn. The pipeline lives in `outputs/luminfest-avatar/`:

```
renders (ImageGen, image-to-image off one master, input_fidelity: high)
  → normalise.py   # bbox → scale to 60% → centre on the feet → 1024 square
  → make_alpha.py  # distance matte: alpha = smoothstep(12, 30, |px − bg|₁), 1px feather
  → assets/transparent/lumi-{state}-256.png
  → copy into Sources/LearningHarness/Resources/Lumi/
```

The "one master" is `lumi-master.png` and nothing else. Never feed the flat vector sketch
in as an img2img input, and never regenerate with a "clean vector" prompt: the style would
drift one generation at a time and the app would end up with the character it rejected.

Two traps worth keeping:

- **Parallel generations collide on filenames.** Two calls in the same second overwrite each
  other silently. Give each render its own directory, or run them sequentially.
- **Build the contact strip from an explicit state**, not from whatever the loop finished
  on — a surface test shipped the *resting* figure once because of exactly that.

## 6. Known limits

- The character cannot turn or be posed arbitrarily; there are seven fixed views.
- No lip-sync. Speech is a text bubble, not mouth animation.
- At 32px and below the figure stops reading; use the asterisk wordmark there instead.
