#!/usr/bin/env python3
"""Probe the consented foreground-heartbeat contract against a real uvicorn server.

Runs the same request sequence the native client issues, and reports the
`active_seconds` the server actually credited. This separates a server-side
accounting fault from a client-side sending fault: the client can only lose an
interval that the server would otherwise have credited.
"""
import argparse
import json
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / 'harness'


def call(port, method, path, body=None, token=None, timeout=15):
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method=method)
    request.add_header('Content-Type', 'application/json')
    if token:
        request.add_header('Authorization', f'Bearer {token}')
    data = json.dumps(body).encode() if body is not None else None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, data=data, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


def heartbeat(interval):
    return {'events': [{'id': secrets.token_hex(8), 'type': 'heartbeat',
                        'occurred_at': datetime.now(timezone.utc).isoformat(),
                        'payload': {'window_active': True, 'interval_seconds': interval}}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8791)
    parser.add_argument('--gap', type=float, default=15.0,
                        help='Seconds between heartbeats; the client cadence is 15')
    args = parser.parse_args()
    python = HARNESS / 'ui-tests/.venv/bin/python'
    if not python.is_file():
        parser.error('Backend Python is missing')
    state = ROOT / 'outputs/probe-heartbeat'
    state.mkdir(parents=True, exist_ok=True)
    database = state / 'probe.sqlite3'
    if database.exists():
        database.unlink()
    environment = {'HARNESS_ENV': 'test', 'HARNESS_DATA_DIR': str(state),
                   'HARNESS_DATABASE_URL': 'sqlite:///' + str(database), 'HARNESS_AUTO_CREATE': '1',
                   'HARNESS_SECRET': secrets.token_urlsafe(48), 'HARNESS_TUTOR_PROVIDER': 'offline',
                   'HARNESS_ALLOWED_HOSTS': '127.0.0.1,localhost', 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                   'PYTHONDONTWRITEBYTECODE': '1'}
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
        server = subprocess.Popen([str(python), '-c', bootstrap, str(HARNESS / 'backend'),
                                   str(listener.fileno()), str(args.port)],
                                  cwd=ROOT, env=environment, pass_fds=(listener.fileno(),),
                                  stdout=open(state / 'backend.out.log', 'w'),
                                  stderr=open(state / 'backend.err.log', 'w'))
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                status, health = call(args.port, 'GET', '/api/v1/health')
                if status == 200 and health.get('ready'):
                    break
            except OSError:
                pass
            time.sleep(0.2)
        else:
            raise SystemExit('backend never became ready')
        stamp = secrets.token_hex(4)
        status, registered = call(args.port, 'POST', '/api/v1/auth/register',
                                  {'name': f'Probe {stamp}', 'email': f'probe-{stamp}@example.com',
                                   'password': 'Probe-' + secrets.token_urlsafe(16) + '!'})
        if status not in (200, 201):
            raise SystemExit(f'register failed {status}: {registered}')
        token = registered['token']
        call(args.port, 'PATCH', '/api/v1/me', {'telemetry_consent': True}, token=token)
        results = []
        for index in range(3):
            if index:
                time.sleep(args.gap)
            status, body = call(args.port, 'POST', '/api/v1/events', heartbeat(15.0), token=token)
            results.append({'send': index + 1, 'status': status, 'body': body})
        status, analytics = call(args.port, 'GET', '/api/v1/analytics', token=token)
        credited = [day['active_seconds'] for day in analytics.get('daily', [])]
        print(json.dumps({'gapSeconds': args.gap, 'sends': results,
                          'dailyActiveSeconds': credited,
                          'totalCredited': sum(credited)}, indent=2))
        return 0 if sum(credited) > 0 else 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == '__main__':
    sys.exit(main())
