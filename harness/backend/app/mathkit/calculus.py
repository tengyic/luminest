"""Figures for calculus and the later Algebra 2 topics.

Why this module exists
----------------------
``templates.py`` was written against the authored mathematics course. Its rules key
off that course's vocabulary (fractions, percent, quadratics, systems), and every one
of the 164 authored concepts matches a real rule. When AP Calculus and Algebra 2 were
added to the registry they inherited the same symbolic engine, but their vocabulary
was not covered: 62% of AP Calculus and 18% of Algebra 2 fell through to
``_generic``, the quadratic probe.

The result was exactly the failure ``figures.py`` documents at the top of the file:
"Absolute and conditional convergence" was drawn as ``0.5x^2 - x + 1`` and labelled
with the concept's name. Nothing errored; a learner would have been shown a
meaningless parabola presented as calculus.

So each family below draws the thing its concept is actually about:

* a **limit** is a hole approached from both sides, not a parabola;
* a **derivative** is a secant whose second point slides towards the first, and a
  tangent line whose slope is reported;
* a **shape** question is f plotted against f', so the sign of the derivative and the
  direction of the curve can be read off together;
* an **integral** is an accumulation function beside the rate it accumulates;
* a **series** is its partial sums as a sequence of dots, with the limit it approaches.

Every builder states its own reasoning through ``explain``. That matters: the generic
explainer describes whatever curve happens to be drawn, which is how a parabola ends
up being explained as if it were a convergence test.

Nothing here invents a value. Slider positions are exact inputs; every readout is
computed from them with the same arithmetic the learner is being asked to do.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping

from .simulate import Mark, Parameter, SimulationSpec  # noqa: F401  (Mark kept for reuse)


def _seed(concept_id: str) -> int:
    """Mirrors ``templates._seed`` so coefficient choice is stable across restarts."""
    return int(hashlib.sha256(concept_id.encode('utf-8')).hexdigest()[:8], 16)


def _pick(concept_id: str, salt: str, low: int, high: int) -> int:
    span = high - low + 1
    return low + (_seed(concept_id + salt) % span)


def _nonzero(concept_id: str, salt: str, low: int, high: int) -> int:
    value = _pick(concept_id, salt, low, high)
    return value if value != 0 else high


def _num(value: float) -> str:
    """A compact number for prose, without a trailing ``.0``."""
    return f'{value:g}'


# --------------------------------------------------------------------- limits


def _limit_hole(concept_id: str) -> SimulationSpec:
    """A removable discontinuity: the limit exists, the function value does not.

    ``(x^2 - c^2)/(x - c)`` is undefined at ``c`` (0/0) and equals ``x + c``
    everywhere else, so the sampler produces a genuine gap at exactly the point the
    concept is about.
    """
    c = _nonzero(concept_id, 'c', -3, 3)
    g = _pick(concept_id, 'g', -2, 2)
    limit = 2 * c + g

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        offset = env.get('g', g)
        at = 2 * c + offset
        probe = env.get('x', 2)
        steps = [
            f'This rule is undefined at x = {c}: substituting gives 0/0, which is not a '
            'number, so the curve has a hole there rather than a value.',
            f'Factorising the top as (x − {c})(x + {c}) cancels the (x − {c}) for every '
            f'x except {c}, which leaves x + {c}. That cancelled form is what the curve '
            'follows on both sides of the hole.',
            f'Both sides therefore approach {_num(at)}. That shared value is the limit: '
            f'lim x→{c} f(x) = {_num(at)}, even though f({c}) is undefined.',
            'A limit is about the values nearby, not the value at the point. That is the '
            'whole idea of limit notation, and it is why the hole can sit at any height '
            'you like while the limit stays where it is.',
        ]
        readouts = [
            {'label': 'Left-hand limit', 'value': _num(at), 'detail': f'Approaching x = {c} from below.'},
            {'label': 'Right-hand limit', 'value': _num(at), 'detail': f'Approaching x = {c} from above.'},
            {'label': 'f at the point', 'value': 'undefined', 'detail': '0/0 is not a number.'},
            {'label': 'Probe f(x)', 'value': _num(probe + c + offset), 'detail': f'At x = {_num(probe)}, away from the hole.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='limit_hole',
        expression=f'(x^2 - {c * c})/(x - ({c})) + g',
        variable='x',
        parameters=[Parameter('g', 'Height offset g', -3, 3, g, step=1, integer=True),
                    Parameter('x', 'Probe input x', -5, 5, c + 2)],
        domain=(-6, 6),
        title='A limit at a hole',
        objective='The limit is the value the outputs approach, which can exist even where '
                  'the function itself is undefined.',
        explain=explain,
        notes=[f'The gap in the curve is x = {c}. It is a missing input, not a missing output, '
               'and the two one-sided limits still agree.'],
    )


def _jump(concept_id: str) -> SimulationSpec:
    """A jump discontinuity: both one-sided limits exist but differ."""
    c = _nonzero(concept_id, 'c', -3, 3)
    a = _pick(concept_id, 'a', 1, 3)
    b = _pick(concept_id, 'b', -2, 2)
    left, right = b - a, b + a

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        scale = env.get('a', a)
        lo, hi = b - scale, b + scale
        steps = [
            f'The rule takes one value below x = {c} and another above it. Approaching from '
            f'the left the outputs settle at {_num(lo)}; from the right they settle at {_num(hi)}.',
            f'Both one-sided limits exist, so this is not a vertical asymptote. They disagree, '
            f'which is what makes the limit itself fail to exist at {c}.',
            'A jump is one of three ways continuity can break: the value can be missing '
            '(a hole), it can be at the wrong height, or the two sides can disagree like this. '
            'Only the last one is a jump.',
            f'The size of the jump is {_num(hi)} − ({_num(lo)}) = {_num(hi - lo)}. Change the '
            'scale slider and the jump widens or narrows while the two levels stay put.',
        ]
        readouts = [
            {'label': 'Left-hand limit', 'value': _num(lo), 'detail': f'x → {c}⁻.'},
            {'label': 'Right-hand limit', 'value': _num(hi), 'detail': f'x → {c}⁺.'},
            {'label': 'Two-sided limit', 'value': 'does not exist', 'detail': 'The sides disagree.'},
            {'label': 'Jump size', 'value': _num(hi - lo), 'detail': 'Right limit minus left limit.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='jump',
        expression=f'a*abs(x - ({c}))/(x - ({c})) + {b}',
        variable='x',
        parameters=[Parameter('a', 'Half the jump a', 0.5, 3, a),
                    Parameter('x', 'Probe input x', -5, 5, c + 2)],
        domain=(-6, 6),
        title='A jump discontinuity',
        objective='A jump happens when both one-sided limits exist but are not equal, so the '
                  'two-sided limit does not exist.',
        explain=explain,
        notes=[f'At x = {c} the expression divides zero by zero, so the point itself is undefined '
               'as well as the limit.'],
    )


def _corner(concept_id: str) -> SimulationSpec:
    """Continuous but not differentiable: the two one-sided slopes disagree."""
    c = _nonzero(concept_id, 'c', -3, 3)
    a = _pick(concept_id, 'a', 1, 3)
    b = _pick(concept_id, 'b', -2, 2)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        scale = env.get('a', a)
        steps = [
            f'The curve is unbroken at x = {c}: both sides meet at the same point, so the '
            'function is continuous there.',
            f'Its slope is not. Coming from the left every step falls at rate −{_num(scale)}; '
            f'coming from the right every step rises at rate +{_num(scale)}.',
            'Differentiability needs the difference quotient to settle on one value as h → 0. '
            'Here the left quotient approaches one number and the right quotient its negative, '
            'so no single slope exists.',
            'That is the point of the pair: continuity is required for differentiability but '
            'does not guarantee it. A corner is the smallest example that shows the gap.',
        ]
        readouts = [
            {'label': 'Value at the corner', 'value': _num(b), 'detail': 'Both sides agree.'},
            {'label': 'Slope from the left', 'value': _num(-scale), 'detail': 'Constant below the corner.'},
            {'label': 'Slope from the right', 'value': _num(scale), 'detail': 'Constant above the corner.'},
            {'label': 'Derivative at the corner', 'value': 'does not exist', 'detail': 'The one-sided slopes differ.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='corner',
        expression=f'a*abs(x - ({c})) + {b}',
        variable='x',
        parameters=[Parameter('a', 'Steepness a', 0.5, 3, a),
                    Parameter('x', 'Probe input x', -5, 5, c + 2)],
        domain=(-6, 6),
        title='Continuous but not differentiable',
        objective='A corner is continuous, but the slope from the left and the slope from the '
                  'right disagree, so no derivative exists there.',
        explain=explain,
        notes=[f'The corner sits at x = {c}. Flatten the steepness slider and the two slopes '
               'still disagree in sign however small they get.'],
    )


def _limits_infinity(concept_id: str) -> SimulationSpec:
    """A horizontal asymptote read off a ratio of linear terms."""
    c = _nonzero(concept_id, 'c', -4, 4)
    b = _pick(concept_id, 'b', -4, 4)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        offset = env.get('b', b)
        steps = [
            f'Divide top and bottom by x: the rule becomes ({_num(a)} + {_num(offset)}/x) / '
            f'(1 + ({c})/x). As x grows without bound, every term with x in the denominator '
            'shrinks to zero.',
            f'What survives is the ratio of the two leading coefficients, so the limit at '
            f'infinity is {_num(a)}. That is the height of the horizontal asymptote, on both '
            'sides because the same argument works for large negative x.',
            f'The denominator is zero at x = {_num(-c)}, which is a vertical asymptote — a '
            'different question entirely. One is about far-away behaviour, the other about a '
            'single excluded input.',
            'Change a and the asymptote moves; change b and the curve shifts shape but still '
            'levels off at the same height. That is what makes the leading terms the ones that '
            'decide the end behaviour.',
        ]
        readouts = [
            {'label': 'Limit as x → ∞', 'value': _num(a), 'detail': 'Ratio of leading coefficients.'},
            {'label': 'Limit as x → −∞', 'value': _num(a), 'detail': 'Same, for the same reason.'},
            {'label': 'Horizontal asymptote', 'value': f'y = {_num(a)}', 'detail': 'The level the curve approaches.'},
            {'label': 'Vertical asymptote', 'value': f'x = {_num(-c)}', 'detail': 'Where the denominator vanishes.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='limits_infinity',
        expression=f'(a*x + b)/(x + ({c}))',
        variable='x',
        parameters=[Parameter('a', 'Leading coefficient a', -3, 3, 1, step=0.5),
                    Parameter('b', 'Constant b', -4, 4, b, step=1, integer=True),
                    Parameter('x', 'Probe input x', -10, 10, 6)],
        domain=(-12, 12),
        title='Behaviour at infinity',
        objective='For a ratio of polynomials, the limit at infinity is decided by the leading '
                  'terms, not by the smaller ones.',
        explain=explain,
        notes=[f'There is a vertical asymptote at x = {_num(-c)}; the curve is not defined there.'],
    )


def _squeeze(concept_id: str) -> SimulationSpec:
    """An oscillating function pinned between two envelopes."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        scale = env.get('k', 1)
        steps = [
            'The factor sin(1/x) swings between −1 and +1 and never settles. On its own that '
            'oscillation has no limit at zero.',
            f'Multiplying by x² changes the picture: the whole oscillation is trapped between '
            f'−{_num(scale)}x² and +{_num(scale)}x², the two envelopes drawn here.',
            'Both envelopes meet at zero as x → 0. Anything trapped between two curves that '
            'meet at the same point has nowhere to go but that point, so the limit is 0 even '
            'though the function never stops oscillating.',
            'This is the squeeze theorem: bounding a function between two others that share a '
            'limit forces the same limit, without ever needing to evaluate the function at the '
            'awkward point.',
        ]
        readouts = [
            {'label': 'Lower bound', 'value': f'−{_num(scale)}x²', 'detail': 'The envelope below.'},
            {'label': 'Upper bound', 'value': f'{_num(scale)}x²', 'detail': 'The envelope above.'},
            {'label': 'Both bounds at 0', 'value': '0', 'detail': 'They meet there.'},
            {'label': 'Squeezed limit', 'value': '0', 'detail': 'Forced by the bounds.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='squeeze',
        expression='k*x^2*sin(1/x)',
        variable='x',
        secondary='k*x^2',
        parameters=[Parameter('k', 'Envelope scale k', 0.2, 2, 1),
                    Parameter('x', 'Probe input x', -2, 2, 0.5)],
        domain=(-2.5, 2.5),
        samples=480,
        title='Trapped between two envelopes',
        objective='A function squeezed between two others that share a limit must have that '
                  'same limit.',
        explain=explain,
        notes=['The oscillation never dies out; it is the shrinking envelope, not the '
               'oscillation, that forces the limit.'],
    )


def _lhopital(concept_id: str) -> SimulationSpec:
    """An indeterminate 0/0 ratio whose limit is the ratio of derivatives."""
    a = _pick(concept_id, 'a', 1, 3)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        rate = env.get('a', a)
        steps = [
            f'At x = 0 both the top and the bottom are zero, so substituting gives 0/0 — an '
            'indeterminate form, not a value. The curve has a hole there.',
            'The limit is not decided by the values at 0 but by how fast each side leaves 0. '
            f'The top leaves at rate {_num(rate)} and the bottom at rate {_num(rate)} as well.',
            'L\'Hôpital\'s rule makes that precise: for 0/0, the limit of the ratio equals the '
            'limit of the ratio of the derivatives, provided that second limit exists. Here it '
            f'is {_num(rate)}/{_num(rate)} = 1.',
            'The rule is not a trick that replaces algebra; it is a statement about the linear '
            'approximations near the point. That is why it only applies when both sides go to '
            '0 or both go to infinity.',
        ]
        readouts = [
            {'label': 'Form at x = 0', 'value': '0/0', 'detail': 'Indeterminate.'},
            {'label': 'Derivative of the top', 'value': _num(rate), 'detail': 'Rate of leaving zero.'},
            {'label': 'Derivative of the bottom', 'value': _num(rate), 'detail': 'Same rate.'},
            {'label': 'Limit', 'value': '1', 'detail': 'The ratio of the two rates.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='lhopital',
        expression='(exp(a*x) - 1)/(a*x)',
        variable='x',
        parameters=[Parameter('a', 'Rate a', 0.5, 2, a),
                    Parameter('x', 'Probe input x', -3, 3, 1)],
        domain=(-4, 4),
        title='An indeterminate ratio',
        objective='A 0/0 form has no value at the point, but the ratio of the derivatives '
                  'decides its limit.',
        explain=explain,
        notes=['The gap at x = 0 is the indeterminate point; the curve approaches 1 from both '
               'sides.'],
    )


# ----------------------------------------------------------------- derivatives


def _secant_tangent(concept_id: str) -> SimulationSpec:
    """The derivative as the limit of a secant slope as h shrinks."""
    c = _nonzero(concept_id, 'c', -2, 2)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        h = env.get('h', 1)
        slope = a * (2 * c + h)
        exact = 2 * a * c
        steps = [
            f'The straight line through ({c}, f({c})) and ({_num(c + h)}, f({_num(c + h)})) is a '
            'secant. Its slope is the average rate of change over that gap of h.',
            f'Here the average rate is {_num(slope)}. It is not the slope at a point — it is the '
            'slope over an interval, and it depends on h.',
            f'Slide h towards zero. The second point slides towards the first and the secant '
            f'slope tends to {_num(exact)}, which is the slope of the tangent at x = {c}.',
            'That limit is the definition of the derivative: f\'(c) is the number the secant '
            'slopes approach, and the tangent line is the line with that slope through the point. '
            'Everything the differentiation rules do is compute this limit without redoing it.',
        ]
        readouts = [
            {'label': 'Step size h', 'value': _num(h), 'detail': 'The gap between the two points.'},
            {'label': 'Secant slope', 'value': _num(slope), 'detail': 'Average rate over the gap.'},
            {'label': 'Tangent slope', 'value': _num(exact), 'detail': 'The limit as h → 0.'},
            {'label': 'Difference', 'value': _num(slope - exact), 'detail': 'Shrinks in proportion to h.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='secant',
        expression='a*x^2',
        variable='x',
        secondary=f'a*({c})^2 + a*(2*({c}) + h)*(x - ({c}))',
        parameters=[Parameter('a', 'Curvature a', 0.2, 2, 1),
                    Parameter('h', 'Step size h', 0.1, 3, 1.5),
                    Parameter('x', 'Probe input x', -5, 5, 2)],
        domain=(-5, 5),
        title='Secant slope tending to tangent slope',
        objective='The derivative is the number the average rate of change approaches as the '
                  'interval shrinks to a point.',
        explain=explain,
        notes=[f'The straight line is the secant through x = {c} and x = {c} + h; the curve is '
               'f itself. Shrink h and watch the two lines meet.'],
    )


def _tangent_line(concept_id: str) -> SimulationSpec:
    """A tangent line at a point on a cubic, with its slope reported."""
    c = _nonzero(concept_id, 'c', -2, 2)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        b = env.get('b', 1)
        slope = 3 * a * c * c + b
        value = a * c ** 3 + b * c
        steps = [
            f'At x = {c} the curve passes through {_num(value)}, and the straight line drawn '
            'through that point with the same slope is the tangent.',
            f'Its slope here is {_num(slope)}. That number is f\'({c}), and it is the local rate '
            'of change: how fast the output moves per unit of input, right at that point.',
            'The rules for constants, sums, products, quotients and compositions are all ways of '
            'getting this number without returning to the difference quotient each time. They '
            'are shortcuts to the same limit, so they must agree with it.',
            f'Near x = {c} the tangent is a good stand-in for the curve — that is what makes it '
            'useful for estimating. Move c and the slope changes, which is exactly why the '
            'derivative is itself a function rather than a single number.',
        ]
        readouts = [
            {'label': 'Point on the curve', 'value': f'({c}, {_num(value)})', 'detail': 'Where the tangent touches.'},
            {'label': 'Slope f′(c)', 'value': _num(slope), 'detail': 'Local rate of change.'},
            {'label': 'Tangent line', 'value': f'y = {_num(value)} + {_num(slope)}(x − {c})', 'detail': 'Point-slope form.'},
            {'label': 'Second derivative', 'value': _num(6 * a * c), 'detail': 'The rate at which the slope itself changes.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='tangent',
        expression='a*x^3 + b*x',
        variable='x',
        secondary=f'a*({c})^3 + b*({c}) + (3*a*({c})^2 + b)*(x - ({c}))',
        parameters=[Parameter('a', 'Cubic coefficient a', 0.1, 1, 0.5),
                    Parameter('b', 'Linear coefficient b', -3, 3, 1, step=1, integer=True),
                    Parameter('x', 'Probe input x', -4, 4, 1)],
        domain=(-4, 4),
        title='The tangent at a point',
        objective='The derivative at a point is the slope of the tangent there, and the tangent '
                  'is the best straight-line stand-in for the curve nearby.',
        explain=explain,
        notes=[f'The tangent touches at x = {c}. The differentiation rules exist to produce this '
               'slope without re-deriving the limit each time.'],
    )


def _tangent_trig(concept_id: str) -> SimulationSpec:
    """A tangent on a sine wave: the derivative of sin is cos."""
    c = _nonzero(concept_id, 'c', -2, 2)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        b = env.get('b', 1)
        angle = b * c
        slope = a * b * math.cos(angle)
        value = a * math.sin(angle)
        steps = [
            f'The curve is a·sin(b·x). At x = {c} the angle is {_num(angle)} radians and the '
            f'height is {_num(value)}.',
            f'The slope there is {_num(slope)}. Differentiating sin gives cos, and the inner b '
            'multiplies out in front, so the derivative is a·b·cos(b·x).',
            'Read the shape rather than the formula: at a peak the tangent is flat, and cos is '
            'zero a quarter-turn from where sin is greatest. The derivative curve is the same '
            'wave shifted, which is why the tangent slope rises and falls with the height.',
            'The factor b is the chain rule in plain sight: stretching the input horizontally '
            'makes the output change b times faster per unit of x.',
        ]
        readouts = [
            {'label': 'Angle b·x', 'value': f'{_num(angle)} rad', 'detail': 'The input in radians.'},
            {'label': 'Height f(x)', 'value': _num(value), 'detail': 'a·sin(b·x).'},
            {'label': 'Slope f′(x)', 'value': _num(slope), 'detail': 'a·b·cos(b·x).'},
            {'label': 'Steepest slope', 'value': _num(abs(a * b)), 'detail': 'Reached where cos = ±1.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='tangent_trig',
        expression='a*sin(b*x)',
        variable='x',
        secondary=f'a*sin(b*({c})) + a*b*cos(b*({c}))*(x - ({c}))',
        parameters=[Parameter('a', 'Amplitude a', 0.5, 3, 1),
                    Parameter('b', 'Frequency b', 0.5, 2, 1),
                    Parameter('x', 'Probe input x', -4, 4, 1)],
        domain=(-4.5, 4.5),
        title='Slope along a sine wave',
        objective='The derivative of a sine wave is a cosine wave of the same frequency, scaled '
                  'by the inner rate.',
        explain=explain,
        notes=[f'The tangent touches at x = {c}. At a crest the slope is zero, which is where the '
               'cosine factor vanishes.'],
    )


def _shape(concept_id: str) -> SimulationSpec:
    """f beside f', so direction, turning points and concavity read off together."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 0.5)
        b = env.get('b', 1)
        c = env.get('c', 1)
        probe = env.get('x', 0)
        first = 3 * a * probe ** 2 + 2 * b * probe + c
        second = 6 * a * probe + 2 * b
        discriminant = (2 * b) ** 2 - 4 * (3 * a) * c
        if discriminant > 0:
            turning = ('two turning points, at x = '
                       + _num((-2 * b - math.sqrt(discriminant)) / (6 * a))
                       + ' and x = ' + _num((-2 * b + math.sqrt(discriminant)) / (6 * a)))
        elif abs(discriminant) < 1e-9:
            turning = 'exactly one turning point, where the derivative only touches zero'
        else:
            turning = 'no turning point, because the derivative never reaches zero'
        direction = 'rising' if first > 0 else ('falling' if first < 0 else 'momentarily flat')
        bend = 'concave up' if second > 0 else ('concave down' if second < 0 else 'momentarily straight')
        steps = [
            f'The upper curve is f and the lower one is its derivative f\'. Where f\' is positive '
            f'the curve is rising; where it is negative the curve is falling. At the probe it is '
            f'{direction} because f\'({_num(probe)}) = {_num(first)}.',
            f'Where f\' crosses zero the direction reverses. This cubic has {turning} — read them '
            'off the lower curve rather than guessing from the picture.',
            f'The second derivative is the slope of f\'. Here f\'\'({_num(probe)}) = {_num(second)}, '
            f'so the curve is {bend} at the probe. Concavity is about how the slope is changing, '
            'not about whether the curve is going up or down.',
            'Together those two signs classify a turning point: f\' = 0 with f\'\' < 0 is a local '
            'maximum, f\' = 0 with f\'\' > 0 is a local minimum, and f\'\' = 0 is inconclusive and '
            'needs the sign change of f\' instead.',
        ]
        readouts = [
            {'label': 'f at the probe', 'value': _num(a * probe ** 3 + b * probe ** 2 + c * probe), 'detail': 'Height of the curve.'},
            {'label': 'f′ at the probe', 'value': _num(first), 'detail': direction.capitalize() + '.'},
            {'label': 'f″ at the probe', 'value': _num(second), 'detail': bend.capitalize() + '.'},
            {'label': 'Turning points', 'value': turning.split(',')[0], 'detail': 'Where f′ = 0.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='shape',
        expression='a*x^3 + b*x^2 + c*x',
        variable='x',
        secondary='3*a*x^2 + 2*b*x + c',
        parameters=[Parameter('a', 'Cubic coefficient a', 0.1, 1, 0.5),
                    Parameter('b', 'Quadratic coefficient b', -3, 3, 1, step=1, integer=True),
                    Parameter('c', 'Linear coefficient c', -4, 4, 1, step=1, integer=True),
                    Parameter('x', 'Probe input x', -3, 3, 0)],
        domain=(-4, 4),
        title='A curve beside its derivative',
        objective='The sign of the derivative gives the direction, its zeros give the turning '
                  'points, and its own slope gives the concavity.',
        explain=explain,
        notes=['The lower curve is f′, not a second copy of f. Reading the two together is the '
               'point of the figure.'],
    )


# ------------------------------------------------------------------- integrals


def _accumulation(concept_id: str) -> SimulationSpec:
    """A rate beside the total it accumulates — the fundamental theorem, drawn."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        b = env.get('b', 1)
        probe = env.get('x', 2)
        rate = a * probe + b
        total = a / 2 * probe ** 2 + b * probe
        steps = [
            'The straight line is the rate f, and the curve is A(x), the area accumulated from 0 '
            'to x. A is not f scaled — it is the running total of f.',
            f'At x = {_num(probe)} the rate is {_num(rate)} per unit, and the accumulated total is '
            f'{_num(total)}. The total grows fastest exactly where the rate is largest.',
            f'The fundamental theorem is the statement that A\'(x) = f(x). The slope of the '
            f'accumulation curve at the probe is {_num(rate)}, which is precisely the height of '
            'the rate line there.',
            'That is why integrating and differentiating undo each other, and why an indefinite '
            'integral carries a constant: shifting the whole accumulation curve up or down does '
            'not change its slope, so the derivative cannot tell you where it started.',
        ]
        readouts = [
            {'label': 'Rate at the probe', 'value': _num(rate), 'detail': 'Height of f.'},
            {'label': 'Accumulated total', 'value': _num(total), 'detail': 'Area under f from 0.'},
            {'label': 'Slope of the total', 'value': _num(rate), 'detail': 'Equal to the rate — the FTC.'},
            {'label': 'Net change', 'value': f'{_num(total)} over [0, {_num(probe)}]', 'detail': 'Signed area, not absolute area.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='accumulation',
        expression='a*x + b',
        variable='x',
        secondary='a/2*x^2 + b*x',
        parameters=[Parameter('a', 'Rate slope a', -3, 3, 1, step=0.5),
                    Parameter('b', 'Starting rate b', -3, 3, 1, step=1, integer=True),
                    Parameter('x', 'Probe input x', 0, 5, 2)],
        domain=(0, 5),
        title='A rate and the total it builds',
        objective='The definite integral accumulates the rate, and its derivative gives the rate '
                  'back.',
        explain=explain,
        notes=['The line is the rate and the curve is the accumulated total. Their relationship is '
               'the fundamental theorem of calculus.'],
    )


def _improper(concept_id: str) -> SimulationSpec:
    """1/x^p over an unbounded interval: convergence decided by p alone."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        p = env.get('p', 1)
        if p > 1.0001:
            verdict = f'converges, to a finite tail area of 1/(p − 1) = {_num(1 / (p - 1))}'
        elif p < 0.9999:
            verdict = 'diverges — the tail keeps adding more than a fixed amount'
        else:
            verdict = 'diverges, but only just: the tail grows like ln of the endpoint'
        steps = [
            f'The shaded tail is the area under 1/x^p from 1 outwards. The question is whether '
            f'that area is finite, and for p = {_num(p)} it {verdict}.',
            'The rule is decided by the exponent alone. Above 1 each new strip shrinks fast '
            'enough for the total to settle; at or below 1 the strips shrink too slowly and the '
            'total grows without bound.',
            f'p = 1 is the boundary case, and it is the one worth remembering: the curve still '
            'falls to zero, yet the area under it does not stop growing. A function going to '
            'zero is not enough to make its integral finite.',
            'This is also the reasoning behind the integral test for series: for a positive, '
            'decreasing function the sum and the integral either both converge or both diverge, '
            'so the exponent settles the series too.',
        ]
        readouts = [
            {'label': 'Exponent p', 'value': _num(p), 'detail': 'The only thing that decides it.'},
            {'label': 'Tail area', 'value': _num(1 / (p - 1)) if p > 1.0001 else 'infinite',
             'detail': 'Area from 1 to infinity.'},
            {'label': 'Verdict', 'value': 'converges' if p > 1.0001 else 'diverges',
             'detail': 'Threshold at p = 1.'},
            {'label': 'Boundary case', 'value': 'p = 1', 'detail': 'Grows like ln, so it diverges.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='improper',
        expression='1/x^p',
        variable='x',
        parameters=[Parameter('p', 'Exponent p', 0.4, 2.4, 1, step=0.1),
                    Parameter('x', 'Probe input x', 1, 8, 3)],
        domain=(0.25, 8),
        samples=360,
        title='An unbounded tail',
        objective='Whether the area out to infinity is finite depends on how fast the integrand '
                  'falls, and the exponent decides that.',
        explain=explain,
        notes=['The vertical asymptote at x = 0 is a separate improperness from the unbounded '
               'interval; both are decided by the same exponent.'],
    )


# ---------------------------------------------------------------------- series


def _partial_sums(concept_id: str) -> SimulationSpec:
    """Partial sums of a geometric series, as a sequence of dots."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        r = env.get('r', 0.5)
        if abs(r) < 0.9999:
            limit_text = f'settles on 1/(1 − r) = {_num(1 / (1 - r))}'
            verdict = 'converges'
        else:
            limit_text = 'never settles — each term is as large as the last'
            verdict = 'diverges'
        steps = [
            'Each dot is a partial sum: the total after n terms, not the nth term. The series is '
            'the sequence of those totals.',
            f'With ratio r = {_num(r)} the totals {limit_text}. Adding a term always changes the '
            'total, so convergence is a statement about the totals closing in on a value, not '
            'about the terms becoming small.',
            'The formula is exact: the sum after n terms is (1 − rⁿ)/(1 − r). As n grows, rⁿ '
            'vanishes when |r| < 1, which leaves 1/(1 − r) — the height the dots approach.',
            'At r = 1 the formula divides by zero and the dots march off at a constant step, '
            'which is what divergence looks like: the totals grow without approaching anything.',
        ]
        readouts = [
            {'label': 'Ratio r', 'value': _num(r), 'detail': 'Each term is r times the previous.'},
            {'label': 'Verdict', 'value': verdict, 'detail': 'Converges only for |r| < 1.'},
            {'label': 'Limit of the totals', 'value': _num(1 / (1 - r)) if abs(r) < 0.9999 else 'none',
             'detail': '1/(1 − r).'},
            {'label': 'Sum after 18 terms', 'value': _num((1 - r ** 18) / (1 - r)) if abs(r - 1) > 1e-9 else 'undefined',
             'detail': 'Where the dots have reached.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='partial_sums',
        expression='(1 - r^n)/(1 - r)',
        variable='n',
        parameters=[Parameter('r', 'Common ratio r', 0.2, 1.4, 0.5, step=0.05)],
        domain=(1, 18),
        # One sample per integer: a discrete plot with the default sample count would
        # place thirteen copies of every dot on top of each other.
        samples=18,
        discrete=True,
        title='Partial sums closing in',
        objective='A series converges when its partial sums approach a value, which for a '
                  'geometric series happens exactly when the ratio is smaller than one in size.',
        explain=explain,
        notes=['Each dot is a running total, not a term. The gap to the limiting height is the '
               'remainder after that many terms.'],
    )


def _alternating_sums(concept_id: str) -> SimulationSpec:
    """Alternating geometric partial sums: oscillation that still converges."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        r = env.get('r', 0.5)
        steps = [
            'The signs alternate, so each dot is a running total that overshoots the limit and '
            'then comes back. The totals do not settle monotonically; they close in from both '
            'sides.',
            f'With ratio −{_num(r)} the totals approach 1/(1 + r) = {_num(1 / (1 + r))}. '
            'Alternation changes the route, not whether there is a destination.',
            'The alternating series test requires the term sizes to decrease to zero. Here they '
            f'shrink by a factor of {_num(r)} each time, so the condition holds and the series '
            'converges.',
            'Absolute convergence is a stronger question: does the series of term sizes converge '
            'too? For a geometric ratio it does whenever |r| < 1, so this example converges '
            'absolutely. The standard conditional example is 1 − 1/2 + 1/3 − …, whose term sizes '
            'form the divergent harmonic series — that case is not drawn here.',
        ]
        readouts = [
            {'label': 'Ratio', 'value': f'−{_num(r)}', 'detail': 'Alternating sign.'},
            {'label': 'Limit', 'value': _num(1 / (1 + r)), 'detail': '1/(1 − r) with r negative.'},
            {'label': 'Term sizes', 'value': 'decreasing to 0', 'detail': 'The test\'s requirement.'},
            {'label': 'Convergence', 'value': 'absolute', 'detail': 'The term sizes also converge.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='alternating_sums',
        expression='(1 - (0 - r)^n)/(1 + r)',
        variable='n',
        parameters=[Parameter('r', 'Term ratio r', 0.2, 0.95, 0.5, step=0.05)],
        domain=(1, 18),
        samples=18,
        discrete=True,
        title='Alternating partial sums',
        objective='Alternating signs make the partial sums oscillate around the limit while still '
                  'closing in on it.',
        explain=explain,
        notes=['The totals cross the limit repeatedly instead of approaching it from one side. '
               'Both behaviours count as convergence.'],
    )


def _comparison_series(concept_id: str) -> SimulationSpec:
    """A series bounded above by one known to converge."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        r = env.get('r', 0.5)
        steps = [
            f'The upper curve is the geometric series with ratio {_num(r)}, whose partial sums '
            f'approach {_num(1 / (1 - r))}. It is the known series in the comparison.',
            'The lower curve is a series with every term smaller. Its partial sums sit below the '
            'upper ones at every stage, so they cannot run away to infinity while the upper ones '
            'stay bounded.',
            'That is the direct comparison test: bounded above by something convergent means '
            'convergent. A monotone increasing sequence that is bounded must converge, and the '
            'bound supplies the bound.',
            'The direction matters. Comparing to something smaller proves nothing about '
            'divergence, and comparing a smaller series to a divergent one proves nothing about '
            'convergence. Only the helpful direction is shown here.',
        ]
        readouts = [
            {'label': 'Comparison series', 'value': f'ratio {_num(r)}', 'detail': 'Known to converge.'},
            {'label': 'Its limit', 'value': _num(1 / (1 - r)), 'detail': '1/(1 − r).'},
            {'label': 'Test series', 'value': f'ratio {_num(r * r)}', 'detail': 'Smaller at every term.'},
            {'label': 'Conclusion', 'value': 'converges', 'detail': 'Bounded by a convergent series.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='comparison_series',
        expression='(1 - r^n)/(1 - r)',
        variable='n',
        secondary='(1 - (r*r)^n)/(1 - r*r)',
        parameters=[Parameter('r', 'Upper ratio r', 0.2, 0.9, 0.6, step=0.05)],
        domain=(1, 18),
        samples=18,
        discrete=True,
        title='Bounded by a known series',
        objective='A series whose terms are smaller than a convergent series must also converge.',
        explain=explain,
        notes=['The lower dots are the test series and the upper dots the comparison series; the '
               'gap between them never closes, but neither total escapes.'],
    )


def _sequence_terms(concept_id: str) -> SimulationSpec:
    """The terms of a geometric sequence, and what their limit does and does not prove."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        r = env.get('r', 0.5)
        last = a * r ** 18
        if abs(r) < 0.9999:
            terms = f'shrink towards 0, reaching {_num(last)} by n = 18'
        elif r > 1:
            terms = 'grow without bound, so the sequence diverges'
        else:
            terms = 'stay at a fixed size, so the sequence does not settle on a single value'
        steps = [
            'Each dot is a single term, not a running total. This figure is about the sequence of '
            'terms; the series figure is about their sums.',
            f'With ratio r = {_num(r)} the terms {terms}. A geometric sequence converges only when '
            'the ratio is smaller than one in size.',
            'The nth-term test says that if the terms do not approach zero, the series cannot '
            'converge. It is a one-way test: terms approaching zero does not prove the series '
            'converges. The harmonic series is the standard counterexample.',
            'That asymmetry is the point. "Terms go to zero" is necessary and cheap to check; '
            '"terms go to zero fast enough" is the real question, and it needs a separate test.',
        ]
        readouts = [
            {'label': 'First term', 'value': _num(a), 'detail': 'At n = 1.'},
            {'label': 'Ratio r', 'value': _num(r), 'detail': 'Each term is r times the last.'},
            {'label': 'Term at n = 18', 'value': _num(last), 'detail': 'Where the dots have reached.'},
            {'label': 'nth-term test', 'value': 'terms → 0' if abs(r) < 0.9999 else 'terms do not → 0',
             'detail': 'Necessary for convergence, not sufficient.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='sequence_terms',
        expression='a*r^n',
        variable='n',
        parameters=[Parameter('a', 'First term a', 1, 5, 1, step=1, integer=True),
                    Parameter('r', 'Ratio r', 0.2, 1.5, 0.5, step=0.05)],
        domain=(1, 18),
        samples=18,
        discrete=True,
        title='The terms of a sequence',
        objective='A sequence converges when its terms approach a single value; the ratio decides '
                  'whether that happens.',
        explain=explain,
        notes=['Dots, not a curve: a sequence is defined at whole-number indices only.'],
    )


# ------------------------------------------------- other coordinate systems


def _polar(concept_id: str) -> SimulationSpec:
    """r as a function of the angle."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        b = env.get('b', 1)
        steps = [
            'This plot shows the radius r against the angle θ — the function, not the polar '
            'picture. The shape in the plane is traced by reading a radius off this curve at '
            'each angle.',
            f'Here r = {_num(a)} + {_num(b)}·cos θ, so the radius runs between {_num(a - abs(b))} '
            f'and {_num(a + abs(b))}. The same curve therefore sits at different distances in '
            'different directions, which is what a non-circular polar graph is.',
            'Where the curve dips below zero the radius is negative, and a negative radius is '
            'drawn on the opposite ray. That is not an error — it is why polar curves can pass '
            'through the origin and reappear on the other side.',
            'Angles are in radians, so a full turn is 2π. The horizontal axis here is the angle, '
            'and the vertical axis is the radius; the polar drawing is a different picture made '
            'from the same information.',
        ]
        readouts = [
            {'label': 'Largest radius', 'value': _num(a + abs(b)), 'detail': 'Where cos θ = ±1.'},
            {'label': 'Smallest radius', 'value': _num(a - abs(b)), 'detail': 'Negative means the opposite ray.'},
            {'label': 'Full turn', 'value': '2π ≈ 6.283 rad', 'detail': 'The width of the plot.'},
            {'label': 'Radius at θ = π/2', 'value': _num(a), 'detail': 'Where cos θ = 0.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='polar',
        expression='a + b*cos(t)',
        variable='t',
        parameters=[Parameter('a', 'Constant radius a', 0.5, 3, 1.5, step=0.5),
                    Parameter('b', 'Cosine amplitude b', 0.5, 3, 1, step=0.5),
                    Parameter('t', 'Angle θ (rad)', 0, 6.28, 1.57)],
        domain=(0, 6.2832),
        samples=360,
        title='Radius as a function of angle',
        objective='A polar curve is a rule for the radius at each angle, and the radius may be '
                  'negative.',
        explain=explain,
        notes=['The horizontal axis is the angle in radians and the vertical axis is the radius, '
               'not x and y.'],
    )


def _motion(concept_id: str) -> SimulationSpec:
    """Position beside velocity, so the derivative can be read as a speed."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        p = env.get('p', 0)
        v = env.get('v', 2)
        a = env.get('a', -1)
        t = env.get('t', 2)
        position = p + v * t + 0.5 * a * t * t
        velocity = v + a * t
        steps = [
            'The curve is position and the line is velocity. Velocity is the derivative of '
            'position, so its height at any time is the slope of the position curve there.',
            f'At t = {_num(t)} the object is at {_num(position)} and moving at {_num(velocity)} per '
            'unit time. A negative velocity means it is moving backwards along the line, not that '
            'it is slowing down.',
            'The velocity crosses zero where the position curve turns around. That instant is the '
            'only time the object is momentarily still, and it is where the motion reverses.',
            f'Acceleration is the slope of the velocity line, here {_num(a)}. It is the second '
            'derivative of position, and it is what changes the velocity rather than the position '
            'directly.',
        ]
        readouts = [
            {'label': 'Position', 'value': _num(position), 'detail': 'Where it is.'},
            {'label': 'Velocity', 'value': _num(velocity), 'detail': 'Slope of the position curve.'},
            {'label': 'Acceleration', 'value': _num(a), 'detail': 'Slope of the velocity line.'},
            {'label': 'Turning time', 'value': _num(-v / a) if a else 'never', 'detail': 'Where velocity is zero.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='motion',
        expression='p + v*t + 0.5*a*t^2',
        variable='t',
        secondary='v + a*t',
        parameters=[Parameter('p', 'Starting position p', 0, 6, 0, step=1, integer=True),
                    Parameter('v', 'Starting velocity v', -4, 6, 4, step=1, integer=True),
                    Parameter('a', 'Acceleration a', -3, 3, -1, step=0.5),
                    Parameter('t', 'Time t', 0, 6, 2)],
        domain=(0, 6),
        title='Position and velocity together',
        objective='Velocity is the rate of change of position, and acceleration is the rate of '
                  'change of velocity.',
        explain=explain,
        notes=['The straight line is velocity, not a second path. A curve that rises while the '
               'line is negative would mean moving backwards while getting further from the start.'],
    )


def _related_rates(concept_id: str) -> SimulationSpec:
    """A composed quantity and its rate, i.e. the chain rule in time."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        k = env.get('k', 1)
        m = env.get('m', 1)
        t = env.get('t', 1)
        inner = k * t + m
        outer = inner ** 2
        rate = 2 * k * inner
        steps = [
            f'The quantity y depends on x, and x depends on time: x = {_num(k)}t + {_num(m)} and '
            'y = x². Neither step is hard on its own; the composition is what needs the chain rule.',
            f'At t = {_num(t)} we have x = {_num(inner)} and y = {_num(outer)}. The inner rate is '
            f'{_num(k)} per unit time, and the outer rate is 2x per unit of x.',
            f'Multiply them: dy/dt = 2x · dx/dt = {_num(rate)} per unit time. Rates along a chain '
            'of dependencies multiply, which is exactly what the chain rule says.',
            'Related-rates problems are this figure in disguise: two quantities linked by an '
            'equation, one of whose rates is known, and the other found by differentiating the '
            'link with respect to time.',
        ]
        readouts = [
            {'label': 'Inner value x', 'value': _num(inner), 'detail': 'k·t + m.'},
            {'label': 'Outer value y', 'value': _num(outer), 'detail': 'x².'},
            {'label': 'dx/dt', 'value': _num(k), 'detail': 'The inner rate.'},
            {'label': 'dy/dt', 'value': _num(rate), 'detail': '2x · dx/dt.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='related_rates',
        expression='(k*t + m)^2',
        variable='t',
        secondary='2*k*(k*t + m)',
        parameters=[Parameter('k', 'Inner rate k', 0.5, 2, 1, step=0.5),
                    Parameter('m', 'Inner offset m', 0, 3, 1, step=1, integer=True),
                    Parameter('t', 'Time t', 0, 4, 1)],
        domain=(0, 4),
        title='Rates multiplying along a chain',
        objective='When one quantity depends on another which depends on time, the rates multiply.',
        explain=explain,
        notes=['The curve is y and the line is dy/dt. The rate grows because x grows, even though '
               'dx/dt is constant.'],
    )


def _implicit(concept_id: str) -> SimulationSpec:
    """A circle and its tangent slope, found without solving for y first."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        r = env.get('r', 3)
        x = env.get('x', 1)
        inside = r * r - x * x
        y = math.sqrt(inside) if inside > 0 else float('nan')
        slope = -x / y if inside > 0 else float('nan')
        steps = [
            f'The curve is the upper half of x² + y² = {_num(r * r)}. It is a relation, not a '
            'function given as y = something, so the usual rules do not apply directly.',
            'Differentiate both sides with respect to x, treating y as a function of x. The y² '
            'term brings out 2y·dy/dx by the chain rule, and the right side differentiates to 0.',
            f'That gives 2x + 2y·dy/dx = 0, so dy/dx = −x/y. At x = {_num(x)} the height is '
            f'{_num(y)} and the slope is {_num(slope)}.',
            'The formula fails where y = 0, at the ends of the diameter, and that is not a defect: '
            'the tangent there is vertical, so the slope really is undefined. The algebra reports '
            'the geometry honestly.',
        ]
        readouts = [
            {'label': 'Radius r', 'value': _num(r), 'detail': 'From x² + y² = r².'},
            {'label': 'Height at x', 'value': _num(y), 'detail': 'The upper branch.'},
            {'label': 'Slope dy/dx', 'value': _num(slope), 'detail': '−x/y.'},
            {'label': 'Where it fails', 'value': 'y = 0', 'detail': 'The tangent is vertical there.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='implicit',
        expression='sqrt(r^2 - x^2)',
        variable='x',
        secondary='0 - x/sqrt(r^2 - x^2)',
        parameters=[Parameter('r', 'Radius r', 2, 5, 3, step=0.5),
                    Parameter('x', 'Probe input x', -4, 4, 1, step=0.5)],
        domain=(-5, 5),
        samples=360,
        title='A slope found without solving for y',
        objective='Implicit differentiation differentiates the relation as it stands, treating y as '
                  'a function of x.',
        explain=explain,
        notes=['The curve stops where x² exceeds r²: outside the circle there is no real height. '
               'The second curve is dy/dx.'],
    )


def _inverse_pair(concept_id: str) -> SimulationSpec:
    """A function and its inverse, with the reciprocal-slope relationship."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        steps = [
            'The parabola is y = x² on the non-negative inputs; the other curve is y = √x. Each is '
            'the other reflected across the line y = x, because swapping input and output is '
            'exactly what an inverse does.',
            'That reflection is why the domain has to be restricted. Over all real inputs x² is '
            'not one-to-one, so it has no inverse; cutting it to x ≥ 0 makes each output come from '
            'a single input.',
            'Slopes reflect too. At the point where the parabola has slope m, the inverse curve has '
            'slope 1/m — a rise of m in one picture becomes a run of m in the other. Steep becomes '
            'shallow and vice versa.',
            'So (f⁻¹)\'(y) = 1 / f\'(x) wherever f\' is not zero. A horizontal tangent on the '
            'original becomes a vertical tangent on the inverse, which is why the reciprocal '
            'formula fails at exactly those points.',
        ]
        readouts = [
            {'label': 'Function', 'value': 'y = x², x ≥ 0', 'detail': 'Restricted to be one-to-one.'},
            {'label': 'Inverse', 'value': 'y = √x', 'detail': 'The reflection across y = x.'},
            {'label': 'Slope at x = 1', 'value': '2 and 1/2', 'detail': 'Reciprocals of each other.'},
            {'label': 'Rule', 'value': '(f⁻¹)′(y) = 1/f′(x)', 'detail': 'Fails where f′ = 0.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='inverse_pair',
        expression='x^2',
        variable='x',
        secondary='sqrt(x)',
        parameters=[Parameter('x', 'Probe input x', 0, 4, 1, step=0.5)],
        domain=(0, 4),
        title='A function and its inverse',
        objective='An inverse undoes the function, which reflects its graph across y = x and '
                  'reciprocates its slopes.',
        explain=explain,
        notes=['The domain is restricted to x ≥ 0 so that the parabola is one-to-one and an '
               'inverse exists.'],
    )


def _composition(concept_id: str) -> SimulationSpec:
    """An inner linear step feeding an outer square."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        b = env.get('b', 1)
        c = env.get('c', 0)
        x = env.get('x', 1)
        inner = b * x + c
        outer = a * inner ** 2
        steps = [
            f'The rule is a·(b·x + c)², which is two functions in sequence: first g(x) = {_num(b)}x '
            f'{c:+g}, then f(u) = {_num(a)}u².',
            f'At x = {_num(x)} the inner step gives {_num(inner)}, and the outer step turns that '
            f'into {_num(outer)}. The order matters — squaring first and shifting afterwards gives '
            'a different curve.',
            'Composition is not multiplication. f(g(x)) and f(x)·g(x) are different functions, and '
            'the notation is the only thing keeping them apart.',
            'The inner function also sets the pace: whatever happens to the input, it happens to '
            'the output faster or slower by the inner rate. That is the observation the chain rule '
            'turns into a formula.',
        ]
        readouts = [
            {'label': 'Inner value g(x)', 'value': _num(inner), 'detail': 'b·x + c.'},
            {'label': 'Outer value f(u)', 'value': _num(outer), 'detail': 'a·u².'},
            {'label': 'Composed rule', 'value': f'{_num(a)}({_num(b)}x {c:+g})²', 'detail': 'f(g(x)).'},
            {'label': 'Inner rate', 'value': _num(b), 'detail': 'How fast the inner step moves.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='composition',
        expression='a*(b*x + c)^2',
        variable='x',
        parameters=[Parameter('a', 'Outer scale a', 0.5, 2, 1, step=0.5),
                    Parameter('b', 'Inner rate b', 0.5, 2, 1, step=0.5),
                    Parameter('c', 'Inner offset c', -3, 3, 0, step=1, integer=True),
                    Parameter('x', 'Probe input x', -3, 3, 1, step=1, integer=True)],
        domain=(-3, 3),
        title='One rule feeding another',
        objective='A composite function applies the inner rule first and the outer rule to its '
                  'result.',
        explain=explain,
        notes=['The vertex moves with c and the steepness with b, so both parts of the composition '
               'are visible in one curve.'],
    )


def _symmetry(concept_id: str) -> SimulationSpec:
    """An odd curve and an even curve, side by side in one plot."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        x = env.get('x', 1)
        steps = [
            'The cubic is odd: replacing x with −x gives exactly the negative of the output. Its '
            'graph has half-turn symmetry about the origin.',
            'The parabola is even: replacing x with −x gives the same output. Its graph is a '
            'mirror image across the vertical axis.',
            'The test is substitution, not appearance. f(−x) = −f(x) means odd, f(−x) = f(x) means '
            'even, and most functions are neither — a curve that looks roughly symmetric is not '
            'evidence of either.',
            f'At x = {_num(x)} the cubic gives {_num(a * x ** 3)} and at −{_num(x)} it gives '
            f'{_num(-a * x ** 3)}. Equal in size, opposite in sign: that is what odd means.',
        ]
        readouts = [
            {'label': 'Odd function', 'value': 'y = a·x³', 'detail': 'f(−x) = −f(x).'},
            {'label': 'Even function', 'value': 'y = a·x²', 'detail': 'f(−x) = f(x).'},
            {'label': 'Odd at ±x', 'value': f'{_num(a * x ** 3)} and {_num(-a * x ** 3)}', 'detail': 'Opposite signs.'},
            {'label': 'Even at ±x', 'value': f'{_num(a * x * x)} both times', 'detail': 'Same value.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='symmetry',
        expression='a*x^3',
        variable='x',
        secondary='a*x^2',
        parameters=[Parameter('a', 'Scale a', 0.2, 2, 1),
                    Parameter('x', 'Probe input x', -3, 3, 1)],
        domain=(-3, 3),
        title='Odd and even symmetry',
        objective='Odd functions satisfy f(−x) = −f(x); even functions satisfy f(−x) = f(x).',
        explain=explain,
        notes=['The cubic is odd and the parabola even. Checking by substitution is the reliable '
               'test; the picture only illustrates it.'],
    )


def _roots(concept_id: str) -> SimulationSpec:
    """A cubic with a repeated root: multiplicity seen as touching versus crossing."""
    r1 = _nonzero(concept_id, 'r1', -2, 2)
    r2 = _nonzero(concept_id, 'r2', -3, 3)
    while r2 == r1:
        r2 += 1

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        steps = [
            f'The rule is a(x − {r1})²(x − {r2}). The root at {r1} appears twice, and the one at '
            f'{r2} appears once.',
            f'At {r1} the curve touches the axis and turns back: an even multiplicity does not '
            'change sign. At ' + f'{r2} it crosses, because an odd multiplicity does.',
            'That is the practical meaning of multiplicity — not a counting curiosity but the '
            'local behaviour of the graph at the root. Change a and the curve stretches '
            'vertically; the roots do not move at all.',
            'Counting multiplicity, this cubic has three roots, which is what the fundamental '
            'theorem of algebra promises: a degree-n polynomial has exactly n complex roots. '
            'Repeated roots are counted repeatedly, and that is what makes the count come out.',
            'A sign change also guarantees a root between the two sides, which is the intermediate '
            'value theorem. The touching root at ' + f'{r1} has no sign change, which is exactly '
            'why the theorem cannot be used to detect it.',
        ]
        readouts = [
            {'label': 'Repeated root', 'value': _num(r1), 'detail': 'Even multiplicity: touches.'},
            {'label': 'Simple root', 'value': _num(r2), 'detail': 'Odd multiplicity: crosses.'},
            {'label': 'Degree', 'value': '3', 'detail': 'So three roots, counted with multiplicity.'},
            {'label': 'Sign change', 'value': f'only at {r2}', 'detail': 'Where the IVT applies.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='roots',
        expression=f'a*(x - ({r1}))^2*(x - ({r2}))',
        variable='x',
        parameters=[Parameter('a', 'Vertical scale a', 0.2, 1.5, 0.6, step=0.1),
                    Parameter('x', 'Probe input x', -4, 4, 0)],
        domain=(-4, 4),
        title='Roots and their multiplicity',
        objective='An even multiplicity makes the curve touch the axis; an odd one makes it cross.',
        explain=explain,
        notes=[f'The root at x = {r1} is repeated and the curve turns there; the root at x = {r2} '
               'is crossed.'],
    )


def _trig_wave(concept_id: str) -> SimulationSpec:
    """Sine and cosine with amplitude and period, in radians."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        b = env.get('b', 1)
        x = env.get('x', 1)
        steps = [
            f'The input is measured in radians, where a full turn is 2π. The sine curve completes '
            f'one turn every 2π/b, which here is {_num(2 * math.pi / b)} — that is the period.',
            f'The height never leaves the band from −{_num(a)} to {_num(a)}. That bound is the '
            'amplitude, and it is the coefficient in front, not something you read off by eye.',
            'The cosine curve is the same wave shifted a quarter-turn earlier. That is why '
            'cos θ = sin(θ + π/2) and why the derivative of sine is cosine: the slope of one is '
            'the height of the other.',
            f'Radians are not a unit choice, they are the natural one: an arc of length 1 on a unit '
            'circle subtends 1 radian. Using degrees would put an arbitrary factor of π/180 into '
            'every derivative.',
        ]
        readouts = [
            {'label': 'Amplitude', 'value': _num(a), 'detail': 'Half the peak-to-peak height.'},
            {'label': 'Period', 'value': _num(2 * math.pi / b), 'detail': '2π/b radians.'},
            {'label': 'At the probe', 'value': f'sin {_num(a * math.sin(b * x))}, cos {_num(a * math.cos(b * x))}', 'detail': 'The two curves.'},
            {'label': 'Full turn', 'value': '2π ≈ 6.283', 'detail': 'In radians.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='trig_wave',
        expression='a*sin(b*x)',
        variable='x',
        secondary='a*cos(b*x)',
        parameters=[Parameter('a', 'Amplitude a', 0.5, 3, 1),
                    Parameter('b', 'Frequency b', 0.5, 2, 1),
                    Parameter('x', 'Probe angle x (rad)', 0, 6.28, 1)],
        domain=(0, 6.2832),
        samples=360,
        title='Sine and cosine in radians',
        objective='Amplitude sets the height, the frequency sets the period, and the two curves are '
                  'the same wave a quarter-turn apart.',
        explain=explain,
        notes=['The horizontal axis is in radians. One full turn is 2π ≈ 6.283.'],
    )


# ---------------------------------------------------------- complex numbers


def _complex_powers(concept_id: str) -> SimulationSpec:
    """Multiplication by a complex number: rotation and scaling together."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        r = env.get('r', 1)
        theta = env.get('theta', 0.5)
        steps = [
            'Multiplying by a complex number does two things at once: it rotates by the number\'s '
            'angle and it scales by its modulus. Repeated multiplication therefore rotates '
            'repeatedly and scales repeatedly.',
            f'With modulus {_num(r)} and angle {_num(theta)} radians, the real part of the nth power '
            f'is rⁿ·cos(nθ). Each dot is one power, so the dots trace that rotation out.',
            'When the modulus is 1 the dots stay on a fixed band and simply rotate — no growth, no '
            'decay, just turning. Above 1 they spiral outwards; below 1 they spiral in. That is '
            'why complex multiplication is usually described as rotation plus scaling rather than '
            'as arithmetic on two separate numbers.',
            'Adding complex numbers is different again: addition is ordinary vector addition, '
            'tail to tip. Multiplication is the operation with the geometric content, and it is '
            'the one this figure is about.',
        ]
        readouts = [
            {'label': 'Modulus', 'value': _num(r), 'detail': 'The scaling factor.'},
            {'label': 'Angle', 'value': f'{_num(theta)} rad', 'detail': 'The rotation per power.'},
            {'label': 'Re(zⁿ) at n = 12', 'value': _num(r ** 12 * math.cos(12 * theta)), 'detail': 'Where the dots end.'},
            {'label': 'Behaviour', 'value': 'bounded' if abs(r - 1) < 1e-9 else ('growing' if r > 1 else 'decaying'),
             'detail': 'Set by the modulus.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='complex_powers',
        expression='r^n*cos(n*theta)',
        variable='n',
        parameters=[Parameter('r', 'Modulus r', 0.7, 1.3, 1, step=0.05),
                    Parameter('theta', 'Angle θ (rad)', 0.2, 1.2, 0.5, step=0.1)],
        domain=(0, 12),
        samples=13,
        discrete=True,
        title='Repeated complex multiplication',
        objective='Multiplying by a complex number rotates and scales, so powers trace a spiral.',
        explain=explain,
        notes=['The dots are successive powers, not a continuous curve. The real part is plotted; '
               'the imaginary part oscillates a quarter-turn out of step.'],
    )


def _complex_conjugate(concept_id: str) -> SimulationSpec:
    """Conjugation negates the imaginary part and leaves everything else alone."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        r = env.get('r', 1)
        theta = env.get('theta', 0.5)
        steps = [
            'Conjugating a complex number flips the sign of its imaginary part. In polar terms '
            'that reflects the angle across the real axis and leaves the modulus untouched.',
            f'The two curves are Im(zⁿ) and its mirror, Im(z̄ⁿ), for modulus {_num(r)} and angle '
            f'{_num(theta)}. They are exact reflections through zero at every power.',
            'Because the modulus is unchanged, the size of z and z̄ is identical — that is why '
            'z·z̄ is a real number, and why dividing by z can be done by multiplying top and '
            'bottom by z̄.',
            'The real parts also agree: cos(−θ) = cos θ. Only the imaginary part changes sign. That '
            'is the whole content of conjugation, and it is what makes it useful for dividing and '
            'for finding real quadratic factors.',
        ]
        readouts = [
            {'label': 'Modulus of z and z̄', 'value': f'{_num(r)} both', 'detail': 'Unchanged by conjugation.'},
            {'label': 'Angle', 'value': f'{_num(theta)} and −{_num(theta)}', 'detail': 'Reflected across the real axis.'},
            {'label': 'Real parts', 'value': 'equal', 'detail': 'cos(−θ) = cos θ.'},
            {'label': 'Imaginary parts', 'value': 'opposite', 'detail': 'The only thing that flips.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='complex_conjugate',
        expression='r^n*sin(n*theta)',
        variable='n',
        secondary='0 - r^n*sin(n*theta)',
        parameters=[Parameter('r', 'Modulus r', 0.7, 1.3, 1, step=0.05),
                    Parameter('theta', 'Angle θ (rad)', 0.2, 1.2, 0.5, step=0.1)],
        domain=(0, 12),
        samples=13,
        discrete=True,
        title='A number and its conjugate',
        objective='Conjugation reflects the angle across the real axis, leaving the modulus and '
                  'the real part unchanged.',
        explain=explain,
        notes=['The two dotted curves are exact mirrors. Their sum is always real, which is why '
               'z + z̄ has no imaginary part.'],
    )


def _counting(concept_id: str) -> SimulationSpec:
    """The fundamental counting principle as a product, not a sum."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 3)
        n = env.get('n', 4)
        steps = [
            f'Each of the {_num(n)} stages offers {_num(a)} choices, independently of the others. '
            'The number of complete outcomes is the product of the choices, not the sum.',
            f'That gives {_num(a)}^{_num(n)} = {_num(a ** n)} outcomes. Adding instead would count '
            'the choices per stage rather than the combinations across stages.',
            'The curve steepens because each extra stage multiplies the total by the same factor. '
            'That is the signature of multiplicative counting, and it is why counts explode so '
            'quickly as stages are added.',
            'The principle only applies when the choices at each stage do not depend on what was '
            'chosen earlier. If they do, the stages have different counts and the simple product '
            'does not apply.',
        ]
        readouts = [
            {'label': 'Choices per stage', 'value': _num(a), 'detail': 'The base.'},
            {'label': 'Stages', 'value': _num(n), 'detail': 'The exponent.'},
            {'label': 'Total outcomes', 'value': _num(a ** n), 'detail': 'aⁿ, not a·n.'},
            {'label': 'One more stage', 'value': _num(a ** (n + 1)), 'detail': f'Multiplies by {_num(a)}.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='counting',
        expression='a^n',
        variable='n',
        parameters=[Parameter('a', 'Choices per stage a', 2, 6, 3, step=1, integer=True),
                    Parameter('n', 'Stages n', 1, 8, 4, step=1, integer=True)],
        domain=(1, 8),
        samples=8,
        discrete=True,
        title='Choices multiplying across stages',
        objective='Independent choices at each stage multiply, so the total count is a power.',
        explain=explain,
        notes=['The dots are counts at whole numbers of stages; there is no meaning to a fractional '
               'stage.'],
    )


# ------------------------------------------------ figures the authored rules mis-claim
#
# A second class of the same defect. These concepts *do* match an authored rule, but the
# wrong one, because ``_haystack`` includes keywords and a keyword can mean something else
# in another topic. "Ellipses" carries the keyword "cone" (conic sections) and was being
# drawn as a cylinder's volume; "Inverse trigonometric functions" carries "range" and was
# being drawn as a standard deviation; "Solving trigonometric equations" matched the word
# "solve" and was drawn as a balance scale. The builders below give each family a figure
# about its own idea, and ``templates._OVERRIDES`` places them ahead of the authored rules.


def conic_figure(concept_id: str) -> SimulationSpec:
    """An ellipse, drawn as its two branches."""
    a = _pick(concept_id, 'a', 3, 5)
    b = _pick(concept_id, 'b', 1, 3)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        wide = env.get('a', a)
        tall = env.get('b', b)
        steps = [
            f'This is an ellipse: every point on it is at the same total distance from two '
            f'fixed points, and that constant sum is what fixes the shape.',
            f'It is drawn as two branches because it is not a function — one x can meet the '
            f'curve twice. The upper branch is y = {_num(tall)}·√(1 − (x/{_num(wide)})²) and '
            'the lower one is its reflection.',
            f'The semi-axes are {_num(wide)} across and {_num(tall)} up. Whichever is larger is '
            'the major axis, and the two fixed points lie on it.',
            'The curve stops at x = ±' + f'{_num(wide)}: beyond that the expression takes the '
            'square root of a negative number, so there is no real height. That bound is the '
            'ellipse itself, not a limit of the drawing.',
        ]
        readouts = [
            {'label': 'Semi-axis across', 'value': _num(wide), 'detail': 'Half the width.'},
            {'label': 'Semi-axis up', 'value': _num(tall), 'detail': 'Half the height.'},
            {'label': 'Major axis', 'value': 'horizontal' if wide >= tall else 'vertical',
             'detail': 'The longer one.'},
            {'label': 'Defined for x', 'value': f'−{_num(wide)} to {_num(wide)}', 'detail': 'Outside, no real y.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='conic',
        expression='b*sqrt(1 - (x/a)^2)',
        variable='x',
        secondary='0 - b*sqrt(1 - (x/a)^2)',
        parameters=[Parameter('a', 'Semi-axis across a', 2, 5, a, step=0.5),
                    Parameter('b', 'Semi-axis up b', 1, 4, b, step=0.5),
                    Parameter('x', 'Probe input x', -5, 5, 1)],
        domain=(-5.5, 5.5),
        samples=480,
        title='An ellipse as two branches',
        objective='An ellipse is not a function of x; it is the set of points at a fixed total '
                  'distance from two foci.',
        explain=explain,
        notes=['The two branches are the upper and lower halves. The curve ends where the square '
               'root stops being real.'],
    )


def hyperbola_figure(concept_id: str) -> SimulationSpec:
    """A hyperbola: two branches outside the vertices."""
    a = _pick(concept_id, 'a', 1, 3)
    b = _pick(concept_id, 'b', 1, 3)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        across = env.get('a', a)
        up = env.get('b', b)
        steps = [
            'A hyperbola is the set of points whose distances to two fixed points differ by a '
            'constant. The difference, rather than the sum, is what separates it from an '
            'ellipse.',
            f'Here the vertices sit at x = ±{_num(across)}, and the curve exists only outside '
            f'that band — between them the expression takes the square root of a negative '
            'number. The gap is part of the shape.',
            f'The branches approach the lines y = ±({_num(up)}/{_num(across)})x without ever '
            'meeting them. Those asymptotes are what the curve settles onto far from the centre.',
            'The two branches are drawn separately because one x can meet the curve twice, once '
            'above and once below. Like the ellipse, a hyperbola is a relation rather than a '
            'function.',
        ]
        readouts = [
            {'label': 'Vertices', 'value': f'x = ±{_num(across)}', 'detail': 'Where each branch starts.'},
            {'label': 'Defined for |x|', 'value': f'≥ {_num(across)}', 'detail': 'No real y inside.'},
            {'label': 'Asymptote slopes', 'value': f'±{_num(up / across)}', 'detail': 'What the branches approach.'},
            {'label': 'Branches', 'value': '2', 'detail': 'Upper and lower.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='hyperbola',
        expression='b*sqrt((x/a)^2 - 1)',
        variable='x',
        secondary='0 - b*sqrt((x/a)^2 - 1)',
        parameters=[Parameter('a', 'Vertex distance a', 1, 3, a, step=0.5),
                    Parameter('b', 'Steepness b', 1, 3, b, step=0.5),
                    Parameter('x', 'Probe input x', -6, 6, 4)],
        domain=(-6, 6),
        samples=480,
        title='A hyperbola and its asymptotes',
        objective='A hyperbola has two branches, defined only outside its vertices, approaching '
                  'asymptotes it never reaches.',
        explain=explain,
        notes=['The gap between the branches is where the expression is undefined, not a drawing '
               'artefact.'],
    )


def rational_figure(concept_id: str) -> SimulationSpec:
    """A vertical asymptote and a horizontal one, in one curve."""
    c = _nonzero(concept_id, 'c', -3, 3)
    k = _pick(concept_id, 'k', 1, 4)
    b = _pick(concept_id, 'b', -2, 2)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        top = env.get('k', k)
        shift = env.get('b', b)
        steps = [
            f'The denominator is zero at x = {c}, and the curve has a vertical asymptote there. '
            'It is not a hole: the numerator is not zero at the same place, so the outputs run '
            'away instead of cancelling.',
            f'Far from x = {c} the constant {_num(top)} dominates the numerator and the '
            f'denominator is essentially x, so the curve levels off at y = {_num(shift)}. That '
            'is the horizontal asymptote.',
            'A hole would need the same factor on top and bottom, which cancels. Comparing the '
            'two is the whole test: a shared factor means a hole, an unmatched one means an '
            'asymptote.',
            'The two sides of the vertical asymptote go in opposite directions, because dividing '
            'by a small negative number gives a large negative result. That is why the curve '
            'looks split rather than continuous.',
        ]
        readouts = [
            {'label': 'Vertical asymptote', 'value': f'x = {c}', 'detail': 'Where the denominator vanishes.'},
            {'label': 'Horizontal asymptote', 'value': f'y = {_num(shift)}', 'detail': 'The far-away level.'},
            {'label': 'Hole', 'value': 'none', 'detail': 'No shared factor to cancel.'},
            {'label': 'Behaviour at the asymptote', 'value': 'opposite sides', 'detail': 'One branch to each infinity.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='rational',
        expression=f'k/(x - ({c})) + {b}',
        variable='x',
        parameters=[Parameter('k', 'Numerator k', -4, 4, k, step=1, integer=True),
                    Parameter('b', 'Horizontal shift b', -3, 3, b, step=1, integer=True),
                    Parameter('x', 'Probe input x', -6, 6, c + 2)],
        domain=(-6, 6),
        samples=480,
        title='A rational function and its asymptotes',
        objective='A zero in the denominator that the numerator does not share produces a '
                  'vertical asymptote, and the degrees decide the far-away level.',
        explain=explain,
        notes=[f'The curve is undefined at x = {c}, which is why it is split into two branches.'],
    )


def polynomial_figure(concept_id: str) -> SimulationSpec:
    """A quartic, so both ends can be seen to go the same way."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 0.5)
        b = env.get('b', -2)
        c = env.get('c', 1)
        probe = env.get('x', 1)
        degree = 4
        lead = 'up' if a > 0 else 'down'
        steps = [
            f'The degree is {degree} and the leading coefficient is {_num(a)}, so both ends go '
            f'{lead}. An even degree means the ends agree; an odd degree would send them '
            'opposite ways.',
            'That end behaviour is decided by the leading term alone. Far from the origin the '
            f'lower powers are negligible next to {_num(a)}x^{degree}, so they cannot change '
            'where the curve is heading.',
            'The turning points in between are decided by the other coefficients, which is why a '
            'polynomial can look complicated in the middle while its ends are completely '
            'predictable.',
            f'At x = {_num(probe)} the value is {_num(a * probe ** 4 + b * probe ** 2 + c * probe)}. '
            'The remainder theorem says that dividing by (x − c) leaves exactly this value as the '
            'remainder, which is the same statement read a different way.',
        ]
        readouts = [
            {'label': 'Degree', 'value': str(degree), 'detail': 'Even, so the ends agree.'},
            {'label': 'Leading coefficient', 'value': _num(a), 'detail': 'Its sign sets the direction.'},
            {'label': 'End behaviour', 'value': f'both ends {lead}', 'detail': 'Decided by the leading term.'},
            {'label': 'Value at the probe', 'value': _num(a * probe ** 4 + b * probe ** 2 + c * probe),
             'detail': 'Also the remainder on dividing by (x − c).'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='polynomial_graph',
        expression='a*x^4 + b*x^2 + c*x',
        variable='x',
        parameters=[Parameter('a', 'Leading coefficient a', -1, 1, 0.5, step=0.1),
                    Parameter('b', 'Quadratic coefficient b', -4, 4, -2, step=1, integer=True),
                    Parameter('c', 'Linear coefficient c', -4, 4, 1, step=1, integer=True),
                    Parameter('x', 'Probe input x', -3, 3, 1)],
        domain=(-3, 3),
        title='End behaviour of a polynomial',
        objective='The degree and the leading coefficient decide where the ends go; the other '
                  'terms only shape the middle.',
        explain=explain,
        notes=['Flip the leading coefficient and both ends reverse together, which is what an even '
               'degree means.'],
    )


def radical_figure(concept_id: str) -> SimulationSpec:
    """A square-root curve: a restricted domain and a starting point."""
    h = _pick(concept_id, 'h', -2, 3)
    k = _pick(concept_id, 'k', -3, 3)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1)
        shift = env.get('k', k)
        steps = [
            f'The curve starts at x = {h} and goes no further left. Before that the expression '
            'takes the square root of a negative number, which is not real, so the domain is '
            f'x ≥ {h}.',
            f'The starting point is ({h}, {_num(shift)}), and every value to its right is '
            'reached by a real square root. That endpoint is a feature of the rule, not of the '
            'drawing.',
            'Solving a radical equation has to respect the same restriction. Squaring both sides '
            'can introduce solutions the original rule never allowed, which is why every answer '
            'must be checked in the original equation.',
            f'The curve rises but flattens: doubling the input below the root does not double the '
            f'output. With a = {_num(a)} the output at x = {h + 1} is {_num(a)}.',
        ]
        readouts = [
            {'label': 'Starting point', 'value': f'({h}, {_num(shift)})', 'detail': 'The left end of the domain.'},
            {'label': 'Domain', 'value': f'x ≥ {h}', 'detail': 'Below it, no real output.'},
            {'label': 'Range', 'value': f'y ≥ {_num(shift)}' if a > 0 else f'y ≤ {_num(shift)}',
             'detail': 'The curve only goes one way.'},
            {'label': 'Check for extraneous roots', 'value': 'required', 'detail': 'Squaring can add false solutions.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='radical',
        expression=f'a*sqrt(x - ({h})) + {k}',
        variable='x',
        parameters=[Parameter('a', 'Steepness a', 0.5, 3, 1),
                    Parameter('x', 'Probe input x', -2, 8, h + 2)],
        domain=(-2, 8),
        samples=360,
        title='A square-root curve',
        objective='A square root restricts the domain to where its argument is non-negative, '
                  'which is why the curve has a starting point.',
        explain=explain,
        notes=[f'The curve begins at x = {h}. Squaring both sides of a radical equation can '
               'produce values outside this domain, so answers need checking.'],
    )


def no_figure(concept_id: str) -> SimulationSpec:
    """For concepts no single-variable plot can honestly show.

    Returns the engine's generic probe on purpose: ``figures.figure_for`` recognises that
    kind and substitutes a concept map built from the graph. Matrices, for instance, are
    not "a quantity as a function of one variable", and the alternative — drawing a line
    and labelling it "Matrix multiplication" — is the fabricated figure this whole module
    exists to prevent.
    """
    return SimulationSpec(
        kind='function_probe',
        expression='x',
        variable='x',
        domain=(-6, 6),
        title='No single-variable figure',
        objective='This concept is not a quantity plotted against one variable.',
        notes=['No figure of one variable can show this concept honestly, so a concept map is '
               'used instead.'],
    )


#: Ordered so the most specific match wins, exactly as in ``templates``. These rules are
#: appended after the authored course's rules, so they can only ever claim a concept that
#: the authored vocabulary did not already claim.
RULES: tuple[tuple[tuple[str, ...], Any], ...] = (
    (('definite integral as a limit', 'riemann*'), _accumulation),
    (('derivative as a limit', 'difference quotient', 'secant*'), _secant_tangent),
    (('limits at infinity', 'limit at infinity'), _limits_infinity),
    (('squeeze',), _squeeze),
    (('hôpital', "l'hopital", 'lhopital'), _lhopital),
    (('improper integral*', 'integral test*'), _improper),
    # Before the absolute-convergence rule: "The ratio test" carries "absolute convergence"
    # as a keyword, and its own name is the more specific signal.
    (('ratio test*', 'root test*'), _partial_sums),
    (('alternating series*', 'absolute convergence', 'conditional convergence'), _alternating_sums),
    (('comparison test*', 'direct comparison', 'limit comparison'), _comparison_series),
    (('nth-term', 'nth term'), _sequence_terms),
    (('convergence of sequences',), _sequence_terms),
    (('series*', 'summation notation*', 'partial sum*'), _partial_sums),
    (('fundamental theorem of calculus',), _accumulation),
    (('fundamental theorem of algebra', 'zeros and multiplicity', 'multiplicit*'), _roots),
    (('intermediate value',), _roots),
    (('accumulation function*', 'antiderivative*', 'definite integral*',
      'integration by parts'), _accumulation),
    (('concavity', 'inflection*', 'critical point*', 'increasing and decreasing',
      'first derivative test*', 'second derivative test*', 'extreme value*',
      'connecting graphs', 'higher-order derivative*'), _shape),
    (('implicit differentiation',), _implicit),
    (('inverse trigonometric', 'derivatives of inverse', 'inverse function*'), _inverse_pair),
    (('derivatives of trigonometric',), _tangent_trig),
    (('trigonometric function*', 'radian*', 'sine', 'cosine'), _trig_wave),
    (('constant, sum and difference', 'product rule*', 'quotient rule*',
      'selecting differentiation'), _tangent_line),
    (('related rates', 'chain rule*'), _related_rates),
    (('straight-line motion', 'vector-valued', 'parametric and vector',
      'interpreting derivatives in context'), _motion),
    (('polar coordinate*',), _polar),
    (('conjugate*',), _complex_conjugate),
    (('complex number*', 'complex arithmetic'), _complex_powers),
    (('counting principle*', 'fundamental counting'), _counting),
    (('composite function*', 'composition of function*'), _composition),
    (('even and odd', 'odd and even', 'symmetr*'), _symmetry),
    (('differentiability',), _corner),
    (('discontinu*',), _jump),
    (('continuity at a point', 'continuous at', 'defining limits', 'limit notation',
      'estimating limits', 'limit*'), _limit_hole),
)


__all__ = ['RULES', 'conic_figure', 'hyperbola_figure', 'no_figure', 'polynomial_figure',
           'radical_figure', 'rational_figure']
