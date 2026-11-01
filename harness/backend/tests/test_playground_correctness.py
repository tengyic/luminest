"""The correctness oracle as a gate.

`playground_dom_smoke.js` proves a page *runs*; the content tests prove a page is
well-formed and self-contained. Neither can prove that a game is *right*, because
neither knows the answer. The correctness oracle does: it derives, from each game's own
spec, a concrete right answer and a concrete wrong answer, drives the rendered page with
the actions a learner would take, and asserts four things -

* a spec-derived correct answer is never scored ``correct: false`` (no inverted scoring);
* a spec-derived wrong answer is never scored ``correct: true``;
* one commit posts at most one outcome;
* a give-up is never scored ``correct: true``.

This module runs that oracle and fails if any case fails. It is the regression gate for a
whole class of bug that is invisible to every other harness here: the oracle's first run
found ``elasticity_probe`` scoring a wrong sign (after three tries) as ``correct: true``,
because ``finish()`` dropped the sign from its verdict entirely.

The two tests below are deliberately paired. The first is the gate; the second is the
negative control that keeps it from passing vacuously if the driver ever stops comparing
anything. Node is optional: both skip cleanly when it is absent, exactly as
``test_every_game_survives_a_headless_click_and_drag`` does.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.harness.playground import catalogue

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
BUILDER = SCRIPTS / 'playground_correctness_cases.py'
DRIVER = SCRIPTS / 'playground_correctness.mjs'


def _node_binary():
    found = shutil.which('node')
    if found:
        return found
    for candidate in ('/Users/tengyi/.workbuddy-ai/binaries/node/versions/22.22.2-6/bin/node',
                      '/usr/local/bin/node', '/opt/homebrew/bin/node'):
        if Path(candidate).exists():
            return candidate
    return None


def _build_cases(destination: Path) -> list:
    assert BUILDER.exists(), f'missing case builder: {BUILDER}'
    completed = subprocess.run([sys.executable, str(BUILDER), str(destination)],
                               capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, (
        f'the case builder exited {completed.returncode}\n'
        f'stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}')
    assert destination.exists(), 'the case builder wrote no bundle'
    return json.loads(destination.read_text(encoding='utf-8'))


def _run_driver(node: str, cases: Path):
    assert DRIVER.exists(), f'missing driver: {DRIVER}'
    completed = subprocess.run([node, str(DRIVER), str(cases)],
                               capture_output=True, text=True, timeout=300)
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    summary = next((line for line in reversed(lines) if line.startswith('SUMMARY ')), None)
    assert summary, (f'the driver produced no summary (exit {completed.returncode}).\n'
                     f'stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}')
    report = json.loads(summary[len('SUMMARY '):])
    rows = [json.loads(line) for line in lines if not line.startswith('SUMMARY ')]
    return completed.returncode, report, rows


def test_every_case_scores_a_correct_answer_correct_and_a_wrong_answer_wrong(tmp_path):
    """The gate: run the oracle over the whole catalogue and require zero failures."""
    node = _node_binary()
    if node is None:
        pytest.skip('node is not available, so the pages cannot be executed')

    cases_path = tmp_path / 'playground_correctness_cases.json'
    cases = _build_cases(cases_path)
    assert cases, 'the oracle built no cases, so this gate would be vacuous'

    returncode, report, rows = _run_driver(node, cases_path)

    # Coverage is part of the contract: a game whose archetype the oracle silently stops
    # covering would otherwise pass the gate by never being asked.
    used = {str(game['archetype']) for game in catalogue.all_games()}
    uncovered = sorted(used - set(report['archetypes_covered']))
    assert not uncovered, ('these archetypes have bundled games but no correctness case, '
                           f'so their scoring is unproven: {uncovered}')

    if report['failed']:
        kinds = ', '.join(f'{kind}={count}'
                          for kind, count in sorted(report['failure_kinds'].items()))
        broken = '\n'.join(
            f'  {row["slug"]} [{row["archetype"]}] {row["label"]}: '
            + '; '.join(f'{f["kind"]}: {f["why"]}' for f in row['failures'])
            for row in rows if not row.get('ok', True))
        pytest.fail(f'{report["failed"]} of {report["cases"]} correctness case(s) failed '
                    f'({kinds}):\n{broken}')

    assert returncode == 0, ('the driver reported no failures but exited '
                             f'{returncode}, so its summary cannot be trusted')


def test_the_gate_is_not_vacuous(tmp_path):
    """A deliberately inverted expectation must make the driver fail.

    Without this control, a driver that quietly stopped comparing outcomes would satisfy
    the gate above forever. Flipping one real case's expectation has to produce a failure
    of the expected kind - which is what proves the gate above can still catch a
    regression.
    """
    node = _node_binary()
    if node is None:
        pytest.skip('node is not available, so the pages cannot be executed')

    cases_path = tmp_path / 'playground_correctness_cases.json'
    cases = _build_cases(cases_path)

    inverted = []
    for case in cases:
        flipped = dict(case)
        flipped['expect_correct'] = [not value for value in case['expect_correct']]
        inverted.append(flipped)
    inverted_path = tmp_path / 'inverted.json'
    inverted_path.write_text(json.dumps(inverted), encoding='utf-8')

    returncode, report, _ = _run_driver(node, inverted_path)
    assert returncode != 0, 'the driver passed a bundle whose every expectation was inverted'
    assert report['failed'] > 0, 'the driver counted no failures on an inverted bundle'
    assert set(report['failure_kinds']) <= {'correct-scored-wrong', 'wrong-scored-correct'}, (
        'inverting an expectation should produce a scoring failure and nothing else, but '
        f'the driver reported: {sorted(report["failure_kinds"])}')
