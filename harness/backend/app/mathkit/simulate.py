"""Turn a simulation spec into a complete, renderable payload.

The client no longer needs to know anything about a concept. It receives a sampled
series, the features of that curve, a short table, derived readouts and the reasoning
steps - all computed from the expression in the spec. Adding a new interactive
concept therefore means writing an expression, not writing Swift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import expression as ex
from . import polynomial as poly

DEFAULT_SAMPLES = 241
MAX_SAMPLES = 801


@dataclass
class Parameter:
    id: str
    label: str
    minimum: float
    maximum: float
    value: float
    step: float = 0.1
    integer: bool = False
    unit: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'label': self.label, 'min': self.minimum, 'max': self.maximum,
                'value': self.value, 'step': self.step, 'integer': self.integer, 'unit': self.unit}


@dataclass
class Part:
    """One row of a part-whole (bar) model.

    Not every quantity a learner must see is a function of one variable. A fraction
    bar, a tape diagram and a ratio table are all part-whole models: a whole cut into
    ``denominator`` equal parts with ``shaded`` of them marked. Those are drawn, not
    plotted, so they travel in the payload as their own primitive instead of being
    forced through the sampling machinery, which would flatten ``1/4 + n/3`` into the
    decimal line ``0.25n + 0.6667`` and destroy the very structure being taught.
    """

    label: str
    denominator: int
    shaded: int
    colour: str = 'primary'
    note: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {'label': self.label, 'denominator': self.denominator, 'shaded': self.shaded,
                'colour': self.colour, 'note': self.note}


@dataclass
class Mark:
    """A labelled point placed on the coordinate grid.

    Used by concepts whose figure is a *set of points* rather than a function: the
    four quadrants, ordered pairs, and the vertical line test, where the whole point
    is that one vertical line meets the relation twice.
    """

    x: float
    y: float
    label: str = ''
    colour: str = 'primary'

    def to_dict(self) -> dict[str, Any]:
        return {'x': self.x, 'y': self.y, 'label': self.label, 'colour': self.colour}


#: Kinds whose figure is a scene (bars, marks) rather than a sampled curve. The client
#: draws the scene and hides the plot, so a fraction bar is never drawn as a line.
SCENE_KINDS = frozenset({'fraction_bar', 'point_plot', 'geometry_primitives'})


@dataclass
class SimulationSpec:
    """A declarative description of one interactive figure."""

    kind: str
    expression: str
    variable: str = 'x'
    parameters: list[Parameter] = field(default_factory=list)
    domain: tuple[float, float] = (-6.0, 6.0)
    samples: int = DEFAULT_SAMPLES
    title: str = ''
    objective: str = ''
    #: Extra expressions, e.g. the second line of a system.
    secondary: str = ''
    relation: str = '='
    #: Fixed values that are not user parameters, used when substituting.
    constants: dict[str, float] = field(default_factory=dict)
    discrete: bool = False
    notes: list[str] = field(default_factory=list)
    #: Part-whole rows, recomputed from the current parameters. ``None`` for figures
    #: that are pure function plots.
    parts: Callable[[Mapping[str, float]], list[Part]] | None = None
    #: Labelled points, recomputed from the current parameters.
    marks: Callable[[Mapping[str, float]], list[Mark]] | None = None
    #: Authored reasoning, recomputed from the current parameters. When present it
    #: replaces the generic explainer. This is what lets a template teach *its own*
    #: concept instead of describing whichever curve the expression happens to draw.
    explain: Callable[[Mapping[str, float]], tuple[list[str], list[dict[str, Any]]]] | None = None
    #: Display the authored expression verbatim instead of normalising it to
    #: coefficients. Fraction bars need this: "1/4 + n/3" must not become
    #: "0.25n + 0.6667", which is the representation the bar model exists to avoid.
    raw_display: bool = False

    def values(self, overrides: Mapping[str, float] | None = None) -> dict[str, float]:
        env = {p.id: p.value for p in self.parameters}
        env.update(self.constants)
        for key, value in (overrides or {}).items():
            if key in env or key == self.variable:
                env[key] = float(value)
        return env


def _finite(value: float) -> float | None:
    return value if isinstance(value, float) and math.isfinite(value) else None


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def sample(spec: SimulationSpec, env: Mapping[str, float], samples: int | None = None) -> list[list[float | None]]:
    """Sample the expression across the domain. Undefined points become ``None``."""
    ast = ex.parse(spec.expression, variables=(spec.variable, *env))
    total = max(2, min(MAX_SAMPLES, samples or spec.samples))
    low, high = spec.domain
    if high <= low:
        high = low + 1
    step = (high - low) / (total - 1)
    points: list[list[float | None]] = []
    for index in range(total):
        x = low + index * step
        if spec.discrete:
            x = round(x)
        y = ex.evaluate(ast, {**env, spec.variable: x})
        points.append([_round(x, 6), _round(y, 6) if math.isfinite(y) and abs(y) < 1e9 else None])
    return points


def _scan_extrema(points: Sequence[Sequence[float | None]]) -> list[dict[str, float]]:
    """Local minima and maxima of a sampled series."""
    found: list[dict[str, float]] = []
    for index in range(1, len(points) - 1):
        previous, current, following = points[index - 1][1], points[index][1], points[index + 1][1]
        if previous is None or current is None or following is None:
            continue
        if current >= previous and current >= following and current > previous:
            found.append({'x': points[index][0], 'y': current, 'kind': 'maximum'})
        elif current <= previous and current <= following and current < previous:
            found.append({'x': points[index][0], 'y': current, 'kind': 'minimum'})
    # Collapse plateaus into a single reported turning point.
    collapsed: list[dict[str, float]] = []
    for item in found:
        if collapsed and abs(item['x'] - collapsed[-1]['x']) < 1e-6 and item['kind'] == collapsed[-1]['kind']:
            continue
        collapsed.append(item)
    return collapsed[:6]


def _gaps(points: Sequence[Sequence[float | None]]) -> list[list[float]]:
    """Domain intervals where the expression is undefined (vertical asymptotes)."""
    gaps: list[list[float]] = []
    start: float | None = None
    for x, y in points:
        if y is None:
            if start is None:
                start = x
        elif start is not None:
            gaps.append([_round(start, 4), _round(x, 4)])
            start = None
    if start is not None:
        gaps.append([_round(start, 4), _round(points[-1][0], 4)])
    return gaps


def _monotonic(points: Sequence[Sequence[float | None]]) -> str:
    values = [(x, y) for x, y in points if y is not None]
    if len(values) < 3:
        return 'unknown'
    rising = sum(1 for a, b in zip(values, values[1:]) if b[1] > a[1] + 1e-9)
    falling = sum(1 for a, b in zip(values, values[1:]) if b[1] < a[1] - 1e-9)
    total = len(values) - 1
    if rising == total:
        return 'increasing'
    if falling == total:
        return 'decreasing'
    if rising == 0 and falling == 0:
        return 'constant'
    return 'neither'


def _probe_table(ast: ex.Node, env: Mapping[str, float], variable: str,
                 points: Sequence[Sequence[float | None]], rows: int = 5) -> list[dict[str, float]]:
    values = [point for point in points if point[1] is not None]
    if not values:
        return []
    stride = max(1, len(values) // rows)
    chosen = values[::stride][:rows]
    return [{'x': point[0], 'y': point[1]} for point in chosen]


def _steps_for_polynomial(poly_form: poly.Poly, spec: SimulationSpec,
                          env: Mapping[str, float], roots: Sequence[float]) -> tuple[list[str], list[dict[str, Any]]]:
    """Derived explanation and readouts for a polynomial, degree by degree."""
    variable = spec.variable
    steps: list[str] = []
    readouts: list[dict[str, Any]] = []
    top = poly.degree(poly_form)

    if top == 0:
        value = poly_form.get(0, 0.0)
        steps.append(f'The rule is constant: {variable} never appears, so the output is {value:g} for every input.')
        readouts.append({'label': 'Value', 'value': f'{value:g}', 'detail': 'A constant rule.'})
        return steps, readouts

    if top == 1:
        slope, intercept = poly_form.get(1, 0.0), poly_form.get(0, 0.0)
        steps.append(f'This is linear, so it has the form y = m·{variable} + b with m = {slope:g} and b = {intercept:g}.')
        steps.append(f'Each additional unit of {variable} changes the output by {slope:g}; that constant rate is what makes the graph a straight line.')
        if slope != 0:
            steps.append(f'Setting y = 0 gives {variable} = {-intercept / slope:g}, the point where the line crosses the horizontal axis.')
        else:
            steps.append('Because m = 0 the rule is constant and never crosses the horizontal axis.')
        readouts.append({'label': 'Rate of change', 'value': f'{slope:g}',
                         'detail': 'Output units per input unit.'})
        readouts.append({'label': f'{variable}-intercept', 'value': f'{intercept:g}',
                         'detail': f'Output when {variable} = 0.'})
        if slope != 0:
            readouts.append({'label': 'Zero', 'value': f'{-intercept / slope:g}',
                             'detail': 'Where the output is zero.'})
        return steps, readouts

    if top == 2:
        a, b, c = poly_form.get(2, 0.0), poly_form.get(1, 0.0), poly_form.get(0, 0.0)
        disc = b * b - 4 * a * c
        turning = poly.vertex(poly_form)
        steps.append(f'This is quadratic with a = {a:g}, b = {b:g}, c = {c:g}. Its graph is a parabola.')
        steps.append(f'The discriminant b² − 4ac = {disc:g}, so there ' +
                     ('are two distinct real roots.' if disc > 0 else
                      'is exactly one real root (a repeated root).' if disc == 0 else
                      'are no real roots: the parabola never meets the horizontal axis.'))
        if turning:
            steps.append(f'The vertex sits at {variable} = -b/(2a) = {turning[0]:g}, giving a '
                         f'{"minimum" if a > 0 else "maximum"} value of {turning[1]:g}.')
        integer_pair = poly.integer_factorisation(int(a), int(b), int(c)) if float(a).is_integer() and float(b).is_integer() and float(c).is_integer() else None
        if integer_pair:
            r, s = integer_pair
            steps.append(f'Because {r} + {s} = {b:g} and {r} × {s} = {c:g}, it factors as '
                         f'({variable} {r:+g})({variable} {s:+g}).')
        elif roots:
            steps.append('The roots are not integers, so factoring over the integers is not available; the quadratic formula or completing the square applies.')
        readouts.append({'label': 'Discriminant', 'value': f'{disc:g}',
                         'detail': 'Positive: two real roots. Zero: one. Negative: none.'})
        if turning:
            readouts.append({'label': 'Vertex', 'value': f'({turning[0]:g}, {turning[1]:g})',
                             'detail': f'{"Minimum" if a > 0 else "Maximum"} of the curve.'})
        readouts.append({'label': 'y-intercept', 'value': f'{c:g}', 'detail': f'Value when {variable} = 0.'})
        if roots:
            readouts.append({'label': 'Real roots',
                             'value': ', '.join(f'{root:g}' for root in roots),
                             'detail': 'Where the curve meets the horizontal axis.'})
        return steps, readouts

    steps.append(f'This is a degree-{top} polynomial. Its real roots were located numerically by scanning for sign changes and refining each one.')
    steps.append('For a polynomial of degree n, at most n real roots are possible, and the leading coefficient controls behaviour far from the origin.')
    readouts.append({'label': 'Degree', 'value': f'{top}', 'detail': 'Highest power present.'})
    readouts.append({'label': 'Leading coefficient', 'value': f'{poly.leading(poly_form):g}',
                     'detail': 'Controls the long-run direction.'})
    if roots:
        readouts.append({'label': 'Real roots', 'value': ', '.join(f'{root:.4g}' for root in roots),
                         'detail': 'Located numerically.'})
    return steps, readouts


def _steps_generic(ast: ex.Node, spec: SimulationSpec, env: Mapping[str, float],
                   points: Sequence[Sequence[float | None]], extrema: Sequence[Mapping[str, float]]) -> tuple[list[str], list[dict[str, Any]]]:
    """Explanation for expressions that are not polynomials."""
    steps: list[str] = []
    readouts: list[dict[str, Any]] = []
    probe = env.get(spec.variable, 0.0)
    value = ex.evaluate(ast, {**env, spec.variable: probe})
    trend = _monotonic(points)
    steps.append(f'The rule is {ex.to_string(ex.simplify(ast))}. It is not a polynomial, so its shape is read from the sampled curve rather than from coefficients.')
    steps.append(f'Across the displayed interval the output is {trend}.')
    if extrema:
        first = extrema[0]
        steps.append(f'The curve has a {first["kind"]} near {spec.variable} = {first["x"]:g} with value {first["y"]:.4g}.')
    derivative_ast = ex.simplify(ex.derivative(ast, spec.variable))
    if probe is not None and math.isfinite(value):
        readouts.append({'label': f'Value at {spec.variable} = {probe:g}', 'value': f'{value:.4g}', 'detail': 'Current probe point.'})
    slope = ex.evaluate(derivative_ast, {**env, spec.variable: probe})
    if math.isfinite(slope):
        readouts.append({'label': 'Local rate of change', 'value': f'{slope:.4g}',
                         'detail': 'Value of the derivative at the probe point.'})
    readouts.append({'label': 'Behaviour', 'value': trend.capitalize(), 'detail': 'Across the displayed interval.'})
    return steps, readouts


EMPTY_FEATURES: dict[str, Any] = {'roots': [], 'degree': None, 'discriminant': None,
                                  'leading_coefficient': None, 'vertex': None, 'y_intercept': None}


def _poly_features(poly_form: poly.Poly | None) -> tuple[dict[str, Any], list[float]]:
    """Curve features for a polynomial, or the empty feature set for anything else."""
    if poly_form is None:
        return dict(EMPTY_FEATURES), []
    roots = poly.real_roots(poly_form)
    turning = poly.vertex(poly_form)
    return ({
        'roots': [_round(root) for root in roots],
        'y_intercept': _round(poly.evaluate(poly_form, 0.0)),
        'degree': poly.degree(poly_form),
        'discriminant': _round(poly.discriminant(poly_form)),
        'leading_coefficient': _round(poly.leading(poly_form)),
        'vertex': ({'x': _round(turning[0]), 'y': _round(turning[1])} if turning else None),
    }, roots)


def build(spec: SimulationSpec, overrides: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Produce the full payload for one simulation."""
    env = spec.values(overrides)
    source_ast = ex.parse(spec.expression, variables=(spec.variable, *env))
    # Fold the numeric parameters in before anything is analysed. The analysis layer
    # only understands expressions whose coefficients are numbers, so without this a
    # template that declared a slider for a coefficient would have an inert slider and
    # would silently lose the exact roots, vertex and discriminant readouts.
    ast = ex.substitute(source_ast, env, keep=(spec.variable,))
    poly_form = poly.from_ast(ast, spec.variable)
    # Prefer the polynomial-normalised form for display: it collects like terms and
    # renders "x^2 + 5x − 6" rather than the raw "1*x^2 + 5*x + -6". Scene kinds opt
    # out, because normalising a fraction bar destroys the structure being taught.
    if spec.raw_display:
        substituted = source_ast
    else:
        substituted = poly.to_ast(poly_form) if poly_form is not None else ast

    scene = spec.kind in SCENE_KINDS
    points = sample(spec, env)
    features, roots = _poly_features(None if scene else poly_form)

    # An authored explainer wins. It is the template's own account of its concept, and
    # it is the only way a dot plot can avoid being described as a straight line.
    if spec.explain is not None:
        steps, readouts = spec.explain(env)
    elif poly_form is not None and not scene:
        steps, readouts = _steps_for_polynomial(poly_form, spec, env, roots)
    else:
        numeric_roots = _numeric_roots_generic(ast, env, spec)
        steps, readouts = _steps_generic(ast, spec, env, points, _scan_extrema(points))
        features['roots'] = [_round(root) for root in numeric_roots]

    features['extrema'] = _scan_extrema(points)
    features['gaps'] = _gaps(points)
    features['behaviour'] = _monotonic(points)
    features.setdefault('y_intercept', None)
    if features['y_intercept'] is None and not scene:
        at_zero = ex.evaluate(ast, {**env, spec.variable: 0.0})
        features['y_intercept'] = _round(at_zero) if math.isfinite(at_zero) else None

    secondary_payload = None
    if spec.secondary:
        secondary_source = ex.parse(spec.secondary, variables=(spec.variable, *env))
        secondary_ast = ex.substitute(secondary_source, env, keep=(spec.variable,))
        # Same normalisation as the primary expression, so a system prints
        # "-x − 2" rather than "-1x + -2".
        secondary_poly = poly.from_ast(secondary_ast, spec.variable)
        secondary_display = poly.to_ast(secondary_poly) if secondary_poly is not None else secondary_ast
        secondary_points = sample(SimulationSpec(kind=spec.kind, expression=spec.secondary,
                                                 variable=spec.variable, parameters=spec.parameters,
                                                 domain=spec.domain, samples=spec.samples,
                                                 constants=spec.constants, discrete=spec.discrete), env)
        secondary_payload = {'expression': ex.to_string(secondary_display),
                             'latex': ex.to_latex(secondary_display),
                             'series': secondary_points}

    parts_payload = [part.to_dict() for part in spec.parts(env)] if spec.parts else []
    marks_payload = [mark.to_dict() for mark in spec.marks(env)] if spec.marks else []

    probe = env.get(spec.variable)
    probe_value = None
    if probe is not None:
        candidate = ex.evaluate(ast, {**env, spec.variable: probe})
        probe_value = _round(candidate) if math.isfinite(candidate) else None

    return {
        'kind': spec.kind,
        'figure': 'scene' if scene else 'curve',
        'title': spec.title or spec.kind.replace('_', ' ').title(),
        'objective': spec.objective,
        #: The independent variable's name, so a client can label an axis and a content
        #: generator can ask "evaluate this at ..." without re-deriving the spec.
        'variable': spec.variable,
        'expression': {
            'source': spec.expression,
            'substituted': ex.to_string(substituted),
            'latex': ex.to_latex(substituted),
            'degree': poly.degree(poly_form) if poly_form is not None else None,
        },
        'secondary': secondary_payload,
        'parts': parts_payload,
        'marks': marks_payload,
        'parameters': [parameter.to_dict() for parameter in spec.parameters],
        'domain': {'min': spec.domain[0], 'max': spec.domain[1], 'samples': len(points)},
        'discrete': spec.discrete,
        'series': [] if scene else points,
        'features': features,
        'table': [] if scene else _probe_table(ast, env, spec.variable, points),
        'steps': steps,
        'readouts': readouts,
        'probe': {'x': probe, 'y': probe_value} if probe is not None else None,
        'notes': list(spec.notes) + ([] if scene else [
            'The curve is sampled from the expression above. Predict before you move a parameter, then check with an independent calculation.',
        ]),
    }


