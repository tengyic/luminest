"""Tests for the generated-interactive-content engine.

The engine exists so that a figure can be *derived* from a concept rather than
hand-written in the client. These tests pin the three things that make that safe:
the symbolic layer is correct, the payload is well formed for every concept in the
shipped course graph, and template selection does not silently hand a concept a
figure about a different idea.
"""

import math
import re

import pytest

from app.curriculum import KNOWLEDGE_GRAPH
from app.mathkit import expression as ex
from app.mathkit import polynomial as poly
from app.mathkit import simulate, templates

#: Rendered text that would indicate a formatting bug rather than a maths bug.
MALFORMED = re.compile(r'\+ -|\u2212 -| - -|\bNone\b|\bnan\b|\binf\b')


def _nodes():
    return [node.to_dict() for node in KNOWLEDGE_GRAPH.nodes.values()]


# --------------------------------------------------------------------- expressions


@pytest.mark.parametrize('source, expected', [
    ('2 + 3*4', 14.0),
    ('2(3 + 4)', 14.0),          # implicit multiplication
    ('-x^2', -9.0),              # unary minus binds looser than the power
    ('(-x)^2', 9.0),
    ('1/2 + 1/3', 5 / 6),
    ('sqrt(16) + abs(-3)', 7.0),
])
def test_expression_evaluation(source, expected):
    ast = ex.parse(source, variables=('x',))
    assert ex.evaluate(ast, {'x': 3.0}) == pytest.approx(expected)


def test_expression_rejects_unknown_names_and_code():
    with pytest.raises(ex.MathSyntaxError):
        ex.parse('nope + 1', variables=('x',))
    # Nothing is ever handed to eval, so a call to an unknown function is a syntax
    # error rather than an execution.
    with pytest.raises(ex.MathSyntaxError):
        ex.parse('__import__("os")', variables=('x',))


@pytest.mark.parametrize('source', [
    '1/(2*sqrt(x))',
    '(x + 2)*(x + 3)',
    '1/(x - 1) + 3/(x + 2)',
    '2*x^2 - 3*x + 1',
    'a*(x + b) - c/x',
    '-(x + 1)^2',
])
def test_rendered_expression_reparses_to_the_same_function(source):
    """The real invariant for rendering: the printed form must mean the same thing.

    Checking a literal string only pins today's spacing. Re-parsing the rendered text
    and comparing values catches the failure that actually matters, which is a missing
    bracket silently changing the formula (``1/(2·sqrt(x))`` vs ``1/2·sqrt(x)``).
    """
    ast = ex.parse(source, variables=('x', 'a', 'b', 'c'))
    rendered = ex.to_string(ast)
    reparsed = ex.parse(rendered, variables=('x', 'a', 'b', 'c'))
    compared = 0
    for point in (-2.5, 0.5, 1.75, 3.0):
        env = {'x': point, 'a': 2.0, 'b': -1.5, 'c': 4.0}
        original, round_tripped = ex.evaluate(ast, env), ex.evaluate(reparsed, env)
        if not (math.isfinite(original) and math.isfinite(round_tripped)):
            continue  # sqrt(-2.5) and friends: undefined on both sides, nothing to compare
        assert round_tripped == pytest.approx(original), (source, rendered, point)
        compared += 1
    assert compared, f'{source} was undefined everywhere it was tested'


def test_rendered_output_can_be_read_back_in():
    """The printed form uses a true minus sign, so the lexer has to accept it."""
    assert ex.to_string(ex.parse('x^2 - 6', variables=('x',))) == 'x^2 \u2212 6'
    reparsed = ex.parse(ex.to_string(ex.parse('(x+2)*(x-3)', variables=('x',))), variables=('x',))
    assert ex.evaluate(reparsed, {'x': 5.0}) == pytest.approx(14.0)


