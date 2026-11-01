#!/usr/bin/env python3
"""Probe the real tutor endpoint for every course.

The tutor resolved concepts against the mathematics graph regardless of enrolment, so a physics
learner's question produced no grounded reply. This checks the real HTTP path, not the unit.
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
    state = Path(tempfile.mkdtemp(prefix='chat-probe-'))
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
        token = call(base + '/auth/register', {
            'name': 'Chat Probe', 'email': 'chat@example.test',
            'password': 'long-secret-password'})['token']
        for course in COURSES:
            call(base + '/me', {'course_id': course, 'daily_minutes': 20}, token, method='PATCH')
            curriculum = call(base + '/curriculum', None, token)
            concepts = curriculum['concepts']
            concept_id = concepts[0]['id'] if concepts else ''
            try:
                reply = call(base + '/chat', {
                    'concept_id': concept_id, 'session_id': 'probe',
                    'message': 'Explain this concept step by step and give a small worked example.'},
                    token)
            except urllib.error.HTTPError as error:
                print(f'{course:22} HTTP {error.code}: {error.read()[:200]}')
                continue
            content = reply.get('content') or ''
            print(f'{course:22} concept={concept_id:34} reply_chars={len(content):5} '
                  f'provider={reply.get("provider")}')
            if len(content) < 80:
                print(f'    !! short reply: {content[:160]!r}')
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == '__main__':
    sys.exit(main())
