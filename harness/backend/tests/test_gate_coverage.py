"""The release gate must cover every test file, not a hand-picked nine.

The 2026-11-13 review found that the published gate ran 9 of 122 files (7.4%)
and still reported PASS. This pins the discovery and the verdict rules so a
subset can never quietly become the release gate again.
"""

import importlib.util
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[2] / 'scripts' / 'quality_gate.py'


@pytest.fixture(scope='module')
def gate():
    spec = importlib.util.spec_from_file_location('quality_gate_under_test', GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_layers_discover_every_test_file(gate):
    discovered = gate.discover_test_files()
    unit, service, coverage = gate.split_backend_layers(fast=False)
    assert coverage['discovered'] == len(discovered)
    assert coverage['executed'] == len(discovered)
    assert coverage['percent'] == 100.0
    assert not coverage['not_exercised']
    assert not coverage['fast_smoke']
    assert not (set(unit) & set(service)), 'a file must not be counted twice'
    assert sorted(unit + service) == discovered


def test_fast_smoke_is_explicitly_partial(gate):
    unit, service, coverage = gate.split_backend_layers(fast=True)
    assert len(unit) == 6 and len(service) == 3
    assert coverage['fast_smoke'] is True
    assert coverage['executed'] < coverage['discovered']
    assert coverage['not_exercised'], 'the smoke must name the files it skips'


def test_a_smoke_run_can_never_produce_a_release_verdict(gate):
    _, _, coverage = gate.split_backend_layers(fast=True)
    passed, blockers = gate.summarise(
        [{'layer': 'unit', 'passed': True, 'exit': 0, 'test_files': 6,
          'blocking_skips': [], 'skipped_tests': 0},
         {'layer': 'integration', 'passed': True, 'exit': 0, 'test_files': 3,
          'blocking_skips': [], 'skipped_tests': 0}],
        strict=False, extras=[], coverage=coverage)
    assert passed is False
    assert any('not a release verdict' in b for b in blockers)


def test_undeclared_skips_block_but_declared_ones_do_not(gate):
    declared = {'layer': 'unit', 'passed': True, 'exit': 0,
                'skipped_tests': 2, 'declared_skips': ['a', 'b'],
                'blocking_skips': []}
    assert gate.summarise([declared], False, [], None)[0] is True
    undeclared = {**declared, 'blocking_skips': ['PostgreSQL half skipped']}
    passed, blockers = gate.summarise([undeclared], False, [], None)
    assert passed is False
    assert any('undeclared skip' in b for b in blockers)


def test_partial_layer_selection_cannot_claim_full_coverage(gate):
    all_files = gate.discover_test_files()
    partial = {'executed': len(all_files) // 2, 'discovered': len(all_files),
               'percent': 50.0, 'fast_smoke': False,
               'not_exercised': all_files[len(all_files) // 2:]}
    passed, blockers = gate.summarise([], False, [], partial)
    assert passed is False
    assert any('not executed' in b for b in blockers)