def _numeric_roots_generic(ast: ex.Node, env: Mapping[str, float], spec: SimulationSpec) -> list[float]:
    """Sign-change roots for expressions that are not polynomials."""
    low, high = spec.domain
    found: list[float] = []
    previous_x, previous_y = low, ex.evaluate(ast, {**env, spec.variable: low})
    steps = 600
    for index in range(1, steps + 1):
        x = low + (high - low) * index / steps
        y = ex.evaluate(ast, {**env, spec.variable: x})
        if not math.isfinite(previous_y) or not math.isfinite(y):
            previous_x, previous_y = x, y
            continue
        if previous_y == 0:
            found.append(previous_x)
        elif previous_y * y < 0:
            found.append(_bisect_generic(ast, env, spec.variable, previous_x, x))
        previous_x, previous_y = x, y
    unique: list[float] = []
    for root in sorted(found):
        if not unique or abs(root - unique[-1]) > 1e-6:
            unique.append(root)
    return unique[:8]


def _bisect_generic(ast: ex.Node, env: Mapping[str, float], variable: str,
                    low: float, high: float, iterations: int = 70) -> float:
    low_value = ex.evaluate(ast, {**env, variable: low})
    for _ in range(iterations):
        middle = (low + high) / 2
        middle_value = ex.evaluate(ast, {**env, variable: middle})
        if not math.isfinite(middle_value) or middle_value == 0:
            return middle
        if low_value * middle_value < 0:
            high = middle
        else:
            low, low_value = middle, middle_value
    return (low + high) / 2
