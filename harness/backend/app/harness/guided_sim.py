"""The guided-simulation cycle: predict, manipulate, explain - and the contract for it.

The playground already turns a completed first-party game into a mastery observation
(:mod:`app.harness.playground.evidence`). What this module adds is the *scaffolding* around
the interaction, because the evidence is unambiguous that an unguided simulation is not
just weaker than a guided one - it can be worse than not simulating at all. Alfieri,
Brooks, Aldrich & Tenenbaum (2011, https://doi.org/10.1037/a0021017) found unassisted
discovery *d ~ -0.38* against explicit instruction, while enhanced/guided discovery was
*d ~ +0.30*; Rutten, van Joolingen & van der Veen (2012,
https://doi.org/10.1016/j.compedu.2011.07.017) found instruction *plus* simulation beat
simulation alone; and de Jong & van Joolingen (1998) documented that learners routinely
fail at unguided discovery because they do not plan, hypothesise or interpret on their own.

So the contract here is deliberately demanding: a simulation outcome is only accepted as
evidence if the learner made a **prediction** before interacting and gave a short
**explanation** afterwards. A run that skipped the scaffolding is refused, and the refusal
names the missing step. This is the same "validate, do not trust" posture the archetype
contract takes for specs.
"""

from __future__ import annotations

from typing import Any, Mapping

#: The three phases of a guided simulation, in order.
STEPS = ('predict', 'manipulate', 'explain')

#: What each phase asks of the learner, for the renderer and the review panel.
STEP_MEANING = {
    'predict': 'Commit to what you expect before touching anything.',
    'manipulate': 'Change one thing at a time and watch what follows.',
    'explain': 'Say why the result came out that way.',
}

#: A graded run needs at least this much explanation. Matches the self-explanation floor
#: in :mod:`app.learning_science`, so the two gates cannot disagree about what counts.
MIN_EXPLANATION_CHARS = 20

#: The fields a committed simulation outcome must carry. ``steps_completed`` must cover
#: every entry in :data:`STEPS`.
REQUIRED_FIELDS = ('sim_id', 'concept_id', 'prediction', 'prediction_correct',
                   'exploration_score', 'explanation', 'steps_completed')

#: How much each phase contributes to the mastery credit. The prediction carries the most
#: weight because it is the only phase that is *scored against what actually happened*: a
#: learner who predicts correctly has committed to a model of the system and been right.
#: Exploration is weighted lowest because it is the easiest to perform without thinking.
CREDIT_WEIGHTS = {'prediction': 0.50, 'exploration': 0.20, 'explanation': 0.30}

#: The explanation length at which the length component of :func:`explanation_substance`
#: saturates. One full sentence of reasoning; longer is not automatically better.
EXPLANATION_TARGET_CHARS = 120

#: Connectives that mark a causal claim rather than a description. A learner who writes
#: "it went up" has described the screen; "it went up because demand shifted" has offered a
#: mechanism. Matched as whole words (and whole bigrams/trigrams for the phrases), so
#: "also" does not count as "so". This is a *gate*, not a semantic grader - see
#: :func:`explanation_substance`.
CAUSAL_WORDS = frozenset({'because', 'therefore', 'since', 'so', 'if', 'then', 'causes',
                          'caused', 'leads', 'led', 'due'})
CAUSAL_PHRASES = ('which means', 'as a result', 'due to', 'leads to', 'led to', 'caused by',
                  'so that')

SIM_CYCLE_RESEARCH_NOTE = (
    'Guided discovery - predict, manipulate, explain - is what makes a simulation teach. '
    'Unguided discovery is associated with worse outcomes than direct instruction (Alfieri '
    'et al. 2011, d ~ -0.38), while guided discovery helps (d ~ +0.30); simulations work '
    'best as a supplement to instruction rather than a replacement (Rutten et al. 2012). '
    'The contract below therefore refuses an outcome that skipped the prediction or the '
    'explanation, because accepting it would record unguided exploration as if it were '
    'evidence of understanding.'
)


