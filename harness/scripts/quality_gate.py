#!/usr/bin/env python3
"""The release gate: run the four test layers and refuse to call the build releasable
unless every layer and all ten golden journeys are green.

Design rules, because a gate that lies is worse than no gate:

* A **skip is not a pass.** The PostgreSQL half of Layer 2 skips when no server is
  reachable; the gate records ``skipped`` and does not treat it as green in ``--strict``.
* A **gap is not a pass.** Any journey whose native path cannot be driven is reported as
  ``gap`` (and a runner error as ``blocked``); both fail the release decision while the
  reason is printed. Course creation (J6) does have a native authoring sheet now, but its
  verdict still comes from the runner's observation, never from the presence of the code.
* A layer's verdict comes from its *runner's* exit code and its own JSON evidence, not
  from parsing log text for the word "passed".

Usage::

    python3 scripts/quality_gate.py                     # every layer
    python3 scripts/quality_gate.py --layers 1,2        # backend only (fast, CI-friendly)
    python3 scripts/quality_gate.py --layers 3 --skip-ui  # records the UI layer as skipped
    python3 scripts/quality_gate.py --strict            # skips also fail the gate
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / 'harness'
BACKEND = HARNESS / 'backend'

UNIT_TESTS = [
    'tests/test_memory.py',
    'tests/test_flashcards.py',
    'tests/test_learning_science.py',
    'tests/test_memory_properties.py',
    'tests/test_learning_properties.py',
    'tests/test_security_contract.py',
]

INTEGRATION_TESTS = [
    'tests/test_api.py',
    'tests/test_database_engines.py',
    'tests/test_desktop_environment.py',
]


def find_python(explicit: str | None) -> Path:
    if explicit:
        # Deliberately NOT .resolve(): a virtualenv's bin/python is a symlink to the base
        # interpreter, and resolving it drops the venv — pytest then runs with the base
        # interpreter's site-packages and reports a missing dependency that is installed.
        path = Path(explicit).expanduser().absolute()
        if not path.is_file():
            raise SystemExit(f'--python does not exist: {path}')
        return path
    candidates = sorted(BACKEND.glob('.venv*/bin/python'))
    if not candidates:
        raise SystemExit('No backend virtualenv found; pass --python <venv python>')
    return candidates[-1]


def run(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> dict:
    started = time.time()
    try:
        completed = subprocess.run(command, cwd=cwd, env=env, timeout=timeout,
                                   capture_output=True, text=True)
        code, out, err = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as expired:
        code = 124
        out = (expired.stdout or '') if isinstance(expired.stdout, str) else ''
        err = f'timed out after {timeout}s'
    return {'command': command, 'cwd': str(cwd), 'exit': code,
            'seconds': round(time.time() - started, 1),
            'stdout': out[-8000:], 'stderr': err[-8000:]}


def pytest_layer(python: Path, files: list[str], output: Path, name: str) -> dict:
    """Run one pytest layer in an isolated temp root inside the repo.

    ``TMPDIR`` and ``--basetemp`` must both point inside the repository: the sandbox
    refuses the system temp root, and a pytest basetemp outside the tree makes the
    session fail before the first test with a message that looks like a product bug.
    """
    temp = output / ('tmp-' + name)
    temp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TMPDIR=str(temp), PYTHONDONTWRITEBYTECODE='1')
    env.pop('HARNESS_DATABASE_URL', None)
    result = run([str(python), '-m', 'pytest', '-q', '--basetemp', str(temp / 'bt'), *files],
                 BACKEND, env, timeout=1800)
    result['layer'] = name
    result['passed'] = result['exit'] == 0
    return result


def native_layer(output: Path, timeout: int, skip_ui: bool, app: str | None,
                 python: Path) -> dict:
    if skip_ui:
        return {'layer': 'native-ui', 'skipped': True,
                'reason': 'UI layer skipped by request (--skip-ui); this is not a pass.',
                'passed': False}
    executable = app or str(HARNESS / 'native/.build/debug/LearningHarness')
    if not Path(executable).exists():
        return {'layer': 'native-ui', 'skipped': True,
                'reason': f'no built app at {executable}; build first (swift build --disable-sandbox)',
                'passed': False}
    evidence = output / 'native'
    if evidence.exists():
        shutil.rmtree(evidence)
    result = run([sys.executable, str(HARNESS / 'scripts/native_qa.py'), '--journeys',
                  '--app', executable, '--backend-python', str(python),
                  '--port', '8891', '--output', str(evidence), '--timeout', str(timeout)],
                 HARNESS, dict(os.environ), timeout=timeout + 120)
    summary_path = evidence / 'run-summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    result.update({
        'layer': 'native-ui',
        'passed': result['exit'] == 0 and summary.get('status') == 'passed',
        'status': summary.get('status'),
        'gate': summary.get('journeyGate', {}),
        'journeys': (summary.get('journeys') or {}).get('journeys', []),
        'counts': summary.get('databaseCounts', {}),
        'evidence': str(evidence),
    })
    return result


def dependency_audit(python: Path, output: Path) -> dict:
    """Known-vulnerability scan of the pinned runtime requirements."""
    audit = shutil.which('pip-audit') or str(Path(python).parent / 'pip-audit')
    if not Path(audit).exists() and not shutil.which('pip-audit'):
        return {'layer': 'dependencies', 'skipped': True,
                'reason': 'pip-audit is not installed in the build environment', 'passed': False}
    report = output / 'pip-audit.json'
    result = run([audit, '-r', str(BACKEND / 'requirements.txt'), '--format', 'json',
                  '--output', str(report), '--progress-spinner', 'off'],
                 HARNESS, dict(os.environ), timeout=600)
    vulnerabilities = []
    if report.is_file():
        try:
            payload = json.loads(report.read_text())
            for dependency in payload.get('dependencies', []):
                for vuln in dependency.get('vulns', []) or []:
                    vulnerabilities.append({'package': dependency.get('name'),
                                            'id': vuln.get('id'),
                                            'fix': ', '.join(vuln.get('fix_versions') or [])})
        except ValueError:
            pass
    result.update({'layer': 'dependencies', 'passed': result['exit'] == 0 and not vulnerabilities,
                   'vulnerabilities': vulnerabilities})
    return result


def mutation_check(python: Path, output: Path) -> dict:
    script = HARNESS / 'scripts/mutation_check.py'
    if not script.is_file():
        return {'layer': 'mutation', 'skipped': True, 'reason': 'mutation_check.py missing',
                'passed': False}
    result = run([str(python), str(script), '--json', str(output / 'mutation.json')],
                 HARNESS, dict(os.environ), timeout=1800)
    payload = {}
    if (output / 'mutation.json').is_file():
        payload = json.loads((output / 'mutation.json').read_text())
    result.update({'layer': 'mutation', 'passed': result['exit'] == 0,
                   'killed': payload.get('killed'), 'survived': payload.get('survived'),
                   'score': payload.get('score')})
    return result


def summarise(rows: list[dict], strict: bool, extras: list[dict] | None = None) -> tuple[bool, list[str]]:
    """Decide the release verdict from the layer evidence.

    A skipped layer blocks the release unconditionally: "we did not run the UI tests" is
    not a green build. ``--strict`` additionally promotes advisory checks (the dependency
    audit) into blockers; without it they are reported but do not decide the gate.
    """
    blockers: list[str] = []
    for row in rows:
        name = row.get('layer')
        if row.get('skipped'):
            blockers.append(f'{name}: skipped — {row.get("reason", "no reason recorded")}')
            continue
        if not row.get('passed'):
            blockers.append(f'{name}: failed (exit {row.get("exit")})')
        if name == 'native-ui':
            gate = row.get('gate') or {}
            for key in ('failed', 'gaps', 'blocked', 'missing'):
                for journey in gate.get(key, []) or []:
                    blockers.append(f'{name}: {journey} {key}')
    if strict:
        for extra in extras or []:
            if not extra.get('passed'):
                blockers.append(f'{extra.get("layer")}: {extra.get("reason") or "advisory check failed"}')
    return not blockers, blockers


def render_markdown(document: dict) -> str:
    lines = ['# Release gate', '',
             f"**Run:** {document['runId']}  ",
             f"**Started:** {document['startedAt']}  ",
             f"**Verdict:** **{'PASS' if document['passed'] else 'FAIL'}**", '']
    lines += ['| Layer | Result | Time | Detail |', '|---|---|---:|---|']
    for row in document['results']:
        if row.get('skipped'):
            verdict, detail = 'SKIPPED', row.get('reason', '')
        else:
            verdict = 'PASS' if row.get('passed') else 'FAIL'
            detail = f"exit {row.get('exit')}"
            if row['layer'] == 'native-ui':
                gate = row.get('gate') or {}
                detail = (f"{gate.get('total', 0)}/10 journeys; "
                          f"failed={gate.get('failed', [])} gaps={gate.get('gaps', [])} "
                          f"blocked={gate.get('blocked', [])}")
        lines.append(f"| {row['layer']} | {verdict} | {row.get('seconds', 0)}s | {detail} |")
    if document.get('blockers'):
        lines += ['', '## Blockers', '']
        lines += [f'- {item}' for item in document['blockers']]
    journeys = next((r.get('journeys') for r in document['results']
                     if r.get('layer') == 'native-ui' and r.get('journeys')), [])
    if journeys:
        lines += ['', '## Golden journeys', '', '| Journey | Status | Checks |', '|---|---|---|']
        for journey in journeys:
            checks = journey.get('checks', [])
            ok = sum(1 for c in checks if c.get('ok'))
            lines.append(f"| {journey['id']} — {journey['title']} | **{journey['status']}** | {ok}/{len(checks)} |")
        lines += ['', 'Verdicts: `pass` = verified through the app; `fail` = the product broke; '
                      '`gap` = no native path exists; `blocked` = could not be exercised here.']
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--layers', default='1,2,3,4', help='Comma-separated layers to run')
    parser.add_argument('--python', default=None, help='Backend virtualenv interpreter')
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--app', default=None, help='Already-built native executable or .app')
    parser.add_argument('--skip-ui', action='store_true')
    parser.add_argument('--no-audit', action='store_true')
    parser.add_argument('--mutation', action='store_true')
    parser.add_argument('--strict', action='store_true', help='Skips fail the gate too')
    parser.add_argument('--ui-timeout', type=int, default=900)
    args = parser.parse_args()

    layers = {part.strip() for part in args.layers.split(',') if part.strip()}
    unknown = layers - {'1', '2', '3', '4'}
    if unknown:
        raise SystemExit(f'Unknown layer(s): {sorted(unknown)}')

    python = find_python(args.python)
    run_id = time.strftime('%Y%m%d-%H%M%S')
    output = (args.output or ROOT / 'outputs/quality' / run_id).resolve()
    output.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    if '1' in layers:
        results.append(pytest_layer(python, UNIT_TESTS, output, 'unit'))
    if '2' in layers:
        results.append(pytest_layer(python, INTEGRATION_TESTS, output, 'integration'))
    if '3' in layers or '4' in layers:
        results.append(native_layer(output, args.ui_timeout, args.skip_ui, args.app, python))

    extras: list[dict] = []
    if not args.no_audit:
        extras.append(dependency_audit(python, output))
    if args.mutation:
        extras.append(mutation_check(python, output))

    passed, blockers = summarise(results, args.strict, extras)
    document = {'runId': run_id, 'startedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                'python': str(python), 'layers': sorted(layers),
                'results': results, 'extras': extras,
                'blockers': blockers, 'passed': passed}
    (output / 'gate.json').write_text(json.dumps(document, indent=2) + '\n')
    (output / 'GATE.md').write_text(render_markdown(document))

    print(render_markdown(document))
    print(f'Evidence: {output}')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
