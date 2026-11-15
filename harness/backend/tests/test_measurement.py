"""Learning-efficiency measurement: the estimator, the aid contract, and the probe budget.

Each test pins a property that a verifier would try to falsify, and several of them exist
because the implementation got that property wrong first:

* the aid label must not be destroyed by segmentation (it was, silently);
* the interval must contain its own point estimate (it did not, because resampling re-paired
  outcomes with opportunity numbers and the fit went flat);
* a saturated learner's estimate must stay finite and unbiased (it must not diverge);
* a probe must not be issued twice in one sitting, or into an assessment.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import learning_science
from app.config import Settings
from app.curriculum import QUESTIONS, course_concepts, course_questions
from app.courses import DEFAULT_COURSE_ID
from app.main import create_app
from app.measurement import bench, contracts, episodes, estimators, probe, report
from app.measurement.models import KINDS, MeasurementProbe

MATH = course_concepts(DEFAULT_COURSE_ID)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def account(client, label='learner'):
    response = client.post('/api/v1/auth/register', json={
        'name': label, 'email': f'{label}@example.test', 'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    value = response.json()
    return {'Authorization': 'Bearer ' + value['token']}, value['user']


def attempts(*, count=20, rate=0.10, concept='frac', start_at=0.0, gap=60.0):
    """""A rising sequence whose correctness is deterministic, so a test can assert a sign."""
    rows = []
    for index in range(1, count + 1):
        threshold = 0.25 + rate * index
        rows.append({'created_at': start_at + index * gap, 'elapsed_seconds': 20.0,
                     'concept_id': concept, 'correct': (index % 10) / 10.0 < threshold,
                     'mode': 'practice', 'question_id': f'{concept}-{index}'})
    return rows


# ------------------------------------------------------------------ the aid contract

def test_aid_precedence_picks_the_strongest_support_present():
    """One tutor turn outranks an open lesson, which outranks a repeated item.

    Returning the strongest aid is what makes ``aid_level == 'none'`` a real claim: it means
    every source was checked and absent, not that the first check found nothing.
    """
    assert contracts.aid_level(tutor_turns=1, lesson_open=True, feedback_before=True,
                               item_seen=True) == 'tutor'
    assert contracts.aid_level(lesson_open=True, feedback_before=True) == 'feedback'
    assert contracts.aid_level(lesson_open=True) == 'lesson'
    assert contracts.aid_level(item_seen=True) == 'repeat'
    assert contracts.aid_level() == 'none'


def test_an_unknown_aid_level_is_never_counted_as_unaided():
    """A typo or a new level must not silently join the unaided bucket."""
    assert contracts.unaided('none') is True
    assert contracts.unaided('Tutor') is False
    assert contracts.unaided('') is False
    assert contracts.unaided('unknown') is False


def test_a_tutor_turn_only_affects_attempts_after_it():
    rows = [{'created_at': 100.0, 'question_id': 'q1', 'mode': 'practice', 'concept_id': 'c'},
            {'created_at': 300.0, 'question_id': 'q2', 'mode': 'practice', 'concept_id': 'c'}]
    labelled = episodes.derive_aid(rows, tutor_timestamps=[200.0])
    assert labelled[0]['aid'] == 'none'
    assert labelled[1]['aid'] == 'tutor'


def test_a_repeat_inside_a_closed_assessment_is_not_feedback_aided():
    """Feedback is withheld until an exam completes, so a repeat there is not feedback."""
    rows = [{'created_at': 100.0, 'question_id': 'q1', 'mode': 'exam', 'concept_id': 'c'},
            {'created_at': 200.0, 'question_id': 'q1', 'mode': 'exam', 'concept_id': 'c'}]
    labelled = episodes.derive_aid(rows)
    assert labelled[0]['aid'] == 'none'
    assert labelled[1]['aid'] == 'repeat'


def test_segmentation_preserves_the_aid_label():
    """Regression: ``as_dict`` once stripped every key it did not name, so the aid label
    vanished during segmentation and the per-episode unaided counts were computed on
    unlabelled rows while the global counts were not."""
    labelled = episodes.derive_aid(attempts(count=6), tutor_timestamps=[130.0])
    segments = episodes.aid_by_episode(episodes.segment(labelled))
    assert len(segments) == 1
    assert {'aid' for row in segments[0]['attempts']} - {None}
    assert segments[0]['unaided_answered'] < len(segments[0]['attempts'])


# --------------------------------------------------------------------- engagement time

def test_a_long_pause_starts_a_new_episode_and_idle_time_is_not_engaged():
    rows = [{'created_at': float(t), 'elapsed_seconds': 30.0, 'concept_id': 'c',
             'correct': True, 'mode': 'practice', 'question_id': f'q{t}'}
            for t in (0, 60, 120, 5000, 5060)]
    segments = episodes.segment(rows)
    assert len(segments) == 2
    assert segments[0]['wall_seconds'] > 0
    # A gap of 4880s is a break, not thinking, and must not inflate engaged time.
    assert segments[1]['engaged_seconds'] < 200
    assert segments[1]['idle_seconds'] == 0


def test_engaged_time_caps_a_single_gap_but_keeps_a_short_one():
    short = episodes.segment([{'created_at': 0.0, 'elapsed_seconds': 10.0, 'concept_id': 'c',
                               'correct': True, 'mode': 'practice', 'question_id': 'a'},
                              {'created_at': 100.0, 'elapsed_seconds': 10.0, 'concept_id': 'c',
                               'correct': True, 'mode': 'practice', 'question_id': 'b'}])[0]
    # 10s solve + 10s solve + 100s (uncapped) between = 120s.
    assert short['engaged_seconds'] == 120.0


# --------------------------------------------------------------------- learning rate

def test_the_learning_rate_is_positive_for_a_rising_learner():
    sequences = episodes.learning_opportunities(attempts(count=40, rate=0.12))
    fit = estimators.fit_learning_rate(sequences, draws=0)
    assert fit['status'] == 'measured'
    assert fit['learning_rate'] > 0
    assert fit['improving'] is True


def test_the_interval_contains_its_own_point_estimate():
    """Regression: the percentile interval was displaced below the estimate because resampling
    re-paired outcomes with opportunity numbers, fitting noise. A bootstrap interval that
    excludes its own point estimate is not an interval."""
    sequences = episodes.learning_opportunities(attempts(count=40, rate=0.12))
    fit = estimators.fit_learning_rate(sequences, draws=120, seed=3)
    interval = fit['interval_90']
    assert interval is not None
    assert interval['method'] == 'pivotal'
    assert interval['low'] <= fit['learning_rate'] <= interval['high']


def test_a_learner_every_answer_right_does_not_produce_an_infinite_slope():
    """Separation guard: maximum likelihood diverges here, and a diverged slope would be
    reported as an extraordinary learning rate."""
    rows = [{'created_at': float(i), 'concept_id': 'c', 'correct': True,
             'question_id': f'q{i}', 'mode': 'practice'} for i in range(1, 31)]
    fit = estimators.fit_concept_curve(rows)
    assert fit['status'] == 'measured'
    assert abs(fit['slope']) < 5
    # Nothing improved - the learner started at ceiling - so there is no half-life.
    assert fit['half_life_opportunities'] is None


def test_a_flat_curve_reports_no_half_life():
    rows = [{'concept_id': 'c', 'correct': index % 2 == 0, 'question_id': f'q{index}'}
            for index in range(1, 25)]
    fit = estimators.fit_concept_curve(rows)
    assert fit['half_life_opportunities'] is None


def test_below_the_minimum_opportunities_the_rate_is_declared_unidentified():
    sequences = episodes.learning_opportunities(attempts(count=5))
    fit = estimators.fit_learning_rate(sequences, draws=0)
    assert fit['status'] == 'insufficient_evidence'
    assert fit['learning_rate'] is None
    assert fit['shortfall'] == contracts.MIN_OPPORTUNITIES - 5


# ------------------------------------------------------------------------- magnitudes

def test_normalized_gain_matches_hakes_definition():
    assert estimators.normalized_gain(0.4, 0.7)['gain'] == pytest.approx(0.5, abs=1e-6)


def test_normalized_gain_refuses_a_ceiling_pretest():
    """A learner already at 100% has no headroom; <g> is undefined, not 1.0."""
    reading = estimators.normalized_gain(1.0, 1.0)
    assert reading['status'] == 'ceiling'
    assert reading['gain'] is None


def test_time_to_criterion_needs_the_criterion_to_be_sustained():
    """A trailing window, so a streak that collapses is not a criterion.

    Three right then five wrong reaches 100% on a *cumulative* count at answer three, so a
    running-total rule would declare the criterion met and never retract it. The trailing
    window is what refuses that: no four consecutive answers ever reach the threshold.
    """
    collapsed = [{'correct': True}] * 3 + [{'correct': False}] * 5
    assert estimators.time_to_criterion(
        collapsed, threshold=0.8, window=4)['status'] == 'not_reached'
    sustained = [{'correct': False}] * 2 + [{'correct': True}] * 8
    reading = estimators.time_to_criterion(sustained, threshold=0.8, window=4)
    assert reading['opportunities_to_criterion'] == 6
    assert reading['sustained_accuracy'] == 1.0


def test_the_aided_unaided_gap_is_withheld_until_enough_unaided_evidence():
    """The most consequential number in the report must not be guessed from two answers."""
    reading = estimators.aided_unaided_gap({'n': 40, 'accuracy': 0.8}, {'n': 2, 'accuracy': 0.5})
    assert reading['gap'] is None
    assert reading['status'] == 'insufficient_evidence'
    measured = estimators.aided_unaided_gap({'n': 40, 'accuracy': 0.8}, {'n': 20, 'accuracy': 0.45})
    assert measured['gap'] == pytest.approx(0.35, abs=1e-6)
    assert measured['significant_at_95'] is True


# ---------------------------------------------------------------------------- probe

def test_a_cold_probe_is_not_issued_twice_in_one_sitting():
    decision = probe.cold_probe_decision(minutes_since_last=600, probes_this_episode=1,
                                         practice_by_concept={'frac': 10})
    assert decision['due'] is False
    assert decision['reason'] == 'already_probed_this_episode'


def test_a_cold_probe_respects_its_cooldown():
    decision = probe.cold_probe_decision(minutes_since_last=4, probes_this_episode=0,
                                         practice_by_concept={'frac': 10})
    assert decision['due'] is False
    assert decision['reason'] == 'cooldown'
    assert decision['remaining_minutes'] > 0


def test_a_probe_will_not_cut_across_an_assessment():
    decision = probe.cold_probe_decision(minutes_since_last=None, probes_this_episode=0,
                                         practice_by_concept={'frac': 10}, blocked=True)
    assert decision['due'] is False
    assert decision['reason'] == 'blocked'


def test_a_concept_with_too_little_practice_is_not_probed():
    """Before a few attempts, a low probe score is first exposure, not weak retention."""
    decision = probe.cold_probe_decision(minutes_since_last=None, probes_this_episode=0,
                                         practice_by_concept={'frac': 2})
    assert decision['due'] is False
    assert decision['reason'] == 'no_eligible_concept'


def test_the_probe_kinds_are_the_same_in_the_table_and_the_policy():
    assert set(KINDS) == set(probe.PROBE_SPECS)


def test_the_transfer_delays_agree_with_the_teaching_core():
    assert tuple(learning_science.TRANSFER_DELAYS) == report.TRANSFER_DELAYS


# --------------------------------------------------------------------------- report

def test_an_account_with_no_history_gets_a_report_that_says_so():
    reading = report.build([])
    assert reading['evidence']['attempts'] == 0
    assert reading['efficiency']['learning_rate']['status'] == 'insufficient_evidence'
    claims = [item['claim'] for item in reading['cannot_claim']]
    assert 'that your error rate is falling' in claims
    assert 'that you will still know this in a week' in claims


def test_the_unaided_bucket_excludes_attempts_made_with_the_tutor_open():
    rows = attempts(count=20, rate=0.1)
    reading = report.build(rows, tutor_timestamps=[rows[10]['created_at']])
    mix = reading['support']['mix']['by_level']
    assert mix['tutor'] > 0
    assert mix['none'] > 0
    assert reading['evidence']['aid']['unaided'] == mix['none']


# ---------------------------------------------------------------------------- the API
#
# Grouped deliberately: constructing the app costs several seconds, and one client covering
# the whole surface is a few assertions that belong together anyway. Separate clients per
# assertion quadrupled the suite's runtime without testing anything extra.


def test_the_measurement_surface_describes_itself_and_reports_for_a_new_account(client):
    assert client.get('/api/v1/measurement/report').status_code in (401, 403)
    assert client.get('/api/v1/measurement').status_code in (401, 403)

    headers, _user = account(client, 'measure-surface')
    schema = client.get('/api/v1/measurement', headers=headers)
    assert schema.status_code == 200, schema.text
    body = schema.json()
    assert body['cooldown_minutes'] == probe.PROBE_COOLDOWN_MINUTES
    assert set(body['probes']) == set(probe.PROBE_SPECS)

    reading = client.get('/api/v1/measurement/report', headers=headers)
    assert reading.status_code == 200, reading.text
    payload = reading.json()
    assert payload['evidence']['attempts'] == 0
    assert payload['cannot_claim']


def test_a_probe_needs_practice_and_an_effort_rating_stays_on_its_scale(client):
    headers, _user = account(client, 'measure-lifecycle')
    # No practice history: nothing to measure, and the refusal says so rather than erroring.
    refused = client.post('/api/v1/measurement/probe', headers=headers)
    assert refused.status_code == 200, refused.text
    assert refused.json()['issued'] is False
    assert refused.json()['reason'] == 'no_eligible_concept'

    for off_scale in (0, 10):
        assert client.post('/api/v1/measurement/effort', headers=headers,
                           json={'value': off_scale}).status_code == 422
    ok = client.post('/api/v1/measurement/effort', headers=headers, json={'value': 7})
    assert ok.status_code == 200, ok.text
    assert ok.json()['value'] == 7


def test_the_benchmark_is_an_operator_surface_not_a_learner_one(client):
    headers, _user = account(client, 'measure-bench')
    assert client.get('/api/v1/measurement/bench', headers=headers).status_code == 403


# ------------------------------------------------------------------------- the benchmark

def test_the_estimator_benchmark_passes_its_own_checks():
    """Deterministic: the suite is seeded, so this is a regression gate on the criteria."""
    suite = bench.run_suite(learners=80)
    failing = [check['check'] for check in suite['checks'] if not check['passes']]
    assert suite['ok'] is True, f'failing checks: {failing}'
    assert suite['validates'] == 'estimator'
    assert len(suite['checks']) == 5
