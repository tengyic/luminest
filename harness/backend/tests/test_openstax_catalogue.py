"""The complete OpenStax catalogue as the textbook source.

The 2026-11-10 audit replaced the two-book hand audit with the publisher's *entire*
catalogue, snapshotted from OpenStax's own CMS API. These tests pin the fail-close
shape of that expansion: every catalogue book is audited with the position its own
publisher data supports, CC BY books are text-eligible subject to per-fetch live
re-verification, NC books stay link-only, no-licence books are refused with zero
network requests, and no book is ever registered twice or under two rights positions.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.ingest import policy
from app.ingest.policy import (IngestionRefused, LicenceClass, OPENSTAX_BOOK_POLICIES,
                               OPENSTAX_UNLICENSED, TEXTBOOK_SOURCES, assert_ingestible,
                               registry)
from app.ingest.sources import openstax

CATALOGUE_FILE = Path(policy.__file__).parent / 'sources' / 'openstax_catalogue.json'
SNAPSHOT = json.loads(CATALOGUE_FILE.read_text(encoding='utf-8'))

#: Counts pinned to the 2026-11-10 snapshot. If the publisher's catalogue changes,
#: ``scripts/refresh_openstax_catalogue.py`` regenerates the data file and these numbers
#: are re-pinned with it -- they exist to catch a classifier regression, not to freeze
#: the publisher's catalogue in time.
EXPECTED_TOTAL = 129
EXPECTED_CC_BY = 38
EXPECTED_NC = 80
EXPECTED_UNLICENSED = 11


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(data_dir=str(tmp_path))


def never_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f'no network request may be made here, but {request.url} was asked')


# ------------------------------------------------------------- catalogue completeness

def test_the_catalogue_snapshot_is_intact():
    assert SNAPSHOT['schema'] == 'openstax_catalogue/1'
    assert SNAPSHOT['total_count'] == len(SNAPSHOT['books']) == EXPECTED_TOTAL
    slugs = [book['slug'] for book in SNAPSHOT['books']]
    assert len(set(slugs)) == EXPECTED_TOTAL, 'duplicate slugs in the snapshot'


def test_every_catalogue_book_has_an_audited_policy():
    for book in SNAPSHOT['books']:
        assert book['slug'] in OPENSTAX_BOOK_POLICIES, book['slug']
    assert len(OPENSTAX_BOOK_POLICIES) == EXPECTED_TOTAL


def test_rights_counts_match_the_publisher_snapshot():
    posture = policy.openstax_catalogue_posture()
    assert posture['text_eligible'] == EXPECTED_CC_BY
    assert posture['noncommercial_link_only'] == EXPECTED_NC
    assert posture['unlicensed_refused'] == EXPECTED_UNLICENSED
    assert posture['books_audited'] == EXPECTED_TOTAL


def test_no_policy_appears_twice_in_the_registry():
    names = [entry['name'] for entry in registry()]
    assert len(names) == len(set(names)), \
        f'duplicate policy names: {sorted(n for n in names if names.count(n) > 1)}'


def test_generated_text_eligible_books_are_in_textbook_sources():
    generated = {slug for slug, entry in OPENSTAX_BOOK_POLICIES.items()
                 if entry.ingestible and slug not in
                 {'algebra-and-trigonometry'}}  # the hand-audited exemplar
    named = {entry.name for entry in TEXTBOOK_SOURCES}
    assert len(TEXTBOOK_SOURCES) == EXPECTED_CC_BY
    for slug in generated:
        assert OPENSTAX_BOOK_POLICIES[slug].name in named


# ------------------------------------------------------------------- per-book rights

def test_a_generated_cc_by_book_is_text_eligible():
    policy_entry = OPENSTAX_BOOK_POLICIES['statistics']
    assert policy_entry.licence_class is LicenceClass.CC_BY
    assert policy_entry.ingestible
    assert policy_entry.evidence_id == 'openstax_full_catalogue_2026_11_10'
    assert_ingestible(policy_entry)  # does not raise


def test_generated_cc_by_book_passes_the_live_gate_on_matching_meta():
    meta = {'slug': 'statistics', 'license_name': 'Creative Commons Attribution License',
            'license_version': '4.0',
            'license_url': 'https://creativecommons.org/licenses/by/4.0/'}
    live = openstax.book_policy(meta, book_slug='statistics')
    assert live.licence_class is LicenceClass.CC_BY
    assert_ingestible(live)


def test_a_generated_cc_by_book_refuses_licence_drift():
    """Drift protection is not special to the hand-audited exemplar: every text-eligible
    book re-verifies against the publisher at fetch time."""
    meta = {'slug': 'statistics',
            'license_name': 'Creative Commons Attribution-NonCommercial-ShareAlike License',
            'license_version': '4.0'}
    with pytest.raises(IngestionRefused, match='no longer agree'):
        openstax.book_policy(meta, book_slug='statistics')


def test_an_nc_book_is_audited_link_only_and_refused(settings):
    nc_slugs = [slug for slug, entry in OPENSTAX_BOOK_POLICIES.items()
                if entry.licence_class is LicenceClass.CC_BY_NC_SA]
    assert nc_slugs, 'the catalogue should contain publisher-reported NC books'
    for slug in nc_slugs:
        entry = OPENSTAX_BOOK_POLICIES[slug]
        assert not entry.ingestible, slug
        assert entry.commercial_ok is False, slug
        with pytest.raises(IngestionRefused, match='link-only'):
            assert_ingestible(entry)
        meta = {'slug': slug, 'license_name': 'Creative Commons Attribution-NonCommercial-ShareAlike License',
                'license_version': '4.0'}
        live = openstax.book_policy(meta, book_slug=slug)
        assert live.licence_class is LicenceClass.CC_BY_NC_SA


def test_unlicensed_books_are_refused_with_zero_network_requests(settings):
    assert len(OPENSTAX_UNLICENSED) == EXPECTED_UNLICENSED
    for slug in sorted(OPENSTAX_UNLICENSED):
        record = openstax.ingest_section(settings, slug, 'index',
                                         transport=httpx.MockTransport(never_network))
        assert record['status'] == 'withheld', slug
        assert 'no licence' in record['withheld_reason'].lower(), slug
        assert 'text' not in record and 'excerpt' not in record, slug


def test_unlicensed_books_refuse_even_when_called_directly():
    slug = sorted(OPENSTAX_UNLICENSED)[0]
    with pytest.raises(IngestionRefused, match='no licence'):
        openstax.book_policy({'slug': slug, 'license_name': None, 'license_version': None},
                             book_slug=slug)


def test_the_hand_audited_exemplar_is_unchanged():
    entry = OPENSTAX_BOOK_POLICIES['algebra-and-trigonometry']
    assert entry.licence_class is LicenceClass.CC_BY
    assert entry.evidence_id == 'openstax_algebra_trig_1e_cc_by'
    assert entry.name == 'OpenStax Algebra and Trigonometry (1e)'


# ------------------------------------------------------------------- transparency

def test_describe_reports_the_full_catalogue(settings):
    posture = openstax.describe(settings)
    assert len(posture['books_audited']) == EXPECTED_TOTAL
    assert posture['catalogue']['text_eligible'] == EXPECTED_CC_BY
    assert posture['catalogue']['unlicensed_refused'] == EXPECTED_UNLICENSED


def test_catalogue_rows_are_sorted_and_complete():
    rows = policy.openstax_catalogue()
    assert len(rows) == EXPECTED_TOTAL
    assert [row['slug'] for row in rows] == sorted(row['slug'] for row in rows)
    for row in rows:
        assert {'slug', 'title', 'url', 'licence', 'licence_class', 'text_eligible',
                'commercial_ok', 'unlicensed', 'evidence_id'} <= set(row)


# --------------------------------------------------------------- the refresh script

def _load_script():
    path = Path(policy.__file__).parents[2] / 'scripts' / 'refresh_openstax_catalogue.py'
    spec = importlib.util.spec_from_file_location('refresh_openstax_catalogue', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refresh_script_refuses_a_truncated_listing():
    script = _load_script()
    with pytest.raises(ValueError, match='partial'):
        script.build_snapshot({'meta': {'total_count': 5}, 'items': [
            {'id': 1, 'meta': {'slug': 'a', 'html_url': 'u'}}]})


def test_refresh_script_refuses_duplicate_slugs():
    script = _load_script()
    with pytest.raises(ValueError, match='duplicate'):
        script.build_snapshot({'meta': {'total_count': 2}, 'items': [
            {'id': 1, 'meta': {'slug': 'a'}, 'title': 'A'},
            {'id': 2, 'meta': {'slug': 'a'}, 'title': 'A'}]})


def test_refresh_script_stores_raw_fields_only():
    """The snapshot must not carry a trusted rights class: editing the JSON cannot widen
    a book's rights, because the policy layer re-derives the class from publisher strings."""
    script = _load_script()
    snapshot = script.build_snapshot({'meta': {'total_count': 1}, 'items': [
        {'id': 9, 'meta': {'slug': 'x', 'html_url': 'https://openstax.org/details/books/x'},
         'title': 'X', 'locale': 'en', 'book_state': 'live',
         'license_name': 'Creative Commons Attribution-NonCommercial-ShareAlike License',
         'license_version': '4.0',
         'license_url': 'https://creativecommons.org/licenses/by-nc-sa/4.0/'}]})
    book = snapshot['books'][0]
    assert 'licence_class' not in book and 'rights' not in book
    assert book['license_name'].startswith('Creative Commons Attribution-NonCommercial')


# ------------------------------------------------------------------------ HTTP surface

def test_catalogue_route_serves_the_whole_audited_catalogue(tmp_path, monkeypatch):
    """The transparency endpoint must require a principal and serve every book."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    with TestClient(create_app(Settings.from_env())) as client:
        assert client.get('/api/v1/textbooks/catalogue').status_code == 401
        body = client.post('/api/v1/auth/register', json={
            'name': 'Catalogue probe', 'email': 'catalogue@example.com',
            'password': 'Correct-Horse-9', 'age_confirmed': True}).json()
        headers = {'Authorization': 'Bearer ' + body['token']}
        response = client.get('/api/v1/textbooks/catalogue', headers=headers)
        assert response.status_code == 200, response.text[:200]
        payload = response.json()
        assert len(payload['books']) == EXPECTED_TOTAL
        assert payload['summary']['text_eligible'] == EXPECTED_CC_BY
        assert payload['summary']['unlicensed_refused'] == EXPECTED_UNLICENSED
        # The same catalogue rides the media-source audit surface.
        sources = client.get('/api/v1/media/sources', headers=headers)
        assert sources.status_code == 200
        assert sources.json()['textbooks']['catalogue']['text_eligible'] == EXPECTED_CC_BY
