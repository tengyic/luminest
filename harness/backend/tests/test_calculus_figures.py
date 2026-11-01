"""Figures for the calculus and Algebra 2 concepts.

The failure these tests exist for is specific. ``templates.py`` matched concepts against
the authored mathematics course's vocabulary. When AP Calculus and Algebra 2 were added
they inherited the same engine but not the vocabulary, so 62% of AP Calculus concepts
fell through to ``_generic`` — a quadratic probe. "Absolute and conditional convergence"
was drawn as ``0.5x^2 - x + 1`` and labelled with the concept's name. Nothing raised an
error, and a learner would have been shown a meaningless parabola presented as calculus.

So there are two guarantees, and both are cheap to check:

1. **No mathematics concept is served a generic probe.** Not through ``template_for``,
   and not through ``figure_for``, which is the last gate before a learner sees it.
2. **The calculus families get a figure about their own idea** — a hole for a limit, a
   secant for a derivative, partial sums for a series — rather than a plausible-looking
   curve chosen by accident.

The third guarantee is quieter but was a real bug: the rendered expression has to mean
what the engine computed. ``-0.5^n`` reads as ``-(0.5^n)``, which differs in sign at
every odd exponent, so a negative base must be bracketed in both the plain and LaTeX
forms.
"""

from __future__ import annotations

import re

import pytest

from app import courses, figures
from app.mathkit import expression as ex
from app.mathkit import simulate, templates

MATHEMATICS = [spec for spec in courses.COURSES if spec.subject_kind == 'mathematics']
REQUESTED_MATHEMATICS = ('algebra_2', 'ap_calculus')

GENERIC_NOTE = 'generic probe used when a concept has no more specific figure yet'

#: The concept each family is for, and the template that must answer it. These are the
#: concepts whose old figure was a parabola.
EXPECTED_KINDS = {
    'ap_calculus_defining_limits_and_limit_notation': 'limit_hole',
    'ap_calculus_estimating_limits_from_graphs_and_tables': 'limit_hole',
    'ap_calculus_continuity_at_a_point': 'limit_hole',
    'ap_calculus_limits_at_infinity': 'limits_infinity',
    'ap_calculus_the_squeeze_theorem': 'squeeze',
    'ap_calculus_l_hopital_s_rule': 'lhopital',
    'ap_calculus_types_of_discontinuity': 'jump',
    'ap_calculus_differentiability_and_continuity': 'corner',
    'ap_calculus_the_derivative_as_a_limit': 'secant',
    'ap_calculus_the_product_rule': 'tangent',
    'ap_calculus_derivatives_of_trigonometric_functions': 'tangent_trig',
    'ap_calculus_concavity_and_inflection_points': 'shape',
    'ap_calculus_the_second_derivative_test': 'shape',
    'ap_calculus_the_fundamental_theorem_of_calculus': 'accumulation',
    'ap_calculus_improper_integrals': 'improper',
    'ap_calculus_the_integral_test': 'improper',
    'ap_calculus_absolute_and_conditional_convergence': 'alternating_sums',
    'ap_calculus_the_ratio_test': 'partial_sums',
    'ap_calculus_geometric_series': 'partial_sums',
    'ap_calculus_comparison_tests': 'comparison_series',
    'ap_calculus_convergence_of_sequences': 'sequence_terms',
    'ap_calculus_the_nth_term_test': 'sequence_terms',
    'ap_calculus_polar_coordinates': 'polar',
    'ap_calculus_straight_line_motion': 'motion',
    'ap_calculus_the_chain_rule': 'related_rates',
    'ap_calculus_implicit_differentiation': 'implicit',
    'ap_calculus_derivatives_of_inverse_functions': 'inverse_pair',
    'algebra_2_inverse_functions': 'inverse_pair',
    'algebra_2_composite_functions': 'composition',
    'algebra_2_even_and_odd_functions': 'symmetry',
    'algebra_2_zeros_and_multiplicity': 'roots',
    'algebra_2_the_fundamental_theorem_of_algebra': 'roots',
    'algebra_2_the_intermediate_value_theorem': 'roots',
    'algebra_2_sine_cosine_and_tangent': 'trig_wave',
    'algebra_2_angles_and_radian_measure': 'trig_wave',
    'algebra_2_complex_conjugates': 'complex_conjugate',
    'algebra_2_complex_numbers_and_their_arithmetic': 'complex_powers',
    'algebra_2_the_counting_principle': 'counting',
    # A second class of the same defect: these matched an authored rule, but the wrong one,
    # because ``_haystack`` includes keywords that mean something else in another topic.
    'algebra_2_ellipses': 'conic',
    'algebra_2_hyperbolas': 'hyperbola',
    'algebra_2_identifying_conic_sections': 'conic',
    'algebra_2_inverse_trigonometric_functions': 'inverse_pair',
    'algebra_2_solving_trigonometric_equations': 'trig_wave',
    'algebra_2_trigonometric_identities': 'trig_wave',
    'algebra_2_the_imaginary_unit_i': 'complex_powers',
    'algebra_2_radical_equations': 'radical',
    'algebra_2_asymptotes_and_holes': 'rational',
    'algebra_2_graphing_rational_functions': 'rational',
    'algebra_2_end_behaviour_of_polynomials': 'polynomial_graph',
    'algebra_2_stretching_and_compressing_graphs': 'transformation',
    'algebra_2_absolute_value_equations_and_inequalities': 'absolute_value',
    'algebra_2_the_unit_circle': 'trig_wave',
    # Changed from 'binomial': the probability rule claimed "permutation*"/"combination*"
    # and drew a sampling distribution for a counting lesson. The concept now has its own
    # template (P(n,r) against C(n,r), differing by r!), which is what it is about.
    'algebra_2_permutations_and_combinations': 'arrangements',
}

