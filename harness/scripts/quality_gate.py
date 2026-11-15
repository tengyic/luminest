#!/usr/bin/env python3
"""The release gate: run the four test layers and refuse to call the build releasable
unless every layer and all ten golden journeys are green.

Design rules, because a gate that lies is worse than no gate:

* **The backend layers run every test file.** Layer 1 and Layer 2 are discovered from
  ``backend/tests/test_*.py`` at run time, not enumerated by hand. A gate that hardcodes
  nine files can report PASS while 113 files have never been executed by it -- the exact
  failure the 2026-11-12 review named ("7.4% of test files"). ``--fast`` keeps the old
  nine-file subset for a quick local smoke, but a smoke run is *never* a release verdict:
  ``summarise`` blocks it and the coverage field says so.
* A **skip is not a pass**, except for the two *declared, opt-in* live-provider smokes
  (``HARNESS_LIVE_SMOKE`` / ``HARNESS_DIAGRAM_LIVE_SMOKE``). Those are off by design and
  their reasons are recorded in ``gate.json``; they are never hidden. Every other test-level
  skip -- notably the PostgreSQL half of Layer 2 when no server is reachable -- blocks the
  verdict at every strictness. A **layer** that was not run at all (``--skip-ui``, no built
  app) blocks unconditionally too. ``--strict`` promotes the advisory *checks* (the
  dependency audit) into blockers.
* A **gap is not a pass.** Any journey whose native path cannot be driven is reported as
  ``gap`` (and a runner error as ``blocked``); both fail the release decision while the
  reason is printed. Course creation (J6) does have a native authoring sheet now, but its
  verdict still comes from the runner's observation, never from the presence of the code.
* A layer's verdict comes from its *runner's* exit code and its own JSON evidence, not
  from parsing log text for the word "passed".

Usage::

    python3 scripts/quality_gate.py                     # every layer, full backend suite
    python3 scripts/quality_gate.py --layers 1,2        # full backend suite, no UI
    python3 scripts/quality_gate.py --layers 1,2 --fast # 9-file smoke; NOT a release verdict
    python3 scripts/quality_gate.py --layers 3 --skip-ui  # records the UI layer as skipped
    python3 scripts/quality_gate.py --strict            # skips also fail the gate
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / 'harness'
BACKEND = HARNESS / 'backend'

#: These are the *old* nine-file subset, retained only for ``--fast``. They are a smoke,
#: not a release gate: ``summarise`` refuses to call a smoke run releasable. The default
#: layers discover the whole suite instead (see ``discover_test_files``).
FAST_UNIT_TESTS = [
    'tests/test_memory.py',
    'tests/test_flashcards.py',
    'tests/test_learning_science.py',
    'tests/test_memory_properties.py',
    'tests/test_learning_properties.py',
    'tests/test_security_contract.py',
]

FAST_INTEGRATION_TESTS = [
    'tests/test_api.py',
    'tests/test_database_engines.py',
    'tests/test_desktop_environment.py',
]

#: Test files that legitimately need an external service and therefore belong to Layer 2.
#: Everything else discovered under tests/ is Layer 1. Both sets are computed from the
#: directory, so a newly added test file cannot silently escape the gate.
SERVICE_TEST_FILES = {
    'tests/test_database_engines.py',   # PostgreSQL half skips when no server is reachable
    'tests/test_desktop_environment.py',
    'tests/test_api.py',
}

#: The only skips that do not block the verdict. Both are explicit opt-in live-provider
#: smokes, off by default with a named reason; everything else is an untested path.
DECLARED_SKIP_REASONS = (
    'Live smoke disabled; set HARNESS_LIVE_SMOKE=1',
    'Live DeepSeek diagram smoke disabled; set HARNESS_DIAGRAM_LIVE_SMOKE=1',
)


def discover_test_files() -> list[str]:
    """Every test file in the backend, discovered rather than enumerated by hand."""
    return sorted(str(path.relative_to(BACKEND))
                  for path in (BACKEND / 'tests').glob('test_*.py'))


def split_backend_layers(fast: bool) -> tuple[list[str], list[str], dict]:
    """Return (unit files, service files, coverage) for this run.

    ``coverage`` is the gate's own, machine-readable answer to "how much of the suite did
    this run actually execute?" so a subset can never be published as a full pass again.
    """
    all_files = discover_test_files()
    if fast:
        unit, service = FAST_UNIT_TESTS, FAST_INTEGRATION_TESTS
    else:
        unit = [f for f in all_files if f not in SERVICE_TEST_FILES]
        service = [f for f in all_files if f in SERVICE_TEST_FILES]
    executed = sorted(set(unit) | set(service))
    coverage = {
        'discovered': len(all_files),
        'executed': len(executed),
        'percent': round(100.0 * len(executed) / len(all_files), 1) if all_files else 0.0,
        'fast_smoke': fast,
        'not_exercised': sorted(set(all_files) - set(executed)),
    }
    return unit, service, coverage


def find_python(explicit: str | None) -> Path:
    if explicit:
        # Deliberately NOT .resolve(): a virtualenv's bin/python is a symlink to the base
        # interpreter, and resolving it drops the venv — pytest then runs with the base
        # interpreter's site-packages and reports a missing dependency that is installed.
        path = Path(explicit).expanduser().absolute()
        if not path.is_file():
            raise SystemExit(f'--python does not exist: {path}')
        return path
    # Prefer the canonical venv by name. ``sorted(...)[-1]`` used to pick whichever
    # throwaway venv happened to sort last — on the build machine that was
    # ``.venv-phase2-test``, which has no dependencies, so the gate failed at collection in
    # 3.7 s while a correct run took two minutes. A release gate whose default command is
    # deterministically broken is worse than no gate: it teaches people to pass --python.
    canonical = BACKEND / '.venv' / 'bin' / 'python'
    if canonical.is_file():
        return canonical
    candidates = sorted(BACKEND.glob('.venv*/bin/python'))
    if not candidates:
        raise SystemExit('No backend virtualenv found; pass --python <venv python>')
    if len(candidates) > 1:
        listed = ', '.join(str(c) for c in candidates)
        raise SystemExit(f'No {canonical} and several alternatives exist ({listed}); '
                         'pass --python <venv python> to say which one this gate should trust')
    return candidates[0]


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


#: A full backend layer runs ~120 test files in one process. Measured 2026-11-12:
#: 1267 s for the whole suite on this host, and 2339 s on a busy machine. The old
#: 1800 s ceiling timed out a legitimate full-suite gate run (2026-11-13), which is
#: worse than a slow gate: it turns a green build into an unexplained failure.
FULL_LAYER_TIMEOUT = 3600


def pytest_layer(python: Path, files: list[str], output: Path, name: str,
                 timeout: int = FULL_LAYER_TIMEOUT) -> dict:
    """Run one pytest layer in an isolated temp root inside the repo.

    ``TMPDIR`` and ``--basetemp`` must both point inside the repository: the sandbox
    refuses the system temp root, and a pytest basetemp outside the tree makes the
    session fail before the first test with a message that looks like a product bug.
    """
    temp = output / ('tmp-' + name)
    temp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TMPDIR=str(temp), PYTHONDONTWRITEBYTECODE='1')
    env.pop('HARNESS_DATABASE_URL', None)
    # -rs prints each skip with its reason, so the gate can tell the two declared opt-in
    # live-provider smokes from a path that was silently not exercised.
    result = run([str(python), '-m', 'pytest', '-q', '-rs', '--basetemp', str(temp / 'bt'),
                  *files], BACKEND, env, timeout=timeout)
    result['layer'] = name
    result['passed'] = result['exit'] == 0
    result['test_files'] = len(files)
    stdout = result.get('stdout') or ''
    skipped = re.search(r'(\d+) skipped', stdout)
    total_skipped = int(skipped.group(1)) if skipped else 0
    reasons = re.findall(r'^SKIPPED \[\d+\] (.+)$', stdout, flags=re.MULTILINE)
    declared = [r for r in reasons
                if any(marker in r for marker in DECLARED_SKIP_REASONS)]
    undeclared = [r for r in reasons
                  if not any(marker in r for marker in DECLARED_SKIP_REASONS)]
    result['declared_skips'] = declared
    result['skipped_tests'] = total_skipped
    # A pytest summary with no -rs detail (older runner, or output truncated) still has
    # to fail closed: any skip we cannot attribute to a declared opt-in reason blocks.
    result['unattributed_skips'] = max(0, total_skipped - len(declared))
    result['blocking_skips'] = undeclared + (
        [f'{result["unattributed_skips"]} skip(s) with no attributable declared reason']
        if result['unattributed_skips'] else [])
    if result['blocking_skips']:
        result['skipped_reason'] = (f'{len(result["blocking_skips"])} undeclared skip(s) inside '
                                    'this layer; a skip is not a pass')
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


def summarise(rows: list[dict], strict: bool, extras: list[dict] | None = None,
              coverage: dict | None = None) -> tuple[bool, list[str]]:
    """Decide the release verdict from the layer evidence.

    A skipped layer blocks the release unconditionally: "we did not run the UI tests" is
    not a green build. A **subset** of the backend suite also blocks it: publishing a
    nine-file PASS as a release verdict is the 7.4% failure this gate now exists to
    prevent. ``--strict`` additionally promotes advisory checks (the dependency audit)
    into blockers; without it they are reported but do not decide the gate.
    """
    blockers: list[str] = []
    if coverage:
        if coverage.get('fast_smoke'):
            blockers.append(
                f'backend coverage: --fast smoke ran {coverage["executed"]} of '
                f'{coverage["discovered"]} test files ({coverage["percent"]}%). '
                'A smoke is not a release verdict; re-run without --fast.')
        elif coverage.get('not_exercised'):
            blockers.append(f'backend coverage: {len(coverage["not_exercised"])} test file(s) '
                            'were discovered but not executed by any layer')
    for row in rows:
        name = row.get('layer')
        if row.get('skipped'):
            blockers.append(f'{name}: skipped — {row.get("reason", "no reason recorded")}')
            continue
        if not row.get('passed'):
            blockers.append(f'{name}: failed (exit {row.get("exit")})')
        # Only *undeclared* skips block. The two opt-in live-provider smokes are declared,
        # off by design and recorded with their reasons; a PostgreSQL half that quietly
        # skipped, or any other untested path, still fails the gate. Declared skips are
        # never hidden -- they are written into gate.json.
        if row.get('blocking_skips'):
            blockers.append(f'{name}: {len(row["blocking_skips"])} undeclared skip(s) — '
                            'a skip is not a pass')
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
    cov = document.get('coverage') or {}
    if cov:
        lines += [f"**Backend test-file coverage:** {cov['executed']}/{cov['discovered']} "
                  f"files ({cov['percent']}%)"
                  + (' — **FAST SMOKE, not a release verdict**' if cov.get('fast_smoke') else ''),
                  '']
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
            elif row.get('test_files'):
                detail += f"; {row['test_files']} test files"
                if row.get('declared_skips'):
                    detail += f"; {len(row['declared_skips'])} declared opt-in skip(s)"
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
    parser.add_argument('--fast', action='store_true',
                        help='Run only the legacy 9-file smoke. This can NEVER produce a '
                             'release verdict; use it for a quick local check only.')
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

    unit_files, service_files, coverage = split_backend_layers(args.fast)
    # Coverage must describe what was actually executed, not what a full run would have
    # executed. A --layers 3 run cannot claim the backend files it never launched.
    backend_layers = [n for n in ('unit', 'integration') if n in
                      ({'unit'} if '1' in layers else set()) |
                      ({'integration'} if '2' in layers else set())]
    all_files = discover_test_files()
    executed = set()
    if '1' in layers:
        executed.update(unit_files)
    if '2' in layers:
        executed.update(service_files)
    coverage = dict(coverage, executed=len(executed & set(all_files)),
                    percent=round(100.0 * len(executed & set(all_files)) / len(all_files), 1)
                    if all_files else 0.0,
                    not_exercised=sorted(set(all_files) - executed),
                    backend_layers_run=backend_layers)
    if not args.fast and ('1' not in layers or '2' not in layers):
        coverage['partial_reason'] = ('both backend layers (1 and 2) are required for a '
                                      'full-suite verdict')

    results: list[dict] = []
    if '1' in layers:
        results.append(pytest_layer(python, unit_files, output, 'unit'))
    if '2' in layers:
        results.append(pytest_layer(python, service_files, output, 'integration'))
    if '3' in layers or '4' in layers:
        results.append(native_layer(output, args.ui_timeout, args.skip_ui, args.app, python))

    extras: list[dict] = []
    if not args.no_audit:
        extras.append(dependency_audit(python, output))
    if args.mutation:
        extras.append(mutation_check(python, output))

    passed, blockers = summarise(results, args.strict, extras, coverage)
    document = {'runId': run_id, 'startedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                'python': str(python), 'layers': sorted(layers), 'coverage': coverage,
                'results': results, 'extras': extras,
                'blockers': blockers, 'passed': passed}
    (output / 'gate.json').write_text(json.dumps(document, indent=2) + '\n')
    (output / 'GATE.md').write_text(render_markdown(document))

    print(render_markdown(document))
    print(f'Evidence: {output}')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