def cycle(title: str, *, prediction_options: list[str] | None = None) -> dict[str, Any]:
    """The three prompts that scaffold a simulation on ``title``.

    ``prediction_options`` is optional: when the sim has discrete outcomes (which curve
    shifts, which way the balance moves) offering the options turns a vague guess into a
    commitment the harness can score. When it is omitted the learner predicts in free text.
    """
    what = (title or 'this model').strip()
    prompts = {
        'predict': f'Before you change anything: what do you expect to happen to {what}, and why?',
        'manipulate': f'Change one thing at a time and watch {what}. Note what changed and what did not.',
        'explain': f'Now say why {what} behaved the way it did, in your own words.',
    }
    return {
        'steps': list(STEPS),
        'prompts': prompts,
        'prediction_options': list(prediction_options or []),
        'scored_only_with_scaffolding': True,
        'research_note': SIM_CYCLE_RESEARCH_NOTE,
    }


def evaluate_prediction(prediction: Any, actual: Any) -> dict[str, Any]:
    """Score a committed prediction against what actually happened.

    Comparison is case- and whitespace-insensitive so a correct free-text prediction is not
    marked wrong on formatting. Returns the boolean plus a plain sentence the learner can
    read; the sentence never scolds a wrong prediction, because a wrong prediction that is
    then tested is the mechanism, not a mistake.
    """
    left = str(prediction or '').strip().casefold()
    right = str(actual or '').strip().casefold()
    correct = bool(left) and left == right
    return {
        'prediction_correct': correct,
        'statement': ('Your prediction matched what happened - that is the model working as '
                      'you expected it to.' if correct else
                      'Your prediction did not match, which is the useful case: the gap '
                      'between what you expected and what happened is the thing to explain.'),
    }


def validate_outcome(payload: Mapping[str, Any]) -> list[str]:
    """Return the reasons an outcome is not acceptable evidence. Empty means acceptable.

    The checks are the interaction contract, not a schema for its own sake: each one exists
    because an outcome that fails it would corrupt a mastery update or record unguided
    exploration as learning.
    """
    problems: list[str] = []
    if not isinstance(payload, Mapping):
        return ['An outcome must be a mapping of fields.']
    for field in REQUIRED_FIELDS:
        if field not in payload:
            problems.append(f'Missing required field {field!r}.')
    if problems:
        return problems

    if not str(payload.get('sim_id') or '').strip():
        problems.append('sim_id must be a non-empty identifier.')
    if not str(payload.get('concept_id') or '').strip():
        problems.append('concept_id must name the concept the run is attributed to.')

    if not isinstance(payload.get('prediction_correct'), bool):
        problems.append('prediction_correct must be a boolean.')

    score = payload.get('exploration_score')
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        problems.append('exploration_score must be a number between 0 and 1.')
    elif not 0.0 <= float(score) <= 1.0:
        problems.append('exploration_score must be between 0 and 1.')

    explanation = str(payload.get('explanation') or '').strip()
    if len(explanation) < MIN_EXPLANATION_CHARS:
        problems.append(f'explanation must be at least {MIN_EXPLANATION_CHARS} characters, so a '
                        f'"yes"/"idk" does not count as explaining anything.')

    completed = payload.get('steps_completed')
    if not isinstance(completed, (list, tuple, set)):
        problems.append('steps_completed must be a list of the phases the learner completed.')
    else:
        done = {str(step) for step in completed}
        missing = [step for step in STEPS if step not in done]
        if missing:
            problems.append('A simulation outcome is only evidence when the scaffolding was '
                            f'completed; missing step(s): {", ".join(missing)}. Unguided '
                            'exploration is not recorded as understanding.')

    return problems


def outcome_payload(*, sim_id: str, concept_id: str, prediction: Any, actual: Any,
                    exploration_score: float, explanation: str,
                    steps_completed: Any = STEPS) -> dict[str, Any]:
    """Compose the canonical ``sim.completed`` payload from a finished run.

    The prediction is scored here rather than passed in, so the caller cannot assert
    ``prediction_correct`` independently of the prediction and the outcome - which would let
    a bug or a bad client claim a correct prediction it never made.
    """
    scored = evaluate_prediction(prediction, actual)
    return {
        'sim_id': sim_id,
        'concept_id': concept_id,
        'prediction': str(prediction or ''),
        'actual': str(actual or ''),
        'prediction_correct': scored['prediction_correct'],
        'exploration_score': float(exploration_score),
        'explanation': str(explanation or ''),
        'steps_completed': list(steps_completed or []),
    }


