"""The per-turn diagnosis query: read the learner, then bind what the turn must do.

The teaching policy already scores moves, but a score is not a *reading*. It does
not say where on the ability scale this learner is, how much to trust that, or how
hard the next item should be. Without those numbers the same learner gets a gentle
hint in one turn and a transfer task in the next, because the only thing choosing
between them is the model's mood.

This is the gate the diagnosis-driven prototype established, reduced to what the
harness can honestly support:

    read(evidence)  ->  TurnReading   (BKT mastery, band, target difficulty, act)
    check(text)     ->  violations    (structural contract for the written turn)
    apply(text)     ->  repaired text (append the missing question, never rewrite)

Two deliberate limits, both of which are the opposite of what an eager
implementation would do:

* **No theta is invented.** ``psychometrics`` can estimate IRT ability only from a
  response matrix; when the caller has no estimate, ``theta`` is ``None`` and the
  target difficulty comes from the BKT logit instead. An invented theta would look
  more scientific and be less true.
* **The contract is checked, not imposed.** ``apply`` appends the question the turn
  was supposed to ask; it never deletes a sentence the model wrote. A gate that
  rewrites teaching is a second teacher with no lesson plan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

__all__ = ['TurnReading', 'read', 'probe_question', 'check', 'apply']

#: Below this BKT posterior the learner is guessing or missing a prerequisite;
#: the next turn should shrink the step, not raise the bar.
FRAGILE = 0.35
#: Above this the move can be a transfer task rather than more instruction.
SECURE = 0.70
#: The success probability the turn aims for. 0.7 is deliberate: 0.9 is busywork,
#: 0.5 makes every turn a coin flip dressed as teaching.
TARGET_SUCCESS = 0.70

#: Bands, in order, so a caller can render a rail without hard-coding strings.
BANDS = ('unmeasured', 'fragile', 'emerging', 'secure')

_ANSWER_MARKERS = ('the answer is', 'the answer would be', '答案是', '最终答案是',
                   'the final answer is', 'so the answer is')


def _clamp_probability(value: float) -> float:
    return min(max(float(value), 0.001), 0.999)


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def count_questions(text: str) -> int:
    """Count question marks in either script. ``?`` alone misses Chinese turns."""
    return str(text or '').count('?') + str(text or '').count('？')


@dataclass(frozen=True)
class TurnReading:
    """One turn's diagnosis: what is believed, how strongly, and what follows."""

    mastery: float
    mastery_known: bool
    attempts: int
    band: str
    target_b: float
    expected_success: float
    uncertainty: float
    act: str
    must_ask: bool
    reveal_allowed: bool
    theta: float | None = None
    theta_se: float | None = None
    trace: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            'mastery': round(self.mastery, 3),
            'mastery_known': self.mastery_known,
            'attempts': self.attempts,
            'band': self.band,
            'target_b': round(self.target_b, 3),
            'expected_success': round(self.expected_success, 3),
            'uncertainty': round(self.uncertainty, 3),
            'act': self.act,
            'must_ask': self.must_ask,
            'reveal_allowed': self.reveal_allowed,
            'theta': None if self.theta is None else round(self.theta, 3),
            'theta_se': None if self.theta_se is None else round(self.theta_se, 3),
            'trace': list(self.trace),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> 'TurnReading':
        """Rebuild a reading that travelled through ``TeachingPlan.to_dict``."""
        return cls(
            mastery=float(data.get('mastery') or 0.0),
            mastery_known=bool(data.get('mastery_known')),
            attempts=int(data.get('attempts') or 0),
            band=str(data.get('band') or 'unmeasured'),
            target_b=float(data.get('target_b') or 0.0),
            expected_success=float(data.get('expected_success') or 0.0),
            uncertainty=float(data.get('uncertainty') or 1.0),
            act=str(data.get('act') or 'probe'),
            must_ask=bool(data.get('must_ask')),
            reveal_allowed=bool(data.get('reveal_allowed')),
            theta=data.get('theta'),
            theta_se=data.get('theta_se'),
            trace=tuple(str(item) for item in (data.get('trace') or ())),
        )


