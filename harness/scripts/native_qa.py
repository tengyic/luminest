#!/usr/bin/env python3
"""Run an already-built native app against an owned, isolated backend; never build or use XCTest."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / 'harness'


def save_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def executable_for(path):
    path = path.expanduser().resolve()
    if path.is_dir() and path.suffix.lower() == '.app':
        with (path / 'Contents/Info.plist').open('rb') as stream:
            name = plistlib.load(stream).get('CFBundleExecutable')
        if not isinstance(name, str) or Path(name).name != name:
            raise RuntimeError('App bundle has no safe CFBundleExecutable name')
        path = path / 'Contents/MacOS' / name
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f'Already-built executable is missing or not executable: {path}')
    return path


def stop_owned(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def verify_password(python, password, encoded):
    # Check the real stored hash using the backend's installed Argon2, not an auth API
    # fallback. The password is sent over stdin only and never written to evidence.
    code = (
        'import json,sys; from argon2 import PasswordHasher; '
        'from argon2.exceptions import VerificationError,InvalidHashError; '
        'data=json.load(sys.stdin)\n'
        'try: matches=PasswordHasher().verify(data["encoded"],data["password"])\n'
        'except (VerificationError,InvalidHashError): matches=False\n'
        'print(json.dumps({"matches":bool(matches)}))\n'
    )
    result = subprocess.run([str(python), '-c', code],
                            input=json.dumps({'encoded': encoded, 'password': password}),
                            text=True, capture_output=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError('Backend password hash verification failed to execute')
    return json.loads(result.stdout)['matches'] is True


def decoded_json(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def observed_text(output, name):
    path = output / (name + '-accessibility.json')
    if not path.is_file():
        return ''
    return ' '.join(json.loads(path.read_text()).get('texts', []))


def normalized(text):
    return ' '.join(str(text).split())


def inspect_database(database, output, python, expected, password, course=None):
    if not database.is_file():
        return {'checks': {'isolatedDatabaseExists': False}, 'databaseCounts': {}, 'records': {}}
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        counts = {table: connection.execute('SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0]
                  for table in tables}
        users = [dict(row) for row in connection.execute(
            'SELECT id,name,email,goal,daily_minutes,telemetry_consent,training_consent,last_heartbeat,'
            'course_id,onboarding_completed_at FROM users')]
        account = next((row for row in users if row['email'] == expected['email']), None)
        checks = {'isolatedDatabaseExists': True, 'uniqueAccount': len(users) == 1 and account is not None,
                  'registeredNameMatches': account is not None and account['name'] == expected['name']}
        records = {'users': users}
        if account is None:
            return {'checks': checks, 'databaseCounts': counts, 'records': records}
        user_id = account['id']
        encoded = connection.execute('SELECT password_hash FROM users WHERE id=?', (user_id,)).fetchone()[0]
        checks['registeredPasswordMatchesRealFieldInput'] = verify_password(python, password, encoded)
        checks['backendIssuedSignedInSession'] = connection.execute(
            'SELECT COUNT(*) FROM tokens WHERE user_id=? AND expires_at>?', (user_id, time.time())).fetchone()[0] > 0
        selections = {
            'attempts': 'SELECT id,question_id,concept_id,mode,correct,elapsed_seconds,category,payload,response FROM attempts WHERE user_id=? ORDER BY created_at',
            'assessments': 'SELECT mode,total,answered,correct,complete FROM assessments WHERE user_id=?',
            'messages': 'SELECT role,provider,content FROM messages WHERE user_id=? ORDER BY created_at',
            'projects': 'SELECT concept_id,status,submission,ai_disclosure,reflection,feedback FROM projects WHERE user_id=? AND submission IS NOT NULL',
            'telemetry_events': 'SELECT type,active_seconds,payload,occurred_at FROM telemetry_events WHERE user_id=? ORDER BY received_at',
        }
        for table, query in selections.items():
            records[table] = [dict(row) for row in connection.execute(query, (user_id,))] if table in tables else []
        for row in records['attempts']:
            row['payload'] = decoded_json(row['payload'])
            row['response'] = decoded_json(row['response'])
        feedback_text = normalized(observed_text(output, 'question-feedback'))
        attempts = records['attempts']
        checks['realPracticeAttempt'] = any(row['mode'] == 'practice' for row in attempts)
        checks['actualOptionAndReasoningPropagated'] = any(
            isinstance(row['payload'], dict) and row['payload'].get('option_id') == 'a'
            and row['payload'].get('reasoning') == 'I compared the options against the concept and will inspect the explanation to check my reasoning.'
            for row in attempts)
        checks['actualAttemptFeedbackRendered'] = any(
            isinstance(row['response'], dict) and bool(row['response'].get('explanation'))
            and normalized(row['response']['explanation']) in feedback_text for row in attempts)
        tutor_text = normalized(observed_text(output, 'tutor'))
        assistants = [row for row in records['messages'] if row['role'] == 'assistant' and row['content'].strip()]
        checks['actualAssistantReplyRendered'] = any(normalized(row['content']) in tutor_text for row in assistants)
        checks['actualUserMessagePersisted'] = any(row['role'] == 'user' and row['content'].startswith('Explain this concept step by step')
                                                   for row in records['messages'])
        checks['actualProjectSubmissionAndReflection'] = any(
            row['submission'].startswith('I used a small numerical example')
            and (row['reflection'] or '').startswith('Writing out each step')
            and (row['ai_disclosure'] or '').startswith('AI assistance was used')
            and bool(row['feedback']) for row in records['projects'])
        checks['explicitActivityConsentSaved'] = bool(account['telemetry_consent'])
        checks['goalFieldPropagated'] = account['goal'] == 'Verify real native learning workflows and reflect on mathematical reasoning'
        # First-run setup is only real if the server recorded it: the completion stamp and the
        # chosen course are written by the same request the sheet sends, so both must be present.
        checks['onboardingCompletedThroughRealUi'] = account['onboarding_completed_at'] is not None
        checks['enrolledCourseMatchesRequested'] = account['course_id'] == course
        checks['trainingConsentRemainsSeparate'] = not bool(account['training_consent'])
        checks['realForegroundHeartbeat'] = any(
            row['type'] == 'heartbeat' and row['active_seconds'] > 0 for row in records['telemetry_events'])
        checks['lastHeartbeatRecorded'] = account['last_heartbeat'] is not None
        return {'checks': checks, 'databaseCounts': counts, 'records': records}


def read_journeys(output):
    path = output / 'journeys.json'
    if not path.is_file():
        return {'journeys': [], 'error': 'journeys.json was never written'}
    return json.loads(path.read_text())


def journey_gate(document):
    """A journey gate passes only when all ten ran and none failed, gapped or blocked."""
    rows = document.get('journeys', [])
    statuses = {row.get('id'): row.get('status') for row in rows}
    failed = [k for k, v in statuses.items() if v == 'fail']
    gaps = [k for k, v in statuses.items() if v == 'gap']
    blocked = [k for k, v in statuses.items() if v == 'blocked']
    missing = [f'J{i}' for i in range(1, 11) if f'J{i}' not in statuses]
    return {'total': len(rows), 'passed': [k for k, v in statuses.items() if v == 'pass'],
            'failed': failed, 'gaps': gaps, 'blocked': blocked, 'missing': missing,
            'allGreen': len(rows) == 10 and not (failed or gaps or blocked or missing)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', '--executable', dest='app', type=Path,
                        default=HARNESS / 'native/.build/release/LearningHarness',
                        help='Already-built .app bundle or executable; this script never compiles')
    parser.add_argument('--port', '--qa-endpoint', dest='port', type=int, default=8765)
    parser.add_argument('--output', '--qa-output', dest='output', type=Path,
                        help='Fresh evidence directory (default: outputs/native-qa/<unique-run>)')
    parser.add_argument('--course', default='integrated_math_1',
                        help='Course the first-run setup sheet must select (proves multi-subject dispatch)')
    parser.add_argument('--skip-setup', action='store_true',
                        help='Exercise the returning-learner path: suppress the first-run course sheet')
    parser.add_argument('--capture-pages', default='',
                        help='Extra Page raw values to photograph after the verified workflow '
                             '(comma-separated, e.g. "today,review"). Non-fatal by design.')
    parser.add_argument('--name', default='',
                        help='Display name for the QA account. Presentation captures use a human '
                             'name so the header chip reads as a learner, not a test run. '
                             'Verification still checks the exact name this account registered with.')
    parser.add_argument('--capture-mode', action='store_true',
                        help='Presentation capture: hide the backend status pill and clear the '
                             'transient notice banner before each frame. Layout and state unchanged.')
    parser.add_argument('--backend-python', type=Path, default=HARNESS / 'ui-tests/.venv/bin/python')
    parser.add_argument('--timeout', type=float, default=420, help='Native process timeout in seconds')
    parser.add_argument('--journeys', action='store_true',
                        help='Run the ten golden student journeys through the app instead of the '
                             'legacy single workflow. Writes journeys.json next to the evidence.')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('Native QA requires macOS and an interactive desktop session')
    if not 1024 <= args.port <= 65535 or args.timeout <= 0:
        parser.error('Use a nonprivileged loopback port and a positive timeout')
    executable = executable_for(args.app)
    python = args.backend_python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        parser.error('Backend Python is missing; pass --backend-python with installed backend dependencies')
    run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4)
    output = (args.output or ROOT / 'outputs/native-qa' / run_id).expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('Use a fresh or empty output directory; existing evidence is never overwritten')
    output.mkdir(parents=True, exist_ok=True)
    state = output / 'state'
    state.mkdir()
    home = state / 'home'
    home.mkdir()
    database = state / 'harness.sqlite3'
    expected = {'name': args.name.strip() or 'Native QA ' + run_id,
                'email': 'native-' + run_id + '@example.com'}
    password = 'Qa-' + secrets.token_urlsafe(24) + '!'
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(('HARNESS_', 'NATIVE_QA_'))}
    environment.update({'HARNESS_ENV': 'test', 'HARNESS_DATA_DIR': str(state),
                        'HARNESS_DATABASE_URL': 'sqlite:///' + str(database), 'HARNESS_AUTO_CREATE': '1',
                        'HARNESS_PORT': str(args.port), 'HARNESS_SECRET': secrets.token_urlsafe(48),
                        'HARNESS_TUTOR_PROVIDER': 'offline', 'HARNESS_ALLOWED_HOSTS': '127.0.0.1,localhost',
                        'PYTHONDONTWRITEBYTECODE': '1'})
    command = [str(executable), '--ui-test', '--native-qa', '--qa-output', str(output),
               '--qa-endpoint', str(args.port)]
    if args.capture_mode:
        command.append('--capture-mode')
    summary = {'driver': 'in-process native AppKit accessibility (no external XCTest)', 'status': 'running',
               'port': args.port, 'output': str(output), 'command': command, 'expectedAccount': expected,
               'requestedCourse': args.course, 'capturePages': args.capture_pages,
               'captureMode': bool(args.capture_mode),
               'stateDirectory': str(state), 'databaseVerified': False,
               'permissionPolicy': 'Owned loopback backend, own app windows only, no app-state mutation fallback, no stored passwords'}
    summary_path = output / 'run-summary.json'
    save_json(summary_path, summary)
    backend = app = None
    exit_code = 1
    try:
        # Bind and keep ownership before spawning. Passing this socket to the child
        # eliminates the check-then-bind race and prevents trusting somebody else's port.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', args.port))
            listener.listen(128)
            bootstrap = (
                'import socket,sys; sys.path.insert(0,sys.argv[1]); import uvicorn; '
                'listener=socket.socket(fileno=int(sys.argv[2])); '
                'config=uvicorn.Config("app.main:create_app",factory=True,host="127.0.0.1",'
                'port=int(sys.argv[3]),access_log=False,proxy_headers=False); '
                'uvicorn.Server(config).run(sockets=[listener])'
            )
            with (output / 'backend.stdout.log').open('w') as stdout, (output / 'backend.stderr.log').open('w') as stderr:
                backend = subprocess.Popen([str(python), '-c', bootstrap, str(HARNESS / 'backend'),
                                            str(listener.fileno()), str(args.port)],
                                           cwd=ROOT, env=environment, pass_fds=(listener.fileno(),),
                                           stdout=stdout, stderr=stderr)
        summary['backendPID'] = backend.pid
        summary['stage'] = 'backend-readiness'
        save_json(summary_path, summary)
        deadline = time.monotonic() + 35
        # Ignore user-configured proxies: health belongs only to this inherited loopback socket.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            if backend.poll() is not None:
                raise RuntimeError(f'Owned backend exited {backend.returncode}; inspect backend stderr log')
            try:
                with opener.open(f'http://127.0.0.1:{args.port}/api/v1/health', timeout=1) as response:
                    health = json.load(response)
                if health.get('ready'):
                    summary['health'] = health
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError('Owned isolated backend did not become ready')
        app_environment = dict(environment, HOME=str(home), CFFIXED_USER_HOME=str(home),
                               NATIVE_QA_NAME=expected['name'], NATIVE_QA_EMAIL=expected['email'],
                               NATIVE_QA_PASSWORD=password, NATIVE_QA_COURSE=args.course,
                               NATIVE_QA_CAPTURE_PAGES=args.capture_pages,
                               NATIVE_QA_SKIP_SETUP='1' if args.skip_setup else '0',
                               NATIVE_QA_JOURNEYS='1' if args.journeys else '0')
        summary['stage'] = 'native-ui'
        save_json(summary_path, summary)
        with (output / 'app.stdout.log').open('w') as stdout, (output / 'app.stderr.log').open('w') as stderr:
            app = subprocess.Popen(command, cwd=ROOT, env=app_environment, stdout=stdout, stderr=stderr)
            summary['appPID'] = app.pid
            save_json(summary_path, summary)
            try:
                summary['appExitCode'] = app.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Native QA timed out; parent integration or real UI action may be blocked') from None
        if backend.poll() is not None:
            raise RuntimeError('Owned backend exited during native UI exercise')
        summary['stage'] = 'backend-verification'
    except (Exception, KeyboardInterrupt) as error:
        summary.update({'status': 'blocked', 'error': 'Interrupted' if isinstance(error, KeyboardInterrupt) else str(error)})
    finally:
        stop_owned(app)
        stop_owned(backend)
        # Read only our isolated database after the processes have stopped. Counts and
        # matching records corroborate real UI actions; no backend records are fabricated.
        try:
            evidence = inspect_database(database, output, python, expected, password, args.course)
            save_json(output / 'backend-evidence.json', evidence)
            summary['databaseCounts'] = evidence['databaseCounts']
            summary['checks'] = evidence['checks']
            summary['databaseVerified'] = bool(evidence['checks']) and all(evidence['checks'].values())
        except Exception as error:
            summary.update({'status': 'blocked', 'verificationError': str(error), 'databaseVerified': False})
        password = ''
        report_path = output / 'workflow-events.json'
        try:
            if report_path.is_file():
                native = json.loads(report_path.read_text())
            else:
                native = {'driver': 'in-process AppKit', 'status': 'blocked', 'workflowCompleted': False,
                          'events': [], 'screenshots': [],
                          'reason': 'No native evidence produced; integrate NativeQA.shared.runIfRequested() onAppear and rebuild'}
                save_json(report_path, native)
            summary['nativeStatus'] = native.get('status')
            if args.journeys:
                summary['journeys'] = read_journeys(output)
                summary['journeyGate'] = journey_gate(summary['journeys'])
                success = (summary.get('status') != 'blocked' and summary.get('appExitCode') == 0
                           and summary['journeyGate']['allGreen'])
                summary['status'] = 'passed' if success else 'blocked'
                summary['stage'] = 'finished'
                summary['databaseVerified'] = bool(summary.get('databaseCounts', {}).get('attempts', 0))
            summary['nativeFailures'] = native.get('failures', [])
            summary['screenshots'] = native.get('screenshots', [])
            files = [output / item['file'] for item in summary['screenshots']]
            summary['screenshotsPresent'] = bool(files) and all(
                path.is_file() and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for path in files)
            summary['screenshotsSuspectedBlank'] = any(item.get('suspectedBlank', False) for item in summary['screenshots'])
            success = (summary.get('status') != 'blocked' and summary.get('appExitCode') == 0
                       and native.get('status') == 'completed' and native.get('workflowCompleted') is True
                       and summary['databaseVerified'] and summary['screenshotsPresent']
                       and not summary['screenshotsSuspectedBlank'])
            summary['status'] = 'passed' if success else 'blocked'
            summary['stage'] = 'finished'
            summary['visualReview'] = 'Inspect actual PNG files; presence and pixel checks are not a human visual acceptance claim'
            exit_code = 0 if success else 1
        except Exception as error:
            summary.update({'status': 'blocked', 'nativeEvidenceError': str(error)})
        save_json(summary_path, summary)
    print(f'Native QA {summary["status"]}; evidence: {output}')
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