#: Concepts for which no single-variable plot is honest. They are the *only* mathematics
#: concepts allowed to reach ``figure_for`` carrying the probe kind, and it is turned into a
#: concept map rather than served.
DELIBERATELY_FIGURELESS = {
    'algebra_2_determinants',
    'algebra_2_inverse_matrices',
    'algebra_2_matrix_multiplication',
    'algebra_2_matrix_notation_and_operations',
    'algebra_2_solving_systems_with_matrices',
}

#: The hand-authored course's figures, which these rules must not change. Each of these
#: was briefly mis-claimed while the overrides above were being written: "Exponential
#: functions and their graphs" carries the keyword "asymptote", "Permutations and
#: combinations" carries "factorial" (which the ``factor*`` stem matched), and
#: "Simplifying radical expressions" carries "simplifying radical".
AUTHORED_FIGURES_THAT_MUST_NOT_MOVE = {
    'exponential_functions_and_their_graphs': 'exponential',
    # Not 'binomial' any more: the binomial distribution is the right figure for a
    # sampling concept and the wrong one for counting. The counting template replaced it.
    'permutations_and_combinations': 'arrangements',
    'simplifying_radical_expressions': 'exponential',
    'prime_factorisation': 'quadratic',
    'fraction_equivalence': 'fraction_bar',
}


def _nodes():
    for spec in MATHEMATICS:
        graph = courses.graph_for(spec.id)
        for node_id, node in graph.nodes.items():
            yield spec, graph, node_id, node


def test_no_mathematics_concept_falls_back_to_the_generic_probe():
    """An *accidental* fallback is the bug; a declared one is handled below."""
    offenders = []
    for spec, _graph, node_id, node in _nodes():
        spec_ = templates.template_for(node.to_dict())
        if any(GENERIC_NOTE in note for note in spec_.notes or []):
            offenders.append((spec.id, node_id, node.title))
    assert not offenders, f'{len(offenders)} concept(s) still fall back to a quadratic: {offenders[:5]}'


def test_only_declared_concepts_are_left_without_a_figure():
    """A concept may only reach ``figure_for`` figure-less on purpose, and is then mapped."""
    figureless = set()
    for spec, _graph, node_id, node in _nodes():
        if templates.template_for(node.to_dict()).kind == figures.GENERIC_PROBE_KIND:
            figureless.add(node_id)
    assert figureless == DELIBERATELY_FIGURELESS, figureless ^ DELIBERATELY_FIGURELESS
    # And for each of them the learner gets a derived concept map, not a curve.
    for node_id in DELIBERATELY_FIGURELESS:
        spec = courses.course(courses.course_for_node(node_id))
        graph = courses.graph_for(spec.id)
        payload = figures.figure_for(graph.nodes[node_id].to_dict(), graph, {}, spec.subject_kind)
        assert payload['kind'] == figures.CONCEPT_MAP, node_id
        assert payload['steps'], node_id


def test_the_authored_course_keeps_its_own_figures():
    """The overrides exist for the new courses; the hand-curated one must not move."""
    graph = courses.graph_for('integrated_math_1')
    for node_id, kind in AUTHORED_FIGURES_THAT_MUST_NOT_MOVE.items():
        assert templates.template_for(graph.nodes[node_id].to_dict()).kind == kind, node_id


