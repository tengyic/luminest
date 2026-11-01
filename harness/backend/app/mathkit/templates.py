"""Generate a simulation spec for any concept, from its own classification.

This is what makes interactive content scale. Instead of hand-writing one figure per
concept, a concept's strand, topic and keywords select a template, and the template's
coefficients are derived deterministically from the concept id. The result is stable
across restarts, reproducible in tests, and available for a concept nobody has
written a figure for yet.

A concept whose classification matches nothing still gets a figure: the generic
function-probe template, which is honest about being generic.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Mapping, Sequence

from .calculus import (RULES as _CALCULUS_RULES, conic_figure, hyperbola_figure,
                       no_figure, polynomial_figure, radical_figure, rational_figure)
# The override table below lives here because it has to name builders from both modules.
# These five are the calculus module's own builders, reached by name so the table stays in
# one place rather than being split across two files.
from .calculus import (_complex_powers as _calc_complex_powers,
                       _counting as _calc_counting,
                       _inverse_pair as _calc_inverse_pair,
                       _symmetry as _calc_symmetry,
                       _trig_wave as _calc_trig_wave)
from .simulate import Mark, Parameter, Part, SimulationSpec


def _seed(concept_id: str) -> int:
    return int(hashlib.sha256(concept_id.encode('utf-8')).hexdigest()[:8], 16)


def _pick(concept_id: str, salt: str, low: int, high: int) -> int:
    """Deterministic integer in ``[low, high]`` for a concept."""
    span = high - low + 1
    return low + (_seed(concept_id + salt) % span)


def _nonzero(concept_id: str, salt: str, low: int, high: int) -> int:
    value = _pick(concept_id, salt, low, high)
    return value if value != 0 else high


def _signed(value: float) -> str:
    """Render a value as an explicit signed term, e.g. ``+ 3`` or ``− 2``.

    Used in prose, where ``f'{v:+g}'`` would produce the unreadable ``+ -2``.
    """
    text = f'{value:+g}'
    return ('− ' if text.startswith('-') else '+ ') + text.lstrip('+-')


def _haystack(concept: Mapping[str, Any]) -> str:
    """Matching text: title, topic and keywords only.

    The summary is deliberately excluded. It is prose about the concept and contains
    incidental words ("slope is a ratio") that would make template matching match
    almost everything, which is worse than a generic fallback.
    """
    return ' '.join([
        str(concept.get('title', '')), str(concept.get('topic', '')),
        ' '.join(str(k) for k in concept.get('keywords') or []),
    ]).casefold()


def _has(haystack: str, *needles: str) -> bool:
    """Whole-word matching, with ``*`` marking a stem.

    Plain substring matching was a real source of wrong figures: the needle ``tip``
    matched inside "mul*tip*le representations" and handed a percentage figure to a
    relations concept. A needle ending in ``*`` is a prefix ("inequalit*" matches
    "inequality" and "inequalities"); every other needle must appear as a whole word,
    so ``mean`` matches "mean" but not "meaning".
    """
    for needle in needles:
        if needle.endswith('*'):
            pattern = r'(?<![a-z0-9])' + re.escape(needle[:-1])
        else:
            pattern = r'(?<![a-z0-9])' + re.escape(needle) + r'(?![a-z0-9])'
        if re.search(pattern, haystack):
            return True
    return False


# --------------------------------------------------------------------------- templates


def _fraction(concept_id: str) -> SimulationSpec:
    a = _pick(concept_id, 'a', 1, 5)
    b = _pick(concept_id, 'b', 2, 6)
    d = _pick(concept_id, 'd', 3, 7)
    if b == d:
        d = d + 1

    def numerator(env: Mapping[str, float]) -> int:
        return max(1, min(d - 1, int(round(env.get('n', 1)))))

    def parts(env: Mapping[str, float]) -> list[Part]:
        n = numerator(env)
        common = b * d // math.gcd(b, d)
        first = a * (common // b)
        second = n * (common // d)
        return [
            Part(label=f'{a}/{b}', denominator=b, shaded=a, colour='primary',
                 note=f'The whole is cut into {b} equal parts and {a} are shaded.'),
            Part(label=f'{n}/{d}', denominator=d, shaded=n, colour='secondary',
                 note=f'The whole is cut into {d} equal parts and {n} are shaded, so the parts are a different size.'),
            Part(label=f'{first + second}/{common}', denominator=common, shaded=first + second, colour='accent',
                 note=f'Both fractions renamed over {common}, so the parts finally match and can be counted together.'),
        ]

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        """Common-denominator reasoning.

        A fraction sum is a polynomial in its numerator, so the generic polynomial
        explainer would call it "a line with slope 1/d" - arithmetically true and
        pedagogically useless. This keeps the denominator visible instead.
        """
        n = numerator(env)
        common = b * d // math.gcd(b, d)
        first = a * (common // b)
        second = n * (common // d)
        total = first + second
        steps = [
            f'The denominators are {b} and {d}. Parts of different sizes cannot be counted together, '
            f'so both fractions have to be renamed over one common denominator first.',
            f'The smallest common denominator is lcm({b}, {d}) = {common}.',
            f'Renaming {a}/{b} over {common} multiplies numerator and denominator by {common // b}, giving {first}/{common}. '
            f'The value is unchanged because the fraction is multiplied by {common // b}/{common // b} = 1.',
            f'Renaming {n}/{d} over {common} multiplies numerator and denominator by {common // d}, giving {second}/{common}.',
            f'The renamed parts are now the same size, so the numerators add: {first} + {second} = {total} parts of size '
            f'1/{common}, that is {total}/{common}.',
            'A denominator names the size of a part rather than a quantity, so denominators are never added. '
            f'Adding {b} + {d} = {b + d} would claim the parts got bigger, which is the opposite of what renaming does.',
        ]
        readouts: list[dict[str, Any]] = [
            {'label': 'Common denominator', 'value': f'{common}', 'detail': f'lcm({b}, {d}).'},
            {'label': f'{a}/{b} renamed', 'value': f'{first}/{common}',
             'detail': f'Numerator and denominator both multiplied by {common // b}.'},
            {'label': f'{n}/{d} renamed', 'value': f'{second}/{common}',
             'detail': f'Numerator and denominator both multiplied by {common // d}.'},
            {'label': 'Total', 'value': f'{total}/{common}', 'detail': f'{total} ÷ {common} ≈ {total / common:.4g}.'},
        ]
        if total > common:
            mixed = (f'{total // common} and {total % common}/{common}' if total % common else f'{total // common} wholes')
            readouts.append({'label': 'More than one whole', 'value': mixed,
                             'detail': 'The total exceeds a whole, so it is also reported as a mixed number.'})
        return steps, readouts

    return SimulationSpec(
        kind='fraction_bar',
        expression=f'{a}/{b} + n/{d}',
        variable='n',
        parameters=[Parameter('n', 'Numerator of the second fraction', 1, d - 1, 1, step=1, integer=True)],
        domain=(1, d - 1),
        discrete=True,
        title='Adding fractions with unlike denominators',
        objective='A denominator names the size of a part, so fractions can only be added once both are renamed '
                  'over a common denominator. The bars show why the denominators are never added.',
        constants={'first_numerator': float(a), 'first_denominator': float(b), 'second_denominator': float(d)},
        parts=parts,
        explain=explain,
        raw_display=True,
        notes=[f'The first fraction is {a}/{b} and the second has denominator {d}. '
               f'Rename both over lcm({b}, {d}) before adding, then check whether the total is more than one whole.'],
    )


def _percent(concept_id: str) -> SimulationSpec:
    start = _pick(concept_id, 'start', 40, 200)
    return SimulationSpec(
        kind='percent_change',
        expression=f'{start} * (1 + p/100)',
        variable='p',
        parameters=[Parameter('p', 'Percent change', -50, 100, _pick(concept_id, 'p', 5, 40), step=1, integer=True, unit='%')],
        domain=(-50, 100),
        title='Percent change against a stated base',
        objective='Percent change is measured against the original quantity, so the base must be named before the change is computed.',
        notes=[f'The original quantity is {start}. A 20% rise followed by a 20% fall does not return to {start}, because the second percentage uses a different base.'],
    )


def _exponent(concept_id: str) -> SimulationSpec:
    base = _pick(concept_id, 'base', 2, 4)
    return SimulationSpec(
        kind='exponential',
        expression=f'a * {base}^x',
        variable='x',
        parameters=[Parameter('a', 'Starting amount a', 1, 10, _pick(concept_id, 'a', 1, 5), step=1),
                    Parameter('x', 'Input x', -3, 6, 3, step=1, integer=True)],
        domain=(-3, 6),
        title='Repeated multiplication',
        objective='An exponent counts repeated factors, so the curve grows by a constant ratio rather than a constant difference.',
        notes=[f'The base is {base}. Compare the change from x = 0 to 1 with the change from x = 4 to 5.'],
    )


def _linear_equation(concept_id: str) -> SimulationSpec:
    a = _nonzero(concept_id, 'a', 2, 9)
    x = _pick(concept_id, 'x', 2, 8)
    b = _pick(concept_id, 'b', 1, 12)
    return SimulationSpec(
        kind='balance',
        expression=f'{a}*x + {b}',
        variable='x',
        parameters=[Parameter('x', 'Candidate solution x', -8, 8, x, step=1, integer=True)],
        domain=(-8, 8),
        title=f'Solving {a}x + {b} = {a * x + b}',
        objective='Undo addition before multiplication, then substitute the candidate back into the original equation.',
        constants={'target': float(a * x + b)},
        notes=[f'The equation is {a}x + {b} = {a * x + b}. The left bar is the expression; the right bar is the target.'],
    )


def _inequality(concept_id: str) -> SimulationSpec:
    a = _nonzero(concept_id, 'a', 2, 6)
    boundary = _pick(concept_id, 'b', 1, 8)
    return SimulationSpec(
        kind='inequality',
        expression=f'{-a}*x',
        variable='x',
        parameters=[Parameter('x', 'Candidate value x', -8, 8, -boundary, step=1, integer=True)],
        domain=(-8, 8),
        title=f'Dividing {a}x by a negative reverses the order',
        objective='Dividing both sides by a negative number reverses the comparison, so the boundary flips.',
        constants={'boundary': float(a * boundary)},
        notes=[f'Compare -{a}x with {a * boundary}. Test a value on each side of x = -{boundary}.'],
    )


def _systems(concept_id: str) -> SimulationSpec:
    m1 = _nonzero(concept_id, 'm1', -3, 3)
    sign = 1 if m1 < 0 else -1
    gap = _pick(concept_id, 'gap', 2, 4)
    m2 = m1 + gap * sign
    if m2 == 0:
        # A zero slope makes the second line horizontal, which is a degenerate
        # example of "two constraints". Push it past zero instead.
        m2 = m1 + (gap + 1) * sign
    b1 = _pick(concept_id, 'b1', -6, 8)
    b2 = _pick(concept_id, 'b2', -6, 8)
    return SimulationSpec(
        kind='systems',
        expression=f'{m1}*x + {b1}',
        secondary=f'{m2}*x + {b2}',
        variable='x',
        parameters=[Parameter('x', 'Probe input x', -6, 6, 2, step=1, integer=True)],
        domain=(-6, 6),
        title='Two constraints at once',
        objective='A solution must satisfy both equations, so it is the intersection of the two lines.',
        notes=[f'Line 1: y = {m1}x {b1:+d}. Line 2: y = {m2}x {b2:+d}. The slopes differ, so the lines meet exactly once.'],
    )


def _quadratic(concept_id: str) -> SimulationSpec:
    # p and q only choose the default coefficients. The expression keeps a, b and c
    # symbolic so that the sliders actually move the parabola.
    p = _pick(concept_id, 'p', -6, -1)
    q = _pick(concept_id, 'q', 1, 6)
    b, c = -(p + q), p * q
    return SimulationSpec(
        kind='quadratic',
        expression='a*x^2 + b*x + c',
        variable='x',
        parameters=[Parameter('a', 'Leading coefficient a', 0.2, 2, 1),
                    Parameter('b', 'Linear coefficient b', -8, 8, b, step=1, integer=True),
                    Parameter('c', 'Constant c', -9, 9, c, step=1, integer=True),
                    Parameter('x', 'Probe input x', -6, 6, 2)],
        domain=(-6, 6),
        title='Parabola, roots and vertex',
        objective='The discriminant reports how many real roots exist before any are computed, and the vertex is the turning point.',
        notes=['The coefficient a controls the direction and width of the parabola; b and c move it without changing its shape. '
               'The roots, vertex and discriminant below are recomputed from the current coefficients.'],
    )


def _polynomial_product(concept_id: str) -> SimulationSpec:
    p = _pick(concept_id, 'p', 1, 7)
    q = _pick(concept_id, 'q', 1, 7)
    return SimulationSpec(
        kind='polynomial',
        expression=f'(x + {p})*(x + {q})',
        variable='x',
        parameters=[Parameter('x', 'Probe input x', -6, 6, 2)],
        domain=(-6, 6),
        title='Expanding a product of binomials',
        objective='Every term of one factor multiplies every term of the other, giving four products before like terms combine.',
        notes=[f'There are four products in (x + {p})(x + {q}); check that the middle coefficient is {p + q} and the constant is {p * q}.'],
    )


def _factoring(concept_id: str) -> SimulationSpec:
    p = _pick(concept_id, 'p', 1, 6)
    q = _pick(concept_id, 'q', 1, 6)
    return SimulationSpec(
        kind='quadratic',
        expression=f'x^2 + {p + q}*x + {p * q}',
        variable='x',
        parameters=[Parameter('x', 'Probe input x', -6, 6, 2)],
        domain=(-6, 6),
        title=f'Factoring x² + {p + q}x + {p * q}',
        objective='For a monic quadratic the factor constants must satisfy both a sum and a product condition at the same time.',
        notes=[f'Look for two numbers with sum {p + q} and product {p * q}. Both conditions must hold.'],
    )


def _linear_function(concept_id: str) -> SimulationSpec:
    m = _nonzero(concept_id, 'm', -4, 4)
    b = _pick(concept_id, 'b', -6, 6)
    return SimulationSpec(
        kind='linear',
        expression='m*x + b',
        variable='x',
        parameters=[Parameter('m', 'Slope m', -4, 4, m),
                    Parameter('b', 'Intercept b', -6, 6, b),
                    Parameter('x', 'Probe input x', -6, 6, 2)],
        domain=(-6, 6),
        title='Constant rate of change',
        objective='Slope is the change in output per unit change in input, and the intercept is the output at zero input.',
        notes=['Keep the same point order in both differences when you compute the slope by hand.'],
    )


def _exponential_function(concept_id: str) -> SimulationSpec:
    factor = _pick(concept_id, 'r', 1, 3) + 0.5
    return SimulationSpec(
        kind='exponential',
        expression='a*b^x',
        variable='x',
        parameters=[Parameter('a', 'Starting amount a', 1, 20, _pick(concept_id, 'a', 2, 8)),
                    Parameter('b', 'Growth factor b', 0.5, 2, factor),
                    Parameter('x', 'Probe input x', -4, 6, 3)],
        domain=(-4, 6),
        title='Exponential growth and decay',
        objective='A constant ratio between successive outputs produces exponential change; a constant difference produces linear change.',
        notes=['Set b below 1 to model decay. Compare how long it takes to double at b = 1.5 against b = 2.'],
    )


def _absolute_value(concept_id: str) -> SimulationSpec:
    h = _pick(concept_id, 'h', -4, 4)
    k = _pick(concept_id, 'k', -4, 4)
    return SimulationSpec(
        kind='absolute_value',
        # Signed formatting, so a negative shift prints "x + 2" rather than "x − -2".
        expression=f'a*abs(x {(-h):+d}){k:+d}',
        variable='x',
        parameters=[Parameter('a', 'Vertical scale a', 0.2, 3, 1),
                    Parameter('x', 'Probe input x', -6, 6, 2)],
        domain=(-6, 6),
        title='Absolute value as distance',
        objective='Absolute value measures distance from a point, which is why its graph is two straight pieces meeting at a vertex.',
        notes=[f'The vertex sits at x = {h} and the graph turns there from falling to rising.'],
    )


def _transformations(concept_id: str) -> SimulationSpec:
    return SimulationSpec(
        kind='transformation',
        expression='a*abs(x - h) + k',
        variable='x',
        parameters=[Parameter('a', 'Vertical stretch a', 0.2, 3, 1),
                    Parameter('h', 'Horizontal shift h', -5, 5, _pick(concept_id, 'h', -3, 3), step=1),
                    Parameter('k', 'Vertical shift k', -5, 5, _pick(concept_id, 'k', -3, 3), step=1),
                    Parameter('x', 'Probe input x', -6, 6, 2)],
        domain=(-6, 6),
        title='Shifting and stretching a parent function',
        objective='A change inside the input shifts horizontally in the opposite direction to its sign; a change outside shifts vertically.',
        notes=['Compare the vertex of the curve with the parent function to see both shifts at once.'],
    )


def _geometry_area(concept_id: str) -> SimulationSpec:
    fixed = _pick(concept_id, 'w', 2, 12)
    return SimulationSpec(
        kind='area',
        expression=f'x * {fixed}',
        variable='x',
        parameters=[Parameter('x', 'Variable side length', 1, 20, _pick(concept_id, 'x', 3, 10))],
        domain=(1, 20),
        title='Area as a product of side lengths',
        objective='Area multiplies two lengths, so its units are square units while perimeter uses linear units.',
        notes=[f'One side is fixed at {fixed}. Doubling the other side doubles the area but not the perimeter.'],
    )


def _geometry_circle(concept_id: str) -> SimulationSpec:
    return SimulationSpec(
        kind='circle',
        expression='pi * r^2',
        variable='r',
        parameters=[Parameter('r', 'Radius r', 0.5, 12, _pick(concept_id, 'r', 2, 8))],
        domain=(0.5, 12),
        title='Area grows with the square of the radius',
        objective='Circumference is proportional to the radius while area is proportional to its square, which is why doubling r quadruples the area.',
        notes=['Compare the area at r and at 2r. The ratio should be 4.'],
    )


def _geometry_volume(concept_id: str) -> SimulationSpec:
    height = _pick(concept_id, 'h', 2, 10)
    return SimulationSpec(
        kind='volume',
        expression=f'pi * r^2 * {height}',
        variable='r',
        parameters=[Parameter('r', 'Radius r', 0.5, 8, _pick(concept_id, 'r', 2, 6))],
        domain=(0.5, 8),
        title='Volume of a cylinder',
        objective='Volume multiplies a base area by a height, so it scales with the square of the radius.',
        notes=[f'The height is fixed at {height}. Doubling the radius multiplies the volume by four.'],
    )


def _distance(concept_id: str) -> SimulationSpec:
    dx = _pick(concept_id, 'dx', 1, 8)
    dy = _pick(concept_id, 'dy', 1, 8)
    return SimulationSpec(
        kind='distance',
        expression=f'sqrt({dx}^2 + {dy}^2) * x',
        variable='x',
        parameters=[Parameter('x', 'Scale factor', 0.2, 5, 1)],
        domain=(0.2, 5),
        title='Distance from the Pythagorean theorem',
        objective='The distance between two points is the hypotenuse of a right triangle built from the coordinate differences.',
        notes=[f'The coordinate differences are {dx} and {dy}, so the base distance is sqrt({dx * dx} + {dy * dy}).'],
    )


def _statistics(concept_id: str) -> SimulationSpec:
    spread = _pick(concept_id, 's', 2, 12)
    return SimulationSpec(
        kind='spread',
        expression=f'abs(x - {spread})',
        variable='x',
        parameters=[Parameter('x', 'An observation', 0, 30, spread, step=1, integer=True)],
        domain=(0, 30),
        discrete=True,
        title='Deviation from the mean',
        objective='Spread measures how far observations sit from centre, and a deviation is squared before averaging so that signs do not cancel.',
        notes=[f'The centre is {spread}. Moving an observation further from centre increases the standard deviation.'],
    )


def _arrangements(concept_id: str) -> SimulationSpec:
    """Permutations against combinations: one selection counted two ways.

    The concepts that land here are not "a quantity as a function of one variable" in any
    useful sense, and the previous rule sent them to the binomial template, which drew a
    sampling distribution for a lesson about counting arrangements. That is the failure
    mode this file's docstring warns about: a figure that is real content for a *different*
    concept. What the idea actually has is a curve — C(n,r) as r varies — and a contrast
    the learner can see move: the ratio P(n,r)/C(n,r) is exactly r!, the orderings a
    combination discards.
    """
    n0 = _pick(concept_id, 'n', 5, 8)
    r0 = max(1, min(n0 - 1, _pick(concept_id, 'r', 2, 4)))

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        n = max(1, min(10, int(round(env.get('n', n0)))))
        r = max(0, min(10, int(round(env.get('r', r0)))))
        if r > n:
            return (
                [f'You cannot select {r} items from {n}: there are not that many available. Both counts '
                 'are 0, which is the counting convention for an impossible selection rather than an error.'],
                [{'label': 'Items selected r', 'value': f'{r}', 'detail': f'More than n = {n} available.'},
                 {'label': 'Ordered arrangements P(n,r)', 'value': '0', 'detail': 'The selection is impossible.'},
                 {'label': 'Unordered selections C(n,r)', 'value': '0', 'detail': 'The selection is impossible.'},
                 {'label': 'Ratio P ÷ C', 'value': '—', 'detail': 'Not defined when both counts are 0.'}],
            )
        ordered = math.perm(n, r)
        unordered = math.comb(n, r)
        orderings = math.factorial(r)
        steps = [
            f'Both counts begin identically: choose r = {r} items from the n = {n} available. '
            'Nothing has been decided about order yet.',
            f'If the order the items come out in matters, each selection can be rearranged in {r}! = '
            f'{orderings} ways, and every one of them counts as a different outcome. So '
            f'P({n},{r}) = {n}!/({n}−{r})! = {ordered}.',
            f'If the order does not matter, those {orderings} arrangements are all the same selection. '
            f'Counting them separately would over-count by a factor of {orderings}, so '
            f'C({n},{r}) = {ordered}/{orderings} = {unordered}.',
            f'The ratio P ÷ C is therefore {orderings} = {r}!, and that is not a coincidence: it is '
            'exactly the number of orderings a combination throws away.',
        ]
        readouts = [
            {'label': 'Ordered arrangements P(n,r)', 'value': f'{ordered}',
             'detail': f'n!/(n−r)! with n = {n}, r = {r}.'},
            {'label': 'Unordered selections C(n,r)', 'value': f'{unordered}',
             'detail': 'The same choice, with order ignored.'},
            {'label': 'Ratio P ÷ C', 'value': f'{orderings}',
             'detail': f'= r!, the orderings discarded per selection.'},
            {'label': 'C as a share of P', 'value': f'1/{orderings}',
             'detail': f'{unordered} of {ordered} arrangements survive as distinct selections.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='arrangements',
        expression='choose(n, r)',
        variable='r',
        parameters=[Parameter('n', 'Items available n', 1, 10, n0, step=1, integer=True),
                    Parameter('r', 'Items selected r', 0, 10, r0, step=1, integer=True)],
        domain=(0, 10),
        # One sample per integer: the default count would repeat each integer ~25 times and
        # draw the counts as a staircase instead of the discrete points they are.
        samples=11,
        discrete=True,
        title='One selection, counted with and without order',
        objective='P(n,r) counts ordered arrangements and C(n,r) counts unordered selections of the same '
                  'r items, so the two counts differ by exactly r!.',
        explain=explain,
        notes=[f'With n = {n0} available and r = {r0} selected, the curve is C(n,r) as r grows: it rises to a '
               'peak in the middle and falls to 0 once r passes n. Watch P ÷ C stay at r! as you move both sliders.'],
    )


def _probability(concept_id: str) -> SimulationSpec:
    trials = _pick(concept_id, 'n', 4, 20)
    successes = _pick(concept_id, 'k', 1, trials - 1)
    probability = round(_pick(concept_id, 'p', 20, 80) / 100, 2)
    return SimulationSpec(
        kind='binomial',
        expression='p',
        variable='p',
        parameters=[Parameter('p', 'Success probability p', 0.05, 0.95, probability, step=0.05)],
        domain=(0.05, 0.95),
        title=f'Binomial with n = {trials}, k = {successes}',
        objective='Independent trials with a constant success probability give a binomial distribution over the number of successes.',
        constants={'n': float(trials), 'k': float(successes)},
        notes=[f'With n = {trials} and k = {successes}, P(X = k) is C(n,k)·pᵏ·(1−p)ⁿ⁻ᵏ. Changing p moves the whole distribution.'],
    )


def _sampling(concept_id: str) -> SimulationSpec:
    proportion = round(_pick(concept_id, 'p', 3, 7) / 10, 2)
    return SimulationSpec(
        kind='standard_error',
        expression=f'sqrt({proportion}*(1 - {proportion})/n)',
        variable='n',
        parameters=[Parameter('n', 'Sample size n', 5, 400, _pick(concept_id, 'n', 20, 120), step=1, integer=True)],
        domain=(5, 400),
        discrete=True,
        title='Standard error shrinks as the sample grows',
        objective='Sampling variability falls with the square root of the sample size, so quadrupling the sample only halves the standard error.',
        notes=[f'The observed proportion is {proportion}. Compare n and 4n to see the square-root relationship.'],
    )


def _generic(concept_id: str) -> SimulationSpec:
    a = _pick(concept_id, 'a', 1, 4)
    return SimulationSpec(
        kind='function_probe',
        expression='a*x^2 - b*x + c',
        variable='x',
        parameters=[Parameter('a', 'Quadratic coefficient a', 0.2, 2, a / 2),
                    Parameter('b', 'Linear coefficient b', -8, 8, _pick(concept_id, 'b', -4, 4)),
                    Parameter('c', 'Constant c', -8, 8, _pick(concept_id, 'c', -4, 4)),
                    Parameter('x', 'Probe input x', -6, 6, 2)],
        domain=(-6, 6),
        title='Probing a rule',
        objective='Change one parameter at a time and predict the effect before you look at the curve.',
        notes=['This is the generic probe used when a concept has no more specific figure yet.'],
    )


# ------------------------------------------------------------------ non-plot figures
#
# The concepts below are not "a quantity as a function of one variable". Plotting a
# quadratic for "Points, lines, rays and planes" is not a simplification, it is wrong
# content. Each of them gets a figure that is actually about its own idea, using the
# ``marks`` scene primitive or an authored explainer.


def _substitution(concept_id: str) -> SimulationSpec:
    """Evaluating an expression, function notation, terms/coefficients/constants."""
    a = _nonzero(concept_id, 'a', 2, 7)
    b = _pick(concept_id, 'b', -9, 9)
    x0 = _pick(concept_id, 'x0', -5, 5)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        value = env.get('x', x0)
        coefficient = env.get('a', a)
        constant = env.get('b', b)
        product = coefficient * value
        steps = [
            f'An expression is a rule, not an answer. Substituting x = {value:g} turns the rule into one number.',
            f'The coefficient {coefficient:g} multiplies the variable, so it acts on the substituted value: '
            f'{coefficient:g} × ({value:g}) = {product:g}.',
            f'The constant {constant:g} carries no variable, so it passes through unchanged no matter what is substituted.',
            f'Combining the two terms gives {product:g} + ({constant:g}) = {product + constant:g}.',
        ]
        if value < 0:
            steps.append(f'Because the substituted value is negative it belongs in brackets. Writing {coefficient:g}·{value:g} '
                         f'invites a sign error; {coefficient:g}·({value:g}) does not.')
        readouts: list[dict[str, Any]] = [
            {'label': 'Value substituted for x', 'value': f'{value:g}', 'detail': 'The input to the rule.'},
            {'label': 'Coefficient × value', 'value': f'{product:g}', 'detail': f'{coefficient:g} × {value:g}.'},
            {'label': 'Constant', 'value': f'{constant:g}', 'detail': 'Passes through unchanged.'},
            {'label': 'Value of the expression', 'value': f'{product + constant:g}', 'detail': 'The terms combined.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='substitution',
        expression=f'a*x{b:+d}',
        variable='x',
        parameters=[Parameter('a', 'Coefficient of x', -6, 6, a, step=1, integer=True),
                    Parameter('x', 'Value substituted for x', -6, 6, x0, step=1, integer=True)],
        domain=(-6, 6),
        title='Evaluating an expression by substitution',
        objective='An expression is a rule rather than an answer. Substituting a value for the variable turns the rule '
                  'into a number, and each term keeps its own sign.',
        explain=explain,
        notes=['The coefficient multiplies the variable; the constant is added unchanged. '
               'Substituting a negative value puts it in brackets before multiplying.'],
    )


def _angle(concept_id: str) -> SimulationSpec:
    """Angle relationships, transversals and the triangle angle sum."""
    known = _pick(concept_id, 'known', 25, 65)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        x = env.get('x', 60)
        third = 180 - x - known
        steps = [
            'Angles on a straight line add to 180°, and so do the three interior angles of a triangle. '
            'That total is a property of the figure, not something to measure each time.',
            f'One angle is given as {known}° and the other is x = {x:g}°.',
            f'Subtracting both from the total leaves {180}° − {x:g}° − {known}° = {third:g}°.',
            'Because the relation is a subtraction, a larger known angle leaves less for the unknown one. '
            'That is why the two move in opposite directions.',
        ]
        if third <= 0:
            steps.append(f'At x = {x:g}° the remaining angle is not positive, so these two angles cannot belong to a valid '
                         'triangle: a geometric answer must be checked for whether it is possible, not only whether it is arithmetic.')
        readouts: list[dict[str, Any]] = [
            {'label': 'Given angle', 'value': f'{known}°', 'detail': 'Fixed by the figure.'},
            {'label': 'Chosen angle x', 'value': f'{x:g}°', 'detail': 'Moved by the slider.'},
            {'label': 'Remaining angle', 'value': f'{third:g}°', 'detail': f'180° − {x:g}° − {known}°.'},
            {'label': 'Still valid?', 'value': 'yes' if third > 0 else 'no',
             'detail': 'Every angle in a triangle must be greater than 0°.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='angle_sum',
        expression=f'180 - x - {known}',
        variable='x',
        parameters=[Parameter('x', 'One angle x', 10, 170, 60, step=1, integer=True, unit='°')],
        domain=(10, 170),
        title='Angles that share a fixed total',
        objective='Angles on a straight line sum to 180°, and the interior angles of a triangle sum to 180°, so an '
                  'unknown angle is found by subtraction rather than by measuring.',
        explain=explain,
        notes=[f'One angle is fixed at {known}°. Move x and watch the remaining angle: the total stays 180°.'],
    )


def _number_line(concept_id: str) -> SimulationSpec:
    """Integer addition and subtraction, signed numbers as directed movement."""
    step = _nonzero(concept_id, 'step', -9, 9)
    start = _pick(concept_id, 'start', -8, 8)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        displacement = env.get('d', step)
        begin = env.get('x', start)
        finish = begin + displacement
        steps = [
            f'Adding on a number line means moving. Start at {begin:g} and move {abs(displacement):g} units '
            f'{"right" if displacement > 0 else "left"}, because a {"positive" if displacement > 0 else "negative"} '
            'number carries the direction with it.',
            'Moving right increases the value and moving left decreases it, so the sign of the second number decides '
            'the direction while its size decides how far to go.',
            f'Landing at {finish:g} means {begin:g} + ({displacement:g}) = {finish:g}.',
        ]
        if displacement < 0:
            steps.append(f'Subtracting a negative is the same as adding its opposite, so {begin:g} − ({displacement:g}) '
                         f'is the same move as {begin:g} + ({-displacement:g}), which lands at {begin - displacement:g}. '
                         'Two sign changes cancel, which is why a double negative moves right.')
        elif displacement > 0:
            steps.append(f'Subtracting a positive moves left: {begin:g} − {displacement:g} would land at '
                         f'{begin - displacement:g}, the mirror image of the move shown here.')
        else:
            steps.append('A displacement of zero leaves the value unchanged: adding nothing is not the same as '
                         'having nothing, so the starting point is still reported.')
        readouts: list[dict[str, Any]] = [
            {'label': 'Starting point', 'value': f'{begin:g}', 'detail': 'Where the move begins.'},
            {'label': 'Displacement', 'value': f'{displacement:+g}',
             'detail': f'{"Right" if displacement > 0 else "Left" if displacement < 0 else "No movement"} along the line.'},
            {'label': 'Landing point', 'value': f'{finish:g}', 'detail': f'{begin:g} + ({displacement:g}).'},
            {'label': 'Distance travelled', 'value': f'{abs(displacement):g}', 'detail': 'Distance is never negative.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='number_line',
        expression='x + d',
        variable='x',
        parameters=[Parameter('x', 'Starting point', -10, 10, start, step=1, integer=True),
                    Parameter('d', 'Displacement d', -10, 10, step, step=1, integer=True)],
        domain=(-10, 10),
        discrete=True,
        title='Signed numbers as directed movement',
        objective='A signed number is a direction together with a distance, so adding moves along the number line and '
                  'the sign of the number added sets the direction.',
        explain=explain,
        notes=['Distance and direction are different questions: the landing point carries a sign, the distance travelled never does.'],
    )


def _sign_rules(concept_id: str) -> SimulationSpec:
    """Sign rules for multiplication and division of signed numbers."""
    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        a = env.get('a', 1.0)
        b = env.get('b', 1.0)
        product = a * b
        same = (a > 0) == (b > 0)
        steps = [
            'Multiplication and division of signed numbers follow a single rule: the sign of the result depends only '
            'on whether the two signs agree.',
            f'Here {a:g} × {b:g} is being evaluated. The two factors have '
            f'{"the same sign" if same else "different signs"}, so the result is {"positive" if product > 0 else "negative"}.',
            'The size of the result comes from the sizes of the factors, and the sign comes from the signs alone. '
            'The two questions are independent, which is why a large negative times a small positive is still negative.',
            'Multiplying by a negative number reverses direction on the number line, so a second negative reverses it '
            'back again. That is the whole reason two negatives give a positive.',
            'Division follows the same rule because division undoes multiplication: if the product of two signed '
            'numbers has a known sign, so does their quotient.',
        ]
        quotient = f'{a / b:+g}' if b else 'undefined'
        readouts: list[dict[str, Any]] = [
            {'label': 'First factor', 'value': f'{a:+g}', 'detail': 'Signed.'},
            {'label': 'Second factor', 'value': f'{b:+g}', 'detail': 'Signed.'},
            {'label': 'Signs agree?', 'value': 'yes' if same else 'no', 'detail': 'The same sign gives a positive result.'},
            {'label': 'Product', 'value': f'{product:+g}', 'detail': f'{a:g} × {b:g}.'},
            {'label': 'Quotient', 'value': quotient, 'detail': 'Division follows the same sign rule.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='sign_rules',
        expression='a*b',
        variable='b',
        parameters=[Parameter('a', 'First factor a', -8, 8, _nonzero(concept_id, 'a', -6, 6), step=1, integer=True),
                    Parameter('b', 'Second factor b', -8, 8, _nonzero(concept_id, 'b', -6, 6), step=1, integer=True)],
        domain=(-8, 8),
        discrete=True,
        title='The sign rules for multiplication and division',
        objective='The sign of a product or quotient depends only on whether the two signs agree: the same sign gives a '
                  'positive result and different signs give a negative one. The sizes never affect the sign.',
        explain=explain,
        notes=['Multiplying by a negative reverses direction on the number line, so a second negative reverses it back.'],
    )


def _place_value(concept_id: str) -> SimulationSpec:
    """Base-ten structure: each place is a power of ten."""
    digit = _pick(concept_id, 'digit', 1, 9)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        power = int(round(env.get('p', 0)))
        value = digit * 10 ** power
        steps = [
            f'Base-ten notation is positional: the same digit {digit} is worth different amounts depending on which '
            f'column it sits in.',
            f'Moving one column to the left multiplies the value by 10, so the {power}th column left of the units is worth 10^{power} = {10 ** power}.',
            f'Placing the digit {digit} in that column therefore contributes {digit} × {10 ** power} = {value}.',
            'Because each column is ten times the one to its right, regrouping is always an exchange of ten units of '
            'one column for one unit of the next column left.',
        ]
        readouts: list[dict[str, Any]] = [
            {'label': 'Digit', 'value': f'{digit}', 'detail': 'The same digit throughout.'},
            {'label': 'Column', 'value': f'10^{power}', 'detail': f'{power} places left of the units.'},
            {'label': 'Place value', 'value': f'{10 ** power}', 'detail': 'What one unit in this column is worth.'},
            {'label': 'Contribution', 'value': f'{value}', 'detail': f'{digit} × {10 ** power}.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='place_value',
        expression=f'{digit} * 10^p',
        variable='p',
        parameters=[Parameter('p', 'Column, counted from the units', 0, 6, 2, step=1, integer=True)],
        domain=(0, 6),
        discrete=True,
        title='One digit, many values',
        objective='A digit carries no value by itself: its value comes from the column it occupies, and each column is '
                  'ten times the column to its right.',
        explain=explain,
        notes=[f'The digit is {digit}. Compare its contribution in adjacent columns to see the factor of ten.'],
    )


def _precision(concept_id: str) -> SimulationSpec:
    """Precision, accuracy and significant figures as rounding error."""
    scale = _pick(concept_id, 'scale', 1, 9)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        unit = env.get('u', 1.0) or 1.0
        reading = env.get('x', 0.0)
        rounded = round(reading / unit) * unit
        error = abs(reading - rounded)
        steps = [
            'Every measurement is reported to some smallest unit, and that unit sets the precision of the reading. '
            'Accuracy is a separate question: it asks whether the value is close to the truth, not how finely it is stated.',
            f'The smallest unit here is {unit:g}. Any reading is therefore reported as a multiple of {unit:g}.',
            f'The true reading {reading:g} is reported as {rounded:g}, so the rounding error is |{reading:g} − {rounded:g}| = {error:g}.',
            f'The greatest possible error of a reading taken to the nearest {unit:g} is half a unit, {unit / 2:g}. '
            'Reporting more decimal places than that would claim precision the instrument does not have.',
        ]
        readouts: list[dict[str, Any]] = [
            {'label': 'Smallest unit', 'value': f'{unit:g}', 'detail': 'The precision of the instrument.'},
            {'label': 'Reading', 'value': f'{reading:g}', 'detail': 'Before rounding.'},
            {'label': 'Reported', 'value': f'{rounded:g}', 'detail': f'Rounded to the nearest {unit:g}.'},
            {'label': 'Rounding error', 'value': f'{error:g}', 'detail': f'At most half a unit, {unit / 2:g}.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='precision',
        expression='abs(x - u*round(x/u))',
        variable='x',
        parameters=[Parameter('x', 'True reading', -20, 20, scale * 1.37),
                    Parameter('u', 'Smallest unit on the instrument', 0.1, 2, 0.5, step=0.1)],
        domain=(-20, 20),
        title='Rounding error and the limits of a measurement',
        objective='Precision is the smallest unit an instrument can distinguish; accuracy is closeness to the true '
                  'value. Reporting more digits than the instrument supports claims precision that does not exist.',
        explain=explain,
        notes=['The sawtooth shape is the point: the error resets to zero at every exact multiple of the unit and is '
               'largest exactly halfway between two of them.'],
    )


def _ratio(concept_id: str) -> SimulationSpec:
    """Ratios as comparisons: part-to-part versus part-to-whole."""
    other = _pick(concept_id, 'other', 2, 9)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        part = env.get('a', 3.0) or 1.0
        whole = part + other
        share = part / whole
        steps = [
            'A ratio compares quantities, and the comparison is meaningless until it is clear whether the second '
            'quantity is the rest of the whole or a separate group.',
            f'If {other} is the remaining part of the same whole, then the whole is {part:g} + {other} = {whole:g} and '
            f'the first part is {part:g}/{whole:g} ≈ {share:.4g} of it.',
            f'As a part-to-part comparison the same situation is written {part:g} : {other}, which reports the two parts '
            'side by side and says nothing directly about the whole.',
            'The two descriptions are both correct and are not interchangeable. '
            f'Read as a part-to-whole fraction the number is {share:.4g}; read as a part-to-part ratio it is {part:g} : {other}.',
        ]
        readouts: list[dict[str, Any]] = [
            {'label': 'First part', 'value': f'{part:g}', 'detail': 'The quantity being compared.'},
            {'label': 'Second part', 'value': f'{other}', 'detail': 'The rest of the whole.'},
            {'label': 'Part to part', 'value': f'{part:g} : {other}', 'detail': 'The two parts side by side.'},
            {'label': 'Part to whole', 'value': f'{part:g}/{whole:g} ≈ {share:.4g}',
             'detail': 'The first part as a fraction of the total.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='ratio',
        expression='a/(a + b)',
        variable='a',
        parameters=[Parameter('a', 'First part a', 1, 20, 3, step=1, integer=True)],
        domain=(1, 20),
        discrete=True,
        title='Part-to-part and part-to-whole',
        objective='A ratio is a comparison, and the comparison changes depending on whether the second quantity is the '
                  'rest of the same whole or a separate group.',
        constants={'b': float(other)},
        explain=explain,
        notes=[f'The other part is fixed at {other}. Watch how the part-to-whole fraction approaches 1 without reaching it.'],
    )


def _frequency(concept_id: str) -> SimulationSpec:
    """Frequency tables, dot plots and the categorical/numerical distinction."""
    data = [_pick(concept_id, f'd{index}', 1, 7) for index in range(7)]

    def marks(env: Mapping[str, float]) -> list[Mark]:
        extra = int(round(env.get('extra', 1)))
        counts: dict[int, int] = {}
        for value in data + [extra]:
            counts[value] = counts.get(value, 0) + 1
        rows: list[Mark] = []
        for value in sorted(counts):
            for level in range(counts[value]):
                rows.append(Mark(x=float(value), y=0.5 + level, label=str(value),
                                 colour='primary' if level == 0 else 'secondary'))
        return rows

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        extra = int(round(env.get('extra', 1)))
        observed = data + [extra]
        counts: dict[int, int] = {}
        for value in observed:
            counts[value] = counts.get(value, 0) + 1
        mode = max(counts, key=lambda value: counts[value])
        steps = [
            f'A frequency table counts how often each value occurs. Here there are {len(observed)} observations across '
            f'{len(counts)} distinct values.',
            'A dot plot shows exactly the same counts, with one mark per observation stacked above its value. '
            'The table is easier to total; the plot makes the shape visible at a glance.',
            f'The tallest stack sits above {mode}, which occurs {counts[mode]} times. That value is the mode.',
            f'An observation of {extra} has been added on top of the recorded data. Adding an observation can only '
            'increase the total count, never reduce it, so the distribution can only grow.',
        ]
        if extra >= max(data):
            steps.append(f'Because {extra} is at or above every recorded value, the added observation stretches the '
                         'distribution to the right and changes its shape as well as its size.')
        readouts: list[dict[str, Any]] = [
            {'label': 'Observations', 'value': f'{len(observed)}', 'detail': 'One mark per observation.'},
            {'label': 'Distinct values', 'value': f'{len(counts)}', 'detail': 'Values that occur at least once.'},
            {'label': 'Mode', 'value': f'{mode}', 'detail': f'Occurs {counts[mode]} times.'},
            {'label': 'Highest value', 'value': f'{max(observed)}', 'detail': 'The right edge of the plot.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='point_plot',
        expression='x',
        variable='x',
        parameters=[Parameter('extra', 'Value of one extra observation', 1, 7, 1, step=1, integer=True)],
        domain=(1, 7),
        discrete=True,
        title='Frequency as stacked marks',
        objective='A frequency table counts how often each value occurs, and a dot plot shows the same counts as '
                  'stacked marks so that the shape of the distribution becomes visible.',
        marks=marks,
        explain=explain,
        notes=['Each mark is one observation. The tallest stack is the mode, and adding an observation above the '
               'current maximum stretches the distribution to the right.'],
    )


def _point_plot(concept_id: str) -> SimulationSpec:
    """Ordered pairs and the four quadrants."""
    def marks(env: Mapping[str, float]) -> list[Mark]:
        rows: list[Mark] = []
        for index, (sign_x, sign_y, quadrant) in enumerate(((1, 1, 'I'), (-1, 1, 'II'), (-1, -1, 'III'), (1, -1, 'IV'))):
            x = sign_x * _pick(concept_id, f'x{index}', 2, 8)
            y = sign_y * _pick(concept_id, f'y{index}', 2, 8)
            rows.append(Mark(x=float(x), y=float(y), label=f'{chr(65 + index)}({x}, {y})',
                             colour=('primary', 'secondary', 'accent', 'primary')[index]))
        return rows

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        rows = marks(env)
        steps = [
            'An ordered pair names one position, not two separate numbers. The first coordinate is the horizontal '
            'distance from the vertical axis and the second is the vertical distance from the horizontal axis.',
            'The order matters. Swapping the two coordinates reflects the point across the diagonal line y = x and '
            'usually lands it somewhere else entirely.',
            'The signs of the two coordinates decide the quadrant: (+, +) is the first quadrant and the others follow '
            'counter-clockwise as (−, +), (−, −) and (+, −).',
            'A coordinate of zero places the point on an axis, which belongs to no quadrant at all.',
        ]
        readouts: list[dict[str, Any]] = []
        for index, mark in enumerate(rows):
            quadrant = ('I', 'II', 'III', 'IV')[index]
            readouts.append({'label': mark.label, 'value': f'Quadrant {quadrant}',
                             'detail': f'x is {"positive" if mark.x > 0 else "negative"}, '
                                       f'y is {"positive" if mark.y > 0 else "negative"}.'})
        return steps, readouts

    return SimulationSpec(
        kind='point_plot',
        expression='x',
        variable='x',
        parameters=[Parameter('x', 'Reference input x', -8, 8, 0, step=1, integer=True)],
        domain=(-8, 8),
        discrete=True,
        title='An ordered pair as a single position',
        objective='A coordinate pair gives one location. The first number is horizontal movement from the vertical '
                  'axis, the second is vertical movement from the horizontal axis, and their signs fix the quadrant.',
        marks=marks,
        explain=explain,
        notes=['The sign of each coordinate, not its size, decides the quadrant.'],
    )


def _geometry_primitives(concept_id: str) -> SimulationSpec:
    """Points, lines, rays and planes."""
    span = _pick(concept_id, 'span', 3, 7)

    def marks(env: Mapping[str, float]) -> list[Mark]:
        return [
            Mark(x=0.0, y=0.0, label='A(0, 0)', colour='primary'),
            Mark(x=float(span), y=0.0, label=f'B({span}, 0)', colour='secondary'),
            Mark(x=float(span), y=float(span), label=f'C({span}, {span})', colour='primary'),
            Mark(x=float(2 * span), y=float(2 * span), label=f'D({2 * span}, {2 * span})', colour='accent'),
        ]

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        steps = [
            'These four ideas are defined by what they contain and how far they extend, not by how they are drawn. '
            'A point has position only and no size. A line has no endpoints and continues forever in both directions.',
            'A ray has exactly one endpoint and continues forever in one direction, so reversing it gives a different ray. '
            'A segment has two endpoints and is the only one of the four with a measurable length.',
            f'A, C and D lie on one straight line: from A to C the rise and run are both {span}, and from C to D they are '
            f'both {span} again, so the same slope continues. Points sharing a slope are collinear.',
            f'B({span}, 0) is not on that line: from A to B the rise is 0 while the run is {span}, giving a slope of 0 instead of 1. '
            'A single point outside a line is enough to show the four points are not all collinear.',
        ]
        readouts: list[dict[str, Any]] = [
            {'label': 'Point', 'value': 'position only', 'detail': 'Named with a capital letter; has no length or width.'},
            {'label': 'Line', 'value': '0 endpoints', 'detail': 'Extends forever in both directions.'},
            {'label': 'Ray', 'value': '1 endpoint', 'detail': 'Extends forever in one direction.'},
            {'label': 'Segment', 'value': '2 endpoints', 'detail': 'The only one with a measurable length.'},
            {'label': 'A, C, D collinear?', 'value': 'yes', 'detail': f'Each step has rise = run = {span}, so the slope is 1 throughout.'},
            {'label': 'A, B, C, D collinear?', 'value': 'no', 'detail': 'B has slope 0 from A, while C and D have slope 1.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='geometry_primitives',
        expression='x',
        variable='x',
        parameters=[Parameter('x', 'Reference input x', -16, 16, 0, step=1, integer=True)],
        domain=(-16, 16),
        discrete=True,
        title='Points, lines, rays and planes',
        objective='These figures are defined by their endpoints and how far they extend. Collinearity is a statement '
                  'about slope, so it is checked by comparing rates of change rather than by looking at the drawing.',
        marks=marks,
        explain=explain,
        notes=[f'A, C and D sit on one straight line of slope 1; B does not, which is enough to show the points are not all collinear.'],
    )


def _vertical_line_test(concept_id: str) -> SimulationSpec:
    """Why a relation may fail to be a function."""
    span = _pick(concept_id, 'span', 2, 4)

    def marks(env: Mapping[str, float]) -> list[Mark]:
        return [Mark(x=float(y * y), y=float(y), label=f'({y * y}, {y})',
                     colour='primary' if y == 0 else 'accent')
                for y in range(-span, span + 1)]

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        line = env.get('x', float(span * span))
        upper = math.sqrt(abs(line))
        hits = sorted({round(upper, 6), round(-upper, 6)})
        steps = [
            'A relation is a function only if every input produces at most one output. The vertical line test makes that '
            'check visual: if any vertical line meets the graph more than once, one input has several outputs.',
            f'The plotted relation is x = y². Solving for y gives y = ±√x, and the two branches are the upper and lower halves of the curve.',
            f'At x = {line:g} the relation gives y = ±{upper:.4g}, so a single vertical line meets it at '
            f'y = {hits[-1]:g} and y = {hits[0]:g}.' if line > 0 else
            f'At x = 0 the two branches meet at the single point y = 0, so this one input does have just one output.',
            'One input with two outputs is enough to disqualify the relation, so x = y² is a relation but not a function. '
            'Restricting the curve to its upper branch, y = √x, does make it a function.',
        ]
        readouts: list[dict[str, Any]] = [
            {'label': 'Relation', 'value': 'x = y²', 'detail': 'A sideways parabola.'},
            {'label': 'Vertical line at x', 'value': f'{line:g}', 'detail': 'Moved by the slider.'},
            {'label': 'Intersections', 'value': f'{len(hits) if line > 0 else 1}',
             'detail': 'More than one intersection means the relation is not a function.'},
            {'label': 'Is it a function?', 'value': 'no', 'detail': 'Every x > 0 has two corresponding y values.'},
            {'label': 'Upper branch only', 'value': 'y = √x', 'detail': 'Restricting the range makes it a function.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='vertical_line_test',
        expression='sqrt(x)',
        variable='x',
        parameters=[Parameter('x', 'Position of the vertical line', 0, span * span, float(span * span), step=1, integer=True)],
        domain=(0, span * span),
        title='The vertical line test',
        objective='A relation is a function only when each input has a single output. A vertical line that meets the '
                  'graph twice is direct evidence that it does not.',
        marks=marks,
        explain=explain,
        notes=[f'The marked points are x = y² for y from {-span} to {span}. The plotted curve is only the upper branch, y = √x.'],
    )


def _domain_range(concept_id: str) -> SimulationSpec:
    """Domain and range read off a rule, including discrete vs continuous sets."""
    left = _pick(concept_id, 'left', -5, 3)
    base = _pick(concept_id, 'base', -3, 4)

    def explain(env: Mapping[str, float]) -> tuple[list[str], list[dict[str, Any]]]:
        start = env.get('h', left)
        floor = env.get('k', base)
        steps = [
            'The domain is the set of inputs the rule actually accepts and the range is the set of outputs it actually '
            'produces. Neither is a property of the drawing: both follow from the rule itself.',
            f'This rule is y = √(x − {start:g}) {_signed(floor)}. The square root of a negative number is not a real number, '
            f'so the input must satisfy x − {start:g} ≥ 0, that is x ≥ {start:g}.',
            f'Every input below x = {start:g} is excluded, which is why the curve starts abruptly instead of continuing '
            'to the left. The gap in the plot is the missing part of the domain, not a drawing error.',
            f'A square root is never negative, so the smallest output is {floor:g}, reached at x = {start:g}. That makes '
            f'the range y ≥ {floor:g}.',
            f'The endpoint is included: √0 = 0 is defined, so the domain is written with a square bracket, x ≥ {start:g}, '
            'and never as a strict inequality. An interval is continuous, so between any two allowed inputs every value '
            'in between is also allowed; a discrete domain would list separate values instead.',
        ]
        readouts: list[dict[str, Any]] = [
            {'label': 'Rule', 'value': f'y = √(x − {start:g}) {_signed(floor)}', 'detail': 'A square-root rule.'},
            {'label': 'Domain', 'value': f'x ≥ {start:g}', 'detail': f'Inputs below {start:g} give no real output.'},
            {'label': 'Range', 'value': f'y ≥ {floor:g}', 'detail': 'A square root is never negative.'},
            {'label': 'Endpoint included?', 'value': 'yes',
             'detail': f'√0 = 0 is defined, so x = {start:g} belongs to the domain.'},
            {'label': 'Type of set', 'value': 'continuous',
             'detail': 'An interval contains every value between its endpoints, unlike a discrete list.'},
        ]
        return steps, readouts

    return SimulationSpec(
        kind='domain_range',
        # h and k stay symbolic so the sliders actually move the curve; the authored
        # explainer reads their current values out of the environment.
        expression='sqrt(x - h) + k',
        variable='x',
        parameters=[Parameter('h', 'Left end of the domain', -8, 6, left, step=1, integer=True),
                    Parameter('k', 'Vertical shift k', -5, 6, base, step=1, integer=True)],
        domain=(-9, 13),
        title='Domain and range read off the rule',
        objective='The domain and range are consequences of the rule, not of the picture. A square root forces the '
                  'input to stay non-negative, and the gap in the graph is exactly the part of the domain that is excluded.',
        explain=explain,
        notes=['The curve is undefined to the left of its starting point; the gap is a missing input, not a missing value.'],
    )


#: Concepts the authored vocabulary claims, but for the wrong reason.
#:
#: ``_haystack`` includes a concept's keywords, and a keyword can mean something else in
#: another topic. "Ellipses" carries the keyword "cone" (conic sections) and was drawn as
#: a cylinder's volume; "Inverse trigonometric functions" carries "range" and was drawn as
#: a standard deviation; "Solving trigonometric equations" matched the word "solve" and was
#: drawn as a balance scale. Each entry here is a phrase specific enough that it cannot
#: appear in a concept of a different kind, and it is placed *before* the authored rules so
#: the more accurate figure wins.
_OVERRIDES: tuple[tuple[tuple[str, ...], Any], ...] = (
    (('ellipse*', 'conic section*', 'identifying conic*'), conic_figure),
    (('hyperbola*',), hyperbola_figure),
    (('parabola*',), _quadratic),
    (('unit circle',), _calc_trig_wave),
    (('inverse trigonometric',), _calc_inverse_pair),
    (('trigonometric identit*', 'solving trigonometric'), _calc_trig_wave),
    (('imaginary unit', 'imaginary number*', 'the imaginary'), _calc_complex_powers),
    (('radical equation*', 'square and cube root'), radical_figure),
    (('remainder theorem', 'long division', 'synthetic division', 'factor theorem'),
     polynomial_figure),
    # "of polynomial(s)" is required: "Limits at infinity" also carries the keyword
    # "end behaviour", and it needs its own limit figure.
    (('end behaviour of polynomial*', 'polynomial end behaviour', 'graphing polynomial',
      'polynomials and their degree'), polynomial_figure),
    (('stretching and compressing',), _transformations),
    (('absolute value equation*',), _absolute_value),
    (('symmetry in polynomial',), _calc_symmetry),
    # Not a bare ``asymptote*``: "Exponential functions and their graphs" carries that
    # keyword, and the authored course must keep its exponential figure.
    (('asymptotes and holes', 'graphing rational', 'solving rational', 'simplifying rational',
      'multiplying and dividing rational', 'rational expressions and simplification',
      'rational function*'), rational_figure),
    # No single-variable plot is honest for these; ``figure_for`` turns the probe into a
    # concept map built from the graph's own edges.
    (('matrix*', 'matrices', 'determinant*'), no_figure),
)


#: Ordered so the most specific match wins. Matching text is the concept's title,
#: topic and keywords (see ``_haystack``), never its prose summary. A trailing ``*``
#: marks a stem, everything else is matched as a whole word.
#:
#: Two needles had to be narrowed during testing because they matched a unit *name*
#: rather than a concept. Bare ``volume`` matched the unit "Perimeter, area and
#: volume" and gave polygon-area concepts a cylinder figure; bare ``sampling``
#: matched the unit "Categorical data and sampling" and gave two-way frequency
#: tables a standard-error figure. Both are now phrased as the concepts they mean.
_RULES: tuple[tuple[tuple[str, ...], Any], ...] = (
    # First, the concepts the authored vocabulary claims for the wrong reason.
    *_OVERRIDES,
    (('fraction*', 'denominator*', 'equivalent fraction*'), _fraction),
    (('percent*', 'discount*', 'tax', 'tip', 'markup*'), _percent),
    (('radical*', 'square root*', 'irrational*', 'rational exponent*'), _exponent),
    (('integer exponent*', 'exponent*', 'scientific notation*', 'power*'), _exponent),
    (('unit rate*', 'percent*', 'proportion*', 'scale drawing*', 'direct variation*',
      'unit conversion*', 'markup*'), _percent),
    (('pythagorean*', 'distance formula*', 'midpoint*'), _distance),
    (('circumference*', 'area of circle*', 'circle*'), _geometry_circle),
    (('cylinder*', 'sphere*', 'cone*', 'prism*', 'surface area*', 'volume of*'), _geometry_volume),
    (('area*', 'perimeter*', 'composite figure*', 'polygon*'), _geometry_area),
    # Non-plot figures. Placed before the algebra rules so that, for example,
    # "Terms, coefficients and constants" is not captured by the polynomial rule.
    (('vertical line test*', 'one output*'), _vertical_line_test),
    (('plotting point*', 'ordered pair*', 'coordinate plane*', 'quadrant*', 'points, lines',
      'rays and planes', 'collinear*', 'coplanar*'), _geometry_primitives),
    (('supplementary', 'complementary', 'vertical angles', 'transversal*', 'angle sum*',
      'exterior angle*', 'corresponding angles'), _angle),
    (('place value*', 'base ten', 'base-ten', 'regrouping', 'expanded form*'), _place_value),
    (('significant figure*', 'precision', 'accuracy'), _precision),
    (('part to part', 'part-to-part', 'part to whole', 'ratio table*', 'tape diagram*', 'ratios as'), _ratio),
    (('system*', 'simultaneous*', 'linear programming', 'elimination', 'substitution*'), _systems),
    (('quadratic*', 'parabola*', 'completing the square', 'discriminant*'), _quadratic),
    # Not ``factor*``: that stem also matches "factorial", which handed the permutations
    # and combinations concept a factoring figure. A whole-word ``factor`` plus the
    # inflections that really mean factoring keeps the two apart.
    (('factor', 'factors', 'factoring', 'factoriz*', 'factoris*', 'trinomial*',
      'difference of squares'), _factoring),
    (('polynomial*', 'binomial*', 'expand*', 'distributive*', 'like term*'), _polynomial_product),
    (('inequalit*', 'constraint*', 'half plane*', 'interval notation'), _inequality),
    # After the inequality rule, so "graphing inequalities on the number line" keeps
    # its inequality figure.
    (('integer addition*', 'integer subtraction*', 'number line*', 'opposite of a number*',
      'additive inverse*'), _number_line),
    (('integer multiplication*', 'integer division*', 'sign rules', 'product of two'), _sign_rules),
    (('absolute value*',), _absolute_value),
    (('transform*', 'translation*', 'reflection*', 'stretch*', 'piecewise*',
      'step function*', 'parent function*'), _transformations),
    (('exponential*', 'compound interest*', 'geometric sequence*', 'growth*', 'decay*', 'logarithm*'), _exponential_function),
    (('arithmetic sequence*', 'slope*', 'rate of change*', 'linear*', 'intercept*',
      'independent variable*', 'dependent variable*'), _linear_function),
    (('equation*', 'solve*', 'isolate*', 'literal*'), _linear_equation),
    (('evaluating expression*', 'function notation*', 'evaluate function*', 'terms, coefficients',
      'coefficients and constants', 'algebraic notation*', 'translating verbal*',
      'verbal expression*', 'word phrase*', 'substitut*'), _substitution),
    (('domain and range*', 'discrete and continuous', 'relations and multiple*'), _domain_range),
    (('standard deviation*', 'spread', 'interquartile', 'range', 'outlier*', 'mean',
      'median', 'box plot*', 'histogram*'), _statistics),
    # Before the probability rule, which used to claim "permutation*"/"combination*" and drew a
    # binomial sampling distribution for a counting lesson. The needles here are deliberately
    # narrow: bare "combination" also matches "Least-cost combination of inputs" in the
    # economics pack, which is a production problem, not a counting one, so only the plural
    # "combinations" (as in "Permutations and combinations") is accepted.
    (('permutation*', 'arrangement*', 'npr', 'ncr', 'combinations'), _arrangements),
    (('probability*', 'sample space*', 'binomial*', 'expected value*', 'conditional probability*',
      'permutation*', 'combination*', 'independent event*'), _probability),
    (('sampling method*', 'sampling bias*', 'sampling distribution*', 'sample size*', 'bias*',
      'variability*', 'survey*', 'margin of error*', 'population*', 'inference*', 'claim*',
      'proportion*'), _sampling),
    # Last, so every more specific data concept keeps its own figure.
    (('frequency table*', 'dot plot*', 'data type*', 'categorical*', 'quantitative variable*',
      'relative frequency*', 'two way table*', 'two-way table*'), _frequency),
    (('correlation*', 'scatter*', 'best fit*', 'residual*', 'association*'), _linear_function),
    # Calculus and the later Algebra 2 vocabulary. Appended last on purpose: the authored
    # course matches a rule above for every one of its concepts, so these can only ever
    # claim a concept the authored vocabulary did not already claim. Without them those
    # concepts fell through to the generic quadratic probe, which is how "Absolute and
    # conditional convergence" came to be drawn as a parabola.
    *_CALCULUS_RULES,
)


def template_for(concept: Mapping[str, Any]) -> SimulationSpec:
    """Choose and instantiate the best template for ``concept``."""
    concept_id = str(concept.get('id') or concept.get('title') or 'concept')
    haystack = _haystack(concept)
    for needles, builder in _RULES:
        if _has(haystack, *needles):
            spec = builder(concept_id)
            spec.title = f'{concept.get("title", spec.title)}: {spec.title}'
            return spec
    spec = _generic(concept_id)
    spec.title = f'{concept.get("title", spec.title)}: {spec.title}'
    return spec


def available_templates() -> list[str]:
    """Template names, for diagnostics and tests."""
    return sorted({builder.__name__.lstrip('_') for _, builder in _RULES} | {'generic'})
