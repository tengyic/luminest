"""The deterministic economics figures.

Every assertion here is about arithmetic, not appearance, and that is the point: a
diagram whose curve sits in the wrong place teaches the wrong economics to a learner who
has no way to tell. The tax wedge is the clearest case - if the buyer and seller prices
came out the same the picture would still *look* like a textbook figure while asserting
that tax has no incidence. So the numbers the caption states are checked against the
algebra they claim to come from.

The classification tests defend the other half: a figure that is not about the concept is
worse than no figure, so the specific shapes must win over the generic ones.
"""

from __future__ import annotations

import re

import pytest

from app.harness import econ_figures


def _payload(kind: str) -> dict:
    return econ_figures.render(kind, title=kind)


def test_every_rule_names_a_template_that_exists():
    """A rule pointing at a missing template would be a silent ``ValueError`` at lesson
    build time, on a concept that used to work."""
    kinds = {kind for _, kind in econ_figures.RULES}
    for kind in sorted(kinds):
        payload = econ_figures.render(kind)
        assert payload['figure'] == 'economics'
        assert payload['svg'].startswith('<svg')
        assert payload['caption'].strip()


def test_no_template_emits_a_broken_coordinate():
    """``nan`` in an SVG attribute renders as nothing at all - a curve that silently
    disappears instead of failing."""
    for kind in sorted({kind for _, kind in econ_figures.RULES}):
        svg = _payload(kind)['svg']
        assert 'nan' not in svg.lower()
        # Colours are stripped first: ``#e5e7eb`` contains digits and an ``e``, so a
        # numeric scan over the raw markup reads a gridline colour as a coordinate.
        body = re.sub(r'#[0-9a-fA-F]{3,8}', '', svg)
        for value in re.findall(r'-?\d+\.?\d*(?:e-?\d+)?', body):
            assert abs(float(value)) < 10000, f'{kind}: coordinate {value} off canvas'


def test_a_tax_wedge_splits_the_burden_by_elasticity():
    payload = _payload('tax_wedge')
    p = payload['parameters']
    assert p['buyer_price'] == pytest.approx(7.0)
    assert p['seller_price'] == pytest.approx(5.0)
    assert p['buyer_price'] - p['seller_price'] == pytest.approx(2.0)
    assert p['buyer_share'] + p['seller_share'] == pytest.approx(1.0)
    assert p['quantity'] == pytest.approx(3.0)


def test_a_subsidy_is_the_tax_wedge_mirrored():
    """Same size, opposite direction: buyers pay less, sellers keep more, output rises."""
    p = _payload('subsidy')['parameters']
    assert p['buyer_price'] == pytest.approx(5.0)
    assert p['seller_price'] == pytest.approx(7.0)
    assert p['seller_price'] - p['buyer_price'] == pytest.approx(p['subsidy'])
    assert p['quantity_after'] > p['quantity_before']
    assert p['government_cost'] == pytest.approx(p['subsidy'] * p['quantity_after'])
    assert p['deadweight_loss'] == pytest.approx(
        0.5 * p['subsidy'] * (p['quantity_after'] - p['quantity_before']))


def test_the_isoquant_is_tangent_to_the_isocost():
    """Tangency is the whole claim. Checked at the point the caption states, from both
    sides: the bundle must lie on the isoquant, and the two slopes must be equal."""
    p = _payload('isoquant')['parameters']
    inputs = p['cost_minimising_inputs']
    capital, labour = inputs['capital'], inputs['labour']
    assert capital * labour == pytest.approx(p['output'])
    slope = float(p['slope_at_tangency'])
    intercept = float(p['isocost'].split('=')[1].split('-')[0])
    ratio = float(p['input_price_ratio'])
    assert intercept - ratio * capital == pytest.approx(labour)
    assert -p['output'] / capital ** 2 == pytest.approx(slope)


def test_a_price_maker_sets_marginal_revenue_equal_to_marginal_cost():
    p = _payload('firm_market')['parameters']
    quantity = p['quantity']
    assert p['marginal_revenue_at_quantity'] == pytest.approx(2.0 + 0.9 * quantity,
                                                            abs=2e-3)
    assert p['price'] == pytest.approx(10.0 - quantity, abs=2e-3), (
        'price is read off demand')
    assert p['price'] > p['marginal_revenue_at_quantity'], (
        'a firm with market power prices above marginal revenue')


def test_a_price_taker_has_no_markup():
    p = _payload('firm_competitive')['parameters']
    assert p['marginal_revenue_at_quantity'] == pytest.approx(p['price'])
    assert p['price'] == pytest.approx(2.0 + 0.9 * p['quantity'], abs=2e-3)


def test_marginal_utility_buys_while_the_next_unit_is_worth_its_price():
    p = _payload('marginal_utility')['parameters']
    utilities, price = p['marginal_utility'], p['price']
    assert p['quantity_bought'] == sum(1 for value in utilities if value >= price)
    assert p['total_utility'] == pytest.approx(sum(utilities[:p['quantity_bought']]))
    assert p['consumer_surplus'] == pytest.approx(
        sum(value - price for value in utilities[:p['quantity_bought']] if value > price))


