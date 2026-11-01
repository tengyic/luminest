"""Tests for the 2PL / CAT module.

The claims under test are the ones a reader would otherwise have to take on trust:

* the response function is a probability that rises with ability and equals 0.5 at
  difficulty;
* information peaks where the item is neither certainly right nor certainly wrong;
* an ability estimate with no evidence is the prior and says so;
* item selection differs by purpose - measurement maximises information, practice targets a
  success rate - and exposure control actually excludes over-exposed items;
* an item with too few responses is *not* given a measured difficulty.
"""

import math

import pytest

from app.harness import psychometrics


# ------------------------------------------------------------------ response function

def test_probability_is_monotonic_in_ability_and_half_at_difficulty():
    values = [psychometrics.probability(theta, 1.0, 0.0) for theta in (-3, -1, 0, 1, 3)]
    assert values == sorted(values)
    assert values[2] == pytest.approx(0.5)
    assert all(0.0 < value < 1.0 for value in values)


def test_discrimination_changes_steepness_not_the_midpoint():
    flat = psychometrics.probability(1.0, 0.5, 0.0)
    steep = psychometrics.probability(1.0, 2.0, 0.0)
    assert flat < steep
    assert psychometrics.probability(0.0, 0.5, 0.0) == pytest.approx(0.5)
    assert psychometrics.probability(0.0, 2.0, 0.0) == pytest.approx(0.5)


def test_a_guessing_floor_raises_the_low_ability_asymptote():
    low = psychometrics.probability(-8.0, 1.0, 0.0, c=0.0)
    floored = psychometrics.probability(-8.0, 1.0, 0.0, c=0.25)
    assert low < 0.01
    assert floored == pytest.approx(0.25, abs=0.01)


def test_extreme_values_do_not_produce_nan():
    for theta in (-1e6, 1e6):
        value = psychometrics.probability(theta, 3.0, 0.0)
        assert not math.isnan(value)
        assert 0.0 <= value <= 1.0


def test_information_peaks_at_the_difficulty():
    at_difficulty = psychometrics.information(0.0, 1.0, 0.0)
    either_side = max(psychometrics.information(-1.0, 1.0, 0.0),
                      psychometrics.information(1.0, 1.0, 0.0))
    assert at_difficulty > either_side
    assert at_difficulty == pytest.approx(0.25)


def test_a_harder_item_carries_its_information_higher_up_the_scale():
    assert psychometrics.information(2.0, 1.0, 2.0) > psychometrics.information(0.0, 1.0, 2.0)


# ------------------------------------------------------------------ ability estimation

def test_no_responses_returns_the_prior_and_says_so():
    posterior = psychometrics.ability_posterior([])
    assert posterior['n'] == 0
    assert posterior['theta'] == pytest.approx(0.0, abs=1e-6)
    assert posterior['se'] == pytest.approx(psychometrics.PRIOR_SD, abs=0.01)
    assert 'prior' in posterior['note']


def test_correct_responses_raise_the_estimate_and_shrink_its_error():
    none = psychometrics.ability_posterior([])
    some = psychometrics.ability_posterior([(1.0, 0.0, True)] * 3)
    more = psychometrics.ability_posterior([(1.0, 0.0, True)] * 10)
    assert some['theta'] > none['theta']
    assert more['theta'] > some['theta']
    assert more['se'] < some['se']


def test_wrong_responses_lower_the_estimate():
    wrong = psychometrics.ability_posterior([(1.0, 0.0, False)] * 8)
    assert wrong['theta'] < 0.0


def test_an_all_correct_run_flags_the_boundary_rather_than_claiming_precision():
    # A hard item answered correctly every time: the estimate runs to the edge of the grid,
    # and the payload has to admit that rather than present a precise-looking number.
    posterior = psychometrics.ability_posterior([(1.5, 2.5, True)] * 40)
    assert posterior['theta'] > 2.5
    assert posterior['at_boundary'] is True


def test_uncalibrated_rows_are_skipped_rather_than_defaulted_to_zero():
    rows = [{'a': 1.0, 'b': 0.0, 'correct': True},
            {'a': 1.0, 'b': None, 'correct': True},
            {'a': 1.0, 'correct': False}]
    payload = psychometrics.estimate_ability(rows)
    assert payload['n'] == 1
    assert payload['skipped_uncalibrated'] == 2


def test_theta_renders_as_a_readable_success_rate():
    assert psychometrics.theta_to_success(0.0) == pytest.approx(0.5)
    assert psychometrics.theta_to_success(2.0) > 0.85


# ------------------------------------------------------------------- item selection

