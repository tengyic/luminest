#!/usr/bin/env python3
"""Probe the real HTTP plan endpoint for every course, with a hard per-request timeout.

The native app hangs right after registration, which is the first moment the client calls
/plan. A pure-function planner test cannot catch a hang in the endpoint itself, so this
exercises the same uvicorn server the desktop app talks to.
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / 'harness'
PYTHON = HARNESS / 'ui-tests/.venv/bin/python'
COURSES = ['integrated_math_1', 'physics', 'chemistry', 'biology',
           'computer_science', 'earth_space_science']


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def call(url, payload=None, token=None, timeout=15, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data,
                                     method=method or ('POST' if data else 'GET'))
    request.add_header('Content-Type', 'application/json')
    if token:
        request.add_header('Authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def main():
    port = free_port()
    state = Path(tempfile.mkdtemp(prefix='plan-probe-'))
    environment = dict(os.environ)
    environment.update({
        'HARNESS_ENV': 'test', 'HARNESS_DATA_DIR': str(state),
        'HARNESS_DATABASE_URL': 'sqlite:///' + str(state / 'h.sqlite3'),
        'HARNESS_AUTO_CREATE': '1', 'HARNESS_PORT': str(port),
        'HARNESS_SECRET': secrets.token_urlsafe(48), 'HARNESS_TUTOR_PROVIDER': 'offline',
        'HARNESS_ALLOWED_HOSTS': '127.0.0.1,localhost',
    })
    server = subprocess.Popen(
        [str(PYTHON), '-m', 'uvicorn', 'app.main:create_app', '--factory',
         '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
        cwd=HARNESS / 'backend', env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f'http://127.0.0.1:{port}/api/v1'
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                if call(base + '/health', timeout=2).get('ready'):
                    break
            except (OSError, ValueError):
                time.sleep(0.2)
        else:
            raise SystemExit('server never became ready: ' + server.stderr.read().decode()[-800:])
        registered = call(base + '/auth/register', {
            'name': 'Plan Probe', 'email': 'probe@example.test',
            'password': 'long-secret-password'})
        token = registered['token']
        for course in COURSES:
            try:
                call(base + '/me', {'course_id': course, 'daily_minutes': 20}, token,
                     method='PATCH')
            except urllib.error.HTTPError as error:
                print(f'{course:22} PATCH failed {error.code}: {error.read()[:200]}')
                continue
            started = time.monotonic()
            try:
                plan = call(base + '/plan', None, token, timeout=20)
            except (TimeoutError, socket.timeout):
                print(f'{course:22} *** /plan HUNG (>{20}s) ***')
                continue
            except urllib.error.HTTPError as error:
                print(f'{course:22} /plan HTTP {error.code}: {error.read()[:300]}')
                continue
            elapsed = time.monotonic() - started
            print(f'{course:22} ok  {elapsed:5.2f}s  today={len(plan.get("today", []))} '
                  f'offered={plan.get("progress", {}).get("concepts_offered")} '
                  f'milestones={len(plan.get("milestones", []))}')
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == '__main__':
    sys.exit(main())