def test_the_lorenz_curve_ends_at_perfect_equality_and_bends_below_it():
    p = _payload('lorenz')['parameters']
    bend = float(p['lorenz_curve'].split('^')[1])
    assert p['gini'] == pytest.approx(1 - 2 / (bend + 1), abs=2e-3)
    assert p['income_share_of_poorest_half'] == pytest.approx(0.5 ** bend, abs=2e-3)
    assert 0 < p['gini'] < 1, 'a curve that is the diagonal is not an illustration of anything'
    assert p['income_share_of_poorest_half'] < 0.5, (
        'the lowest half cannot hold its population share unless incomes are equal')


def test_average_product_peaks_where_it_crosses_marginal_product():
    p = _payload('production_function')['parameters']
    marginal = p['marginal_product']
    average = []
    running = 0.0
    for index, step in enumerate(marginal, 1):
        running += step
        average.append(running / index)
    peak = p['average_product_peak']
    assert peak['worker'] == average.index(max(average)) + 1
    assert peak['value'] == pytest.approx(max(average), abs=2e-3)
    assert marginal[0] < marginal[1], (
        'the figure claims marginal product first rises and then falls')
    assert marginal[-1] < max(marginal), 'and falls, which is what diminishing returns means'


def test_economic_profit_charges_for_the_owners_own_inputs():
    p = _payload('profit_bars')['parameters']
    assert p['accounting_profit'] == pytest.approx(p['revenue'] - p['explicit_cost'])
    assert p['economic_profit'] == pytest.approx(p['accounting_profit'] - p['implicit_cost'])
    assert p['economic_profit'] < p['accounting_profit']


def test_present_value_discounts_each_receipt_by_its_own_year():
    p = _payload('discount_bars')['parameters']
    rate = p['discount_rate']
    for year, (amount, value) in enumerate(zip(p['receipts'], p['present_values']), 1):
        assert value == pytest.approx(amount / (1 + rate) ** year, abs=1e-3)
    assert p['present_value_total'] < p['nominal_total']


def test_the_payoff_matrix_marks_a_mutual_best_response():
    """A Nash equilibrium is not "the worst cell" - it is the one neither player can leave
    alone. Checked by moving each player in turn, not by trusting the label."""
    p = _payload('payoff_matrix')['parameters']
    payoffs = {(0, 0): (8, 8), (0, 1): (2, 10), (1, 0): (10, 2), (1, 1): (4, 4)}
    for cell in payoffs:
        row, column = cell
        row_alternative = [payoffs[(other, column)][0] for other in (0, 1)]
        column_alternative = [payoffs[(row, other)][1] for other in (0, 1)]
        stable = (payoffs[cell][0] == max(row_alternative)
                  and payoffs[cell][1] == max(column_alternative))
        assert stable == (cell == (1, 1)), f'{cell} should not be a mutual best response'
    assert p['cooperate_payoff'] == payoffs[(0, 0)]
    assert p['undercut_gain'] == payoffs[(1, 0)][0] - payoffs[(0, 0)][0]


def test_a_public_good_is_under_provided_because_private_demand_is_too_low():
    p = _payload('public_good')['parameters']
    assert p['optimal_quantity'] > p['market_quantity']
    assert p['deadweight_loss'] > 0
    assert 2.0 + p['optimal_quantity'] == pytest.approx(
        10.0 - 0.5 * p['optimal_quantity'], abs=2e-3), (
        'the optimum is where marginal social benefit meets marginal cost')
    assert 2.0 + p['market_quantity'] == pytest.approx(
        10.0 - p['market_quantity'], abs=2e-3), (
        'the market outcome is where private demand meets marginal cost')


@pytest.mark.parametrize(('title', 'expected'), [
    # Specific shapes must beat the generic rule that shares their vocabulary.
    ('Price ceilings and floors', 'price_ceiling'),
    ('Taxes and tax incidence', 'tax_wedge'),
    ('Common resources and the tragedy of the commons', 'externality'),
    ('Public goods and the free-rider problem', 'public_good'),
    ('Budget constraints and trade-offs', 'ppf'),
    ('Least-cost combination of inputs', 'isoquant'),
    ('Short-run production and diminishing returns', 'production_function'),
    ('Perfect competition: characteristics', 'firm_competitive'),
    ('Monopoly profit maximisation', 'firm_market'),
    ('Collusion and cartels', 'payoff_matrix'),
    ('Income inequality and redistribution', 'lorenz'),
    ('Subsidies', 'subsidy'),
    ('Accounting profit versus economic profit', 'profit_bars'),
    ('Marginal revenue product', 'labour_market'),
])
def test_the_specific_shape_wins_over_the_generic_one(title, expected):
    assert econ_figures.classify('', title, '') == expected