@pytest.mark.parametrize('typed, expected', [
    ('2\u00b7x', 6.0),      # middle dot
    ('2\u00d7x', 6.0),      # multiplication sign
    ('6\u00f7x', 2.0),      # division sign
    ('5\u2212x', 2.0),      # true minus sign
])
def test_typographic_operators_are_accepted(typed, expected):
    assert ex.evaluate(ex.parse(typed, variables=('x',)), {'x': 3.0}) == pytest.approx(expected)


def test_denominator_of_a_product_is_bracketed():
    """``1/2·sqrt(x)`` would be a different formula from ``1/(2·sqrt(x))``."""
    rendered = ex.to_string(ex.parse('1/(2*sqrt(x))', variables=('x',)))
    assert rendered.startswith('1/('), rendered


def test_latex_uses_braces_for_radicals():
    ast = ex.parse('sqrt(x) + abs(x)', variables=('x',))
    latex = ex.to_latex(ast)
    assert r'\sqrt{x}' in latex and r'\left|x\right|' in latex


def test_derivative_of_a_product_is_normalised():
    ast = ex.parse('(x + 2)*(x + 3)', variables=('x',))
    derivative = ex.simplify(ex.derivative(ast, 'x'))
    # ``simplify`` alone does not collect like terms, so the derivative of the product
    # still reads x + 3 + x + 2. Normalising through the polynomial layer is what
    # produces 2x + 5, and that is the form the payload displays.
    assert ex.evaluate(derivative, {'x': 4.0}) == pytest.approx(13.0)
    form = poly.from_ast(derivative, 'x')
    assert form == {1: 2.0, 0: 5.0}
    assert ex.to_string(poly.to_ast(form)) == '2x + 5'


# --------------------------------------------------------------------- polynomials


def test_polynomial_collects_like_terms_and_solves_exactly():
    form = poly.from_ast(ex.parse('1*x^2 + 5*x + -6', variables=('x',)), 'x')
    assert form == {2: 1.0, 1: 5.0, 0: -6.0}
    assert sorted(poly.real_roots(form)) == [-6.0, 1.0]
    assert poly.discriminant(form) == pytest.approx(49.0)
    assert poly.integer_factorisation(1, 5, -6) == (-1, 6)


def test_non_polynomial_is_reported_as_such():
    assert poly.from_ast(ex.parse('sin(x)', variables=('x',)), 'x') is None
    assert poly.from_ast(ex.parse('1/x', variables=('x',)), 'x') is None


# ----------------------------------------------------------------- payload shape


