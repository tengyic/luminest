#!/usr/bin/env python3
"""Probe the real practice-question path for every course, including grading.

The native Practice button produced no question sheet for a physics learner. The client shows
nothing when the request fails, so this checks the endpoint the button actually calls, and then
grades the item through the same attempt path the UI uses.
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
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / 'harness'
PYTHON = HARNESS / 'ui-tests/.venv/bin/python'
COURSES = ['integrated_math_1', 'physics', 'chemistry', 'biology',
           'computer_science', 'earth_space_science']


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def call(url, payload=None, token=None, timeout=30, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'))
    request.add_header('Content-Type', 'application/json')
    if token:
        request.add_header('Authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def main():
    port = free_port()
    state = Path(tempfile.mkdtemp(prefix='question-probe-'))
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
            raise SystemExit('server never became ready')
        for course in COURSES:
            token = call(base + '/auth/register', {
                'name': f'Q {course}', 'email': f'q-{course}@example.test',
                'password': 'long-secret-password'})['token']
            call(base + '/me', {'course_id': course, 'daily_minutes': 20}, token, method='PATCH')
            for mode in ('practice', 'diagnostic'):
                try:
                    question = call(base + f'/questions/next?mode={mode}', None, token)
                except urllib.error.HTTPError as error:
                    print(f'{course:22} {mode:11} HTTP {error.code}: {error.read()[:180]}')
                    continue
                options = question.get('options') or []
                answer = question.get('answer_id') or ''
                print(f'{course:22} {mode:11} q={question.get("id","")[:34]:34} '
                      f'options={len(options)} answer={answer!r} receipt={"receipt" in question}')
                if mode == 'practice' and options:
                    option_id = next((o['id'] for o in options if o['id'] != answer), options[0]['id'])
                    try:
                        graded = call(base + '/attempts', {
                            'question_id': question['id'], 'option_id': option_id,
                            'receipt': question['receipt'], 'client_event_id': str(uuid4()),
                            'elapsed_seconds': 12, 'reasoning': 'probe', 'confidence': 0.6}, token)
                        print(f'{"":22} {"grade":11} correct={graded.get("correct")} '
                              f'explanation_chars={len(graded.get("explanation") or "")}')
                    except urllib.error.HTTPError as error:
                        print(f'{"":22} {"grade":11} HTTP {error.code}: {error.read()[:180]}')
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == '__main__':
    sys.exit(main())
