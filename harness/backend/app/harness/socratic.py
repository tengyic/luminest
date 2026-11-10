"""The Socratic dialogue ladder: which move the tutor makes on the next turn.

This is the S5 sub-loop from the modified agentic loop, expressed as a pure function so it
can be tested and reviewed independently of any model call. The evidence behind it is the
AutoTutor line of work on tutorial dialogue - pumping, hinting, prompting and assertion as
distinct moves, associated with large tutoring gains (Graesser et al.; Nye, Graesser & Hu
2018) - plus the self-explanation literature (Chi et al.).

Two rules are load-bearing and are enforced here rather than left to the prompt:

* **The answer is not revealed before the ladder has been worked.** ``reveal_answer`` is
  True only at the assertion rung, which is reached after three failed cycles (pump at 0,
  hint at 1, prompt at 2, assert at 3). This gives the harness a checkable answer-leakage
  guard instead of a hope. The number here is load-bearing: it is also stated in
  :mod:`app.harness.conduct`, which is injected into two system prompts, and
  :func:`describe` publishes it to the transparency panel. All three must agree, or the
  model is told it may reveal an answer that the server-side guard still withholds.
* **An explicit request for a worked explanation is honoured immediately.** Forcing Socratic
  questioning on a learner who has asked to be shown is not pedagogy, it is obstinacy; the
  existing tutor prompt already says so, and this module makes that branch explicit.
"""

from __future__ import annotations

from typing import Any, Mapping

#: The dialogue moves, in the order they escalate.
LADDER = ('pump', 'hint', 'prompt', 'assert')

#: How many failed cycles before the tutor may state the step outright. This equals the
#: index of ``assert`` in :data:`LADDER` and is asserted by the tests; the conduct block
#: injected into the system prompts states the same number.
ASSERT_AFTER_FAILURES = LADDER.index('assert')

#: What each move asks the tutor to do, in plain language, for the review panel.
MOVE_MEANING = {
    'pump': 'Invite more of the learner\'s own thinking ("say more about how you got there").',
    'hint': 'Narrow the space without solving it.',
    'prompt': 'Ask for the specific missing sub-step.',
    'assert': 'State the step itself, because the ladder has been worked.',
}

DIALOGUE_RESEARCH_NOTE = (
    'The ladder follows the AutoTutor dialogue-move account (pumping, hinting, prompting, '
    'assertion) and the self-explanation literature (Chi et al.). Conversational tutoring of '
    'this kind is associated with large gains (Nye, Graesser & Hu 2018, ~0.8 SD), but those '
    'are effect sizes for well-designed dialogue systems on specific tasks, not a guarantee '
    'for this product. The one hard rule encoded here is procedural: do not hand over the '
    'answer before the learner has had the chance to produce it. '
    'What that rule is worth, and what it is not: in a randomised field trial an unguarded '
    'GPT-4 tutor raised assisted practice performance by 48% but lowered a later unassisted '
    'exam score by 17% (Bastani et al., PNAS 2025, '
    'https://doi.org/10.1073/pnas.2422633122); the guardrailed arm, which used '
    'teacher-designed hints instead of answers, removed the harm but did not produce a '
    'statistically significant learning gain. A separate crossover RCT that did find large '
    'gains (Kestin et al., Scientific Reports 2025, '
    'https://www.nature.com/articles/s41598-025-97652-6) relied on expert-crafted prompts, '
    'pre-written step-by-step answers and platform-enforced sequencing, and its authors '
    'explicitly warn against AI as a crutch and against replacing in-person teaching. '
    'So the rule below is a floor against a measured harm, not evidence that this product '
    'improves learning outcomes. No learner-outcome trial has been run on this harness.'
)


