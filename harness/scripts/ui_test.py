#!/usr/bin/env python3
"""Build and drive the native macOS app with an isolated real backend."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / 'harness/ui-tests'
OUTPUT = ROOT / 'outputs/ui'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate-only', action='store_true')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--backend-python', type=Path, default=TESTS / '.venv/bin/python')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use a nonprivileged local port')
    for parent in (TESTS, OUTPUT.parent):
        if not parent.is_dir():
            raise RuntimeError(f'Expected verified parent directory: {parent}')
    if not OUTPUT.is_dir():
        OUTPUT.mkdir()
    spec = importlib.util.spec_from_file_location('native_ui_project', TESTS / 'generate_project.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    config = 'enum RunnerConfiguration { static let endpoint = ' + json.dumps(f'http://127.0.0.1:{args.port}') + '; static let output = ' + json.dumps(str(OUTPUT)) + ' }\n'
    (TESTS / 'Tests/RunnerConfiguration.swift').write_text(config)
    sources = generator.generate(args.port)
    summary = {'driver': 'native macOS XCTest', 'sources': sources, 'port': args.port,
               'permissionPolicy': 'No AppleScript, browser automation, privilege changes, or fabricated UI results',
               'stage': 'project-generated'}
    summary_path = OUTPUT / 'run-summary.json'

    def save():
        summary_path.write_text(json.dumps(summary, indent=2))

    save()
    if args.generate_only:
        print(TESTS / 'NativeHarnessUI.xcodeproj')
        return 0
    if not args.backend_python.exists():
        raise RuntimeError('Backend Python missing; create harness/ui-tests/.venv with required backend dependencies, or pass --backend-python')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    state_parent = TESTS / 'test-state'
    if not state_parent.is_dir():
        raise RuntimeError('Expected harness/ui-tests/test-state')
    state = state_parent / (time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    state.mkdir()
    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith('HARNESS_'):
            environment.pop(key)
    environment.update({'HARNESS_ENV': 'test', 'HARNESS_DATA_DIR': str(state),
                        'HARNESS_DATABASE_URL': f'sqlite:///{state / "harness.sqlite3"}',
                        'HARNESS_AUTO_CREATE': '1', 'HARNESS_PORT': str(args.port),
                        'HARNESS_SECRET': secrets.token_urlsafe(48), 'HARNESS_TUTOR_PROVIDER': 'offline',
                        'HARNESS_UI_OUTPUT': str(OUTPUT), 'HARNESS_UI_ENDPOINT': f'http://127.0.0.1:{args.port}',
                        'HARNESS_ALLOWED_HOSTS': '127.0.0.1,localhost', 'PYTHONDONTWRITEBYTECODE': '1'})
    result = OUTPUT / 'NativeWorkflow.xcresult'
    if result.exists():
        result = OUTPUT / ('NativeWorkflow-' + state.name + '.xcresult')
    command = ['xcodebuild', 'test', '-project', str(TESTS / 'NativeHarnessUI.xcodeproj'),
               '-scheme', 'NativeHarnessUI', '-destination', 'platform=macOS',
               '-derivedDataPath', str(TESTS / 'DerivedData'), '-resultBundlePath', str(result),
               '-parallel-testing-enabled', 'NO']
    summary.update({'stateDirectory': str(state.relative_to(ROOT)), 'resultBundle': str(result.relative_to(ROOT)),
                    'command': command, 'stage': 'backend-starting'})
    save()
    returncode = 1
    with (OUTPUT / 'backend.log').open('w') as backend_log:
        backend = subprocess.Popen([str(args.backend_python), str(ROOT / 'harness/backend/scripts/run.py')],
                                   cwd=ROOT, env=environment, stdout=backend_log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 35
            while True:
                if backend.poll() is not None:
                    raise RuntimeError(f'Isolated backend exited {backend.returncode}; see outputs/ui/backend.log')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/v1/health', timeout=1) as response:
                        health = json.load(response)
                    if health.get('ready'):
                        break
                except (OSError, ValueError):
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError('Isolated backend readiness timed out')
                time.sleep(0.2)
            summary.update({'health': health, 'stage': 'xcodebuild-testing'})
            save()
            with (OUTPUT / 'xcodebuild.log').open('w') as build_log:
                process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in process.stdout:
                    build_log.write(line)
                    build_log.flush()
                    if any(word in line for word in ('error:', 'warning:', 'Test Case', 'Test Suite', '** TEST', 't =', 'Failing tests:')):
                        print(line.rstrip(), flush=True)
                returncode = process.wait()
            summary.update({'stage': 'passed' if returncode == 0 else 'failed', 'xcodebuildExitCode': returncode})
            result_summary = subprocess.run(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], capture_output=True, text=True)
            if result_summary.returncode == 0:
                summary['testResults'] = json.loads(result_summary.stdout)
                (OUTPUT / 'xcresult-summary.json').write_text(result_summary.stdout)
        except BaseException as error:
            summary.update({'stage': 'blocked', 'error': str(error)})
            raise
        finally:
            if backend.poll() is None:
                backend.terminate()
                try:
                    backend.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    backend.wait()
            database = state / 'harness.sqlite3'
            if database.exists():
                connection = sqlite3.connect(f'file:{database}?mode=ro', uri=True)
                tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                summary['databaseCounts'] = {table: connection.execute('SELECT count(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0] for table in tables}
                connection.row_factory = sqlite3.Row
                evidence = {}
                selections = {
                    'users': 'SELECT id, name, email, goal, daily_minutes, telemetry_consent FROM users',
                    'attempts': 'SELECT question_id, concept_id, mode, correct, elapsed_seconds, category FROM attempts ORDER BY created_at',
                    'assessments': 'SELECT mode, total, answered, correct, complete FROM assessments',
                    'messages': 'SELECT role, provider, content FROM messages ORDER BY created_at',
                    'projects': 'SELECT concept_id, status, submission, ai_disclosure, reflection, feedback FROM projects WHERE submission IS NOT NULL',
                }
                for table, query in selections.items():
                    if table in tables:
                        evidence[table] = [dict(row) for row in connection.execute(query)]
                (OUTPUT / 'backend-evidence.json').write_text(json.dumps(evidence, indent=2))
                summary['observedAttemptCount'] = len(evidence.get('attempts', []))
                summary['observedCompletedDiagnostic'] = any(row['mode'] == 'diagnostic' and row['complete'] for row in evidence.get('assessments', []))
                connection.close()
            summary['screenshots'] = sorted(path.name for path in OUTPUT.glob('*.png'))
            if not (OUTPUT / 'workflow-events.json').exists():
                (OUTPUT / 'workflow-events.json').write_text(json.dumps({'driver': 'native macOS XCTest / XCUIApplication', 'events': [], 'workflowCompleted': False, 'reason': 'No first-person UI event evidence was produced; consult xcresult and runner diagnostics.'}, indent=2))
            save()
    print(f'Native XCTest exit code: {returncode}; evidence: {OUTPUT}')
    return returncode


if __name__ == '__main__':
    sys.exit(main())
