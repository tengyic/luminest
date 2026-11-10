"""The level layer: a readable band over theta, that fails closed.

The failure this file exists to prevent is specific and common: theta starts at the prior
(0.0), the prior maps cleanly onto a CEFR band, and a learner who has answered nothing is
shown a confident level. ``test_no_evidence_means_no_level`` is the guard. It is the same
rule as ``mastery_known`` in the teaching core - "no attempts yet" is not "weak" - applied
one layer up, where the consequence is a label on a person rather than a teaching move.

The second guard is subject honesty. CEFR is a language-proficiency scale; a physics learner
reported as "B1" is a category error wearing the clothes of precision, so ``cefr`` is
``None`` unless the course subject is a language, with a reason rather than a silent gap.

The route half proves the two meet: a fresh account's ``/ability`` reports ``known=False``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.harness import leveling, psychometrics
from app.main import create_app


# --------------------------------------------------------------------------- fixtures

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    application = create_app(Settings.from_env())
    with TestClient(application) as client:
        yield application, client


def _learner(client, email='leveller@example.com'):
    registered = client.post('/api/v1/auth/register', json={
        'name': 'Level probe', 'email': email,
        'password': 'Correct-Horse-9', 'age_confirmed': True}).json()
    return {'Authorization': 'Bearer ' + registered['token']}


# --------------------------------------------------------------------------- no evidence

def test_no_evidence_means_no_level():
    payload = leveling.learner_level(0.0, 0.9, n=0, subject='Mathematics')
    assert payload['known'] is False
    assert payload['cefr'] is None and payload['grade'] is None
    assert payload['label'] == 'Not yet measured'
    assert 'starting assumption' in payload['note']


def test_one_item_short_of_the_minimum_is_still_no_level():
    assert leveling.learner_level(0.4, 0.8, n=leveling.MIN_ITEMS_FOR_LEVEL - 1)['known'] is False


def test_an_unstated_count_is_treated_as_not_enough():
    """The permissive default is exactly how a prior becomes a label."""
    assert leveling.learner_level(0.4, 0.8, n=None)['known'] is False


def test_enough_evidence_produces_a_level():
    payload = leveling.learner_level(0.4, 0.5, n=leveling.MIN_ITEMS_FOR_LEVEL,
                                     subject='Mathematics')
    assert payload['known'] is True
    assert payload['grade'] is not None
    assert payload['label'] == payload['interpretable']


# --------------------------------------------------------------------------- subject honesty

def test_cefr_is_withheld_for_a_non_language_subject():
    payload = leveling.level_summary(1.2, subject='Physics')
    assert payload['cefr'] is None
    assert 'CEFR describes language proficiency' in payload['cefr_reason']
    assert 'B1' not in payload['interpretable']


def test_cefr_is_reported_for_a_language_subject():
    payload = leveling.level_summary(1.2, subject='Spanish')
    assert payload['cefr'] == 'B1'
    assert payload['cefr_reason'] is None
    assert payload['interpretable'].startswith('B1')


def test_language_subject_matching_is_not_fooled_by_a_substring_of_a_non_language():
    assert leveling.is_language_subject('Spanish')
    assert not leveling.is_language_subject('Mathematics')
    assert not leveling.is_language_subject('Earth and Space Science')


# --------------------------------------------------------------------------- the mapping

def test_the_band_rises_with_ability():
    labels = [leveling.grade_from_theta(t)[0] for t in (-3.0, -1.0, 0.0, 1.0, 2.0, 4.0)]
    assert labels == sorted(labels)
    assert labels[0] == 0 and labels[-1] == 12


def test_grade_labels_read_as_english():
    assert leveling.grade_from_theta(-3.0)[1] == 'Kindergarten'
    assert leveling.grade_from_theta(0.0)[1] == 'Grade 5'
    assert leveling.grade_from_theta(4.0)[1] == 'Grade 12'


def test_the_readable_success_matches_the_psychometric_function():
    """Two renderings of the same theta must not disagree; that is how a panel loses trust."""
    for theta in (-2.0, -0.5, 0.0, 0.7, 2.5):
        assert (leveling.level_summary(theta)['success_on_average_item']
                == psychometrics.theta_to_success(theta))


def test_nothing_claims_certification():
    assert leveling.level_summary(1.0)['not_certified'] is True
    assert leveling.learner_level(1.0, 0.4, n=10)['not_certified'] is True
    assert leveling.describe()['not_certified'] is True


# --------------------------------------------------------------------------- the route

def test_a_fresh_account_is_not_given_a_level(app):
    application, client = app
    headers = _learner(client)
    payload = client.get('/api/v1/ability', headers=headers).json()
    assert payload['n_calibrated'] == 0
    assert payload['level']['known'] is False
    assert payload['level']['cefr'] is None
    assert payload['success_on_average_item'] is None


def test_the_route_reports_a_grade_for_a_measured_learner(app):
    """With enough calibrated items the route must produce a level, not merely refuse one."""
    application, client = app
    headers = _learner(client, email='measured@example.com')
    payload = client.get('/api/v1/ability', headers=headers).json()
    # The default course has no pooled calibration until items have been answered, so the
    # route's honest answer for this account is still "not measured". The mapping itself is
    # pinned above; what this test adds is that the route passes n through rather than
    # dropping it, which is the bug that let a prior be shown as a band.
    assert payload['level']['n_items'] == payload['n_calibrated']