def step(state: Mapping[str, Any]) -> dict[str, Any]:
    """Decide the next dialogue move from the turn's state.

    ``state`` keys (all optional, all defaulting to a fresh turn):
      * ``consecutive_failures`` - how many attempts in a row have failed on this idea.
      * ``hints_given`` - how many hints have already been offered this cycle.
      * ``learner_explained`` - whether the learner has produced a self-explanation.
      * ``asked_for_explanation`` - whether the learner explicitly asked to be shown.
      * ``trend`` - the loop's ``elapsed_trend`` reading, for a struggle signal.

    Returns ``{'move', 'say', 'reveal_answer', 'reason', 'ladder_position'}``.
    """
    failures = max(0, int(state.get('consecutive_failures', 0) or 0))
    explained = bool(state.get('learner_explained'))
    asked = bool(state.get('asked_for_explanation'))
    trend = str(state.get('trend') or '')

    # An explicit request is honoured at once: withholding a worked explanation from a
    # learner who asked for one is not Socratic, it is unhelpful.
    if asked:
        return _result('assert', True,
                       'The learner asked to be shown the step, so the ladder is skipped '
                       'deliberately rather than ignored.')

    # A learner who has just explained their reasoning is asked to go deeper, not corrected
    # by a hint: keep them producing.
    if explained and failures == 0:
        return _result('pump', False,
                       'The learner just explained their reasoning; invite more of it before '
                       'adding anything.')

    # A sharply worsening latency trend with no failure yet is a struggle signal; the
    # response is a hint, not more pumping.
    if trend == 'much_slower' and failures == 0:
        return _result('hint', False,
                       'Response time is climbing, so narrow the space rather than asking for '
                       'more.')

    # The ladder itself: one rung per failed cycle, and only the last rung reveals.
    if failures == 0:
        return _result('pump', False,
                       'No failed cycle yet, so elicit the learner\'s own thinking first.')
    if failures == 1:
        return _result('hint', False, 'One failed cycle; narrow the space before prompting.')
    if failures == 2:
        return _result('prompt', False,
                       'Two failed cycles; ask for the specific missing sub-step.')
    return _result('assert', True,
                   f'{failures} failed cycles: the ladder has been worked, so state the step.')


def may_reveal_answer(state: Mapping[str, Any]) -> bool:
    """Whether it is currently permissible to reveal the solution.

    The single source of truth for the threshold, so a future output guard cannot re-derive
    the rule and disagree with the dialogue policy.

    Honest scope: **nothing in the shipped server calls this yet.** The ladder is computed
    (``app.harness.loop``) and injected into the prompt as state, which makes the three-cycle
    rule an instruction the model is given, not a filter applied to what it produces. Call
    this from a guard before claiming one exists.
    """
    return bool(step(state)['reveal_answer'])


def _result(move: str, reveal: bool, reason: str) -> dict[str, Any]:
    return {
        'move': move,
        'say': MOVE_MEANING[move],
        'reveal_answer': reveal,
        'reason': reason,
        'ladder_position': LADDER.index(move),
    }


def state_from_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Translate the loop's gathered evidence into the ladder's own state.

    The derivation lives here rather than in :mod:`app.harness.loop` so the policy and the
    evidence that feeds it cannot drift apart: if the ladder's inputs change, this function
    changes, and the loop keeps calling it.

    ``consecutive_failures`` comes from the attempt history the loop already fetched
    (``evidence['consecutive_failures']``); ``learner_explained`` from whether the learner
    wrote reasoning on their last attempt; ``trend`` from the loop's latency reading. There
    is no ``asked_for_explanation`` here because that needs the learner's *message*, which
    the decision step does not see - so it defaults to False, and the turn-level caller can
    override it before asking for a move.
    """
    return {
        'consecutive_failures': max(0, int(evidence.get('consecutive_failures') or 0)),
        'hints_given': max(0, int(evidence.get('hints_given') or 0)),
        'learner_explained': bool(evidence.get('reasoning_written')),
        'asked_for_explanation': bool(evidence.get('asked_for_explanation')),
        'trend': str(evidence.get('elapsed_trend') or ''),
    }


def describe() -> dict[str, Any]:
    """The ladder's posture, for the status endpoint and the transparency panel."""
    return {
        'ladder': list(LADDER),
        'meaning': dict(MOVE_MEANING),
        'assert_after_failures': ASSERT_AFTER_FAILURES,
        'honours_explicit_request': True,
        'research_note': DIALOGUE_RESEARCH_NOTE,
    }