def test_a_concept_with_nothing_to_draw_gets_no_figure():
    """``None`` is the honest answer for a definition, and the fallback must not quietly
    become "draw a market anyway"."""
    assert econ_figures.for_concept('', 'Epistemology of the firm', '') is None


def test_the_caption_states_the_parameters_the_figure_was_drawn_with():
    """A learner who checks the diagram has to be able to see the numbers behind it."""
    caption = econ_figures.caption_with_parameters(_payload('tax_wedge'))
    assert 'Drawn with' in caption
    assert 'tax = 2.0' in caption
    assert 'buyer_price = 7.0' in caption


def test_a_template_with_no_axes_still_renders_a_full_canvas():
    """The payoff matrix is a table, so it draws no axes - but it must still cover the
    canvas rather than leaving the lesson with a blank rectangle."""
    svg = _payload('payoff_matrix')['svg']
    assert 'viewBox' in svg
    assert svg.count('<rect') >= 4, 'four cells'
    assert 'Nash equilibrium' in svg


def test_the_paper_is_painted_before_the_title_it_sits_behind():
    """Paint order is a fact about the file, not a matter of taste.

    The background rect used to be emitted by ``_axes``, i.e. *after* the title text, and an
    opaque white plate drawn over a title hides it completely: 57 lessons shipped with a
    figure whose title nobody could read, and nothing failed. This pins the order for every
    template, including the one with no axes and therefore no rect from ``_axes``.
    """
    for kind in sorted({kind for _, kind in econ_figures.RULES} | {'payoff_matrix'}):
        svg = econ_figures.render(kind, title='A title a learner should see')['svg']
        paper = svg.find(f'fill="{econ_figures.PAPER}"')
        # The svg element's own aria-label carries the title too, and it sits before
        # everything; the element this test is about is the visible <text>.
        title = svg.find('>A title a learner should see</text>')
        assert paper != -1, kind
        assert title != -1, kind
        assert paper < title, f'{kind}: the paper is painted over its own title'
        axes = svg.find('<line')
        if axes != -1:
            assert title < axes, f'{kind}: the title is painted over by the plot'


def test_adverse_selection_draws_a_missing_market_rather_than_a_cheap_one():
    """The lemons figure has to show the good half of the market *not clearing*.

    A generic supply-and-demand picture would show a low clearing price, which is the
    opposite claim: the concept is that the good units withdraw, so there is no price at
    which they trade. The template's own numbers are the check - the average-value curve
    must stay below what good owners require across the whole frame, and the only trade in
    the picture must be the lemons.
    """
    payload = econ_figures.render('adverse_selection', title='Adverse selection')
    parameters = payload['parameters']
    assert parameters['good_units_require'] == 7.0
    assert parameters['lemons_require'] == 3.0
    # At the widest point the gap is exactly one: buyers can pay 6 for the average unit,
    # the owners of a good one will not sell below 7.
    assert parameters['gap_at_zero_quantity'] == 1.0
    # P = 6 - 0.5Q meets 3 at Q = 6, and reaches 7 at no positive quantity.
    assert parameters['lemons_traded'] == 6.0
    assert econ_figures._average_value(0.0) < parameters['good_units_require']
    assert econ_figures._average_value(10.0) < parameters['good_units_require']
    assert 'missing rather than cheap' in payload['caption']
    assert 'good units need 7' in payload['svg']
    assert 'only lemons trade' in payload['svg']


def test_a_concept_with_no_honest_shape_gets_no_figure():
    """The word "market" is not a shape.

    The catch-all rule used to include it, so a lesson on asymmetric information was handed
    a clearing supply-and-demand picture - a figure that asserts the opposite of the concept
    it sits under. The catch-all now needs an actual market phrase, and a bare mention of a
    market is answered with nothing, which the review copy says out loud.
    """
    assert econ_figures.classify('x_market_failure', 'Market failure',
                                 'When a market does not allocate efficiently.') == ''
    assert econ_figures.classify(
        'x_supply_demand', 'Supply and demand',
        'Price settles where the curves cross.') == 'supply_demand'


def test_the_pack_id_decides_the_figure_before_any_paraphrase_does():
    """A published summary must not be able to change which diagram a concept carries.

    Measured on a real rebuild: the overlay's own summary replaced the pack's, the word the
    classification needed disappeared, and two finished lessons silently lost their figures.
    The id and the pack text are the stable identity, so the attribution holds whichever
    prose is attached.
    """
    pack_summary = ('When one side knows more, adverse selection and moral hazard can drive '
                    'good participants out of the market.')
    flat_paraphrase = ('Asymmetric information occurs when one party has more knowledge than '
                       'another, leading to adverse selection and moral hazard.')
    for summary in (pack_summary, flat_paraphrase):
        assert econ_figures.classify('ap_microeconomics_asymmetric_information',
                                     'Asymmetric information', summary) == 'adverse_selection'