def test_a_factorial_is_not_a_factor():
    """The needle bug behind a permutations concept being drawn as a factoring exercise."""
    assert not templates._has('permutations and combinations factorial', 'factor')
    assert not templates._has('permutations and combinations factorial', 'factoring')
    assert templates._has('factoring common factors', 'factoring')
    assert templates._has('prime factorisation', 'factoris*')
    assert templates._has('greatest common factor', 'factor')


def test_no_mathematics_concept_is_served_a_quadratic_figure():
    """``figure_for`` is the last gate: a probe must never reach a learner.

    A concept with no template is allowed a concept map — that is derived from the graph
    and always true — but never the generic probe, which would put a parabola on screen
    under the concept's own name.
    """
    offenders = []
    for spec, graph, node_id, node in _nodes():
        payload = figures.figure_for(node.to_dict(), graph, {}, spec.subject_kind)
        if payload['kind'] == figures.GENERIC_PROBE_KIND:
            offenders.append((spec.id, node_id))
        if payload['figure'] == 'curve' and not payload['series']:
            offenders.append((spec.id, node_id, 'empty curve'))
    assert not offenders, offenders


@pytest.mark.parametrize('node_id,kind', sorted(EXPECTED_KINDS.items()))
def test_each_calculus_family_gets_its_own_figure(node_id: str, kind: str):
    course_id = courses.course_for_node(node_id)
    assert course_id, f'{node_id} belongs to no course'
    node = courses.graph_for(course_id).nodes[node_id]
    assert templates.template_for(node.to_dict()).kind == kind


def test_every_generated_figure_explains_itself_and_reads_out():
    """A figure that cannot say what it shows is a picture, not teaching."""
    for spec, _graph, node_id, node in _nodes():
        payload = simulate.build(templates.template_for(node.to_dict()))
        if payload['figure'] != 'curve':
            continue
        assert payload['steps'], node_id
        assert payload['readouts'], node_id
        # Word-bounded: "discriminant" contains the letters "nan".
        joined = ' '.join(payload['steps'])
        assert not re.search(r'\bnan\b', joined, re.I), node_id
        for readout in payload['readouts']:
            assert not re.search(r'\bnan\b', str(readout.get('value', '')), re.I), (node_id, readout)


def test_every_generated_figure_builds_at_every_parameter_extreme():
    """Sliders must not be able to produce a crash or an empty payload."""
    for spec, _graph, node_id, node in _nodes():
        spec_ = templates.template_for(node.to_dict())
        for parameter in spec_.parameters:
            for value in (parameter.minimum, parameter.maximum, parameter.value):
                payload = simulate.build(spec_, {parameter.id: value})
                assert payload['steps'], (node_id, parameter.id, value)
                if payload['figure'] == 'curve':
                    assert payload['series'], (node_id, parameter.id, value)


def test_a_negative_power_base_is_bracketed_in_both_renderings():
    """``-0.5^n`` is ``-(0.5^n)``; the alternating series is ``(-0.5)^n``.

    Constant folding turns ``(0 - r)^n`` into a power whose base is the literal ``-0.5``.
    Rendering that base without brackets changes the meaning at every even exponent.
    """
    folded = ex.substitute(ex.parse('(0 - r)^n', variables=('n', 'r')), {'r': 0.5})
    assert ex.to_string(folded) == '(-0.5)^n'
    assert ex.to_latex(folded) == '\\left(-0.5\\right)^{n}'
    # At an even exponent the two readings differ in sign, so the brackets matter.
    bracketed = ex.evaluate(ex.parse('(0 - 0.5)^n', variables=('n',)), {'n': 2.0})
    unbracketed = ex.evaluate(ex.parse('0 - 0.5^n', variables=('n',)), {'n': 2.0})
    assert bracketed == pytest.approx(0.25)
    assert unbracketed == pytest.approx(-0.25)


def test_a_series_figure_plots_totals_not_terms():
    """The distinction the series figure exists to teach must hold in its own data."""
    node = courses.graph_for('ap_calculus').nodes['ap_calculus_geometric_series']
    payload = simulate.build(templates.template_for(node.to_dict()), {'r': 0.5})
    totals = [point[1] for point in payload['series']]
    assert totals[0] == pytest.approx(1.0)          # after one term: 1
    assert totals[1] == pytest.approx(1.5)          # after two: 1 + 0.5
    assert totals[-1] == pytest.approx(2.0, abs=1e-4)  # tending to 1/(1 - 0.5)
