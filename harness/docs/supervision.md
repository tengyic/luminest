# Supervision: the decision engine behind the four design pages

The design notes describe one system in four layers: an architecture (three consoles + RAG +
TTS), a state machine (active/inactive, rest, timeouts), a risk layer (suspicious behaviour,
adaptive difficulty), and a reward layer (resources, locks, streaks, badges). This document
maps each part onto the code that owns it, and says plainly which parts are built, which
already existed, and which were deliberately not built.

The rule that organises everything: **`policy.py` decides what to teach next; this engine
decides whether to speak at all.** Those are different questions and they fail differently.
A wrong move is a bad lesson. A wrong interruption is a learner who closes the app.

## Where each piece lives

| Design layer | Code | Status |
| --- | --- | --- |
| Scroll/click activity sampling | client → `POST /api/v1/supervision/assess` | **new** |
| Idle → nudge / break / retrieval | `teaching/supervision.py: assess` | **new** |
| Rest quota, 5-minute timeout | `supervision.assess` (`rest_quota_*`, `IDLE_AWAY_SECONDS`) | **new** |
| Progress vs plan (`progress < n`) | `supervision.progress_reading` | **new** |
| Active-but-behind is not stuck | `supervision.assess` (scroll branch) | **new** |
| Node memory → explain / quiz / skip / ask-why | `teaching/evidence.py`, `policy.py` | existed |
| Adaptive difficulty (INC/DEC/Normal) | `supervision.difficulty` | **new** (policy was config-only) |
| Variant item / explain-back on a suspicious answer | `supervision.provenance` | **new** |
| Streaks, quiz streaks, node milestones, badges, certificate | `teaching/motivation.py` | **new** |
| Lesson artifacts, deck, simulation, whiteboard | `teaching/procedure.py`, `toolbox.py` | existed |
| RAG grounding on the textbook | `teaching/retrieval.py`, `source_context` | existed |
| TTS output | `harness/speech.py`, `/voice/speak` | existed |
| Browser control (Playwright) | `harness/browser.py` | existed, teacher-gated |
| Onboarding slides + animated pointer | native client only | **not built** |
| Camera-based verification | — | **refused**, see below |
| Participation deduction, ban flags, lock-in test shell | — | **refused**, see below |

## The three refusals

These are not omissions. They are the parts of the design that would make the product worse
at the thing it is for, and each has a cheaper replacement that does the same job.

**Camera frames as a cheat check.** The app already has a camera path for presentation
recording, and `attention.py` sets the precedent: the visual question is about the *work in
the frame*, frames are never stored, and disagreement is reported rather than resolved. A
camera aimed at a learner to decide whether they are cheating is a different product, is
wrong more often for disabled learners, and cannot be run on minors in several jurisdictions
without a specific consent process. The replacement is the one a teacher uses: ask them to
explain, then give a variant. Both are in `supervision.provenance` and both are stronger
evidence than a webcam.

**Participation deductions and ban flags.** `participation()` returns an active share and a
sentence the learner can read. It is not subtracted from anything, and no branch in the
module can flag an account or block a lesson. A timeout *re-plans* the session
(`move.shorten_session`), because the useful response to an absent learner is a shorter
session, not a record against them.

**A quiz that traps the learner.** The spec's `quiz <stay>` is implemented as one retrieval
question with a cooldown, not a modal that blocks progress until answered. A learner who
walks away from a trapped modal is a learner who uninstalls.

## What "suspicious" actually means

The three conditions the notes put under *very suspicious* are, read correctly, the three
conditions under which knowledge is fragile rather than owned:

* answered in a fraction of this learner's own average time;
* solved the original item and not a same-concept variant;
* right answer, no reasoning.

Each routes to a teaching move — variant item, explain-back, drop to the prerequisite — and
the payload carries `not_a_verdict` so a client cannot present the check as an accusation.
Assessment contexts (`test`, `diagnostic`) never trigger a check: a variant inside a test is
a second test.

## HTTP surface

```
GET  /api/v1/supervision          thresholds + posture, for the transparency panel
POST /api/v1/supervision/assess   one decision for this moment
```

`assess` never writes. It is a pure function of the request plus one read of the account's
own concept state, which is why it is safe to call on every interval tick. The client cannot
state its own mastery: the field is not in the schema (`extra="forbid"`, 422) and the stored
belief overwrites anything else. `mastery_known` is separate from the number, because
`evidence.PRIOR` (0.15) means "no attempts yet", not "weak" — collapsing the two would open
every new learner with an unsolicited explanation and a difficulty drop.

## Still to wire

1. **Client signals.** The native app does not yet send scroll/click/idle counts. Until it
   does, the route is callable but nothing calls it.
2. **Rest quota persistence.** Currently per-request. It belongs in
   `user_preferences.ui` alongside `deck_cursor`, with the same no-migration trick.
3. **Streak and badge storage.** `motivation.py` is pure; it needs a read of session days
   and practice results, both of which already exist (`Message`, `Attempt`).
4. **The onboarding tour.** Slides and the animated pointer are native UI work, untouched.

Tests: `backend/tests/test_supervision.py` (32). Live probe:
`scripts/probe_supervision.py`, which starts a server, registers an account, and prints the
move for each scenario.