def read(evidence, *, theta: float | None = None, theta_se: float | None = None,
         explicit_request: bool = False) -> TurnReading:
    """Query the belief state and decide the shape of this turn.

    ``explicit_request`` is the learner asking to be shown, and it outranks the
    band: a learner who says "just tell me" gets an explanation, not a fourth
    probe. That is a teaching decision, not a loophole -- refusing a direct
    request is how a tutor becomes an obstacle.
    """
    mastery = _clamp_probability(getattr(evidence, 'mastery', 0.15) or 0.15)
    attempts = int(getattr(evidence, 'attempts', 0) or 0)
    known = attempts > 0
    if not known:
        band = 'unmeasured'
    elif mastery < FRAGILE:
        band = 'fragile'
    elif mastery < SECURE:
        band = 'emerging'
    else:
        band = 'secure'

    ability = _logit(mastery)
    target = ability - _logit(TARGET_SUCCESS)
    if band == 'fragile':
        # Below the target band, aim easier than the point estimate: the next
        # correct answer is worth more than one more calibrated failure.
        target -= 0.25
    elif band == 'secure':
        target += 0.15

    # A secure learner who just got it wrong is not ready for transfer; the last
    # response is the strongest single piece of evidence in the turn.
    last_correct = getattr(evidence, 'last_correct', None)
    if band == 'secure' and last_correct is False:
        band_act = 'prompt'
    else:
        band_act = {'unmeasured': 'probe', 'fragile': 'hint',
                    'emerging': 'prompt', 'secure': 'transfer'}[band]

    if explicit_request:
        act = 'reveal'
    else:
        act = band_act

    expected = _sigmoid(ability - target)
    uncertainty = 1.0 / (1.0 + attempts)
    must_ask = act in ('probe', 'hint', 'prompt', 'transfer')

    trace = (
        f'BKT p={mastery:.2f} over {attempts} attempt(s)',
        f'band={band}',
        f'target b={target:+.2f} (aim {TARGET_SUCCESS:.0%} success, '
        f'expected {expected:.0%})',
        ('theta from IRT' if theta is not None else 'theta absent: no response matrix'),
        f'act={act}',
    )
    return TurnReading(
        mastery=mastery, mastery_known=known, attempts=attempts, band=band,
        target_b=target, expected_success=expected, uncertainty=uncertainty,
        act=act, must_ask=must_ask, reveal_allowed=explicit_request,
        theta=theta, theta_se=theta_se, trace=trace)


def probe_question(title: str) -> str:
    """The question a turn owes the learner when the model forgot to ask one."""
    subject = (title or 'this idea').strip()
    return (f'Before I add anything: what is your first step on {subject}, '
            f'and why that one?')


def check(text: str, reading: TurnReading) -> tuple[str, ...]:
    """Structural contract violations for a written turn.

    Only rules that are unambiguous are checked. "This explanation is too long"
    or "the hint gives too much away" need judgement; "a probe turn with no
    question in it" does not.
    """
    body = str(text or '')
    violations: list[str] = []
    questions = count_questions(body)
    if reading.must_ask and questions == 0:
        violations.append('no_question')
    if questions > 2:
        violations.append('too_many_questions')
    if reading.must_ask:
        lowered = body.casefold()
        if any(marker in lowered for marker in _ANSWER_MARKERS):
            violations.append('states_answer_on_probe')
    return tuple(violations)


def apply(text: str, reading: TurnReading, *, title: str = '') -> tuple[str, str]:
    """Repair the one violation that can be repaired without rewriting teaching.

    Returns ``(text, action)`` where action is ``'ok'``, ``'appended_probe'`` or
    ``'flagged'``. Appending is additive and visible; deleting or regenerating
    would replace the teacher's words with a template's, which is the failure this
    gate exists to prevent, not a fix for it.
    """
    violations = check(text, reading)
    if not violations:
        return text, 'ok'
    if 'no_question' in violations:
        question = probe_question(title)
        separator = '\n\n' if str(text).strip() else ''
        return f'{str(text).rstrip()}{separator}{question}', 'appended_probe'
    return text, 'flagged'