def _bank():
    return [{'id': 'easy', 'a': 1.0, 'b': -1.5},
            {'id': 'middle', 'a': 1.0, 'b': 0.0},
            {'id': 'hard', 'a': 1.0, 'b': 1.5},
            {'id': 'sharp', 'a': 2.0, 'b': 0.0}]


def test_measurement_picks_maximum_information():
    chosen = psychometrics.select_item(_bank(), 0.0, purpose='measure')
    assert chosen['item']['id'] == 'sharp'
    assert chosen['purpose'] == 'measure'
    assert chosen['target'] == psychometrics.MEASUREMENT_TARGET


def test_practice_picks_a_high_success_item_not_the_most_informative_one():
    chosen = psychometrics.select_item(_bank(), 0.0, purpose='practice')
    assert chosen['item']['id'] == 'easy'
    assert chosen['item']['p'] >= 0.8
    assert chosen['item']['p'] == pytest.approx(0.85, abs=0.06)


def test_the_two_purposes_disagree_and_that_is_the_point():
    measure = psychometrics.select_item(_bank(), 0.0, purpose='measure')['item']['id']
    practice = psychometrics.select_item(_bank(), 0.0, purpose='practice')['item']['id']
    assert measure != practice


def test_exposure_control_skips_an_over_exposed_item():
    exposure = {'sharp': {'administered': 40, 'opportunities': 100}}
    chosen = psychometrics.select_item(_bank(), 0.0, purpose='measure', exposure=exposure)
    assert chosen['item']['id'] != 'sharp'


def test_when_every_item_is_over_the_cap_the_least_exposed_is_returned_and_flagged():
    exposure = {item: {'administered': 50, 'opportunities': 100}
                for item in ('easy', 'middle', 'hard', 'sharp')}
    chosen = psychometrics.select_item(_bank(), 0.0, purpose='measure', exposure=exposure)
    assert chosen['item'] is not None
    assert chosen['notes']


def test_excluded_items_are_never_selected():
    chosen = psychometrics.select_item(_bank(), 0.0, purpose='measure',
                                       exclude=['sharp'])
    assert chosen['item']['id'] != 'sharp'


def test_an_uncalibrated_candidate_is_reported_not_assumed():
    bank = _bank() + [{'id': 'unknown', 'a': 1.0}]
    chosen = psychometrics.select_item(bank, 0.0, purpose='measure')
    assert 'unknown' in chosen['skipped_uncalibrated']
    assert chosen['item']['id'] != 'unknown'


def test_an_empty_bank_returns_no_item_rather_than_a_default():
    chosen = psychometrics.select_item([], 0.0)
    assert chosen['item'] is None
    assert 'cold-start' in chosen['reason']


def test_an_unknown_purpose_is_refused():
    with pytest.raises(ValueError):
        psychometrics.select_item(_bank(), 0.0, purpose='fun')


def test_the_selection_says_why_and_reports_an_expected_error():
    chosen = psychometrics.select_item(_bank(), 0.0, purpose='measure')
    assert 'Maximum information' in chosen['reason']
    assert 0.0 < chosen['expected_se_after'] < psychometrics.PRIOR_SD


# --------------------------------------------------------------------- calibration

def test_a_thin_item_is_cold_start_and_its_difficulty_is_the_prior():
    entry = psychometrics.rasch_item(count=3, successes=3)
    assert entry['calibrated'] is False
    assert entry['discrimination_estimated'] is False
    assert 'below' in entry['reason']


def test_a_well_observed_item_is_calibrated_and_its_difficulty_orders_correctly():
    easy = psychometrics.rasch_item(count=100, successes=90)
    hard = psychometrics.rasch_item(count=100, successes=30)
    assert easy['calibrated'] and hard['calibrated']
    assert easy['b'] < hard['b']
    assert easy['b'] < 0.0 < hard['b']


def test_a_fifty_percent_item_sits_at_zero_difficulty():
    entry = psychometrics.rasch_item(count=200, successes=100)
    assert entry['b'] == pytest.approx(0.0, abs=1e-6)


def test_calibration_counts_are_reported_with_their_denominator():
    bank = psychometrics.calibrate_bank([
        {'id': 'a', 'count': 100, 'successes': 70},
        {'id': 'b', 'count': 2, 'successes': 1},
    ])
    assert bank['total'] == 2
    assert bank['calibrated'] == 1
    assert bank['cold_start'] == 1


def test_status_reports_the_model_and_what_it_does_not_do():
    described = psychometrics.describe()
    assert '2PL' in described['model']
    assert any('discrimination' in item for item in described['not_implemented'])
