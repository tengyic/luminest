# AI Disclosure

**Version:** 2026-11 · **Effective:** 1 November 2026

Luminfest uses software — rule-based policy, statistical estimates, and optionally a language
model that **you** configure — to decide what you practise next and to help explain ideas.
This page says plainly what the AI does, what it does not do, and how you can tell the
difference. It is written to meet transparency expectations under the EU AI Act and similar
regimes, and because you deserve to know.

## 1. Where AI is used

| Feature | What it does | Is it AI? |
|---|---|---|
| Practice sequencing | Chooses which concept and which item to show next, from your recorded evidence | Rule-based policy, with an optional statistical model |
| Recall prediction | Estimates how likely you are to remember a concept | Statistical model; **labelled as an estimate** |
| Diagnosis | Suggests *possible* error patterns behind a wrong answer | Heuristic hypothesis, **never a verdict** |
| Tutor | Answers questions about a concept | Retrieval-grounded from the curriculum; an LLM only if you configure one |
| Generated artefacts | Drafts flashcards, quizzes, figures | Template and symbolic generation; optional LLM |
| Project feedback | Returns a rubric checklist | Rule-based |

## 2. What the AI does not do

- It does **not** grade you, and it does not issue any accredited or certified result.
- It does **not** make decisions with legal or similarly significant effects about you.
- It does **not** infer your personality, ability, intelligence, or mental state.
- It does **not** measure your attention. Foreground-window time is a crude interaction
  proxy, is off by default, and is labelled as such wherever it appears.
- It does **not** decide whether you are "good at" a subject. It reports what your answers
  show so far, and it says when the evidence is thin.

## 3. How we keep it honest

Every automated decision the harness makes is recorded with the evidence it used and the
reason it gave, and it is deterministic: the same evidence produces the same decision, so a
decision can be reviewed and challenged. Predictions carry their calibration status. A
diagnosis always carries its alternatives. When the evidence is insufficient, the app says so
rather than guessing.

A specific example, because it is the kind of thing that is easy to fake: a concept you have
never attempted has a prior mastery of 0.15. The app treats that as *no evidence yet*, not as
"you are weak at this". Reading the prior as a measurement is how an adaptive system starts
insulting a beginner on their first screen, and this one is written not to.

## 4. Your controls

- **Explain this decision** — every recommendation shows its reason in the app.
- **Turn off activity tracking** — *Settings*. Off by default.
- **Refuse model training** — separate, opt-in consent. Withdraw any time.
- **Choose your model** — a language model is required. Until you add your own provider,
  model and key in *Settings → Language model*, the app reports *model required* and only
  shows grounded curriculum material with a notice that no model answered. You choose the
  endpoint and can remove the key at any time; see the privacy policy, section 4.
- **Export or delete** — *Settings*, self-service.

## 5. Model provenance

The adaptive research model shipped in this build was trained on a **publicly licensed
academic dataset** that is **not** subject-specific to the courses here and is **not**
validated for them. It is therefore disabled for scoring in the default path; that path uses
transparent, uncalibrated priors and says so on screen. We do not claim a trained, validated
model for any subject until one exists and has passed held-out evaluation.

Where a course's practice items are machine-generated rather than written, each item is
stamped as generated in the API response. Generated items are recognition-level practice, and
they are labelled that way rather than presented as authored teaching.

## 6. Human oversight

If you are using Luminfest in a classroom, the educator remains the decision-maker about your
learning. The app is designed to give a teacher evidence and practice opportunities, not to
replace their judgement. A teacher-facing flag such as a suspected-integrity signal is a
prompt for a human conversation and never an automatic penalty.

## 7. Reporting a problem

If an AI feature gives you something wrong, harmful, or confusing, report it from inside the
app: *Settings → Report a problem*. Choose the *AI* category so it is routed as a model problem
rather than a bug. We review reports and will say what we changed.