def explanation_substance(text: Any) -> dict[str, Any]:
    """A 0-1 *admission* score for a self-explanation, not a grade of its correctness.

    Two cheap signals, both visible in the output so the score is auditable rather than
    mysterious:

    * **length** - saturates at :data:`EXPLANATION_TARGET_CHARS`. It is a proxy for effort,
      and effort is the only thing it measures; a long wrong explanation scores high here.
    * **causal language** - whether the learner used a connective that marks a mechanism
      (:data:`CAUSAL_MARKERS`).

    The score deliberately does *not* try to decide whether the explanation is right. That
    is a semantic judgement, and faking one with a word count would be worse than admitting
    the limit: a reviewer or a model-graded pass can replace this function without changing
    the contract around it. What it does do is stop "yes", "idk" and "it changed" from
    counting as an explanation, which is the failure mode the research names.
    """
    body = str(text or '').strip()
    length = min(1.0, len(body) / float(EXPLANATION_TARGET_CHARS)) if body else 0.0
    words = [word for word in ''.join(ch if ch.isalnum() else ' ' for ch in body.casefold()).split()]
    markers = sorted({word for word in words if word in CAUSAL_WORDS})
    joined = ' ' + ' '.join(words) + ' '
    for phrase in CAUSAL_PHRASES:
        if f' {phrase} ' in joined:
            markers.append(phrase)
    causal = 1.0 if markers else 0.0
    score = 0.6 * length + 0.4 * causal
    return {
        'score': round(score, 4),
        'length_chars': len(body),
        'length_component': round(length, 4),
        'causal_markers': markers,
        'note': 'An admission gate for evidence, not a judgement of whether the reasoning is '
                'correct. Length measures effort; connectives measure whether a mechanism '
                'was offered at all.',
    }


def credit(outcome: Mapping[str, Any]) -> dict[str, Any]:
    """Turn a *validated* outcome into the mastery credit it has earned.

    Raises :class:`ValueError` when the outcome fails the contract, because an outcome that
    skipped the scaffolding has no credit to award - silently returning zero would let the
    caller record it as a failed attempt, which is a different and false claim.

    ``counts_as_correct`` is the binary the mastery estimator consumes. It requires **both**
    a correct prediction and a substantive explanation: predicting without explaining is
    luck plus a guess, and explaining without predicting is a post-hoc story. Either alone
    is weaker evidence than the pair, which is exactly why the cycle asks for both.
    """
    problems = validate_outcome(outcome)
    if problems:
        raise ValueError('; '.join(problems))
    substance = explanation_substance(outcome.get('explanation'))
    exploration = min(1.0, max(0.0, float(outcome.get('exploration_score') or 0.0)))
    predicted = bool(outcome.get('prediction_correct'))
    score = (CREDIT_WEIGHTS['prediction'] * float(predicted)
             + CREDIT_WEIGHTS['exploration'] * exploration
             + CREDIT_WEIGHTS['explanation'] * substance['score'])
    explained = substance['score'] >= 0.5
    return {
        'score': round(score, 4),
        'counts_as_correct': bool(predicted and explained),
        'prediction_correct': predicted,
        'explanation_substantive': explained,
        'explanation': substance,
        'weights': dict(CREDIT_WEIGHTS),
        'basis': ('A simulation outcome counts as a correct observation only when the '
                  'prediction matched and the explanation offered a mechanism. A correct '
                  'prediction alone can be a lucky guess; an explanation alone is a story '
                  'told after the fact.'),
    }


def describe() -> dict[str, Any]:
    """The cycle's posture, for the status endpoint and the transparency panel."""
    return {
        'steps': list(STEPS),
        'meaning': dict(STEP_MEANING),
        'required_fields': list(REQUIRED_FIELDS),
        'min_explanation_chars': MIN_EXPLANATION_CHARS,
        'credit_weights': dict(CREDIT_WEIGHTS),
        'scored_only_with_scaffolding': True,
        'research_note': SIM_CYCLE_RESEARCH_NOTE,
    }