def test_fraction_bar_is_a_bar_model_not_a_flattened_line():
    """The defect this replaces printed ``0.25n + 0.6667`` for a fraction sum."""
    spec = templates._fraction('fractions_and_decimals')
    payload = simulate.build(spec)
    assert payload['kind'] == 'fraction_bar'
    assert payload['figure'] == 'scene'
    assert payload['series'] == [], 'a bar model must not be drawn as a curve'
    assert payload['parts'], 'the bar rows are the figure'
    # The authored structure survives; it is not normalised to coefficients.
    assert '/' in payload['expression']['substituted']
    assert '0.25' not in payload['expression']['substituted']
    for part in payload['parts']:
        assert part['denominator'] >= 1
        assert part['shaded'] >= 0
    # The three rows are the two addends and their common-denominator total.
    first, second, total = payload['parts']
    assert total['denominator'] % first['denominator'] == 0
    assert total['denominator'] % second['denominator'] == 0
    assert total['shaded'] == first['shaded'] * (total['denominator'] // first['denominator']) + \
        second['shaded'] * (total['denominator'] // second['denominator'])


def test_fraction_bars_recompute_when_the_numerator_moves():
    spec = templates._fraction('fractions_and_decimals')
    low = simulate.build(spec, {'n': 1})['parts'][-1]
    high = simulate.build(spec, {'n': spec.parameters[0].maximum})['parts'][-1]
    assert high['shaded'] > low['shaded'], 'moving the slider must change the bar'
    assert high['denominator'] == low['denominator'], 'the common denominator is fixed by the two denominators'


def test_system_second_line_is_normalised_too():
    """The defect this replaces rendered the second line as ``-1x + -2``."""
    payload = simulate.build(templates._systems('systems_of_equations'))
    for expression in (payload['expression']['substituted'], payload['secondary']['expression']):
        assert not MALFORMED.search(expression), expression
        assert 'x' in expression, 'both lines must depend on x'


def test_scene_kinds_supply_a_scene_and_curve_kinds_supply_a_series():
    for node in _nodes():
        payload = simulate.build(templates.template_for(node))
        if payload['figure'] == 'scene':
            assert payload['parts'] or payload['marks'], node['id']
            assert payload['series'] == [] and payload['table'] == [], node['id']
        else:
            assert len(payload['series']) >= 2, node['id']
            assert payload['table'], node['id']


# ------------------------------------------------------------ whole-graph coverage


def test_every_concept_produces_a_well_formed_figure():
    """The engine must cover the shipped course, not a hand-picked sample."""
    problems = []
    for node in _nodes():
        spec = templates.template_for(node)
        payload = simulate.build(spec)
        if not payload['steps'] or not payload['readouts']:
            problems.append((node['id'], 'empty explanation'))
        for text in payload['steps'] + [str(r) for r in payload['readouts']] + payload['notes']:
            if MALFORMED.search(text):
                problems.append((node['id'], text[:90]))
        if MALFORMED.search(payload['expression']['substituted']):
            problems.append((node['id'], payload['expression']['substituted']))
    assert not problems, problems


def test_every_parameter_extreme_still_builds():
    """Sliders must not be able to produce a crash or a NaN payload."""
    for node in _nodes():
        spec = templates.template_for(node)
        for parameter in spec.parameters:
            for value in (parameter.minimum, parameter.maximum, parameter.value):
                payload = simulate.build(spec, {parameter.id: value})
                assert payload['steps'], (node['id'], parameter.id, value)
                for readout in payload['readouts']:
                    assert 'nan' not in str(readout['value']).lower(), (node['id'], readout)


def test_no_concept_falls_back_to_the_generic_probe():
    """A quadratic probe is wrong content for "Points, lines, rays and planes"."""
    generic = [n['title'] for n in _nodes() if templates.template_for(n).kind == 'function_probe']
    assert generic == [], generic


def test_template_selection_uses_whole_words():
    """``tip`` used to match inside "mul*tip*le representations"."""
    assert not templates._has('relations and multiple representations', 'tip')
    assert templates._has('find the tip', 'tip')
    assert templates._has('solving inequalities', 'inequalit*')
    assert not templates._has('meaning of a word', 'mean')
    assert templates._has('the mean value', 'mean')


def test_template_choice_is_deterministic():
    node = _nodes()[0]
    first = simulate.build(templates.template_for(node))
    second = simulate.build(templates.template_for(node))
    assert first == second, 'generated content must be reproducible across restarts'


def test_unmatched_concept_still_gets_an_honest_generic_figure():
    spec = templates.template_for({'id': 'nothing_matches', 'title': 'Totally new idea',
                                   'topic': 'unseen', 'keywords': []})
    payload = simulate.build(spec)
    assert payload['kind'] == 'function_probe'
    assert payload['steps'], 'the fallback must still explain itself'


def test_number_line_explains_direction_without_malformed_signs():
    payload = simulate.build(templates._number_line('integer_addition_and_subtraction'), {'d': -4})
    joined = ' '.join(payload['steps'])
    assert 'Subtracting a negative' in joined
    assert not MALFORMED.search(joined), joined


def test_domain_figure_reports_the_excluded_region():
    payload = simulate.build(templates._domain_range('domain_and_range'))
    domain = next(r for r in payload['readouts'] if r['label'] == 'Domain')
    assert domain['value'].startswith('x ≥')
    # A square root is undefined below its start, so the sampled series must contain
    # missing points rather than a smooth curve.
    assert any(point[1] is None for point in payload['series'])


def test_vertical_line_test_marks_both_branches():
    payload = simulate.build(templates._vertical_line_test('functions_and_the_vertical_line_test'))
    positives = [m for m in payload['marks'] if m['y'] > 0]
    negatives = [m for m in payload['marks'] if m['y'] < 0]
    assert positives and negatives, 'both branches are needed to show the relation is not a function'
    verdict = next(r for r in payload['readouts'] if 'function' in r['label'].lower())
    assert verdict['value'] == 'no'


def test_every_declared_parameter_actually_moves_the_figure():
    """An inert slider is worse than no slider: it teaches that a coefficient is inert.

    ``_quadratic`` used to bake a, b and c into the expression string, so dragging
    them changed nothing at all. Folding parameter values into the expression before
    analysis is what makes this hold for every template.
    """
    inert = []
    for node in _nodes():
        spec = templates.template_for(node)
        base = simulate.build(spec)
        for parameter in spec.parameters:
            moved = parameter.value + (1 if parameter.value < parameter.maximum else -1)
            if moved == parameter.value:
                continue
            payload = simulate.build(spec, {parameter.id: moved})
            if payload == base:
                inert.append((node['id'], parameter.id))
    assert not inert, inert


def test_folding_parameters_keeps_the_exact_analysis():
    """A symbolic coefficient must not cost the discriminant, vertex or exact roots."""
    spec = templates._quadratic('quadratic_expressions_and_their_graphs')
    payload = simulate.build(spec, {'a': 1, 'b': 5, 'c': -6})
    assert payload['expression']['substituted'] == 'x^2 + 5x \u2212 6'
    assert sorted(payload['features']['roots']) == [-6.0, 1.0]
    assert payload['features']['discriminant'] == pytest.approx(49.0)
    assert payload['features']['vertex']['x'] == pytest.approx(-2.5)


def test_signed_second_terms_render_as_subtraction():
    """``x + -3`` must print as ``x − 3``, in both plain text and LaTeX."""
    ast = ex.substitute(ex.parse('sqrt(x - h) + k', variables=('x', 'h', 'k')), {'h': 3, 'k': -2},
                        keep=('x',))
    assert ex.to_string(ast) == 'sqrt(x \u2212 3) \u2212 2'
    assert '+ -' not in ex.to_string(ast)
    assert '+ -' not in ex.to_latex(ast)
    # And the rendered form must still be readable by the parser.
    assert ex.evaluate(ex.parse(ex.to_string(ast), variables=('x',)), {'x': 7.0}) == pytest.approx(0.0)


def test_domain_figure_renders_signed_shifts():
    """The generated domain figure must not print ``+ -1`` for a negative shift."""
    for seed in ('domain_and_range', 'discrete_and_continuous_domains',
                 'relations_and_multiple_representations'):
        payload = simulate.build(templates._domain_range(seed))
        assert not MALFORMED.search(payload['expression']['substituted']), payload['expression']
        assert not MALFORMED.search(payload['expression']['latex']), payload['expression']


def test_simulation_sampling_is_bounded():
    spec = templates.template_for(_nodes()[0])
    huge = simulate.SimulationSpec(kind='linear', expression='x', variable='x',
                                   parameters=[], domain=(-6, 6), samples=10 ** 6)
    assert len(simulate.sample(huge, {})) == simulate.MAX_SAMPLES


def test_quadratic_readouts_agree_with_the_curve():
    """The reported roots must actually satisfy the displayed quadratic."""
    spec = templates._quadratic('quadratic_expressions_and_their_graphs')
    payload = simulate.build(spec)
    assert payload['features']['degree'] == 2
    a, b, c = (parameter['value'] for parameter in payload['parameters'][:3])
    for root in payload['features']['roots']:
        assert math.isclose(a * root * root + b * root + c, 0.0, abs_tol=1e-6)
    vertex = payload['features']['vertex']
    assert math.isclose(vertex['x'], -b / (2 * a), abs_tol=1e-6)
