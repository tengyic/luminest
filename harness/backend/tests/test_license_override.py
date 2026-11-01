"""Tests for the operator-controlled licence override mechanism.

The override is data, not code: absent by default, fail-closed on every malformed
input, and never able to widen a PROHIBITED source. These tests pin each of those
rules because a licence gate that quietly misreads its own override file is worse
than one with no override mechanism at all.
"""

from __future__ import annotations

import json

import pytest

from app.ingest import policy
from app.ingest.policy import (OPENSTAX_ELEMENTARY_ALGEBRA, KHAN_ACADEMY_TERMS,
                               IngestionRefused, apply_overrides, assert_ingestible,
                               load_overrides, registry, reset_override_cache)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(policy.OVERRIDE_ENV_VAR, raising=False)
    reset_override_cache()
    yield
    reset_override_cache()


def _write_override(tmp_path, payload):
    path = tmp_path / 'overrides.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _enable(monkeypatch, path):
    monkeypatch.setenv(policy.OVERRIDE_ENV_VAR, str(path))


def _record(**over):
    base = {'policy_name': 'OpenStax Elementary Algebra 2e',
            'licence_class': 'cc_by',
            'scope': 'Attribution-preserving quotation only',
            'evidence_url': 'https://example.com/rights',
            'approved_by': 'operator', 'approved_at': '2026-10-11'}
    base.update(over)
    return {'schema': policy.OVERRIDE_SCHEMA, 'overrides': [base]}


def test_no_file_means_no_overrides():
    assert load_overrides() == {}


def test_default_position_unchanged_without_file():
    assert apply_overrides(OPENSTAX_ELEMENTARY_ALGEBRA) is OPENSTAX_ELEMENTARY_ALGEBRA
    with pytest.raises(IngestionRefused):
        assert_ingestible(OPENSTAX_ELEMENTARY_ALGEBRA)


def test_valid_override_flips_only_the_named_policy(tmp_path, monkeypatch):
    _enable(monkeypatch, _write_override(tmp_path, _record()))
    effective = apply_overrides(OPENSTAX_ELEMENTARY_ALGEBRA)
    assert effective is not OPENSTAX_ELEMENTARY_ALGEBRA
    assert effective.licence_class.value == 'cc_by'
    assert effective.ingestible
    assert effective.evidence_id.startswith('operator_override:')
    # The original frozen declaration is untouched.
    assert OPENSTAX_ELEMENTARY_ALGEBRA.licence_class.value == 'link_only'
    # A policy with no override keeps its identity and its class.
    assert apply_overrides(KHAN_ACADEMY_TERMS) is KHAN_ACADEMY_TERMS


def test_unknown_policy_name_is_dropped(tmp_path, monkeypatch):
    _enable(monkeypatch, _write_override(tmp_path, _record(policy_name='Not A Real Source')))
    assert load_overrides() == {}
    assert apply_overrides(OPENSTAX_ELEMENTARY_ALGEBRA) is OPENSTAX_ELEMENTARY_ALGEBRA


def test_prohibited_source_can_never_be_overridden(tmp_path, monkeypatch, recwarn):
    _enable(monkeypatch, _write_override(tmp_path, _record(policy_name=KHAN_ACADEMY_TERMS.name,
                                                           licence_class='cc_by')))
    assert load_overrides() == {}
    with pytest.raises(IngestionRefused):
        assert_ingestible(KHAN_ACADEMY_TERMS)
    assert any('never operator-overridable' in str(w.message) for w in recwarn.list)


def test_unknown_target_class_dropped(tmp_path, monkeypatch):
    _enable(monkeypatch, _write_override(tmp_path, _record(licence_class='cc_by_nc_nd_wildcard')))
    assert load_overrides() == {}


def test_missing_approval_fields_dropped(tmp_path, monkeypatch):
    _enable(monkeypatch, _write_override(tmp_path, _record(approved_by='')))
    assert load_overrides() == {}
    _enable(monkeypatch, _write_override(tmp_path, _record(approved_at='')))
    assert load_overrides() == {}


def test_unreadable_file_fails_closed(tmp_path, monkeypatch, recwarn):
    path = tmp_path / 'broken.json'
    path.write_text('{not json', encoding='utf-8')
    _enable(monkeypatch, path)
    assert load_overrides() == {}
    assert apply_overrides(OPENSTAX_ELEMENTARY_ALGEBRA) is OPENSTAX_ELEMENTARY_ALGEBRA
    assert any('unreadable' in str(w.message) for w in recwarn.list)


def test_wrong_schema_fails_closed(tmp_path, monkeypatch):
    _enable(monkeypatch, _write_override(tmp_path, {'overrides': [_record()['overrides'][0]]}))
    assert load_overrides() == {}


def test_registry_reports_effective_position_and_override(tmp_path, monkeypatch):
    _enable(monkeypatch, _write_override(tmp_path, _record()))
    entries = {e['name']: e for e in registry()}
    effective = entries[OPENSTAX_ELEMENTARY_ALGEBRA.name]
    assert effective['licence_class'] == 'cc_by'
    assert effective['operator_override']['approved_by'] == 'operator'
    untouched = entries[KHAN_ACADEMY_TERMS.name]
    assert untouched['licence_class'] == 'prohibited'
    assert untouched['operator_override'] is None
